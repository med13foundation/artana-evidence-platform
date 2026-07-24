"""Persist V18 evaluations and terminal results under exclusive custody."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_exclusive,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v18.config import (
    EXPERIMENT_ID,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    V17_SEALED_HEAD,
    V18Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v18.reporting import (
    write_final_report,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.acceptance import (
        ScientificFailure,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.accounting import (
        V13OperationalLedger,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v18.evaluation import (
        V18CaseEvaluation,
    )

PASS_TERMINAL = "V18_EXPOSED_GATE_PASS_PENDING_INDEPENDENT_REVIEW"
SOURCE_FAIL_TERMINAL = "V18_EXPOSED_GATE_FAIL_SOURCE_SEMANTICS"
REGRESSION_FAIL_TERMINAL = "V18_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION"
INVALID_TERMINAL = "INVALID_V18_EXECUTION"
OPERATIONAL_BUDGET_TERMINAL = "V18_OPERATIONAL_BUDGET_STOP_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """One scientifically evaluated, custody-admitted V18 provider response."""

    case_id: str
    response_id: str
    usage: dict[str, object]
    evaluation: V18CaseEvaluation
    failure_classification: ScientificFailure | None
    custody: dict[str, object] | None = None

    def as_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "response_id": self.response_id,
            "usage": self.usage,
            "v18_evaluation": self.evaluation.as_json(),
            "failure_classification": self.failure_classification,
            "custody": self.custody,
        }


@dataclass(frozen=True, slots=True)
class InvalidTerminal:
    """A non-scientific failure after preserving every available artifact."""

    failed_case_id: str
    stage: str
    reason: str
    diagnostics: dict[str, object]


def persist_case_evaluation(path: Path, outcome: CaseOutcome) -> None:
    """Seal an evaluation only after its provider custody is admitted."""

    write_json_exclusive(
        path,
        {
            "schema_version": "artana.staged_generalization.v18_case_evaluation.v1",
            "experiment_id": EXPERIMENT_ID,
            **outcome.as_json(),
            "evaluator_implementation": "repair_v17.evaluate_v17_case",
            "scientific_decision_lane": "SOURCE_SEMANTICS",
            "raw_v16_diagnostic_lane": "PRESERVED_UNSCORED",
            "bionlp_cg_projection_lane": "RAW_REVIEW_ONLY",
            "qualification_credit": False,
            "graph_writes": 0,
            "trusted_promotion": False,
        },
    )


def persist_scientific_terminal(
    paths: V18Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V13OperationalLedger,
    planned_case_count: int,
    grading_policy_sha256: str,
) -> str:
    """Persist the first scientific failure or the complete exposed result."""

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
            "schema_version": "artana.staged_generalization.v18_exposed_result.v1",
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
    paths: V18Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V13OperationalLedger,
    failure: InvalidTerminal,
    planned_case_count: int,
) -> str:
    """Persist a custody, transport, or evaluator failure without rescoring."""

    result = _base_result(
        outcomes=outcomes,
        ledger=ledger,
        planned_case_count=planned_case_count,
    )
    result.update(
        {
            "schema_version": "artana.staged_generalization.v18_invalid_result.v1",
            "decision": INVALID_TERMINAL,
            "failure_stage": failure.stage,
            "failed_case_id": failure.failed_case_id,
            "first_failure_classification": None,
            "root_cause": failure.reason,
            "diagnostics": failure.diagnostics,
            "all_evaluations_persisted": failure.stage
            in {"POST_CASE_PERSISTENCE_HOOK", "OPERATIONAL_BUDGET_STOP"},
            "all_receipts_valid": failure.stage
            in {
                "POST_CASE_PERSISTENCE_HOOK",
                "OPERATIONAL_BUDGET_STOP",
                "EVALUATOR_DEFECT",
                "CASE_EVALUATION_PERSISTENCE",
            },
        }
    )
    _persist(paths, result)
    return INVALID_TERMINAL


def persist_operational_budget_terminal(
    paths: V18Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V13OperationalLedger,
    failure: InvalidTerminal,
    planned_case_count: int,
) -> str:
    """Stop before another call once the $5 cumulative limit is reached."""

    result = _base_result(
        outcomes=outcomes,
        ledger=ledger,
        planned_case_count=planned_case_count,
    )
    result.update(
        {
            "schema_version": "artana.staged_generalization.v18_operational_stop.v1",
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
    ledger_value = ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD)
    ledger_value["operational_policy_version"] = (
        "artana.staged_generalization.v18_operational_policy.v1"
    )
    prior_key = "transport_qualification_provider_calls_in_v13"
    ledger_value["transport_qualification_provider_calls_in_v18"] = ledger_value.pop(
        prior_key
    )
    return {
        "experiment_id": EXPERIMENT_ID,
        "root_cause_classification": "MODEL_PROMPT_OUTPUT_COMPLETENESS_GAP",
        "single_scientific_change": "ANAPHORIC_LOCUS_COMPLETENESS_V1",
        "scientific_change_kind": "PROMPT_ONLY_NO_EVALUATOR_CHANGE",
        "evaluator_implementation": "repair_v17.evaluate_v17_case",
        "shared_or_historical_grader_changed": False,
        "v16_schema_reused_byte_identical": True,
        "v17_evaluator_reused_byte_identical": True,
        "inline_optional_scope_capability_added": False,
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
        "raw_v16_diagnostic_lane": [
            {
                "case_id": outcome.case_id,
                "status": outcome.evaluation.raw_v16_metrics.source_semantic_status,
                "passed": outcome.evaluation.raw_v16_metrics.passed,
            }
            for outcome in outcomes
        ],
        "raw_bionlp_cg_projection_lane": [
            {
                "case_id": outcome.case_id,
                "status": outcome.evaluation.raw_v16_metrics.benchmark_projection_status,
                "projection": outcome.evaluation.raw_v16_metrics.benchmark_projection,
            }
            for outcome in outcomes
        ],
        "benchmark_projection_is_review_only": True,
        "benchmark_projection_affects_scientific_decision": False,
        "all_evaluations_persisted": True,
        "all_receipts_valid": True,
        **ledger_value,
        "model": f"openai:{MODEL}",
        "reasoning_effort": REASONING_EFFORT,
        "sealed_v17_head": V17_SEALED_HEAD,
        "sealed_v17_preserved": True,
        "historical_results_rescored": False,
        "fresh_cases_consumed": 0,
        "remaining_fresh_cases_preserved": 7,
        "fresh_qualification_status": "NOT_STARTED",
        "qualification_credit": False,
        "graph_writes": 0,
        "trusted_promotion": False,
    }


def _persist(paths: V18Paths, result: dict[str, object]) -> None:
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
