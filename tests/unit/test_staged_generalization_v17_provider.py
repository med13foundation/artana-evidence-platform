"""V17 request identity and immutable-schema regressions."""

from __future__ import annotations

import json

from scripts.validation.public_gold.staged_event.generalization.repair_v16.provider import (
    build_request as build_v16_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.config import (
    CASE_ORDER,
    EXPERIMENT_ID,
    MODEL,
    REASONING_EFFORT,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v17.provider import (
    build_request,
)


def test_v17_request_reuses_v16_schema_and_freezes_inline_scope_boundary() -> None:
    request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="a" * 64,
    )
    serialized_schema = json.dumps(request.provider_format, sort_keys=True)

    assert request.provider_model_id == MODEL
    assert request.reasoning_effort == REASONING_EFFORT
    assert "participant_scope_links" in serialized_schema
    assert "partitive_scope" in serialized_schema
    assert request.metadata == {
        "artana_experiment": EXPERIMENT_ID,
        "artana_preregistration_sha256": "a" * 64,
        "artana_case_id": CASE_ORDER[0],
        "artana_scientific_change": "INLINE_VERSUS_ANAPHORIC_SCOPE_BOUNDARY_V1",
        "artana_evaluation_contract": (
            "V17_LOCAL_SCOPE_EVALUATOR_WITH_V16_UNCERTAINTY_OVERLAY_"
            "AND_NO_INLINE_DECOMPOSITION"
        ),
        "artana_output_schema": "V16_REUSED_BYTE_IDENTICAL_NO_NEW_SCHEMA",
        "artana_inline_scope_policy": "NO_INLINE_OPTIONAL_SCOPE_DECOMPOSITION",
        "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
        "artana_transport_implementation": "V13_REUSED_BYTE_IDENTICAL",
    }


def test_v17_changes_only_metadata_and_format_description_from_v16() -> None:
    v16_request = build_v16_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="b" * 64,
    )
    v17_request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="b" * 64,
    )

    assert v17_request.provider_input == v16_request.provider_input
    assert v17_request.provider_model_id == v16_request.provider_model_id
    assert v17_request.reasoning_effort == v16_request.reasoning_effort
    assert v17_request.pricing == v16_request.pricing
    assert _without_description(v17_request.provider_format) == _without_description(
        v16_request.provider_format
    )
    assert (
        v17_request.provider_format["description"]
        != (v16_request.provider_format["description"])
    )


def test_v17_request_has_record_only_usage_and_no_token_or_cost_ceiling() -> None:
    request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="c" * 64,
    )

    assert request.pricing == {
        "input": 0.000001,
        "cached_input": 0.0000001,
        "output": 0.000006,
    }
    assert not hasattr(request, "max_output_tokens")
    assert not hasattr(request, "max_total_tokens")
    assert not hasattr(request, "max_cost_usd")


def _without_description(value: dict[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if key != "description"}
