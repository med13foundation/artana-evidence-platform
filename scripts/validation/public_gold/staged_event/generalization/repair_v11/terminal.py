"""Persist V11 evaluations, terminal results, and the final report."""

from __future__ import annotations

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
from scripts.validation.public_gold.staged_event.generalization.repair_v11.config import (
    EXPERIMENT_ID,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    V11ExecutionPaths,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v11.acceptance import (
        V11Acceptance,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v11.accounting import (
        V11OperationalLedger,
    )

PASS_TERMINAL = "V11_EXPOSED_GATE_PASS_READY_FOR_NEW_FRESH_PREREGISTRATION"
BOUNDARY_FAIL_TERMINAL = "V11_EXPOSED_GATE_FAIL_BOUNDARY"
GROUNDING_FAIL_TERMINAL = "V11_EXPOSED_GATE_FAIL_GROUNDING"
UNRELATED_FAIL_TERMINAL = "V11_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION"
INVALID_TERMINAL = "INVALID_V11_EXECUTION"


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
                "artana.staged_generalization.v11_exposed_case_evaluation.v1"
            ),
            "experiment_id": EXPERIMENT_ID,
            **outcome.as_json(),
            "qualification_credit": False,
            "graph_writes": 0,
        },
    )


def persist_scientific_terminal(
    paths: V11ExecutionPaths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V11OperationalLedger,
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
        "schema_version": ("artana.staged_generalization.v11_exposed_run_result.v1"),
        "experiment_id": EXPERIMENT_ID,
        "decision": decision,
        "single_scientific_change": ("UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"),
        "root_cause_classification": ("SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP"),
        "planned_case_count": planned_case_count,
        "executed_case_count": len(outcomes),
        "stopped_after_case_id": outcomes[-1].case_id,
        "first_failure_classification": first_failure,
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
        "grading_policy_sha256": grading_policy_sha256,
        "all_receipts_valid": True,
        **ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD),
        "model": f"openai:{MODEL}",
        "reasoning_effort": REASONING_EFFORT,
        "fresh_cases_consumed": 0,
        "remaining_fresh_cases_preserved": 7,
        "optional_consumed_case_diagnostic": (
            "NOT_RUN_SEPARATE_PREREGISTRATION_REQUIRED"
            if all_passed
            else "SKIPPED_PUBLIC_GATE_FAILED"
        ),
        "next_fresh_preregistration_proposal": (
            "PREPARE_ONLY_NO_PROVIDER_CALLS" if all_passed else "NOT_AUTHORIZED"
        ),
        "qualification_credit": False,
        "trusted_promotion": False,
        "graph_writes": 0,
    }
    write_json_atomic(paths.result, result)
    _write_report(paths, result)
    return decision


def persist_invalid_terminal(
    paths: V11ExecutionPaths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: V11OperationalLedger,
    failure: InvalidTerminal,
    planned_case_count: int,
) -> str:
    result = {
        "schema_version": (
            "artana.staged_generalization.v11_exposed_invalid_result.v1"
        ),
        "experiment_id": EXPERIMENT_ID,
        "decision": INVALID_TERMINAL,
        "failure_stage": failure.stage,
        "root_cause": failure.reason,
        "failed_case_id": failure.failed_case_id,
        "diagnostics": failure.diagnostics,
        "planned_case_count": planned_case_count,
        "executed_case_count": len(outcomes),
        "case_outcomes": [outcome.as_json() for outcome in outcomes],
        **ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD),
        "scientific_metrics_calculated_for_admitted_cases": bool(outcomes),
        "fresh_cases_consumed": 0,
        "remaining_fresh_cases_preserved": 7,
        "optional_consumed_case_diagnostic": "SKIPPED_INVALID_EXECUTION",
        "qualification_credit": False,
        "trusted_promotion": False,
        "graph_writes": 0,
    }
    write_json_atomic(paths.result, result)
    _write_report(paths, result)
    return INVALID_TERMINAL


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


def _write_report(
    paths: V11ExecutionPaths,
    result: dict[str, object],
) -> None:
    cases = cast("list[dict[str, object]]", result.get("case_outcomes", []))
    case_lines = "\n".join(
        "- `{}`: grader `{}`, V11 gate `{}`, failure `{}`.".format(
            item["case_id"],
            _nested(item, "scientific_grader", "passed"),
            _nested(item, "v11_acceptance", "passed"),
            _nested(item, "v11_acceptance", "failure_classification"),
        )
        for item in cases
    )
    accounting = {
        key: result.get(key)
        for key in (
            "provider_calls",
            "provider_retries",
            "duplicate_creation_calls",
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "total_tokens",
            "latency_seconds",
            "cost_usd",
            "remaining_cost_usd",
        )
    }
    report = (
        "# Staged Generalization V11 Exposed Gate\n\n"
        "## 1. Root cause\n\n"
        f"`{result.get('root_cause_classification')}`\n\n"
        "## 2. Single V11 change\n\n"
        f"`{result.get('single_scientific_change')}`\n\n"
        "## 3. Exposed/public case outcomes\n\n"
        f"{case_lines or '- No scientifically admitted case.'}\n\n"
        "## 4. SLC12A3 boundary\n\n"
        f"`{result.get('slc12a3_corrected_by_actual_model_call', False)}`\n\n"
        "## 5. Negated grounding regression\n\n"
        f"`{result.get('negated_complete_unique_sentence_observed', False)}`\n\n"
        "## 6. V9 and V10 preservation\n\n"
        f"- V9 regressions: `{result.get('v9_regressed_fields', [])}`\n"
        f"- V10 regressions: `{result.get('v10_regressed_fields', [])}`\n"
        f"- V9 count regressions: `{result.get('v9_count_regressions', [])}`\n"
        f"- V10 count regressions: `{result.get('v10_count_regressions', [])}`\n\n"
        "## 7. Provider execution and budget\n\n"
        f"`{accounting}`\n\n"
        "## 8. Fresh-case accounting\n\n"
        f"Fresh cases consumed: `{result.get('fresh_cases_consumed', 0)}`. "
        f"Remaining preserved: "
        f"`{result.get('remaining_fresh_cases_preserved', 7)}`.\n\n"
        "## 9. Optional consumed diagnostic\n\n"
        f"`{result.get('optional_consumed_case_diagnostic')}`\n\n"
        "## 10. Graph and promotion state\n\n"
        f"Graph writes: `{result.get('graph_writes', 0)}`. Trusted promotion: "
        f"`{result.get('trusted_promotion', False)}`.\n\n"
        "## 11. Terminal decision\n\n"
        f"`{result['decision']}`\n"
    )
    paths.report.parent.mkdir(parents=True, exist_ok=True)
    paths.report.write_text(report, encoding="utf-8")


def _nested(value: dict[str, object], outer: str, inner: str) -> object:
    nested = value.get(outer)
    return nested.get(inner) if isinstance(nested, dict) else None


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
