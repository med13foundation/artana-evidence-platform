"""Classify V13 scientific outcomes without grading the CG projection lane."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
        V13CaseMetrics,
    )

ScientificFailure = Literal[
    "COMPOSITIONAL_ROOT",
    "SOURCE_SEMANTICS",
    "UNRELATED_REGRESSION",
]
_NESTED_CASE = "generalization-explicit-nested-cause"


def failure_classification(
    metrics: V13CaseMetrics,
) -> ScientificFailure | None:
    """Return the first source-scientific failure, never a CG-only mismatch."""

    if metrics.passed:
        return None
    if metrics.case_id != _NESTED_CASE:
        return "UNRELATED_REGRESSION"
    if (
        metrics.root_only_failure
        and metrics.root_selection_status == "FAIL"
        and metrics.completeness == "COMPLETE"
        and metrics.source_dimensions_except_root_passed
    ):
        return "COMPOSITIONAL_ROOT"
    if metrics.source_semantic_status != "PASS":
        return "SOURCE_SEMANTICS"
    return "UNRELATED_REGRESSION"


__all__ = ["ScientificFailure", "failure_classification"]
