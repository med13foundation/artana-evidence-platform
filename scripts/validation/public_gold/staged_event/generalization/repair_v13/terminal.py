"""Persist V13 case evaluations and terminal results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_exclusive,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    EXPERIMENT_ID,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    V13Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.reporting import (
    write_final_report,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.acceptance import (
        ScientificFailure,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.accounting import (
        V13OperationalLedger,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.evaluation import (
        V13CaseMetrics,
    )

PASS_TERMINAL = "V13_EXPOSED_GATE_PASS_PENDING_INDEPENDENT_REVIEW"
ROOT_FAIL_TERMINAL = "V13_EXPOSED_GATE_FAIL_COMPOSITIONAL_ROOT"
SOURCE_FAIL_TERMINAL = "V13_EXPOSED_GATE_FAIL_SOURCE_SEMANTICS"
UNRELATED_FAIL_TERMINAL = "V13_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION"
INVALID_TERMINAL = "INVALID_V13_EXECUTION"
OPERATIONAL_BUDGET_TERMINAL = "V13_OPERATIONAL_BUDGET_STOP_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case_id: str
    response_id: str
    usage: dict[str, object]
    metrics: V13CaseMetrics
    failure_classification: ScientificFailure | None
    custody: dict[str, object] | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "response_id": self.response_id,
            "usage": self.usage,
            "v13_metrics": self.metrics.as_json(),
            "failure_classification": self.failure_classification,
            "custody": self.custody,
        }


@dataclass(frozen=True, slots=True)
class InvalidTerminal:
    failed_case_id: str
    stage: str
    reason: str
    diagnostics: dict[str, object]


def persist_case_evaluation(path: Path, outcome: CaseOutcome) -> None:
    write_json_exclusive(
        path,
        {
            "schema_version": ("artana.staged_generalization.v13_case_evaluation.v1"),
            "experiment_id": EXPERIMENT_ID,
            **outcome.as_json(),
            "benchmark_projection_is_review_only": True,
            "qualification_credit": False,
            "graph_writes": 0,
            "trusted_promotion": False,
        },
    )


def persist_scientific_terminal(
    paths: V13Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V13OperationalLedger,
    planned_case_count: int,
    grading_policy_sha256: str,
) -> str:
    first_failure = next(
        (
            outcome.failure_classification
            for outcome in outcomes
            if outcome.failure_classification is not None
        ),
        None,
    )
    all_passed = len(outcomes) == planned_case_count and first_failure is None
    decision = _decision(all_passed=all_passed, failure=first_failure)
    result = _base_result(
        outcomes=outcomes,
        ledger=ledger,
        planned_case_count=planned_case_count,
    )
    result.update(
        {
            "schema_version": ("artana.staged_generalization.v13_exposed_result.v1"),
            "decision": decision,
            "failure_stage": None,
            "failed_case_id": (None if all_passed else outcomes[-1].case_id),
            "first_failure_classification": first_failure,
            "grading_policy_sha256": grading_policy_sha256,
        }
    )
    write_json_exclusive(paths.result, result)
    write_final_report(paths.report, result)
    return decision


def persist_invalid_terminal(
    paths: V13Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V13OperationalLedger,
    failure: InvalidTerminal,
    planned_case_count: int,
) -> str:
    result = _base_result(
        outcomes=outcomes,
        ledger=ledger,
        planned_case_count=planned_case_count,
    )
    result.update(
        {
            "schema_version": ("artana.staged_generalization.v13_invalid_result.v1"),
            "decision": INVALID_TERMINAL,
            "failure_stage": failure.stage,
            "failed_case_id": failure.failed_case_id,
            "first_failure_classification": None,
            "root_cause": failure.reason,
            "diagnostics": failure.diagnostics,
            "all_evaluations_persisted": failure.stage
            in {
                "OPERATIONAL_BUDGET_STOP",
                "POST_CASE_PERSISTENCE_HOOK",
            },
            "all_receipts_valid": failure.stage
            in {
                "OPERATIONAL_BUDGET_STOP",
                "POST_CASE_PERSISTENCE_HOOK",
                "EVALUATOR_DEFECT",
                "CASE_EVALUATION_PERSISTENCE",
            },
        }
    )
    write_json_exclusive(paths.result, result)
    write_final_report(paths.report, result)
    return INVALID_TERMINAL


def persist_operational_budget_terminal(
    paths: V13Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V13OperationalLedger,
    failure: InvalidTerminal,
    planned_case_count: int,
) -> str:
    """Seal an incomplete operational stop without invalidating case science."""

    result = _base_result(
        outcomes=outcomes,
        ledger=ledger,
        planned_case_count=planned_case_count,
    )
    result.update(
        {
            "schema_version": ("artana.staged_generalization.v13_operational_stop.v1"),
            "decision": OPERATIONAL_BUDGET_TERMINAL,
            "failure_stage": failure.stage,
            "failed_case_id": failure.failed_case_id,
            "first_failure_classification": next(
                (
                    outcome.failure_classification
                    for outcome in outcomes
                    if outcome.failure_classification is not None
                ),
                None,
            ),
            "root_cause": failure.reason,
            "diagnostics": failure.diagnostics,
            "all_evaluations_persisted": True,
            "all_receipts_valid": True,
            "scientific_case_results_preserved": True,
            "experiment_complete": False,
            "qualification_credit": False,
        }
    )
    write_json_exclusive(paths.result, result)
    write_final_report(paths.report, result)
    return OPERATIONAL_BUDGET_TERMINAL


def _base_result(
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V13OperationalLedger,
    planned_case_count: int,
) -> dict[str, object]:
    attempted_case_ids = tuple(record.case_id for record in ledger.records)
    evaluated_case_ids = tuple(outcome.case_id for outcome in outcomes)
    evaluated_case_id_set = set(evaluated_case_ids)
    called_but_unevaluated_case_ids = tuple(
        case_id
        for case_id in attempted_case_ids
        if case_id not in evaluated_case_id_set
    )
    nested = next(
        (
            outcome.metrics
            for outcome in outcomes
            if outcome.case_id == "generalization-explicit-nested-cause"
        ),
        None,
    )
    return {
        "experiment_id": EXPERIMENT_ID,
        "root_cause_classification": ("COMPOSITIONAL_FOCUS_ROOT_AMBIGUITY"),
        "single_scientific_change": ("COMPOSITIONAL_FOCUS_ROOT_SELECTION"),
        "planned_case_count": planned_case_count,
        "executed_case_count": len(attempted_case_ids),
        "provider_attempted_case_ids": list(attempted_case_ids),
        "scientifically_evaluated_case_count": len(evaluated_case_ids),
        "scientifically_evaluated_case_ids": list(evaluated_case_ids),
        "called_but_unevaluated_case_ids": list(called_but_unevaluated_case_ids),
        "stopped_after_case_id": (
            attempted_case_ids[-1]
            if attempted_case_ids
            else (outcomes[-1].case_id if outcomes else None)
        ),
        "case_outcomes": [outcome.as_json() for outcome in outcomes],
        "nested_source_semantic_outcome": (
            nested.source_semantic_status if nested is not None else "NOT_REACHED"
        ),
        "nested_root_selection_outcome": (
            nested.root_selection_status if nested is not None else "NOT_REACHED"
        ),
        "nested_completeness": (
            nested.completeness if nested is not None else "NOT_REACHED"
        ),
        "nested_source_dimensions_except_root_passed": (
            nested.source_dimensions_except_root_passed if nested is not None else None
        ),
        "nested_benchmark_projection_outcome": (
            nested.benchmark_projection_status if nested is not None else "NOT_REACHED"
        ),
        "nested_benchmark_projection_scope": (
            nested.benchmark_projection_scope if nested is not None else "NOT_REACHED"
        ),
        "nested_full_focus_cg_outcome": (
            nested.full_focus_cg_status if nested is not None else "NOT_REACHED"
        ),
        "benchmark_projection_is_review_only": True,
        "benchmark_projection_affects_scientific_decision": False,
        "all_evaluations_persisted": True,
        "all_receipts_valid": True,
        **ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD),
        "model": f"openai:{MODEL}",
        "reasoning_effort": REASONING_EFFORT,
        "sealed_v12_preserved": True,
        "historical_replay_credit": False,
        "fresh_cases_consumed": 0,
        "remaining_fresh_cases_preserved": 7,
        "next_fresh_preregistration": None,
        "fresh_qualification_status": "PENDING_INDEPENDENT_REVIEW",
        "automatic_fresh_draft_generated": False,
        "qualification_credit": False,
        "graph_writes": 0,
        "trusted_promotion": False,
    }


def _decision(
    *,
    all_passed: bool,
    failure: ScientificFailure | None,
) -> str:
    if all_passed:
        return PASS_TERMINAL
    if failure == "COMPOSITIONAL_ROOT":
        return ROOT_FAIL_TERMINAL
    if failure == "SOURCE_SEMANTICS":
        return SOURCE_FAIL_TERMINAL
    return UNRELATED_FAIL_TERMINAL


__all__ = [
    "CaseOutcome",
    "INVALID_TERMINAL",
    "OPERATIONAL_BUDGET_TERMINAL",
    "InvalidTerminal",
    "PASS_TERMINAL",
    "ROOT_FAIL_TERMINAL",
    "SOURCE_FAIL_TERMINAL",
    "UNRELATED_FAIL_TERMINAL",
    "persist_case_evaluation",
    "persist_invalid_terminal",
    "persist_operational_budget_terminal",
    "persist_scientific_terminal",
]
