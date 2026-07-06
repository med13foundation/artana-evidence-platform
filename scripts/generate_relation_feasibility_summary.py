#!/usr/bin/env python3
"""Generate Markdown evidence summaries from relation feasibility JSON artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

JSONObject = dict[str, object]

_KEY_METRICS = (
    "case_count",
    "gold_relation_count",
    "candidate_count",
    "completed_agent_candidate_count",
    "completed_agent_precision_against_gold",
    "completed_agent_recall_against_gold",
    "high_value_recall",
    "trusted_high_value_recall",
    "high_value_review_gold_relation_count",
    "high_value_review_candidate_count",
    "high_value_review_gold_match_count",
    "high_value_review_recall",
    "low_value_review_recall",
    "trusted_eligible_curie_linked_gold_endpoint_rate",
    "candidate_curie_present_rate",
    "verified_curie_match_rate",
    "valuable_candidate_rate",
    "completed_agent_valuable_candidate_rate",
    "generic_relation_rate",
    "raw_unknown_relation_type_count",
    "raw_unknown_relation_type_surface_count",
    "model_curie_wrong_count",
    "wrong_verified_curie_link_count",
    "fallback_case_count",
    "invalid_agent_case_count",
    "negative_control_leakage_count",
    "weak_claim_trusted_leakage_count",
)


@dataclass(frozen=True, slots=True)
class GenerateSummaryInput:
    """Inputs for one generated evidence summary."""

    relation_report: Path
    branch: str
    commit: str
    command: str
    model_label: str
    fixture_path: Path
    output_path: Path | None = None
    failure_analysis_report: Path | None = None
    readiness_report: Path | None = None


def generate_summary_markdown(summary_input: GenerateSummaryInput) -> str:
    """Return a generated Markdown evidence summary."""

    relation_payload = _load_json_object(summary_input.relation_report)
    relation_summary = _object(relation_payload.get("summary"))
    failure_payload = (
        _load_json_object(summary_input.failure_analysis_report)
        if summary_input.failure_analysis_report is not None
        else None
    )
    readiness_payload = (
        _load_json_object(summary_input.readiness_report)
        if summary_input.readiness_report is not None
        else None
    )
    artifact_paths = [
        summary_input.relation_report,
        summary_input.failure_analysis_report,
        summary_input.readiness_report,
    ]
    lines = [
        "# Relation Feasibility Generated Summary",
        "",
        "## Run Context",
        "",
        f"- Branch: `{summary_input.branch}`",
        f"- Commit: `{summary_input.commit}`",
        f"- Command: `{summary_input.command}`",
        f"- Model label: `{summary_input.model_label}`",
        f"- Fixture path: `{summary_input.fixture_path}`",
        "",
        "## Artifact Hashes",
        "",
    ]
    for artifact_path in artifact_paths:
        if artifact_path is not None:
            lines.append(
                f"- `{artifact_path.name}`: `{_sha256_file(artifact_path)}`",
            )
    lines.extend(
        [
            "",
            "## Key Metrics",
            "",
            f"- Verdict: `{relation_summary.get('verdict', 'unknown')}`",
        ],
    )
    lines.extend(_metric_lines(relation_summary))
    lines.extend(
        [
            "",
            "## Blocking Reasons",
            "",
        ],
    )
    blocking_reasons = [
        *_string_list(relation_summary.get("blocking_reasons")),
        *_string_list(
            readiness_payload.get("blocking_reasons")
            if readiness_payload is not None
            else None,
        ),
    ]
    lines.extend(_bullet_lines(blocking_reasons))
    lines.extend(
        [
            "",
            "## Warning Reasons",
            "",
        ],
    )
    warning_reasons = _string_list(relation_summary.get("warning_reasons"))
    lines.extend(_bullet_lines(warning_reasons))
    lines.extend(
        [
            "",
            "## Remaining Failures",
            "",
        ],
    )
    remaining_failures = [
        *_missed_gold_lines(relation_payload),
        *_failure_analysis_lines(failure_payload),
    ]
    lines.extend(_bullet_lines(remaining_failures))
    if readiness_payload is not None:
        lines.extend(
            [
                "",
                "## Readiness",
                "",
                f"- Status: `{readiness_payload.get('readiness_status', 'unknown')}`",
            ],
        )
        lines.extend(_object_metric_lines(_object(readiness_payload.get("worst_metrics"))))
        lines.extend(
            _object_metric_lines(_object(readiness_payload.get("hard_failure_counts"))),
        )
    return "\n".join(lines) + "\n"


def write_generated_summary(summary_input: GenerateSummaryInput) -> Path:
    """Write one generated Markdown summary and return its path."""

    output_path = summary_input.output_path
    if output_path is None:
        output_path = summary_input.relation_report.with_name(
            "relation_feasibility_generated_summary.md",
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generate_summary_markdown(summary_input), encoding="utf-8")
    return output_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Generate a Markdown summary from relation feasibility JSON.",
    )
    parser.add_argument("--relation-report", type=Path, required=True)
    parser.add_argument("--failure-analysis-report", type=Path)
    parser.add_argument("--readiness-report", type=Path)
    parser.add_argument("--output-path", type=Path, required=True)
    parser.add_argument("--branch", default=None)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--command", required=True)
    parser.add_argument("--model-label", required=True)
    parser.add_argument("--fixture-path", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate a Markdown evidence summary from the CLI."""

    args = parse_args(argv)
    output_path = write_generated_summary(
        GenerateSummaryInput(
            relation_report=args.relation_report,
            failure_analysis_report=args.failure_analysis_report,
            readiness_report=args.readiness_report,
            output_path=args.output_path,
            branch=args.branch or _git_output(("branch", "--show-current")),
            commit=args.commit or _git_output(("rev-parse", "--short", "HEAD")),
            command=args.command,
            model_label=args.model_label,
            fixture_path=args.fixture_path,
        ),
    )
    print(f"Wrote generated summary: {output_path}")
    return 0


