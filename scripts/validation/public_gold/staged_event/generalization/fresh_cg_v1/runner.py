"""Fail-fast execution of the frozen fresh-CG occurrence-V2 experiment."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundProviderExecution,
)
from scripts.validation.public_gold.lossless_event_provider import (
    ProviderExecutionError,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    reserve_attempt,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    CustodyPersistenceError,
    StageCustodyInput,
    StageCustodyPaths,
    persist_stage_custody,
    write_json_atomic,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.config import (
    DEFAULT_PATHS,
    EXPERIMENT_ID,
    GLOBAL_MAX_CALLS,
    GLOBAL_MAX_COST_USD,
    MAX_COST_USD,
    MODEL,
    REASONING_EFFORT,
    CaseArtifactPaths,
    ExperimentPaths,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.evaluation import (
    FreshCaseMetrics,
    aggregate,
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.preflight import (
    verify,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider import (
    execute_case,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_input import (
    provider_input,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.reference_contracts import (
    FreshCGTwoLaneReference,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.selection import (
    load_frozen_selection,
)
from scripts.validation.public_gold.staged_event.generalization.occurrence_evaluator_v2.bindings import (
    OccurrenceBindingError,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

ProviderCall = Callable[
    [str, str, str, str, CaseArtifactPaths],
    BackgroundProviderExecution[FreshCGProviderOutput],
]


class FreshCGExecutionError(RuntimeError):
    """Execution cannot continue without violating frozen custody."""


@dataclass(frozen=True, slots=True)
class FreshCGRuntime:
    provider_call: ProviderCall
    after_persist: Callable[[], None] = lambda: None


@dataclass(frozen=True, slots=True)
class InvalidExecution:
    reason: str
    stage: str
    failed_case_id: str
    creation_attempted: bool = False
    acknowledged_response_id: str | None = None
    diagnostics: dict[str, object] | None = None


def _live_call(
    api_key: str,
    case_id: str,
    value: str,
    preregistration_sha256: str,
    paths: CaseArtifactPaths,
) -> BackgroundProviderExecution[FreshCGProviderOutput]:
    return execute_case(
        api_key=api_key,
        case_id=case_id,
        provider_input=value,
        preregistration_sha256=preregistration_sha256,
        paths=paths,
    )


def execute(
    runtime: FreshCGRuntime | None = None,
    *,
    paths: ExperimentPaths = DEFAULT_PATHS,
) -> str:
    """Execute at most once per case, stopping before the case after a failure."""

    selection = load_frozen_selection(paths.selection)
    _require_unused(paths, tuple(case.case_id for case in selection.cases))
    verify(paths, remote_gate=True, offline_regression=True)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise FreshCGExecutionError("OPENAI_API_KEY is absent")
    preregistration_sha256 = hashlib.sha256(
        paths.preregistration.read_bytes()
    ).hexdigest()
    reference = FreshCGTwoLaneReference.model_validate_json(
        paths.reference.read_text(encoding="utf-8")
    )
    references = {case.case_id: case for case in reference.cases}
    active = runtime or FreshCGRuntime(_live_call)
    metrics: list[FreshCaseMetrics] = []
    executions: list[BackgroundProviderExecution[BaseModel]] = []

    for case in selection.cases:
        if not _prospective_budget_allows(executions):
            return _write_invalid(
                paths,
                executions=executions,
                failure=InvalidExecution(
                    reason="global prospective call or cost budget exhausted",
                    stage="PROSPECTIVE_BUDGET",
                    failed_case_id=case.case_id,
                ),
            )
        case_paths = paths.case(case.case_id)
        value = provider_input(
            case,
            scientific_prompt_path=paths.scientific_prompt,
            binding_prompt_path=paths.binding_prompt,
        )
        reserve_attempt(
            case_paths.attempt,
            stage=f"FRESH_CG_V1:{case.case_id}",
            provider_input=value,
            preregistration_sha256=preregistration_sha256,
        )
        try:
            execution = active.provider_call(
                api_key,
                case.case_id,
                value,
                preregistration_sha256,
                case_paths,
            )
        except ProviderExecutionError as exc:
            return _write_invalid(
                paths,
                executions=executions,
                failure=InvalidExecution(
                    reason=exc.root_cause,
                    stage=exc.stage,
                    failed_case_id=case.case_id,
                    creation_attempted=True,
                    acknowledged_response_id=_attempt_response_id(case_paths.attempt),
                    diagnostics=exc.diagnostics,
                ),
            )
        try:
            persist_stage_custody(
                custody_input=StageCustodyInput(
                    paths=StageCustodyPaths(
                        bundle=case_paths.bundle,
                        receipt=case_paths.receipt,
                        raw_output=case_paths.raw_output,
                    ),
                    stage=f"FRESH_CG_V1:{case.case_id}",
                    provider_input=value,
                    schema_sha256=_canonical_schema_sha256(),
                ),
                output=execution.extraction,
                canonical_payload=execution.canonical_payload,
                receipt=execution.receipt,
            )
            active.after_persist()
        except CustodyPersistenceError as exc:
            executions.append(cast("BackgroundProviderExecution[BaseModel]", execution))
            return _write_invalid(
                paths,
                executions=executions,
                failure=InvalidExecution(
                    reason=str(exc),
                    stage="LOCAL_CUSTODY",
                    failed_case_id=case.case_id,
                ),
            )
        executions.append(cast("BackgroundProviderExecution[BaseModel]", execution))
        try:
            case_metrics = evaluate_case(
                case,
                references[case.case_id],
                execution.extraction,
            )
        except OccurrenceBindingError as exc:
            return _write_invalid(
                paths,
                executions=executions,
                failure=InvalidExecution(
                    reason=str(exc),
                    stage="OCCURRENCE_BINDING",
                    failed_case_id=case.case_id,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - fail closed on evaluator defects.
            return _write_invalid(
                paths,
                executions=executions,
                failure=InvalidExecution(
                    reason=f"{type(exc).__name__}: {exc}",
                    stage="EVALUATOR_DEFECT",
                    failed_case_id=case.case_id,
                ),
            )
        metrics.append(case_metrics)
        if not case_metrics.passed:
            return _write_scientific_result(
                paths,
                tuple(metrics),
                executions,
                planned_case_count=len(selection.cases),
            )

    return _write_scientific_result(
        paths,
        tuple(metrics),
        executions,
        planned_case_count=len(selection.cases),
    )


def _write_scientific_result(
    paths: ExperimentPaths,
    metrics: tuple[FreshCaseMetrics, ...],
    executions: list[BackgroundProviderExecution[BaseModel]],
    *,
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
            "experiment_id": EXPERIMENT_ID,
            "planned_case_count": planned_case_count,
            "stopped_after_case_id": metrics[-1].case_id,
            "terminal_stage": terminal_stage,
            **_accounting(executions),
            "all_receipts_valid": True,
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
            "scientific_readiness": result["decision"],
            "evaluator_governance_readiness": "PASS",
            "production_readiness": "NOT_READY_INDEPENDENT_REPLICATION_REQUIRED",
        }
    )
    _persist_terminal(paths, result)
    return cast("str", result["decision"])


def _write_invalid(
    paths: ExperimentPaths,
    *,
    executions: list[BackgroundProviderExecution[BaseModel]],
    failure: InvalidExecution,
) -> str:
    accounting = _accounting(executions)
    response_ids = cast("list[str]", accounting["response_ids"])
    acknowledged_not_accounted = (
        failure.acknowledged_response_id is not None
        and failure.acknowledged_response_id not in response_ids
    )
    if acknowledged_not_accounted:
        assert failure.acknowledged_response_id is not None
        response_ids.append(failure.acknowledged_response_id)
    if failure.creation_attempted:
        accounting["provider_calls"] = cast("int", accounting["provider_calls"]) + 1
    result: dict[str, object] = {
        "schema_version": "artana.staged_generalization.fresh_cg_invalid.v1",
        "experiment_id": EXPERIMENT_ID,
        "decision": "INVALID_EXPERIMENT_EXECUTION",
        "failure_stage": failure.stage,
        "root_cause": failure.reason,
        "failed_case_id": failure.failed_case_id,
        "diagnostics": failure.diagnostics or {},
        **accounting,
        "response_ids": response_ids,
        "scientific_metrics_calculated": False,
        "qualification_credit": False,
        "trusted_graph_ready": False,
        "graph_writes": 0,
        "scientific_readiness": "UNSCORED_INVALID_EXECUTION",
        "evaluator_governance_readiness": "FAIL_CLOSED",
        "production_readiness": "NOT_READY",
    }
    _persist_terminal(paths, result)
    return "INVALID_EXPERIMENT_EXECUTION"


def _persist_terminal(paths: ExperimentPaths, result: dict[str, object]) -> None:
    write_json_atomic(paths.result, result)
    paths.report.parent.mkdir(parents=True, exist_ok=True)
    report = _render_report(result)
    paths.report.write_text(report, encoding="utf-8")
    if paths.report.read_text(encoding="utf-8") != report:
        raise FreshCGExecutionError("terminal report differs after readback")


def _render_report(result: dict[str, object]) -> str:
    decision = result.get("decision", "UNKNOWN")
    stopped = result.get("stopped_after_case_id", result.get("failed_case_id", "NONE"))
    return (
        "# Fresh CG occurrence-V2 experiment\n\n"
        f"- Decision: `{decision}`\n"
        f"- Stopped after/at: `{stopped}`\n"
        f"- Terminal stage: `{result.get('terminal_stage', result.get('failure_stage'))}`\n"
        f"- Provider calls: `{result.get('provider_calls', 0)}`\n"
        f"- Verified cost (USD): `{result.get('cost_usd', 0)}`\n"
        "- Direct CG required fidelity: "
        f"`{result.get('direct_cg_required_fidelity', 'UNSCORED')}`\n"
        "- Artana source-semantic fidelity: "
        f"`{result.get('artana_source_semantic_fidelity', 'UNSCORED')}`\n"
        "- Occurrence-binding fidelity: "
        f"`{result.get('occurrence_binding_fidelity', 'UNSCORED')}`\n"
        f"- Scientific readiness: `{result.get('scientific_readiness')}`\n"
        "- Evaluator/governance readiness: "
        f"`{result.get('evaluator_governance_readiness')}`\n"
        f"- Production readiness: `{result.get('production_readiness')}`\n"
        "- Qualification credit: `false`\n"
        "- Trusted graph writes: `0`\n\n"
        "The public CG reserve is fresh to Artana development but may occur in model "
        "pretraining. Even an 8/8 result is not production qualification; independent "
        "replication remains required.\n"
    )


def _accounting(
    executions: list[BackgroundProviderExecution[BaseModel]],
) -> dict[str, object]:
    usage: list[dict[str, object]] = []
    response_ids: list[str] = []
    for execution in executions:
        item = execution.receipt.get("usage")
        identity = execution.receipt.get("identity")
        if not isinstance(item, dict) or not isinstance(identity, dict):
            raise FreshCGExecutionError("verified receipt accounting is absent")
        response_id = identity.get("response_id")
        if not isinstance(response_id, str):
            raise FreshCGExecutionError("verified response identity is absent")
        usage.append(item)
        response_ids.append(response_id)
    return {
        "provider_calls": len(executions),
        "input_tokens": sum(_int(item, "input_tokens") for item in usage),
        "output_tokens": sum(_int(item, "output_tokens") for item in usage),
        "total_tokens": sum(_int(item, "total_tokens") for item in usage),
        "latency_seconds": sum(_float(item, "latency_seconds") for item in usage),
        "cost_usd": sum(_float(item, "cost_usd") for item in usage),
        "response_ids": response_ids,
    }


def _prospective_budget_allows(
    executions: list[BackgroundProviderExecution[BaseModel]],
) -> bool:
    if len(executions) + 1 > GLOBAL_MAX_CALLS:
        return False
    observed_cost = cast("float", _accounting(executions)["cost_usd"])
    return observed_cost + MAX_COST_USD <= GLOBAL_MAX_COST_USD + 1e-12


def _require_unused(paths: ExperimentPaths, case_ids: tuple[str, ...]) -> None:
    candidates = [paths.result, paths.report]
    for case_id in case_ids:
        item = paths.case(case_id)
        candidates.extend((item.attempt, item.bundle, item.receipt, item.raw_output))
    if any(path.exists() for path in candidates):
        raise FreshCGExecutionError(f"{EXPERIMENT_ID} already started")


def _attempt_response_id(path: Path) -> str | None:
    if not path.exists():
        return None
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return None
    value = loaded.get("response_id")
    return value if isinstance(value, str) else None


def _canonical_schema_sha256() -> str:
    raw = json.dumps(
        FreshCGProviderOutput.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int):
        raise FreshCGExecutionError(f"verified {key} is absent")
    return item


def _float(value: dict[str, object], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, int | float):
        raise FreshCGExecutionError(f"verified {key} is absent")
    return float(item)


__all__ = ["FreshCGExecutionError", "FreshCGRuntime", "execute"]
