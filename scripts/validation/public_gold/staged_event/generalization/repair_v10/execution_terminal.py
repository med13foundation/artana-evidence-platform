"""Persist V10 case evaluations, terminal results, and the final report."""

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
    BoundaryAcceptance,
    V9Comparison,
    comparison_json,
    metrics_json,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
    EXPERIMENT_ID,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    V10ExecutionPaths,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_accounting import (
        OperationalLedger,
    )

PASS_TERMINAL = "V10_EXPOSED_GATE_PASS_READY_FOR_NEW_FRESH_PREREGISTRATION"
FAIL_TERMINAL = "V10_EXPOSED_GATE_FAIL_MODEL_CORRECTION_REQUIRED"
INVALID_TERMINAL = "INVALID_V10_EXECUTION"


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case_id: str
    response_id: str
    usage: dict[str, object]
    metrics: DualLaneCaseMetrics
    comparison: V9Comparison
    acceptance: BoundaryAcceptance
    gene_or_protein_occurrences: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "response_id": self.response_id,
            "usage": self.usage,
            "scientific_grader": metrics_json(self.metrics),
            "v9_comparison": comparison_json(self.comparison),
            "boundary_acceptance": self.acceptance.as_json(),
            "gene_or_protein_occurrences": list(
                self.gene_or_protein_occurrences
            ),
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
                "artana.staged_generalization.v10_exposed_case_evaluation.v1"
            ),
            "experiment_id": EXPERIMENT_ID,
            **outcome.as_json(),
            "qualification_credit": False,
            "graph_writes": 0,
        },
    )


def persist_scientific_terminal(
    paths: V10ExecutionPaths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: OperationalLedger,
    planned_case_count: int,
    grading_policy_sha256: str,
) -> str:
    all_passed = (
        len(outcomes) == planned_case_count
        and all(outcome.acceptance.passed for outcome in outcomes)
    )
    decision = PASS_TERMINAL if all_passed else FAIL_TERMINAL
    scientific = aggregate(tuple(outcome.metrics for outcome in outcomes))
    result = {
        **scientific,
        "schema_version": (
            "artana.staged_generalization.v10_exposed_run_result.v1"
        ),
        "experiment_id": EXPERIMENT_ID,
        "decision": decision,
        "single_scientific_change": "NAMED_BIOMEDICAL_OCCURRENCE_BOUNDARY",
        "planned_case_count": planned_case_count,
        "executed_case_count": len(outcomes),
        "stopped_after_case_id": outcomes[-1].case_id,
        "first_failure_classification": next(
            (
                outcome.acceptance.failure_classification
                for outcome in outcomes
                if not outcome.acceptance.passed
            ),
            None,
        ),
        "case_outcomes": [outcome.as_json() for outcome in outcomes],
        "v9_preserved_fields": sorted(
            {
                field
                for outcome in outcomes
                for field in outcome.comparison.preserved_fields
            }
        ),
        "v9_improved_fields": sorted(
            {
                field
                for outcome in outcomes
                for field in outcome.comparison.improved_fields
            }
        ),
        "v9_regressed_fields": sorted(
            {
                field
                for outcome in outcomes
                for field in outcome.comparison.regressed_fields
            }
        ),
        "v9_count_regressions": sorted(
            {
                field
                for outcome in outcomes
                for field in outcome.comparison.count_regressions
            }
        ),
        "slc12a3_corrected_by_actual_model_call": _slc12a3_corrected(outcomes),
        "grading_policy_sha256": grading_policy_sha256,
        "all_receipts_valid": True,
        **ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD),
        "model": f"openai:{MODEL}",
        "reasoning_effort": REASONING_EFFORT,
        "fresh_cases_consumed": 0,
        "remaining_fresh_cases_preserved": 7,
        "optional_consumed_case_diagnostic": (
            "AUTHORIZED_SEPARATE_PREREGISTRATION_REQUIRED"
            if all_passed
            else "SKIPPED_PUBLIC_GATE_FAILED"
        ),
        "qualification_credit": False,
        "trusted_promotion": False,
        "graph_writes": 0,
    }
    write_json_atomic(paths.result, result)
    _write_report(paths, result)
    return decision


