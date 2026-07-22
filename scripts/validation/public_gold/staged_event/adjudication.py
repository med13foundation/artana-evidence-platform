"""Validate and summarize the bounded staged-event scientific adjudication."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.assembly import (
    resolve_discovery_candidates,
)
from scripts.validation.public_gold.staged_event.contracts import EventDiscoveryOutput
from scripts.validation.public_gold.staged_event.paths import repository_root

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.assembly import ResolvedCandidate

EXPECTED_CANDIDATES = 34
GOLD_EVENT_DENOMINATOR = 30


class StagedAdjudicationError(ValueError):
    """The adjudication does not match its preserved exposed evidence."""


@dataclass(frozen=True, slots=True)
class _ValidatedRow:
    labels: tuple[str, ...]
    benchmark: str
    source_validity: str
    audit: str
    verdict: str


@dataclass(frozen=True, slots=True)
class _RowValidationContext:
    verification_events: dict[str, dict[str, object]]
    source_text: str
    allowed_labels: set[str]
    rule_catalog: dict[str, object]


def validate_and_summarize(
    *,
    adjudication_path: Path,
    staged_result_path: Path,
    source_path: Path,
    gold_path: Path,
) -> dict[str, object]:
    adjudication = _load_object(adjudication_path)
    staged_result = _load_object(staged_result_path)
    source_text = source_path.read_text(encoding="utf-8")
    _require_hash(adjudication, "staged_result_sha256", staged_result_path)
    _require_hash(adjudication, "source_sha256", source_path)
    _require_hash(adjudication, "gold_annotation_sha256", gold_path)

    stage_outputs = _require_object(staged_result, "stage_outputs")
    discovery = EventDiscoveryOutput.model_validate_json(
        json.dumps(_require_object(stage_outputs, "discovery"))
    )
    resolved = resolve_discovery_candidates(
        discovery.candidates,
        source_text=source_text,
        source_sha256=_require_string(adjudication, "source_sha256"),
    ).candidates
    candidates = {item.event_id: item for item in resolved}
    verification = _require_object(stage_outputs, "verification")
    verification_events = {
        _require_string(item, "event_id"): item
        for item in _require_object_list(verification, "events")
    }
    rule_catalog = _require_object(adjudication, "rule_catalog")
    allowed_labels = set(_require_string_list(adjudication, "allowed_failure_labels"))
    rows = _require_object_list(adjudication, "adjudications")
    if len(rows) != EXPECTED_CANDIDATES or len(candidates) != EXPECTED_CANDIDATES:
        raise StagedAdjudicationError("adjudication must cover all 34 candidates")
    if {_require_string(row, "event_id") for row in rows} != set(candidates):
        raise StagedAdjudicationError("adjudication event IDs differ from staged output")

    label_counts: Counter[str] = Counter()
    benchmark_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    audit_counts: Counter[str] = Counter()
    entailed = 0
    false_accepts = 0
    row_context = _RowValidationContext(
        verification_events=verification_events,
        source_text=source_text,
        allowed_labels=allowed_labels,
        rule_catalog=rule_catalog,
    )
    for row in rows:
        event_id = _require_string(row, "event_id")
        validated = _validate_row(
            row,
            candidate=candidates[event_id],
            context=row_context,
        )
        if validated.verdict == "ENTAILED":
            entailed += 1
            if validated.audit == "PLAUSIBLE_OR_PARTIAL_EVENT_ACCEPTED":
                false_accepts += 1
        label_counts.update(validated.labels)
        benchmark_counts[validated.benchmark] += 1
        source_counts[validated.source_validity] += 1
        audit_counts[validated.audit] += 1

    return {
        "schema_version": "artana.public_gold.staged_event_adjudication_result.v1",
        "status": "ADJUDICATION_VALID",
        "qualification_status": "EXPOSED_DEVELOPMENT_REVIEW_ONLY",
        "candidate_count": len(rows),
        "benchmark_fidelity": dict(sorted(benchmark_counts.items())),
        "source_validity": dict(sorted(source_counts.items())),
        "failure_labels": dict(sorted(label_counts.items())),
        "verifier_audit": {
            **dict(sorted(audit_counts.items())),
            "entailed_total": entailed,
            "false_accept_count": false_accepts,
            "false_accept_rate": false_accepts / entailed,
        },
        "benchmark_exact_gold_events_recovered": benchmark_counts["EXACT"],
        "benchmark_gold_event_denominator": GOLD_EVENT_DENOMINATOR,
        "benchmark_exact_recovery_rate": (
            benchmark_counts["EXACT"] / GOLD_EVENT_DENOMINATOR
        ),
        "source_supported_complete_events": source_counts[
            "SUPPORTED_COMPLETE_TYPED_EVENT"
        ],
        "unsupported_by_source": label_counts["UNSUPPORTED_BY_SOURCE"],
        "decision": "REVISE_ONCE",
    }


def _validate_row(
    row: dict[str, object],
    *,
    candidate: ResolvedCandidate,
    context: _RowValidationContext,
) -> _ValidatedRow:
    event_id = _require_string(row, "event_id")
    verifier = context.verification_events[event_id]
    if _require_string(row, "trigger") != candidate.candidate.trigger_text:
        raise StagedAdjudicationError(f"{event_id}: trigger differs")
    if (
        _require_string(row, "proposed_event_type")
        != candidate.candidate.source_event_type.value
    ):
        raise StagedAdjudicationError(f"{event_id}: event type differs")
    evidence = _require_string(row, "exact_source_evidence")
    if (
        evidence != candidate.candidate.event_passage
        or evidence not in context.source_text
    ):
        raise StagedAdjudicationError(f"{event_id}: evidence differs from source")
    verdict = _require_string(row, "verifier_verdict")
    if verdict != _require_string(verifier, "verdict"):
        raise StagedAdjudicationError(f"{event_id}: verifier verdict differs")
    labels = tuple(_require_string_list(row, "failure_labels"))
    if not set(labels) <= context.allowed_labels:
        raise StagedAdjudicationError(f"{event_id}: invalid failure labels")
    for rule_id in _require_string_list(row, "rule_ids"):
        if rule_id not in context.rule_catalog:
            raise StagedAdjudicationError(f"{event_id}: unknown rule {rule_id}")
    benchmark = _require_string(row, "benchmark_fidelity")
    if (benchmark == "EXACT") != ("EXACT_GOLD_EVENT" in labels):
        raise StagedAdjudicationError(f"{event_id}: exact-gold status contradicts labels")
    audit = _require_string(row, "verifier_audit")
    if verdict == "ENTAILED" and audit not in {
        "COMPLETE_TYPED_EVENT_ACCEPTED",
        "PLAUSIBLE_OR_PARTIAL_EVENT_ACCEPTED",
    }:
        raise StagedAdjudicationError(
            f"{event_id}: entailed event has an invalid audit category"
        )
    if verdict != "ENTAILED" and not audit.endswith("_REJECTED"):
        raise StagedAdjudicationError(
            f"{event_id}: rejected event has an invalid audit category"
        )
    return _ValidatedRow(
        labels=labels,
        benchmark=benchmark,
        source_validity=_require_string(row, "source_validity"),
        audit=audit,
        verdict=verdict,
    )


def write_report(path: Path, result: dict[str, object]) -> None:
    report = [
        "# Staged Event V1 Scientific Error Adjudication",
        "",
        "**Decision:** `REVISE_ONCE`",
        "",
        "This is an exposed-development, review-only adjudication. It does not change the terminal `INVALID_EXPERIMENT` result and gives no graph or qualification credit.",
        "",
        "## Deterministic Results",
        "",
        "```json",
        json.dumps(result, indent=2, sort_keys=True),
        "```",
        "",
        "## Interpretation",
        "",
        "Benchmark fidelity and source validity are different. Exact benchmark recovery requires the complete public gold event. Source-supported alternatives remain review-only and receive no benchmark credit.",
        "",
        "The verifier accepted many passages that were generally plausible but did not preserve the complete typed event. The next correction must verify event type, trigger, participants, roles, nesting, modifiers, and evidence independently and accept only when every axis passes.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(report) + "\n", encoding="utf-8")


def _require_hash(payload: dict[str, object], key: str, path: Path) -> None:
    if _require_string(payload, key) != hashlib.sha256(path.read_bytes()).hexdigest():
        raise StagedAdjudicationError(f"{key} does not match {path}")


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise StagedAdjudicationError(f"{path} must contain an object")
    return value


def _require_object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise StagedAdjudicationError(f"{key} must be an object")
    return value


def _require_object_list(
    payload: dict[str, object], key: str
) -> list[dict[str, object]]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise StagedAdjudicationError(f"{key} must be a list of objects")
    return value


def _require_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise StagedAdjudicationError(f"{key} must be a non-empty string")
    return value


def _require_string_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise StagedAdjudicationError(f"{key} must be a non-empty string list")
    return value


def main() -> int:
    root = repository_root()
    parser = argparse.ArgumentParser()
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--staged-result", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = validate_and_summarize(
        adjudication_path=root / args.adjudication,
        staged_result_path=root / args.staged_result,
        source_path=root / args.source,
        gold_path=root / args.gold,
    )
    result_path = root / args.result
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(root / args.report, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["StagedAdjudicationError", "validate_and_summarize", "write_report"]
