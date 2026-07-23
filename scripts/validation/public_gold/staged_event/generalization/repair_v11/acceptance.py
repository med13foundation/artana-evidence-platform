"""V11 grounding acceptance layered over frozen V9/V10 science checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.generalization.anchors import (
    GeneralizationAnchorError,
    resolve_evidence,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_acceptance import (
    BoundaryAcceptance,
    V9Comparison,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_acceptance import (
    evaluate_acceptance as evaluate_v10_acceptance,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
        DualLaneCaseMetrics,
    )
    from scripts.validation.public_gold.staged_event.generalization.panel import (
        GeneralizationCase,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
        V9StagedGeneralizationOutput,
    )

_NEGATED_REGRESSION_CASE = "generalization-negated-association"


@dataclass(frozen=True, slots=True)
class V11AcceptanceInput:
    case: GeneralizationCase
    output: V9StagedGeneralizationOutput
    metrics: DualLaneCaseMetrics
    v9_comparison: V9Comparison
    v10_comparison: V9Comparison
    v9_baseline_passed: bool | None


@dataclass(frozen=True, slots=True)
class V11Acceptance:
    """Three-gate acceptance: boundary, grounding, and science preservation."""

    v10_boundary: BoundaryAcceptance
    semantic_evidence_unique: bool
    negated_complete_sentence_required: bool
    negated_complete_sentence_observed: bool | None
    v10_fields_regressed: tuple[str, ...]
    v10_count_regressions: tuple[str, ...]
    passed: bool
    failure_classification: str | None

    def as_json(self) -> dict[str, object]:
        return asdict(self)


def evaluate_acceptance(
    value: V11AcceptanceInput,
) -> V11Acceptance:
    boundary = evaluate_v10_acceptance(
        value.output,
        value.metrics,
        value.v9_comparison,
        v9_baseline_passed=value.v9_baseline_passed,
    )
    semantic_unique = _semantic_evidence_unique(value.case, value.output)
    negated_required = value.case.case_id == _NEGATED_REGRESSION_CASE
    negated_observed = (
        _negated_uses_complete_event_sentence(value.output)
        if negated_required
        else None
    )
    passed = (
        boundary.passed
        and semantic_unique
        and (not negated_required or bool(negated_observed))
        and not value.v10_comparison.regressed_fields
        and not value.v10_comparison.count_regressions
    )
    return V11Acceptance(
        v10_boundary=boundary,
        semantic_evidence_unique=semantic_unique,
        negated_complete_sentence_required=negated_required,
        negated_complete_sentence_observed=negated_observed,
        v10_fields_regressed=value.v10_comparison.regressed_fields,
        v10_count_regressions=value.v10_comparison.count_regressions,
        passed=passed,
        failure_classification=(
            None
            if passed
            else _failure_classification(
                boundary=boundary,
                semantic_unique=semantic_unique,
                negated_grounding_failed=bool(
                    negated_required and not negated_observed
                ),
                v10_comparison=value.v10_comparison,
            )
        ),
    )


def _semantic_evidence_unique(
    case: GeneralizationCase,
    output: V9StagedGeneralizationOutput,
) -> bool:
    try:
        for axes in output.semantic_axes:
            for exact_text in axes.evidence_items:
                resolve_evidence(
                    source=case.source,
                    context_start=case.context_start,
                    context_end=case.context_end,
                    exact_text=exact_text,
                )
    except GeneralizationAnchorError:
        return False
    return True


def _negated_uses_complete_event_sentence(
    output: V9StagedGeneralizationOutput,
) -> bool:
    evidence_by_event = {
        event.event_id: event.exact_evidence for event in output.inventory
    }
    return all(
        axes.evidence_items == (evidence_by_event.get(axes.event_id, ""),)
        for axes in output.semantic_axes
    )


def _failure_classification(
    *,
    boundary: BoundaryAcceptance,
    semantic_unique: bool,
    negated_grounding_failed: bool,
    v10_comparison: V9Comparison,
) -> str | None:
    if boundary.failure_classification == "BOUNDARY_RULE_ERROR":
        return "BOUNDARY_RULE_ERROR"
    if (
        not semantic_unique
        or negated_grounding_failed
        or "exact_evidence_grounding" in boundary.v9_fields_regressed
    ):
        return "SEMANTIC_EVIDENCE_GROUNDING_FAILURE"
    if (
        boundary.v9_fields_regressed
        or boundary.v9_count_regressions
        or v10_comparison.regressed_fields
        or v10_comparison.count_regressions
    ):
        return "UNRELATED_SCIENTIFIC_REGRESSION"
    return "UNRELATED_SCIENTIFIC_FAILURE"


__all__ = ["V11Acceptance", "V11AcceptanceInput", "evaluate_acceptance"]
