"""Failure attribution for repeated relation feasibility reports."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

JSONObject = dict[str, object]
_METRIC_KEYS = (
    "completed_agent_precision_against_gold",
    "completed_agent_recall_against_gold",
    "high_value_recall",
    "completed_agent_valuable_candidate_rate",
    "curie_linked_gold_endpoint_rate",
    "verified_curie_match_rate",
    "generic_relation_rate",
)


@dataclass(frozen=True, slots=True)
class FailureAnalysisInput:
    """One relation feasibility report and optional comparison labels."""

    path: Path
    label: str | None = None
    model_label: str | None = None


@dataclass(frozen=True, slots=True)
class _MissedGoldKey:
    case_id: str
    subject: str
    relation_type: str
    object: str
    value_level: str


@dataclass(frozen=True, slots=True)
class _FalsePositiveKey:
    case_id: str
    subject: str
    relation_type: str
    proposed_relation_type: str | None
    object: str
    support_verification: str | None


@dataclass(frozen=True, slots=True)
class _CurieGapKey:
    case_id: str
    endpoint_role: str
    label: str
    candidate_curie: str | None
    candidate_curie_source: str
    gap_type: str


@dataclass(frozen=True, slots=True)
class _GovernedProposalKey:
    case_id: str
    subject: str
    proposed_relation_type: str | None
    object: str
    trusted_evidence_eligible: bool
    support_verification: str | None


@dataclass(slots=True)
class _Accumulator:
    count: int = 0
    run_labels: set[str] = field(default_factory=set)

    def add(self, label: str) -> None:
        """Record one occurrence in a run."""

        self.count += 1
        self.run_labels.add(label)


@dataclass(frozen=True, slots=True)
class _CollectionStores:
    false_positives: dict[_FalsePositiveKey, _Accumulator]
    curie_gaps: dict[_CurieGapKey, _Accumulator]
    governed_proposals: dict[_GovernedProposalKey, _Accumulator]


@dataclass(frozen=True, slots=True)
class _AssessmentContext:
    assessment: JSONObject
    candidate: JSONObject
    case_id: str
    run_label: str


def build_failure_analysis_report(
    inputs: Sequence[FailureAnalysisInput],
) -> JSONObject:
    """Build a read-only failure attribution report from feasibility reports."""

    missed_gold: dict[_MissedGoldKey, _Accumulator] = {}
    false_positives: dict[_FalsePositiveKey, _Accumulator] = {}
    curie_gaps: dict[_CurieGapKey, _Accumulator] = {}
    governed_proposals: dict[_GovernedProposalKey, _Accumulator] = {}
    summaries_by_model: dict[str, list[JSONObject]] = {}
    input_reports: list[JSONObject] = []
    proposal_candidate_count = 0
    proposal_gold_match_count = 0
    proposal_eligible_gold_count = 0
    trusted_proposal_capture_count = 0

    for index, report_input in enumerate(inputs, start=1):
        report_path = _resolve_report_path(report_input.path)
        payload = _load_report(report_path)
        summary = _object_dict(payload.get("summary"))
        label = report_input.label or _default_label(report_path, index)
        model_label = report_input.model_label or _model_label_from_summary(summary)
        input_reports.append(
            {
                "path": str(report_path),
                "label": label,
                "model_label": model_label,
            },
        )
        summaries_by_model.setdefault(model_label, []).append(summary)
        proposal_candidate_count += _int_value(summary.get("proposal_candidate_count"))
        proposal_gold_match_count += _int_value(summary.get("proposal_gold_match_count"))
        proposal_eligible_gold_count += _int_value(
            summary.get("proposal_eligible_gold_count"),
        )

        for case_result in _object_list(payload.get("case_results")):
            case_id = _case_id(case_result)
            _collect_missed_gold(
                missed_gold,
                case_result=case_result,
                case_id=case_id,
                run_label=label,
            )
            trusted_proposal_capture_count += _collect_assessments(
                _CollectionStores(
                    false_positives=false_positives,
                    curie_gaps=curie_gaps,
                    governed_proposals=governed_proposals,
                ),
                case_result=case_result,
                case_id=case_id,
                run_label=label,
            )

    return {
        "run_count": len(inputs),
        "input_reports": input_reports,
        "repeated_missed_gold_relations": _missed_gold_rows(missed_gold),
        "repeated_false_positive_candidates": _false_positive_rows(false_positives),
        "curie_gaps": _curie_gap_rows(curie_gaps),
        "proposal_capture": {
            "proposal_candidate_count": proposal_candidate_count,
            "proposal_gold_match_count": proposal_gold_match_count,
            "proposal_eligible_gold_count": proposal_eligible_gold_count,
            "proposal_recall_against_proposal_eligible_gold": _ratio(
                proposal_gold_match_count,
                proposal_eligible_gold_count,
            ),
            "trusted_proposal_capture_count": trusted_proposal_capture_count,
        },
        "governed_proposal_captures": _governed_proposal_rows(governed_proposals),
        "model_comparison": _model_comparison_rows(summaries_by_model),
    }


def render_failure_analysis_markdown(report: JSONObject) -> str:
    """Render a compact Markdown failure attribution report."""

    lines = [
        "# Relation Feasibility Failure Attribution",
        "",
        f"- Runs analyzed: {report.get('run_count')}",
        "",
        "## Repeated Missed Gold Relations",
        "",
    ]
    lines.extend(
        _table_lines(
            report.get("repeated_missed_gold_relations"),
            ("occurrence_count", "value_level", "case_id", "subject", "relation_type", "object"),
        ),
    )
    lines.extend(["", "## Repeated False Positives", ""])
    lines.extend(
        _table_lines(
            report.get("repeated_false_positive_candidates"),
            (
                "occurrence_count",
                "case_id",
                "subject",
                "relation_type",
                "proposed_relation_type",
                "object",
                "support_verification",
            ),
        ),
    )
    lines.extend(["", "## CURIE Gaps", ""])
    lines.extend(
        _table_lines(
            report.get("curie_gaps"),
            (
                "occurrence_count",
                "gap_type",
                "case_id",
                "endpoint_role",
                "label",
                "candidate_curie",
                "candidate_curie_source",
            ),
        ),
    )
    lines.extend(["", "## Proposal Capture", ""])
    proposal_capture = report.get("proposal_capture")
    if isinstance(proposal_capture, dict):
        lines.extend(f"- {key}: {value}" for key, value in sorted(proposal_capture.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Model Comparison", ""])
    lines.extend(
        _table_lines(
            report.get("model_comparison"),
            ("model_label", "run_count", "mean_completed_agent_precision_against_gold", "mean_high_value_recall", "mean_curie_linked_gold_endpoint_rate"),
        ),
    )
    return "\n".join(lines) + "\n"


def write_failure_analysis_report(*, report: JSONObject, output_dir: Path) -> JSONObject:
    """Write failure attribution JSON and Markdown artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "relation_feasibility_failure_analysis_report.json"
    markdown_path = output_dir / "relation_feasibility_failure_analysis_report.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    markdown_path.write_text(render_failure_analysis_markdown(report))
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def _collect_missed_gold(
    missed_gold: dict[_MissedGoldKey, _Accumulator],
    *,
    case_result: JSONObject,
    case_id: str,
    run_label: str,
) -> None:
    for missed_relation in _object_list(case_result.get("missed_gold_relations")):
        key = _MissedGoldKey(
            case_id=case_id,
            subject=_string_value(missed_relation.get("subject")),
            relation_type=_string_value(missed_relation.get("relation_type")),
            object=_string_value(missed_relation.get("object")),
            value_level=_string_value(missed_relation.get("value_level")),
        )
        _add_occurrence(missed_gold, key, run_label)


