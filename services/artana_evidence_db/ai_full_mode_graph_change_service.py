# mypy: disable-error-code="attr-defined,no-any-return"
"""Graph-change proposal workflows for AI Full Mode."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from artana_evidence_db.ai_full_mode_models import (
    GraphChangeProposal,
)
from artana_evidence_db.ai_full_mode_persistence_models import (
    GraphChangeProposalModel,
)
from artana_evidence_db.ai_full_mode_support import (
    _REVIEWABLE_GRAPH_CHANGE_STATUSES,
    _as_uuid,
    _graph_change_from_model,
    _json_mapping,
    _json_optional_str,
    _json_sequence,
    _json_str,
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
from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.fact_assessment import FactAssessment, assessment_confidence
from artana_evidence_db.fact_assessment_support import fact_assessment_metadata
from artana_evidence_db.relation_claim_models import KernelRelationClaim
from pydantic import ValidationError
from sqlalchemy import select


class AIFullModeGraphChangeMixin:
    """Graph-change proposal, planning, and application behavior."""

    def propose_graph_change(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        proposal_payload: JSONObject,
        proposed_by: str,
        source_ref: str | None,
    ) -> GraphChangeProposal:
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_actor = _manual_actor(proposed_by)
        normalized_source_ref = _normalize_optional_text(source_ref)
        existing_replay = self._get_graph_change_by_source_ref(
            research_space_id=normalized_space_id,
            source_ref=normalized_source_ref,
        )
        if existing_replay is not None:
            if existing_replay.proposal_payload != proposal_payload:
                msg = "source_ref is already bound to a different graph-change proposal"
                raise ValueError(msg)
            return _graph_change_from_model(existing_replay)

        resolution_plan, warnings = self.build_graph_change_resolution_plan(
            research_space_id=normalized_space_id,
            proposal_payload=proposal_payload,
        )
        errors = [
            item
            for item in _json_sequence(resolution_plan.get("errors"))
            if isinstance(item, str)
        ]
        if errors:
            msg = "; ".join(errors)
            raise ValueError(msg)
        model = GraphChangeProposalModel(
            id=uuid4(),
            research_space_id=_as_uuid(normalized_space_id),
            status="READY_FOR_REVIEW",
            proposal_payload=proposal_payload,
            resolution_plan_payload=resolution_plan,
            warnings_payload=warnings,
            error_payload=[],
            proposed_by=normalized_actor,
            source_ref=normalized_source_ref,
            proposal_hash="pending",
        )
        self._session.add(model)
        self._session.flush()
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=GraphChangeProposalModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=normalized_actor,
            source_ref=normalized_source_ref,
        )
        return _graph_change_from_model(model)

    def get_graph_change_proposal(self, proposal_id: str) -> GraphChangeProposal:
        return _graph_change_from_model(self._get_graph_change_model(proposal_id))

    def list_graph_change_proposals(
        self,
        *,
        research_space_id: str,
        status: Literal[
            "READY_FOR_REVIEW",
            "CHANGES_REQUESTED",
            "REJECTED",
            "APPLIED",
        ]
        | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[GraphChangeProposal]:
        stmt = select(GraphChangeProposalModel).where(
            GraphChangeProposalModel.research_space_id == _as_uuid(research_space_id),
        )
        if status is not None:
            stmt = stmt.where(GraphChangeProposalModel.status == status)
        stmt = stmt.order_by(GraphChangeProposalModel.created_at.desc()).offset(offset).limit(limit)
        return [
            _graph_change_from_model(model)
            for model in self._session.scalars(stmt).all()
        ]

    def reject_graph_change_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> GraphChangeProposal:
        return self._set_graph_change_status(
            proposal_id,
            research_space_id=research_space_id,
            status="REJECTED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="REJECT",
        )

    def request_graph_change_changes(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> GraphChangeProposal:
        return self._set_graph_change_status(
            proposal_id,
            research_space_id=research_space_id,
            status="CHANGES_REQUESTED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="REQUEST_CHANGES",
        )

    def build_graph_change_resolution_plan(
        self,
        *,
        research_space_id: str,
        proposal_payload: JSONObject,
    ) -> tuple[JSONObject, list[str]]:
        concepts = self._parse_graph_change_concepts(proposal_payload)
        claims = self._parse_graph_change_claims(proposal_payload)
        warnings: list[str] = []
        errors: list[str] = []
        concept_steps: list[JSONValue] = []
        concept_index: dict[str, JSONObject] = {}
        for concept in concepts:
            local_id = _json_str(concept.get("local_id"), field_name="concept.local_id")
            domain_context = _normalize_domain_context(
                _json_str(concept.get("domain_context"), field_name="concept.domain_context"),
            )
            entity_type = _normalize_entity_type(
                _json_str(concept.get("entity_type"), field_name="concept.entity_type"),
            )
            label = _normalize_label(
                _json_str(concept.get("canonical_label"), field_name="concept.canonical_label"),
            )
            synonyms = [
                _normalize_label(item)
                for item in _json_sequence(concept.get("synonyms"))
                if isinstance(item, str)
            ]
            external_refs = [
                _json_mapping(item)
                for item in _json_sequence(concept.get("external_refs"))
                if isinstance(item, Mapping)
            ]
            resolution = self.resolve_concept_candidate(
                research_space_id=research_space_id,
                domain_context=domain_context,
                entity_type=entity_type,
                normalized_label=_normalize_alias_key(label),
                synonyms=self._normalize_synonyms(synonyms, canonical_label=label),
                external_refs=_normalize_external_refs(external_refs),
            )
            if resolution.candidate_decision == "SYNONYM_COLLISION":
                errors.extend(resolution.warnings)
            step: JSONObject = {
                "local_id": local_id,
                "action": resolution.candidate_decision,
                "existing_concept_member_id": resolution.existing_concept_member_id,
                "domain_context": domain_context,
                "entity_type": entity_type,
                "canonical_label": label,
            }
            concept_steps.append(step)
            concept_index[local_id] = step

        claim_steps: list[JSONValue] = []
        for position, claim in enumerate(claims):
            claim_step = self._build_claim_plan_step(
                position=position,
                claim=claim,
                concept_index=concept_index,
            )
            claim_errors = [
                item
                for item in _json_sequence(claim_step.get("errors"))
                if isinstance(item, str)
            ]
            errors.extend(claim_errors)
            claim_steps.append(claim_step)
        return (
            {
                "concept_steps": concept_steps,
                "claim_steps": claim_steps,
                "errors": errors,
            },
            warnings,
        )

    def _parse_graph_change_concepts(self, proposal_payload: JSONObject) -> list[JSONObject]:
        concepts = _json_sequence(proposal_payload.get("concepts"))
        parsed = [_json_mapping(item) for item in concepts if isinstance(item, Mapping)]
        if not parsed:
            msg = "graph-change proposal must include at least one concept"
            raise ValueError(msg)
        return parsed

    def _parse_graph_change_claims(self, proposal_payload: JSONObject) -> list[JSONObject]:
        return [
            _json_mapping(item)
            for item in _json_sequence(proposal_payload.get("claims"))
            if isinstance(item, Mapping)
        ]

    def _build_claim_plan_step(
        self,
        *,
        position: int,
        claim: JSONObject,
        concept_index: dict[str, JSONObject],
    ) -> JSONObject:
        errors: list[JSONValue] = []
        source_local_id = _json_optional_str(claim.get("source_local_id"))
        target_local_id = _json_optional_str(claim.get("target_local_id"))
        relation_type = _normalize_required_text(
            _json_str(claim.get("relation_type"), field_name="claim.relation_type"),
            field_name="claim.relation_type",
        ).upper()
        source_step = concept_index.get(source_local_id or "")
        target_step = concept_index.get(target_local_id or "")
        if source_step is None:
            errors.append(f"claim[{position}] source_local_id does not resolve")
        if target_step is None:
            errors.append(f"claim[{position}] target_local_id does not resolve")
        evidence_payload = _json_mapping(claim.get("evidence_payload"))
        claim_text = _json_optional_str(claim.get("claim_text"))
        has_evidence = bool(evidence_payload) or claim_text is not None
        try:
            FactAssessment.model_validate(claim.get("assessment"))
        except ValidationError:
            errors.append(f"claim[{position}] requires qualitative assessment")
        source_type = (
            _json_str(source_step.get("entity_type"), field_name="source.entity_type")
            if source_step is not None
            else "UNKNOWN"
        )
        target_type = (
            _json_str(target_step.get("entity_type"), field_name="target.entity_type")
            if target_step is not None
            else "UNKNOWN"
        )
        validation_state: Literal["ALLOWED", "FORBIDDEN", "UNDEFINED"] = "UNDEFINED"
        persistability: Literal["PERSISTABLE", "NON_PERSISTABLE"] = "NON_PERSISTABLE"
        requires_evidence = True
        if source_step is not None and target_step is not None:
            constraints = self._dictionary.get_constraints(
                source_type=source_type,
                relation_type=relation_type,
                include_inactive=False,
            )
            matching_constraint = next(
                (
                    constraint
                    for constraint in constraints
                    if constraint.target_type == target_type
                ),
                None,
            )
            if matching_constraint is None:
                errors.append(
                    f"claim[{position}] has no active relation constraint for "
                    f"{source_type}-{relation_type}-{target_type}",
                )
            elif not matching_constraint.is_allowed:
                validation_state = "FORBIDDEN"
                errors.append(
                    f"claim[{position}] relation is forbidden by active constraints",
                )
            else:
                validation_state = "ALLOWED"
                persistability = "PERSISTABLE"
                requires_evidence = matching_constraint.requires_evidence
        if requires_evidence and not has_evidence:
            errors.append(f"claim[{position}] requires evidence")
            persistability = "NON_PERSISTABLE"
        return {
            "position": position,
            "action": "CREATE_CLAIM",
            "source_local_id": source_local_id,
            "target_local_id": target_local_id,
            "source_type": source_type,
            "target_type": target_type,
            "relation_type": relation_type,
            "validation_state": validation_state,
            "persistability": persistability,
            "requires_evidence": requires_evidence,
            "errors": errors,
        }

    def apply_graph_change_proposal(
        self,
        proposal_id: str,
        *,
        research_space_id: str,
        reviewed_by: str,
        decision_reason: str | None = None,
    ) -> GraphChangeProposal:
        """Apply one graph-change proposal through the normal governed service path."""
        self._apply_graph_change_ai_decision(
            research_space_id=research_space_id,
            target_id=proposal_id,
            action="APPLY_RESOLUTION_PLAN",
            actor=reviewed_by,
            decision_reason=decision_reason
            or "Batch review applied this graph-change proposal.",
        )
        return self.get_graph_change_proposal(proposal_id)

    def _set_graph_change_status(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None,
        status: Literal["CHANGES_REQUESTED", "REJECTED"],
        reviewed_by: str,
        decision_reason: str,
        action: str,
    ) -> GraphChangeProposal:
        model = self._get_graph_change_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Graph-change proposal",
        )
        if model.status not in _REVIEWABLE_GRAPH_CHANGE_STATUSES:
            msg = f"Graph-change proposal '{model.id}' is already {model.status}"
            raise ValueError(msg)
        before = _snapshot_model(model)
        model.status = status
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = _normalize_required_text(
            decision_reason,
            field_name="decision_reason",
        )
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=GraphChangeProposalModel.__tablename__,
            record_id=str(model.id),
            action=action,
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _graph_change_from_model(model)

    def _apply_graph_change_concepts(
        self,
        model: GraphChangeProposalModel,
        *,
        actor: str,
    ) -> list[str]:
        proposal_payload = model.proposal_payload
        concepts = self._parse_graph_change_concepts(proposal_payload)
        concept_member_ids: list[str] = []
        for concept in concepts:
            proposal = self.propose_concept(
                research_space_id=str(model.research_space_id),
                domain_context=_json_str(concept.get("domain_context"), field_name="concept.domain_context"),
                entity_type=_json_str(concept.get("entity_type"), field_name="concept.entity_type"),
                canonical_label=_json_str(
                    concept.get("canonical_label"),
                    field_name="concept.canonical_label",
                ),
                synonyms=[
                    item
                    for item in _json_sequence(concept.get("synonyms"))
                    if isinstance(item, str)
                ],
                external_refs=[
                    _json_mapping(item)
                    for item in _json_sequence(concept.get("external_refs"))
                    if isinstance(item, Mapping)
                ],
                evidence_payload=_json_mapping(concept.get("evidence_payload")),
                rationale=_json_optional_str(concept.get("rationale")),
                proposed_by=actor,
                source_ref=f"graph-change:{model.id}:concept:{_json_str(concept.get('local_id'), field_name='concept.local_id')}",
            )
            if proposal.candidate_decision == "CREATE_NEW":
                applied = self.approve_concept_proposal(
                    proposal.id,
                    research_space_id=str(model.research_space_id),
                    reviewed_by=actor,
                    decision_reason="Applied as part of graph-change proposal.",
                )
                if applied.applied_concept_member_id is not None:
                    concept_member_ids.append(applied.applied_concept_member_id)
            elif proposal.existing_concept_member_id is not None:
                merged = self.merge_concept_proposal(
                    proposal.id,
                    research_space_id=str(model.research_space_id),
                    target_concept_member_id=proposal.existing_concept_member_id,
                    reviewed_by=actor,
                    decision_reason="Merged as part of graph-change proposal.",
                )
                if merged.applied_concept_member_id is not None:
                    concept_member_ids.append(merged.applied_concept_member_id)
        return concept_member_ids

    def _apply_graph_change_claims(
        self,
        model: GraphChangeProposalModel,
        *,
        actor: str,
    ) -> list[str]:
        if self._relation_claim_service is None:
            return []
        proposal_payload = model.proposal_payload
        claims = self._parse_graph_change_claims(proposal_payload)
        claim_ids: list[str] = []
        for position, claim in enumerate(claims):
            source_ref = f"graph-change:{model.id}:claim:{position}"
            existing = self._relation_claim_service.get_by_source_ref(
                research_space_id=str(model.research_space_id),
                source_ref=source_ref,
            )
            if existing is not None:
                claim_ids.append(str(existing.id))
                continue
            created = self._create_graph_change_claim(
                model=model,
                claim=claim,
                source_ref=source_ref,
                actor=actor,
            )
            claim_ids.append(str(created.id))
        return claim_ids

    def _create_graph_change_claim(
        self,
        *,
        model: GraphChangeProposalModel,
        claim: JSONObject,
        source_ref: str,
        actor: str,
    ) -> KernelRelationClaim:
        if self._relation_claim_service is None:
            msg = "Relation claim service is required"
            raise ValueError(msg)
        payload = model.proposal_payload
        concept_index = {
            _json_str(item.get("local_id"), field_name="concept.local_id"): item
            for item in self._parse_graph_change_concepts(payload)
        }
        source = concept_index[
            _json_str(claim.get("source_local_id"), field_name="claim.source_local_id")
        ]
        target = concept_index[
            _json_str(claim.get("target_local_id"), field_name="claim.target_local_id")
        ]
        assessment = FactAssessment.model_validate(claim.get("assessment"))
        derived_confidence = assessment_confidence(assessment)
        confidence_metadata = fact_assessment_metadata(assessment)
        return self._relation_claim_service.create_claim(
            research_space_id=str(model.research_space_id),
            source_document_id=None,
            source_document_ref=_json_optional_str(claim.get("source_document_ref")),
            source_ref=source_ref,
            agent_run_id=actor,
            source_type=_normalize_entity_type(
                _json_str(source.get("entity_type"), field_name="source.entity_type"),
            ),
            relation_type=_normalize_entity_type(
                _json_str(claim.get("relation_type"), field_name="claim.relation_type"),
            ),
            target_type=_normalize_entity_type(
                _json_str(target.get("entity_type"), field_name="target.entity_type"),
            ),
            source_label=_json_str(
                source.get("canonical_label"),
                field_name="source.canonical_label",
            ),
            target_label=_json_str(
                target.get("canonical_label"),
                field_name="target.canonical_label",
            ),
            confidence=derived_confidence,
            validation_state="ALLOWED",
            validation_reason="ai_full_mode:validated_resolution_plan",
            persistability="PERSISTABLE",
            assertion_class="COMPUTATIONAL",
            claim_status="OPEN",
            polarity="SUPPORT",
            claim_text=_json_optional_str(claim.get("claim_text")),
            claim_section=None,
            linked_relation_id=None,
            metadata={
                "origin": "ai_full_mode_graph_change",
                "graph_change_proposal_id": str(model.id),
                "evidence_payload": _json_mapping(claim.get("evidence_payload")),
                **confidence_metadata,
            },
        )
