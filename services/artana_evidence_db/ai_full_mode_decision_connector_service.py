# mypy: disable-error-code="attr-defined,no-any-return"
"""AI decision and connector proposal workflows for AI Full Mode."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import uuid4

from artana_evidence_db.ai_full_mode_models import (
    AIDecision,
    AIDecisionAction,
    AIDecisionRiskTier,
    AIPolicyOutcome,
    ConnectorProposal,
    ConnectorProposalStatus,
)
from artana_evidence_db.ai_full_mode_persistence_models import (
    AIDecisionModel,
    ConnectorProposalModel,
    GraphChangeProposalModel,
)
from artana_evidence_db.ai_full_mode_support import (
    _DEFAULT_MIN_AI_CONFIDENCE,
    _REVIEWABLE_CONNECTOR_STATUSES,
    _REVIEWABLE_GRAPH_CHANGE_STATUSES,
    _ai_decision_from_model,
    _as_uuid,
    _connector_from_model,
    _json_mapping,
    _json_optional_str,
    _json_sequence,
    _json_str,
    _manual_actor,
    _normalize_domain_context,
    _normalize_label,
    _normalize_optional_text,
    _normalize_required_text,
    _normalize_slug,
    _proposal_hash,
    _snapshot_model,
)
from artana_evidence_db.common_types import AIFullModeSettings, JSONObject, JSONValue
from artana_evidence_db.decision_confidence import (
    DecisionConfidenceAssessment,
    decision_confidence_assessment_payload,
    score_decision_confidence,
)
from artana_evidence_db.kernel_dictionary_models import DictionaryChangelogModel
from artana_evidence_db.space_models import GraphSpaceModel
from sqlalchemy import select


class AIFullModeDecisionConnectorMixin:
    """AI decision envelope and connector governance behavior."""

    def submit_ai_decision(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        target_type: Literal["concept_proposal", "graph_change_proposal"],
        target_id: str,
        action: AIDecisionAction,
        ai_principal: str,
        authenticated_ai_principal: str | None,
        confidence_assessment: DecisionConfidenceAssessment | None,
        risk_tier: AIDecisionRiskTier,
        input_hash: str,
        evidence_payload: JSONObject,
        decision_payload: JSONObject,
        created_by: str,
    ) -> AIDecision:
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_principal = _normalize_required_text(
            ai_principal,
            field_name="ai_principal",
        )
        settings = self._get_ai_full_mode_settings(normalized_space_id)
        if confidence_assessment is None:
            msg = "Decision confidence assessment is required for AI decisions"
            raise ValueError(msg)
        if confidence_assessment.risk_tier != risk_tier:
            msg = "Decision confidence assessment risk_tier must match decision risk_tier"
            raise ValueError(msg)
        confidence_result = score_decision_confidence(confidence_assessment)
        computed_confidence = confidence_result.computed_confidence
        confidence_payload = decision_confidence_assessment_payload(
            confidence_assessment,
        )
        confidence_result_payload = confidence_result.to_payload()
        rejection_reason = self._validate_ai_decision_envelope(
            settings=settings,
            research_space_id=normalized_space_id,
            target_type=target_type,
            target_id=target_id,
            action=action,
            ai_principal=normalized_principal,
            authenticated_ai_principal=authenticated_ai_principal,
            computed_confidence=computed_confidence,
            confidence_blocking_reasons=confidence_result.blocking_reasons,
            confidence_human_review_reasons=confidence_result.human_review_reasons,
            risk_tier=risk_tier,
            input_hash=input_hash,
            evidence_payload=evidence_payload,
        )
        policy_outcome = self._policy_outcome(
            settings=settings,
            risk_tier=risk_tier,
            rejection_reason=rejection_reason,
        )
        model = AIDecisionModel(
            id=uuid4(),
            research_space_id=_as_uuid(normalized_space_id),
            target_type=target_type,
            target_id=_as_uuid(target_id),
            action=action,
            status="REJECTED" if rejection_reason is not None else "SUBMITTED",
            ai_principal=normalized_principal,
            confidence=computed_confidence,
            computed_confidence=computed_confidence,
            confidence_assessment_payload=confidence_payload,
            confidence_model_version=confidence_result.confidence_model_version,
            risk_tier=risk_tier,
            input_hash=input_hash,
            policy_outcome=policy_outcome,
            evidence_payload=evidence_payload,
            decision_payload={
                **decision_payload,
                "confidence_result": confidence_result_payload,
            },
            rejection_reason=rejection_reason,
            created_by=_manual_actor(created_by),
        )
        self._session.add(model)
        self._session.flush()
        if rejection_reason is not None:
            self._record_ai_decision(model)
            raise ValueError(rejection_reason)

        if target_type == "concept_proposal":
            self._apply_concept_ai_decision(
                research_space_id=normalized_space_id,
                target_id=target_id,
                action=action,
                decision_payload=decision_payload,
                actor=normalized_principal,
            )
        else:
            self._apply_graph_change_ai_decision(
                research_space_id=normalized_space_id,
                target_id=target_id,
                action=action,
                actor=normalized_principal,
                decision_reason="AI Full Mode applied this graph-change proposal.",
            )
        model.status = "APPLIED"
        model.applied_at = datetime.now(UTC)
        self._session.flush()
        self._record_ai_decision(model)
        return _ai_decision_from_model(model)

    def list_ai_decisions(
        self,
        *,
        research_space_id: str,
        target_type: Literal["concept_proposal", "graph_change_proposal"] | None = None,
        target_id: str | None = None,
    ) -> list[AIDecision]:
        stmt = select(AIDecisionModel).where(
            AIDecisionModel.research_space_id == _as_uuid(research_space_id),
        )
        if target_type is not None:
            stmt = stmt.where(AIDecisionModel.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(AIDecisionModel.target_id == _as_uuid(target_id))
        stmt = stmt.order_by(AIDecisionModel.created_at.desc())
        return [_ai_decision_from_model(model) for model in self._session.scalars(stmt).all()]

    def propose_connector(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        connector_slug: str,
        display_name: str,
        connector_kind: str,
        domain_context: str,
        metadata_payload: JSONObject,
        mapping_payload: JSONObject,
        rationale: str | None,
        evidence_payload: JSONObject,
        proposed_by: str,
        source_ref: str | None,
    ) -> ConnectorProposal:
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_slug = _normalize_slug(connector_slug)
        normalized_domain = _normalize_domain_context(domain_context)
        validation_payload = self._validate_connector_mapping(
            domain_context=normalized_domain,
            mapping_payload=mapping_payload,
        )
        model = ConnectorProposalModel(
            id=uuid4(),
            research_space_id=_as_uuid(normalized_space_id),
            status="SUBMITTED",
            connector_slug=normalized_slug,
            display_name=_normalize_label(display_name),
            connector_kind=_normalize_required_text(
                connector_kind,
                field_name="connector_kind",
            ),
            domain_context=normalized_domain,
            metadata_payload=metadata_payload,
            mapping_payload=mapping_payload,
            validation_payload=validation_payload,
            approval_payload={},
            rationale=_normalize_optional_text(rationale),
            evidence_payload=evidence_payload,
            proposed_by=_manual_actor(proposed_by),
            source_ref=_normalize_optional_text(source_ref),
        )
        self._session.add(model)
        self._session.flush()
        self._record_change(
            table_name=ConnectorProposalModel.__tablename__,
            record_id=str(model.id),
            action="CREATE",
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=model.proposed_by,
            source_ref=model.source_ref,
        )
        return _connector_from_model(model)

    def approve_connector(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str | None,
    ) -> ConnectorProposal:
        return self._set_connector_status(
            proposal_id,
            research_space_id=research_space_id,
            status="APPROVED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="APPROVE",
        )

    def reject_connector(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> ConnectorProposal:
        return self._set_connector_status(
            proposal_id,
            research_space_id=research_space_id,
            status="REJECTED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="REJECT",
        )

    def request_connector_changes(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None = None,
        reviewed_by: str,
        decision_reason: str,
    ) -> ConnectorProposal:
        return self._set_connector_status(
            proposal_id,
            research_space_id=research_space_id,
            status="CHANGES_REQUESTED",
            reviewed_by=reviewed_by,
            decision_reason=decision_reason,
            action="REQUEST_CHANGES",
        )

    def get_connector_proposal(self, proposal_id: str) -> ConnectorProposal:
        return _connector_from_model(self._get_connector_model(proposal_id))

    def list_connector_proposals(
        self,
        *,
        research_space_id: str,
        status: ConnectorProposalStatus | None = None,
    ) -> list[ConnectorProposal]:
        stmt = select(ConnectorProposalModel).where(
            ConnectorProposalModel.research_space_id == _as_uuid(research_space_id),
        )
        if status is not None:
            stmt = stmt.where(ConnectorProposalModel.status == status)
        stmt = stmt.order_by(ConnectorProposalModel.created_at.desc())
        return [_connector_from_model(model) for model in self._session.scalars(stmt).all()]

    def _get_ai_full_mode_settings(self, research_space_id: str) -> AIFullModeSettings:
        space = self._session.get(GraphSpaceModel, _as_uuid(research_space_id))
        if space is None:
            return {}
        settings = space.settings
        ai_settings = settings.get("ai_full_mode")
        if isinstance(ai_settings, Mapping):
            return cast("AIFullModeSettings", dict(ai_settings))
        return {}

    def _validate_ai_decision_envelope(  # noqa: PLR0911, PLR0913
        self,
        *,
        settings: AIFullModeSettings,
        research_space_id: str,
        target_type: Literal["concept_proposal", "graph_change_proposal"],
        target_id: str,
        action: AIDecisionAction,
        ai_principal: str,
        authenticated_ai_principal: str | None,
        computed_confidence: float,
        confidence_blocking_reasons: list[str],
        confidence_human_review_reasons: list[str],
        risk_tier: AIDecisionRiskTier,
        input_hash: str,
        evidence_payload: JSONObject,
    ) -> str | None:
        expected_hash = self._target_hash(
            research_space_id=research_space_id,
            target_type=target_type,
            target_id=target_id,
        )
        trusted = settings.get("trusted_principals", [])
        normalized_authenticated = _normalize_optional_text(authenticated_ai_principal)
        if normalized_authenticated is None:
            return "Authenticated AI principal is required for AI decisions"
        if normalized_authenticated != ai_principal:
            return "AI decision principal does not match authenticated AI principal"
        if ai_principal not in trusted:
            return "AI principal is not trusted for this graph space"
        if not evidence_payload:
            return "AI decision evidence_payload is required"
        if confidence_blocking_reasons:
            return "AI decision confidence assessment is blocked: " + ", ".join(
                confidence_blocking_reasons,
            )
        if confidence_human_review_reasons:
            return "AI decision confidence assessment requires human review: " + ", ".join(
                confidence_human_review_reasons,
            )
        if computed_confidence < float(
            settings.get("min_confidence", _DEFAULT_MIN_AI_CONFIDENCE),
        ):
            return (
                "AI decision computed confidence is below policy threshold; "
                "human review required"
            )
        if input_hash != expected_hash:
            return "AI decision input_hash does not match current proposal snapshot"
        mode = settings.get("governance_mode", "human_review")
        if mode != "ai_full":
            return "AI Full Mode is not enabled for this graph space"
        if risk_tier == "high" and not bool(settings.get("allow_high_risk_actions", False)):
            return "High-risk AI decisions require human review"
        if target_type == "concept_proposal" and action not in {"APPROVE", "MERGE", "REJECT"}:
            return "Unsupported AI action for concept proposal"
        if target_type == "graph_change_proposal" and action != "APPLY_RESOLUTION_PLAN":
            return "Unsupported AI action for graph-change proposal"
        return None

    def _policy_outcome(
        self,
        *,
        settings: AIFullModeSettings,
        risk_tier: AIDecisionRiskTier,
        rejection_reason: str | None,
    ) -> AIPolicyOutcome:
        if rejection_reason is not None:
            if "human review" in rejection_reason or "not enabled" in rejection_reason:
                return "human_required"
            return "blocked"
        if risk_tier == "low":
            return "ai_allowed_when_low_risk"
        if bool(settings.get("allow_high_risk_actions", False)):
            return "ai_allowed"
        return "human_required"

    def _target_hash(
        self,
        *,
        research_space_id: str,
        target_type: Literal["concept_proposal", "graph_change_proposal"],
        target_id: str,
    ) -> str:
        if target_type == "concept_proposal":
            concept_model = self._get_concept_model(target_id)
            self._assert_model_in_space(
                concept_model,
                research_space_id=research_space_id,
                resource_name="AI decision target",
            )
            return concept_model.proposal_hash
        graph_model = self._get_graph_change_model(target_id)
        self._assert_model_in_space(
            graph_model,
            research_space_id=research_space_id,
            resource_name="AI decision target",
        )
        return graph_model.proposal_hash

    def _apply_concept_ai_decision(
        self,
        *,
        research_space_id: str,
        target_id: str,
        action: AIDecisionAction,
        decision_payload: JSONObject,
        actor: str,
    ) -> None:
        if action == "APPROVE":
            self.approve_concept_proposal(
                target_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason="AI Full Mode approved this concept proposal.",
            )
            return
        if action == "MERGE":
            target_member_id = _json_str(
                decision_payload.get("target_concept_member_id"),
                field_name="target_concept_member_id",
            )
            self.merge_concept_proposal(
                target_id,
                research_space_id=research_space_id,
                target_concept_member_id=target_member_id,
                reviewed_by=actor,
                decision_reason="AI Full Mode merged this concept proposal.",
            )
            return
        if action == "REJECT":
            self.reject_concept_proposal(
                target_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason="AI Full Mode rejected this concept proposal.",
            )
            return
        msg = "Unsupported AI concept action"
        raise ValueError(msg)

    def _apply_graph_change_ai_decision(
        self,
        *,
        research_space_id: str,
        target_id: str,
        action: AIDecisionAction,
        actor: str,
        decision_reason: str,
    ) -> None:
        if action != "APPLY_RESOLUTION_PLAN":
            msg = "Unsupported AI graph-change action"
            raise ValueError(msg)
        if self._relation_claim_service is None:
            msg = "Relation claim service is required to apply graph-change proposals"
            raise ValueError(msg)
        model = self._get_graph_change_model(target_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Graph-change proposal",
        )
        if model.status == "APPLIED":
            return
        if model.status not in _REVIEWABLE_GRAPH_CHANGE_STATUSES:
            msg = f"Graph-change proposal '{model.id}' is already {model.status}"
            raise ValueError(msg)
        before = _snapshot_model(model)
        concept_ids = self._apply_graph_change_concepts(model, actor=actor)
        claim_ids = self._apply_graph_change_claims(model, actor=actor)
        model.status = "APPLIED"
        model.applied_concept_member_ids_payload = concept_ids
        model.applied_claim_ids_payload = claim_ids
        model.reviewed_by = actor
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = decision_reason
        model.proposal_hash = _proposal_hash(model)
        self._session.flush()
        self._record_change(
            table_name=GraphChangeProposalModel.__tablename__,
            record_id=str(model.id),
            action="APPLY",
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=actor,
            source_ref=model.source_ref,
        )

    def _record_ai_decision(self, model: AIDecisionModel) -> None:
        self._record_change(
            table_name=AIDecisionModel.__tablename__,
            record_id=str(model.id),
            action=model.status,
            before_snapshot=None,
            after_snapshot=_snapshot_model(model),
            changed_by=model.created_by,
            source_ref=f"ai-decision:{model.target_type}:{model.target_id}",
        )

    def _validate_connector_mapping(
        self,
        *,
        domain_context: str,
        mapping_payload: JSONObject,
    ) -> JSONObject:
        errors: list[JSONValue] = []
        mappings = _json_sequence(mapping_payload.get("field_mappings"))
        for index, raw_mapping in enumerate(mappings):
            mapping = _json_mapping(raw_mapping)
            dimension = _json_optional_str(mapping.get("target_dimension"))
            target_id = _json_optional_str(mapping.get("target_id"))
            if dimension is None or target_id is None:
                errors.append(f"field_mappings[{index}] needs target_dimension and target_id")
                continue
            normalized_dimension = dimension.lower()
            if normalized_dimension == "entity_type":
                entity_type = self._dictionary.get_entity_type(
                    target_id,
                    include_inactive=False,
                )
                if entity_type is None or entity_type.domain_context != domain_context:
                    errors.append(f"field_mappings[{index}] entity_type is not active in domain")
            elif normalized_dimension == "relation_type":
                relation_type = self._dictionary.get_relation_type(
                    target_id,
                    include_inactive=False,
                )
                if relation_type is None or relation_type.domain_context != domain_context:
                    errors.append(f"field_mappings[{index}] relation_type is not active in domain")
            elif normalized_dimension == "variable":
                variable = self._dictionary.get_variable(target_id)
                if variable is None or variable.domain_context != domain_context:
                    errors.append(f"field_mappings[{index}] variable is not active in domain")
            else:
                errors.append(f"field_mappings[{index}] target_dimension is unsupported")
        return {"valid": not errors, "errors": errors, "execution_enabled": False}

    def _set_connector_status(
        self,
        proposal_id: str,
        *,
        research_space_id: str | None,
        status: ConnectorProposalStatus,
        reviewed_by: str,
        decision_reason: str | None,
        action: str,
    ) -> ConnectorProposal:
        model = self._get_connector_model(proposal_id)
        self._assert_model_in_space(
            model,
            research_space_id=research_space_id,
            resource_name="Connector proposal",
        )
        if model.status not in _REVIEWABLE_CONNECTOR_STATUSES:
            msg = f"Connector proposal '{model.id}' is already {model.status}"
            raise ValueError(msg)
        before = _snapshot_model(model)
        if status == "APPROVED" and not bool(model.validation_payload.get("valid", False)):
            msg = "Connector proposal mappings must be valid before approval"
            raise ValueError(msg)
        model.status = status
        model.reviewed_by = _manual_actor(reviewed_by)
        model.reviewed_at = datetime.now(UTC)
        model.decision_reason = _normalize_optional_text(decision_reason)
        model.approval_payload = {
            "approved_metadata_only": status == "APPROVED",
            "connector_runtime_executed": False,
        }
        self._session.flush()
        self._record_change(
            table_name=ConnectorProposalModel.__tablename__,
            record_id=str(model.id),
            action=action,
            before_snapshot=before,
            after_snapshot=_snapshot_model(model),
            changed_by=model.reviewed_by,
            source_ref=model.source_ref,
        )
        return _connector_from_model(model)

    def _record_change(
        self,
        *,
        table_name: str,
        record_id: str,
        action: str,
        before_snapshot: JSONObject | None,
        after_snapshot: JSONObject,
        changed_by: str | None,
        source_ref: str | None,
    ) -> None:
        self._session.add(
            DictionaryChangelogModel(
                table_name=table_name,
                record_id=record_id,
                action=action,
                before_snapshot=before_snapshot,
                after_snapshot=after_snapshot,
                changed_by=changed_by,
                source_ref=source_ref,
            ),
        )
        self._session.flush()