def _collect_assessments(
    stores: _CollectionStores,
    *,
    case_result: JSONObject,
    case_id: str,
    run_label: str,
) -> int:
    trusted_proposal_capture_count = 0
    for assessment in _object_list(case_result.get("candidate_assessments")):
        candidate = _object_dict(assessment.get("candidate"))
        if not _bool_value(assessment.get("is_supported_by_gold")):
            key = _FalsePositiveKey(
                case_id=case_id,
                subject=_string_value(candidate.get("subject")),
                relation_type=_string_value(candidate.get("relation_type")),
                proposed_relation_type=_optional_string(
                    candidate.get("proposed_relation_type"),
                ),
                object=_string_value(candidate.get("object")),
                support_verification=_optional_string(
                    assessment.get("support_verification"),
                ),
            )
            _add_occurrence(stores.false_positives, key, run_label)
        proposal_match = assessment.get("proposal_matched_gold_index") is not None
        if _bool_value(assessment.get("is_governed_relation_proposal")) and proposal_match:
            trusted_eligible = _bool_value(
                assessment.get("is_trusted_evidence_eligible"),
            ) or _bool_value(candidate.get("trusted_evidence_eligible"))
            if trusted_eligible:
                trusted_proposal_capture_count += 1
            proposal_key = _GovernedProposalKey(
                case_id=case_id,
                subject=_string_value(candidate.get("subject")),
                proposed_relation_type=_optional_string(
                    candidate.get("proposed_relation_type"),
                ),
                object=_string_value(candidate.get("object")),
                trusted_evidence_eligible=trusted_eligible,
                support_verification=_optional_string(
                    assessment.get("support_verification"),
                ),
            )
            _add_occurrence(stores.governed_proposals, proposal_key, run_label)
        if _bool_value(assessment.get("is_supported_by_gold")):
            _collect_curie_gap(
                stores.curie_gaps,
                context=_AssessmentContext(
                    assessment=assessment,
                    candidate=candidate,
                    case_id=case_id,
                    run_label=run_label,
                ),
                role="subject",
            )
            _collect_curie_gap(
                stores.curie_gaps,
                context=_AssessmentContext(
                    assessment=assessment,
                    candidate=candidate,
                    case_id=case_id,
                    run_label=run_label,
                ),
                role="object",
            )
    return trusted_proposal_capture_count


