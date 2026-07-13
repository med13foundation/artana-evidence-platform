"""Tests for fail-closed agent output schema governance."""

from __future__ import annotations

from typing import Literal

import pytest
from artana_evidence_api.runtime.agent_output_debt import (
    validate_agent_output_debt_coverage,
)
from artana_evidence_api.runtime.agent_output_manifest import (
    validate_registered_agent_output_schema,
)
from artana_evidence_api.runtime.agent_output_report import (
    build_agent_output_registry_report,
)
from artana_evidence_api.runtime.agent_output_schema import (
    AgentOutputSchemaPolicy,
    AgentOutputSchemaRegistrationError,
    AgentOutputSchemaRegistry,
    CategoryFieldPolicy,
    CategoryValuePolicy,
    NumericFieldPolicy,
    NumericOrigin,
    SourceMeasurementNumber,
    agent_output_schema_shape_hash,
)
from pydantic import BaseModel


class _RegisteredDecision(BaseModel):
    decision: Literal["select", "reject"]
    record_index: int


class _NumericInjection(BaseModel):
    decision: Literal["select", "reject"]
    record_index: int
    confidence: float


class _SourceMeasurementResult(BaseModel):
    measurement: SourceMeasurementNumber


class _GenericNumericMetadata(BaseModel):
    metadata: dict[str, str | float]


class _UntypedMetadata(BaseModel):
    metadata: dict[str, object]


def _decision_category() -> CategoryFieldPolicy:
    return CategoryFieldPolicy(
        path="$.decision",
        values=(
            CategoryValuePolicy(
                value="select",
                definition="The cited record satisfies every required criterion.",
                positive_example="A cited trial directly reports the requested cohort.",
                counterexample="The population is absent from the cited record.",
            ),
            CategoryValuePolicy(
                value="reject",
                definition="A cited record contradicts a required criterion.",
                positive_example="The cited record is a review when a trial is required.",
                counterexample="All required criteria are directly supported.",
            ),
        ),
        evidence_requirement="A literal source span must support the decision.",
        invalid_behavior="Missing or conflicting evidence rejects the model output.",
    )


def _registry() -> AgentOutputSchemaRegistry:
    return AgentOutputSchemaRegistry(
        (
            AgentOutputSchemaPolicy(
                schema_id="test.decision.v1",
                schema_names=("_RegisteredDecision",),
                shape_hash=agent_output_schema_shape_hash(_RegisteredDecision),
                producer_paths=("tests/registered_decision.py",),
                prompt_identifiers=("test.decision.prompt.v1",),
                numeric_fields=(
                    NumericFieldPolicy(
                        path="$.record_index",
                        debt_id="TEST-LOCATOR-001",
                    ),
                ),
                categorical_fields=(_decision_category(),),
            ),
        ),
    )


def test_registered_schema_requires_complete_numeric_and_category_coverage() -> None:
    policy = _registry().validate(
        schema_id="test.decision.v1",
        output_schema=_RegisteredDecision,
    )

    assert policy.schema_id == "test.decision.v1"


def test_unknown_schema_id_fails_closed() -> None:
    with pytest.raises(
        AgentOutputSchemaRegistrationError,
        match="Unregistered agent output schema ID",
    ):
        _registry().validate(
            schema_id="test.unknown.v1",
            output_schema=_RegisteredDecision,
        )


def test_numeric_self_score_injection_fails_registry_validation() -> None:
    registry = AgentOutputSchemaRegistry(
        (
            AgentOutputSchemaPolicy(
                schema_id="test.decision.v1",
                schema_names=("_NumericInjection",),
                shape_hash=agent_output_schema_shape_hash(_NumericInjection),
                producer_paths=("tests/numeric_injection.py",),
                prompt_identifiers=("test.numeric_injection.prompt.v1",),
                numeric_fields=(
                    NumericFieldPolicy(
                        path="$.record_index",
                        debt_id="TEST-LOCATOR-001",
                    ),
                ),
                categorical_fields=(_decision_category(),),
            ),
        ),
    )

    with pytest.raises(
        AgentOutputSchemaRegistrationError,
        match=r"unregistered=\['\$\.confidence'\]",
    ):
        registry.validate(
            schema_id="test.decision.v1",
            output_schema=_NumericInjection,
        )


def test_same_named_schema_cannot_change_unscored_fields() -> None:
    class _ChangedShape(BaseModel):
        decision: Literal["select", "reject"]
        record_index: int
        unsupported_summary: str

    _ChangedShape.__name__ = "_RegisteredDecision"

    with pytest.raises(AgentOutputSchemaRegistrationError, match="shape changed"):
        _registry().validate(
            schema_id="test.decision.v1",
            output_schema=_ChangedShape,
        )


