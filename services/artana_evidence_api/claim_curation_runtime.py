"""Deterministic runtime helpers for claim-curation harness runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.approval_store import (
    HarnessApprovalAction,
    HarnessApprovalStore,
)
from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.graph_client import GraphTransportBundle  # noqa: TC001
from artana_evidence_api.proposal_actions import (
    decide_proposal,
    promote_to_graph_claim,
    require_proposal,
)
from artana_evidence_api.run_registry import (  # noqa: TC001
    HarnessRunProgressRecord,
    HarnessRunRecord,
    HarnessRunRegistry,
)
from artana_evidence_api.tool_catalog import (
    ListClaimEvidenceToolArgs,
    ListClaimParticipantsToolArgs,
    ListClaimsByEntityToolArgs,
    ListRelationConflictsToolArgs,
)
from artana_evidence_api.tool_runtime import (
    run_list_claim_evidence,
    run_list_claim_participants,
    run_list_claims_by_entity,
    run_list_relation_conflicts,
)
from artana_evidence_api.transparency import append_skill_activity
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.approval_store import HarnessApprovalRecord
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.proposal_store import (
        HarnessProposalRecord,
        HarnessProposalStore,
    )
    from artana_evidence_api.types.graph_contracts import (
        ClaimParticipantResponse,
        KernelRelationConflictResponse,
    )

_WORKFLOW_KIND = "claim_curation"
_RUNNING_PROGRESS_START = 0.6
_RUNNING_PROGRESS_SPAN = 0.3
_GRAPH_DUPLICATE_CLAIM_LIMIT = 200
_GRAPH_CONFLICT_LIMIT = 200


@dataclass(frozen=True, slots=True)
class ClaimCurationGraphDuplicate:
    """One exact graph-side duplicate claim detected during curation review."""

    claim_id: str
    claim_status: str
    validation_state: str
    persistability: str
    confidence: float
    linked_relation_id: str | None
    source_label: str | None
    target_label: str | None
    evidence_count: int


@dataclass(frozen=True, slots=True)
class ClaimCurationProposalReview:
    """One proposal assessment used to build the curation packet."""

    proposal: HarnessProposalRecord
    source_entity_id: str | None
    target_entity_id: str | None
    relation_type: str | None
    duplicate_selected_count: int
    existing_promoted_proposal_ids: tuple[str, ...]
    graph_duplicates: tuple[ClaimCurationGraphDuplicate, ...]
    conflicting_relation_ids: tuple[str, ...]
    invariant_issues: tuple[str, ...]
    blocker_reasons: tuple[str, ...]
    eligible_for_approval: bool


def approval_key_for_proposal(proposal_id: str) -> str:
    """Return the stable approval key for one proposal-application action."""
    return f"apply-proposal:{proposal_id}"


def is_claim_curation_workflow(run: HarnessRunRecord) -> bool:
    """Return whether one run was created by the claim-curation workflow route."""
    workflow = run.input_payload.get("workflow")
    return isinstance(workflow, str) and workflow == _WORKFLOW_KIND


def normalize_requested_proposal_ids(
    proposal_ids: list[UUID],
) -> tuple[str, ...]:
    """Normalize and validate one ordered proposal-id selection."""
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for proposal_id in proposal_ids:
        normalized = str(proposal_id)
        if normalized in seen_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate proposal id '{normalized}' in claim-curation request",
            )
        seen_ids.add(normalized)
        normalized_ids.append(normalized)
    return tuple(normalized_ids)


def load_curatable_proposals(
    *,
    space_id: UUID,
    proposal_ids: tuple[str, ...],
    proposal_store: HarnessProposalStore,
) -> list[HarnessProposalRecord]:
    """Load and validate proposals selected for claim curation."""
    proposals: list[HarnessProposalRecord] = []
    for proposal_id in proposal_ids:
        proposal = require_proposal(
            space_id=space_id,
            proposal_id=proposal_id,
            proposal_store=proposal_store,
        )
        if proposal.proposal_type != "candidate_claim":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Proposal '{proposal.id}' has unsupported type "
                    f"'{proposal.proposal_type}' for claim curation"
                ),
            )
        if proposal.status != "pending_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Proposal '{proposal.id}' is already decided with status "
                    f"'{proposal.status}'"
                ),
            )
        proposals.append(proposal)
    return proposals


def _proposal_payload_uuid(
    proposal: HarnessProposalRecord,
    *,
    field_name: str,
) -> tuple[str | None, str | None]:
    value = proposal.payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        return None, f"Proposal payload is missing '{field_name}'."
    normalized = value.strip()
    try:
        UUID(normalized)
    except ValueError:
        return None, f"Proposal payload field '{field_name}' must be a UUID."
    return normalized, None


def _proposal_payload_string(
    proposal: HarnessProposalRecord,
    *,
    field_name: str,
) -> tuple[str | None, str | None]:
    value = proposal.payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        return None, f"Proposal payload is missing '{field_name}'."
    return value.strip(), None


def _participants_match_claim(
    *,
    participants: list[ClaimParticipantResponse],
    source_entity_id: str,
    target_entity_id: str,
) -> bool:
    subject_entity_id: str | None = None
    object_entity_id: str | None = None
    for participant in participants:
        if participant.entity_id is None:
            continue
        entity_id = str(participant.entity_id)
        if participant.role == "SUBJECT" and subject_entity_id is None:
            subject_entity_id = entity_id
        elif participant.role == "OBJECT" and object_entity_id is None:
            object_entity_id = entity_id
    return (
        subject_entity_id == source_entity_id and object_entity_id == target_entity_id
    )


def _exact_graph_duplicates_for_proposal(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    space_id: UUID,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str,
    participant_cache: dict[str, list[ClaimParticipantResponse]],
    evidence_count_cache: dict[str, int],
) -> tuple[ClaimCurationGraphDuplicate, ...]:
    candidate_claims = run_list_claims_by_entity(
        runtime=runtime,
        run=run,
        arguments=ListClaimsByEntityToolArgs(
            space_id=str(space_id),
            entity_id=source_entity_id,
            limit=_GRAPH_DUPLICATE_CLAIM_LIMIT,
        ),
        step_key=f"claim_curation.claims_by_entity.{source_entity_id}",
    ).claims
    duplicates: list[ClaimCurationGraphDuplicate] = []
    for claim in candidate_claims:
        if claim.relation_type != relation_type or claim.polarity != "SUPPORT":
            continue
        cached_participants = participant_cache.get(str(claim.id))
        if cached_participants is None:
            cached_participants = run_list_claim_participants(
                runtime=runtime,
                run=run,
                arguments=ListClaimParticipantsToolArgs(
                    space_id=str(space_id),
                    claim_id=str(claim.id),
                ),
                step_key=f"claim_curation.claim_participants.{claim.id}",
            ).participants
            participant_cache[str(claim.id)] = cached_participants
        if not _participants_match_claim(
            participants=cached_participants,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
        ):
            continue
        evidence_count = evidence_count_cache.get(str(claim.id))
        if evidence_count is None:
            evidence_count = run_list_claim_evidence(
                runtime=runtime,
                run=run,
                arguments=ListClaimEvidenceToolArgs(
                    space_id=str(space_id),
                    claim_id=str(claim.id),
                ),
                step_key=f"claim_curation.claim_evidence.{claim.id}",
            ).total
            evidence_count_cache[str(claim.id)] = evidence_count
        duplicates.append(
            ClaimCurationGraphDuplicate(
                claim_id=str(claim.id),
                claim_status=claim.claim_status,
                validation_state=claim.validation_state,
                persistability=claim.persistability,
                confidence=claim.confidence,
                linked_relation_id=(
                    str(claim.linked_relation_id)
                    if claim.linked_relation_id is not None
                    else None
                ),
                source_label=claim.source_label,
                target_label=claim.target_label,
                evidence_count=evidence_count,
            ),
        )
    return tuple(
        sorted(
            duplicates,
            key=lambda duplicate: (
                duplicate.claim_status,
                duplicate.validation_state,
                duplicate.claim_id,
            ),
        ),
    )


def _conflict_map(
    conflicts: list[KernelRelationConflictResponse],
) -> dict[str, set[str]]:
    by_claim_id: dict[str, set[str]] = {}
    for conflict in conflicts:
        relation_id = str(conflict.relation_id)
        for claim_id in (*conflict.support_claim_ids, *conflict.refute_claim_ids):
            by_claim_id.setdefault(str(claim_id), set()).add(relation_id)
    return by_claim_id


def review_curatable_proposals(  # noqa: C901,PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    space_id: UUID,
    proposals: list[HarnessProposalRecord],
    proposal_store: HarnessProposalStore,
) -> list[ClaimCurationProposalReview]:
    """Assess duplicate, conflict, and invariant status for selected proposals."""
    duplicate_counts: dict[str, int] = {}
    for proposal in proposals:
        duplicate_counts[proposal.source_key] = (
            duplicate_counts.get(proposal.source_key, 0) + 1
        )

    promoted_duplicates_by_source_key: dict[str, list[str]] = {}
    for promoted in proposal_store.list_proposals(
        space_id=space_id,
        status="promoted",
    ):
        promoted_duplicates_by_source_key.setdefault(promoted.source_key, []).append(
            promoted.id,
        )

    participant_cache: dict[str, list[ClaimParticipantResponse]] = {}
    evidence_count_cache: dict[str, int] = {}
    conflict_lookup = _conflict_map(
        run_list_relation_conflicts(
            runtime=runtime,
            run=run,
            arguments=ListRelationConflictsToolArgs(
                space_id=str(space_id),
                limit=_GRAPH_CONFLICT_LIMIT,
            ),
            step_key="claim_curation.relation_conflicts",
        ).conflicts,
    )
    reviews: list[ClaimCurationProposalReview] = []
    for proposal in proposals:
        invariant_issues: list[str] = []
        blocker_reasons: list[str] = []
        source_entity_id, source_error = _proposal_payload_uuid(
            proposal,
            field_name="proposed_subject",
        )
        if source_error is not None:
            invariant_issues.append(source_error)
        target_entity_id, target_error = _proposal_payload_uuid(
            proposal,
            field_name="proposed_object",
        )
        if target_error is not None:
            invariant_issues.append(target_error)
        relation_type, relation_error = _proposal_payload_string(
            proposal,
            field_name="proposed_claim_type",
        )
        if relation_error is not None:
            invariant_issues.append(relation_error)
        if (
            source_entity_id is not None
            and target_entity_id is not None
            and source_entity_id == target_entity_id
        ):
            invariant_issues.append(
                "Proposed subject and object must not be the same entity.",
            )

        graph_duplicates: tuple[ClaimCurationGraphDuplicate, ...] = ()
        conflicting_relation_ids: tuple[str, ...] = ()
        if (
            source_entity_id is not None
            and target_entity_id is not None
            and relation_type is not None
            and not invariant_issues
        ):
            graph_duplicates = _exact_graph_duplicates_for_proposal(
                runtime=runtime,
                run=run,
                space_id=space_id,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type=relation_type,
                participant_cache=participant_cache,
                evidence_count_cache=evidence_count_cache,
            )
            conflicting_relation_ids = tuple(
                sorted(
                    {
                        relation_id
                        for duplicate in graph_duplicates
                        for relation_id in conflict_lookup.get(
                            duplicate.claim_id,
                            set(),
                        )
                    },
                ),
            )

        if duplicate_counts.get(proposal.source_key, 0) > 1:
            blocker_reasons.append(
                "Selection contains duplicate proposals for the same source key.",
            )
        existing_promoted_proposal_ids = tuple(
            promoted_duplicates_by_source_key.get(proposal.source_key, []),
        )
        if existing_promoted_proposal_ids:
            blocker_reasons.append(
                "Previously promoted harness proposals already exist for this source key.",
            )
        if graph_duplicates:
            blocker_reasons.append(
                "Exact matching graph claims already exist for this proposed claim.",
            )
        blocker_reasons.extend(invariant_issues)

        reviews.append(
            ClaimCurationProposalReview(
                proposal=proposal,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type=relation_type,
                duplicate_selected_count=duplicate_counts.get(proposal.source_key, 0),
                existing_promoted_proposal_ids=existing_promoted_proposal_ids,
                graph_duplicates=graph_duplicates,
                conflicting_relation_ids=conflicting_relation_ids,
                invariant_issues=tuple(invariant_issues),
                blocker_reasons=tuple(blocker_reasons),
                eligible_for_approval=not blocker_reasons,
            ),
        )
    return reviews


def build_curation_packet(
    *,
    reviews: list[ClaimCurationProposalReview],
) -> JSONObject:
    """Build the rich curation-preflight artifact for one curation run."""
    return {
        "proposal_count": len(reviews),
        "eligible_proposal_count": sum(
            1 for review in reviews if review.eligible_for_approval
        ),
        "blocked_proposal_count": sum(
            1 for review in reviews if not review.eligible_for_approval
        ),
        "graph_duplicate_claim_count": sum(
            len(review.graph_duplicates) for review in reviews
        ),
        "graph_conflict_count": sum(
            len(review.conflicting_relation_ids) for review in reviews
        ),
        "invariant_issue_count": sum(
            len(review.invariant_issues) for review in reviews
        ),
        "proposals": [
            {
                "proposal_id": review.proposal.id,
                "title": review.proposal.title,
                "summary": review.proposal.summary,
                "source_key": review.proposal.source_key,
                "source_entity_id": review.source_entity_id,
                "target_entity_id": review.target_entity_id,
                "relation_type": review.relation_type,
                "eligible_for_approval": review.eligible_for_approval,
                "blocker_reasons": list(review.blocker_reasons),
                "invariant_issues": list(review.invariant_issues),
                "existing_promoted_proposal_ids": list(
                    review.existing_promoted_proposal_ids,
                ),
                "graph_duplicate_claims": [
                    {
                        "claim_id": duplicate.claim_id,
                        "claim_status": duplicate.claim_status,
                        "validation_state": duplicate.validation_state,
                        "persistability": duplicate.persistability,
                        "confidence": duplicate.confidence,
                        "linked_relation_id": duplicate.linked_relation_id,
                        "source_label": duplicate.source_label,
                        "target_label": duplicate.target_label,
                        "evidence_count": duplicate.evidence_count,
                    }
                    for duplicate in review.graph_duplicates
                ],
                "conflicting_relation_ids": list(review.conflicting_relation_ids),
            }
            for review in reviews
        ],
    }


def build_review_plan(
    *,
    reviews: list[ClaimCurationProposalReview],
) -> JSONObject:
    """Build the review-plan artifact payload for one curation run."""
    warnings: list[str] = []
    for review in reviews:
        if review.duplicate_selected_count > 1:
            warnings.append(
                "Selected proposals include multiple entries for source_key "
                f"'{review.proposal.source_key}'.",
            )
        if review.existing_promoted_proposal_ids:
            warnings.append(
                "Previously promoted proposals already exist for source_key "
                f"'{review.proposal.source_key}': "
                f"{', '.join(review.existing_promoted_proposal_ids)}",
            )
        if review.graph_duplicates:
            warnings.append(
                f"Graph duplicates already exist for proposal '{review.proposal.id}'.",
            )
        if review.conflicting_relation_ids:
            warnings.append(
                f"Graph conflicts already exist for proposal '{review.proposal.id}'.",
            )
        warnings.extend(
            f"Proposal '{review.proposal.id}': {issue}"
            for issue in review.invariant_issues
        )

    return {
        "proposal_count": len(reviews),
        "eligible_proposal_count": sum(
            1 for review in reviews if review.eligible_for_approval
        ),
        "blocked_proposal_count": sum(
            1 for review in reviews if not review.eligible_for_approval
        ),
        "proposal_ids": [review.proposal.id for review in reviews],
        "warnings": warnings,
        "warning_count": len(warnings),
        "proposals": [
            {
                "proposal_id": review.proposal.id,
                "title": review.proposal.title,
                "summary": review.proposal.summary,
                "proposal_type": review.proposal.proposal_type,
                "source_kind": review.proposal.source_kind,
                "source_key": review.proposal.source_key,
                "confidence": review.proposal.confidence,
                "ranking_score": review.proposal.ranking_score,
                "approval_key": approval_key_for_proposal(review.proposal.id),
                "duplicate_selected_count": review.duplicate_selected_count,
                "existing_promoted_proposal_ids": list(
                    review.existing_promoted_proposal_ids,
                ),
                "graph_duplicate_claim_ids": [
                    duplicate.claim_id for duplicate in review.graph_duplicates
                ],
                "conflicting_relation_ids": list(review.conflicting_relation_ids),
                "invariant_issues": list(review.invariant_issues),
                "blocker_reasons": list(review.blocker_reasons),
                "eligible_for_approval": review.eligible_for_approval,
                "payload": review.proposal.payload,
                "metadata": review.proposal.metadata,
            }
            for review in reviews
        ],
    }


def build_approval_actions(
    *,
    reviews: list[ClaimCurationProposalReview],
) -> tuple[HarnessApprovalAction, ...]:
    """Build approval-gated actions for one curation run."""
    return tuple(
        HarnessApprovalAction(
            approval_key=approval_key_for_proposal(review.proposal.id),
            title=f"Apply proposal: {review.proposal.title}",
            risk_level="high",
            target_type="proposal",
            target_id=review.proposal.id,
            requires_approval=True,
            metadata={
                "proposal_id": review.proposal.id,
                "proposal_type": review.proposal.proposal_type,
                "source_key": review.proposal.source_key,
                "source_kind": review.proposal.source_kind,
            },
        )
        for review in reviews
        if review.eligible_for_approval
    )


def build_approval_intent_artifact(
    *,
    run_id: str,
    summary: str,
    actions: tuple[HarnessApprovalAction, ...],
) -> JSONObject:
    """Build the approval-intent artifact payload for one curation run."""
    return {
        "run_id": run_id,
        "summary": summary,
        "pending_approval_count": len(actions),
        "actions": [
            {
                "approval_key": action.approval_key,
                "title": action.title,
                "risk_level": action.risk_level,
                "target_type": action.target_type,
                "target_id": action.target_id,
                "requires_approval": action.requires_approval,
                "metadata": action.metadata,
            }
            for action in actions
        ],
    }


def build_curation_summary(
    *,
    run_id: str,
    action_results: list[JSONObject],
    resume_reason: str | None,
) -> JSONObject:
    """Build the summary artifact for a completed curation run."""
    promoted_count = sum(
        1 for action in action_results if action.get("decision_status") == "promoted"
    )
    rejected_count = sum(
        1 for action in action_results if action.get("decision_status") == "rejected"
    )
    return {
        "run_id": run_id,
        "action_count": len(action_results),
        "promoted_count": promoted_count,
        "rejected_count": rejected_count,
        "resume_reason": resume_reason,
        "applied_proposal_ids": [
            action["proposal_id"]
            for action in action_results
            if isinstance(action.get("proposal_id"), str)
        ],
    }


def _normalized_run_proposal_ids(run: HarnessRunRecord) -> tuple[str, ...]:
    raw_ids = run.input_payload.get("proposal_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Claim-curation run '{run.id}' is missing proposal_ids in its "
                "workflow payload"
            ),
        )
    normalized_ids: list[str] = []
    for value in raw_ids:
        if not isinstance(value, str) or value.strip() == "":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Claim-curation run '{run.id}' contains an invalid proposal id "
                    "in its workflow payload"
                ),
            )
        normalized_ids.append(value.strip())
    return tuple(normalized_ids)


def _approval_for_proposal(
    *,
    approvals_by_key: dict[str, HarnessApprovalRecord],
    approval_key: str,
    run_id: str,
) -> HarnessApprovalRecord:
    approval = approvals_by_key.get(approval_key)
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Claim-curation run '{run_id}' is missing approval "
                f"'{approval_key}'"
            ),
        )
    return approval


def _raise_invalid_approval_status(
    *,
    run_id: str,
    approval_key: str,
    approval_status: str,
) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"Claim-curation run '{run_id}' cannot apply approval "
            f"'{approval_key}' with status '{approval_status}'"
        ),
    )


def _mark_run_failed(  # noqa: PLR0913
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    error_message: str,
    partial_action_results: list[JSONObject],
) -> None:
    """Persist a failed curation-resume outcome."""
    failed_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="failed",
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="failed",
        message=error_message,
        progress_percent=1.0,
        completed_steps=len(partial_action_results),
        total_steps=len(partial_action_results) or None,
        clear_resume_point=True,
        metadata={"failed_action_count": len(partial_action_results)},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="claim_curation_error",
        media_type="application/json",
        content={
            "run_id": run.id,
            "error": error_message,
            "partial_action_results": partial_action_results,
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "failed",
            "error": error_message,
            "failed_action_count": len(partial_action_results),
            "last_claim_curation_error_key": "claim_curation_error",
        },
    )
    if failed_run is not None:
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="claim_curation.failed",
            message=error_message,
            payload={"partial_action_count": len(partial_action_results)},
            progress_percent=1.0,
        )


def resume_claim_curation_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    approval_store: HarnessApprovalStore,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    runtime: GraphHarnessKernelRuntime,
    graph_api_gateway: GraphTransportBundle,
    resume_reason: str | None,
    resume_metadata: JSONObject,
) -> tuple[HarnessRunRecord, HarnessRunProgressRecord]:
    """Apply approved claim-curation actions and complete the run."""
    proposal_ids = _normalized_run_proposal_ids(run)
    approvals = approval_store.list_approvals(space_id=space_id, run_id=run.id)
    approvals_by_key = {approval.approval_key: approval for approval in approvals}
    action_results: list[JSONObject] = []
    total_steps = len(proposal_ids)

    run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="running",
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "running",
            "pending_approvals": 0,
        },
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="curation_apply",
        message="Applying approved claim-curation actions.",
        progress_percent=_RUNNING_PROGRESS_START,
        completed_steps=0,
        total_steps=total_steps,
        clear_resume_point=True,
        metadata={
            **resume_metadata,
            "resume_reason": resume_reason or "manual_resume",
        },
    )

    try:
        for index, proposal_id in enumerate(proposal_ids, start=1):
            approval_key = approval_key_for_proposal(proposal_id)
            approval = _approval_for_proposal(
                approvals_by_key=approvals_by_key,
                approval_key=approval_key,
                run_id=run.id,
            )
            proposal = require_proposal(
                space_id=space_id,
                proposal_id=proposal_id,
                proposal_store=proposal_store,
            )
            action_metadata = {
                **resume_metadata,
                "curation_run_id": run.id,
                "approval_key": approval.approval_key,
                "approval_status": approval.status,
            }
            if approval.status == "approved":
                promotion_metadata = promote_to_graph_claim(
                    space_id=space_id,
                    proposal=proposal,
                    request_metadata=action_metadata,
                    graph_api_gateway=graph_api_gateway,
                )
                updated_proposal = decide_proposal(
                    space_id=space_id,
                    proposal_id=proposal_id,
                    decision_status="promoted",
                    decision_reason=approval.decision_reason,
                    request_metadata=action_metadata,
                    proposal_store=proposal_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    decision_metadata=promotion_metadata,
                    event_payload={
                        **promotion_metadata,
                        "curation_run_id": run.id,
                    },
                    workspace_patch={
                        "last_promoted_graph_claim_id": promotion_metadata[
                            "graph_claim_id"
                        ],
                        "last_promoted_graph_relation_id": promotion_metadata.get(
                            "graph_relation_id",
                        ),
                    },
                )
                action_results.append(
                    {
                        "proposal_id": proposal.id,
                        "approval_key": approval.approval_key,
                        "decision_status": "promoted",
                        "graph_claim_id": promotion_metadata["graph_claim_id"],
                        "graph_claim_status": promotion_metadata["graph_claim_status"],
                        "decision_reason": approval.decision_reason,
                        "updated_at": updated_proposal.updated_at.isoformat(),
                    },
                )
            elif approval.status == "rejected":
                updated_proposal = decide_proposal(
                    space_id=space_id,
                    proposal_id=proposal_id,
                    decision_status="rejected",
                    decision_reason=approval.decision_reason,
                    request_metadata=action_metadata,
                    proposal_store=proposal_store,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                )
                action_results.append(
                    {
                        "proposal_id": proposal.id,
                        "approval_key": approval.approval_key,
                        "decision_status": "rejected",
                        "decision_reason": approval.decision_reason,
                        "updated_at": updated_proposal.updated_at.isoformat(),
                    },
                )
            else:
                _raise_invalid_approval_status(
                    run_id=run.id,
                    approval_key=approval.approval_key,
                    approval_status=approval.status,
                )

            progress_percent = _RUNNING_PROGRESS_START + (
                (index / total_steps) * _RUNNING_PROGRESS_SPAN
            )
            run_registry.set_progress(
                space_id=space_id,
                run_id=run.id,
                phase="curation_apply",
                message=f"Applied {index} of {total_steps} curation actions.",
                progress_percent=progress_percent,
                completed_steps=index,
                total_steps=total_steps,
                metadata={
                    **resume_metadata,
                    "resume_reason": resume_reason or "manual_resume",
                },
            )
            run_registry.record_event(
                space_id=space_id,
                run_id=run.id,
                event_type="claim_curation.action_applied",
                message=(
                    f"Applied {approval.status} decision for proposal '{proposal.id}'."
                ),
                payload=action_results[-1],
                progress_percent=progress_percent,
            )
    except HTTPException as exc:
        _mark_run_failed(
            space_id=space_id,
            run=run,
            artifact_store=artifact_store,
            run_registry=run_registry,
            error_message=exc.detail,
            partial_action_results=action_results,
        )
        raise
    except Exception as exc:
        _mark_run_failed(
            space_id=space_id,
            run=run,
            artifact_store=artifact_store,
            run_registry=run_registry,
            error_message=f"Claim-curation run failed: {exc}",
            partial_action_results=action_results,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Claim-curation run failed: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()

    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="curation_actions",
        media_type="application/json",
        content={
            "run_id": run.id,
            "action_count": len(action_results),
            "actions": action_results,
        },
    )
    curation_summary = build_curation_summary(
        run_id=run.id,
        action_results=action_results,
        resume_reason=resume_reason,
    )
    if curation_summary["promoted_count"] > 0:
        append_skill_activity(
            space_id=space_id,
            run_id=run.id,
            skill_names=("graph_harness.governed_graph_write",),
            source_run_id=run.id,
            source_kind="claim_curation",
            artifact_store=artifact_store,
            run_registry=run_registry,
            runtime=runtime,
        )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="curation_summary",
        media_type="application/json",
        content=curation_summary,
    )
    completed_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    completed_progress = run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="completed",
        message="Claim-curation run completed.",
        progress_percent=1.0,
        completed_steps=total_steps,
        total_steps=total_steps,
        clear_resume_point=True,
        metadata={
            **resume_metadata,
            "resume_reason": resume_reason or "manual_resume",
            "action_count": len(action_results),
            "promoted_count": curation_summary["promoted_count"],
            "rejected_count": curation_summary["rejected_count"],
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "pending_approvals": 0,
            "last_curation_actions_key": "curation_actions",
            "last_curation_summary_key": "curation_summary",
            "curation_action_count": len(action_results),
            "curation_action_counts": {
                "promoted": curation_summary["promoted_count"],
                "rejected": curation_summary["rejected_count"],
            },
        },
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="claim_curation.applied",
        message="Claim-curation actions applied.",
        payload=curation_summary,
        progress_percent=1.0,
    )
    if completed_run is None or completed_progress is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Claim-curation run '{run.id}' could not be completed",
        )
    return completed_run, completed_progress


__all__ = [
    "approval_key_for_proposal",
    "build_approval_actions",
    "build_approval_intent_artifact",
    "build_curation_packet",
    "build_review_plan",
    "is_claim_curation_workflow",
    "load_curatable_proposals",
    "normalize_requested_proposal_ids",
    "review_curatable_proposals",
    "resume_claim_curation_run",
]
