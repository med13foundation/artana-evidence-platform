"""Direct foreground provider boundary for V11 exposed run 2."""

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
from scripts.validation.public_gold.staged_event.generalization.repair_v11_run2.config import (
    EXPERIMENT_ID,
    FOREGROUND_REQUEST_TIMEOUT_SECONDS,
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
) -> ForegroundProviderExecution[V9StagedGeneralizationOutput]:
    """Create one foreground response with no application generation ceiling."""

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
            "artana_scientific_change": (
                "UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING"
            ),
            "artana_execution_continuation": "TRANSPORT_ONLY_RUN_2",
            "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
        },
    )
    return execute_foreground_provider_call_telemetry_v2(
        api_key=api_key,
        request=request,
        request_timeout_seconds=FOREGROUND_REQUEST_TIMEOUT_SECONDS,
        output_model=V9StagedGeneralizationOutput,
        runtime=ForegroundExecutionRuntime(
            on_completed=lambda response_id: acknowledge_attempt(
                paths.attempt,
                response_id=response_id,
            )
        ),
    )


__all__ = ["execute_case", "provider_format"]