def _collect_curie_gap(
    curie_gaps: dict[_CurieGapKey, _Accumulator],
    *,
    context: _AssessmentContext,
    role: str,
) -> None:
    assessment = context.assessment
    candidate = context.candidate
    verified_key = f"has_verified_{role}_curie"
    match_key = f"{role}_curie_matches_gold"
    if _bool_value(assessment.get(verified_key)) and _bool_value(assessment.get(match_key)):
        return
    curie = _optional_string(candidate.get(f"{role}_curie"))
    curie_source = _string_value(candidate.get(f"{role}_curie_source")) or "none"
    key = _CurieGapKey(
        case_id=context.case_id,
        endpoint_role=role,
        label=_string_value(candidate.get(role)),
        candidate_curie=curie,
        candidate_curie_source=curie_source,
        gap_type=_curie_gap_type(
            curie=curie,
            curie_source=curie_source,
            has_verified_curie=_bool_value(assessment.get(verified_key)),
        ),
    )
    _add_occurrence(curie_gaps, key, context.run_label)


def _curie_gap_type(
    *,
    curie: str | None,
    curie_source: str,
    has_verified_curie: bool,
) -> str:
    if has_verified_curie:
        return "wrong_verified_match"
    if curie is None:
        return "missing_curie"
    if curie_source == "model":
        return "unverified_model_hint"
    return "unverified_candidate_curie"


def _missed_gold_rows(
    missed_gold: dict[_MissedGoldKey, _Accumulator],
) -> list[JSONObject]:
    rows: list[JSONObject] = []
    for key, accumulator in missed_gold.items():
        rows.append(
            {
                "case_id": key.case_id,
                "subject": key.subject,
                "relation_type": key.relation_type,
                "object": key.object,
                "value_level": key.value_level,
                "occurrence_count": accumulator.count,
                "run_labels": sorted(accumulator.run_labels),
            },
        )
    return _sort_rows(rows)


def _false_positive_rows(
    false_positives: dict[_FalsePositiveKey, _Accumulator],
) -> list[JSONObject]:
    rows: list[JSONObject] = []
    for key, accumulator in false_positives.items():
        rows.append(
            {
                "case_id": key.case_id,
                "subject": key.subject,
                "relation_type": key.relation_type,
                "proposed_relation_type": key.proposed_relation_type,
                "object": key.object,
                "support_verification": key.support_verification,
                "occurrence_count": accumulator.count,
                "run_labels": sorted(accumulator.run_labels),
            },
        )
    return _sort_rows(rows)


