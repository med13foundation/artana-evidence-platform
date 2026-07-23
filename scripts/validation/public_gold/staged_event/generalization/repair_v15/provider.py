"""V15 identity over the byte-frozen V13 exactly-once transport."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
    V13ForegroundExecutionRuntime,
    V13ProviderExecution,
    execute_v13_foreground_call,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.provider import (
    build_request as build_v14_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v14.provider import (
    provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
    EXPERIMENT_ID,
    REQUEST_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from scripts.validation.public_gold.staged_event.generalization.repair_v10.execution_config import (
        CaseExecutionPaths,
    )
    from scripts.validation.public_gold.staged_event.generalization.repair_v13.request_contract import (
        V13ForegroundProviderRequest,
    )


def build_request(
    *,
    case_id: str,
    provider_input: str,
    preregistration_sha256: str,
) -> V13ForegroundProviderRequest:
    """Build one V15 request with record-only telemetry and no token ceiling."""

    frozen_v14_request = build_v14_request(
        case_id=case_id,
        provider_input=provider_input,
        preregistration_sha256=preregistration_sha256,
    )
    return replace(
        frozen_v14_request,
        metadata={
            "artana_experiment": EXPERIMENT_ID,
            "artana_preregistration_sha256": preregistration_sha256,
            "artana_case_id": case_id,
            "artana_scientific_change": (
                "FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1"
            ),
            "artana_evaluation_contract": (
                "V14_LOCAL_EVALUATOR_REUSED_BYTE_IDENTICAL_WITH_RAW_REVIEW_ONLY_CG"
            ),
            "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
            "artana_transport_implementation": "V13_REUSED_BYTE_IDENTICAL",
        },
    )


def execute_case(
    *,
    api_key: str,
    case_id: str,
    provider_input: str,
    preregistration_sha256: str,
    paths: CaseExecutionPaths,
) -> V13ProviderExecution[V9StagedGeneralizationOutput]:
    request = build_request(
        case_id=case_id,
        provider_input=provider_input,
        preregistration_sha256=preregistration_sha256,
    )
    return execute_v13_foreground_call(
        api_key=api_key,
        request=request,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        output_model=V9StagedGeneralizationOutput,
        runtime=V13ForegroundExecutionRuntime(
            on_completed=lambda response_id: acknowledge_attempt(
                paths.attempt,
                response_id=response_id,
            )
        ),
    )


__all__ = ["build_request", "execute_case", "provider_format"]
