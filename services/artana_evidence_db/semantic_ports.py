"""Service-local semantic governance port protocols."""

from __future__ import annotations

from typing import Literal, Protocol

from artana_evidence_db.common_types import JSONObject, ResearchSpaceSettings
from artana_evidence_db.kernel_domain_models import (
    ConceptAlias,
    ConceptDecision,
    ConceptDecisionStatus,
    ConceptDecisionType,
    ConceptMember,
    ConceptPolicy,
    ConceptPolicyMode,
    ConceptSet,
    DictionaryChangelog,
    DictionaryDomainContext,
    DictionaryEntityType,
    DictionaryRelationSynonym,
    DictionaryRelationType,
    DictionarySearchResult,
    EntityResolutionPolicy,
    RelationConstraint,
    TransformRegistry,
    TransformVerificationResult,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
)


class ConceptPort(Protocol):
    """Graph-service concept governance interface."""

    def create_concept_set(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        name: str,
        slug: str,
        domain_context: str,
        description: str | None = None,
        created_by: str,
        source_ref: str | None = None,
    ) -> ConceptSet: ...

    def list_concept_sets(
        self,
        *,
        research_space_id: str,
        include_inactive: bool = False,
    ) -> list[ConceptSet]: ...

    def create_concept_member(  # noqa: PLR0913
        self,
        *,
        concept_set_id: str,
        research_space_id: str,
        domain_context: str,
        canonical_label: str,
        normalized_label: str,
        sense_key: str = "",
        dictionary_dimension: str | None = None,
        dictionary_entry_id: str | None = None,
        is_provisional: bool = False,
        metadata_payload: JSONObject | None = None,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ConceptMember: ...

    def list_concept_members(
        self,
        *,
        research_space_id: str,
        concept_set_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptMember]: ...

    def create_concept_alias(  # noqa: PLR0913
        self,
        *,
        concept_member_id: str,
        research_space_id: str,
        domain_context: str,
        alias_label: str,
        alias_normalized: str,
        source: str | None = None,
        created_by: str,
        source_ref: str | None = None,
    ) -> ConceptAlias: ...

    def list_concept_aliases(
        self,
        *,
        research_space_id: str,
        concept_member_id: str | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptAlias]: ...

    def resolve_member_by_alias(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        alias_normalized: str,
        include_inactive: bool = False,
    ) -> ConceptMember | None: ...

    def get_active_policy(
        self,
        *,
        research_space_id: str,
    ) -> ConceptPolicy | None: ...

    def upsert_active_policy(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        mode: ConceptPolicyMode,
        created_by: str,
        minimum_edge_confidence: float = 0.6,
        minimum_distinct_documents: int = 1,
        allow_generic_relations: bool = True,
        max_edges_per_document: int | None = None,
        policy_payload: JSONObject | None = None,
        source_ref: str | None = None,
    ) -> ConceptPolicy: ...

    def propose_decision(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        decision_type: ConceptDecisionType,
        proposed_by: str,
        decision_payload: JSONObject | None = None,
        evidence_payload: JSONObject | None = None,
        confidence: float | None = None,
        rationale: str | None = None,
        concept_set_id: str | None = None,
        concept_member_id: str | None = None,
        concept_link_id: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ConceptDecision: ...

    def set_decision_status(
        self,
        decision_id: str,
        *,
        decision_status: ConceptDecisionStatus,
        decided_by: str,
    ) -> ConceptDecision: ...

    def list_decisions(
        self,
        *,
        research_space_id: str,
        decision_status: ConceptDecisionStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptDecision]: ...


class DictionaryPort(Protocol):
    """Graph-service dictionary governance interface."""

    def list_domain_contexts(
        self,
        *,
        include_inactive: bool = False,
    ) -> list[DictionaryDomainContext]: ...

    def create_domain_context(
        self,
        *,
        domain_context_id: str,
        display_name: str,
        description: str | None = None,
        created_by: str | None = None,
        source_ref: str | None = None,
    ) -> DictionaryDomainContext: ...

    def get_variable(self, variable_id: str) -> VariableDefinition | None: ...

    def get_transform(
        self,
        input_unit: str,
        output_unit: str,
        *,
        include_inactive: bool = False,
        require_production: bool = False,
    ) -> TransformRegistry | None: ...

    def list_variables(
        self,
        *,
        domain_context: str | None = None,
        data_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[VariableDefinition]: ...

    def create_variable(  # noqa: PLR0913
        self,
        *,
        variable_id: str,
        canonical_name: str,
        display_name: str,
        data_type: str,
        domain_context: str = "general",
        sensitivity: str = "INTERNAL",
        preferred_unit: str | None = None,
        constraints: JSONObject | None = None,
        description: str | None = None,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> VariableDefinition: ...

    def set_review_status(
        self,
        variable_id: str,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> VariableDefinition: ...

    def revoke_variable(
        self,
        variable_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> VariableDefinition: ...

    def create_value_set(  # noqa: PLR0913
        self,
        *,
        value_set_id: str,
        variable_id: str,
        name: str,
        description: str | None = None,
        external_ref: str | None = None,
        is_extensible: bool = False,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ValueSet: ...

    def get_value_set(self, value_set_id: str) -> ValueSet | None: ...

    def list_value_sets(
        self,
        *,
        variable_id: str | None = None,
    ) -> list[ValueSet]: ...

    def create_value_set_item(  # noqa: PLR0913
        self,
        *,
        value_set_id: str,
        code: str,
        display_label: str,
        synonyms: list[str] | None = None,
        external_ref: str | None = None,
        sort_order: int = 0,
        is_active: bool = True,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> ValueSetItem: ...

    def list_value_set_items(
        self,
        *,
        value_set_id: str,
        include_inactive: bool = False,
    ) -> list[ValueSetItem]: ...

    def set_value_set_item_active(
        self,
        value_set_item_id: int,
        *,
        is_active: bool,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> ValueSetItem: ...

    def dictionary_search_by_domain(
        self,
        *,
        domain_context: str,
        limit: int = 50,
        include_inactive: bool = False,
    ) -> list[DictionarySearchResult]: ...

    def is_relation_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool: ...

    def requires_evidence(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool: ...

    def create_relation_constraint(  # noqa: PLR0913
        self,
        *,
        source_type: str,
        relation_type: str,
        target_type: str,
        is_allowed: bool = True,
        requires_evidence: bool = True,
        profile: str = "ALLOWED",
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> RelationConstraint: ...

    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[RelationConstraint]: ...

    def list_resolution_policies(
        self,
        *,
        include_inactive: bool = False,
    ) -> list[EntityResolutionPolicy]: ...

    def create_entity_type(  # noqa: PLR0913
        self,
        *,
        entity_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        external_ontology_ref: str | None = None,
        expected_properties: JSONObject | None = None,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> DictionaryEntityType: ...

    def list_entity_types(
        self,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryEntityType]: ...

    def get_entity_type(
        self,
        entity_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryEntityType | None: ...

    def set_entity_type_review_status(
        self,
        entity_type_id: str,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryEntityType: ...

    def revoke_entity_type(
        self,
        entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryEntityType: ...

    def create_relation_type(  # noqa: PLR0913
        self,
        *,
        relation_type: str,
        display_name: str,
        description: str,
        domain_context: str,
        is_directional: bool = True,
        inverse_label: str | None = None,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> DictionaryRelationType: ...

    def list_relation_types(
        self,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryRelationType]: ...

    def get_relation_type(
        self,
        relation_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryRelationType | None: ...

    def set_relation_type_review_status(
        self,
        relation_type_id: str,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationType: ...

    def revoke_relation_type(
        self,
        relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryRelationType: ...

    def resolve_relation_synonym(
        self,
        synonym: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryRelationType | None: ...

    def create_relation_synonym(  # noqa: PLR0913
        self,
        *,
        relation_type_id: str,
        synonym: str,
        source: str | None = None,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> DictionaryRelationSynonym: ...

    def list_relation_synonyms(
        self,
        *,
        relation_type_id: str | None = None,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryRelationSynonym]: ...

    def set_relation_synonym_review_status(
        self,
        synonym_id: int,
        *,
        review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"],
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationSynonym: ...

    def revoke_relation_synonym(
        self,
        synonym_id: int,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryRelationSynonym: ...

    def list_changelog_entries(
        self,
        *,
        table_name: str | None = None,
        record_id: str | None = None,
        limit: int = 100,
    ) -> list[DictionaryChangelog]: ...

    def list_transforms(
        self,
        *,
        status: str = "ACTIVE",
        include_inactive: bool = False,
        production_only: bool = False,
    ) -> list[TransformRegistry]: ...

    def verify_transform(
        self,
        transform_id: str,
    ) -> TransformVerificationResult: ...

    def promote_transform(
        self,
        transform_id: str,
        *,
        reviewed_by: str,
    ) -> TransformRegistry: ...

    def merge_variable_definition(
        self,
        source_variable_id: str,
        target_variable_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> VariableDefinition: ...

    def merge_entity_type(
        self,
        source_entity_type_id: str,
        target_entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryEntityType: ...

    def merge_relation_type(
        self,
        source_relation_type_id: str,
        target_relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryRelationType: ...


__all__ = ["ConceptPort", "DictionaryPort"]
