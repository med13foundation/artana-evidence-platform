"""Batch-review helpers for graph workflows."""


from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_db.ai_full_mode_service import AIFullModeService
from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.decision_confidence import DecisionConfidenceAssessment
from artana_evidence_db.dictionary_proposal_service import DictionaryProposalService
from artana_evidence_db.graph_workflow_support import (
    _BATCH_RESOURCE_ACTIONS,
    _CLAIM_BATCH_STATUS_BY_ACTION,
    _WORKFLOW_BATCH_ACTION_BY_ITEM_ACTION,
    _claim_triage_actor,
    _GeneratedResourcesApplication,
    _json_object,
    _json_object_list,
    _json_optional_str,
    _json_str,
)
from artana_evidence_db.kernel_services import KernelRelationClaimService
from artana_evidence_db.workflow_models import (
    GraphWorkflow,
    GraphWorkflowAction,
    GraphWorkflowRiskTier,
    GraphWorkflowStatus,
)
from artana_evidence_db.workflow_persistence_models import (
    GraphWorkflowModel,
)
from pydantic import ValidationError


class GraphWorkflowBatchMixin:
    """Mixin for batch workflow resource application."""

    if TYPE_CHECKING:
        _ai_full_mode_service: AIFullModeService
        _dictionary_proposal_service: DictionaryProposalService
        _relation_claim_service: KernelRelationClaimService

        def _get_workflow_model(
            self,
            *,
            research_space_id: str,
            workflow_id: str,
        ) -> GraphWorkflowModel: ...

        def act_on_workflow(
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
        ) -> GraphWorkflow: ...

    def _apply_batch_review_resources(
        self,
        *,
        research_space_id: str,
        workflow: GraphWorkflowModel,
        actor: str,
    ) -> _GeneratedResourcesApplication:
        items = _json_object_list(workflow.input_payload.get("generated_resources"))
        applied_refs: list[JSONValue] = []
        failed_refs: list[JSONValue] = []
        batch_results: list[JSONValue] = []
        if not items:
            failed: JSONObject = {
                "resource_type": "batch_review",
                "resource_id": str(workflow.id),
                "status": "failed",
                "reason": "batch_review requires input_payload.generated_resources",
            }
            failed_refs.append(failed)
            batch_results.append(failed)

        for index, item in enumerate(items):
            try:
                result = self._apply_batch_review_item(
                    research_space_id=research_space_id,
                    workflow=workflow,
                    item=item,
                    actor=actor,
                    index=index,
                )
                applied_refs.append(result)
                batch_results.append(result)
            except (ValueError, ValidationError) as exc:
                failed = self._failed_batch_item_result(
                    item=item,
                    index=index,
                    reason=str(exc),
                )
                failed_refs.append(failed)
                batch_results.append(failed)

        return _GeneratedResourcesApplication(
            status="CHANGES_REQUESTED" if failed_refs else "APPLIED",
            generated_updates={
                "applied_resource_refs": applied_refs,
                "failed_resource_refs": failed_refs,
                "batch_results": batch_results,
            },
        )

    def _apply_batch_review_item(
        self,
        *,
        research_space_id: str,
        workflow: GraphWorkflowModel,
        item: JSONObject,
        actor: str,
        index: int,
    ) -> JSONObject:
        resource_type = _json_str(
            item.get("resource_type"),
            field_name=f"generated_resources[{index}].resource_type",
        )
        resource_id = _json_str(
            item.get("resource_id"),
            field_name=f"generated_resources[{index}].resource_id",
        )
        action = _json_str(
            item.get("action"),
            field_name=f"generated_resources[{index}].action",
        )
        supported_actions = _BATCH_RESOURCE_ACTIONS.get(resource_type)
        if supported_actions is None:
            msg = f"Unsupported batch resource_type '{resource_type}'"
            raise ValueError(msg)
        if action not in supported_actions:
            msg = (
                f"Unsupported batch action '{action}' for resource_type "
                f"'{resource_type}'"
            )
            raise ValueError(msg)
        reason = _json_optional_str(item.get("reason")) or "Batch review action"
        input_hash = _json_optional_str(item.get("input_hash"))
        decision_payload = _json_object(item.get("decision_payload")) or {}

        if resource_type == "concept_proposal":
            return self._apply_batch_concept_proposal(
                research_space_id=research_space_id,
                resource_id=resource_id,
                action=action,
                input_hash=input_hash,
                decision_payload=decision_payload,
                reason=reason,
                actor=actor,
            )
        if resource_type == "dictionary_proposal":
            return self._apply_batch_dictionary_proposal(
                resource_id=resource_id,
                action=action,
                reason=reason,
                actor=actor,
            )
        if resource_type == "graph_change_proposal":
            return self._apply_batch_graph_change_proposal(
                research_space_id=research_space_id,
                resource_id=resource_id,
                action=action,
                input_hash=input_hash,
                reason=reason,
                actor=actor,
            )
        if resource_type == "connector_proposal":
            return self._apply_batch_connector_proposal(
                research_space_id=research_space_id,
                resource_id=resource_id,
                action=action,
                reason=reason,
                actor=actor,
            )
        if resource_type == "claim":
            return self._apply_batch_claim(
                research_space_id=research_space_id,
                resource_id=resource_id,
                action=action,
                actor=actor,
            )
        return self._apply_batch_workflow(
            research_space_id=research_space_id,
            workflow=workflow,
            resource_id=resource_id,
            action=action,
            input_hash=input_hash,
            reason=reason,
            decision_payload=decision_payload,
            actor=actor,
        )

    def _apply_batch_concept_proposal(
        self,
        *,
        research_space_id: str,
        resource_id: str,
        action: str,
        input_hash: str | None,
        decision_payload: JSONObject,
        reason: str,
        actor: str,
    ) -> JSONObject:
        proposal = self._ai_full_mode_service.get_concept_proposal(resource_id)
        if proposal.research_space_id != str(research_space_id):
            msg = f"Concept proposal '{resource_id}' is not in this space"
            raise ValueError(msg)
        if (
            (action == "approve" and proposal.status == "APPLIED")
            or (action == "merge" and proposal.status == "MERGED")
            or (action == "reject" and proposal.status == "REJECTED")
            or (
                action == "request_changes"
                and proposal.status == "CHANGES_REQUESTED"
            )
        ):
            return self._batch_result(
                resource_type="concept_proposal",
                resource_id=resource_id,
                action=action,
                resource_status=proposal.status,
                details={
                    "applied_concept_member_id": proposal.applied_concept_member_id,
                    "candidate_decision": proposal.candidate_decision,
                },
            )
        self._assert_batch_input_hash(
            input_hash=input_hash,
            current_hash=proposal.proposal_hash,
            resource_type="concept_proposal",
            resource_id=resource_id,
        )
        if action == "approve":
            proposal = self._ai_full_mode_service.approve_concept_proposal(
                resource_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason=reason,
            )
        elif action == "merge":
            target_id = _json_str(
                decision_payload.get("target_concept_member_id"),
                field_name="decision_payload.target_concept_member_id",
            )
            proposal = self._ai_full_mode_service.merge_concept_proposal(
                resource_id,
                research_space_id=research_space_id,
                target_concept_member_id=target_id,
                reviewed_by=actor,
                decision_reason=reason,
            )
        elif action == "reject":
            proposal = self._ai_full_mode_service.reject_concept_proposal(
                resource_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason=reason,
            )
        else:
            proposal = self._ai_full_mode_service.request_concept_changes(
                resource_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason=reason,
            )
        return self._batch_result(
            resource_type="concept_proposal",
            resource_id=resource_id,
            action=action,
            resource_status=proposal.status,
            details={
                "applied_concept_member_id": proposal.applied_concept_member_id,
                "candidate_decision": proposal.candidate_decision,
            },
        )

    def _apply_batch_dictionary_proposal(
        self,
        *,
        resource_id: str,
        action: str,
        reason: str,
        actor: str,
    ) -> JSONObject:
        proposal = self._dictionary_proposal_service.get_proposal(resource_id)
        if action == "approve":
            if proposal.status != "APPROVED":
                proposal, applied = self._dictionary_proposal_service.approve_proposal(
                    resource_id,
                    reviewed_by=actor,
                    decision_reason=reason,
                )
                applied_payload: JSONObject = {
                    "applied_type": type(applied).__name__,
                    "applied_id": str(applied.id),
                }
            else:
                applied_payload = {}
        elif action == "reject":
            if proposal.status != "REJECTED":
                proposal = self._dictionary_proposal_service.reject_proposal(
                    resource_id,
                    reviewed_by=actor,
                    decision_reason=reason,
                )
            applied_payload = {}
        else:
            if proposal.status != "CHANGES_REQUESTED":
                proposal = self._dictionary_proposal_service.request_changes(
                    resource_id,
                    reviewed_by=actor,
                    decision_reason=reason,
                )
            applied_payload = {}
        return self._batch_result(
            resource_type="dictionary_proposal",
            resource_id=resource_id,
            action=action,
            resource_status=proposal.status,
            details={
                "proposal_type": proposal.proposal_type,
                **applied_payload,
            },
        )

    def _apply_batch_graph_change_proposal(
        self,
        *,
        research_space_id: str,
        resource_id: str,
        action: str,
        input_hash: str | None,
        reason: str,
        actor: str,
    ) -> JSONObject:
        proposal = self._ai_full_mode_service.get_graph_change_proposal(resource_id)
        if proposal.research_space_id != str(research_space_id):
            msg = f"Graph-change proposal '{resource_id}' is not in this space"
            raise ValueError(msg)
        if (
            (action == "apply" and proposal.status == "APPLIED")
            or (action == "reject" and proposal.status == "REJECTED")
            or (
                action == "request_changes"
                and proposal.status == "CHANGES_REQUESTED"
            )
        ):
            return self._batch_result(
                resource_type="graph_change_proposal",
                resource_id=resource_id,
                action=action,
                resource_status=proposal.status,
                details={
                    "applied_concept_member_ids": proposal.applied_concept_member_ids_payload,
                    "applied_claim_ids": proposal.applied_claim_ids_payload,
                },
            )
        self._assert_batch_input_hash(
            input_hash=input_hash,
            current_hash=proposal.proposal_hash,
            resource_type="graph_change_proposal",
            resource_id=resource_id,
        )
        if action == "apply":
            proposal = self._ai_full_mode_service.apply_graph_change_proposal(
                resource_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason=reason,
            )
        elif action == "reject":
            proposal = self._ai_full_mode_service.reject_graph_change_proposal(
                resource_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason=reason,
            )
        else:
            proposal = self._ai_full_mode_service.request_graph_change_changes(
                resource_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason=reason,
            )
        return self._batch_result(
            resource_type="graph_change_proposal",
            resource_id=resource_id,
            action=action,
            resource_status=proposal.status,
            details={
                "applied_concept_member_ids": proposal.applied_concept_member_ids_payload,
                "applied_claim_ids": proposal.applied_claim_ids_payload,
            },
        )

    def _apply_batch_connector_proposal(
        self,
        *,
        research_space_id: str,
        resource_id: str,
        action: str,
        reason: str,
        actor: str,
    ) -> JSONObject:
        proposal = self._ai_full_mode_service.get_connector_proposal(resource_id)
        if proposal.research_space_id != str(research_space_id):
            msg = f"Connector proposal '{resource_id}' is not in this space"
            raise ValueError(msg)
        if action == "approve":
            if proposal.status != "APPROVED":
                proposal = self._ai_full_mode_service.approve_connector(
                    resource_id,
                    research_space_id=research_space_id,
                    reviewed_by=actor,
                    decision_reason=reason,
                )
        elif action == "reject":
            if proposal.status != "REJECTED":
                proposal = self._ai_full_mode_service.reject_connector(
                    resource_id,
                    research_space_id=research_space_id,
                    reviewed_by=actor,
                    decision_reason=reason,
                )
        elif proposal.status != "CHANGES_REQUESTED":
            proposal = self._ai_full_mode_service.request_connector_changes(
                resource_id,
                research_space_id=research_space_id,
                reviewed_by=actor,
                decision_reason=reason,
            )
        return self._batch_result(
            resource_type="connector_proposal",
            resource_id=resource_id,
            action=action,
            resource_status=proposal.status,
            details={"connector_slug": proposal.connector_slug},
        )

    def _apply_batch_claim(
        self,
        *,
        research_space_id: str,
        resource_id: str,
        action: str,
        actor: str,
    ) -> JSONObject:
        claim = self._relation_claim_service.get_claim(resource_id)
        if claim is None or str(claim.research_space_id) != str(research_space_id):
            msg = f"Claim '{resource_id}' is not in this space"
            raise ValueError(msg)
        target_status = _CLAIM_BATCH_STATUS_BY_ACTION[action]
        if claim.claim_status != target_status:
            claim = self._relation_claim_service.update_claim_status(
                resource_id,
                claim_status=target_status,
                triaged_by=_claim_triage_actor(actor),
            )
        return self._batch_result(
            resource_type="claim",
            resource_id=resource_id,
            action=action,
            resource_status=claim.claim_status,
            details={
                "validation_state": claim.validation_state,
                "persistability": claim.persistability,
            },
        )

    def _apply_batch_workflow(
        self,
        *,
        research_space_id: str,
        workflow: GraphWorkflowModel,
        resource_id: str,
        action: str,
        input_hash: str | None,
        reason: str,
        decision_payload: JSONObject,
        actor: str,
    ) -> JSONObject:
        if resource_id == str(workflow.id):
            msg = "A batch_review workflow cannot apply itself"
            raise ValueError(msg)
        target_workflow = self._get_workflow_model(
            workflow_id=resource_id,
            research_space_id=research_space_id,
        )
        workflow_action = _WORKFLOW_BATCH_ACTION_BY_ITEM_ACTION[action]
        terminal_status_by_action: dict[str, GraphWorkflowStatus] = {
            "approve": "APPLIED",
            "reject": "REJECTED",
            "request_changes": "CHANGES_REQUESTED",
            "defer_to_human": "WAITING_REVIEW",
        }
        target_status = terminal_status_by_action[action]
        if target_workflow.status != target_status:
            nested = self.act_on_workflow(
                research_space_id=research_space_id,
                workflow_id=resource_id,
                action=workflow_action,
                actor=actor,
                input_hash=input_hash,
                risk_tier="low",
                confidence_assessment=None,
                reason=reason,
                decision_payload=decision_payload,
                generated_resources_payload={},
                ai_decision_payload=None,
                authenticated_ai_principal=None,
            )
            resource_status = nested.status
        else:
            resource_status = target_workflow.status
        return self._batch_result(
            resource_type="workflow",
            resource_id=resource_id,
            action=action,
            resource_status=resource_status,
            details={},
        )

    def _assert_batch_input_hash(
        self,
        *,
        input_hash: str | None,
        current_hash: str,
        resource_type: str,
        resource_id: str,
    ) -> None:
        if input_hash is not None and input_hash != current_hash:
            msg = (
                f"{resource_type} '{resource_id}' input_hash does not match "
                "the current resource hash"
            )
            raise ValueError(msg)

    def _failed_batch_item_result(
        self,
        *,
        item: JSONObject,
        index: int,
        reason: str,
    ) -> JSONObject:
        return {
            "resource_type": _json_optional_str(item.get("resource_type"))
            or "unknown",
            "resource_id": _json_optional_str(item.get("resource_id"))
            or f"generated_resources[{index}]",
            "action": _json_optional_str(item.get("action")) or "unknown",
            "status": "failed",
            "reason": reason,
        }

    def _batch_result(
        self,
        *,
        resource_type: str,
        resource_id: str,
        action: str,
        resource_status: str,
        details: JSONObject,
    ) -> JSONObject:
        return {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "status": "applied",
            "resource_status": resource_status,
            "details": details,
        }
