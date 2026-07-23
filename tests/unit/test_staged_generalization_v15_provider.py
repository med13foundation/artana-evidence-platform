"""V15 request identity over frozen V13 transport regressions."""

from __future__ import annotations

from scripts.validation.public_gold.staged_event.generalization.repair_v14.provider import (
    build_request as build_v14_request,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.config import (
    CASE_ORDER,
    EXPERIMENT_ID,
    MODEL,
    REASONING_EFFORT,
)
from scripts.validation.public_gold.staged_event.generalization.repair_v15.provider import (
    build_request,
)


def test_v15_request_identifies_the_frozen_scientific_and_transport_boundaries() -> (
    None
):
    request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="a" * 64,
    )

    assert request.provider_model_id == MODEL
    assert request.reasoning_effort == REASONING_EFFORT
    assert request.metadata == {
        "artana_experiment": EXPERIMENT_ID,
        "artana_preregistration_sha256": "a" * 64,
        "artana_case_id": CASE_ORDER[0],
        "artana_scientific_change": (
            "FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1"
        ),
        "artana_evaluation_contract": (
            "V14_LOCAL_EVALUATOR_REUSED_BYTE_IDENTICAL_WITH_RAW_REVIEW_ONLY_CG"
        ),
        "artana_operational_policy": "RECORD_ONLY_USAGE_CUMULATIVE_5_USD",
        "artana_transport_implementation": "V13_REUSED_BYTE_IDENTICAL",
    }


def test_v15_request_preserves_every_nonmetadata_v14_field() -> None:
    v14_request = build_v14_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="c" * 64,
    )
    v15_request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="c" * 64,
    )

    assert v15_request.provider_input == v14_request.provider_input
    assert v15_request.provider_format == v14_request.provider_format
    assert v15_request.provider_model_id == v14_request.provider_model_id
    assert v15_request.reasoning_effort == v14_request.reasoning_effort
    assert v15_request.pricing == v14_request.pricing


def test_v15_request_has_record_only_usage_and_no_generation_or_cost_ceiling() -> None:
    request = build_request(
        case_id=CASE_ORDER[0],
        provider_input="frozen input",
        preregistration_sha256="b" * 64,
    )

    assert request.pricing == {
        "input": 0.000001,
        "cached_input": 0.0000001,
        "output": 0.000006,
    }
    assert not hasattr(request, "max_output_tokens")
    assert not hasattr(request, "max_total_tokens")
    assert not hasattr(request, "max_cost_usd")
