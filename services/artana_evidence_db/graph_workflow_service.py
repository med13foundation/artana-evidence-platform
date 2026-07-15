"""Unified graph workflow service for product-mode APIs."""

from __future__ import annotations

from typing import NoReturn, cast
from uuid import uuid4

from artana_evidence_db.ai_full_mode_service import AIFullModeService
from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.decision_confidence import (
    DecisionConfidenceAssessment,
    DecisionConfidenceResult,
    score_decision_confidence,
)
from artana_evidence_db.dictionary_proposal_service import DictionaryProposalService
from artana_evidence_db.graph_api_schemas.workflow_schemas import ExplanationResponse
from artana_evidence_db.graph_workflow.actor_context import WorkflowActorContext
from artana_evidence_db.graph_workflow.policy import GraphWorkflowPolicyMixin
from artana_evidence_db.graph_workflow_batch import GraphWorkflowBatchMixin
from artana_evidence_db.graph_workflow_planning import GraphWorkflowPlanningMixin
from artana_evidence_db.graph_workflow_support import (
    WorkflowActionRejected,
    _as_uuid,
    _confidence_assessment_payload,
    _GeneratedResourcesApplication,
    _json_object,
    _json_optional_str,
    _normalize_optional_text,
    _policy_payload,
    _workflow_from_model,
    _workflow_hash,
    stable_workflow_input_hash,
)
from artana_evidence_db.kernel_services import (
    KernelClaimEvidenceService,
    KernelClaimParticipantService,
    KernelEntityService,
    KernelRelationClaimService,
)
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.space_models import GraphSpaceModel
from artana_evidence_db.workflow_models import (
    GraphWorkflow,
    GraphWorkflowAction,
    GraphWorkflowKind,
    GraphWorkflowPolicyOutcome,
    GraphWorkflowRiskTier,
    GraphWorkflowStatus,
)
from artana_evidence_db.workflow_persistence_models import (
    GraphWorkflowEventModel,
    GraphWorkflowModel,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session


def _json_string_list(value: JSONValue | None) -> list[str]:
    """Return string items from a JSON array-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str)]


class GraphWorkflowService(
    GraphWorkflowPolicyMixin,
    GraphWorkflowPlanningMixin,
    GraphWorkflowBatchMixin,
):
    """Application service for unified graph workflows."""

    def __init__(
        self,
        *,
        session: Session,
        entity_service: KernelEntityService,
        relation_claim_service: KernelRelationClaimService,
        claim_participant_service: KernelClaimParticipantService,
        claim_evidence_service: KernelClaimEvidenceService,
        dictionary_service: DictionaryPort,
        dictionary_proposal_service: DictionaryProposalService,
        ai_full_mode_service: AIFullModeService,
    ) -> None:
        self._session = session
        self._entity_service = entity_service
        self._relation_claim_service = relation_claim_service
        self._claim_participant_service = claim_participant_service
        self._claim_evidence_service = claim_evidence_service
        self._dictionary_service = dictionary_service
        self._dictionary_proposal_service = dictionary_proposal_service
        self._ai_full_mode_service = ai_full_mode_service

    def create_workflow(
        self,
        *,
        research_space_id: str,
        kind: GraphWorkflowKind,
        input_payload: JSONObject,
        decision_payload: JSONObject,
        source_ref: str | None,
        created_by: str,
        authenticated_ai_principal: str | None = None,
    ) -> GraphWorkflow:
        """Create or replay one unified graph workflow."""
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_source_ref = _normalize_optional_text(source_ref)
        actor_context = WorkflowActorContext(
            authenticated_user_actor=created_by,
            authenticated_ai_principal=_normalize_optional_text(
                authenticated_ai_principal,
            ),
        )
        effective_decision_payload = {
            **decision_payload,
            "actor_context": actor_context.as_payload(),
        }
        input_payload = _workflow_input_for_authenticated_principal(
            input_payload=input_payload,
            authenticated_ai_principal=authenticated_ai_principal,
        )
        existing = self._get_workflow_by_source_ref(
            research_space_id=normalized_space_id,
            source_ref=normalized_source_ref,
        )
        if existing is not None:
            if existing.kind != kind or existing.input_payload != input_payload:
                msg = "source_ref is already bound to a different workflow"
                raise ValueError(msg)
            return _workflow_from_model(existing)

        mode_config = self.get_operating_mode(normalized_space_id)
        plan = self._build_plan(
            research_space_id=normalized_space_id,
            kind=kind,
            input_payload=input_payload,
            decision_payload=effective_decision_payload,
            source_ref=normalized_source_ref,
            actor=actor_context.effective_actor,
            mode=mode_config.mode,
        )
        model = GraphWorkflowModel(
            id=uuid4(),
            research_space_id=_as_uuid(normalized_space_id),
            kind=kind,
            status=plan.status,
            operating_mode=mode_config.mode,
            input_payload=input_payload,
            plan_payload=plan.plan_payload,
            generated_resources_payload=plan.generated_resources_payload,
            decision_payload=plan.decision_payload,
            policy_payload=plan.policy_payload,
            explanation_payload=plan.explanation_payload,
            source_ref=normalized_source_ref,
            workflow_hash=stable_workflow_input_hash(
                kind=kind,
                operating_mode=mode_config.mode,
                input_payload=input_payload,
                source_ref=normalized_source_ref,
            ),
            created_by=actor_context.effective_actor,
            updated_by=actor_context.effective_actor,
        )
        self._session.add(model)
        self._session.flush()
        model.workflow_hash = _workflow_hash(model)
        self._session.flush()
        self._record_event(
            workflow=model,
            actor=actor_context.effective_actor,
            action="create",
            before_status=None,
            after_status=model.status,
            risk_tier=None,
            confidence=None,
            computed_confidence=None,
            confidence_assessment_payload={},
            confidence_model_version=None,
            input_hash=None,
            policy_outcome_payload=model.policy_payload,
            generated_resources_payload=model.generated_resources_payload,
            reason="Workflow created.",
            event_payload={
                "kind": kind,
                "actor_context": actor_context.as_payload(),
            },
        )
        return _workflow_from_model(model)

    def list_workflows(
        self,
        *,
        research_space_id: str,
        kind: GraphWorkflowKind | None,
        status: GraphWorkflowStatus | None,
        offset: int,
        limit: int,
    ) -> list[GraphWorkflow]:
        """List workflows in one graph space."""
        stmt = (
            select(GraphWorkflowModel)
            .where(GraphWorkflowModel.research_space_id == _as_uuid(research_space_id))
            .order_by(GraphWorkflowModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        if kind is not None:
            stmt = stmt.where(GraphWorkflowModel.kind == kind)
        if status is not None:
            stmt = stmt.where(GraphWorkflowModel.status == status)
        return [
            _workflow_from_model(model) for model in self._session.scalars(stmt).all()
        ]

    def count_workflows(
        self,
        *,
        research_space_id: str,
        kind: GraphWorkflowKind | None,
        status: GraphWorkflowStatus | None,
    ) -> int:
        """Count workflows in one graph space."""
        stmt = (
            select(func.count())
            .select_from(GraphWorkflowModel)
            .where(
                GraphWorkflowModel.research_space_id == _as_uuid(research_space_id),
            )
        )
        if kind is not None:
            stmt = stmt.where(GraphWorkflowModel.kind == kind)
        if status is not None:
            stmt = stmt.where(GraphWorkflowModel.status == status)
        return int(self._session.scalar(stmt) or 0)

    def get_workflow(
        self, *, research_space_id: str, workflow_id: str
    ) -> GraphWorkflow:
        """Return one workflow by ID and space."""
        return _workflow_from_model(
            self._get_workflow_model(
                workflow_id=workflow_id,
                research_space_id=research_space_id,
            ),
        )

    def act_on_workflow(  # noqa: PLR0912, PLR0913, PLR0915
        self,
        *,
        research_space_id: str,
        workflow_id: str,
        action: GraphWorkflowAction,
        actor: str,
        input_hash: str | None,
        risk_tier: GraphWorkflowRiskTier,
        confidence_assessment: DecisionConfidenceAssessment | None,
        reason: str | None,
        decision_payload: JSONObject,
        generated_resources_payload: JSONObject,
        ai_decision_payload: JSONObject | None,
        authenticated_ai_principal: str | None,
    ) -> GraphWorkflow:
        """Apply one governed action to a workflow."""
        model = self._get_workflow_model(
            workflow_id=workflow_id,
            research_space_id=research_space_id,
        )
        before_status = model.status
        if input_hash is not None and input_hash != model.workflow_hash:
            msg = "Workflow action input_hash does not match current workflow_hash"
            self._reject_workflow_action(
                workflow=model,
                actor=actor,
                action=action,
                risk_tier=risk_tier,
                confidence_assessment=confidence_assessment,
                confidence_result=None,
                input_hash=input_hash,
                reason=msg,
                generated_resources_payload=generated_resources_payload,
                decision_payload=decision_payload,
                ai_decision_payload=ai_decision_payload,
            )
        normalized_authenticated_ai_principal = _normalize_optional_text(
            authenticated_ai_principal,
        )
        if (
            normalized_authenticated_ai_principal is not None
            and ai_decision_payload is None
        ):
            self._reject_workflow_action(
                workflow=model,
                actor=actor,
                action=action,
                risk_tier=risk_tier,
                confidence_assessment=confidence_assessment,
                confidence_result=None,
                input_hash=input_hash,
                reason=(
                    "Authenticated AI principals cannot submit manual workflow actions"
                ),
                generated_resources_payload=generated_resources_payload,
                decision_payload=decision_payload,
                ai_decision_payload=None,
            )
        ai_principal = (
            _json_optional_str(ai_decision_payload.get("ai_principal"))
            if ai_decision_payload is not None
            else None
        )
        if ai_decision_payload is not None:
            if normalized_authenticated_ai_principal is None:
                self._reject_workflow_action(
                    workflow=model,
                    actor=actor,
                    action=action,
                    risk_tier=risk_tier,
                    confidence_assessment=confidence_assessment,
                    confidence_result=None,
                    input_hash=input_hash,
                    reason="Authenticated AI principal is required for workflow AI actions",
                    generated_resources_payload=generated_resources_payload,
                    decision_payload=decision_payload,
                    ai_decision_payload=ai_decision_payload,
                )
            if ai_principal != normalized_authenticated_ai_principal:
                self._reject_workflow_action(
                    workflow=model,
                    actor=actor,
                    action=action,
                    risk_tier=risk_tier,
                    confidence_assessment=confidence_assessment,
                    confidence_result=None,
                    input_hash=input_hash,
                    reason=(
                        "Workflow AI principal does not match authenticated "
                        "AI principal"
                    ),
                    generated_resources_payload=generated_resources_payload,
                    decision_payload=decision_payload,
                    ai_decision_payload=ai_decision_payload,
                )
        actor_context = WorkflowActorContext(
            authenticated_user_actor=actor,
            authenticated_ai_principal=normalized_authenticated_ai_principal,
        )
        try:
            confidence_result = self._score_workflow_action_confidence(
                action=action,
                risk_tier=risk_tier,
                ai_decision_payload=ai_decision_payload,
                confidence_assessment=confidence_assessment,
            )
        except ValueError as exc:
            self._reject_workflow_action(
                workflow=model,
                actor=ai_principal or actor,
                action=action,
                risk_tier=risk_tier,
                confidence_assessment=confidence_assessment,
                confidence_result=None,
                input_hash=input_hash,
                reason=str(exc),
                generated_resources_payload=generated_resources_payload,
                decision_payload=decision_payload,
                ai_decision_payload=ai_decision_payload,
            )
        policy = self.evaluate_policy(
            research_space_id=research_space_id,
            kind=cast("GraphWorkflowKind", model.kind),
            action=action,
            risk_tier=risk_tier,
            ai_principal=ai_principal,
            computed_confidence=(
                confidence_result.computed_confidence
                if confidence_result is not None
                else None
            ),
        )
        if confidence_result is not None and confidence_result.blocked:
            msg = "Decision confidence assessment is blocked: " + ", ".join(
                confidence_result.blocking_reasons,
            )
            self._reject_workflow_action(
                workflow=model,
                actor=ai_principal or actor,
                action=action,
                risk_tier=risk_tier,
                confidence_assessment=confidence_assessment,
                confidence_result=confidence_result,
                input_hash=input_hash,
                reason=msg,
                generated_resources_payload=generated_resources_payload,
                decision_payload=decision_payload,
                ai_decision_payload=ai_decision_payload,
                policy=policy,
            )
        if confidence_result is not None and confidence_result.human_review_required:
            msg = "Decision confidence assessment requires human review: " + ", ".join(
                confidence_result.human_review_reasons,
            )
            self._reject_workflow_action(
                workflow=model,
                actor=ai_principal or actor,
                action=action,
                risk_tier=risk_tier,
                confidence_assessment=confidence_assessment,
                confidence_result=confidence_result,
                input_hash=input_hash,
                reason=msg,
                generated_resources_payload=generated_resources_payload,
                decision_payload=decision_payload,
                ai_decision_payload=ai_decision_payload,
                policy=policy,
            )
        if ai_decision_payload is not None and (
            policy.blocked or policy.human_required
        ):
            msg = policy.reason
            self._reject_workflow_action(
                workflow=model,
                actor=ai_principal or actor,
                action=action,
                risk_tier=risk_tier,
                confidence_assessment=confidence_assessment,
                confidence_result=confidence_result,
                input_hash=input_hash,
                reason=msg,
                generated_resources_payload=generated_resources_payload,
                decision_payload=decision_payload,
                ai_decision_payload=ai_decision_payload,
                policy=policy,
            )

        merged_generated = {
            **model.generated_resources_payload,
            **generated_resources_payload,
        }
        try:
            self._assert_generated_resources_in_space(
                research_space_id=research_space_id,
                generated_resources_payload=merged_generated,
            )
        except ValueError as exc:
            self._reject_workflow_action(
                workflow=model,
                actor=ai_principal or actor,
                action=action,
                risk_tier=risk_tier,
                confidence_assessment=confidence_assessment,
                confidence_result=confidence_result,
                input_hash=input_hash,
                reason=str(exc),
                generated_resources_payload=generated_resources_payload,
                decision_payload=decision_payload,
                ai_decision_payload=ai_decision_payload,
                policy=policy,
            )
        confidence_payload = _confidence_assessment_payload(confidence_assessment)
        confidence_result_payload = (
            confidence_result.to_payload() if confidence_result is not None else {}
        )
        model.decision_payload = {
            **model.decision_payload,
            **decision_payload,
            "actor_context": actor_context.as_payload(),
            "confidence_assessment": confidence_payload,
            "confidence_result": confidence_result_payload,
        }
        model.policy_payload = _policy_payload(policy, confidence_result)
        model.updated_by = actor_context.effective_actor

        if action == "reject":
            model.status = "REJECTED"
        elif action == "request_changes":
            model.status = "CHANGES_REQUESTED"
        elif action == "defer_to_human":
            model.status = "WAITING_REVIEW"
        elif action == "split":
            model.status = "CHANGES_REQUESTED"
        elif action == "mark_resolved":
            model.status = "APPLIED"
        elif action in {"apply_plan", "approve"}:
            application = self._apply_generated_resources(
                research_space_id=research_space_id,
                workflow=model,
                actor_context=actor_context,
                confidence_assessment=confidence_assessment,
                risk_tier=risk_tier,
                ai_decision_payload=ai_decision_payload,
            )
            merged_generated = {
                **merged_generated,
                **application.generated_updates,
            }
            model.status = application.status or "APPLIED"
        model.generated_resources_payload = merged_generated
        model.explanation_payload = self._build_workflow_explanation_payload(model)
        self._session.flush()
        model.workflow_hash = _workflow_hash(model)
        self._session.flush()
        self._record_event(
            workflow=model,
            actor=actor_context.effective_actor,
            action=action,
            before_status=before_status,
            after_status=model.status,
            risk_tier=risk_tier,
            confidence=(
                confidence_result.computed_confidence
                if confidence_result is not None
                else None
            ),
            computed_confidence=(
                confidence_result.computed_confidence
                if confidence_result is not None
                else None
            ),
            confidence_assessment_payload=confidence_payload,
            confidence_model_version=(
                confidence_result.confidence_model_version
                if confidence_result is not None
                else None
            ),
            input_hash=input_hash,
            policy_outcome_payload=_policy_payload(policy, confidence_result),
            generated_resources_payload=merged_generated,
            reason=reason,
            event_payload={
                "decision_payload": decision_payload,
                "ai_decision": ai_decision_payload or {},
                "confidence_result": confidence_result_payload,
            },
        )
        return _workflow_from_model(model)

    def explain_resource(
        self,
        *,
        research_space_id: str,
        resource_type: str,
        resource_id: str,
    ) -> ExplanationResponse:
        """Explain why a graph workflow resource exists."""
        normalized_type = resource_type.strip().lower()
        if normalized_type == "workflow":
            workflow = self._get_workflow_model(
                workflow_id=resource_id,
                research_space_id=research_space_id,
            )
            return self._workflow_explanation(workflow)
        if normalized_type in {"claim", "relation_claim"}:
            claim = self._relation_claim_service.get_claim(resource_id)
            if claim is None or str(claim.research_space_id) != str(research_space_id):
                msg = f"Claim '{resource_id}' not found"
                raise ValueError(msg)
            return ExplanationResponse(
                research_space_id=research_space_id,
                resource_type=resource_type,
                resource_id=resource_id,
                why_this_exists="This claim was created as governed graph evidence.",
                approved_by=None,
                evidence={"claim_text": claim.claim_text},
                policy={},
                generated_resources={},
                validation={
                    "validation_state": claim.validation_state,
                    "persistability": claim.persistability,
                },
                next_action={"action": "review_claim"},
                details=cast("JSONObject", claim.model_dump(mode="json")),
            )
        if normalized_type == "graph_change_proposal":
            proposal = self._ai_full_mode_service.get_graph_change_proposal(resource_id)
            if proposal.research_space_id != str(research_space_id):
                msg = f"Graph-change proposal '{resource_id}' not found"
                raise ValueError(msg)
            return ExplanationResponse(
                research_space_id=research_space_id,
                resource_type=resource_type,
                resource_id=resource_id,
                why_this_exists="This proposal records graph repair needed before evidence can be applied.",
                approved_by=proposal.reviewed_by,
                evidence=proposal.proposal_payload,
                policy={},
                generated_resources={
                    "applied_concept_member_ids": proposal.applied_concept_member_ids_payload,
                    "applied_claim_ids": proposal.applied_claim_ids_payload,
                },
                validation=proposal.resolution_plan_payload,
                next_action={
                    "action": "review_graph_change",
                    "status": proposal.status,
                },
                details=cast("JSONObject", proposal.model_dump(mode="json")),
            )
        msg = f"Explanation for resource_type '{resource_type}' is not available"
        raise ValueError(msg)

    def validate_explain(
        self,
        *,
        research_space_id: str,
        validation_payload: JSONObject,
        context_payload: JSONObject,
    ) -> ExplanationResponse:
        """Explain a validation response without mutating graph state."""
        valid = validation_payload.get("valid")
        code = validation_payload.get("code")
        return ExplanationResponse(
            research_space_id=research_space_id,
            resource_type="validation",
            resource_id=str(code or "validation"),
            why_this_exists=(
                "The graph DB validation layer checked dictionary rules, relation "
                "constraints, duplicate claims, and evidence requirements."
            ),
            approved_by=None,
            evidence={"context": context_payload},
            policy={},
            generated_resources={},
            validation=validation_payload,
            next_action={
                "action": "continue" if valid is True else "review_next_actions",
                "next_actions": validation_payload.get("next_actions", []),
            },
            details={"valid": valid, "code": code},
        )

    def _apply_generated_resources(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        workflow: GraphWorkflowModel,
        actor_context: WorkflowActorContext,
        confidence_assessment: DecisionConfidenceAssessment | None,
        risk_tier: GraphWorkflowRiskTier,
        ai_decision_payload: JSONObject | None,
    ) -> _GeneratedResourcesApplication:
        if workflow.kind == "batch_review":
            return self._apply_batch_review_resources(
                research_space_id=research_space_id,
                workflow=workflow,
                actor_context=actor_context,
                confidence_assessment=confidence_assessment,
                ai_decision_payload=ai_decision_payload,
            )

        actor = actor_context.effective_actor
        generated_updates: JSONObject = {}
        graph_change_ids = self._workflow_graph_change_ids(workflow)
        if ai_decision_payload is not None and graph_change_ids:
            self._apply_workflow_graph_change_proposals(
                research_space_id=research_space_id,
                workflow=workflow,
                actor=actor,
                confidence_assessment=confidence_assessment,
                risk_tier=risk_tier,
                ai_decision_payload=ai_decision_payload,
                authenticated_ai_principal=(
                    actor_context.authenticated_ai_principal
                ),
                graph_change_ids=graph_change_ids,
            )
        if workflow.kind == "evidence_approval":
            pending_claim_payload = _json_object(
                workflow.generated_resources_payload.get("pending_claim_request"),
            )
            if pending_claim_payload is not None:
                if not self._pending_generated_resources_resolved(workflow):
                    return _GeneratedResourcesApplication(
                        status="PLAN_READY",
                        generated_updates={
                            "pending_claim_request": pending_claim_payload,
                            "pending_generated_resources": {
                                "dictionary_proposal_ids": workflow.generated_resources_payload.get(
                                    "dictionary_proposal_ids",
                                    [],
                                ),
                                "graph_change_proposal_ids": graph_change_ids,
                            },
                        },
                    )
                claim_plan = self._plan_claim_request(
                    research_space_id=research_space_id,
                    request_payload=pending_claim_payload,
                    actor=actor,
                    source_ref=workflow.source_ref,
                    should_apply=True,
                    authorship_override=(
                        "AGENT"
                        if actor_context.is_ai
                        else None
                    ),
                )
                if claim_plan.get("status") == "APPLIED":
                    generated_updates = cast(
                        "JSONObject",
                        claim_plan["generated_resources_payload"],
                    )
                else:
                    return _GeneratedResourcesApplication(
                        status=cast("GraphWorkflowStatus", claim_plan["status"]),
                        generated_updates={
                            "pending_claim_request": pending_claim_payload,
                            "pending_claim_plan": cast(
                                "JSONObject",
                                claim_plan["plan_payload"],
                            ),
                        },
                    )
        if (
            workflow.kind == "evidence_approval"
            and not workflow.generated_resources_payload
        ):
            claim_payload = _json_object(workflow.input_payload.get("claim_request"))
            if claim_payload is not None:
                claim_plan = self._plan_claim_request(
                    research_space_id=research_space_id,
                    request_payload=claim_payload,
                    actor=actor,
                    source_ref=workflow.source_ref,
                    should_apply=True,
                    authorship_override=(
                        "AGENT"
                        if actor_context.is_ai
                        else None
                    ),
                )
                if claim_plan.get("status") == "APPLIED":
                    generated_updates = cast(
                        "JSONObject",
                        claim_plan["generated_resources_payload"],
                    )
        return _GeneratedResourcesApplication(
            status=None,
            generated_updates=generated_updates,
        )

    def _workflow_graph_change_ids(self, workflow: GraphWorkflowModel) -> list[str]:
        return _json_string_list(
            workflow.generated_resources_payload.get("graph_change_proposal_ids"),
        )

    def _apply_workflow_graph_change_proposals(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        workflow: GraphWorkflowModel,
        actor: str,
        confidence_assessment: DecisionConfidenceAssessment | None,
        risk_tier: GraphWorkflowRiskTier,
        ai_decision_payload: JSONObject,
        authenticated_ai_principal: str | None,
        graph_change_ids: list[str],
    ) -> None:
        for proposal_id in graph_change_ids:
            proposal = self._ai_full_mode_service.get_graph_change_proposal(proposal_id)
            if proposal.status == "APPLIED":
                continue
            self._ai_full_mode_service.submit_ai_decision(
                research_space_id=research_space_id,
                target_type="graph_change_proposal",
                target_id=proposal_id,
                action="APPLY_RESOLUTION_PLAN",
                ai_principal=actor,
                authenticated_ai_principal=authenticated_ai_principal,
                confidence_assessment=confidence_assessment,
                risk_tier=risk_tier,
                input_hash=proposal.proposal_hash,
                evidence_payload={
                    "source": "graph_workflow",
                    "workflow_id": str(workflow.id),
                    "rationale": ai_decision_payload.get("rationale"),
                },
                decision_payload={},
                created_by=actor,
            )

    def _pending_generated_resources_resolved(
        self,
        workflow: GraphWorkflowModel,
    ) -> bool:
        dictionary_ids = _json_string_list(
            workflow.generated_resources_payload.get("dictionary_proposal_ids"),
        )
        for proposal_id in dictionary_ids:
            dictionary_proposal = self._dictionary_proposal_service.get_proposal(
                proposal_id,
            )
            if dictionary_proposal.status not in {"APPROVED", "MERGED"}:
                return False
        for proposal_id in self._workflow_graph_change_ids(workflow):
            graph_proposal = self._ai_full_mode_service.get_graph_change_proposal(
                proposal_id,
            )
            if graph_proposal.status != "APPLIED":
                return False
        return True

    def _score_workflow_action_confidence(
        self,
        *,
        action: GraphWorkflowAction,
        risk_tier: GraphWorkflowRiskTier,
        ai_decision_payload: JSONObject | None,
        confidence_assessment: DecisionConfidenceAssessment | None,
    ) -> DecisionConfidenceResult | None:
        if ai_decision_payload is None:
            return None
        if action in {"approve", "apply_plan"} and confidence_assessment is None:
            msg = "Decision confidence assessment is required for AI approval actions"
            raise ValueError(msg)
        if confidence_assessment is None:
            return None
        if confidence_assessment.risk_tier != risk_tier:
            msg = "Decision confidence assessment risk_tier must match action risk_tier"
            raise ValueError(msg)
        return score_decision_confidence(confidence_assessment)

    def _assert_generated_resources_in_space(
        self,
        *,
        research_space_id: str,
        generated_resources_payload: JSONObject,
    ) -> None:
        graph_change_ids = _json_string_list(
            generated_resources_payload.get("graph_change_proposal_ids"),
        )
        for proposal_id in graph_change_ids:
            graph_proposal = self._ai_full_mode_service.get_graph_change_proposal(
                proposal_id,
            )
            if graph_proposal.research_space_id != str(research_space_id):
                msg = f"Generated graph-change proposal '{proposal_id}' is not in this space"
                raise ValueError(msg)
        concept_ids = _json_string_list(
            generated_resources_payload.get("concept_proposal_ids"),
        )
        for proposal_id in concept_ids:
            concept_proposal = self._ai_full_mode_service.get_concept_proposal(
                proposal_id,
            )
            if concept_proposal.research_space_id != str(research_space_id):
                msg = f"Generated concept proposal '{proposal_id}' is not in this space"
                raise ValueError(msg)
        connector_ids = _json_string_list(
            generated_resources_payload.get("connector_proposal_ids"),
        )
        for proposal_id in connector_ids:
            connector_proposal = self._ai_full_mode_service.get_connector_proposal(
                proposal_id,
            )
            if connector_proposal.research_space_id != str(research_space_id):
                msg = (
                    f"Generated connector proposal '{proposal_id}' is not in this space"
                )
                raise ValueError(msg)
        claim_ids = _json_string_list(generated_resources_payload.get("claim_ids"))
        for claim_id in claim_ids:
            claim = self._relation_claim_service.get_claim(claim_id)
            if claim is None or str(claim.research_space_id) != str(research_space_id):
                msg = f"Generated claim '{claim_id}' is not in this space"
                raise ValueError(msg)

    def _get_space_model(self, research_space_id: str) -> GraphSpaceModel:
        space = self._session.get(GraphSpaceModel, _as_uuid(research_space_id))
        if space is None:
            msg = f"Graph space '{research_space_id}' not found"
            raise ValueError(msg)
        return space

    def _get_workflow_model(
        self,
        *,
        workflow_id: str,
        research_space_id: str,
    ) -> GraphWorkflowModel:
        model = self._session.get(GraphWorkflowModel, _as_uuid(workflow_id))
        if model is None or str(model.research_space_id) != str(research_space_id):
            msg = f"Graph workflow '{workflow_id}' not found"
            raise ValueError(msg)
        return model

    def _get_workflow_by_source_ref(
        self,
        *,
        research_space_id: str,
        source_ref: str | None,
    ) -> GraphWorkflowModel | None:
        if source_ref is None:
            return None
        stmt = select(GraphWorkflowModel).where(
            GraphWorkflowModel.research_space_id == _as_uuid(research_space_id),
            GraphWorkflowModel.source_ref == source_ref,
        )
        return self._session.scalars(stmt).first()

    def _record_event(  # noqa: PLR0913
        self,
        *,
        workflow: GraphWorkflowModel,
        actor: str,
        action: str,
        before_status: str | None,
        after_status: str,
        risk_tier: GraphWorkflowRiskTier | None,
        confidence: float | None,
        computed_confidence: float | None,
        confidence_assessment_payload: JSONObject,
        confidence_model_version: str | None,
        input_hash: str | None,
        policy_outcome_payload: JSONObject,
        generated_resources_payload: JSONObject,
        reason: str | None,
        event_payload: JSONObject,
    ) -> None:
        self._session.add(
            GraphWorkflowEventModel(
                id=uuid4(),
                workflow_id=workflow.id,
                research_space_id=workflow.research_space_id,
                actor=actor,
                action=action,
                before_status=before_status,
                after_status=after_status,
                risk_tier=risk_tier,
                confidence=confidence,
                computed_confidence=computed_confidence,
                confidence_assessment_payload=confidence_assessment_payload,
                confidence_model_version=confidence_model_version,
                input_hash=input_hash,
                policy_outcome_payload=policy_outcome_payload,
                generated_resources_payload=generated_resources_payload,
                reason=reason,
                event_payload=event_payload,
            ),
        )
        self._session.flush()

    def _reject_workflow_action(  # noqa: PLR0913
        self,
        *,
        workflow: GraphWorkflowModel,
        actor: str,
        action: GraphWorkflowAction,
        risk_tier: GraphWorkflowRiskTier,
        confidence_assessment: DecisionConfidenceAssessment | None,
        confidence_result: DecisionConfidenceResult | None,
        input_hash: str | None,
        reason: str,
        generated_resources_payload: JSONObject,
        decision_payload: JSONObject,
        ai_decision_payload: JSONObject | None,
        policy: GraphWorkflowPolicyOutcome | None = None,
    ) -> NoReturn:
        confidence_payload = _confidence_assessment_payload(confidence_assessment)
        confidence_result_payload = (
            confidence_result.to_payload() if confidence_result is not None else {}
        )
        if policy is None:
            human_required = "human review" in reason.lower()
            policy = GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=human_required,
                blocked=not human_required,
                outcome="human_required" if human_required else "blocked",
                reason=reason,
            )
        self._record_event(
            workflow=workflow,
            actor=actor,
            action=action,
            before_status=workflow.status,
            after_status=workflow.status,
            risk_tier=risk_tier,
            confidence=(
                confidence_result.computed_confidence
                if confidence_result is not None
                else None
            ),
            computed_confidence=(
                confidence_result.computed_confidence
                if confidence_result is not None
                else None
            ),
            confidence_assessment_payload=confidence_payload,
            confidence_model_version=(
                confidence_result.confidence_model_version
                if confidence_result is not None
                else None
            ),
            input_hash=input_hash,
            policy_outcome_payload=_policy_payload(policy, confidence_result),
            generated_resources_payload={
                **workflow.generated_resources_payload,
                "attempted": generated_resources_payload,
            },
            reason=reason,
            event_payload={
                "rejected": True,
                "decision_payload": decision_payload,
                "ai_decision": ai_decision_payload or {},
                "confidence_result": confidence_result_payload,
            },
        )
        raise WorkflowActionRejected(reason)

    def _build_workflow_explanation_payload(
        self,
        model: GraphWorkflowModel,
    ) -> JSONObject:
        return {
            "why_this_exists": (
                model.explanation_payload.get("why_this_exists")
                or f"Workflow '{model.kind}' records a governed graph decision."
            ),
            "approved_by": model.updated_by if model.status == "APPLIED" else None,
            "policy": model.policy_payload,
            "generated_resources": model.generated_resources_payload,
            "next_action": model.explanation_payload.get("next_action"),
        }

    def _workflow_explanation(self, model: GraphWorkflowModel) -> ExplanationResponse:
        payload = self._build_workflow_explanation_payload(model)
        return ExplanationResponse(
            research_space_id=str(model.research_space_id),
            resource_type="workflow",
            resource_id=str(model.id),
            why_this_exists=str(payload["why_this_exists"]),
            approved_by=_json_optional_str(payload.get("approved_by")),
            evidence=model.input_payload,
            policy=model.policy_payload,
            generated_resources=model.generated_resources_payload,
            validation=_json_object(model.plan_payload.get("validation")) or {},
            next_action={"action": payload.get("next_action") or "inspect_workflow"},
            details={
                "kind": model.kind,
                "status": model.status,
                "workflow_hash": model.workflow_hash,
            },
        )

def _workflow_input_for_authenticated_principal(
    *,
    input_payload: JSONObject,
    authenticated_ai_principal: str | None,
) -> JSONObject:
    """Make server-owned AI authorship explicit before planning or replay."""

    principal = _normalize_optional_text(authenticated_ai_principal)
    claim_request = _json_object(input_payload.get("claim_request"))
    if principal is None or claim_request is None:
        return input_payload
    effective_claim_request = {
        **claim_request,
        "authorship": "AGENT",
    }
    if (
        _normalize_optional_text(
            _json_optional_str(effective_claim_request.get("agent_run_id")),
        )
        is None
    ):
        effective_claim_request["agent_run_id"] = principal
    return {
        **input_payload,
        "claim_request": effective_claim_request,
    }


__all__ = ["GraphWorkflowService", "stable_workflow_input_hash"]
