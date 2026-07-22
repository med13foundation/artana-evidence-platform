"""Exactly-once Luna execution for one frozen V6 generalization case."""

from __future__ import annotations

from typing import cast

from openai.lib._parsing._responses import type_to_text_format_param

from scripts.validation.provider_receipt_boundary.background import (
    BackgroundExecutionBudgets,
    BackgroundExecutionRuntime,
    BackgroundProviderExecution,
    execute_background_provider_call,
)
from scripts.validation.public_gold.lossless_event_provider import ProviderRequest
from scripts.validation.public_gold.staged_event.context_experiment.source_first.attempts import (
    acknowledge_attempt,
)
from scripts.validation.public_gold.staged_event.generalization.contracts import (
    StagedGeneralizationOutput,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v6.config import (
    EXPERIMENT_ID,
    MAX_COST_USD,
    MAX_LATENCY_SECONDS,
    MAX_OUTPUT_TOKENS,
    MAX_TOTAL_TOKENS,
    MODEL,
    REASONING_EFFORT,
    CaseArtifactPaths,
)


def provider_format() -> dict[str, object]:
    value = cast(
        "dict[str, object]",
        type_to_text_format_param(StagedGeneralizationOutput),
    )
    value["description"] = (
        "Source-grounded staged scientific event inventory, referential "
        "grounding, linking, and semantics."
    )
    return value


def execute_case(
    *,
    api_key: str,
    case_id: str,
    provider_input: str,
    preregistration_sha256: str,
    paths: CaseArtifactPaths,
) -> BackgroundProviderExecution[StagedGeneralizationOutput]:
    request = ProviderRequest(
        provider_input=provider_input,
        provider_format=provider_format(),
        provider_model_id=MODEL,
        reasoning_effort=REASONING_EFFORT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        max_total_tokens=MAX_TOTAL_TOKENS,
        max_cost_usd=MAX_COST_USD,
        max_latency_seconds=MAX_LATENCY_SECONDS,
        pricing={"input": 0.000001, "cached_input": 0.0000001, "output": 0.000006},
        metadata={
            "artana_experiment": EXPERIMENT_ID,
            "artana_preregistration_sha256": preregistration_sha256,
            "artana_case_id": case_id,
        },
    )
    return execute_background_provider_call(
        api_key=api_key,
        request=request,
        transport_budgets=BackgroundExecutionBudgets(30, 5, 900),
        output_model=StagedGeneralizationOutput,
        runtime=BackgroundExecutionRuntime(
            on_acknowledged=lambda response_id: acknowledge_attempt(
                paths.attempt,
                response_id=response_id,
            )
        ),
    )


__all__ = ["execute_case", "provider_format"]
