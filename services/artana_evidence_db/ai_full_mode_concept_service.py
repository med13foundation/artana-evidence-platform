# mypy: disable-error-code="attr-defined,no-any-return"
"""Concept proposal workflows for AI Full Mode."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_db.ai_full_mode_models import (
    ConceptProposal,
    ConceptProposalStatus,
)
from artana_evidence_db.ai_full_mode_persistence_models import (
    ConceptProposalModel,
)
from artana_evidence_db.ai_full_mode_support import (
    ConceptResolution,
    _as_uuid,
    _concept_from_model,
    _manual_actor,
    _normalize_alias_key,
    _normalize_domain_context,
    _normalize_entity_type,
    _normalize_external_refs,
    _normalize_label,
    _normalize_optional_text,
    _normalize_required_text,
    _proposal_hash,
    _snapshot_model,
)
from artana_evidence_db.common_types import JSONObject
from sqlalchemy import select


class AIFullModeConceptMixin:
    """Concept proposal and duplicate-resolution behavior."""

    def propose_concept(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        canonical_label: str,
        synonyms: list[str],
        external_refs: list[JSONObject],
        evidence_payload: JSONObject,
        rationale: str | None,
        proposed_by: str,
        source_ref: str | None = None,
    ) -> ConceptProposal:
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_domain = _normalize_domain_context(domain_context)
        normalized_entity_type = _normalize_entity_type(entity_type)
        normalized_label = _normalize_label(canonical_label)
        normalized_alias = _normalize_alias_key(normalized_label)
        normalized_synonyms = self._normalize_synonyms(synonyms, canonical_label=normalized_label)
        normalized_external_refs = _normalize_external_refs(external_refs)
        normalized_actor = _manual_actor(proposed_by)
        normalized_source_ref = _normalize_optional_text(source_ref)

        existing_replay = self._get_concept_proposal_by_source_ref(
            research_space_id=normalized_space_id,
            source_ref=normalized_source_ref,
        )
        if existing_replay is not None:
            self._assert_concept_replay_matches(
                existing_replay,
                domain_context=normalized_domain,
                entity_type=normalized_entity_type,
                normalized_label=normalized_alias,
                synonyms=normalized_synonyms,
                external_refs=normalized_external_refs,
            )
            return _concept_from_model(existing_replay)

        resolution = self.resolve_concept_candidate(
            research_space_id=normalized_space_id,
            domain_context=normalized_domain,
            entity_type=normalized_entity_type,
            normalized_label=normalized_alias,
            synonyms=normalized_synonyms,
            external_refs=normalized_external_refs,
        )
        status: ConceptProposalStatus = (
            "DUPLICATE_CANDIDATE"
            if resolution.candidate_decision != "CREATE_NEW"
            else "SUBMITTED"
        )
        model = ConceptProposalModel(
            id=uuid4(),
            research_space_id=_as_uuid(normalized_space_id),
            status=status,
            candidate_decision=resolution.candidate_decision,
            domain_context=normalized_domain,
            entity_type=normalized_entity_type,
            canonical_label=normalized_label,
            normalized_label=normalized_alias,
            existing_concept_member_id=(
                _as_uuid(resolution.existing_concept_member_id)
                if resolution.existing_concept_member_id is not None
                else None
            ),
            synonyms_payload=normalized_synonyms,
            external_refs_payload=normalized_external_refs,
            evidence_payload=evidence_payload,
            duplicate_checks_payload=resolution.duplicate_checks,
            warnings_payload=resolution.warnings,
            decision_payload={"recommended_action": resolution.candidate_decision},
            rationale=_normalize_optional_text(rationale),
            proposed_by=normalized_actor,
            source_ref=normalized_source_ref,
            proposal_hash="pending",
        )
        self._session.add(model)
        self._session.flush()
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=normalized_actor,
            source_ref=normalized_source_ref,
        )
        return _concept_from_model(model)

    def list_concept_proposals(
        self,
        *,
        research_space_id: str,
        status: ConceptProposalStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConceptProposal]:
        stmt = select(ConceptProposalModel).where(
            ConceptProposalModel.research_space_id == _as_uuid(research_space_id),
        )
        if status is not None:
            stmt = stmt.where(ConceptProposalModel.status == status)
        stmt = stmt.order_by(ConceptProposalModel.created_at.desc()).offset(offset).limit(limit)
        return [_concept_from_model(model) for model in self._session.scalars(stmt).all()]

    def get_concept_proposal(self, proposal_id: str) -> ConceptProposal:
        return _concept_from_model(self._get_concept_model(proposal_id))

    def reject_concept_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> ConceptProposal:
        model = self._get_concept_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Concept proposal",
        )
        self._require_concept_reviewable(model)
        before = _snapshot_model(model)
        now = datetime.now(UTC)
        model.status = "REJECTED"
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = now
        model.decision_reason = _normalize_required_text(
            decision_reason,
            field_name="decision_reason",
        )
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="REJECT",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _concept_from_model(model)

    def request_concept_changes(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> ConceptProposal:
        model = self._get_concept_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Concept proposal",
        )
        self._require_concept_reviewable(model)
        before = _snapshot_model(model)
        model.status = "CHANGES_REQUESTED"
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = _normalize_required_text(
            decision_reason,
            field_name="decision_reason",
        )
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="REQUEST_CHANGES",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _concept_from_model(model)

    def approve_concept_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str | None = None,
    ) -> ConceptProposal:
        model = self._get_concept_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Concept proposal",
        )
        if model.status == "APPLIED":
            return _concept_from_model(model)
        self._require_concept_reviewable(model)
        if model.candidate_decision != "CREATE_NEW":
            msg = "Duplicate concept proposals must be merged, rejected, or changed"
            raise ValueError(msg)
        before = _snapshot_model(model)
        set_id = self._ensure_ai_concept_set(
            research_space_id=str(model.research_space_id),
            domain_context=model.domain_context,
            entity_type=model.entity_type,
            created_by=_manual_actor(reviewed_by),
        )
        member = self._concepts.create_concept_member(
            member_id=str(uuid4()),
            concept_set_id=set_id,
            research_space_id=str(model.research_space_id),
            domain_context=model.domain_context,
            canonical_label=model.canonical_label,
            normalized_label=model.normalized_label,
            sense_key=model.entity_type.lower(),
            dictionary_dimension="AI_CONCEPT",
            dictionary_entry_id=f"proposal:{model.id}",
            is_provisional=False,
            metadata_payload={
                "entity_type": model.entity_type,
                "proposal_id": str(model.id),
                "synonyms": list(model.synonyms_payload),
                "external_refs": list(model.external_refs_payload),
            },
            created_by=_manual_actor(reviewed_by),
            source_ref=f"concept-proposal:{model.id}",
            review_status="ACTIVE",
        )
        self._ensure_alias(
            concept_member_id=member.id,
            research_space_id=str(model.research_space_id),
            domain_context=model.domain_context,
            alias_label=model.canonical_label,
            alias_normalized=model.normalized_label,
            source="canonical",
            created_by=_manual_actor(reviewed_by),
            source_ref=f"concept-proposal:{model.id}:canonical",
        )
        self._ensure_proposed_aliases(model, target_member_id=member.id, actor=reviewed_by)
        self._finalize_concept_model(
            model,
            status="APPLIED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            applied_member_id=member.id,
        )
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="APPLY",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _concept_from_model(model)

    def merge_concept_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        target_concept_member_id: str,
        reviewed_by: str,
        decision_reason: str | None = None,
    ) -> ConceptProposal:
        model = self._get_concept_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Concept proposal",
        )
        if model.status == "MERGED":
            return _concept_from_model(model)
        self._require_concept_reviewable(model)
        target = self._get_concept_member_model(target_concept_member_id)
        if str(target.research_space_id) != str(model.research_space_id):
            msg = "Merge target belongs to a different graph space"
            raise ValueError(msg)
        before = _snapshot_model(model)
        self._ensure_alias(
            concept_member_id=str(target.id),
            research_space_id=str(model.research_space_id),
            domain_context=model.domain_context,
            alias_label=model.canonical_label,
            alias_normalized=model.normalized_label,
            source="merged_label",
            created_by=_manual_actor(reviewed_by),
            source_ref=f"concept-proposal:{model.id}:merged-label",
        )
        self._ensure_proposed_aliases(model, target_member_id=str(target.id), actor=reviewed_by)
        self._finalize_concept_model(
            model,
            status="MERGED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            applied_member_id=str(target.id),
        )
        self._record_change(
            table_name=ConceptProposalModel.__tablename__,
            record_id=str(model.id),
            action="MERGE",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _concept_from_model(model)

    def resolve_concept_candidate(
        self,
        *,
        research_space_id: str,
        domain_context: str,
        entity_type: str,
        normalized_label: str,
        synonyms: list[str],
        external_refs: list[JSONObject],
    ) -> ConceptResolution:
        exact_member = self._find_member_by_normalized_label(
            research_space_id=research_space_id,
            domain_context=domain_context,
            entity_type=entity_type,
            normalized_label=normalized_label,
        )
        if exact_member is not None:
            return ConceptResolution(
                candidate_decision="MATCH_EXISTING",
                existing_concept_member_id=str(exact_member.id),
                duplicate_checks={
                    "exact_label": {
                        "matched": True,
                        "concept_member_id": str(exact_member.id),
                    },
                },
                warnings=[],
            )

        external_ref_member = self._find_member_by_external_refs(
            research_space_id=research_space_id,
            domain_context=domain_context,
            entity_type=entity_type,
            external_refs=external_refs,
        )
        if external_ref_member is not None:
            return ConceptResolution(
                candidate_decision="EXTERNAL_REF_MATCH",
                existing_concept_member_id=str(external_ref_member.id),
                duplicate_checks={
                    "external_ref": {
                        "matched": True,
                        "concept_member_id": str(external_ref_member.id),
                    },
                },
                warnings=[],
            )

        synonym_members = self._find_members_by_synonyms(
            research_space_id=research_space_id,
            domain_context=domain_context,
            entity_type=entity_type,
            synonyms=synonyms,
        )
        if len(synonym_members) == 1:
            target_member_id = next(iter(synonym_members))
            return ConceptResolution(
                candidate_decision="MERGE_AS_SYNONYM",
                existing_concept_member_id=target_member_id,
                duplicate_checks={
                    "synonyms": {
                        "matched": True,
                        "concept_member_ids": [target_member_id],
                    },
                },
                warnings=[],
            )
        if len(synonym_members) > 1:
            sorted_member_ids = sorted(synonym_members)
            return ConceptResolution(
                candidate_decision="SYNONYM_COLLISION",
                existing_concept_member_id=None,
                duplicate_checks={
                    "synonyms": {
                        "matched": True,
                        "concept_member_ids": sorted_member_ids,
                    },
                },
                warnings=[
                    "Synonyms match more than one existing concept; human review is required.",
                ],
            )
        return ConceptResolution(
            candidate_decision="CREATE_NEW",
            existing_concept_member_id=None,
            duplicate_checks={
                "exact_label": {"matched": False},
                "external_ref": {"matched": False},
                "synonyms": {"matched": False},
            },
            warnings=[],
        )

