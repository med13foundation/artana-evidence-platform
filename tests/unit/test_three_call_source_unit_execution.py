"""Regression tests for the V11 three-call agent topology."""

from __future__ import annotations

import inspect
from dataclasses import replace
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
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13.execution import (
    V13_EXECUTION_POLICY,
    V13_EXECUTION_POLICY_V3,
    V13HistoricalSchemaCustodyError,
    execute_v13_source_unit_agents,
    execute_v13_v3_source_unit_agents,
    has_locally_consistent_v13_v3_execution,
    qualifies_v13_v3_agent_run,
    require_v13_v4_schema_custody,
)
from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13.prompts import (
    V13_NORMALIZATION_PROMPT_VERSION_V6,
    V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6,
    V13_PROMPT_POLICY,
    v13_normalization_prompt_v6,
    v13_normalized_review_prompt_v6,
)
from scripts.validation.claim_events.finite_source_unit.normalization.contracts import (
    MaterialAxis,
    SourceUnitNormalizationOutput,
    SourceUnitNormalizedReviewOutput,
)
from scripts.validation.claim_events.finite_source_unit.normalization.execution import (
    IssuedExecutionContractBoundaryError,
    ThreeCallAgentRunEvidence,
    _execute_three_source_unit_agents,
    bind_issued_v13_executor,
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
from scripts.validation.claim_events.finite_source_unit.normalization.v13_contracts import (
    SourceUnitNormalizationOutputV13,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review import (
    bind_v13_context_dimension_review,
)
from scripts.validation.claim_events.finite_source_unit.normalization.v13_review_contracts import (
    SourceUnitNormalizedReviewOutputV13V6,
)
from scripts.validation.claim_events.finite_source_unit.service import (
    FiniteSourceUnitModelClient,
    bind_source_unit_extraction,
)
from scripts.validation.claim_events.finite_source_unit.source_units import (
    enumerate_source_units,
)

_SOURCE = "IL-4 did not affect FOXP3 expression in T cells."


def _attacker_normalization_prompt(**_: object) -> str:
    return "ATTACKER CONTROLLED NORMALIZATION PROMPT"


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


def _v13_normalization() -> SourceUnitNormalizationOutputV13:
    return SourceUnitNormalizationOutputV13.model_validate(
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


def _v13_v6_review(
    *, axis_decision: str = "PRESERVED"
) -> SourceUnitNormalizedReviewOutputV13V6:
    payload = _review(axis_decision=axis_decision).model_dump(mode="json")
    payload["context_dimension_reviews"] = []
    return SourceUnitNormalizedReviewOutputV13V6.model_validate(payload)


class _ThreeCallClient:
    def __init__(
        self,
        *,
        bad_mapping: bool = False,
        review_axis_decision: str = "PRESERVED",
    ) -> None:
        self.bad_mapping = bad_mapping
        self.review_axis_decision = review_axis_decision
        self.calls: list[type[object]] = []
        self.prompts: list[str] = []
        self.step_keys: list[str] = []

    async def step(self, **kwargs: object) -> object:
        schema = cast("type[object]", kwargs["output_schema"])
        self.calls.append(schema)
        self.prompts.append(cast("str", kwargs["prompt"]))
        self.step_keys.append(cast("str", kwargs["step_key"]))
        if schema is SourceUnitExtractionOutput:
            output: object = _extraction()
        elif schema in {
            SourceUnitNormalizationOutput,
            SourceUnitNormalizationOutputV12,
            SourceUnitNormalizationOutputV13,
        }:
            if schema is SourceUnitNormalizationOutputV12:
                output = _v12_normalization()
            elif schema is SourceUnitNormalizationOutputV13:
                output = _v13_normalization()
            else:
                output = _normalization(bad_mapping=self.bad_mapping)
        elif schema is SourceUnitNormalizedReviewOutputV13V6:
            output = _v13_v6_review(axis_decision=self.review_axis_decision)
        else:
            assert schema is SourceUnitNormalizedReviewOutput
            output = _review(axis_decision=self.review_axis_decision)
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
    assert result.local_review_passed is True
    assert result.scientifically_qualified is False
    assert qualifies_v13_v3_agent_run(result) is False
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


@pytest.mark.asyncio
async def test_v13_execution_binds_prompt_schema_and_reviewer_versions() -> None:
    unit = enumerate_source_units(case_id="v13-three-call", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    result = await execute_v13_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v13-three-call-test",
        unit=unit,
    )

    assert client.calls == [
        SourceUnitExtractionOutput,
        SourceUnitNormalizationOutputV13,
        SourceUnitNormalizedReviewOutput,
    ]
    assert result.error_type is None
    assert result.execution_contract_version == (
        "tg04.finite_source_unit.v13_execution.v2"
    )
    assert {record.execution_contract_version for record in result.records} == {
        "tg04.finite_source_unit.v13_execution.v2"
    }
    assert isinstance(result.normalized_extraction, SourceUnitNormalizationOutputV13)
    assert client.prompts[0].endswith(
        V13_EXECUTION_POLICY.extraction_prompt_policy.extraction_prompt(unit)
    )
    assert "structure_normalization.v5" in client.prompts[1]
    assert "normalized_review.v5" in client.prompts[2]
    contract = V13_EXECUTION_POLICY.as_json()
    assert contract == {
        "contract_version": "tg04.finite_source_unit.v13_execution.v2",
        "extraction_prompt_version": "tg04.finite_source_unit.extraction.v22",
        "verification_prompt_version": "tg04.finite_source_unit.verification.v20",
        "normalization_prompt_version": (
            "tg04.finite_source_unit.structure_normalization.v5"
        ),
        "normalization_output_schema": (
            "scripts.validation.claim_events.finite_source_unit.normalization."
            "v13_contracts.SourceUnitNormalizationOutputV13"
        ),
        "normalization_output_schema_sha256": (
            "43418016713a4b848069e1a82babd0ab0706a5502889d14209ec371512456e0f"
        ),
        "review_prompt_version": "tg04.finite_source_unit.normalized_review.v5",
    }


@pytest.mark.asyncio
async def test_v13_v3_execution_binds_context_eligibility_prompt_and_review() -> None:
    unit = enumerate_source_units(case_id="v13-v3-three-call", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    result = await execute_v13_v3_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v13-v3-three-call-test",
        unit=unit,
    )

    assert result.error_type is None
    assert result.execution_contract_version == (
        "tg04.finite_source_unit.v13_execution.v3"
    )
    assert "structure_normalization.v6" in client.prompts[1]
    assert "V13 CONTEXT-DIMENSION ELIGIBILITY" in client.prompts[1]
    assert "normalized_review.v6" in client.prompts[2]
    assert "V13 CONTEXT-DIMENSION FALSIFICATION" in client.prompts[2]
    assert client.calls[2] is SourceUnitNormalizedReviewOutputV13V6
    contract = V13_EXECUTION_POLICY_V3.as_json()
    assert contract["review_output_schema"] == (
        "scripts.validation.claim_events.finite_source_unit.normalization."
        "v13_review_contracts.SourceUnitNormalizedReviewOutputV13V6"
    )
    assert contract["review_binder"] == (
        "scripts.validation.claim_events.finite_source_unit.normalization."
        "v13_review.bind_v13_context_dimension_review"
    )
    assert contract["review_output_schema_sha256"] == (
        "393d5913526f4eaf0f280b9b15488972ec4464f96c3e52d441083efab4bf612f"
    )


@pytest.mark.asyncio
async def test_completed_agent_run_does_not_qualify_without_explicit_pass() -> None:
    unit = enumerate_source_units(case_id="v13-v3-abstain", source_text=_SOURCE)[0]
    client = _ThreeCallClient(review_axis_decision="ABSTAIN")

    result = await execute_v13_v3_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", client),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v13-v3-abstain-test",
        unit=unit,
    )

    assert result.error_type is None
    assert result.failed_stage is None
    assert result.review_result is not None
    assert result.review_result.local_review_disposition.value == "ABSTAIN"
    assert result.scientifically_qualified is False


@pytest.mark.asyncio
async def test_shared_executor_rejects_v6_tuple_relabelled_as_v13_v2() -> None:
    unit = enumerate_source_units(case_id="v13-custody-attack", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    with pytest.raises(
        IssuedExecutionContractBoundaryError,
        match="issued V13 contracts require their dedicated executor",
    ):
        await execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v13-custody-attack",
            unit=unit,
            extraction_prompt_policy=V13_PROMPT_POLICY,
            normalization_prompt_builder=v13_normalization_prompt_v6,
            normalization_prompt_version=V13_NORMALIZATION_PROMPT_VERSION_V6,
            normalization_output_schema=SourceUnitNormalizationOutputV13,
            review_prompt_builder=v13_normalized_review_prompt_v6,
            review_prompt_version=V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6,
            review_output_schema=SourceUnitNormalizedReviewOutputV13V6,
            review_binder=bind_v13_context_dimension_review,
            execution_contract_version="tg04.finite_source_unit.v13_execution.v2",
        )

    assert client.calls == []


@pytest.mark.asyncio
async def test_shared_executor_rejects_exact_v13_tuple_under_attacker_label() -> None:
    unit = enumerate_source_units(case_id="v13-label-attack", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    with pytest.raises(
        IssuedExecutionContractBoundaryError,
        match="exact dedicated executor",
    ):
        await execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v13-label-attack",
            unit=unit,
            extraction_prompt_policy=V13_PROMPT_POLICY,
            normalization_prompt_builder=v13_normalization_prompt_v6,
            normalization_prompt_version=V13_NORMALIZATION_PROMPT_VERSION_V6,
            normalization_output_schema=SourceUnitNormalizationOutputV13,
            review_prompt_builder=v13_normalized_review_prompt_v6,
            review_prompt_version=V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6,
            review_output_schema=SourceUnitNormalizedReviewOutputV13V6,
            review_binder=bind_v13_context_dimension_review,
            execution_contract_version="attacker.relabelled.v13-v3",
        )

    assert client.calls == []


@pytest.mark.asyncio
async def test_internal_executor_rejects_wrong_tuple_under_issued_v13_identity() -> (
    None
):
    unit = enumerate_source_units(case_id="v13-tuple-attack", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    with pytest.raises(
        IssuedExecutionContractBoundaryError,
        match="sealed executor",
    ):
        await _execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v13-tuple-attack",
            unit=unit,
            extraction_prompt_policy=V11_EXTRACTION_PROMPT_POLICY,
            normalization_prompt_builder=v11_normalization_prompt,
            normalization_prompt_version=V11_NORMALIZATION_PROMPT_VERSION,
            review_prompt_builder=v11_normalized_review_prompt,
            review_prompt_version=V11_NORMALIZED_REVIEW_PROMPT_VERSION,
            execution_contract_version=V13_EXECUTION_POLICY_V3.contract_version,
        )

    assert client.calls == []


@pytest.mark.asyncio
async def test_issued_v13_identity_rejects_prepared_prompt_injection() -> None:
    unit = enumerate_source_units(case_id="v13-prompt-attack", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    with pytest.raises(
        IssuedExecutionContractBoundaryError,
        match="sealed executor and prompt",
    ):
        await _execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v13-prompt-attack",
            unit=unit,
            extraction_prompt_policy=V13_PROMPT_POLICY,
            prepared_extraction_prompt="ATTACKER CONTROLLED EXTRACTION PROMPT",
            normalization_prompt_builder=v13_normalization_prompt_v6,
            normalization_prompt_version=V13_NORMALIZATION_PROMPT_VERSION_V6,
            normalization_output_schema=SourceUnitNormalizationOutputV13,
            review_prompt_builder=v13_normalized_review_prompt_v6,
            review_prompt_version=V13_NORMALIZED_REVIEW_PROMPT_VERSION_V6,
            review_output_schema=SourceUnitNormalizedReviewOutputV13V6,
            review_binder=bind_v13_context_dimension_review,
            execution_contract_version=V13_EXECUTION_POLICY_V3.contract_version,
            issued_manifest_sha256=(
                "983666f2d5a0a9813b26714e86ea5e981ea5c43ae5709c96753f8780a769da66"
            ),
            issued_authority=object(),
        )

    assert client.calls == []


def test_internal_executor_has_no_boolean_issued_ownership_escape_hatch() -> None:
    parameters = inspect.signature(_execute_three_source_unit_agents).parameters

    assert "issued_contract_owner" not in parameters
    assert "issued_execution_policy" not in parameters


def test_modified_policy_cannot_register_for_official_v13_lineage() -> None:
    attacker_policy = replace(
        V13_EXECUTION_POLICY_V3,
        normalization_prompt_builder=_attacker_normalization_prompt,
    )

    with pytest.raises(
        IssuedExecutionContractBoundaryError,
        match="frozen component manifest",
    ):
        bind_issued_v13_executor(attacker_policy)


@pytest.mark.asyncio
async def test_rebinding_public_policy_does_not_change_captured_v13_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13 import (
        execution as v13_execution_module,
    )
    from scripts.validation.claim_events.finite_source_unit.nested_holdout_trial.v13 import (
        prompts as v13_prompts_module,
    )

    attacker_policy = replace(
        V13_EXECUTION_POLICY_V3,
        normalization_prompt_builder=_attacker_normalization_prompt,
    )
    monkeypatch.setattr(
        v13_execution_module,
        "V13_EXECUTION_POLICY_V3",
        attacker_policy,
    )
    monkeypatch.setattr(
        v13_prompts_module,
        "_CORRECTION_POLICY_V6",
        "ATTACKER CONTROLLED TRANSITIVE POLICY",
    )
    prompt_defaults = v13_prompts_module.v13_normalization_prompt_v6.__kwdefaults__
    assert prompt_defaults is not None
    monkeypatch.setitem(
        prompt_defaults,
        "_policy",
        "ATTACKER CONTROLLED MUTABLE DEFAULT",
    )
    original_version = V13_EXECUTION_POLICY_V3.normalization_prompt_version
    original_binder = V13_EXECUTION_POLICY_V3.review_binder
    original_contract = V13_EXECUTION_POLICY_V3.contract_version
    object.__setattr__(
        V13_EXECUTION_POLICY_V3,
        "normalization_prompt_version",
        "attacker.mutable.version",
    )
    object.__setattr__(
        V13_EXECUTION_POLICY_V3,
        "review_binder",
        bind_source_unit_normalized_review,
    )
    object.__setattr__(
        V13_EXECUTION_POLICY_V3,
        "contract_version",
        "attacker.mutable.contract",
    )
    unit = enumerate_source_units(case_id="v13-policy-rebind", source_text=_SOURCE)[0]
    client = _ThreeCallClient()

    try:
        result = await execute_v13_v3_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="v13-policy-rebind-test",
            unit=unit,
        )
    finally:
        object.__setattr__(
            V13_EXECUTION_POLICY_V3,
            "normalization_prompt_version",
            original_version,
        )
        object.__setattr__(
            V13_EXECUTION_POLICY_V3,
            "review_binder",
            original_binder,
        )
        object.__setattr__(
            V13_EXECUTION_POLICY_V3,
            "contract_version",
            original_contract,
        )

    assert result.execution_contract_version == (
        "tg04.finite_source_unit.v13_execution.v3"
    )
    assert has_locally_consistent_v13_v3_execution(result) is True
    assert "ATTACKER CONTROLLED" not in client.prompts[1]
    assert "attacker.mutable.version" not in result.records[1].step_key


@pytest.mark.asyncio
async def test_review_result_substitution_cannot_convert_abstain_to_pass() -> None:
    unit = enumerate_source_units(case_id="v13-review-swap", source_text=_SOURCE)[0]
    passing = await execute_v13_v3_source_unit_agents(
        client=cast("FiniteSourceUnitModelClient", _ThreeCallClient()),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v13-review-swap-pass",
        unit=unit,
    )
    abstaining = await execute_v13_v3_source_unit_agents(
        client=cast(
            "FiniteSourceUnitModelClient",
            _ThreeCallClient(review_axis_decision="ABSTAIN"),
        ),
        tenant=object(),
        model_id="openai:gpt-5.6-luna",
        execution_namespace="v13-review-swap-abstain",
        unit=unit,
    )

    assert passing.review_result is not None
    assert has_locally_consistent_v13_v3_execution(passing) is True
    assert passing.local_review_passed is True
    assert passing.scientifically_qualified is False
    assert qualifies_v13_v3_agent_run(passing) is False
    assert abstaining.scientifically_qualified is False
    assert qualifies_v13_v3_agent_run(abstaining) is False
    with pytest.raises(
        ValueError,
        match="parsed output and validated result disagree",
    ):
        replace(abstaining, review_result=passing.review_result)


@pytest.mark.asyncio
async def test_execution_contract_version_changes_every_stage_identity() -> None:
    unit = enumerate_source_units(
        case_id="contract-version-custody", source_text=_SOURCE
    )[0]
    first_client = _ThreeCallClient()
    second_client = _ThreeCallClient()

    async def execute(
        client: _ThreeCallClient,
        contract_version: str,
    ) -> ThreeCallAgentRunEvidence:
        return await execute_three_source_unit_agents(
            client=cast("FiniteSourceUnitModelClient", client),
            tenant=object(),
            model_id="openai:gpt-5.6-luna",
            execution_namespace="contract-version-custody-test",
            unit=unit,
            extraction_prompt_policy=V11_EXTRACTION_PROMPT_POLICY,
            normalization_prompt_builder=v11_normalization_prompt,
            normalization_prompt_version=V11_NORMALIZATION_PROMPT_VERSION,
            review_prompt_builder=v11_normalized_review_prompt,
            review_prompt_version=V11_NORMALIZED_REVIEW_PROMPT_VERSION,
            execution_contract_version=contract_version,
        )

    first = await execute(first_client, "test.contract.v1")
    second = await execute(second_client, "test.contract.v2")

    assert len(first_client.step_keys) == len(second_client.step_keys) == 3
    assert all(
        first_key != second_key
        for first_key, second_key in zip(
            first_client.step_keys,
            second_client.step_keys,
            strict=True,
        )
    )
    assert first_client.step_keys == [record.step_key for record in first.records]
    assert second_client.step_keys == [record.step_key for record in second.records]
    assert first.execution_contract_version == "test.contract.v1"
    assert second.execution_contract_version == "test.contract.v2"
    assert {record.execution_contract_version for record in first.records} == {
        "test.contract.v1"
    }
    assert {record.execution_contract_version for record in second.records} == {
        "test.contract.v2"
    }


def test_v13_v4_schema_custody_fails_closed_when_issued_schema_is_unavailable() -> None:
    with pytest.raises(V13HistoricalSchemaCustodyError, match="cannot be replayed"):
        require_v13_v4_schema_custody()


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
        execution_contract_version="test.contract.semantic-failure.v1",
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
    assert result.execution_contract_version == "test.contract.semantic-failure.v1"
    assert {record.execution_contract_version for record in result.records} == {
        "test.contract.semantic-failure.v1"
    }


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
