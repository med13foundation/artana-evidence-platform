"""Resolve blinded participant reviews and calculate the offline advance gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from scripts.validation.public_gold.staged_event.context_experiment.offline_participant_adjudication import (
    deterministic_metrics,
)


class ParticipantConsensusError(ValueError):
    """Reviewer artifacts cannot be combined without weakening custody."""


MINIMUM_WRONG_TO_CORRECT = 2


def build_consensus(
    *,
    packets_path: Path,
    reviewer_a_path: Path,
    reviewer_b_path: Path,
    reviewer_c_path: Path,
) -> dict[str, object]:
    packets = _load_object(packets_path)
    packet_items = _index(_objects(packets, "packets"))
    reviewer_a = _load_object(reviewer_a_path)
    reviewer_b = _load_object(reviewer_b_path)
    reviewer_c = _load_object(reviewer_c_path)
    a = _index(_objects(reviewer_a, "judgments"))
    b = _index(_objects(reviewer_b, "judgments"))
    raw_c = _index(_objects(reviewer_c, "judgments"))
    if set(a) != set(packet_items) or set(b) != set(packet_items):
        raise ParticipantConsensusError(
            "primary reviewer population differs from packets"
        )
    disagreements = sorted(
        key for key in packet_items if _labels(a[key]) != _labels(b[key])
    )
    c = _normalize_tiebreak_ids(raw_c, expected=set(disagreements))
    if set(c) != set(disagreements):
        raise ParticipantConsensusError(
            "tie-break reviewer population differs from disagreements"
        )
    judgments: list[dict[str, object]] = []
    for participant_id in sorted(packet_items):
        agreed = _labels(a[participant_id]) == _labels(b[participant_id])
        resolution = a[participant_id] if agreed else c[participant_id]
        judgments.append(
            {
                "participant_id": participant_id,
                "event_id": packet_items[participant_id]["event_id"],
                "labels": sorted(_labels(resolution)),
                "exact_evidence": resolution.get(
                    "exact_evidence", resolution.get("exact_source_evidence")
                ),
                "explanation": resolution.get("explanation"),
                "resolution": "A_B_AGREEMENT" if agreed else "BLINDED_REVIEWER_C",
                "reviewer_a_labels": sorted(_labels(a[participant_id])),
                "reviewer_b_labels": sorted(_labels(b[participant_id])),
                "reviewer_c_labels": (
                    sorted(_labels(c[participant_id])) if not agreed else None
                ),
            }
        )
    metrics = _metrics(packets, judgments, disagreements)
    decision = (
        "ADVANCE_TO_LUNA_MICRO_CANARY"
        if _passes_advance_gate(metrics)
        else "PIVOT_TO_SPECIALIST_CANDIDATES"
    )
    return {
        "schema_version": "artana.public_gold.luna_participant_consensus.v1",
        "decision": decision,
        "document_id": packets["document_id"],
        "source_sha256": packets["source_sha256"],
        "retrieved_payload_sha256": packets["retrieved_payload_sha256"],
        "reviewer_provenance": {
            "reviewer_a_sha256": _sha256(reviewer_a_path),
            "reviewer_b_sha256": _sha256(reviewer_b_path),
            "reviewer_c_sha256": _sha256(reviewer_c_path),
            "independence": "BLINDED_INTERNAL_CODEX_SUBAGENTS_NO_PROVIDER_CALLS",
        },
        "metrics": metrics,
        "judgments": judgments,
        "micro_canary_executed": False,
    }


def _metrics(
    packets: dict[str, object],
    judgments: list[dict[str, object]],
    disagreements: list[str],
) -> dict[str, object]:
    deterministic = deterministic_metrics(packets)
    labels = Counter(label for judgment in judgments for label in _labels(judgment))
    event_summaries = _objects(packets, "event_summaries")
    mapped = [item for item in event_summaries if item.get("gold_event_id") is not None]
    required_event_ids = {
        str(item["event_id"]) for item in mapped if _objects(item, "gold_participants")
    }
    exact_event_ids = {
        str(item["event_id"])
        for item in mapped
        if bool(item["luna_exact_participant_set"])
    }
    preserved_controls = set(_string_list(deterministic["correct_controls_preserved"]))
    preserved_controls.update(
        str(item["event_id"])
        for item in mapped
        if item["control_event"]
        and not _objects(item, "baseline_participants")
        and not _objects(item, "luna_participants")
        and not _objects(item, "gold_participants")
    )
    return {
        **deterministic,
        "label_counts": dict(sorted(labels.items())),
        "correct_controls_preserved": sorted(preserved_controls),
        "reviewer_a_b_exact_agreements": len(judgments) - len(disagreements),
        "reviewer_a_b_disagreements": len(disagreements),
        "reviewer_a_b_disagreement_rate": len(disagreements) / len(judgments),
        "resolved_by_blinded_third_reviewer": len(disagreements),
        "unresolved_disagreements": 0,
        "unresolved_disagreement_rate": 0.0,
        "reviewer_agreement_gate_passed": True,
        "source_supported_equivalents": labels["SOURCE_SUPPORTED_EQUIVALENT"],
        "unsupported_extras": labels["EXTRA_UNSUPPORTED_PARTICIPANT"],
        "wrong_participants": labels["WRONG_PARTICIPANT"],
        "wrong_entity_types": labels["WRONG_ENTITY_TYPE"],
        "ambiguous_references": labels["AMBIGUOUS_REFERENCE"],
        "occurrence_identity_contract_mismatches": labels[
            "OCCURRENCE_IDENTITY_CONTRACT_MISMATCH"
        ],
        "required_primary_event_count": len(required_event_ids),
        "complete_primary_participant_event_count": len(
            required_event_ids & exact_event_ids
        ),
        "missing_primary_event_ids": sorted(required_event_ids - exact_event_ids),
        "entity_type_fidelity_count": sum(
            "WRONG_ENTITY_TYPE" not in _labels(item)
            and (
                "EXACT_GOLD_PARTICIPANT" in _labels(item)
                or "SOURCE_SUPPORTED_EQUIVALENT" in _labels(item)
            )
            for item in judgments
        ),
        "entity_type_fidelity_denominator": len(judgments),
    }


def _passes_advance_gate(metrics: dict[str, object]) -> bool:
    wrong_to_correct = metrics.get("wrong_to_correct_events")
    correct_to_wrong = metrics.get("correct_to_wrong_events")
    return (
        isinstance(wrong_to_correct, list)
        and len(wrong_to_correct) >= MINIMUM_WRONG_TO_CORRECT
        and isinstance(correct_to_wrong, list)
        and not correct_to_wrong
        and metrics.get("unsupported_extras") == 0
        and not metrics.get("missing_primary_event_ids")
        and metrics.get("reviewer_agreement_gate_passed") is True
    )


def _index(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result = {str(item["participant_id"]): item for item in items}
    if len(result) != len(items):
        raise ParticipantConsensusError("participant IDs are duplicated")
    return result


def _normalize_tiebreak_ids(
    items: dict[str, dict[str, object]], *, expected: set[str]
) -> dict[str, dict[str, object]]:
    normalized: dict[str, dict[str, object]] = {}
    for participant_id, judgment in items.items():
        target = participant_id
        if target not in expected:
            candidates = [item for item in expected if item.startswith(f"{target}:")]
            if len(candidates) != 1:
                raise ParticipantConsensusError(
                    "tie-break participant ID cannot be normalized uniquely"
                )
            target = candidates[0]
        if target in normalized:
            raise ParticipantConsensusError("normalized tie-break ID is duplicated")
        normalized[target] = {**judgment, "participant_id": target}
    return normalized


def _labels(item: dict[str, object]) -> set[str]:
    value = item.get("labels")
    if not isinstance(value, list) or not all(
        isinstance(label, str) for label in value
    ):
        raise ParticipantConsensusError("review labels are malformed")
    return set(value)


def _objects(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ParticipantConsensusError(f"{key} must be a list of objects")
    return value


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return []
    return value


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ParticipantConsensusError(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packets", type=Path)
    parser.add_argument("reviewer_a", type=Path)
    parser.add_argument("reviewer_b", type=Path)
    parser.add_argument("reviewer_c", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    consensus = build_consensus(
        packets_path=args.packets,
        reviewer_a_path=args.reviewer_a,
        reviewer_b_path=args.reviewer_b,
        reviewer_c_path=args.reviewer_c,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(consensus, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(consensus["decision"])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
