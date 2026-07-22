"""Deterministically reconcile blinded V2 scientific adjudications."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from scripts.validation.public_gold.staged_event.assembly import (
    resolve_discovery_candidates,
)
from scripts.validation.public_gold.staged_event.contracts import EventDiscoveryOutput
from scripts.validation.public_gold.staged_event.diagnostic_projection import (
    DiagnosticProjectionError,
)

ALLOWED_LABELS = {
    "EXACT_GOLD_EVENT",
    "VALID_EXTRA_OUTSIDE_GOLD_POLICY",
    "WRONG_EVENT_TYPE",
    "WRONG_TRIGGER",
    "WRONG_PARTICIPANT",
    "WRONG_ROLE",
    "WRONG_NESTING",
    "WRONG_MODIFIER",
    "UNSUPPORTED_BY_SOURCE",
    "DEPENDS_ON_REJECTED_EVENT",
}
EXPECTED_ENTAILED = 32
GOLD_EVENT_DENOMINATOR = 30
MAXIMUM_UNRESOLVED_RATE = 0.2
V1_EXACT_EVENTS = 9
V1_FALSE_ACCEPTANCES = 15
V1_WRONG_ROLES = 16
V1_WRONG_NESTING = 9
V1_WRONG_MODIFIERS = 4


@dataclass(frozen=True, slots=True)
class ConsensusPaths:
    reviewer_a: Path
    reviewer_b: Path
    reviewer_c: Path
    staged_result: Path
    source: Path
    v1_adjudication: Path
    projection: Path


def reconcile_adjudications(
    *,
    paths: ConsensusPaths,
) -> dict[str, object]:
    """Validate reviewer custody and use a third vote only on A/B disputes."""

    staged = _load_object(paths.staged_result)
    source_text = paths.source.read_text(encoding="utf-8")
    stage_outputs = _object(staged, "stage_outputs")
    discovery = EventDiscoveryOutput.model_validate_json(
        json.dumps(_object(stage_outputs, "discovery"))
    )
    candidates = resolve_discovery_candidates(
        discovery.candidates,
        source_text=source_text,
        source_sha256=hashlib.sha256(paths.source.read_bytes()).hexdigest(),
    ).candidates
    verification = {
        _string(item, "event_id"): item
        for item in _object_list(_object(stage_outputs, "verification"), "events")
    }
    entailed_ids = {
        event_id
        for event_id, event in verification.items()
        if event.get("verdict") == "ENTAILED"
    }
    if len(entailed_ids) != EXPECTED_ENTAILED:
        raise DiagnosticProjectionError("V2 ENTAILED population changed")
    passages = {item.event_id: item.candidate.event_passage for item in candidates}

    reviewer_a = _review_index(paths.reviewer_a, entailed_ids, passages, source_text)
    reviewer_b = _review_index(paths.reviewer_b, entailed_ids, passages, source_text)
    disputed_ids = {
        event_id
        for event_id in entailed_ids
        if _categorical_signature(reviewer_a[event_id])
        != _categorical_signature(reviewer_b[event_id])
    }
    reviewer_c = _review_index(
        paths.reviewer_c, disputed_ids, passages, source_text, exact_population=True
    )

    consensus: list[dict[str, object]] = []
    unresolved: list[str] = []
    for event_id in sorted(entailed_ids):
        reviews = [reviewer_a[event_id], reviewer_b[event_id]]
        if event_id in disputed_ids:
            reviews.append(reviewer_c[event_id])
        benchmark = _majority_value(reviews, "benchmark_fidelity")
        source_validity = _majority_value(reviews, "source_validity")
        labels = sorted(
            label
            for label in ALLOWED_LABELS
            if sum(label in _labels(review) for review in reviews) > len(reviews) / 2
        )
        if benchmark is None or source_validity is None:
            unresolved.append(event_id)
            continue
        gold_id_votes = Counter(
            gold_id for review in reviews for gold_id in _gold_ids(review)
        )
        consensus.append(
            {
                "event_id": event_id,
                "labels": labels,
                "benchmark_fidelity": benchmark,
                "source_validity": source_validity,
                "gold_event_ids": sorted(
                    gold_id
                    for gold_id, count in gold_id_votes.items()
                    if count > len(reviews) / 2
                ),
                "exact_source_evidence": passages[event_id],
                "reviewer_votes": [
                    {
                        "reviewer": name,
                        "labels": sorted(_labels(review)),
                        "benchmark_fidelity": _normalized_benchmark(review),
                        "source_validity": _normalized_source_validity(review),
                    }
                    for name, review in zip(("A", "B", "C"), reviews, strict=False)
                ],
            }
        )
    unresolved_rate = len(unresolved) / EXPECTED_ENTAILED
    if unresolved_rate > MAXIMUM_UNRESOLVED_RATE:
        raise DiagnosticProjectionError("unresolved reviewer disagreement exceeds 20%")

    label_counts = Counter(
        label for row in consensus for label in _labels(row)
    )
    source_counts = Counter(
        _normalized_source_validity(row) for row in consensus
    )
    benchmark_counts = Counter(_normalized_benchmark(row) for row in consensus)
    false_acceptances = (
        source_counts["SUPPORTED_STRUCTURALLY_INCORRECT"]
        + source_counts["UNSUPPORTED"]
    )
    transitions = _case_transitions(paths.v1_adjudication, consensus)
    projection = _load_object(paths.projection)
    projection_metrics = _object(projection, "score")
    decision = _diagnostic_decision(
        {
            "exact_events": benchmark_counts["EXACT"],
            "false_acceptances": false_acceptances,
            "wrong_roles": label_counts["WRONG_ROLE"],
            "wrong_nesting": label_counts["WRONG_NESTING"],
            "wrong_modifiers": label_counts["WRONG_MODIFIER"],
            "unsupported": label_counts["UNSUPPORTED_BY_SOURCE"],
        }
    )
    return {
        "schema_version": "artana.public_gold.staged_event_v2_consensus.v1",
        "status": "ADJUDICATION_CONSENSUS_VALID",
        "qualification_status": "NON_QUALIFYING_DIAGNOSTIC_REVIEW_ONLY",
        "custody": {
            "reviewer_a_sha256": _sha256(paths.reviewer_a),
            "reviewer_b_sha256": _sha256(paths.reviewer_b),
            "reviewer_c_sha256": _sha256(paths.reviewer_c),
            "staged_result_sha256": _sha256(paths.staged_result),
            "source_sha256": _sha256(paths.source),
            "projection_sha256": _sha256(paths.projection),
        },
        "reviewer_agreement": {
            "a_b_complete_agreement": EXPECTED_ENTAILED - len(disputed_ids),
            "a_b_disagreement": len(disputed_ids),
            "a_b_agreement_rate": (
                (EXPECTED_ENTAILED - len(disputed_ids)) / EXPECTED_ENTAILED
            ),
            "third_reviewer_cases": len(reviewer_c),
            "unresolved_cases": unresolved,
            "unresolved_rate": unresolved_rate,
        },
        "metrics": {
            "exact_complete_gold_events": benchmark_counts["EXACT"],
            "gold_event_denominator": GOLD_EVENT_DENOMINATOR,
            "source_supported_complete_events": source_counts["SUPPORTED_COMPLETE"],
            "source_supported_structurally_incorrect_events": source_counts[
                "SUPPORTED_STRUCTURALLY_INCORRECT"
            ],
            "valid_extras_outside_gold_policy": label_counts[
                "VALID_EXTRA_OUTSIDE_GOLD_POLICY"
            ],
            "unsupported_claims": label_counts["UNSUPPORTED_BY_SOURCE"],
            "verifier_false_acceptances": false_acceptances,
            "verifier_false_acceptance_denominator": EXPECTED_ENTAILED,
            "verifier_false_acceptance_rate": false_acceptances / EXPECTED_ENTAILED,
            "failure_labels": dict(sorted(label_counts.items())),
        },
        "case_transitions": transitions,
        "closed_subgraph": {
            "projection": _object(projection, "projection"),
            "deterministic_score": projection_metrics,
        },
        "adjudications": consensus,
        "decision": decision,
        "trusted_promotion": False,
    }


def _review_index(
    path: Path,
    expected: set[str],
    passages: dict[str, str],
    source_text: str,
    *,
    exact_population: bool = True,
) -> dict[str, dict[str, object]]:
    payload = _load_object(path)
    rows = _object_list_alias(payload, ("reviews", "judgments"))
    index = {_string(row, "event_id"): row for row in rows}
    if len(index) != len(rows):
        raise DiagnosticProjectionError(f"{path}: duplicate review event IDs")
    if exact_population and set(index) != expected:
        raise DiagnosticProjectionError(f"{path}: reviewer population differs")
    for event_id, row in index.items():
        if event_id not in expected:
            raise DiagnosticProjectionError(f"{path}: unexpected event {event_id}")
        evidence = row.get(
            "exact_source_evidence", row.get("exact_evidence", row.get("evidence"))
        )
        if (
            not isinstance(evidence, str)
            or not evidence
            or evidence not in passages[event_id]
            or evidence not in source_text
        ):
            raise DiagnosticProjectionError(f"{path}: {event_id} evidence differs")
        if not _labels(row) <= ALLOWED_LABELS:
            raise DiagnosticProjectionError(f"{path}: {event_id} has invalid labels")
    return index


def _categorical_signature(row: dict[str, object]) -> tuple[object, ...]:
    return (
        tuple(sorted(_labels(row))),
        _normalized_benchmark(row),
        _normalized_source_validity(row),
    )


def _normalized_benchmark(row: dict[str, object]) -> str:
    value = _string(row, "benchmark_fidelity")
    return {
        "EXACT_GOLD_EVENT": "EXACT",
        "VALID_EXTRA_OUTSIDE_GOLD_POLICY": "OUTSIDE_GOLD_POLICY",
    }.get(value, value)


def _normalized_source_validity(row: dict[str, object]) -> str:
    value = _string(row, "source_validity")
    return {
        "SUPPORTED_COMPLETE_TYPED_EVENT": "SUPPORTED_COMPLETE",
        "SUPPORTED_CLAIM_BUT_TYPED_EVENT_INCORRECT": (
            "SUPPORTED_STRUCTURALLY_INCORRECT"
        ),
    }.get(value, value)


def _majority_value(
    rows: list[dict[str, object]], field: str
) -> str | None:
    values = [
        _normalized_benchmark(row)
        if field == "benchmark_fidelity"
        else _normalized_source_validity(row)
        for row in rows
    ]
    value, count = Counter(values).most_common(1)[0]
    return value if count > len(rows) / 2 else None


def _labels(row: dict[str, object]) -> set[str]:
    value = row.get("labels", row.get("failure_labels"))
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DiagnosticProjectionError("review labels must be strings")
    return set(value)


def _case_transitions(
    v1_path: Path, consensus: list[dict[str, object]]
) -> dict[str, object]:
    v1 = _load_object(v1_path)
    v1_rows = _object_list(v1, "adjudications")
    v1_exact = {
        _string(row, "gold_reference").split()[0]
        for row in v1_rows
        if _normalized_benchmark(row) == "EXACT"
    }
    v2_exact = {
        gold_id
        for row in consensus
        if _normalized_benchmark(row) == "EXACT"
        for gold_id in _gold_ids(row)
    }
    # Reviewer vote summaries intentionally omit evidence details. Recover exact IDs
    # from stable event identity by using the full V1 rows where possible and the
    # eight agreed V2 IDs supplied by both source-only reviewers.
    v2_exact_event_ids = {
        _string(row, "event_id")
        for row in consensus
        if _normalized_benchmark(row) == "EXACT"
    }
    v1_event_to_gold = {
        _string(row, "event_id"): _string(row, "gold_reference").split()[0]
        for row in v1_rows
        if _normalized_benchmark(row) == "EXACT"
    }
    v1_event_ids = {_string(row, "event_id") for row in v1_rows}
    wrong_labels = {
        "WRONG_EVENT_TYPE",
        "WRONG_TRIGGER",
        "WRONG_PARTICIPANT",
        "WRONG_ROLE",
        "WRONG_NESTING",
        "WRONG_MODIFIER",
    }
    v2_exact.update(
        v1_event_to_gold[event_id]
        for event_id in v2_exact_event_ids
        if event_id in v1_event_to_gold
    )
    all_gold = {f"E{index}" for index in range(1, GOLD_EVENT_DENOMINATOR + 1)}
    return {
        "wrong_to_correct": sorted(v2_exact - v1_exact),
        "correct_to_wrong": sorted(v1_exact - v2_exact),
        "unchanged_correct": sorted(v1_exact & v2_exact),
        "unchanged_wrong_count": len(all_gold - (v1_exact | v2_exact)),
        "newly_discovered_valid_extra_event_ids": sorted(
            _string(row, "event_id")
            for row in consensus
            if "VALID_EXTRA_OUTSIDE_GOLD_POLICY" in _labels(row)
            and _string(row, "event_id")
            not in v1_event_ids
        ),
        "newly_introduced_unsupported_event_ids": sorted(
            _string(row, "event_id")
            for row in consensus
            if "UNSUPPORTED_BY_SOURCE" in _labels(row)
        ),
        "newly_introduced_malformed_event_ids": sorted(
            _string(row, "event_id")
            for row in consensus
            if _string(row, "event_id") not in v1_event_ids
            and bool(_labels(row) & wrong_labels)
        ),
    }


def _diagnostic_decision(metrics: dict[str, int]) -> str:
    materially_improved = any(
        (
            metrics["exact_events"] > V1_EXACT_EVENTS,
            metrics["false_acceptances"] < V1_FALSE_ACCEPTANCES,
            metrics["wrong_roles"] < V1_WRONG_ROLES,
            metrics["wrong_nesting"] < V1_WRONG_NESTING,
            metrics["wrong_modifiers"] < V1_WRONG_MODIFIERS,
        )
    )
    if metrics["unsupported"] == 0 and materially_improved:
        return "CONTINUE_WITH_CONTEXT_EXPERIMENT"
    return "PIVOT_TO_SPECIALIST_CANDIDATES"


def _gold_ids(row: dict[str, object]) -> tuple[str, ...]:
    value = row.get("gold_event_ids", row.get("gold_ids", []))
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DiagnosticProjectionError("gold_event_ids must be strings")
    return tuple(value)


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DiagnosticProjectionError(f"{path} must contain an object")
    return value


def _object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise DiagnosticProjectionError(f"{key} must be an object")
    return value


def _object_list(payload: dict[str, object], key: str) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise DiagnosticProjectionError(f"{key} must be a list of objects")
    return value


def _object_list_alias(
    payload: dict[str, object], keys: tuple[str, ...]
) -> list[dict[str, object]]:
    for key in keys:
        if key in payload:
            return _object_list(payload, key)
    raise DiagnosticProjectionError(f"expected one of {keys}")


def _string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise DiagnosticProjectionError(f"{key} must be a non-empty string")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    parser.add_argument("--reviewer-c", type=Path, required=True)
    parser.add_argument("--staged-result", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--v1-adjudication", type=Path, required=True)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = reconcile_adjudications(
        paths=ConsensusPaths(
            reviewer_a=args.reviewer_a,
            reviewer_b=args.reviewer_b,
            reviewer_c=args.reviewer_c,
            staged_result=args.staged_result,
            source=args.source,
            v1_adjudication=args.v1_adjudication,
            projection=args.projection,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["metrics"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["ConsensusPaths", "reconcile_adjudications"]
