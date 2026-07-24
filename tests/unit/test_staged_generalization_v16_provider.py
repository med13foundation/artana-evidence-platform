"""V16 request identity over the frozen exactly-once transport."""

from __future__ import annotations

import json

from scripts.validation.public_gold.staged_event.generalization.repair_v15.provider import (
    build_request as build_v15_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.config import (
    CASE_ORDER,
    EXPERIMENT_ID,
    MODEL,
    REASONING_EFFORT,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v16.provider import (
    build_request,
)


def test_v16_request_freezes_the_new_schema_and_scientific_boundary() -> None:
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
        "artana_scientific_change": "PARTICIPANT_SCOPE_AND_PARTITIVE_REPRESENTATION_V1",
        "artana_evaluation_contract": (
            "V16_LOCAL_SCOPE_EVALUATOR_WITH_NON_TARGET_EXTENSION_REJECTION_"
            "AND_RAW_V14_REVIEW_ONLY_CG"
        ),
        "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
        "artana_transport_implementation": "V13_REUSED_BYTE_IDENTICAL",
    }


def test_v16_request_changes_only_schema_and_metadata_from_v15() -> None:
    v15_request = build_v15_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="b" * 64,
    )
    v16_request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="b" * 64,
    )

    assert v16_request.provider_input == v15_request.provider_input
    assert v16_request.provider_model_id == v15_request.provider_model_id
    assert v16_request.reasoning_effort == v15_request.reasoning_effort
    assert v16_request.pricing == v15_request.pricing
    assert v16_request.provider_format != v15_request.provider_format


def test_v16_request_has_record_only_usage_and_no_token_or_cost_ceiling() -> None:
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