def _curie_gap_rows(curie_gaps: dict[_CurieGapKey, _Accumulator]) -> list[JSONObject]:
    rows: list[JSONObject] = []
    for key, accumulator in curie_gaps.items():
        rows.append(
            {
                "case_id": key.case_id,
                "endpoint_role": key.endpoint_role,
                "label": key.label,
                "candidate_curie": key.candidate_curie,
                "candidate_curie_source": key.candidate_curie_source,
                "gap_type": key.gap_type,
                "occurrence_count": accumulator.count,
                "run_labels": sorted(accumulator.run_labels),
            },
        )
    return _sort_rows(rows)


def _governed_proposal_rows(
    governed_proposals: dict[_GovernedProposalKey, _Accumulator],
) -> list[JSONObject]:
    rows: list[JSONObject] = []
    for key, accumulator in governed_proposals.items():
        rows.append(
            {
                "case_id": key.case_id,
                "subject": key.subject,
                "proposed_relation_type": key.proposed_relation_type,
                "object": key.object,
                "trusted_evidence_eligible": key.trusted_evidence_eligible,
                "support_verification": key.support_verification,
                "occurrence_count": accumulator.count,
                "run_labels": sorted(accumulator.run_labels),
            },
        )
    return _sort_rows(rows)


def _model_comparison_rows(summaries_by_model: dict[str, list[JSONObject]]) -> list[JSONObject]:
    rows: list[JSONObject] = []
    for model_label, summaries in summaries_by_model.items():
        row: JSONObject = {"model_label": model_label, "run_count": len(summaries)}
        for key in _METRIC_KEYS:
            values = [_float_value(summary.get(key)) for summary in summaries]
            row[f"mean_{key}"] = _round_metric(sum(values) / len(values)) if values else 0.0
            row[f"worst_{key}"] = _worst_metric(key, values)
        rows.append(row)
    return sorted(rows, key=lambda row: str(row.get("model_label", "")))


def _worst_metric(key: str, values: list[float]) -> float:
    if not values:
        return 0.0
    if key == "generic_relation_rate":
        return _round_metric(max(values))
    return _round_metric(min(values))


def _sort_rows(rows: list[JSONObject]) -> list[JSONObject]:
    return sorted(
        rows,
        key=lambda row: (
            -_int_value(row.get("occurrence_count")),
            str(row.get("case_id", "")),
            str(row.get("subject", "")),
            str(row.get("relation_type", "")),
            str(row.get("object", "")),
        ),
    )


def _add_occurrence[KeyT](
    values: dict[KeyT, _Accumulator],
    key: KeyT,
    run_label: str,
) -> None:
    accumulator = values.setdefault(key, _Accumulator())
    accumulator.add(run_label)


def _load_report(path: Path) -> JSONObject:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        msg = f"{path} does not contain a JSON object"
        raise TypeError(msg)
    return payload


def _resolve_report_path(path: Path) -> Path:
    if path.is_dir():
        return path / "relation_feasibility_report.json"
    return path


def _default_label(path: Path, index: int) -> str:
    if path.name == "relation_feasibility_report.json":
        return path.parent.name
    return path.stem or f"run{index}"


def _model_label_from_summary(summary: JSONObject) -> str:
    for key in ("model_label", "model_id", "extraction_model"):
        value = _optional_string(summary.get(key))
        if value is not None:
            return value
    return "unlabeled"


def _case_id(case_result: JSONObject) -> str:
    case = _object_dict(case_result.get("case"))
    return _string_value(case.get("case_id"))


def _object_dict(value: object) -> JSONObject:
    return value if isinstance(value, dict) else {}


def _object_list(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _table_lines(value: object, keys: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- none"]
    header = "| " + " | ".join(keys) + " |"
    separator = "| " + " | ".join("---" for _ in keys) + " |"
    lines = [header, separator]
    for row in value:
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            + " | ".join(str(row.get(key, "")) if row.get(key) is not None else "" for key in keys)
            + " |",
        )
    return lines


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return _round_metric(numerator / denominator)


def _round_metric(value: float) -> float:
    return round(value, 4)


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _float_value(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    return 0.0


def _bool_value(value: object) -> bool:
    return value is True


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _string_value(value: object) -> str:
    return _optional_string(value) or ""


__all__ = [
    "FailureAnalysisInput",
    "build_failure_analysis_report",
    "render_failure_analysis_markdown",
    "write_failure_analysis_report",
]
