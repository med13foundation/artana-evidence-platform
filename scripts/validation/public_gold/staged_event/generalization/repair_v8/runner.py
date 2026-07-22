"""Fail-fast execution of the preregistered V8 checkpoint."""

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
from scripts.validation.public_gold.staged_event.generalization.grading.artifacts import (
    verify_frozen_policy,
)
from scripts.validation.public_gold.staged_event.generalization.grading.evaluation import (
    DualLaneCaseMetrics,
    aggregate,
    evaluate_case,
)
from scripts.validation.public_gold.staged_event.generalization.grading.policy import (
    case_policy,
    policy_sha256,
)
from scripts.validation.public_gold.staged_event.generalization.panel import build_panel
from scripts.validation.public_gold.staged_event.generalization.repair_v8.config import (
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
from scripts.validation.public_gold.staged_event.generalization.repair_v8.contracts import (
    V8StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8.preflight import (
    provider_input,
    verify,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v8.provider import (
    execute_case,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

ProviderCall = Callable[
    [str, str, str, str, CaseArtifactPaths],
    BackgroundProviderExecution[V8StagedGeneralizationOutput],
]


class V8ExecutionError(RuntimeError):
    """The V8 checkpoint cannot execute without violating frozen custody."""


@dataclass(frozen=True, slots=True)
class V8Runtime:
    provider_call: ProviderCall
    after_persist: Callable[[], None] = lambda: None


@dataclass(frozen=True, slots=True)
class InvalidExecution:
    reason: str
    stage: str
    failed_case_id: str
    acknowledged_response_id: str | None = None
    diagnostics: dict[str, object] | None = None


def _live_call(
    api_key: str,
    case_id: str,
    value: str,
    preregistration_sha256: str,
    paths: CaseArtifactPaths,
) -> BackgroundProviderExecution[V8StagedGeneralizationOutput]:
    return execute_case(
        api_key=api_key,
        case_id=case_id,
        provider_input=value,
        preregistration_sha256=preregistration_sha256,
        paths=paths,
    )


def execute(
    runtime: V8Runtime | None = None,
    *,
    paths: ExperimentPaths = DEFAULT_PATHS,
) -> str:
    """Run canary-first and stop on invalid custody or scientific failure."""

    _require_unused(paths)
    verify(paths)
    policy = verify_frozen_policy(paths.grading)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise V8ExecutionError("OPENAI_API_KEY is absent")
    preregistration_sha256 = hashlib.sha256(
        paths.preregistration.read_bytes()
    ).hexdigest()
    active = runtime or V8Runtime(_live_call)
    metrics: list[DualLaneCaseMetrics] = []
    executions: list[BackgroundProviderExecution[BaseModel]] = []
    cases = build_panel()

    for case in cases:
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
        value = provider_input(paths, case.case_id)
        reserve_attempt(
            case_paths.attempt,
            stage=f"GENERALIZATION_V8:{case.case_id}",
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
                    stage=f"GENERALIZATION_V8:{case.case_id}",
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
        case_metrics = evaluate_case(
            case,
            execution.extraction,
            case_policy(policy, case.case_id),
        )
        metrics.append(case_metrics)
        if not case_metrics.passed:
            return _write_scientific_result(
                paths,
                tuple(metrics),
                executions,
                planned_case_count=len(cases),
                grading_policy_sha256=policy_sha256(policy),
            )

    return _write_scientific_result(
        paths,
        tuple(metrics),
        executions,
        planned_case_count=len(cases),
        grading_policy_sha256=policy_sha256(policy),
    )


def _write_scientific_result(
    paths: ExperimentPaths,
    metrics: tuple[DualLaneCaseMetrics, ...],
    executions: list[BackgroundProviderExecution[BaseModel]],
    *,
    planned_case_count: int,
    grading_policy_sha256: str,
) -> str:
    result = aggregate(metrics)
    result.update(
        {
            "experiment_id": EXPERIMENT_ID,
            "scientific_change": "SOURCE_GENERAL_POLARITY_TAXONOMY",
            "planned_case_count": planned_case_count,
            "stopped_after_case_id": metrics[-1].case_id,
            "grading_policy_sha256": grading_policy_sha256,
            **_accounting(executions),
            "all_receipts_valid": True,
            "model": f"openai:{MODEL}",
            "reasoning_effort": REASONING_EFFORT,
        }
    )
    write_json_atomic(paths.result, result)
    return cast("str", result["decision"])


def _write_invalid(
    paths: ExperimentPaths,
    *,
    executions: list[BackgroundProviderExecution[BaseModel]],
    failure: InvalidExecution,
) -> str:
    accounting = _accounting(executions)
    response_ids = cast("list[str]", accounting["response_ids"])
    if failure.acknowledged_response_id is not None:
        response_ids.append(failure.acknowledged_response_id)
        accounting["provider_calls"] = cast("int", accounting["provider_calls"]) + 1
    write_json_atomic(
        paths.result,
        {
            "schema_version": "artana.staged_generalization.v8_invalid.v1",
            "experiment_id": EXPERIMENT_ID,
            "decision": "INVALID_PROVIDER_EXECUTION",
            "failure_stage": failure.stage,
            "root_cause": failure.reason,
            "failed_case_id": failure.failed_case_id,
            "diagnostics": failure.diagnostics or {},
            **accounting,
            "response_ids": response_ids,
            "failed_call_usage_verified": False,
            "scientific_metrics_calculated": False,
            "qualification_credit": False,
            "review_only": True,
            "trusted_promotion": False,
            "graph_writes": 0,
        },
    )
    return "INVALID_PROVIDER_EXECUTION"


def _accounting(
    executions: list[BackgroundProviderExecution[BaseModel]],
) -> dict[str, object]:
    usage: list[dict[str, object]] = []
    response_ids: list[str] = []
    for execution in executions:
        item = execution.receipt.get("usage")
        identity = execution.receipt.get("identity")
        if not isinstance(item, dict) or not isinstance(identity, dict):
            raise V8ExecutionError("verified receipt accounting is absent")
        response_id = identity.get("response_id")
        if not isinstance(response_id, str):
            raise V8ExecutionError("verified response identity is absent")
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


def _require_unused(paths: ExperimentPaths) -> None:
    candidates = [paths.result]
    for case in build_panel():
        item = paths.case(case.case_id)
        candidates.extend((item.attempt, item.bundle, item.receipt, item.raw_output))
    if any(path.exists() for path in candidates):
        raise V8ExecutionError(f"{EXPERIMENT_ID} already started")


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
        V8StagedGeneralizationOutput.model_json_schema(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def _int(value: dict[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int):
        raise V8ExecutionError(f"verified {key} is absent")
    return item


def _float(value: dict[str, object], key: str) -> float:
    item = value.get(key)
    if not isinstance(item, int | float):
        raise V8ExecutionError(f"verified {key} is absent")
    return float(item)


__all__ = ["V8ExecutionError", "V8Runtime", "execute"]
