# mypy: disable-error-code="attr-defined,no-any-return"
"""Repository helper methods for AI Full Mode service mixins."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_db.ai_full_mode_models import (
    ConceptProposalStatus,
)
from artana_evidence_db.ai_full_mode_persistence_models import (
    ConceptProposalModel,
    ConnectorProposalModel,
    GraphChangeProposalModel,
)
from artana_evidence_db.ai_full_mode_support import (
    _REVIEWABLE_CONCEPT_STATUSES,
    _as_uuid,
    _external_ref_alias,
    _manual_actor,
    _member_matches_entity_type,
    _normalize_alias_key,
    _normalize_label,
    _normalize_optional_text,
    _proposal_hash,
)
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_concept_models import (
    ConceptAliasModel,
    ConceptMemberModel,
    ConceptSetModel,
)
from sqlalchemy import select


class AIFullModeRepositoryMixin:
    """Shared SQLAlchemy lookup and concept alias helpers."""

    def _normalize_synonyms(self, synonyms: list[str], *, canonical_label: str) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = {_normalize_alias_key(canonical_label)}
        for item in synonyms:
            label = _normalize_label(item)
            key = _normalize_alias_key(label)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(label)
        return normalized

    def _get_concept_model(self, proposal_id: str) -> ConceptProposalModel:
        model = self._session.get(ConceptProposalModel, _as_uuid(proposal_id))
        if model is None:
            msg = f"Concept proposal '{proposal_id}' not found"
            raise ValueError(msg)
        return model

    def _get_graph_change_model(self, proposal_id: str) -> GraphChangeProposalModel:
        model = self._session.get(GraphChangeProposalModel, _as_uuid(proposal_id))
        if model is None:
            msg = f"Graph-change proposal '{proposal_id}' not found"
            raise ValueError(msg)
        return model

    def _get_connector_model(self, proposal_id: str) -> ConnectorProposalModel:
        model = self._session.get(ConnectorProposalModel, _as_uuid(proposal_id))
        if model is None:
            msg = f"Connector proposal '{proposal_id}' not found"
            raise ValueError(msg)
        return model

    def _assert_model_in_space(
        self,
        model: ConceptProposalModel | GraphChangeProposalModel | ConnectorProposalModel,
        *,
        research_space_id: str | None,
        resource_name: str,
    ) -> None:
        if research_space_id is None:
            return
        if str(model.research_space_id) != str(_as_uuid(research_space_id)):
            msg = f"{resource_name} '{model.id}' not found in graph space"
            raise ValueError(msg)

    def _get_concept_member_model(self, concept_member_id: str) -> ConceptMemberModel:
        model = self._session.get(ConceptMemberModel, _as_uuid(concept_member_id))
        if model is None:
            msg = f"Concept member '{concept_member_id}' not found"
            raise ValueError(msg)
        return model

    def _get_concept_proposal_by_source_ref(
        self,
        *,
        research_space_id: str,
        source_ref: str | None,
    ) -> ConceptProposalModel | None:
        if source_ref is None:
            return None
        stmt = select(ConceptProposalModel).where(
            ConceptProposalModel.research_space_id == _as_uuid(research_space_id),
            ConceptProposalModel.source_ref == source_ref,
        )
        return self._session.scalar(stmt.limit(1))

    def _get_graph_change_by_source_ref(
        self,
        *,
        research_space_id: str,
        source_ref: str | None,
    ) -> GraphChangeProposalModel | None:
        if source_ref is None:
            return None
        stmt = select(GraphChangeProposalModel).where(
            GraphChangeProposalModel.research_space_id == _as_uuid(research_space_id),
            GraphChangeProposalModel.source_ref == source_ref,
        )
        return self._session.scalar(stmt.limit(1))

    def _assert_concept_replay_matches(
        self,
        model: ConceptProposalModel,
        *,
        domain_context: str,
        entity_type: str,
        normalized_label: str,
        synonyms: list[str],
        external_refs: list[JSONObject],
    ) -> None:
        if (
            model.domain_context != domain_context
            or model.entity_type != entity_type
            or model.normalized_label != normalized_label
            or list(model.synonyms_payload) != synonyms
            or list(model.external_refs_payload) != external_refs
        ):
            msg = "source_ref is already bound to a different concept proposal"
            raise ValueError(msg)

    def _require_concept_reviewable(self, model: ConceptProposalModel) -> None:
        if model.status not in _REVIEWABLE_CONCEPT_STATUSES:
            msg = f"Concept proposal '{model.id}' is already {model.status}"
            raise ValueError(msg)

    def _find_member_by_normalized_label(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        normalized_label: str,
    ) -> ConceptMemberModel | None:
        stmt = select(ConceptMemberModel).where(
            ConceptMemberModel.research_space_id == _as_uuid(research_space_id),
            ConceptMemberModel.domain_context == domain_context,
            ConceptMemberModel.normalized_label == normalized_label,
            ConceptMemberModel.is_active.is_(True),
        )
        for model in self._session.scalars(stmt).all():
            if _member_matches_entity_type(model, entity_type=entity_type):
                return model
        return None

    def _find_member_by_external_refs(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        external_refs: list[JSONObject],
    ) -> ConceptMemberModel | None:
        for ref in external_refs:
            _, alias_normalized, _ = _external_ref_alias(ref)
            member = self._find_member_by_alias(
                research_space_id=research_space_id,
                domain_context=domain_context,
                entity_type=entity_type,
                alias_normalized=alias_normalized,
            )
            if member is not None:
                return member
        return None

    def _find_members_by_synonyms(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        synonyms: list[str],
    ) -> set[str]:
        matches: set[str] = set()
        for synonym in synonyms:
            member = self._find_member_by_alias(
                research_space_id=research_space_id,
                domain_context=domain_context,
                entity_type=entity_type,
                alias_normalized=_normalize_alias_key(synonym),
            )
            if member is not None:
                matches.add(str(member.id))
        return matches

    def _find_member_by_alias(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        alias_normalized: str,
    ) -> ConceptMemberModel | None:
        stmt = (
            select(ConceptMemberModel)
            .join(ConceptAliasModel, ConceptAliasModel.concept_member_id == ConceptMemberModel.id)
            .where(
                ConceptAliasModel.research_space_id == _as_uuid(research_space_id),
                ConceptAliasModel.domain_context == domain_context,
                ConceptAliasModel.alias_normalized == alias_normalized,
                ConceptAliasModel.is_active.is_(True),
                ConceptMemberModel.is_active.is_(True),
            )
        )
        for model in self._session.scalars(stmt).all():
            if _member_matches_entity_type(model, entity_type=entity_type):
                return model
        return None

    def _ensure_ai_concept_set(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        created_by: str,
    ) -> str:
        slug = f"ai-full-{domain_context}-{entity_type.lower()}"
        stmt = select(ConceptSetModel).where(
            ConceptSetModel.research_space_id == _as_uuid(research_space_id),
            ConceptSetModel.slug == slug,
            ConceptSetModel.is_active.is_(True),
        )
        existing = self._session.scalar(stmt.limit(1))
        if existing is not None:
            return str(existing.id)
        concept_set = self._concepts.create_concept_set(
            set_id=str(uuid4()),
            research_space_id=research_space_id,
            name=f"AI Full Mode {entity_type} Concepts",
            slug=slug,
            domain_context=domain_context,
            description="Concept set managed by DB-owned AI Full Mode governance.",
            created_by=created_by,
            source_ref=f"ai-full-mode:{domain_context}:{entity_type}",
            review_status="ACTIVE",
        )
        return concept_set.id

    def _ensure_alias(  # noqa: PLR0913
        self,
        *,
        concept_member_id: str,
        research_space_id: str,
        domain_context: str,
        alias_label: str,
        alias_normalized: str,
        source: str,
        created_by: str,
        source_ref: str,
    ) -> None:
        existing = self._concepts.resolve_member_by_alias(
            research_space_id=research_space_id,
            domain_context=domain_context,
            alias_normalized=alias_normalized,
            include_inactive=False,
        )
        if existing is not None:
            if existing.id == concept_member_id:
                return
            msg = f"Alias '{alias_label}' already belongs to another concept"
            raise ValueError(msg)
        self._concepts.create_concept_alias(
            concept_member_id=concept_member_id,
            research_space_id=research_space_id,
            domain_context=domain_context,
            alias_label=alias_label,
            alias_normalized=alias_normalized,
            source=source,
            created_by=created_by,
            source_ref=source_ref,
            review_status="ACTIVE",
        )

    def _ensure_proposed_aliases(
        self,
        model: ConceptProposalModel,
        *,
        target_member_id: str,
        actor: str,
    ) -> None:
        for synonym in model.synonyms_payload:
            self._ensure_alias(
                concept_member_id=target_member_id,
                research_space_id=str(model.research_space_id),
                domain_context=model.domain_context,
                alias_label=synonym,
                alias_normalized=_normalize_alias_key(synonym),
                source="synonym",
                created_by=_manual_actor(actor),
                source_ref=f"concept-proposal:{model.id}:synonym:{_normalize_alias_key(synonym)}",
            )
        for ref in model.external_refs_payload:
            label, alias_normalized, source = _external_ref_alias(ref)
            self._ensure_alias(
                concept_member_id=target_member_id,
                research_space_id=str(model.research_space_id),
                domain_context=model.domain_context,
                alias_label=label,
                alias_normalized=alias_normalized,
                source=source,
                created_by=_manual_actor(actor),
                source_ref=f"concept-proposal:{model.id}:external-ref:{alias_normalized}",
            )

    def _finalize_concept_model(
        self,
        model: ConceptProposalModel,
        *,
        status: ConceptProposalStatus,
        reviewed_by: str,
        decision_reason: str | None,
        applied_member_id: str,
    ) -> None:
        model.status = status
        model.applied_concept_member_id = _as_uuid(applied_member_id)
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = _normalize_optional_text(decision_reason)
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()

