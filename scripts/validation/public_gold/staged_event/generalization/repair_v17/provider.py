"""V17 identity over the frozen exactly-once V13 transport."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

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
from scripts.validation.public_gold.staged_event.generalization.repair_v16.contracts import (
    V16StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.provider import (
    provider_format as v16_provider_format,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.config import (
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
    """Build one V17 request without a token or per-case cost ceiling."""

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
            "artana_scientific_change": ("INLINE_VERSUS_ANAPHORIC_SCOPE_BOUNDARY_V1"),
            "artana_evaluation_contract": (
                "V17_LOCAL_SCOPE_EVALUATOR_WITH_V16_UNCERTAINTY_OVERLAY_"
                "AND_NO_INLINE_DECOMPOSITION"
            ),
            "artana_output_schema": "V16_REUSED_BYTE_IDENTICAL_NO_NEW_SCHEMA",
            "artana_inline_scope_policy": ("NO_INLINE_OPTIONAL_SCOPE_DECOMPOSITION"),
            "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
            "artana_transport_implementation": "V13_REUSED_BYTE_IDENTICAL",
        },
    )


def provider_format() -> dict[str, object]:
    """Reuse the V16 schema while freezing V17's narrower scope instruction."""

    value = v16_provider_format()
    value["description"] = (
        "Source-grounded staged biomedical event output using the immutable V16 "
        "schema. Retain a material inline restriction inside its complete "
        "participant span; separately represent scope only when an independently "
        "grounded non-inline anaphoric or aggregate relation requires it."
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
    """Create exactly once and acknowledge the reserved V17 attempt."""

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