def test_bare_numeric_field_cannot_claim_an_allowed_origin() -> None:
    registry = AgentOutputSchemaRegistry(
        (
            AgentOutputSchemaPolicy(
                schema_id="test.decision.v1",
                schema_names=("_RegisteredDecision",),
                shape_hash=agent_output_schema_shape_hash(_RegisteredDecision),
                producer_paths=("tests/registered_decision.py",),
                prompt_identifiers=("test.decision.prompt.v1",),
                numeric_fields=(
                    NumericFieldPolicy(
                        path="$.record_index",
                        origin=NumericOrigin.DETERMINISTIC_POLICY,
                    ),
                ),
                categorical_fields=(_decision_category(),),
            ),
        ),
    )

    with pytest.raises(AgentOutputSchemaRegistrationError, match="typed provenance"):
        registry.validate(
            schema_id="test.decision.v1",
            output_schema=_RegisteredDecision,
        )


def test_typed_source_measurement_envelope_satisfies_origin_policy() -> None:
    registry = AgentOutputSchemaRegistry(
        (
            AgentOutputSchemaPolicy(
                schema_id="test.measurement.v1",
                schema_names=("_SourceMeasurementResult",),
                shape_hash=agent_output_schema_shape_hash(_SourceMeasurementResult),
                producer_paths=("tests/source_measurement.py",),
                prompt_identifiers=("test.source_measurement.prompt.v1",),
                numeric_fields=(
                    NumericFieldPolicy(
                        path="$.measurement.value",
                        origin=NumericOrigin.SOURCE_MEASUREMENT,
                    ),
                ),
            ),
        ),
    )

    policy = registry.validate(
        schema_id="test.measurement.v1",
        output_schema=_SourceMeasurementResult,
    )

    assert policy.numeric_fields[0].origin is NumericOrigin.SOURCE_MEASUREMENT


def test_source_measurement_envelope_requires_complete_provenance() -> None:
    with pytest.raises(ValueError, match="literal_span"):
        SourceMeasurementNumber.model_validate(
            {
                "value": "1.25",
                "source_locator": "paper:doi:10.1/example",
                "field_name": "effect_size",
                "unit": "ratio",
                "extraction_method": "literal_copy",
                "source_hash": "sha256:abc",
            },
        )


def test_generic_dictionary_numeric_value_is_discovered() -> None:
    registry = AgentOutputSchemaRegistry(
        (
            AgentOutputSchemaPolicy(
                schema_id="test.metadata.v1",
                schema_names=("_GenericNumericMetadata",),
                shape_hash=agent_output_schema_shape_hash(_GenericNumericMetadata),
                producer_paths=("tests/generic_numeric_metadata.py",),
                prompt_identifiers=("test.generic_numeric_metadata.prompt.v1",),
            ),
        ),
    )

    with pytest.raises(
        AgentOutputSchemaRegistrationError,
        match=r"unregistered=\['\$\.metadata\.\*'\]",
    ):
        registry.validate(
            schema_id="test.metadata.v1",
            output_schema=_GenericNumericMetadata,
        )


def test_untyped_dictionary_is_treated_as_potential_numeric_input() -> None:
    registry = AgentOutputSchemaRegistry(
        (
            AgentOutputSchemaPolicy(
                schema_id="test.untyped_metadata.v1",
                schema_names=("_UntypedMetadata",),
                shape_hash=agent_output_schema_shape_hash(_UntypedMetadata),
                producer_paths=("tests/untyped_metadata.py",),
                prompt_identifiers=("test.untyped_metadata.prompt.v1",),
            ),
        ),
    )

    with pytest.raises(
        AgentOutputSchemaRegistrationError,
        match=r"unregistered=\['\$\.metadata\.\*'\]",
    ):
        registry.validate(
            schema_id="test.untyped_metadata.v1",
            output_schema=_UntypedMetadata,
        )


def test_numeric_policy_requires_exactly_one_origin_or_debt_id() -> None:
    with pytest.raises(AgentOutputSchemaRegistrationError, match="exactly one"):
        NumericFieldPolicy(path="$.confidence")
    with pytest.raises(AgentOutputSchemaRegistrationError, match="exactly one"):
        NumericFieldPolicy(
            path="$.confidence",
            origin=NumericOrigin.COMPUTED_METRIC,
            debt_id="NUM-001",
        )


def test_unanchored_category_value_is_rejected() -> None:
    with pytest.raises(AgentOutputSchemaRegistrationError, match="counterexample"):
        CategoryValuePolicy(
            value="strong",
            definition="Strong support.",
            positive_example="Some support exists.",
            counterexample="",
        )


