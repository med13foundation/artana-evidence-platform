"""Provider-free tests for the sealed V14 deterministic-mapping path."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import pytest

from scripts.validation.claim_events.finite_source_unit.contracts import (
    SourceUnitExtractionOutput,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14 import (
    execution as execution_module,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.execution import (
    V14_EXECUTION_MANIFEST_SHA256,
    V14ExecutionContractError,
    computed_v14_execution_manifest_sha256,
    execute_v14_source_unit_agents,
    has_locally_consistent_v14_execution,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v14.prompts import (
    V14_EXTRACTION_PROMPT_VERSION,
    V14_NORMALIZATION_PROMPT_VERSION,
    V14_NORMALIZED_REVIEW_PROMPT_VERSION,
    v14_normalization_prompt,
    v14_normalized_review_prompt,
    v14_source_unit_extraction_prompt,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    NormalizationOperation,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
    SourceUnitNormalizedReviewOutputV13V6,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v14_contracts import (
    SourceUnitNormalizationProposalV14,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    FiniteSourceUnitModelClient,
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    enumerate_source_units,
)

_SOURCE = "IL-4 does not affect Foxp3 expression."


def _argument(
    role: str,
    event_role: str,
    exact_span: str,
    *,
    invalid_anchor: bool = False,
    mixed_anchor: bool = False,
) -> dict[str, object]:
    return {
        "role": role,
        "event_role": event_role,
        "exact_span": exact_span,
        "mention_anchors": (
            [
                {
                    "left_context": "",
                    "mention_span": exact_span,
                    "right_context": " does not affect",
                },
                {
                    "left_context": "IL-4 does not affect ",
                    "mention_span": "Foxp3",
                    "right_context": " expression.",
                },
            ]
            if mixed_anchor
            else
            [
                {
                    "left_context": "invented repeated context ",
                    "mention_span": exact_span,
                    "right_context": " invented suffix",
                }
            ]
            if invalid_anchor
            else []
        ),
        "referent_anchors": [],
        "controlled_event_ref": None,
        "role_rationale": "The source explicitly assigns this event role.",
    }


def _event(
    *,
    invalid_anchor: bool = False,
    mixed_anchor: bool = False,
) -> dict[str, object]:
    return {
        "exact_span": _SOURCE,
        "relation_cue_span": "does not affect",
        "arguments": [
            _argument(
                "GENE_OR_PROTEIN",
                "AGENT",
                "IL-4",
                invalid_anchor=invalid_anchor,
                mixed_anchor=mixed_anchor,
            ),
            _argument("GENE_OR_PROTEIN", "THEME", "Foxp3"),
        ],
        "source_locator": "normalized_extraction_text",
        "claim_kind": "SCIENTIFIC_FINDING",
        "event_type": "NO_EFFECT",
        "assertion_scope": "SOURCE_ASSERTED",
        "polarity": "NULL_RESULT",
        "epistemic_status": "ASSERTED",
        "local_event_id": "null-event",
        "inventory_rationale": "The source explicitly reports the null result.",
    }


def _extraction() -> SourceUnitExtractionOutput:
    return SourceUnitExtractionOutput.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "decision": "EXPLICIT_EVENT",
            "events": [_event()],
            "reasoning": "The source explicitly reports one null event.",
        }
    )


def _proposal(
    *,
    invalid_anchor: bool = False,
    mixed_anchor: bool = False,
) -> SourceUnitNormalizationProposalV14:
    return SourceUnitNormalizationProposalV14.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "family": "DIRECT",
            "abstention_reason": "NONE",
            "events": [
                _event(
                    invalid_anchor=invalid_anchor,
                    mixed_anchor=mixed_anchor,
                )
            ],
            "mappings": [
                {
                    "normalized_event_position": 0,
                    "source_event_positions": [0],
                    "reasoning": "The same source event is represented.",
                    "falsification_condition": "A changed event would falsify it.",
                }
            ],
            "context_dimensions": [],
            "reasoning": "The direct representation is complete.",
            "falsification_condition": "A controlled process would require nesting.",
        }
    )


def _review() -> SourceUnitNormalizedReviewOutputV13V6:
    return SourceUnitNormalizedReviewOutputV13V6.model_validate(
        {
            "eligibility_category": "NULL_RESULT",
            "inventory_coverage": "COMPLETE",
            "unsupported_additions": "ABSENT",
            "family_validity": "VALID",
            "cue_alignment": "EXACT",
            "axis_reviews": [
                {
                    "axis": axis.value,
                    "decision": "PRESERVED",
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The source and normalized event agree.",
                    "falsification_condition": "A changed axis would falsify it.",
                }
                for axis in MaterialAxis
            ],
            "candidate_reviews": [
                {
                    "normalized_event_position": 0,
                    "source_entailment": "ENTAILED",
                    "evidence_spans": [_SOURCE],
                    "reasoning": "The source entails the complete null event.",
                    "falsification_condition": "A changed participant would falsify it.",
                }
            ],
            "context_dimension_reviews": [],
            "reasoning": "The proposal preserves the source event.",
            "falsification_condition": "An omitted event would falsify completeness.",
        }
    )


class _V14Client:
    def __init__(
        self,
        *,
        invalid_anchor: bool = False,
        mixed_anchor: bool = False,
    ) -> None:
        self.invalid_anchor = invalid_anchor
        self.mixed_anchor = mixed_anchor
        self.calls: list[type[object]] = []
        self.prompts: list[str] = []

    async def step(self, **kwargs: object) -> object:
        schema = cast("type[object]", kwargs["output_schema"])
        self.calls.append(schema)
        self.prompts.append(cast("str", kwargs["prompt"]))
        if schema is SourceUnitExtractionOutput:
            output: object = _extraction()
        elif schema is SourceUnitNormalizationProposalV14:
            output = _proposal(
                invalid_anchor=self.invalid_anchor,
                mixed_anchor=self.mixed_anchor,
            )
        else:
            assert schema is SourceUnitNormalizedReviewOutputV13V6
            output = _review()
        return SimpleNamespace(
            output=output,
            run_id=kwargs["run_id"],
            seq=len(self.calls),
            replayed=False,
            response_id=f"resp_v14_{len(self.calls)}",
            response_output_items=(),
        )


def test_v14_prompt_removes_operation_authority_and_forbids_invented_anchors() -> None:
    unit = enumerate_source_units(case_id="v14-prompt", source_text=_SOURCE)[0]
    original = bind_source_unit_extraction(_extraction(), unit=unit)

    prompt = v14_normalization_prompt(unit=unit, original=original)

    assert "and choose UNCHANGED, REFRAME" not in prompt
    assert "mark that mapping REFRAME" not in prompt
    assert "not return UNCHANGED, REFRAME, SPLIT, MERGE" in prompt
    assert "never an implied repetition" in prompt
    assert "event exact_span must be one contiguous" in prompt
    assert "extend exact_span back to the participant's one literal" in prompt
    assert f"prompt_version: {V14_NORMALIZATION_PROMPT_VERSION}" in prompt


def test_v14_primary_prompt_separates_mentions_from_referents() -> None:
    unit = enumerate_source_units(case_id="v14-primary-prompt", source_text=_SOURCE)[0]

    prompt = v14_source_unit_extraction_prompt(unit)

    assert "Every mention_anchor.mention_span must equal that exact_span" in prompt
    assert "source-verbatim referent_anchors for its antecedent" in prompt
    assert "never return a score, probability, confidence" in prompt
    assert f"prompt_version: {V14_EXTRACTION_PROMPT_VERSION}" in prompt


def test_v14_review_treats_operations_as_provenance_not_quality() -> None:
    unit = enumerate_source_units(case_id="v14-review-prompt", source_text=_SOURCE)[0]
    original = bind_source_unit_extraction(_extraction(), unit=unit)
    from scripts.validation.claim_events.finite_source_unit.normalization.v14_service import (
        bind_source_unit_normalization_v14,
    )

    normalized = bind_source_unit_normalization_v14(
        _proposal(),
        unit=unit,
        original=original,
    )

    prompt = v14_normalized_review_prompt(
        unit=unit,
        original=original,
        normalized=normalized.canonical_result,
    )

    assert "They are provenance, not agent judgments" in prompt
    assert "Never treat REFRAME frequency as scientific loss" in prompt
    assert f"prompt_version: {V14_NORMALIZED_REVIEW_PROMPT_VERSION}" in prompt


def test_v14_execution_manifest_is_frozen() -> None:
    assert computed_v14_execution_manifest_sha256() == V14_EXECUTION_MANIFEST_SHA256


def test_v14_manifest_seals_top_level_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = computed_v14_execution_manifest_sha256()
    monkeypatch.setattr(execution_module, "_schema_identity", lambda _schema: "forged")

    assert computed_v14_execution_manifest_sha256() != original


@pytest.mark.asyncio
async def test_v14_executes_three_agent_stages_with_derived_mapping() -> None:
    unit = enumerate_source_units(case_id="v14-success", source_text=_SOURCE)[0]
    client = _V14Client()

    evidence = await execute_v14_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        execution_namespace="v14-success-test",
        unit=unit,
    )

    assert client.calls == [
        SourceUnitExtractionOutput,
        SourceUnitNormalizationProposalV14,
        SourceUnitNormalizedReviewOutputV13V6,
    ]
    assert evidence.error_type is None
    assert evidence.failed_stage is None
    assert evidence.normalization_envelope is not None
    assert evidence.normalization_envelope.derived_operations == (
        NormalizationOperation.UNCHANGED,
    )
    assert evidence.local_review_passed is True
    assert evidence.scientifically_qualified is False
    assert has_locally_consistent_v14_execution(evidence) is True


@pytest.mark.asyncio
async def test_v14_malformed_anchor_stops_before_review_without_repair() -> None:
    unit = enumerate_source_units(case_id="v14-anchor-stop", source_text=_SOURCE)[0]
    client = _V14Client(invalid_anchor=True)

    evidence = await execute_v14_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        execution_namespace="v14-anchor-stop-test",
        unit=unit,
    )

    assert client.calls == [
        SourceUnitExtractionOutput,
        SourceUnitNormalizationProposalV14,
    ]
    assert evidence.error_type == "StructuredModelSemanticError"
    assert evidence.failed_stage == "structure_normalization"
    assert evidence.normalization_proposal is None
    assert evidence.normalization_envelope is None
    assert evidence.normalization_raw_output == _proposal(
        invalid_anchor=True
    ).model_dump(mode="json")
    assert [record.validation_outcome for record in evidence.records] == [
        "accepted",
        "semantic_invalid",
    ]
    assert evidence.local_review_passed is False
    assert has_locally_consistent_v14_execution(evidence) is False


@pytest.mark.asyncio
async def test_v14_mixed_entity_anchors_stop_before_review() -> None:
    unit = enumerate_source_units(case_id="v14-mixed-anchor", source_text=_SOURCE)[0]
    client = _V14Client(mixed_anchor=True)

    evidence = await execute_v14_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        execution_namespace="v14-mixed-anchor-test",
        unit=unit,
    )

    assert client.calls == [
        SourceUnitExtractionOutput,
        SourceUnitNormalizationProposalV14,
    ]
    assert evidence.error_type == "StructuredModelSemanticError"
    assert evidence.failed_stage == "structure_normalization"
    assert evidence.normalization_envelope is None
    assert evidence.local_review_passed is False


@pytest.mark.asyncio
async def test_v14_rejects_detached_derived_operations() -> None:
    unit = enumerate_source_units(case_id="v14-custody", source_text=_SOURCE)[0]
    client = _V14Client()
    evidence = await execute_v14_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        execution_namespace="v14-custody-test",
        unit=unit,
    )
    assert evidence.normalization_envelope is not None
    forged = replace(
        evidence.normalization_envelope,
        derived_operations=(NormalizationOperation.REFRAME,),
    )

    with pytest.raises(
        ValueError,
        match="normalization envelope is not canonical",
    ):
        replace(evidence, normalization_envelope=forged)


@pytest.mark.asyncio
async def test_v14_rejects_rewritten_local_audit_lineage() -> None:
    unit = enumerate_source_units(case_id="v14-lineage", source_text=_SOURCE)[0]
    client = _V14Client()
    evidence = await execute_v14_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        execution_namespace="v14-lineage-test",
        unit=unit,
        audit_evidence_unit_id="v14-lineage-audit",
    )
    rewritten = tuple(
        replace(record, step_key="forged-step-key") for record in evidence.records
    )

    with pytest.raises(ValueError, match="static lineage was rewritten"):
        replace(evidence, records=rewritten)

    with pytest.raises(ValueError, match="static lineage was rewritten"):
        replace(evidence, audit_evidence_unit_id="forged-audit-unit")

    missing_kernel = (
        replace(evidence.records[0], kernel_run_id=None),
        *evidence.records[1:],
    )
    with pytest.raises(ValueError, match="kernel run is detached"):
        replace(evidence, records=missing_kernel)


@pytest.mark.asyncio
async def test_v14_terminal_success_cannot_be_empty() -> None:
    unit = enumerate_source_units(case_id="v14-empty", source_text=_SOURCE)[0]
    evidence = await execute_v14_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", _V14Client()),
        tenant=object(),
        model_id="openai/gpt-5.6-luna",
        execution_namespace="v14-empty-test",
        unit=unit,
    )

    with pytest.raises(ValueError, match="terminal success requires all three"):
        replace(
            evidence,
            original_extraction=None,
            original_result=None,
            original_raw_output=None,
            normalization_proposal=None,
            normalization_envelope=None,
            normalization_raw_output=None,
            normalized_review=None,
            review_result=None,
            review_raw_output=None,
            records=(),
        )


@pytest.mark.asyncio
async def test_v14_rejects_unissued_model_before_any_call() -> None:
    unit = enumerate_source_units(case_id="v14-model", source_text=_SOURCE)[0]
    client = _V14Client()

    with pytest.raises(V14ExecutionContractError, match="model is not authorized"):
        await execute_v14_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai/gpt-5-mini",
            execution_namespace="v14-model-test",
            unit=unit,
        )

    assert client.calls == []
