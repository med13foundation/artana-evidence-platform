# mypy: disable-error-code="attr-defined,no-any-return"
"""Plan-building helpers for graph workflow service."""

from __future__ import annotations

from typing import cast

from artana_evidence_db.common_types import JSONObject, JSONValue
from artana_evidence_db.decision_confidence import score_decision_confidence
from artana_evidence_db.dictionary_models import DictionaryProposal
from artana_evidence_db.fact_assessment_support import fact_assessment_metadata
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationClaimCreateRequest,
)
from artana_evidence_db.graph_validation_service import GraphValidationService
from artana_evidence_db.graph_workflow_support import (
    _AUTO_CLAIM_MODES,
    _CLAIM_VALIDATION_STATE_MAP,
    _confidence_assessment_from_payload,
    _confidence_assessment_payload,
    _json_bool,
    _json_object,
    _json_object_list,
    _json_optional_str,
    _json_str,
    _normalize_optional_text,
    _normalize_sentence_confidence,
    _normalize_sentence_source,
    _policy_payload,
    _WorkflowPlan,
)
from artana_evidence_db.relation_claim_models import RelationClaimPersistability
from artana_evidence_db.workflow_models import (
    GraphOperatingMode,
    GraphWorkflowKind,
    GraphWorkflowRiskTier,
    GraphWorkflowStatus,
)


def _json_string_list(value: JSONValue | None) -> list[str]:
    """Return string items from a JSON array-like value."""
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, str)]


class GraphWorkflowPlanningMixin:
    """Build workflow plans and generated dictionary resources."""

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

            claim_dictionary_ids = _json_string_list(
                claim_generated.get("dictionary_proposal_ids"),
            )
            if claim_dictionary_ids:
                existing_dictionary_ids = _json_string_list(
                    generated.get("dictionary_proposal_ids"),
                )
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
        normalized_persistability: RelationClaimPersistability = (
            "PERSISTABLE" if persistability == "PERSISTABLE" else "NON_PERSISTABLE"
        )
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
            persistability=normalized_persistability,
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


__all__ = ["GraphWorkflowPlanningMixin"]
