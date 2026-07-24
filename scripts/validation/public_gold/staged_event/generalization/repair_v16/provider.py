"""V16 identity over the byte-frozen V13 exactly-once transport."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from openai.lib._parsing._responses import type_to_text_format_param

from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
    V13ForegroundExecutionRuntime,
    V13ProviderExecution,
    execute_v13_foreground_call,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.provider import (
    build_request as build_v15_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.config import (
    EXPERIMENT_ID,
    REQUEST_TIMEOUT_SECONDS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
    V16StagedGeneralizationOutput,
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
    """Build one V16 request with the versioned schema and no token ceiling."""

    frozen_v15_request = build_v15_request(
        case_id=case_id,
        provider_input=provider_input,
        preregistration_sha256=preregistration_sha256,
    )
    return replace(
        frozen_v15_request,
        provider_format=provider_format(),
        metadata={
            "artana_experiment": EXPERIMENT_ID,
            "artana_preregistration_sha256": preregistration_sha256,
            "artana_case_id": case_id,
            "artana_scientific_change": (
                "PARTICIPANT_SCOPE_AND_PARTITIVE_REPRESENTATION_V1"
            ),
            "artana_evaluation_contract": (
                "V16_LOCAL_SCOPE_EVALUATOR_WITH_NON_TARGET_EXTENSION_REJECTION_"
                "AND_RAW_V14_REVIEW_ONLY_CG"
            ),
            "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
            "artana_transport_implementation": "V13_REUSED_BYTE_IDENTICAL",
        },
    )


def provider_format() -> dict[str, object]:
    """Build the V16 response schema without changing the transport boundary."""

    value = cast(
        "dict[str, object]",
        type_to_text_format_param(V16StagedGeneralizationOutput),
    )
    value["description"] = (
        "Source-grounded staged biomedical event output with explicit participant "
        "scope links and partitive qualifiers where the source states them."
    )
    return value


def execute_case(
    *,
    api_key: str,
    case_id: str,
    provider_input: str,
    preregistration_sha256: str,
    paths: CaseExecutionPaths,
) -> V13ProviderExecution[V16StagedGeneralizationOutput]:
    """Create exactly once and acknowledge the reserved V16 attempt on completion."""

    request = build_request(
        case_id=case_id,
        provider_input=provider_input,
        preregistration_sha256=preregistration_sha256,
    )
    return execute_v13_foreground_call(
        api_key=api_key,
        request=request,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        output_model=V16StagedGeneralizationOutput,
        runtime=V13ForegroundExecutionRuntime(
            on_completed=lambda response_id: acknowledge_attempt(
                paths.attempt,
                response_id=response_id,
            )
        ),
    )


__all__ = ["build_request", "execute_case", "provider_format"]
