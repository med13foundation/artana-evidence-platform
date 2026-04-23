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
from artana_evidence_db.dictionary_models import DictionaryProposal
from artana_evidence_db.dictionary_proposal_service import DictionaryProposalService
from artana_evidence_db.fact_assessment_support import fact_assessment_metadata
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationClaimCreateRequest,
)
from artana_evidence_db.graph_api_schemas.workflow_schemas import ExplanationResponse
from artana_evidence_db.graph_validation_service import GraphValidationService
from artana_evidence_db.graph_workflow_batch import GraphWorkflowBatchMixin
from artana_evidence_db.graph_workflow_support import (
    _AI_EVIDENCE_MODES,
    _AI_GRAPH_MODES,
    _AUTO_CLAIM_MODES,
    _CLAIM_VALIDATION_STATE_MAP,
    _SUPPORTED_WORKFLOW_ACTIONS,
    _SUPPORTED_WORKFLOW_KINDS,
    WorkflowActionRejected,
    _as_uuid,
    _confidence_assessment_from_payload,
    _confidence_assessment_payload,
    _GeneratedResourcesApplication,
    _json_bool,
    _json_object,
    _json_object_list,
    _json_optional_str,
    _json_str,
    _normalize_optional_text,
    _normalize_sentence_confidence,
    _normalize_sentence_source,
    _policy_payload,
    _workflow_from_model,
    _workflow_hash,
    _WorkflowPlan,
    stable_workflow_input_hash,
)
from artana_evidence_db.kernel_services import (
    KernelClaimEvidenceService,
    KernelClaimParticipantService,
    KernelEntityService,
    KernelRelationClaimService,
)
from artana_evidence_db.relation_claim_models import (
    RelationClaimPersistability,
)
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.space_models import GraphSpaceModel
from artana_evidence_db.workflow_models import (
    GraphOperatingMode,
    GraphOperatingModeConfig,
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
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session


class GraphWorkflowService(GraphWorkflowBatchMixin):
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

    def get_operating_mode(self, research_space_id: str) -> GraphOperatingModeConfig:
        """Return the configured operating mode, defaulting safely to manual."""
        space = self._get_space_model(research_space_id)
        raw_settings = space.settings if isinstance(space.settings, dict) else {}
        raw_operating_mode = raw_settings.get("operating_mode")
        if raw_operating_mode is None:
            return GraphOperatingModeConfig()
        try:
            return GraphOperatingModeConfig.model_validate(raw_operating_mode)
        except ValidationError as exc:
            msg = "Stored operating_mode settings are invalid"
            raise ValueError(msg) from exc

    def update_operating_mode(
        self,
        *,
        research_space_id: str,
        mode: GraphOperatingMode,
        workflow_policy: JSONObject,
    ) -> GraphOperatingModeConfig:
        """Persist one operating mode under graph_spaces.settings."""
        space = self._get_space_model(research_space_id)
        config = GraphOperatingModeConfig.model_validate(
            {"mode": mode, "workflow_policy": workflow_policy},
        )
        settings = dict(space.settings) if isinstance(space.settings, dict) else {}
        settings["operating_mode"] = config.model_dump(mode="json")
        settings["ai_full_mode"] = self._compatible_ai_full_mode_settings(
            config=config,
            current=_json_object(cast("JSONValue", settings.get("ai_full_mode"))),
        )
        space.settings = settings
        self._session.flush()
        return config

    def capabilities(self, research_space_id: str) -> JSONObject:
        """Return product capabilities for the active operating mode."""
        config = self.get_operating_mode(research_space_id)
        policy = config.workflow_policy
        ai_graph = policy.allow_ai_graph_repair or config.mode in _AI_GRAPH_MODES
        ai_evidence = (
            policy.allow_ai_evidence_decisions or config.mode in _AI_EVIDENCE_MODES
        )
        return {
            "mode": config.mode,
            "workflow_pattern": "create workflow -> inspect workflow -> take action -> explain result",
            "supported_workflow_kinds": list(_SUPPORTED_WORKFLOW_KINDS),
            "supported_actions": list(_SUPPORTED_WORKFLOW_ACTIONS),
            "ai_graph_repair_allowed": ai_graph,
            "ai_evidence_decisions_allowed": ai_evidence,
            "batch_auto_apply_low_risk": policy.batch_auto_apply_low_risk,
            "human_review_required_by_default": config.mode
            in {"manual", "ai_assist_human_batch"},
        }

    def evaluate_policy(  # noqa: PLR0911
        self,
        *,
        research_space_id: str,
        kind: GraphWorkflowKind,
        action: GraphWorkflowAction | None,
        risk_tier: GraphWorkflowRiskTier,
        ai_principal: str | None,
        computed_confidence: float | None,
    ) -> GraphWorkflowPolicyOutcome:
        """Evaluate one workflow action against the active operating mode."""
        config = self.get_operating_mode(research_space_id)
        policy = config.workflow_policy
        ai_graph_allowed = policy.allow_ai_graph_repair or config.mode in _AI_GRAPH_MODES
        ai_evidence_allowed = (
            policy.allow_ai_evidence_decisions or config.mode in _AI_EVIDENCE_MODES
        )
        if ai_principal is None:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason="No AI decision envelope was supplied; human action is required.",
            )
        if ai_principal not in policy.trusted_ai_principals:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=False,
                blocked=True,
                outcome="blocked",
                reason="AI principal is not trusted for this graph space.",
            )
        if computed_confidence is None:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=False,
                blocked=True,
                outcome="blocked",
                reason="Decision confidence assessment is required for AI authority.",
            )
        if computed_confidence < policy.min_ai_confidence:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason="Computed confidence is below operating-mode policy.",
            )
        if kind == "ai_evidence_decision" and not ai_evidence_allowed:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason="AI evidence decisions are not enabled for this space.",
            )
        if action in {"apply_plan", "approve"} and not ai_graph_allowed:
            return GraphWorkflowPolicyOutcome(
                ai_allowed=False,
                ai_allowed_when_low_risk=False,
                human_required=True,
                blocked=False,
                outcome="human_required",
                reason="AI graph repair is not enabled for this space.",
            )
        if risk_tier == "low":
            return GraphWorkflowPolicyOutcome(
                ai_allowed=True,
                ai_allowed_when_low_risk=True,
                human_required=False,
                blocked=False,
                outcome="ai_allowed_when_low_risk",
                reason="Trusted low-risk AI action is allowed by operating mode.",
            )
        return GraphWorkflowPolicyOutcome(
            ai_allowed=False,
            ai_allowed_when_low_risk=False,
            human_required=True,
            blocked=False,
            outcome="human_required",
            reason="Medium and high-risk AI actions require human review.",
        )

    def create_workflow(
        self,
        *,
        research_space_id: str,
        kind: GraphWorkflowKind,
        input_payload: JSONObject,
        decision_payload: JSONObject,
        source_ref: str | None,
        created_by: str,
    ) -> GraphWorkflow:
        """Create or replay one unified graph workflow."""
        normalized_space_id = str(_as_uuid(research_space_id))
        normalized_source_ref = _normalize_optional_text(source_ref)
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
            decision_payload=decision_payload,
            source_ref=normalized_source_ref,
            actor=created_by,
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
            created_by=created_by,
            updated_by=created_by,
        )
        self._session.add(model)
        self._session.flush()
        model.workflow_hash = _workflow_hash(model)
        self._session.flush()
        self._record_event(
            workflow=model,
            actor=created_by,
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
            event_payload={"kind": kind},
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
            _workflow_from_model(model)
            for model in self._session.scalars(stmt).all()
        ]

    def count_workflows(
        self,
        *,
        research_space_id: str,
        kind: GraphWorkflowKind | None,
        status: GraphWorkflowStatus | None,
    ) -> int:
        """Count workflows in one graph space."""
        stmt = select(func.count()).select_from(GraphWorkflowModel).where(
            GraphWorkflowModel.research_space_id == _as_uuid(research_space_id),
        )
        if kind is not None:
            stmt = stmt.where(GraphWorkflowModel.kind == kind)
        if status is not None:
            stmt = stmt.where(GraphWorkflowModel.status == status)
        return int(self._session.scalar(stmt) or 0)

    def get_workflow(self, *, research_space_id: str, workflow_id: str) -> GraphWorkflow:
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
        ai_principal = (
            _json_optional_str(ai_decision_payload.get("ai_principal"))
            if ai_decision_payload is not None
            else None
        )
        if ai_decision_payload is not None:
            normalized_authenticated_ai_principal = _normalize_optional_text(
                authenticated_ai_principal,
            )
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
        if ai_decision_payload is not None and (policy.blocked or policy.human_required):
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
            "confidence_assessment": confidence_payload,
            "confidence_result": confidence_result_payload,
        }
        model.policy_payload = _policy_payload(policy, confidence_result)
        model.updated_by = ai_principal or actor

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
                actor=ai_principal or actor,
                confidence_assessment=confidence_assessment,
                risk_tier=risk_tier,
                ai_decision_payload=ai_decision_payload,
                authenticated_ai_principal=authenticated_ai_principal,
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
            actor=ai_principal or actor,
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
                next_action={"action": "review_graph_change", "status": proposal.status},
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

    def _build_plan(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        kind: GraphWorkflowKind,
        input_payload: JSONObject,
        decision_payload: JSONObject,
        source_ref: str | None,
        actor: str,
        mode: GraphOperatingMode,
    ) -> _WorkflowPlan:
        policy = self.evaluate_policy(
            research_space_id=research_space_id,
            kind=kind,
            action=None,
            risk_tier="low",
            ai_principal=None,
            computed_confidence=None,
        )
        if kind == "evidence_approval":
            return self._plan_evidence_approval(
                research_space_id=research_space_id,
                input_payload=input_payload,
                decision_payload=decision_payload,
                source_ref=source_ref,
                actor=actor,
                mode=mode,
                policy_payload=_policy_payload(policy),
            )
        if kind == "batch_review":
            batch_items = _json_object_list(input_payload.get("generated_resources"))
            return _WorkflowPlan(
                status="WAITING_REVIEW",
                plan_payload={
                    "generated_resources": batch_items,
                    "instructions": "Approve, reject, or split generated resources through their normal services.",
                },
                generated_resources_payload={},
                decision_payload=decision_payload,
                policy_payload=_policy_payload(policy),
                explanation_payload={
                    "why_this_exists": "A batch of generated graph resources needs governed review.",
                    "next_action": "approve",
                },
            )
        if kind == "ai_evidence_decision":
            risk_tier = cast(
                "GraphWorkflowRiskTier",
                _json_optional_str(input_payload.get("risk_tier")) or "low",
            )
            confidence_assessment = _confidence_assessment_from_payload(
                input_payload.get("confidence_assessment"),
            )
            if (
                confidence_assessment is not None
                and confidence_assessment.risk_tier != risk_tier
            ):
                msg = "Decision confidence assessment risk_tier must match input risk_tier"
                raise ValueError(msg)
            confidence_result = (
                score_decision_confidence(confidence_assessment)
                if confidence_assessment is not None
                else None
            )
            ai_policy = self.evaluate_policy(
                research_space_id=research_space_id,
                kind=kind,
                action="approve",
                risk_tier=risk_tier,
                ai_principal=_json_optional_str(input_payload.get("ai_principal")),
                computed_confidence=(
                    confidence_result.computed_confidence
                    if confidence_result is not None
                    else None
                ),
            )
            confidence_result_payload = (
                confidence_result.to_payload() if confidence_result is not None else {}
            )
            return _WorkflowPlan(
                status=(
                    "PLAN_READY"
                    if ai_policy.ai_allowed
                    else "BLOCKED" if ai_policy.blocked else "WAITING_REVIEW"
                ),
                plan_payload={
                    "ai_decision_recorded": True,
                    "evidence_locator": input_payload.get("evidence_locator"),
                    "input_hash": input_payload.get("input_hash"),
                    "confidence_result": confidence_result_payload,
                },
                generated_resources_payload={},
                decision_payload={
                    **decision_payload,
                    "confidence_assessment": _confidence_assessment_payload(
                        confidence_assessment,
                    ),
                    "confidence_result": confidence_result_payload,
                },
                policy_payload=_policy_payload(ai_policy, confidence_result),
                explanation_payload={
                    "why_this_exists": "An AI evidence decision envelope was recorded for governed review.",
                    "next_action": "approve" if ai_policy.ai_allowed else "defer_to_human",
                    "computed_confidence": (
                        confidence_result.computed_confidence
                        if confidence_result is not None
                        else None
                    ),
                },
            )
        if kind == "conflict_resolution":
            return _WorkflowPlan(
                status="WAITING_REVIEW",
                plan_payload={
                    "claim_ids": input_payload.get("claim_ids", []),
                    "resolution_options": [
                        "KEEP_BOTH",
                        "MARK_CONTEXT_SPECIFIC",
                        "PREFER_SOURCE",
                        "REJECT_SOURCE",
                        "REQUEST_MORE_EVIDENCE",
                        "DEFER_TO_HUMAN",
                    ],
                },
                generated_resources_payload={},
                decision_payload=decision_payload,
                policy_payload=_policy_payload(policy),
                explanation_payload={
                    "why_this_exists": "Opposing or conflicting claims must stay visible until governed resolution.",
                    "next_action": "mark_resolved",
                },
            )
        return _WorkflowPlan(
            status="PLAN_READY",
            plan_payload={"input": input_payload, "next_action": "approve"},
            generated_resources_payload={},
            decision_payload=decision_payload,
            policy_payload=_policy_payload(policy),
            explanation_payload={
                "why_this_exists": f"Workflow '{kind}' was submitted for governed graph review.",
                "next_action": "approve",
            },
        )

    def _plan_evidence_approval(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        input_payload: JSONObject,
        decision_payload: JSONObject,
        source_ref: str | None,
        actor: str,
        mode: GraphOperatingMode,
        policy_payload: JSONObject,
    ) -> _WorkflowPlan:
        generated: JSONObject = {}
        plan_payload: JSONObject = {
            "input": input_payload,
            "next_action": "approve",
        }
        explanation_payload: JSONObject = {
            "why_this_exists": "Evidence was submitted for governed review.",
            "next_action": "approve",
        }
        pending_claim_request: JSONObject | None = None
        blocked_claim = False

        claim_request_payload = _json_object(input_payload.get("claim_request"))

        graph_change_payload = _json_object(input_payload.get("graph_change_proposal"))
        if graph_change_payload is not None:
            proposal = self._ai_full_mode_service.propose_graph_change(
                research_space_id=research_space_id,
                proposal_payload=graph_change_payload,
                proposed_by=actor,
                source_ref=_normalize_optional_text(
                    _json_optional_str(graph_change_payload.get("source_ref"))
                    or (f"{source_ref}:graph-change" if source_ref else None),
                ),
            )
            generated["graph_change_proposal_ids"] = [proposal.id]
            generated["graph_change_proposal_hashes"] = {
                proposal.id: proposal.proposal_hash,
            }
            plan_payload["graph_repair_plan"] = proposal.resolution_plan_payload
            plan_payload["graph_repair_warnings"] = proposal.warnings_payload
            explanation_payload = {
                "why_this_exists": "Evidence references graph pieces that need a governed repair plan.",
                "next_action": "approve",
            }

        dictionary_ids = self._create_dictionary_proposals_from_input(
            input_payload=input_payload,
            actor=actor,
        )
        if dictionary_ids:
            generated["dictionary_proposal_ids"] = dictionary_ids
            plan_payload["dictionary_proposal_ids"] = dictionary_ids
            explanation_payload = {
                "why_this_exists": "Evidence needs new dictionary vocabulary before it can become official graph state.",
                "next_action": "review_dictionary_proposals",
            }

        pending_resources = bool(
            generated.get("graph_change_proposal_ids")
            or generated.get("dictionary_proposal_ids"),
        )
        if claim_request_payload is not None:
            claim_plan = self._plan_claim_request(
                research_space_id=research_space_id,
                request_payload=claim_request_payload,
                actor=actor,
                source_ref=source_ref,
                should_apply=mode in _AUTO_CLAIM_MODES and not pending_resources,
            )
            claim_plan_payload = cast("JSONObject", claim_plan["plan_payload"])
            claim_generated = cast("JSONObject", claim_plan["generated_resources_payload"])
            claim_status = cast("GraphWorkflowStatus", claim_plan["status"])
            plan_payload["claim_plan"] = claim_plan_payload
            plan_payload["validation"] = claim_plan_payload.get("validation")

            claim_dictionary_ids = [
                str(item)
                for item in claim_generated.get("dictionary_proposal_ids", [])
                if isinstance(item, str)
            ]
            if claim_dictionary_ids:
                existing_dictionary_ids = [
                    str(item)
                    for item in generated.get("dictionary_proposal_ids", [])
                    if isinstance(item, str)
                ]
                generated["dictionary_proposal_ids"] = list(
                    dict.fromkeys([*existing_dictionary_ids, *claim_dictionary_ids]),
                )
                plan_payload["dictionary_proposal_ids"] = generated[
                    "dictionary_proposal_ids"
                ]
                pending_resources = True

            if claim_status == "APPLIED":
                generated = {**generated, **claim_generated}
                explanation_payload = cast("JSONObject", claim_plan["explanation_payload"])
            elif claim_status == "BLOCKED" and not pending_resources:
                blocked_claim = True
                explanation_payload = cast("JSONObject", claim_plan["explanation_payload"])
            else:
                pending_claim_request = claim_request_payload
                generated["pending_claim_request"] = pending_claim_request
                plan_payload["pending_claim_request"] = pending_claim_request
                explanation_payload = cast("JSONObject", claim_plan["explanation_payload"])

        if pending_resources or pending_claim_request is not None:
            return _WorkflowPlan(
                status="PLAN_READY",
                plan_payload=plan_payload,
                generated_resources_payload=generated,
                decision_payload=decision_payload,
                policy_payload=policy_payload,
                explanation_payload=explanation_payload,
            )
        if blocked_claim:
            return _WorkflowPlan(
                status="BLOCKED",
                plan_payload=plan_payload,
                generated_resources_payload=generated,
                decision_payload=decision_payload,
                policy_payload=policy_payload,
                explanation_payload=explanation_payload,
            )
        if generated.get("claim_ids"):
            return _WorkflowPlan(
                status="APPLIED",
                plan_payload=plan_payload,
                generated_resources_payload=generated,
                decision_payload=decision_payload,
                policy_payload=policy_payload,
                explanation_payload=explanation_payload,
            )
        return _WorkflowPlan(
            status="WAITING_REVIEW",
            plan_payload=plan_payload,
            generated_resources_payload=generated,
            decision_payload=decision_payload,
            policy_payload=policy_payload,
            explanation_payload=explanation_payload,
        )

    def _plan_claim_request(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        request_payload: JSONObject,
        actor: str,
        source_ref: str | None,
        should_apply: bool,
    ) -> JSONObject:
        request = KernelRelationClaimCreateRequest.model_validate(request_payload)
        validation_service = GraphValidationService(
            entity_service=self._entity_service,
            dictionary_service=self._dictionary_service,
            relation_claim_service=self._relation_claim_service,
        )
        validation = validation_service.validate_claim_request(
            space_id=research_space_id,
            request=request,
            check_existing_claims=True,
        )
        validation_payload = cast("JSONObject", validation.model_dump(mode="json"))
        if not validation.valid:
            dictionary_proposal_ids = self._create_dictionary_proposals_from_validation(
                validation_payload=validation_payload,
                actor=actor,
            )
            status: GraphWorkflowStatus = (
                "PLAN_READY" if dictionary_proposal_ids else "BLOCKED"
            )
            return {
                "status": status,
                "plan_payload": {
                    "validation": validation_payload,
                    "next_actions": validation_payload.get("next_actions", []),
                },
                "generated_resources_payload": {
                    "dictionary_proposal_ids": dictionary_proposal_ids,
                },
                "explanation_payload": {
                    "why_this_exists": validation.message,
                    "validation_code": validation.code,
                    "next_action": "review_dictionary_proposals"
                    if dictionary_proposal_ids
                    else "defer_to_human",
                },
            }
        if not should_apply:
            return {
                "status": "WAITING_REVIEW",
                "plan_payload": {
                    "validation": validation_payload,
                    "claim_request": request_payload,
                    "next_action": "approve",
                },
                "generated_resources_payload": {},
                "explanation_payload": {
                    "why_this_exists": "The claim is valid, but this operating mode requires review before applying evidence.",
                    "next_action": "approve",
                },
            }
        claim_id = self._create_valid_claim(
            research_space_id=research_space_id,
            request=request,
            normalized_relation_type=validation.normalized_relation_type
            or request.relation_type,
            validation_state=validation.validation_state,
            validation_reason=validation.validation_reason
            or f"validation:{validation.code}",
            persistability=validation.persistability,
            actor=actor,
            source_ref=source_ref,
        )
        return {
            "status": "APPLIED",
            "plan_payload": {
                "validation": validation_payload,
                "claim_request": request_payload,
            },
            "generated_resources_payload": {"claim_ids": [claim_id]},
            "explanation_payload": {
                "why_this_exists": "The evidence matched approved graph rules and was applied as a claim.",
                "next_action": "inspect_claim",
            },
        }

    def _create_valid_claim(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        request: KernelRelationClaimCreateRequest,
        normalized_relation_type: str,
        validation_state: str | None,
        validation_reason: str | None,
        persistability: str | None,
        actor: str,
        source_ref: str | None,
    ) -> str:
        source_entity = self._entity_service.get_entity(str(request.source_entity_id))
        target_entity = self._entity_service.get_entity(str(request.target_entity_id))
        if (
            source_entity is None
            or target_entity is None
            or str(source_entity.research_space_id) != str(research_space_id)
            or str(target_entity.research_space_id) != str(research_space_id)
        ):
            msg = "Source or target entity not found"
            raise ValueError(msg)
        relation_type = normalized_relation_type.strip().upper()
        claim_source_ref = _normalize_optional_text(request.source_ref) or (
            f"workflow:{source_ref}:claim" if source_ref else None
        )
        if claim_source_ref is not None:
            existing = self._relation_claim_service.get_by_source_ref(
                research_space_id=research_space_id,
                source_ref=claim_source_ref,
            )
            if existing is not None:
                return str(existing.id)
        has_evidence = any(
            (
                request.evidence_summary,
                request.evidence_sentence,
                request.source_document_ref,
            ),
        )
        confidence_metadata = fact_assessment_metadata(request.assessment)
        claim = self._relation_claim_service.create_claim(
            research_space_id=research_space_id,
            source_document_id=None,
            source_document_ref=request.source_document_ref,
            source_ref=claim_source_ref,
            agent_run_id=request.agent_run_id,
            source_type=source_entity.entity_type,
            relation_type=relation_type,
            target_type=target_entity.entity_type,
            source_label=source_entity.display_label,
            target_label=target_entity.display_label,
            confidence=request.derived_confidence,
            validation_state=_CLAIM_VALIDATION_STATE_MAP.get(
                validation_state or "",
                "UNDEFINED",
            ),
            validation_reason=validation_reason,
            persistability=cast(
                "RelationClaimPersistability",
                "PERSISTABLE"
                if persistability == "PERSISTABLE"
                else "NON_PERSISTABLE",
            ),
            claim_status="OPEN",
            polarity="SUPPORT",
            claim_text=request.claim_text,
            claim_section=None,
            linked_relation_id=None,
            metadata={
                **request.metadata,
                "origin": "graph_workflow",
                "created_by": actor,
                "source_entity_id": str(source_entity.id),
                "target_entity_id": str(target_entity.id),
                **confidence_metadata,
            },
        )
        claim_id = str(claim.id)
        self._claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=research_space_id,
            role="SUBJECT",
            label=source_entity.display_label,
            entity_id=str(source_entity.id),
            position=0,
            qualifiers={"origin": "graph_workflow"},
        )
        self._claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=research_space_id,
            role="OBJECT",
            label=target_entity.display_label,
            entity_id=str(target_entity.id),
            position=1,
            qualifiers={"origin": "graph_workflow"},
        )
        if has_evidence:
            self._claim_evidence_service.create_evidence(
                claim_id=claim_id,
                source_document_id=None,
                source_document_ref=request.source_document_ref,
                agent_run_id=request.agent_run_id,
                sentence=request.evidence_sentence,
                sentence_source=_normalize_sentence_source(
                    request.evidence_sentence_source,
                ),
                sentence_confidence=_normalize_sentence_confidence(
                    request.evidence_sentence_confidence,
                ),
                sentence_rationale=request.evidence_sentence_rationale,
                figure_reference=None,
                table_reference=None,
                confidence=request.derived_confidence,
                metadata={
                    "origin": "graph_workflow",
                    "evidence_summary": request.evidence_summary,
                    **confidence_metadata,
                },
            )
        return claim_id

    def _create_dictionary_proposals_from_input(
        self,
        *,
        input_payload: JSONObject,
        actor: str,
    ) -> list[str]:
        proposal_ids: list[str] = []
        for payload in _json_object_list(input_payload.get("dictionary_proposals")):
            proposal_type = _json_str(payload.get("proposal_type"), field_name="proposal_type")
            proposal = self._create_dictionary_proposal(
                proposal_type=proposal_type,
                payload=payload,
                actor=actor,
            )
            proposal_ids.append(proposal.id)
        return proposal_ids

    def _create_dictionary_proposals_from_validation(
        self,
        *,
        validation_payload: JSONObject,
        actor: str,
    ) -> list[str]:
        proposal_ids: list[str] = []
        for action_payload in _json_object_list(validation_payload.get("next_actions")):
            if action_payload.get("action") != "create_dictionary_proposal":
                continue
            proposal_type = _json_optional_str(action_payload.get("proposal_type"))
            payload = _json_object(action_payload.get("payload"))
            if proposal_type is None or payload is None:
                continue
            proposal = self._create_dictionary_proposal(
                proposal_type=proposal_type,
                payload=payload,
                actor=actor,
            )
            proposal_ids.append(proposal.id)
        return proposal_ids

    def _create_dictionary_proposal(
        self,
        *,
        proposal_type: str,
        payload: JSONObject,
        actor: str,
    ) -> DictionaryProposal:
        if proposal_type == "RELATION_TYPE":
            return self._dictionary_proposal_service.create_relation_type_proposal(
                relation_type=_json_str(payload.get("id"), field_name="id"),
                display_name=_json_str(
                    payload.get("display_name"),
                    field_name="display_name",
                ),
                description=_json_str(
                    payload.get("description"),
                    field_name="description",
                ),
                domain_context=_json_str(
                    payload.get("domain_context"),
                    field_name="domain_context",
                ),
                rationale=_json_str(payload.get("rationale"), field_name="rationale"),
                proposed_by=actor,
                evidence_payload=_json_object(payload.get("evidence_payload")) or {},
                is_directional=_json_bool(payload.get("is_directional"), default=True),
                inverse_label=_json_optional_str(payload.get("inverse_label")),
                source_ref=_json_optional_str(payload.get("source_ref")),
            )
        if proposal_type == "RELATION_CONSTRAINT":
            return self._dictionary_proposal_service.create_relation_constraint_proposal(
                source_type=_json_str(payload.get("source_type"), field_name="source_type"),
                relation_type=_json_str(
                    payload.get("relation_type"),
                    field_name="relation_type",
                ),
                target_type=_json_str(payload.get("target_type"), field_name="target_type"),
                rationale=_json_str(payload.get("rationale"), field_name="rationale"),
                proposed_by=actor,
                evidence_payload=_json_object(payload.get("evidence_payload")) or {},
                is_allowed=_json_bool(payload.get("is_allowed"), default=True),
                requires_evidence=_json_bool(
                    payload.get("requires_evidence"),
                    default=True,
                ),
                profile=_json_optional_str(payload.get("profile")) or "ALLOWED",
                source_ref=_json_optional_str(payload.get("source_ref")),
            )
        msg = f"Unsupported dictionary proposal type '{proposal_type}'"
        raise ValueError(msg)

    def _apply_generated_resources(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        workflow: GraphWorkflowModel,
        actor: str,
        confidence_assessment: DecisionConfidenceAssessment | None,
        risk_tier: GraphWorkflowRiskTier,
        ai_decision_payload: JSONObject | None,
        authenticated_ai_principal: str | None,
    ) -> _GeneratedResourcesApplication:
        if workflow.kind == "batch_review":
            return self._apply_batch_review_resources(
                research_space_id=research_space_id,
                workflow=workflow,
                actor=actor,
            )

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
                authenticated_ai_principal=authenticated_ai_principal,
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
        if workflow.kind == "evidence_approval" and not workflow.generated_resources_payload:
            claim_payload = _json_object(workflow.input_payload.get("claim_request"))
            if claim_payload is not None:
                claim_plan = self._plan_claim_request(
                    research_space_id=research_space_id,
                    request_payload=claim_payload,
                    actor=actor,
                    source_ref=workflow.source_ref,
                    should_apply=True,
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
        return [
            str(item)
            for item in workflow.generated_resources_payload.get(
                "graph_change_proposal_ids",
                [],
            )
            if isinstance(item, str)
        ]

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
        dictionary_ids = [
            str(item)
            for item in workflow.generated_resources_payload.get(
                "dictionary_proposal_ids",
                [],
            )
            if isinstance(item, str)
        ]
        for proposal_id in dictionary_ids:
            proposal = self._dictionary_proposal_service.get_proposal(proposal_id)
            if proposal.status not in {"APPROVED", "MERGED"}:
                return False
        for proposal_id in self._workflow_graph_change_ids(workflow):
            proposal = self._ai_full_mode_service.get_graph_change_proposal(proposal_id)
            if proposal.status != "APPLIED":
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
        graph_change_ids = [
            str(item)
            for item in generated_resources_payload.get("graph_change_proposal_ids", [])
            if isinstance(item, str)
        ]
        for proposal_id in graph_change_ids:
            proposal = self._ai_full_mode_service.get_graph_change_proposal(proposal_id)
            if proposal.research_space_id != str(research_space_id):
                msg = f"Generated graph-change proposal '{proposal_id}' is not in this space"
                raise ValueError(msg)
        concept_ids = [
            str(item)
            for item in generated_resources_payload.get("concept_proposal_ids", [])
            if isinstance(item, str)
        ]
        for proposal_id in concept_ids:
            proposal = self._ai_full_mode_service.get_concept_proposal(proposal_id)
            if proposal.research_space_id != str(research_space_id):
                msg = f"Generated concept proposal '{proposal_id}' is not in this space"
                raise ValueError(msg)
        connector_ids = [
            str(item)
            for item in generated_resources_payload.get("connector_proposal_ids", [])
            if isinstance(item, str)
        ]
        for proposal_id in connector_ids:
            proposal = self._ai_full_mode_service.get_connector_proposal(proposal_id)
            if proposal.research_space_id != str(research_space_id):
                msg = f"Generated connector proposal '{proposal_id}' is not in this space"
                raise ValueError(msg)
        claim_ids = [
            str(item)
            for item in generated_resources_payload.get("claim_ids", [])
            if isinstance(item, str)
        ]
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

    def _compatible_ai_full_mode_settings(
        self,
        *,
        config: GraphOperatingModeConfig,
        current: JSONObject | None,
    ) -> JSONObject:
        current_payload = current or {}
        trusted = config.workflow_policy.trusted_ai_principals or [
            str(item)
            for item in current_payload.get("trusted_principals", [])
            if isinstance(item, str)
        ]
        governance_mode = (
            "ai_full"
            if config.mode in {"ai_full_graph", "ai_full_evidence", "continuous_learning"}
            else "human_review"
        )
        return {
            **current_payload,
            "governance_mode": governance_mode,
            "trusted_principals": trusted,
            "min_confidence": config.workflow_policy.min_ai_confidence,
            "allow_high_risk_actions": False,
        }


__all__ = ["GraphWorkflowService", "stable_workflow_input_hash"]
