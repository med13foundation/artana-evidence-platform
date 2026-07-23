"""Persist Fresh-CG V2 scientific, invalid, and operational-stop terminals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.evaluation import (
    FreshCaseMetrics,
    aggregate,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.config import (
    CONSUMED_CASE_ID,
    EXPERIMENT_ID,
    GLOBAL_MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    ExperimentPaths,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.accounting import (
        OperationalLedger,
    )


@dataclass(frozen=True, slots=True)
class InvalidTerminal:
    failed_case_id: str
    stage: str
    reason: str
    diagnostics: dict[str, object]


def persist_scientific_terminal(
    paths: ExperimentPaths,
    *,
    metrics: tuple[FreshCaseMetrics, ...],
    ledger: OperationalLedger,
    planned_case_count: int,
) -> str:
    result = aggregate(metrics)
    last = metrics[-1]
    if all(item.passed for item in metrics) and len(metrics) == planned_case_count:
        terminal_stage = "COMPLETED_CASE_ORDER"
    elif last.contradiction_count or last.unsupported_claim_count:
        terminal_stage = "CONTRADICTION_OR_UNSUPPORTED"
    else:
        terminal_stage = "SCIENTIFIC_ACCEPTANCE"
    result.update(
        {
            **_base(ledger, planned_case_count=planned_case_count),
            "stopped_after_case_id": last.case_id,
            "terminal_stage": terminal_stage,
            "scientific_metrics_calculated": True,
            "scientific_readiness": result["decision"],
            "evaluator_governance_readiness": "PASS",
            "production_readiness": "NOT_READY_INDEPENDENT_REPLICATION_REQUIRED",
        }
    )
    _persist(paths, result)
    return cast("str", result["decision"])


def persist_operational_stop(
    paths: ExperimentPaths,
    *,
    metrics: tuple[FreshCaseMetrics, ...],
    ledger: OperationalLedger,
    next_case_id: str,
    planned_case_count: int,
) -> str:
    result: dict[str, object] = {
        **_base(ledger, planned_case_count=planned_case_count),
        "schema_version": "artana.staged_generalization.fresh_cg_operational_stop.v2",
        "decision": "OPERATIONAL_BUDGET_STOP",
        "terminal_stage": "CUMULATIVE_OPERATIONAL_BUDGET",
        "next_case_not_called": next_case_id,
        "completed_scientific_cases": [asdict(item) for item in metrics],
        "scientific_metrics_calculated": bool(metrics),
        "scientific_case_results_preserved": True,
        "qualification_credit": False,
        "scientific_readiness": "INCOMPLETE_OPERATIONAL_STOP",
        "evaluator_governance_readiness": "PASS",
        "production_readiness": "NOT_READY",
    }
    _persist(paths, result)
    return "OPERATIONAL_BUDGET_STOP"


def persist_invalid_terminal(
    paths: ExperimentPaths,
    *,
    metrics: tuple[FreshCaseMetrics, ...],
    ledger: OperationalLedger,
    failure: InvalidTerminal,
    planned_case_count: int,
) -> str:
    result: dict[str, object] = {
        **_base(ledger, planned_case_count=planned_case_count),
        "schema_version": "artana.staged_generalization.fresh_cg_invalid.v2",
        "decision": "INVALID_EXPERIMENT_EXECUTION",
        "failure_stage": failure.stage,
        "root_cause": failure.reason,
        "failed_case_id": failure.failed_case_id,
        "diagnostics": failure.diagnostics,
        "completed_scientific_cases": [asdict(item) for item in metrics],
        "scientific_metrics_calculated": bool(metrics),
        "scientific_case_results_preserved": True,
        "qualification_credit": False,
        "scientific_readiness": "UNSCORED_INVALID_EXECUTION",
        "evaluator_governance_readiness": "FAIL_CLOSED",
        "production_readiness": "NOT_READY",
    }
    _persist(paths, result)
    return "INVALID_EXPERIMENT_EXECUTION"


def persist_case_evaluation(
    path: Path,
    *,
    metrics: FreshCaseMetrics,
    response_id: str,
    usage: dict[str, object],
) -> None:
    write_json_atomic(
        path,
        {
            "schema_version": (
                "artana.staged_generalization.fresh_cg_case_evaluation.v2"
            ),
            "experiment_id": EXPERIMENT_ID,
            "case_id": metrics.case_id,
            "response_id": response_id,
            "metrics": asdict(metrics),
            "usage": usage,
            "token_and_cost_affect_scientific_scoring": False,
            "graph_writes": 0,
            "promotion": False,
        },
    )


def _base(
    ledger: OperationalLedger,
    *,
    planned_case_count: int,
) -> dict[str, object]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "planned_case_count": planned_case_count,
        "consumed_v1_case_id": CONSUMED_CASE_ID,
        "consumed_v1_case_reused": False,
        **ledger.as_json(global_max_cost_usd=GLOBAL_MAX_COST_USD),
        "all_completed_receipts_valid": all(
            item.status == "VERIFIED_SCIENTIFIC_CUSTODY" for item in ledger.records
        ),
        "model": f"openai:{MODEL}",
        "reasoning_effort": REASONING_EFFORT,
        "max_output_tokens_sent": False,
        "total_token_limit_applied": False,
        "graph_writes": 0,
        "trusted_graph_ready": False,
        "promotion": False,
        "qualification_credit": False,
    }


def _persist(paths: ExperimentPaths, result: dict[str, object]) -> None:
    write_json_atomic(paths.result, result)
    paths.report.parent.mkdir(parents=True, exist_ok=True)
    report = _render_report(result)
    paths.report.write_text(report, encoding="utf-8")
    if paths.report.read_text(encoding="utf-8") != report:
        raise RuntimeError("terminal report differs after readback")


def _render_report(result: dict[str, object]) -> str:
    decision = result.get("decision", "UNKNOWN")
    stopped = result.get(
        "stopped_after_case_id",
        result.get("failed_case_id", result.get("next_case_not_called", "NONE")),
    )
    return (
        "# Fresh CG occurrence-V2 V2 experiment\n\n"
        f"- Decision: `{decision}`\n"
        f"- Stopped after/at: `{stopped}`\n"
        f"- Terminal stage: `{result.get('terminal_stage', result.get('failure_stage'))}`\n"
        f"- Provider calls: `{result.get('provider_calls', 0)}`\n"
        f"- Provider retries: `{result.get('provider_retries', 0)}`\n"
        f"- Cumulative cost (USD): `{result.get('cost_usd', 0)}`\n"
        f"- Remaining budget (USD): `{result.get('remaining_cost_usd', 0)}`\n"
        "- Direct CG required fidelity: "
        f"`{result.get('direct_cg_required_fidelity', 'PARTIAL_OR_UNSCORED')}`\n"
        "- Artana source-semantic fidelity: "
        f"`{result.get('artana_source_semantic_fidelity', 'PARTIAL_OR_UNSCORED')}`\n"
        "- Occurrence-binding fidelity: "
        f"`{result.get('occurrence_binding_fidelity', 'PARTIAL_OR_UNSCORED')}`\n"
        f"- Scientific readiness: `{result.get('scientific_readiness')}`\n"
        "- Evaluator/governance readiness: "
        f"`{result.get('evaluator_governance_readiness')}`\n"
        f"- Production readiness: `{result.get('production_readiness')}`\n"
        "- Qualification credit: `false`\n"
        "- Trusted graph writes: `0`\n\n"
        "Token count, answer length, latency, and cost were recorded as operational "
        "telemetry and did not affect scientific scoring. The cumulative $5 budget "
        "was used only to decide whether another provider call could begin.\n"
    )


__all__ = [
    "InvalidTerminal",
    "persist_case_evaluation",
    "persist_invalid_terminal",
    "persist_operational_stop",
    "persist_scientific_terminal",
]
