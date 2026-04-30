# mypy: disable-error-code="attr-defined,no-any-return"
"""Relation and entity governance helpers for dictionary management."""

from __future__ import annotations

from typing import Literal

from artana_evidence_db.common_types import JSONObject, ResearchSpaceSettings
from artana_evidence_db.dictionary_support import DomainContextResolver
from artana_evidence_db.kernel_domain_models import (
    DictionaryEntityType,
    DictionaryRelationSynonym,
    DictionaryRelationType,
    EntityResolutionPolicy,
    RelationConstraint,
)

ReviewStatus = Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"]

_DEFAULT_RESOLUTION_POLICY_BY_ENTITY_TYPE: dict[
    str,
    tuple[str, tuple[str, ...], float],
] = {
    "GENE": ("LOOKUP", ("hgnc_id",), 1.0),
    "VARIANT": ("STRICT_MATCH", ("hgvs_notation", "gene_symbol"), 1.0),
    "PHENOTYPE": ("LOOKUP", ("hpo_id",), 1.0),
    "PUBLICATION": ("FUZZY", ("doi", "title"), 0.95),
    "DRUG": ("LOOKUP", ("drugbank_id",), 1.0),
    "PATHWAY": ("LOOKUP", ("reactome_id",), 1.0),
    "MECHANISM": ("NONE", (), 1.0),
    "PATIENT": ("STRICT_MATCH", ("mrn", "issuer"), 1.0),
    "PROTEIN": ("LOOKUP", ("uniprot_id",), 1.0),
    "COMPLEX": ("STRICT_MATCH", ("name",), 1.0),
    "MICROBIOTA_TAXON": ("LOOKUP", ("taxon_id",), 1.0),
}


