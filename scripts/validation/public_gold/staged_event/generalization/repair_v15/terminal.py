"""Persist V15 evaluations and terminal results under exclusive custody."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_exclusive,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.terminal import (
    CaseOutcome,
    InvalidTerminal,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
    EXPERIMENT_ID,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    V14_SEALED_HEAD,
    V15_AUTHORIZATION_HEAD,
    V15_AUTHORIZATION_SHA256,
    V15Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.reporting import (
    write_final_report,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.accounting import (
        V13OperationalLedger,
    )

PASS_TERMINAL = "V15_EXPOSED_GATE_PASS_PENDING_INDEPENDENT_REVIEW"
SOURCE_FAIL_TERMINAL = "V15_EXPOSED_GATE_FAIL_SOURCE_SEMANTICS"
REGRESSION_FAIL_TERMINAL = "V15_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION"
INVALID_TERMINAL = "INVALID_V15_EXECUTION"
OPERATIONAL_BUDGET_TERMINAL = "V15_OPERATIONAL_BUDGET_STOP_INCOMPLETE"


def persist_case_evaluation(path: Path, outcome: CaseOutcome) -> None:
    write_json_exclusive(
        path,
        {
            "schema_version": "artana.staged_generalization.v15_case_evaluation.v1",
            "experiment_id": EXPERIMENT_ID,
            **outcome.as_json(),
            "evaluator_implementation": "repair_v14.evaluate_v14_case",
            "scientific_decision_lane": "SOURCE_SEMANTICS",
            "bionlp_cg_projection_lane": "RAW_REVIEW_ONLY",
            "qualification_credit": False,
            "graph_writes": 0,
            "trusted_promotion": False,
        },
    )


def persist_scientific_terminal(
    paths: V15Paths,
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
    decision = (
        PASS_TERMINAL
        if all_passed
        else (
            SOURCE_FAIL_TERMINAL
            if first_failure == "SOURCE_SEMANTICS"
            else REGRESSION_FAIL_TERMINAL
        )
    )
    result = _base_result(
        outcomes=outcomes,
        ledger=ledger,
        planned_case_count=planned_case_count,
    )
    result.update(
        {
            "schema_version": "artana.staged_generalization.v15_exposed_result.v1",
            "decision": decision,
            "failure_stage": None,
            "failed_case_id": None if all_passed else outcomes[-1].case_id,
            "first_failure_classification": first_failure,
            "grading_policy_sha256": grading_policy_sha256,
        }
    )
    _persist(paths, result)
    return decision


def persist_invalid_terminal(
    paths: V15Paths,
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
            "schema_version": "artana.staged_generalization.v15_invalid_result.v1",
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
    _persist(paths, result)
    return INVALID_TERMINAL


def persist_operational_budget_terminal(
    paths: V15Paths,
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
            "schema_version": ("artana.staged_generalization.v15_operational_stop.v1"),
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
            "scientific_case_results_preserved": True,
            "experiment_complete": False,
            "qualification_credit": False,
        }
    )
    _persist(paths, result)
    return OPERATIONAL_BUDGET_TERMINAL


def _base_result(
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V13OperationalLedger,
    planned_case_count: int,
) -> dict[str, object]:
    attempted = tuple(record.case_id for record in ledger.records)
    evaluated = tuple(outcome.case_id for outcome in outcomes)
    nested = next(
        (
            outcome.evaluation
            for outcome in outcomes
            if outcome.case_id == "generalization-explicit-nested-cause"
        ),
        None,
    )
    ledger_value = ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD)
    ledger_value["operational_policy_version"] = (
        "artana.staged_generalization.v15_operational_policy.v1"
    )
    prior_key = "transport_qualification_provider_calls_in_v13"
    ledger_value["transport_qualification_provider_calls_in_v15"] = ledger_value.pop(
        prior_key
    )
    return {
        "experiment_id": EXPERIMENT_ID,
        "root_cause_classification": "FOCUS_CLOSURE_AND_OCCURRENCE_CUSTODY",
        "single_scientific_change": (
            "FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1"
        ),
        "scientific_change_kind": "PROVIDER_PROMPT_ONLY",
        "evaluator_implementation": "repair_v14.evaluate_v14_case",
        "evaluator_changed_from_v14": False,
        "planned_case_count": planned_case_count,
        "executed_case_count": len(attempted),
        "provider_attempted_case_ids": list(attempted),
        "scientifically_evaluated_case_count": len(evaluated),
        "scientifically_evaluated_case_ids": list(evaluated),
        "called_but_unevaluated_case_ids": [
            case_id for case_id in attempted if case_id not in set(evaluated)
        ],
        "stopped_after_case_id": attempted[-1] if attempted else None,
        "case_outcomes": [outcome.as_json() for outcome in outcomes],
        "source_semantic_lane": [
            {
                "case_id": outcome.case_id,
                "status": outcome.evaluation.metrics.source_semantic_status,
                "passed": outcome.evaluation.metrics.passed,
                "failure_reasons": list(outcome.evaluation.metrics.failure_reasons),
            }
            for outcome in outcomes
        ],
        "raw_bionlp_cg_projection_lane": [
            {
                "case_id": outcome.case_id,
                "status": (
                    outcome.evaluation.raw_v13_metrics.benchmark_projection_status
                ),
                "projection": (outcome.evaluation.raw_v13_metrics.benchmark_projection),
            }
            for outcome in outcomes
        ],
        "nested_source_semantic_outcome": (
            nested.metrics.source_semantic_status
            if nested is not None
            else "NOT_REACHED"
        ),
        "nested_root_selection_outcome": (
            nested.metrics.root_selection_status
            if nested is not None
            else "NOT_REACHED"
        ),
        "nested_raw_benchmark_projection_outcome": (
            nested.raw_v13_metrics.benchmark_projection_status
            if nested is not None
            else "NOT_REACHED"
        ),
        "benchmark_projection_is_review_only": True,
        "benchmark_projection_affects_scientific_decision": False,
        "all_evaluations_persisted": True,
        "all_receipts_valid": True,
        **ledger_value,
        "model": f"openai:{MODEL}",
        "reasoning_effort": REASONING_EFFORT,
        "sealed_v14_head": V14_SEALED_HEAD,
        "sealed_v14_preserved": True,
        "v15_authorization_head": V15_AUTHORIZATION_HEAD,
        "v15_authorization_sha256": V15_AUTHORIZATION_SHA256,
        "historical_results_rescored": False,
        "fresh_cases_consumed": 0,
        "remaining_fresh_cases_preserved": 7,
        "fresh_qualification_status": "NOT_STARTED",
        "qualification_credit": False,
        "graph_writes": 0,
        "trusted_promotion": False,
    }


def _persist(paths: V15Paths, result: dict[str, object]) -> None:
    write_json_exclusive(paths.result, result)
    write_final_report(paths.report, result)


__all__ = [
    "CaseOutcome",
    "INVALID_TERMINAL",
    "InvalidTerminal",
    "OPERATIONAL_BUDGET_TERMINAL",
    "PASS_TERMINAL",
    "REGRESSION_FAIL_TERMINAL",
    "SOURCE_FAIL_TERMINAL",
    "persist_case_evaluation",
    "persist_invalid_terminal",
    "persist_operational_budget_terminal",
    "persist_scientific_terminal",
]
