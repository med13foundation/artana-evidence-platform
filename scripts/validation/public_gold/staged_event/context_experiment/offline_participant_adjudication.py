"""Build deterministic packets for offline adjudication of rejected Luna participants."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.bionlp_cg_event_projection import (
    project_development_directory,
)
from scripts.validation.public_gold.staged_event.context_experiment.contracts import (
    SourceBoundParticipantOutput,
)
from scripts.validation.public_gold.staged_event.context_experiment.panel import (
    CONTROL_IDS,
    ContextPanel,
    build_context_panel,
)
from scripts.validation.public_gold.staged_event.context_experiment.preflight import (
    RESULT_PATH,
    SOURCE_PATH,
)
from scripts.validation.public_gold.staged_event.contracts import (
    ParticipantCandidate,
    ParticipantInventoryOutput,
)
from scripts.validation.public_gold.staged_event.paths import repository_root

if TYPE_CHECKING:
    from artana_evidence_api.document_extraction_support.scientific_events import (
        ScientificEvent,
        ScientificEventDocument,
        ScientificEventMention,
    )

RESPONSE_ID = "resp_0909915ba5830325006a60620dbff88198adf8625d389c717e"
PAYLOAD_SHA256 = "df430cd9d3db4d87a9d7172ffb7d1c98d007011146bd60faf3cf8237b0dc8e1f"


class OfflineParticipantAdjudicationError(ValueError):
    """Preserved diagnostic inputs cannot be aligned without inference."""


def build_packets(*, payload_path: Path) -> dict[str, object]:
    root = repository_root()
    payload_bytes = payload_path.read_bytes()
    payload = json.loads(payload_bytes)
    if _canonical_sha256(payload) != PAYLOAD_SHA256:
        raise OfflineParticipantAdjudicationError(
            "retrieved participant payload changed"
        )
    luna = SourceBoundParticipantOutput.model_validate_json(payload_bytes)
    panel = build_context_panel(
        result_path=root / RESULT_PATH,
        source_path=root / SOURCE_PATH,
    )
    source = str(panel.shared_context["source_text"])
    baseline = _baseline_output(root / RESULT_PATH)
    gold = next(
        item
        for item in project_development_directory((root / SOURCE_PATH).parent)
        if item.document_id == "PMID-16428936"
    )
    mentions = {item.annotation_id: item for item in gold.mentions}
    events = {item.annotation_id: item for item in gold.events}
    candidate_gold = _candidate_gold_events(panel, gold)
    expected = {
        event_id: _expected_participants(
            events[gold_event_id], events=events, mentions=mentions
        )
        for event_id, gold_event_id in candidate_gold.items()
    }
    baseline_index = {item.event_id: item for item in baseline.inventories}
    luna_index = {item.event_id: item for item in luna.inventories}
    packets: list[dict[str, object]] = []
    event_summaries: list[dict[str, object]] = []
    for candidate in panel.candidates:
        event_id = candidate.event_id
        gold_participants = expected.get(event_id, ())
        baseline_participants = tuple(
            _baseline_participant(item, source=source)
            for item in baseline_index[event_id].participants
        )
        luna_participants = tuple(
            item.model_dump(mode="json") for item in luna_index[event_id].participants
        )
        baseline_exact = _prediction_set_matches_gold(
            baseline_participants,
            gold_participants,
            has_gold_event=event_id in candidate_gold,
        )
        luna_exact = _prediction_set_matches_gold(
            luna_participants,
            gold_participants,
            has_gold_event=event_id in candidate_gold,
        )
        event_summaries.append(
            {
                "event_id": event_id,
                "gold_event_id": candidate_gold.get(event_id),
                "control_event": event_id in CONTROL_IDS,
                "gold_participants": list(gold_participants),
                "baseline_participants": list(baseline_participants),
                "luna_participants": list(luna_participants),
                "baseline_exact_participant_set": baseline_exact,
                "luna_exact_participant_set": luna_exact,
                "transition": (
                    "WRONG_TO_CORRECT"
                    if not baseline_exact and luna_exact
                    else "CORRECT_TO_WRONG"
                    if baseline_exact and not luna_exact
                    else "PRESERVED_CORRECT"
                    if baseline_exact and luna_exact
                    else "PRESERVED_WRONG"
                ),
            }
        )
        for index, participant in enumerate(luna_index[event_id].participants):
            resolved = source[participant.start : participant.end]
            exact_span_valid = resolved == participant.exact_text
            exact_gold = _matches_gold(
                participant.model_dump(mode="json"), gold_participants
            )
            packets.append(
                {
                    "participant_id": f"{event_id}:P{index + 1}",
                    "event_id": event_id,
                    "panel_classification": next(
                        str(packet["panel_classification"])
                        for packet in panel.packets
                        if packet["event_id"] == event_id
                    ),
                    "target_event": candidate.as_json(),
                    "source_passage": candidate.as_json()["event_passage"],
                    "permitted_evidence_offsets": next(
                        packet["permitted_evidence_offsets"]
                        for packet in panel.packets
                        if packet["event_id"] == event_id
                    ),
                    "luna_participant": participant.model_dump(mode="json"),
                    "resolved_source_text": resolved,
                    "exact_span_valid": exact_span_valid,
                    "exact_gold_participant": exact_gold and exact_span_valid,
                    "counterfactual_exact_gold_if_offset_valid": (
                        _matches_gold_semantics(
                            participant.model_dump(mode="json"), gold_participants
                        )
                    ),
                    "gold_event_id": candidate_gold.get(event_id),
                    "gold_participants": list(gold_participants),
                    "baseline_participants": list(baseline_participants),
                    "control_event": event_id in CONTROL_IDS,
                    "review_required": not exact_gold or not exact_span_valid,
                }
            )
    return {
        "schema_version": "artana.public_gold.luna_participant_packets.v1",
        "document_id": "PMID-16428936",
        "source_sha256": panel.source_sha256,
        "response_id": RESPONSE_ID,
        "retrieved_payload_sha256": PAYLOAD_SHA256,
        "retrieval_mode": "EXISTING_RESPONSE_RETRIEVAL_NO_GENERATION",
        "participant_count": len(packets),
        "gold_mapped_event_count": len(candidate_gold),
        "event_summaries": event_summaries,
        "packets": packets,
    }


def deterministic_metrics(packet_set: dict[str, object]) -> dict[str, object]:
    packets = _list_of_objects(packet_set, "packets")
    event_summaries = _list_of_objects(packet_set, "event_summaries")
    exact = len([item for item in packets if bool(item["exact_gold_participant"])])
    offset_failures = len(
        [item for item in packets if not bool(item["exact_span_valid"])]
    )
    labels = Counter(
        label
        for item in packets
        for label in _string_list(item.get("consensus_labels", []))
        if isinstance(label, str)
    )
    gold_total = sum(
        len(_list_of_objects(item, "gold_participants"))
        for item in event_summaries
        if item.get("gold_event_id") is not None
    )
    return {
        "participant_predictions": len(packets),
        "exact_gold_participants": exact,
        "exact_participant_span_precision": exact / len(packets) if packets else 0.0,
        "exact_participant_span_recall": exact / gold_total if gold_total else 0.0,
        "gold_participant_denominator": gold_total,
        "offset_failures": offset_failures,
        "wrong_to_correct_events": sorted(
            str(item["event_id"])
            for item in event_summaries
            if item["transition"] == "WRONG_TO_CORRECT"
        ),
        "correct_to_wrong_events": sorted(
            str(item["event_id"])
            for item in event_summaries
            if item["transition"] == "CORRECT_TO_WRONG"
        ),
        "correct_controls_preserved": sorted(
            str(item["event_id"])
            for item in event_summaries
            if item["control_event"] and item["transition"] == "PRESERVED_CORRECT"
        ),
        "label_counts": dict(sorted(labels.items())),
    }


def _candidate_gold_events(
    panel: ContextPanel, gold: ScientificEventDocument
) -> dict[str, str]:
    gold_mentions = {item.annotation_id: item for item in gold.mentions}
    result: dict[str, str] = {}
    for candidate in panel.candidates:
        source_type = str(candidate.as_json()["source_event_type"])
        matches = [
            event.annotation_id
            for event in gold.events
            if event.source_event_type == source_type
            and gold_mentions[event.trigger_id].span.start == candidate.trigger_start
            and gold_mentions[event.trigger_id].span.end == candidate.trigger_end
        ]
        if len(matches) > 1:
            raise OfflineParticipantAdjudicationError(
                "candidate maps to multiple gold events"
            )
        if matches:
            result[candidate.event_id] = matches[0]
    return result


def _expected_participants(
    event: ScientificEvent,
    *,
    events: Mapping[str, ScientificEvent],
    mentions: Mapping[str, ScientificEventMention],
) -> tuple[dict[str, object], ...]:
    expected: list[dict[str, object]] = []
    for argument in event.arguments:
        if argument.target_kind.value == "PARTICIPANT":
            mention = mentions[argument.target_id]
            expected.append(
                {
                    "target_kind": "PARTICIPANT",
                    "start": mention.span.start,
                    "end": mention.span.end,
                    "exact_text": mention.span.exact_text,
                    "source_entity_type": mention.source_type,
                }
            )
        else:
            nested = events[argument.target_id]
            trigger = mentions[nested.trigger_id]
            expected.append(
                {
                    "target_kind": "EVENT",
                    "start": trigger.span.start,
                    "end": trigger.span.end,
                    "exact_text": trigger.span.exact_text,
                    "source_entity_type": None,
                }
            )
    return tuple(expected)


def _matches_gold(
    participant: dict[str, object], expected: tuple[dict[str, object], ...]
) -> bool:
    return any(
        participant.get("candidate_target_kind") == item["target_kind"]
        and participant.get("start") == item["start"]
        and participant.get("end") == item["end"]
        and participant.get("exact_text") == item["exact_text"]
        and participant.get("source_entity_type") == item["source_entity_type"]
        for item in expected
    )


def _matches_gold_semantics(
    participant: dict[str, object], expected: tuple[dict[str, object], ...]
) -> bool:
    return any(
        participant.get("candidate_target_kind") == item["target_kind"]
        and participant.get("exact_text") == item["exact_text"]
        and participant.get("source_entity_type") == item["source_entity_type"]
        for item in expected
    )


def _prediction_set_matches_gold(
    predictions: tuple[dict[str, object], ...],
    expected: tuple[dict[str, object], ...],
    *,
    has_gold_event: bool,
) -> bool:
    if not has_gold_event:
        return False
    predicted_counter = Counter(_participant_signature(item) for item in predictions)
    expected_counter = Counter(_participant_signature(item) for item in expected)
    return predicted_counter == expected_counter


def _participant_signature(item: dict[str, object]) -> tuple[object, ...]:
    return (
        item.get("candidate_target_kind", item.get("target_kind")),
        item.get("start"),
        item.get("end"),
        item.get("exact_text"),
        item.get("source_entity_type"),
    )


def _baseline_participant(
    participant: ParticipantCandidate, *, source: str
) -> dict[str, object]:
    starts: list[int] = []
    cursor = 0
    while True:
        found = source.find(participant.exact_text, cursor)
        if found < 0:
            break
        starts.append(found)
        cursor = found + 1
    start = (
        starts[participant.occurrence_index]
        if participant.occurrence_index < len(starts)
        else None
    )
    return {
        **participant.model_dump(mode="json"),
        "start": start,
        "end": start + len(participant.exact_text) if start is not None else None,
    }


def _baseline_output(path: Path) -> ParticipantInventoryOutput:
    result = json.loads(path.read_text(encoding="utf-8"))
    return ParticipantInventoryOutput.model_validate_json(
        json.dumps(result["stage_outputs"]["participants"])
    )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _list_of_objects(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise OfflineParticipantAdjudicationError(f"{key} must be a list of objects")
    return value


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return value


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("payload", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    packets = build_packets(payload_path=args.payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(packets, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(deterministic_metrics(packets), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
