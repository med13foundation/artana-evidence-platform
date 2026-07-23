"""Exactly-once direct foreground provider boundary for V12."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.validation.provider_receipt_boundary.background.contracts import (
    TelemetryProviderRequestV2,
)
from scripts.validation.provider_receipt_boundary.foreground import (
    ForegroundExecutionRuntime,
    ForegroundProviderExecution,
    execute_foreground_provider_call_telemetry_v2,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v12.config import (
    EXPERIMENT_ID,
    MODEL,
    REASONING_EFFORT,
    REQUEST_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
        CaseExecutionPaths,
    )


def build_request(
    *,
    case_id: str,
    provider_input: str,
    preregistration_sha256: str,
) -> TelemetryProviderRequestV2:
    """Build a request with record-only telemetry and no generation ceiling."""

    return TelemetryProviderRequestV2(
        provider_input=provider_input,
        provider_format=provider_format(),
        provider_model_id=MODEL,
        reasoning_effort=REASONING_EFFORT,
        pricing={
            "input": 0.000001,
            "cached_input": 0.0000001,
            "output": 0.000006,
        },
        metadata={
            "artana_experiment": EXPERIMENT_ID,
            "artana_preregistration_sha256": preregistration_sha256,
            "artana_case_id": case_id,
            "artana_scientific_change": "FOCUS_EVENT_ANCHORING",
            "artana_evaluation_contract": "SOURCE_SEMANTICS_PLUS_CG_PROJECTION",
            "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
        },
    )


def execute_case(
    *,
    api_key: str,
    case_id: str,
    provider_input: str,
    preregistration_sha256: str,
    paths: CaseExecutionPaths,
) -> ForegroundProviderExecution[V9StagedGeneralizationOutput]:
    request = build_request(
        case_id=case_id,
        provider_input=provider_input,
        preregistration_sha256=preregistration_sha256,
    )
    return execute_foreground_provider_call_telemetry_v2(
        api_key=api_key,
        request=request,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        output_model=V9StagedGeneralizationOutput,
        runtime=ForegroundExecutionRuntime(
            on_completed=lambda response_id: acknowledge_attempt(
                paths.attempt,
                response_id=response_id,
            )
        ),
    )


__all__ = ["build_request", "execute_case", "provider_format"]
