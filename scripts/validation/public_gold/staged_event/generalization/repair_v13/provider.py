"""Exactly-once direct foreground provider boundary for V13."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from openai.lib._parsing._responses import type_to_text_format_param

from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v9.contracts import (
    V9StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.config import (
    EXPERIMENT_ID,
    MODEL,
    REASONING_EFFORT,
    REQUEST_TIMEOUT_SECONDS,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.provider_execution import (
    V13ForegroundExecutionRuntime,
    V13ProviderExecution,
    execute_v13_foreground_call,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v13.request_contract import (
    V13ForegroundProviderRequest,
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
) -> V13ForegroundProviderRequest:
    """Build a request with record-only telemetry and no generation ceiling."""

    return V13ForegroundProviderRequest(
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
            "artana_scientific_change": ("COMPOSITIONAL_FOCUS_ROOT_SELECTION"),
            "artana_evaluation_contract": (
                "SOURCE_SEMANTICS_WITH_REVIEW_ONLY_CG_PROJECTION"
            ),
            "artana_operational_policy": ("RECORD_ONLY_USAGE_CUMULATIVE_5_USD"),
        },
    )


def provider_format() -> dict[str, object]:
    """Build the unchanged V9 scientific schema without importing its transport."""

    value = cast(
        "dict[str, object]",
        type_to_text_format_param(V9StagedGeneralizationOutput),
    )
    value["description"] = (
        "Source-grounded staged scientific event inventory, referential "
        "grounding, linking, and versioned classification-argument semantics."
    )
    return value


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
