"""V10 target-boundary and frozen-V9 regression evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
        DualLaneCaseMetrics,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
        V9StagedGeneralizationOutput,
    )

_BOOLEAN_FIELDS = (
    "required_core_complete",
    "complete_event_recovery",
    "participant_role_fidelity",
    "nested_event_structure",
    "direction_fidelity",
    "comparison_fidelity",
    "polarity_fidelity",
    "uncertainty_fidelity",
    "statistical_fidelity",
    "exact_evidence_grounding",
)
_COUNT_FIELDS = (
    "ambiguous_context_count",
    "unsupported_claim_count",
    "contradiction_count",
)
_TARGET_CASE = "generalization-uncertainty"
_TARGET_REQUIRED_TEXT = "SLC12A3"
_TARGET_FORBIDDEN_TEXT = "SLC12A3 gene"
_PROTECTED_CASE = "generalization-explicit-nested-cause"
_PROTECTED_LEXICALIZED_NAMES = (
    "HCMV immediate-early proteins",
    "immediate-early proteins",
)


@dataclass(frozen=True, slots=True)
class V9Comparison:
    status: str
    preserved_fields: tuple[str, ...]
    improved_fields: tuple[str, ...]
    regressed_fields: tuple[str, ...]
    unchanged_failure_fields: tuple[str, ...]
    count_regressions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BoundaryAcceptance:
    target_case: bool
    target_correction_required: bool
    target_correction_observed: bool | None
    forbidden_suffix_absent: bool | None
    protected_lexicalized_name_required: bool
    protected_lexicalized_name_preserved: bool | None
    scientific_grader_passed: bool
    v9_fields_regressed: tuple[str, ...]
    v9_count_regressions: tuple[str, ...]
    passed: bool
    failure_classification: str | None

    def as_json(self) -> dict[str, object]:
        return asdict(self)


def compare_with_v9(
    metrics: DualLaneCaseMetrics,
    baseline: dict[str, object] | None,
) -> V9Comparison:
    if baseline is None:
        return V9Comparison(
            status="NOT_CALLED_IN_V9",
            preserved_fields=(),
            improved_fields=(),
            regressed_fields=(),
            unchanged_failure_fields=(),
            count_regressions=(),
        )
    preserved: list[str] = []
    improved: list[str] = []
    regressed: list[str] = []
    unchanged_failure: list[str] = []
    for field in _BOOLEAN_FIELDS:
        before = baseline.get(field)
        after = bool(getattr(metrics, field))
        if not isinstance(before, bool):
            raise TypeError(f"V9 baseline {field} is malformed")
        if before and after:
            preserved.append(field)
        elif not before and after:
            improved.append(field)
        elif before and not after:
            regressed.append(field)
        else:
            unchanged_failure.append(field)
    count_regressions = tuple(
        field
        for field in _COUNT_FIELDS
        if _required_int(baseline, field) < int(getattr(metrics, field))
    )
    return V9Comparison(
        status="COMPARED",
        preserved_fields=tuple(preserved),
        improved_fields=tuple(improved),
        regressed_fields=tuple(regressed),
        unchanged_failure_fields=tuple(unchanged_failure),
        count_regressions=count_regressions,
    )


def evaluate_acceptance(
    output: V9StagedGeneralizationOutput,
    metrics: DualLaneCaseMetrics,
    comparison: V9Comparison,
    *,
    v9_baseline_passed: bool | None,
) -> BoundaryAcceptance:
    target_case = output.case_id == _TARGET_CASE
    target_observed: bool | None = None
    forbidden_absent: bool | None = None
    if target_case:
        gene_texts = tuple(
            participant.exact_text
            for participant in output.participants
            if participant.entity_type == "GENE_OR_PROTEIN"
        )
        target_observed = gene_texts.count(_TARGET_REQUIRED_TEXT) == 1
        forbidden_absent = _TARGET_FORBIDDEN_TEXT not in gene_texts

    protected_required = output.case_id == _PROTECTED_CASE
    protected_preserved: bool | None = None
    if protected_required:
        protected_gene_texts = {
            participant.exact_text
            for participant in output.participants
            if participant.entity_type == "GENE_OR_PROTEIN"
        }
        protected_preserved = bool(
            protected_gene_texts.intersection(_PROTECTED_LEXICALIZED_NAMES)
        )

    boundary_passed = (
        (not target_case or bool(target_observed and forbidden_absent))
        and (not protected_required or bool(protected_preserved))
    )
    passed = (
        metrics.passed
        and boundary_passed
        and not comparison.regressed_fields
        and not comparison.count_regressions
    )
    failure_classification: str | None = None
    if not passed:
        if target_case and not boundary_passed:
            failure_classification = "BOUNDARY_RULE_ERROR"
        elif comparison.regressed_fields or comparison.count_regressions:
            failure_classification = "UNRELATED_SCIENTIFIC_REGRESSION"
        elif v9_baseline_passed is False and not metrics.passed:
            failure_classification = "PREEXISTING_V9_SCIENTIFIC_FAILURE_PERSISTED"
        else:
            failure_classification = "UNRELATED_SCIENTIFIC_FAILURE"
    return BoundaryAcceptance(
        target_case=target_case,
        target_correction_required=target_case,
        target_correction_observed=target_observed,
        forbidden_suffix_absent=forbidden_absent,
        protected_lexicalized_name_required=protected_required,
        protected_lexicalized_name_preserved=protected_preserved,
        scientific_grader_passed=metrics.passed,
        v9_fields_regressed=comparison.regressed_fields,
        v9_count_regressions=comparison.count_regressions,
        passed=passed,
        failure_classification=failure_classification,
    )


def metrics_json(metrics: DualLaneCaseMetrics) -> dict[str, object]:
    return cast("dict[str, object]", asdict(metrics))


def comparison_json(comparison: V9Comparison) -> dict[str, object]:
    return cast("dict[str, object]", asdict(comparison))


def _required_int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int):
        raise TypeError(f"V9 baseline {key} is malformed")
    return item


__all__ = [
    "BoundaryAcceptance",
    "V9Comparison",
    "compare_with_v9",
    "comparison_json",
    "evaluate_acceptance",
    "metrics_json",
]