class DictionaryManagementRelationMixin:
    """Provide relation/entity governance service operations."""

    def is_relation_allowed(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check whether a triple is permitted by the constraint schema."""
        return self._dictionary.is_triple_allowed(
            source_type,
            relation_type,
            target_type,
        )

    def requires_evidence(
        self,
        source_type: str,
        relation_type: str,
        target_type: str,
    ) -> bool:
        """Check whether a triple requires evidence."""
        return self._dictionary.requires_evidence(
            source_type,
            relation_type,
            target_type,
        )

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
    ) -> RelationConstraint:
        """Create a relation constraint with provenance metadata."""
        created_by_normalized = self._normalize_created_by(created_by)

        normalized_source = source_type.strip().upper()
        normalized_relation = relation_type.strip().upper()
        normalized_target = target_type.strip().upper()
        if not normalized_source:
            msg = "source_type is required"
            raise ValueError(msg)
        if not normalized_relation:
            msg = "relation_type is required"
            raise ValueError(msg)
        if not normalized_target:
            msg = "target_type is required"
            raise ValueError(msg)
        normalized_profile = profile.strip().upper()
        if normalized_profile not in {
            "EXPECTED",
            "ALLOWED",
            "REVIEW_ONLY",
            "FORBIDDEN",
        }:
            msg = (
                "profile must be one of EXPECTED, ALLOWED, REVIEW_ONLY, or FORBIDDEN"
            )
            raise ValueError(msg)

        if self._dictionary.get_entity_type(normalized_source) is None:
            msg = f"Entity type '{normalized_source}' not found"
            raise ValueError(msg)
        if self._dictionary.get_relation_type(normalized_relation) is None:
            msg = f"Relation type '{normalized_relation}' not found"
            raise ValueError(msg)
        if self._dictionary.get_entity_type(normalized_target) is None:
            msg = f"Entity type '{normalized_target}' not found"
            raise ValueError(msg)

        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )
        return self._dictionary.create_relation_constraint(
            source_type=normalized_source,
            relation_type=normalized_relation,
            target_type=normalized_target,
            is_allowed=is_allowed,
            requires_evidence=requires_evidence,
            profile=normalized_profile,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

    def get_constraints(
        self,
        *,
        source_type: str | None = None,
        relation_type: str | None = None,
        include_inactive: bool = False,
    ) -> list[RelationConstraint]:
        """List constraints, optionally filtered."""
        return self._dictionary.get_constraints(
            source_type=source_type,
            relation_type=relation_type,
            include_inactive=include_inactive,
        )

    # ── Resolution policies ───────────────────────────────────────────

    def get_resolution_policy(
        self,
        entity_type: str,
        *,
        include_inactive: bool = False,
    ) -> EntityResolutionPolicy | None:
        """Get the dedup strategy for an entity type."""
        return self._dictionary.get_resolution_policy(
            entity_type,
            include_inactive=include_inactive,
        )

    def list_resolution_policies(
        self,
        *,
        include_inactive: bool = False,
    ) -> list[EntityResolutionPolicy]:
        """List all entity resolution policies."""
        return self._dictionary.find_resolution_policies(
            include_inactive=include_inactive,
        )

    def ensure_resolution_policy_for_entity_type(
        self,
        *,
        entity_type: str,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> EntityResolutionPolicy | None:
        """Ensure an active resolution policy exists for an entity type."""
        normalized_entity_type = self._normalize_entity_type_id(entity_type)
        created_by_normalized = self._normalize_created_by(created_by)
        existing_policy = self._dictionary.get_resolution_policy(normalized_entity_type)
        if existing_policy is not None:
            return existing_policy
        if (
            self._dictionary.get_entity_type(
                normalized_entity_type,
                include_inactive=True,
            )
            is None
        ):
            return None

        policy_strategy, required_anchors, auto_merge_threshold = (
            self._resolve_default_resolution_policy(normalized_entity_type)
        )
        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )
        return self._dictionary.create_resolution_policy(
            entity_type=normalized_entity_type,
            policy_strategy=policy_strategy,
            required_anchors=list(required_anchors),
            auto_merge_threshold=auto_merge_threshold,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

    @staticmethod
    def _resolve_default_resolution_policy(
        entity_type: str,
    ) -> tuple[str, tuple[str, ...], float]:
        normalized_entity_type = entity_type.strip().upper()
        direct_match = _DEFAULT_RESOLUTION_POLICY_BY_ENTITY_TYPE.get(
            normalized_entity_type,
        )
        if direct_match is not None:
            return direct_match
        if normalized_entity_type.startswith("GENE_"):
            return ("STRICT_MATCH", (), 1.0)
        if normalized_entity_type.startswith("PROTEIN_"):
            return ("STRICT_MATCH", (), 1.0)
        return ("STRICT_MATCH", (), 1.0)

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
    ) -> DictionaryEntityType:
        """Create a dictionary entity type with provenance metadata."""
        resolved_domain_context = self._resolve_domain_context(
            explicit_domain_context=domain_context,
            fallback=DomainContextResolver.GENERAL_DEFAULT_DOMAIN,
        )
        if resolved_domain_context is None:
            resolved_domain_context = DomainContextResolver.GENERAL_DEFAULT_DOMAIN
        created_by_normalized = self._normalize_created_by(created_by)
        existing_entity_type = self._resolve_existing_entity_type_for_create(
            entity_type=entity_type,
            display_name=display_name,
            domain_context=resolved_domain_context,
            allow_semantic_reuse=created_by_normalized.startswith("agent:"),
        )
        if existing_entity_type is not None:
            target_review_status = self._resolve_agent_creation_review_status(
                created_by=created_by_normalized,
                research_space_settings=research_space_settings,
            )
            resolved_entity_type = existing_entity_type
            if target_review_status == "ACTIVE" and (
                not existing_entity_type.is_active
                or existing_entity_type.review_status != "ACTIVE"
            ):
                resolved_entity_type = self._dictionary.set_entity_type_review_status(
                    existing_entity_type.id,
                    review_status="ACTIVE",
                    reviewed_by=created_by_normalized,
                )
            self.ensure_resolution_policy_for_entity_type(
                entity_type=resolved_entity_type.id,
                created_by=created_by_normalized,
                source_ref=source_ref,
                research_space_settings=research_space_settings,
            )
            return resolved_entity_type

        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )
        embedding_model = self._resolve_embedding_model()
        description_embedding, embedded_at, resolved_embedding_model = (
            self._embed_description(
                description,
                model_name=embedding_model,
            )
        )
        created_entity_type = self._dictionary.create_entity_type(
            entity_type=entity_type,
            display_name=display_name,
            description=description,
            domain_context=resolved_domain_context,
            external_ontology_ref=external_ontology_ref,
            expected_properties=expected_properties,
            description_embedding=description_embedding,
            embedded_at=embedded_at,
            embedding_model=resolved_embedding_model,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )
        self.ensure_resolution_policy_for_entity_type(
            entity_type=created_entity_type.id,
            created_by=created_by_normalized,
            source_ref=source_ref,
            research_space_settings=research_space_settings,
        )
        return created_entity_type

    def list_entity_types(
        self,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryEntityType]:
        """List dictionary entity types."""
        resolved_domain_context = self._resolve_domain_context(
            explicit_domain_context=domain_context,
            fallback=None,
        )
        return self._dictionary.find_entity_types(
            domain_context=resolved_domain_context,
            include_inactive=include_inactive,
        )

    def get_entity_type(
        self,
        entity_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryEntityType | None:
        """Get a dictionary entity type by ID."""
        return self._dictionary.get_entity_type(
            entity_type_id,
            include_inactive=include_inactive,
        )

    def set_entity_type_review_status(
        self,
        entity_type_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryEntityType:
        """Set review state for a dictionary entity type."""
        reviewed_by_normalized = reviewed_by.strip()
        if not reviewed_by_normalized:
            msg = "reviewed_by is required"
            raise ValueError(msg)

        target_status = self._normalize_review_status(review_status)
        current = self._dictionary.get_entity_type(
            entity_type_id,
            include_inactive=True,
        )
        if current is None:
            msg = f"Entity type '{entity_type_id}' not found"
            raise ValueError(msg)

        self._validate_status_transition(
            from_status=current.review_status,
            to_status=target_status,
        )

        normalized_reason: str | None = None
        if target_status == "REVOKED":
            if revocation_reason is None or not revocation_reason.strip():
                msg = "revocation_reason is required when setting REVOKED status"
                raise ValueError(msg)
            normalized_reason = revocation_reason.strip()
        elif revocation_reason is not None:
            msg = "revocation_reason is only valid for REVOKED status"
            raise ValueError(msg)

        return self._dictionary.set_entity_type_review_status(
            entity_type_id,
            review_status=target_status,
            reviewed_by=reviewed_by_normalized,
            revocation_reason=normalized_reason,
        )

    def revoke_entity_type(
        self,
        entity_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryEntityType:
        """Convenience operation for revoking an entity type."""
        return self.set_entity_type_review_status(
            entity_type_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

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
    ) -> DictionaryRelationType:
        """Create a dictionary relation type with provenance metadata."""
        resolved_domain_context = self._resolve_domain_context(
            explicit_domain_context=domain_context,
            fallback=DomainContextResolver.GENERAL_DEFAULT_DOMAIN,
        )
        if resolved_domain_context is None:
            resolved_domain_context = DomainContextResolver.GENERAL_DEFAULT_DOMAIN
        created_by_normalized = self._normalize_created_by(created_by)
        existing_relation_type = self._resolve_existing_relation_type_for_create(
            relation_type=relation_type,
            display_name=display_name,
            domain_context=resolved_domain_context,
            allow_semantic_reuse=created_by_normalized.startswith("agent:"),
        )
        if existing_relation_type is not None:
            return existing_relation_type

        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )
        embedding_model = self._resolve_embedding_model()
        description_embedding, embedded_at, resolved_embedding_model = (
            self._embed_description(
                description,
                model_name=embedding_model,
            )
        )
        return self._dictionary.create_relation_type(
            relation_type=relation_type,
            display_name=display_name,
            description=description,
            domain_context=resolved_domain_context,
            is_directional=is_directional,
            inverse_label=inverse_label,
            description_embedding=description_embedding,
            embedded_at=embedded_at,
            embedding_model=resolved_embedding_model,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

    def list_relation_types(
        self,
        *,
        domain_context: str | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryRelationType]:
        """List dictionary relation types."""
        resolved_domain_context = self._resolve_domain_context(
            explicit_domain_context=domain_context,
            fallback=None,
        )
        return self._dictionary.find_relation_types(
            domain_context=resolved_domain_context,
            include_inactive=include_inactive,
        )

    def get_relation_type(
        self,
        relation_type_id: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryRelationType | None:
        """Get a dictionary relation type by ID."""
        return self._dictionary.get_relation_type(
            relation_type_id,
            include_inactive=include_inactive,
        )

    def set_relation_type_review_status(
        self,
        relation_type_id: str,
        *,
        review_status: ReviewStatus,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationType:
        """Set review state for a dictionary relation type."""
        reviewed_by_normalized = reviewed_by.strip()
        if not reviewed_by_normalized:
            msg = "reviewed_by is required"
            raise ValueError(msg)

        target_status = self._normalize_review_status(review_status)
        current = self._dictionary.get_relation_type(
            relation_type_id,
            include_inactive=True,
        )
        if current is None:
            msg = f"Relation type '{relation_type_id}' not found"
            raise ValueError(msg)

        self._validate_status_transition(
            from_status=current.review_status,
            to_status=target_status,
        )

        normalized_reason: str | None = None
        if target_status == "REVOKED":
            if revocation_reason is None or not revocation_reason.strip():
                msg = "revocation_reason is required when setting REVOKED status"
                raise ValueError(msg)
            normalized_reason = revocation_reason.strip()
        elif revocation_reason is not None:
            msg = "revocation_reason is only valid for REVOKED status"
            raise ValueError(msg)

        return self._dictionary.set_relation_type_review_status(
            relation_type_id,
            review_status=target_status,
            reviewed_by=reviewed_by_normalized,
            revocation_reason=normalized_reason,
        )

    def revoke_relation_type(
        self,
        relation_type_id: str,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryRelationType:
        """Convenience operation for revoking a relation type."""
        return self.set_relation_type_review_status(
            relation_type_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )

    def resolve_relation_synonym(
        self,
        synonym: str,
        *,
        include_inactive: bool = False,
    ) -> DictionaryRelationType | None:
        """Resolve a relation synonym to its canonical relation type."""
        return self._dictionary.resolve_relation_synonym(
            synonym,
            include_inactive=include_inactive,
        )

    def create_relation_synonym(  # noqa: PLR0913
        self,
        *,
        relation_type_id: str,
        synonym: str,
        source: str | None = None,
        created_by: str,
        source_ref: str | None = None,
        research_space_settings: ResearchSpaceSettings | None = None,
    ) -> DictionaryRelationSynonym:
        """Create a synonym entry for a relation type."""
        created_by_normalized = self._normalize_created_by(created_by)
        relation_type = self._dictionary.get_relation_type(
            relation_type_id,
            include_inactive=True,
        )
        if relation_type is None:
            msg = f"Relation type '{relation_type_id}' not found"
            raise ValueError(msg)

        initial_review_status = self._resolve_agent_creation_review_status(
            created_by=created_by_normalized,
            research_space_settings=research_space_settings,
        )
        return self._dictionary.create_relation_synonym(
            relation_type_id=relation_type_id,
            synonym=synonym,
            source=source,
            created_by=created_by_normalized,
            source_ref=source_ref,
            review_status=initial_review_status,
        )

    def list_relation_synonyms(
        self,
        *,
        relation_type_id: str | None = None,
        review_status: ReviewStatus | None = None,
        include_inactive: bool = False,
    ) -> list[DictionaryRelationSynonym]:
        """List relation-type synonyms."""
        normalized_review_status = (
            self._normalize_review_status(review_status)
            if review_status is not None
            else None
        )
        return self._dictionary.find_relation_synonyms(
            relation_type_id=relation_type_id,
            review_status=normalized_review_status,
            include_inactive=include_inactive,
        )

    def set_relation_synonym_review_status(
        self,
        synonym_id: int,
        *,
        review_status: ReviewStatus,
        reviewed_by: str,
        revocation_reason: str | None = None,
    ) -> DictionaryRelationSynonym:
        """Set review state for a relation-type synonym."""
        reviewed_by_normalized = reviewed_by.strip()
        if not reviewed_by_normalized:
            msg = "reviewed_by is required"
            raise ValueError(msg)

        target_status = self._normalize_review_status(review_status)
        if target_status == "REVOKED":
            if revocation_reason is None or not revocation_reason.strip():
                msg = "revocation_reason is required when setting REVOKED status"
                raise ValueError(msg)
            normalized_reason: str | None = revocation_reason.strip()
        elif revocation_reason is not None:
            msg = "revocation_reason is only valid for REVOKED status"
            raise ValueError(msg)
        else:
            normalized_reason = None

        return self._dictionary.set_relation_synonym_review_status(
            synonym_id,
            review_status=target_status,
            reviewed_by=reviewed_by_normalized,
            revocation_reason=normalized_reason,
        )

    def revoke_relation_synonym(
        self,
        synonym_id: int,
        *,
        reason: str,
        reviewed_by: str,
    ) -> DictionaryRelationSynonym:
        """Convenience operation for revoking a relation-type synonym."""
        return self.set_relation_synonym_review_status(
            synonym_id,
            review_status="REVOKED",
            reviewed_by=reviewed_by,
            revocation_reason=reason,
        )


__all__ = ["DictionaryManagementRelationMixin"]
