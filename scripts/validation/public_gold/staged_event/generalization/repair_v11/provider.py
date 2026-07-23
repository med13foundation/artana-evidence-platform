"""Exactly-once V11 transport with record-only provider telemetry."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v11.config import (
    EXPERIMENT_ID,
    MODEL,
    REASONING_EFFORT,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
        CaseExecutionPaths,
    )


def execute_case(
    *,
    api_key: str,
    case_id: str,
    provider_input: str,
    preregistration_sha256: str,
    paths: CaseExecutionPaths,
) -> BackgroundProviderExecution[V9StagedGeneralizationOutput]:
    """Create one background response without application generation ceilings."""

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
            "artana_scientific_change": ("UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"),
            "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
        },
    )
    return execute_background_provider_call_telemetry_v2(
        api_key=api_key,
        request=request,
        transport_budgets=BackgroundExecutionBudgets(30, 5, 900),
        output_model=V9StagedGeneralizationOutput,
        runtime=BackgroundExecutionRuntime(
            on_acknowledged=lambda response_id: acknowledge_attempt(
                paths.attempt,
                response_id=response_id,
            )
        ),
    )


__all__ = ["execute_case", "provider_format"]