def test_category_vocabulary_drift_fails_registry_validation() -> None:
    class _ChangedDecision(BaseModel):
        decision: Literal["select", "reject", "maybe"]
        record_index: int

    registry = AgentOutputSchemaRegistry(
        (
            AgentOutputSchemaPolicy(
                schema_id="test.decision.v1",
                schema_names=("_ChangedDecision",),
                shape_hash=agent_output_schema_shape_hash(_ChangedDecision),
                producer_paths=("tests/changed_decision.py",),
                prompt_identifiers=("test.changed_decision.prompt.v1",),
                numeric_fields=(
                    NumericFieldPolicy(
                        path="$.record_index",
                        debt_id="TEST-LOCATOR-001",
                    ),
                ),
                categorical_fields=(_decision_category(),),
            ),
        ),
    )

    with pytest.raises(AgentOutputSchemaRegistrationError, match="values changed"):
        registry.validate(
            schema_id="test.decision.v1",
            output_schema=_ChangedDecision,
        )


def test_production_manifest_covers_current_model_output_schemas() -> None:
    from artana_evidence_api.agent_contracts import OnboardingAssistantModelOutput
    from artana_evidence_api.document_extraction_prompting import (
        build_llm_guarded_extraction_output_schema,
        build_proposal_review_output_schema,
    )
    from artana_evidence_api.evidence_selection.semantic.contracts import (
        EvidenceSelectionSemanticBatchContract,
    )
    from artana_evidence_api.evidence_selection_source_planning import (
        ModelEvidenceSelectionSourcePlanContract,
    )
    from artana_evidence_api.full_ai_orchestrator.shadow_planner.models import (
        ShadowPlannerRecommendationOutput,
    )
    from artana_evidence_api.graph_connection_runtime import (
        _GraphConnectionExecutionContract,
    )
    from artana_evidence_api.graph_search_runtime import _GraphSearchExecutionContract
    from artana_evidence_api.marrvel_enrichment import _MarrvelGeneInferenceResult
    from artana_evidence_api.pubmed_relevance import PubMedRelevanceModelOutput
    from artana_evidence_api.relation_type_resolver import (
        EntityDecision,
        RelationTypeDecision,
    )
    from artana_evidence_api.research_init_brief import LLMBriefOutput
    from artana_evidence_api.runtime.model_health import (
        build_model_health_probe_output_schema,
    )
    from artana_evidence_api.variant_extraction_contracts import LLMExtractionContract

    schemas = {
        "document_extraction.proposal_review.v1": build_proposal_review_output_schema(),
        "document_extraction.relation.v2": (
            build_llm_guarded_extraction_output_schema(max_relations=3)
        ),
        "entity_resolution.agent.v1": EntityDecision,
        "evidence_selection.semantic.v2": EvidenceSelectionSemanticBatchContract,
        "evidence_selection.source_plan.v1": ModelEvidenceSelectionSourcePlanContract,
        "full_ai.shadow_planner.v1": ShadowPlannerRecommendationOutput,
        "graph_connection.agent.v1": _GraphConnectionExecutionContract,
        "graph_search.agent.v1": _GraphSearchExecutionContract,
        "marrvel.gene_inference.v1": _MarrvelGeneInferenceResult,
        "model_health.probe.v1": build_model_health_probe_output_schema(),
        "pubmed.relevance.v1": PubMedRelevanceModelOutput,
        "relation_type_resolution.agent.v1": RelationTypeDecision,
        "research.brief.v1": LLMBriefOutput,
        "research_onboarding.agent.v1": OnboardingAssistantModelOutput,
        "variant_extraction.agent.v1": LLMExtractionContract,
    }

    for schema_id, output_schema in schemas.items():
        validate_registered_agent_output_schema(
            schema_id=schema_id,
            output_schema=output_schema,
        )


def test_debt_manifest_exactly_covers_registered_legacy_fields() -> None:
    manifest = validate_agent_output_debt_coverage()

    debt_ids = [item.debt_id for item in manifest]
    assert debt_ids == []
    assert all(item.quarantined for item in manifest)


def test_registry_report_exposes_merge_gate_counts() -> None:
    report = build_agent_output_registry_report()

    assert report["registered_schema_count"] == 15
    assert report["registered_numeric_field_count"] == 1
    assert report["origin_governed_numeric_field_count"] == 1
    assert report["debt_numeric_field_count"] == 0
    assert report["active_debt_count"] == 0
    assert report["unquarantined_debt_count"] == 0
