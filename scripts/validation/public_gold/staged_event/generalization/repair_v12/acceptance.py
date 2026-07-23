"""Classify V12 scientific outcomes without changing the frozen grader."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v12.evaluation import (
        V12CaseMetrics,
    )

ScientificFailure = Literal[
    "FOCUS_EVENT",
    "SOURCE_SEMANTICS",
    "CG_PROJECTION",
    "UNRELATED_REGRESSION",
]


def failure_classification(
    metrics: V12CaseMetrics,
) -> ScientificFailure | None:
    if metrics.passed:
        return None
    if metrics.case_id != "generalization-drug-sensitivity":
        return "UNRELATED_REGRESSION"
    if not metrics.focus_event_passed:
        return "FOCUS_EVENT"
    if metrics.source_semantic_status != "PASS":
        return "SOURCE_SEMANTICS"
    if metrics.cg_projection_status != "PASS":
        return "CG_PROJECTION"
    return "UNRELATED_REGRESSION"


__all__ = ["ScientificFailure", "failure_classification"]
