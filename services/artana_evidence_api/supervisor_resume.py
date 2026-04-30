"""Supervisor approval-resume reconciliation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.claim_curation_runtime import resume_claim_curation_run
from artana_evidence_api.supervisor_child_activity import (
    _propagate_child_skill_activity,
)
from artana_evidence_api.supervisor_payloads import (
    _SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY,
    _SUPERVISOR_SUMMARY_ARTIFACT_KEY,
    _claim_curation_response_payload,
    _json_object_sequence,
    _load_supervisor_summary,
    _summary_steps_with_updated_curation_status,
    _supervisor_child_curation_run_id,
    _write_supervisor_artifacts,
)

if TYPE_CHECKING:
    from uuid import UUID

    from artana_evidence_api.approval_store import HarnessApprovalStore
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.run_registry import (
        HarnessRunProgressRecord,
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.types.common import JSONObject

def resume_supervisor_run(  # noqa: PLR0913, PLR0915
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
    """Resume one paused supervisor run by reconciling the child curation run."""
    curation_run_id = _supervisor_child_curation_run_id(
        space_id=space_id,
        run_id=run.id,
        artifact_store=artifact_store,
    )
    if curation_run_id is None:
        graph_api_gateway.close()
        error_message = f"Supervisor run '{run.id}' has no child curation run to resume"
        raise RuntimeError(error_message)
    curation_run = run_registry.get_run(space_id=space_id, run_id=curation_run_id)
    if curation_run is None:
        graph_api_gateway.close()
        error_message = (
            f"Supervisor child curation run '{curation_run_id}' was not found"
        )
        raise RuntimeError(error_message)

    child_approvals = approval_store.list_approvals(
        space_id=space_id,
        run_id=curation_run.id,
    )
    pending_approvals = [
        approval.approval_key
        for approval in child_approvals
        if approval.status == "pending"
    ]
    if pending_approvals:
        graph_api_gateway.close()
        raise RuntimeError(
            (
                f"Supervisor run '{run.id}' cannot resume while child curation run "
                f"'{curation_run.id}' has pending approvals: "
            )
            + ", ".join(pending_approvals),
        )

    current_progress = run_registry.get_progress(space_id=space_id, run_id=run.id)
    total_steps = (
        current_progress.total_steps
        if current_progress is not None and current_progress.total_steps is not None
        else 0
    )
    completed_steps = (
        current_progress.completed_steps if current_progress is not None else 0
    )
    run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="running",
        existing_progress=current_progress,
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "running",
            "pending_approvals": 0,
            "resume_point": None,
        },
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="curation_resume",
        message="Reconciling child curation run.",
        progress_percent=(
            current_progress.progress_percent if current_progress is not None else 0.0
        ),
        completed_steps=completed_steps,
        total_steps=total_steps,
        clear_resume_point=True,
        metadata={
            **resume_metadata,
            "resume_reason": resume_reason or "manual_resume",
            "child_curation_run_id": curation_run.id,
        },
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="supervisor.resumed",
        message="Supervisor run resumed to reconcile child curation.",
        payload={
            "reason": resume_reason,
            "metadata": resume_metadata,
            "child_curation_run_id": curation_run.id,
        },
        progress_percent=(
            current_progress.progress_percent if current_progress is not None else 0.0
        ),
    )

    completed_curation_run = curation_run
    if curation_run.status == "paused":
        completed_curation_run, _ = resume_claim_curation_run(
            space_id=space_id,
            run=curation_run,
            approval_store=approval_store,
            proposal_store=proposal_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            runtime=runtime,
            graph_api_gateway=graph_api_gateway,
            resume_reason=resume_reason,
            resume_metadata=resume_metadata,
        )
    elif curation_run.status == "completed":
        graph_api_gateway.close()
    else:
        graph_api_gateway.close()
        error_message = (
            f"Supervisor child curation run '{curation_run.id}' has unsupported "
            f"status '{curation_run.status}'"
        )
        raise RuntimeError(error_message)

    _propagate_child_skill_activity(
        space_id=space_id,
        parent_run_id=run.id,
        child_run_id=completed_curation_run.id,
        source_kind="claim_curation",
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )

    curation_summary_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=completed_curation_run.id,
        artifact_key="curation_summary",
    )
    curation_actions_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=completed_curation_run.id,
        artifact_key="curation_actions",
    )
    review_plan_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=completed_curation_run.id,
        artifact_key="review_plan",
    )
    if (
        curation_summary_artifact is None
        or curation_actions_artifact is None
        or review_plan_artifact is None
    ):
        error_message = (
            "Completed child curation run "
            f"'{completed_curation_run.id}' is missing summary artifacts"
        )
        raise RuntimeError(error_message)

    existing_summary = _load_supervisor_summary(
        space_id=space_id,
        run_id=run.id,
        artifact_store=artifact_store,
    )
    existing_steps = (
        existing_summary.get("steps")
        if isinstance(existing_summary.get("steps"), list)
        else []
    )
    updated_steps = _summary_steps_with_updated_curation_status(
        steps=list(_json_object_sequence(existing_steps)),
        curation_run_id=completed_curation_run.id,
        status="completed",
        detail="Claim-curation run completed through supervisor resume.",
    )
    completed_steps = total_steps
    summary_content: JSONObject = {
        **existing_summary,
        "curation_run_id": completed_curation_run.id,
        "curation_status": completed_curation_run.status,
        "completed_at": None,
        "curation_response": _claim_curation_response_payload(
            run=completed_curation_run,
            review_plan=review_plan_artifact.content,
            pending_approval_count=0,
        ),
        "curation_summary": curation_summary_artifact.content,
        "curation_actions": curation_actions_artifact.content,
        "steps": updated_steps,
    }
    completed_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    summary_content["completed_at"] = (
        completed_run.updated_at.isoformat() if completed_run is not None else None
    )
    _write_supervisor_artifacts(
        space_id=space_id,
        run_id=run.id,
        bootstrap_run_id=str(existing_summary.get("bootstrap_run_id") or ""),
        chat_run_id=(
            str(existing_summary["chat_run_id"])
            if isinstance(existing_summary.get("chat_run_id"), str)
            else None
        ),
        chat_session_id=(
            str(existing_summary["chat_session_id"])
            if isinstance(existing_summary.get("chat_session_id"), str)
            else None
        ),
        curation_run_id=completed_curation_run.id,
        curation_status=completed_curation_run.status,
        summary_content=summary_content,
        artifact_store=artifact_store,
    )
    completed_progress = run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="completed",
        message="Supervisor workflow completed.",
        progress_percent=1.0,
        completed_steps=completed_steps,
        total_steps=total_steps,
        clear_resume_point=True,
        metadata={
            **resume_metadata,
            "resume_reason": resume_reason or "manual_resume",
            "child_curation_run_id": completed_curation_run.id,
            "promoted_count": curation_summary_artifact.content.get(
                "promoted_count",
                0,
            ),
            "rejected_count": curation_summary_artifact.content.get(
                "rejected_count",
                0,
            ),
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "resume_point": None,
            "pending_approvals": 0,
            "curation_run_id": completed_curation_run.id,
            "last_supervisor_summary_key": _SUPERVISOR_SUMMARY_ARTIFACT_KEY,
            "last_child_run_links_key": _SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY,
            "last_child_curation_summary_key": "curation_summary",
            "last_child_curation_actions_key": "curation_actions",
            "curation_status": completed_curation_run.status,
        },
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="supervisor.completed",
        message="Supervisor workflow completed.",
        payload=summary_content,
        progress_percent=1.0,
    )
    if completed_run is None or completed_progress is None:
        error_message = f"Supervisor run '{run.id}' could not be completed"
        raise RuntimeError(error_message)
    return completed_run, completed_progress




__all__ = ["resume_supervisor_run"]
