"""Build source-grounded context packets for the frozen semantic repair panel."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.assembly import (
    ResolvedCandidate,
    resolve_discovery_candidates,
)
from scripts.validation.public_gold.staged_event.contracts import (
    EventDiscoveryOutput,
    ParticipantInventoryOutput,
)

REPAIR_TARGET_IDS = frozenset(
    {
        "E-11f3a0578efc0b883103",
        "E-544748ccc8e6c17eb290",
        "E-66488a62883bb758e80b",
        "E-8498b84a9b3bb3e93c2f",
        "E-94edf9d8896d3f0729cb",
        "E-9b071863693a57dae92b",
        "E-a00865ea42e6f577581d",
        "E-b43186fccd287bbb1cd5",
        "E-d96f3f94563f9fce3286",
        "E-dc2596d35c7a939787a6",
        "E-e2a89e97c05e2b8d93d2",
        "E-2773996d557442a07d58",
    }
)
CONTROL_IDS = frozenset(
    {
        "E-0effc9409e12ed77b198",
        "E-205f021ad42236e5f142",
        "E-2d5bd3d8506d519d2d69",
        "E-60b0d54816b0585893d1",
    }
)
DEPENDENCY_CONTEXT_IDS = frozenset(
    {
        "E-7c96d5ccc6b62c1f4602",
        "E-c1c8f47ea535c511fb62",
        "E-cf483c0e6ea43235f767",
        "E-fd23ca8aac731381622e",
    }
)
PANEL_IDS = REPAIR_TARGET_IDS | CONTROL_IDS | DEPENDENCY_CONTEXT_IDS
WRONG_EVENT_TYPE_IDS = frozenset({"E-6a75a0999b748f2fe913", "E-a699191e71c887b4c5b8"})
NON_CREDITABLE_IDS = DEPENDENCY_CONTEXT_IDS | {"E-c1c8f47ea535c511fb62"}


class ContextPanelError(ValueError):
    """A preserved source or V2 identity cannot form the frozen panel."""


@dataclass(frozen=True, slots=True)
class ContextPanel:
    shared_context: dict[str, object]
    packets: tuple[dict[str, object], ...]
    candidates: tuple[ResolvedCandidate, ...]
    all_event_map: tuple[dict[str, object], ...]
    source_sha256: str


def build_context_panel(*, result_path: Path, source_path: Path) -> ContextPanel:
    result = _load_object(result_path)
    source_text = source_path.read_text(encoding="utf-8")
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    stages = _object(result, "stage_outputs")
    discovery = EventDiscoveryOutput.model_validate_json(
        json.dumps(_object(stages, "discovery"))
    )
    resolved = resolve_discovery_candidates(
        discovery.candidates,
        source_text=source_text,
        source_sha256=source_sha256,
    ).candidates
    candidate_index = {item.event_id: item for item in resolved}
    if not set(candidate_index) >= PANEL_IDS:
        raise ContextPanelError("frozen panel event IDs differ from V2")
    if PANEL_IDS & WRONG_EVENT_TYPE_IDS:
        raise ContextPanelError("wrong-event-type candidates entered repair panel")

    sentences = _sentence_spans(source_text)
    event_map = tuple(item.as_json() for item in resolved if item.event_id in PANEL_IDS)
    packets = tuple(
        _packet(
            candidate_index[event_id],
            sentences=sentences,
        )
        for event_id in sorted(PANEL_IDS)
    )
    return ContextPanel(
        shared_context={
            "source_text": source_text,
            "source_hash": source_sha256,
            "compact_event_map": list(event_map),
        },
        packets=packets,
        candidates=tuple(candidate_index[event_id] for event_id in sorted(PANEL_IDS)),
        all_event_map=event_map,
        source_sha256=source_sha256,
    )


def _packet(
    candidate: ResolvedCandidate,
    *,
    sentences: tuple[dict[str, object], ...],
) -> dict[str, object]:
    sentence_index = next(
        index
        for index, sentence in enumerate(sentences)
        if _int(sentence, "start") <= candidate.trigger_start
        and candidate.trigger_end <= _int(sentence, "end")
    )
    nearby = sentences[max(0, sentence_index - 1) : sentence_index + 2]
    classification = (
        "REPAIR_TARGET"
        if candidate.event_id in REPAIR_TARGET_IDS
        else "REGRESSION_CONTROL"
        if candidate.event_id in CONTROL_IDS
        else "DEPENDENCY_CONTEXT"
    )
    return {
        "event_id": candidate.event_id,
        "panel_classification": classification,
        "target_event": candidate.as_json(),
        "primary_evidence_sentence": sentences[sentence_index],
        "previous_sentence": sentences[sentence_index - 1] if sentence_index else None,
        "following_sentence": (
            sentences[sentence_index + 1]
            if sentence_index + 1 < len(sentences)
            else None
        ),
        "permitted_evidence_offsets": {
            "start": _int(nearby[0], "start"),
            "end": _int(nearby[-1], "end"),
        },
    }


def _sentence_spans(source_text: str) -> tuple[dict[str, object], ...]:
    spans: list[dict[str, object]] = []
    cursor = 0
    for match in re.finditer(r"(?<=[.!?])\s+", source_text):
        end = match.start()
        if end > cursor:
            spans.append({"start": cursor, "end": end, "text": source_text[cursor:end]})
        cursor = match.end()
    if cursor < len(source_text):
        spans.append(
            {"start": cursor, "end": len(source_text), "text": source_text[cursor:]}
        )
    if not spans:
        raise ContextPanelError("source contains no sentence spans")
    return tuple(spans)


def _participant_map(
    source_text: str, output: ParticipantInventoryOutput
) -> tuple[dict[str, object], ...]:
    exact_texts = sorted(
        {
            participant.exact_text
            for item in output.inventories
            for participant in item.participants
        }
    )
    mentions: list[dict[str, object]] = []
    for exact_text in exact_texts:
        starts = [
            match.start() for match in re.finditer(re.escape(exact_text), source_text)
        ]
        for index, start in enumerate(starts):
            mentions.append(
                {
                    "mention_id": f"mention-{hashlib.sha256(exact_text.encode()).hexdigest()[:12]}-{index}",
                    "exact_text": exact_text,
                    "occurrence_id": f"occurrence-{index}",
                    "occurrence_index": index,
                    "start": start,
                    "end": start + len(exact_text),
                }
            )
    return tuple(
        sorted(
            mentions, key=lambda item: (_int(item, "start"), str(item["mention_id"]))
        )
    )


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ContextPanelError(f"{path} must contain an object")
    return value


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ContextPanelError(f"{key} must be an object")
    return value


def _int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ContextPanelError(f"{key} must be an integer")
    return value


__all__ = [
    "build_context_panel",
    "ContextPanel",
    "ContextPanelError",
    "CONTROL_IDS",
    "NON_CREDITABLE_IDS",
    "PANEL_IDS",
    "REPAIR_TARGET_IDS",
]