def persist_invalid_terminal(
    paths: V10ExecutionPaths,
    *,
    outcomes: tuple[CaseOutcome, ...],
    ledger: OperationalLedger,
    failure: InvalidTerminal,
    planned_case_count: int,
) -> str:
    result = {
        "schema_version": (
            "artana.staged_generalization.v10_exposed_invalid_result.v1"
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


def _slc12a3_corrected(outcomes: tuple[CaseOutcome, ...]) -> bool:
    return any(
        outcome.case_id == "generalization-uncertainty"
        and outcome.acceptance.target_correction_observed is True
        and outcome.acceptance.forbidden_suffix_absent is True
        for outcome in outcomes
    )


def _write_report(
    paths: V10ExecutionPaths,
    result: dict[str, object],
) -> None:
    cases = cast("list[dict[str, object]]", result.get("case_outcomes", []))
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
    case_lines = "\n".join(
        "- `{}`: grader `{}`, V10 gate `{}`, failure `{}`.".format(
            item["case_id"],
            _nested(item, "scientific_grader", "passed"),
            _nested(item, "boundary_acceptance", "passed"),
            _nested(item, "boundary_acceptance", "failure_classification"),
        )
        for item in cases
    )
    report = (
        "# Staged Generalization V10 Exposed Run\n\n"
        "## 1. Historical V9 reproducibility\n\n"
        "V9 reproduces at its pinned commit. Current receipt code is isolated by "
        "the versioned provenance artifact and is not authorized to rewrite or "
        "rescore V9.\n\n"
        "## 2. Exposed/public case outcomes\n\n"
        f"{case_lines or '- No scientifically admitted case.'}\n\n"
        "## 3. SLC12A3 actual-call correction\n\n"
        f"`{result.get('slc12a3_corrected_by_actual_model_call', False)}`\n\n"
        "## 4. Preserved and regressed V9 fields\n\n"
        f"- Preserved: `{result.get('v9_preserved_fields', [])}`\n"
        f"- Improved: `{result.get('v9_improved_fields', [])}`\n"
        f"- Regressed: `{result.get('v9_regressed_fields', [])}`\n"
        f"- Count regressions: `{result.get('v9_count_regressions', [])}`\n\n"
        "## 5. Boundary versus unrelated failures\n\n"
        f"First failure classification: "
        f"`{result.get('first_failure_classification', result.get('failure_stage'))}`.\n\n"
        "## 6. Provider execution and budget\n\n"
        f"`{accounting}`\n\n"
        "## 7. Optional consumed-case diagnostic\n\n"
        f"`{result.get('optional_consumed_case_diagnostic')}`\n\n"
        "## 8. Fresh-case accounting\n\n"
        f"Fresh cases consumed: `{result.get('fresh_cases_consumed', 0)}`. "
        f"Remaining preserved: "
        f"`{result.get('remaining_fresh_cases_preserved', 7)}`.\n\n"
        "## 9. Graph and promotion state\n\n"
        f"Graph writes: `{result.get('graph_writes', 0)}`. Trusted promotion: "
        f"`{result.get('trusted_promotion', False)}`.\n\n"
        "## 10. Terminal decision\n\n"
        f"`{result['decision']}`\n"
    )
    paths.report.parent.mkdir(parents=True, exist_ok=True)
    paths.report.write_text(report, encoding="utf-8")


def _nested(value: dict[str, object], outer: str, inner: str) -> object:
    nested = value.get(outer)
    return nested.get(inner) if isinstance(nested, dict) else None


__all__ = [
    "FAIL_TERMINAL",
    "INVALID_TERMINAL",
    "PASS_TERMINAL",
    "CaseOutcome",
    "InvalidTerminal",
    "persist_case_evaluation",
    "persist_invalid_terminal",
    "persist_scientific_terminal",
]
