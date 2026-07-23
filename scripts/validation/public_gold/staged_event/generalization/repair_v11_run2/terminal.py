"""Persist V11 run-2 evaluations, terminal results, and reports."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    DualLaneCaseMetrics,
    aggregate,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_acceptance import (
    V9Comparison,
    comparison_json,
    metrics_json,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.config import (
    EXPERIMENT_ID,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    V11Run2Paths,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.fresh_preregistration import (
    write_fresh_preregistration,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.reporting import (
    write_final_report,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v11.acceptance import (
        V11Acceptance,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.accounting import (
        V11Run2OperationalLedger,
    )

PASS_TERMINAL = "V11_EXPOSED_RUN_V2_PASS_READY_FOR_FRESH_PREREGISTRATION"
BOUNDARY_FAIL_TERMINAL = "V11_EXPOSED_RUN_V2_FAIL_BOUNDARY"
GROUNDING_FAIL_TERMINAL = "V11_EXPOSED_RUN_V2_FAIL_GROUNDING"
UNRELATED_FAIL_TERMINAL = "V11_EXPOSED_RUN_V2_FAIL_UNRELATED_REGRESSION"
INVALID_TERMINAL = "INVALID_V11_RUN_V2_EXECUTION"
_ROOT_CAUSE = "SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP"
_SCIENTIFIC_CHANGE = "UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case_id: str
    response_id: str
    usage: dict[str, object]
    metrics: DualLaneCaseMetrics
    v9_comparison: V9Comparison
    v10_comparison: V9Comparison
    acceptance: V11Acceptance
    gene_or_protein_occurrences: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "response_id": self.response_id,
            "usage": self.usage,
            "scientific_grader": metrics_json(self.metrics),
            "v9_comparison": comparison_json(self.v9_comparison),
            "v10_comparison": comparison_json(self.v10_comparison),
            "v11_acceptance": self.acceptance.as_json(),
            "gene_or_protein_occurrences": list(self.gene_or_protein_occurrences),
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
                "artana.staged_generalization.v11_exposed_run2_case_evaluation.v1"
            ),
            "experiment_id": EXPERIMENT_ID,
            **outcome.as_json(),
            "qualification_credit": False,
            "graph_writes": 0,
        },
    )


def persist_scientific_terminal(
    paths: V11Run2Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V11Run2OperationalLedger,
    planned_case_count: int,
    grading_policy_sha256: str,
) -> str:
    all_passed = len(outcomes) == planned_case_count and all(
        outcome.acceptance.passed for outcome in outcomes
    )
    first_failure = next(
        (
            outcome.acceptance.failure_classification
            for outcome in outcomes
            if not outcome.acceptance.passed
        ),
        None,
    )
    decision = _decision(all_passed=all_passed, failure=first_failure)
    scientific = aggregate(tuple(outcome.metrics for outcome in outcomes))
    result = {
        **scientific,
        "schema_version": (
            "artana.staged_generalization.v11_exposed_run2_result.v1"
        ),
        "experiment_id": EXPERIMENT_ID,
        "decision": decision,
        **_scientific_context(paths, validated=all_passed),
        "planned_case_count": planned_case_count,
        "executed_case_count": len(outcomes),
        "stopped_after_case_id": outcomes[-1].case_id,
        "first_failure_classification": first_failure,
        "failure_stage": None,
        "failed_case_id": None if all_passed else outcomes[-1].case_id,
        "case_outcomes": [outcome.as_json() for outcome in outcomes],
        "v9_preserved_fields": _fields(outcomes, "v9_comparison", "preserved_fields"),
        "v9_improved_fields": _fields(outcomes, "v9_comparison", "improved_fields"),
        "v9_regressed_fields": _fields(outcomes, "v9_comparison", "regressed_fields"),
        "v9_count_regressions": _fields(
            outcomes,
            "v9_comparison",
            "count_regressions",
        ),
        "v10_preserved_fields": _fields(
            outcomes,
            "v10_comparison",
            "preserved_fields",
        ),
        "v10_improved_fields": _fields(
            outcomes,
            "v10_comparison",
            "improved_fields",
        ),
        "v10_regressed_fields": _fields(
            outcomes,
            "v10_comparison",
            "regressed_fields",
        ),
        "v10_count_regressions": _fields(
            outcomes,
            "v10_comparison",
            "count_regressions",
        ),
        "slc12a3_corrected_by_actual_model_call": _slc12a3_corrected(outcomes),
        "negated_complete_unique_sentence_observed": _negated_repaired(outcomes),
        "all_semantic_evidence_unique": all(
            outcome.acceptance.semantic_evidence_unique for outcome in outcomes
        ),
        "grading_policy_sha256": grading_policy_sha256,
        "all_receipts_valid": True,
        **ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD),
        "model": f"openai:{MODEL}",
        "reasoning_effort": REASONING_EFFORT,
        "fresh_cases_consumed": 0,
        "remaining_fresh_cases_preserved": 7,
        "next_fresh_preregistration": (
            str(paths.fresh_preregistration) if all_passed else None
        ),
        "qualification_credit": False,
        "trusted_promotion": False,
        "graph_writes": 0,
    }
    write_json_atomic(paths.result, result)
    write_final_report(paths.report, result)
    if all_passed:
        write_fresh_preregistration(paths)
    return decision


def persist_invalid_terminal(
    paths: V11Run2Paths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V11Run2OperationalLedger,
    failure: InvalidTerminal,
    planned_case_count: int,
) -> str:
    result = {
        "schema_version": (
            "artana.staged_generalization.v11_exposed_run2_invalid_result.v1"
        ),
        "experiment_id": EXPERIMENT_ID,
        "decision": INVALID_TERMINAL,
        **_scientific_context(paths, validated=False),
        "failure_stage": failure.stage,
        "root_cause": failure.reason,
        "failed_case_id": failure.failed_case_id,
        "first_failure_classification": None,
        "diagnostics": failure.diagnostics,
        "planned_case_count": planned_case_count,
        "executed_case_count": len(outcomes),
        "case_outcomes": [outcome.as_json() for outcome in outcomes],
        "slc12a3_corrected_by_actual_model_call": _slc12a3_corrected(outcomes),
        "negated_complete_unique_sentence_observed": _negated_repaired(outcomes),
        "all_semantic_evidence_unique": bool(outcomes)
        and all(
            outcome.acceptance.semantic_evidence_unique for outcome in outcomes
        ),
        **ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD),
        "scientific_metrics_calculated_for_admitted_cases": bool(outcomes),
        "fresh_cases_consumed": 0,
        "remaining_fresh_cases_preserved": 7,
        "next_fresh_preregistration": None,
        "qualification_credit": False,
        "trusted_promotion": False,
        "graph_writes": 0,
    }
    write_json_atomic(paths.result, result)
    write_final_report(paths.report, result)
    return INVALID_TERMINAL


def _scientific_context(
    paths: V11Run2Paths,
    *,
    validated: bool,
) -> dict[str, object]:
    return {
        "preregistered_root_cause_classification": _ROOT_CAUSE,
        "frozen_scientific_change": _SCIENTIFIC_CHANGE,
        "scientific_contract_validated_during_run": validated,
        "operational_root_cause_classification": "PROVIDER_QUEUE_STALL",
        "transport": "DIRECT_OPENAI_FOREGROUND_RESPONSES",
        "run1_report_correction_sha256": _sha256(paths.report_correction),
    }


def _decision(*, all_passed: bool, failure: str | None) -> str:
    if all_passed:
        return PASS_TERMINAL
    if failure == "BOUNDARY_RULE_ERROR":
        return BOUNDARY_FAIL_TERMINAL
    if failure == "SEMANTIC_EVIDENCE_GROUNDING_FAILURE":
        return GROUNDING_FAIL_TERMINAL
    return UNRELATED_FAIL_TERMINAL


def _fields(
    outcomes: tuple[CaseOutcome, ...],
    comparison_name: str,
    field_name: str,
) -> list[str]:
    return sorted(
        {
            field
            for outcome in outcomes
            for field in cast(
                "tuple[str, ...]",
                getattr(getattr(outcome, comparison_name), field_name),
            )
        }
    )


def _slc12a3_corrected(outcomes: tuple[CaseOutcome, ...]) -> bool:
    return any(
        outcome.case_id == "generalization-uncertainty"
        and outcome.acceptance.v10_boundary.target_correction_observed is True
        and outcome.acceptance.v10_boundary.forbidden_suffix_absent is True
        for outcome in outcomes
    )


def _negated_repaired(outcomes: tuple[CaseOutcome, ...]) -> bool:
    return any(
        outcome.case_id == "generalization-negated-association"
        and outcome.acceptance.semantic_evidence_unique
        and outcome.acceptance.negated_complete_sentence_observed is True
        for outcome in outcomes
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "BOUNDARY_FAIL_TERMINAL",
    "GROUNDING_FAIL_TERMINAL",
    "INVALID_TERMINAL",
    "PASS_TERMINAL",
    "UNRELATED_FAIL_TERMINAL",
    "CaseOutcome",
    "InvalidTerminal",
    "persist_case_evaluation",
    "persist_invalid_terminal",
    "persist_scientific_terminal",
]
