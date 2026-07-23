"""Exactly-once Fresh-CG V2 transport with record-only usage telemetry."""

from __future__ import annotations

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundExecutionBudgets,
    BackgroundExecutionRuntime,
    BackgroundProviderExecution,
    TelemetryProviderRequestV2,
    execute_background_provider_call_telemetry_v2,
)
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v1.provider_contract import (
    FreshCGProviderOutput,
)
from scripts.validation.public_gold.staged_event.generalization.fresh_cg_v2.config import (
    EXPERIMENT_ID,
    MODEL,
    REASONING_EFFORT,
    CaseArtifactPaths,
)


def execute_case(
    *,
    api_key: str,
    case_id: str,
    provider_input: str,
    preregistration_sha256: str,
    paths: CaseArtifactPaths,
) -> BackgroundProviderExecution[FreshCGProviderOutput]:
    request = TelemetryProviderRequestV2(
        provider_input=provider_input,
        provider_format=provider_format(),
        provider_model_id=MODEL,
        reasoning_effort=REASONING_EFFORT,
        pricing={"input": 0.000001, "cached_input": 0.0000001, "output": 0.000006},
        metadata={
            "artana_experiment": EXPERIMENT_ID,
            "artana_preregistration_sha256": preregistration_sha256,
            "artana_case_id": case_id,
            "artana_scientific_change": "NONE",
            "artana_instrumentation_change": ("ABSOLUTE_SOURCE_OCCURRENCE_BINDINGS_V2"),
            "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
        },
    )
    return execute_background_provider_call_telemetry_v2(
        api_key=api_key,
        request=request,
        transport_budgets=BackgroundExecutionBudgets(30, 5, 900),
        output_model=FreshCGProviderOutput,
        runtime=BackgroundExecutionRuntime(
            on_acknowledged=lambda response_id: acknowledge_attempt(
                paths.attempt,
                response_id=response_id,
            )
        ),
    )


__all__ = ["execute_case", "provider_format"]
