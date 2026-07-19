"""Regression tests for the V11 three-call agent topology."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from artana_evidence_api.document_extraction_support.llm_extraction.structured_step import (
    StructuredModelSemanticError,
)

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v10.prompts import (
    v10_source_unit_extraction_prompt,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v11.prompts import (
    V11_EXTRACTION_PROMPT_POLICY,
    V11_NORMALIZATION_PROMPT_VERSION,
    V11_NORMALIZED_REVIEW_PROMPT_VERSION,
    v11_normalization_prompt,
    v11_normalized_review_prompt,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    execute_three_source_unit_agents,
)
from scripts.validation.claim_events.finite_source_unit.normalization.review import (
    bind_source_unit_normalized_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.service import (
    bind_source_unit_normalization,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v12_contracts import (
    SourceUnitNormalizationOutputV12,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    FiniteSourceUnitModelClient,
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    enumerate_source_units,
)

_SOURCE = "IL-4 did not affect FOXP3 expression in T cells."


def _argument(role: str, event_role: str, exact_span: str) -> dict[str, object]:
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": exact_span,
        "mention_anchors": [],
        "referent_anchors": [],
        "controlled_event_ref": None,
        "role_rationale": "The source explicitly assigns this role.",
    }


def _event() -> dict[str, object]:
    return {
        "exact_span": _SOURCE,
        "relation_cue_span": "did not affect",
        "arguments": [
            _argument("GENE_OR_PROTEIN", "AGENT", "IL-4"),
            _argument("GENE_OR_PROTEIN", "THEME", "FOXP3"),
            _argument("OUTCOME", "EFFECT", "FOXP3 expression"),
            _argument("POPULATION", "CONTEXT", "T cells"),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "NO_EFFECT",
        "assertion_scope": "SOURCE_ASSERTED",
        "polarity": "NULL_RESULT",
        "epistemic_status": "ASSERTED",
        "local_event_id": "null-effect",
        "inventory_rationale": "The source explicitly reports no effect.",
    }


def _extraction() -> SourceUnitExtractionOutput:
    return SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "decision": "EXPLICIT_EVENT",
            "events": [_event()],
            "reasoning": "PRIVATE ORIGINAL REASONING",
        }
    )


def _normalization(*, bad_mapping: bool = False) -> SourceUnitNormalizationOutput:
    return SourceUnitNormalizationOutput.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "family": "DIRECT",
            "abstention_reason": "NONE",
            "events": [_event()],
            "mappings": [
                {
                    "normalized_event_position": 0,
                    "source_event_positions": [1 if bad_mapping else 0],
                    "operation": "UNCHANGED",
                    "reasoning": "PRIVATE NORMALIZER REASONING",
                    "falsification_condition": "A changed event would falsify this map.",
                }
            ],
            "reasoning": "PRIVATE NORMALIZATION SUMMARY",
            "falsification_condition": "A controlled target would require nesting.",
        }
    )


def _v12_normalization() -> SourceUnitNormalizationOutputV12:
    return SourceUnitNormalizationOutputV12.model_validate(
        _normalization().model_dump(mode="json")
    )


def _review(*, axis_decision: str = "PRESERVED") -> SourceUnitNormalizedReviewOutput:
    return SourceUnitNormalizedReviewOutput.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "inventory_coverage": "COMPLETE",
            "unsupported_additions": "ABSENT",
            "family_validity": "VALID",
            "cue_alignment": "EXACT",
            "axis_reviews": [
                {
                    "axis": axis.value,
                    "decision": axis_decision,
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The structures preserve this axis.",
                    "falsification_condition": "A changed axis value would falsify it.",
                }
                for axis in MaterialAxis
            ],
            "candidate_reviews": [
                {
                    "normalized_event_position": 0,
                    "source_entailment": "ENTAILED",
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The complete event is source entailed.",
                    "falsification_condition": "A different participant would falsify it.",
                }
            ],
            "reasoning": "The normalized representation is lossless.",
            "falsification_condition": "Any missing context would falsify completeness.",
        }
    )


class _ThreeCallClient:
    def __init__(self, *, bad_mapping: bool = False) -> None:
        self.bad_mapping = bad_mapping
        self.calls: list[type[object]] = []
        self.prompts: list[str] = []

    async def step(self, **kwargs: object) -> object:
        schema = cast("type[object]", kwargs["output_schema"])
        self.calls.append(schema)
        self.prompts.append(cast("str", kwargs["prompt"]))
        if schema is SourceUnitExtractionOutput:
            output: object = _extraction()
        elif schema in {
            SourceUnitNormalizationOutput,
            SourceUnitNormalizationOutputV12,
        }:
            output = (
                _v12_normalization()
                if schema is SourceUnitNormalizationOutputV12
                else _normalization(bad_mapping=self.bad_mapping)
            )
        else:
            assert schema is SourceUnitNormalizedReviewOutput
            output = _review()
        return SimpleNamespace(
            output=output,
            run_id=kwargs["run_id"],
            seq=len(self.calls),
            replayed=False,
            response_id=f"resp_v11_{len(self.calls)}",
            response_output_items=(),
        )


@pytest.mark.asyncio
async def test_three_call_path_preserves_outputs_and_audit_topology() -> None:
    unit = enumerate_source_units(case_id="v11-three-call", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    result = await execute_three_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v11-three-call-test",
        unit=unit,
        extraction_prompt_policy=V11_EXTRACTION_PROMPT_POLICY,
        normalization_prompt_builder=v11_normalization_prompt,
        normalization_prompt_version=V11_NORMALIZATION_PROMPT_VERSION,
        review_prompt_builder=v11_normalized_review_prompt,
        review_prompt_version=V11_NORMALIZED_REVIEW_PROMPT_VERSION,
    )

    assert client.calls == [
        SourceUnitExtractionOutput,
        SourceUnitNormalizationOutput,
        SourceUnitNormalizedReviewOutput,
    ]
    assert result.error_type is None
    assert result.original_raw_output == _extraction().model_dump(mode="json")
    assert result.normalized_raw_output == _normalization().model_dump(mode="json")
    assert result.review_result is not None
    assert result.review_result.scientific_loss_count == 0
    assert [record.attempt_role for record in result.records] == [
        "primary",
        "structure_normalization",
        "normalized_review",
    ]
    assert "PRIVATE ORIGINAL REASONING" in client.prompts[1]
    assert "PRIVATE ORIGINAL REASONING" not in client.prompts[2]
    assert "PRIVATE NORMALIZER REASONING" not in client.prompts[2]
    assert len({record.provider_response_id for record in result.records}) == 3
    assert client.prompts[0].endswith(v10_source_unit_extraction_prompt(unit))


@pytest.mark.asyncio
async def test_three_call_path_uses_injected_v12_normalization_schema() -> None:
    unit = enumerate_source_units(case_id="v12-three-call", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    result = await execute_three_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v12-three-call-test",
        unit=unit,
        extraction_prompt_policy=V11_EXTRACTION_PROMPT_POLICY,
        normalization_prompt_builder=v11_normalization_prompt,
        normalization_prompt_version=V11_NORMALIZATION_PROMPT_VERSION,
        normalization_output_schema=SourceUnitNormalizationOutputV12,
        review_prompt_builder=v11_normalized_review_prompt,
        review_prompt_version=V11_NORMALIZED_REVIEW_PROMPT_VERSION,
    )

    assert client.calls == [
        SourceUnitExtractionOutput,
        SourceUnitNormalizationOutputV12,
        SourceUnitNormalizedReviewOutput,
    ]
    assert result.error_type is None
    assert isinstance(result.normalized_extraction, SourceUnitNormalizationOutputV12)


def test_not_applicable_axes_are_unresolved_not_silent_passes() -> None:
    unit = enumerate_source_units(case_id="v11-not-applicable", source_text=_SOURCE)[0]
    original = bind_source_unit_extraction(_extraction(), unit=unit)
    normalized = bind_source_unit_normalization(
        _normalization(),
        unit=unit,
        original=original,
    )

    reviewed = bind_source_unit_normalized_review(
        _review(axis_decision="NOT_APPLICABLE"),
        unit=unit,
        original=original,
        normalized=normalized,
    )

    assert reviewed.unresolved_axis_count == len(MaterialAxis)


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ("REFRAME", "REFRAME must alter"),
        ("SPLIT", "SPLIT requires one source event to produce multiple"),
    ],
)
def test_normalization_rejects_false_operation_labels(
    operation: str,
    message: str,
) -> None:
    unit = enumerate_source_units(case_id="mapping-operation", source_text=_SOURCE)[0]
    original = bind_source_unit_extraction(_extraction(), unit=unit)
    payload = _normalization().model_dump(mode="json")
    mappings = payload["mappings"]
    assert isinstance(mappings, list)
    assert isinstance(mappings[0], dict)
    mappings[0]["operation"] = operation
    normalized = SourceUnitNormalizationOutput.model_validate(payload)

    with pytest.raises(StructuredModelSemanticError, match=message):
        bind_source_unit_normalization(normalized, unit=unit, original=original)


def test_normalization_accepts_reframe_when_representation_changes() -> None:
    unit = enumerate_source_units(case_id="mapping-reframe", source_text=_SOURCE)[0]
    original = bind_source_unit_extraction(_extraction(), unit=unit)
    payload = _normalization().model_dump(mode="json")
    events = payload["events"]
    mappings = payload["mappings"]
    assert isinstance(events, list)
    assert isinstance(events[0], dict)
    assert isinstance(mappings, list)
    assert isinstance(mappings[0], dict)
    events[0]["local_event_id"] = "reframed-null-effect"
    mappings[0]["operation"] = "REFRAME"
    normalized = SourceUnitNormalizationOutput.model_validate(payload)

    result = bind_source_unit_normalization(normalized, unit=unit, original=original)

    assert result.output.events[0].local_event_id == "reframed-null-effect"


@pytest.mark.asyncio
async def test_three_call_path_stops_after_semantically_invalid_normalization() -> None:
    unit = enumerate_source_units(case_id="v11-three-call-stop", source_text=_SOURCE)[0]
    client = _ThreeCallClient(bad_mapping=True)

    result = await execute_three_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v11-three-call-stop-test",
        unit=unit,
        extraction_prompt_policy=V11_EXTRACTION_PROMPT_POLICY,
        normalization_prompt_builder=v11_normalization_prompt,
        normalization_prompt_version=V11_NORMALIZATION_PROMPT_VERSION,
        review_prompt_builder=v11_normalized_review_prompt,
        review_prompt_version=V11_NORMALIZED_REVIEW_PROMPT_VERSION,
    )

    assert client.calls == [SourceUnitExtractionOutput, SourceUnitNormalizationOutput]
    assert result.error_type == "StructuredModelSemanticError"
    assert result.normalized_extraction is None
    assert result.normalized_review is None
    assert [record.validation_outcome for record in result.records] == [
        "accepted",
        "semantic_invalid",
    ]
    assert result.failed_stage == "structure_normalization"


@pytest.mark.asyncio
async def test_three_call_path_records_failure_between_provider_stages() -> None:
    unit = enumerate_source_units(case_id="v11-builder-stop", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    def fail_normalization_prompt(**_kwargs: object) -> str:
        raise RuntimeError("simulated prompt construction failure")

    result = await execute_three_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v11-builder-stop-test",
        unit=unit,
        extraction_prompt_policy=V11_EXTRACTION_PROMPT_POLICY,
        normalization_prompt_builder=fail_normalization_prompt,
        normalization_prompt_version=V11_NORMALIZATION_PROMPT_VERSION,
        review_prompt_builder=v11_normalized_review_prompt,
        review_prompt_version=V11_NORMALIZED_REVIEW_PROMPT_VERSION,
    )

    assert client.calls == [SourceUnitExtractionOutput]
    assert result.error_type == "SourceUnitPromptBuildError"
    assert result.failed_stage == "structure_normalization"
    assert [record.validation_outcome for record in result.records] == ["accepted"]