def _load_json_object(path: Path) -> JSONObject:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"{path} must contain a JSON object"
        raise TypeError(msg)
    return payload


def _object(value: object) -> JSONObject:
    return dict(value) if isinstance(value, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _metric_lines(summary: JSONObject) -> list[str]:
    lines: list[str] = []
    for metric in _KEY_METRICS:
        if metric in summary:
            lines.append(f"- {metric}: {summary[metric]}")
    return lines


def _object_metric_lines(metrics: JSONObject) -> list[str]:
    return [f"- {key}: {value}" for key, value in sorted(metrics.items())]


def _bullet_lines(values: Sequence[str]) -> list[str]:
    if not values:
        return ["- none"]
    return [f"- {value}" for value in values]


def _missed_gold_lines(relation_payload: JSONObject) -> list[str]:
    lines: list[str] = []
    raw_case_results = relation_payload.get("case_results")
    if not isinstance(raw_case_results, list):
        return lines
    for raw_case_result in raw_case_results:
        if not isinstance(raw_case_result, dict):
            continue
        case = _object(raw_case_result.get("case"))
        case_id = str(case.get("case_id", "unknown_case"))
        missed_gold = raw_case_result.get("missed_gold_relations")
        if not isinstance(missed_gold, list):
            continue
        for raw_relation in missed_gold:
            relation = _object(raw_relation)
            lines.append(
                f"{case_id}: {_relation_label(relation)}",
            )
    return lines


def _failure_analysis_lines(failure_payload: JSONObject | None) -> list[str]:
    if failure_payload is None:
        return []
    lines: list[str] = []
    for key in ("repeated_missed_gold_relations", "repeated_false_positive_candidates"):
        raw_rows = failure_payload.get(key)
        if not isinstance(raw_rows, list):
            continue
        for raw_row in raw_rows[:10]:
            row = _object(raw_row)
            case_id = str(row.get("case_id", "unknown_case"))
            lines.append(f"{key}: {case_id}: {_relation_label(row)}")
    raw_curie_gaps = failure_payload.get("curie_gaps")
    if isinstance(raw_curie_gaps, list):
        for raw_row in raw_curie_gaps[:10]:
            row = _object(raw_row)
            case_id = str(row.get("case_id", "unknown_case"))
            lines.append(f"curie_gaps: {case_id}: {_curie_gap_label(row)}")
    return lines


def _relation_label(payload: JSONObject) -> str:
    subject = str(payload.get("subject", "unknown_subject"))
    relation_type = str(payload.get("relation_type", "unknown_relation"))
    object_label = str(payload.get("object", "unknown_object"))
    return f"{subject} {relation_type} {object_label}"


def _curie_gap_label(payload: JSONObject) -> str:
    gap_type = str(payload.get("gap_type", "unknown_gap"))
    endpoint_role = str(payload.get("endpoint_role", "unknown_endpoint"))
    label = str(payload.get("label", "unknown_label"))
    curie_label = _curie_gap_identifier(payload)
    return f"{gap_type} {endpoint_role} {label} -> {curie_label}"


def _curie_gap_identifier(payload: JSONObject) -> str:
    gold_curie = payload.get("gold_curie")
    if isinstance(gold_curie, str) and gold_curie.strip():
        return gold_curie
    candidate_curie = payload.get("candidate_curie")
    if isinstance(candidate_curie, str) and candidate_curie.strip():
        source = payload.get("candidate_curie_source")
        if isinstance(source, str) and source.strip():
            return f"{candidate_curie} ({source})"
        return candidate_curie
    return "no_curie"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _git_output(args: tuple[str, ...]) -> str:
    result = subprocess.run(  # noqa: S603
        ("git", *args),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
