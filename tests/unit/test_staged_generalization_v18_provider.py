"""V18 request identity and immutable-schema regressions."""

from __future__ import annotations

import json

from scripts.validation.public_gold.staged_event.generalization.repair_v17.provider import (
    build_request as build_v17_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v18.config import (
    CASE_ORDER,
    EXPERIMENT_ID,
    MODEL,
    REASONING_EFFORT,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v18.provider import (
    build_request,
)


def test_v18_request_reuses_v16_schema_and_freezes_anaphoric_locus_boundary() -> None:
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
        "artana_scientific_change": "ANAPHORIC_LOCUS_COMPLETENESS_V1",
        "artana_evaluation_contract": (
            "V17_EVALUATOR_REUSED_BYTE_IDENTICAL_NO_LOCAL_CHANGE"
        ),
        "artana_output_schema": "V16_REUSED_BYTE_IDENTICAL_NO_NEW_SCHEMA",
        "artana_inline_scope_policy": "NO_INLINE_OPTIONAL_SCOPE_DECOMPOSITION",
        "artana_anaphoric_locus_policy": (
            "NON_INLINE_LOCUS_SCOPE_MANDATORY_WHEN_ANAPHOR_DEPENDS_ON_IT"
        ),
        "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
        "artana_transport_implementation": "V13_REUSED_BYTE_IDENTICAL",
    }


def test_v18_changes_only_metadata_and_format_description_from_v17() -> None:
    v17_request = build_v17_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="b" * 64,
    )
    v18_request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="b" * 64,
    )

    assert v18_request.provider_input == v17_request.provider_input
    assert v18_request.provider_model_id == v17_request.provider_model_id
    assert v18_request.reasoning_effort == v17_request.reasoning_effort
    assert v18_request.pricing == v17_request.pricing
    assert _without_description(v18_request.provider_format) == _without_description(
        v17_request.provider_format
    )
    assert (
        v18_request.provider_format["description"]
        != (v17_request.provider_format["description"])
    )


def test_v18_request_has_record_only_usage_and_no_token_or_cost_ceiling() -> None:
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
