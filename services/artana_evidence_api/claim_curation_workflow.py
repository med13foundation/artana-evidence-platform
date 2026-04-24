"""Reusable claim-curation workflow helpers for composed harness runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from artana_evidence_api.claim_curation_runtime import (
    build_approval_actions,
    build_approval_intent_artifact,
    build_curation_packet,
    build_review_plan,
    review_curatable_proposals,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.response_serialization import serialize_run_record
from artana_evidence_api.transparency import (
    append_skill_activity,
    ensure_run_transparency_seed,
)
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from uuid import UUID

    from artana_evidence_api.approval_store import (
        HarnessApprovalAction,
        HarnessApprovalStore,
    )
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.claim_curation_runtime import (
        ClaimCurationProposalReview,
    )
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.proposal_store import (
        HarnessProposalRecord,
        HarnessProposalStore,
    )
    from artana_evidence_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.types.common import JSONObject


class ClaimCurationNoEligibleProposalsError(RuntimeError):
    """Raised when no selected proposals remain eligible for governed review."""


@dataclass(frozen=True, slots=True)
class ClaimCurationRunExecution:
    """One created claim-curation run paused at the approval gate."""

    run: HarnessRunRecord
    curation_packet: JSONObject
    review_plan: JSONObject
    approval_intent: JSONObject
    proposal_count: int
    blocked_proposal_count: int
    pending_approval_count: int


def _raise_no_eligible_proposals_error() -> None:
    error_message = (
        "No eligible proposals remain for claim curation after duplicate, "
        "conflict, and invariant checks."
    )
    raise ClaimCurationNoEligibleProposalsError(error_message)


def _selected_proposals_response_payload(
    *,
    review_plan: JSONObject,
) -> list[JSONObject]:
    proposals_value = review_plan.get("proposals")
    if not isinstance(proposals_value, list):
        return []
    selected: list[JSONObject] = []
    for item in proposals_value:
        if not isinstance(item, dict):
            continue
        selected.append(
            {
                "proposal_id": str(item["proposal_id"]),
                "title": str(item["title"]),
                "summary": str(item["summary"]),
                "source_key": str(item["source_key"]),
                "confidence": float(item["confidence"]),
                "ranking_score": float(item["ranking_score"]),
                "approval_key": str(item["approval_key"]),
                "duplicate_selected_count": int(item["duplicate_selected_count"]),
                "existing_promoted_proposal_ids": [
                    str(value)
                    for value in item.get("existing_promoted_proposal_ids", [])
                    if isinstance(value, str)
                ],
                "graph_duplicate_claim_ids": [
                    str(value)
                    for value in item.get("graph_duplicate_claim_ids", [])
                    if isinstance(value, str)
                ],
                "conflicting_relation_ids": [
                    str(value)
                    for value in item.get("conflicting_relation_ids", [])
                    if isinstance(value, str)
                ],
                "invariant_issues": [
                    str(value)
                    for value in item.get("invariant_issues", [])
                    if isinstance(value, str)
                ],
                "blocker_reasons": [
                    str(value)
                    for value in item.get("blocker_reasons", [])
                    if isinstance(value, str)
                ],
                "eligible_for_approval": bool(
                    item.get("eligible_for_approval", False),
                ),
            },
        )
    return selected


def build_claim_curation_run_input_payload(
    *,
    reviews: list[ClaimCurationProposalReview] | None = None,
    proposal_ids: list[str] | None = None,
    blocked_proposal_ids: list[str] | None = None,
) -> JSONObject:
    if reviews is not None:
        selected_proposal_ids = [
            review.proposal.id
            for review in reviews
            if getattr(review, "eligible_for_approval", False)
        ]
        blocked_ids = [
            review.proposal.id
            for review in reviews
            if not getattr(review, "eligible_for_approval", False)
        ]
    else:
        selected_proposal_ids = list(proposal_ids or [])
        blocked_ids = list(blocked_proposal_ids or [])
    return {
        "workflow": "claim_curation",
        "proposal_ids": selected_proposal_ids,
        "blocked_proposal_ids": blocked_ids,
    }


def queue_claim_curation_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    proposal_ids: list[str],
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="claim-curation",
        title=title,
        input_payload=build_claim_curation_run_input_payload(proposal_ids=proposal_ids),
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "claim_curation_proposal_count": len(proposal_ids),
            "blocked_claim_curation_proposal_count": 0,
        },
    )
    return run


def _json_int(payload: JSONObject, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _json_list_length(payload: JSONObject, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, list):
        return len(value)
    return 0


def _cleanup_claim_curation_run(
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
) -> None:
    artifact_store.delete_run(space_id=space_id, run_id=run_id)
    run_registry.delete_run(space_id=space_id, run_id=run_id)


def _mark_claim_curation_setup_failed(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    error_message: str,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
) -> None:
    current_progress = run_registry.get_progress(space_id=space_id, run_id=run.id)
    failed_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="failed",
        existing_progress=current_progress,
    )
    progress_percent = (
        current_progress.progress_percent if current_progress is not None else 0.0
    )
    completed_steps = (
        current_progress.completed_steps if current_progress is not None else 0
    )
    total_steps = current_progress.total_steps if current_progress is not None else None
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="failed",
        message=error_message,
        progress_percent=progress_percent,
        completed_steps=completed_steps,
        total_steps=total_steps,
        clear_resume_point=True,
        metadata={"error": error_message, "failed_during": "claim_curation_setup"},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="claim_curation_error",
        media_type="application/json",
        content={
            "run_id": run.id,
            "error": error_message,
            "phase": "claim_curation_setup",
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "failed",
            "error": error_message,
            "last_claim_curation_error_key": "claim_curation_error",
        },
    )
    if failed_run is not None:
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="claim_curation.failed",
            message=error_message,
            payload={"phase": "claim_curation_setup"},
            progress_percent=progress_percent,
        )


def _load_claim_curation_reviews(  # noqa: PLR0913
    *,
    space_id: UUID,
    proposals: list[HarnessProposalRecord],
    title: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    graph_api_gateway: GraphTransportBundle,
    runtime: GraphHarnessKernelRuntime,
    existing_run: HarnessRunRecord | None,
) -> tuple[HarnessRunRecord, list[ClaimCurationProposalReview]]:
    run: HarnessRunRecord | None = existing_run
    try:
        graph_health = graph_api_gateway.get_health()
        if existing_run is None:
            run = queue_claim_curation_run(
                space_id=space_id,
                title=title,
                proposal_ids=[proposal.id for proposal in proposals],
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
            ensure_run_transparency_seed(
                run=run,
                artifact_store=artifact_store,
                runtime=runtime,
            )
        else:
            run = existing_run
            if artifact_store.get_workspace(space_id=space_id, run_id=run.id) is None:
                artifact_store.seed_for_run(run=run)
            ensure_run_transparency_seed(
                run=run,
                artifact_store=artifact_store,
                runtime=runtime,
            )
        reviews = review_curatable_proposals(
            runtime=runtime,
            run=run,
            space_id=space_id,
            proposals=proposals,
            proposal_store=proposal_store,
        )
    except Exception:
        if existing_run is None and run is not None:
            artifact_store.delete_run(space_id=space_id, run_id=run.id)
            run_registry.delete_run(space_id=space_id, run_id=run.id)
        raise
    finally:
        graph_api_gateway.close()

    return run, reviews


def _store_claim_curation_pause_state(  # noqa: PLR0913
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    proposals: list[HarnessProposalRecord],
    reviews: list[ClaimCurationProposalReview],
    curation_packet: JSONObject,
    review_plan: JSONObject,
    approval_actions: tuple[HarnessApprovalAction, ...],
    approval_store: HarnessApprovalStore,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
) -> ClaimCurationRunExecution:
    approval_summary = f"Review {len(approval_actions)} eligible proposal(s) for graph claim promotion."
    updated_run = run_registry.replace_run_input_payload(
        space_id=space_id,
        run_id=run.id,
        input_payload=build_claim_curation_run_input_payload(reviews=reviews),
    )
    if updated_run is not None:
        run = updated_run
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="review",
        message="Built claim-curation review plan.",
        progress_percent=0.35,
        completed_steps=1,
        total_steps=2,
        metadata={"proposal_count": len(proposals)},
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "running",
            "claim_curation_proposal_count": len(proposals),
            "blocked_claim_curation_proposal_count": _json_int(
                curation_packet,
                "blocked_proposal_count",
            ),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="curation_packet",
        media_type="application/json",
        content=curation_packet,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="review_plan",
        media_type="application/json",
        content=review_plan,
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="claim_curation.review_built",
        message=f"Built review plan for {len(proposals)} proposal(s).",
        payload={
            "proposal_ids": [proposal.id for proposal in proposals],
            "warning_count": _json_list_length(review_plan, "warnings"),
            "blocked_proposal_count": _json_int(
                review_plan,
                "blocked_proposal_count",
            ),
        },
        progress_percent=0.35,
    )

    approval_store.upsert_intent(
        space_id=space_id,
        run_id=run.id,
        summary=approval_summary,
        proposed_actions=approval_actions,
        metadata={
            "intent_kind": "claim_curation",
            "proposal_ids": [
                review.proposal.id for review in reviews if review.eligible_for_approval
            ],
            "blocked_proposal_ids": [
                review.proposal.id
                for review in reviews
                if not review.eligible_for_approval
            ],
        },
    )
    approvals = approval_store.list_approvals(space_id=space_id, run_id=run.id)
    approval_intent = build_approval_intent_artifact(
        run_id=run.id,
        summary=approval_summary,
        actions=approval_actions,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="approval_intent",
        media_type="application/json",
        content=approval_intent,
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="run.intent_recorded",
        message="Run intent plan recorded.",
        payload={
            "summary": approval_summary,
            "approval_count": len(approvals),
        },
        progress_percent=0.5,
    )
    paused_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="paused",
    )
    paused_progress = run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="approval",
        message="Run paused pending curator approval.",
        progress_percent=0.5,
        completed_steps=1,
        total_steps=2,
        resume_point="approval_gate",
        metadata={"pending_approvals": len(approvals)},
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="run.paused",
        message="Run paused at approval gate.",
        payload={"pending_approvals": len(approvals)},
        progress_percent=(
            paused_progress.progress_percent if paused_progress is not None else 0.5
        ),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "paused",
            "resume_point": "approval_gate",
            "pending_approvals": len(approvals),
            "blocked_proposal_count": _json_int(
                review_plan,
                "blocked_proposal_count",
            ),
            "last_curation_packet_key": "curation_packet",
            "last_review_plan_key": "review_plan",
            "last_approval_intent_key": "approval_intent",
        },
    )
    final_run = paused_run or run
    store_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key="claim_curation_response",
        content={
            "run": serialize_run_record(run=final_run),
            "curation_packet_key": "curation_packet",
            "review_plan_key": "review_plan",
            "approval_intent_key": "approval_intent",
            "proposal_count": len(proposals),
            "blocked_proposal_count": _json_int(review_plan, "blocked_proposal_count"),
            "pending_approval_count": len(approvals),
            "proposals": _selected_proposals_response_payload(
                review_plan=review_plan,
            ),
        },
        status_value="paused",
        result_keys=("curation_packet", "review_plan", "approval_intent"),
    )
    return ClaimCurationRunExecution(
        run=final_run,
        curation_packet=curation_packet,
        review_plan=review_plan,
        approval_intent=approval_intent,
        proposal_count=len(proposals),
        blocked_proposal_count=_json_int(review_plan, "blocked_proposal_count"),
        pending_approval_count=len(approvals),
    )


def execute_claim_curation_run_for_proposals(  # noqa: PLR0913
    *,
    space_id: UUID,
    proposals: list[HarnessProposalRecord],
    title: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    approval_store: HarnessApprovalStore,
    graph_api_gateway: GraphTransportBundle,
    runtime: GraphHarnessKernelRuntime,
    existing_run: HarnessRunRecord | None = None,
) -> ClaimCurationRunExecution:
    """Create one approval-gated claim-curation run from selected proposals."""
    run, reviews = _load_claim_curation_reviews(
        space_id=space_id,
        proposals=proposals,
        title=title,
        run_registry=run_registry,
        artifact_store=artifact_store,
        proposal_store=proposal_store,
        graph_api_gateway=graph_api_gateway,
        runtime=runtime,
        existing_run=existing_run,
    )
    try:
        append_skill_activity(
            space_id=space_id,
            run_id=run.id,
            skill_names=("graph_harness.claim_validation",),
            source_run_id=run.id,
            source_kind="claim_curation",
            artifact_store=artifact_store,
            run_registry=run_registry,
            runtime=runtime,
        )

        if not any(review.eligible_for_approval for review in reviews):
            if existing_run is None:
                _cleanup_claim_curation_run(
                    space_id=space_id,
                    run_id=run.id,
                    artifact_store=artifact_store,
                    run_registry=run_registry,
                )
            _raise_no_eligible_proposals_error()

        curation_packet = build_curation_packet(reviews=reviews)
        review_plan = build_review_plan(reviews=reviews)
        approval_actions = build_approval_actions(reviews=reviews)
        return _store_claim_curation_pause_state(
            space_id=space_id,
            run=run,
            proposals=proposals,
            reviews=reviews,
            curation_packet=curation_packet,
            review_plan=review_plan,
            approval_actions=approval_actions,
            approval_store=approval_store,
            artifact_store=artifact_store,
            run_registry=run_registry,
        )
    except ClaimCurationNoEligibleProposalsError:
        raise
    except Exception as exc:
        if existing_run is None:
            _cleanup_claim_curation_run(
                space_id=space_id,
                run_id=run.id,
                artifact_store=artifact_store,
                run_registry=run_registry,
            )
        else:
            _mark_claim_curation_setup_failed(
                space_id=space_id,
                run=run,
                error_message=f"Failed to initialize claim curation: {exc}",
                artifact_store=artifact_store,
                run_registry=run_registry,
            )
        raise


__all__ = [
    "ClaimCurationNoEligibleProposalsError",
    "ClaimCurationRunExecution",
    "build_claim_curation_run_input_payload",
    "execute_claim_curation_run_for_proposals",
    "queue_claim_curation_run",
]
