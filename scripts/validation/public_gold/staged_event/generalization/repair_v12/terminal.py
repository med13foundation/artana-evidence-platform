"""Persist V12 case evaluations and terminal results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.config import (
    EXPERIMENT_ID,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    V12Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.fresh_preregistration import (
    write_fresh_draft,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.preflight import (
    CG_FAIL_TERMINAL,
    FOCUS_FAIL_TERMINAL,
    INVALID_TERMINAL,
    PASS_TERMINAL,
    SOURCE_FAIL_TERMINAL,
    UNRELATED_FAIL_TERMINAL,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.reporting import (
    write_final_report,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v12.acceptance import (
        ScientificFailure,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v12.accounting import (
        V12OperationalLedger,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v12.evaluation import (
        V12CaseMetrics,
    )


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case_id: str
    response_id: str
    usage: dict[str, object]
    metrics: V12CaseMetrics
    failure_classification: ScientificFailure | None

    def as_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "response_id": self.response_id,
            "usage": self.usage,
            "v12_metrics": self.metrics.as_json(),
            "failure_classification": self.failure_classification,
        }


@dataclass(frozen=True, slots=True)
class InvalidTerminal:
    failed_case_id: str
    stage: str
    reason: str
    diagnostics: dict[str, object]


def persist_case_evaluation(path: Path, outcome: CaseOutcome) -> None:
    write_json_atomic(
        path,
        {
            "schema_version": (
                "artana.staged_generalization.v12_case_evaluation.v1"
            ),
            "experiment_id": EXPERIMENT_ID,
            **outcome.as_json(),
            "qualification_credit": False,
            "graph_writes": 0,
            "trusted_promotion": False,
        },
    )


def persist_scientific_terminal(
    paths: V12Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V12OperationalLedger,
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
            "schema_version": (
                "artana.staged_generalization.v12_exposed_result.v1"
            ),
            "decision": decision,
            "failure_stage": None,
            "failed_case_id": (
                None if all_passed else outcomes[-1].case_id
            ),
            "first_failure_classification": first_failure,
            "grading_policy_sha256": grading_policy_sha256,
        }
    )
    write_json_atomic(paths.result, result)
    if all_passed:
        write_fresh_draft(paths)
        result["next_fresh_preregistration"] = str(
            paths.next_fresh_preregistration
        )
        write_json_atomic(paths.result, result)
    write_final_report(paths.report, result)
    return decision


def persist_invalid_terminal(
    paths: V12Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V12OperationalLedger,
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
            "schema_version": (
                "artana.staged_generalization.v12_invalid_result.v1"
            ),
            "decision": INVALID_TERMINAL,
            "failure_stage": failure.stage,
            "failed_case_id": failure.failed_case_id,
            "first_failure_classification": None,
            "root_cause": failure.reason,
            "diagnostics": failure.diagnostics,
        }
    )
    write_json_atomic(paths.result, result)
    write_final_report(paths.report, result)
    return INVALID_TERMINAL


def _base_result(
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V12OperationalLedger,
    planned_case_count: int,
) -> dict[str, object]:
    drug = next(
        (
            outcome.metrics
            for outcome in outcomes
            if outcome.case_id == "generalization-drug-sensitivity"
        ),
        None,
    )
    return {
        "experiment_id": EXPERIMENT_ID,
        "root_cause_classification": "FOCUS_EVENT_ANCHORING_PROMPT_GAP",
        "single_scientific_change": "FOCUS_EVENT_ANCHORING",
        "planned_case_count": planned_case_count,
        "executed_case_count": len(outcomes),
        "stopped_after_case_id": outcomes[-1].case_id if outcomes else None,
        "case_outcomes": [outcome.as_json() for outcome in outcomes],
        "drug_source_semantic_outcome": (
            drug.source_semantic_status if drug is not None else "NOT_REACHED"
        ),
        "drug_cg_projection_outcome": (
            drug.cg_projection_status if drug is not None else "NOT_REACHED"
        ),
        "all_evaluations_persisted": True,
        "all_receipts_valid": True,
        **ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD),
        "model": f"openai:{MODEL}",
        "reasoning_effort": REASONING_EFFORT,
        "sealed_v11_preserved": True,
        "historical_replay_credit": False,
        "fresh_cases_consumed": 0,
        "remaining_fresh_cases_preserved": 7,
        "next_fresh_preregistration": None,
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
    if failure == "FOCUS_EVENT":
        return FOCUS_FAIL_TERMINAL
    if failure == "SOURCE_SEMANTICS":
        return SOURCE_FAIL_TERMINAL
    if failure == "CG_PROJECTION":
        return CG_FAIL_TERMINAL
    return UNRELATED_FAIL_TERMINAL


__all__ = [
    "CaseOutcome",
    "InvalidTerminal",
    "persist_case_evaluation",
    "persist_invalid_terminal",
    "persist_scientific_terminal",
]
