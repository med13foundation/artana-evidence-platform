"""Supervisor harness runtime for composed research workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.chat_graph_write_workflow import (
    ChatGraphWriteArtifactError,
    ChatGraphWriteCandidateError,
    ChatGraphWriteProposalExecution,
    ChatGraphWriteVerificationError,
    derive_chat_graph_write_candidates,
    stage_chat_graph_write_proposals,
)
from artana_evidence_api.chat_workflow import (
    DEFAULT_CHAT_SESSION_TITLE,
    GraphChatMessageExecution,
    execute_graph_chat_message,
)
from artana_evidence_api.claim_curation_runtime import (
    resume_claim_curation_run,
)
from artana_evidence_api.claim_curation_workflow import (
    ClaimCurationNoEligibleProposalsError,
    ClaimCurationRunExecution,
    execute_claim_curation_run_for_proposals,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.research_bootstrap_runtime import (
    ResearchBootstrapExecutionResult,
    execute_research_bootstrap_run,
)
from artana_evidence_api.transparency import (
    active_skill_names_from_policy_content,
    append_skill_activity,
    ensure_run_transparency_seed,
    sync_policy_decisions_artifact,
)

if TYPE_CHECKING:
    from artana_evidence_api.approval_store import HarnessApprovalStore
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.chat_sessions import (
        HarnessChatMessageRecord,
        HarnessChatSessionRecord,
        HarnessChatSessionStore,
    )
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.graph_chat_runtime import HarnessGraphChatRunner
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_connection_runtime import (
        HarnessGraphConnectionRunner,
    )
    from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.run_registry import (
        HarnessRunProgressRecord,
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.schedule_store import HarnessScheduleStore
    from artana_evidence_api.types.common import JSONObject

_SUPERVISOR_WORKFLOW = "bootstrap_chat_curation"
_SUPERVISOR_RESUME_POINT = "supervisor_child_approval_gate"
_SUPERVISOR_SUMMARY_ARTIFACT_KEY = "supervisor_summary"
_SUPERVISOR_PLAN_ARTIFACT_KEY = "supervisor_plan"
_SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY = "child_run_links"


@dataclass(frozen=True, slots=True)
class SupervisorExecutionResult:
    """One completed supervisor orchestration result."""

    run: HarnessRunRecord
    bootstrap: ResearchBootstrapExecutionResult
    chat_session: HarnessChatSessionRecord | None
    chat: GraphChatMessageExecution | None
    curation: ClaimCurationRunExecution | None
    briefing_question: str | None
    curation_source: str
    chat_graph_write: ChatGraphWriteProposalExecution | None
    selected_curation_proposal_ids: tuple[str, ...]
    steps: tuple[JSONObject, ...]


def is_supervisor_workflow(run: HarnessRunRecord) -> bool:
    """Return whether one run belongs to the supervisor workflow."""
    workflow = run.input_payload.get("workflow")
    return run.harness_id == "supervisor" and workflow == _SUPERVISOR_WORKFLOW


def _progress_percent(*, completed_steps: int, total_steps: int) -> float:
    if total_steps <= 0:
        return 0.0
    return round(completed_steps / total_steps, 6)


def _propagate_child_skill_activity(  # noqa: PLR0913
    *,
    space_id: UUID,
    parent_run_id: str,
    child_run_id: str,
    source_kind: str,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    runtime: GraphHarnessKernelRuntime,
) -> None:
    policy_content = sync_policy_decisions_artifact(
        space_id=space_id,
        run_id=child_run_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        runtime=runtime,
    )
    if policy_content is None:
        return
    append_skill_activity(
        space_id=space_id,
        run_id=parent_run_id,
        skill_names=tuple(active_skill_names_from_policy_content(policy_content)),
        source_run_id=child_run_id,
        source_kind=source_kind,
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )


def _json_object_sequence(value: object) -> tuple[JSONObject, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def _derived_briefing_question(
    *,
    objective: str | None,
    pending_questions: list[str],
    top_proposal_title: str | None,
) -> str:
    if pending_questions:
        return pending_questions[0]
    if objective is not None and objective.strip() != "":
        return f"What should a researcher review next to advance: {objective.strip()}?"
    if top_proposal_title is not None and top_proposal_title.strip() != "":
        return (
            f"What evidence should be reviewed first for: {top_proposal_title.strip()}?"
        )
    return "What should be reviewed next in this research space?"


def build_supervisor_run_input_payload(  # noqa: PLR0913
    *,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    include_chat: bool,
    include_curation: bool,
    curation_source: str,
    briefing_question: str | None,
    chat_max_depth: int,
    chat_top_k: int,
    chat_include_evidence_chains: bool,
    curation_proposal_limit: int,
    current_user_id: str,
) -> JSONObject:
    return {
        "workflow": _SUPERVISOR_WORKFLOW,
        "objective": objective,
        "seed_entity_ids": list(seed_entity_ids),
        "source_type": source_type,
        "relation_types": list(relation_types or []),
        "max_depth": max_depth,
        "max_hypotheses": max_hypotheses,
        "model_id": model_id,
        "include_chat": include_chat,
        "include_curation": include_curation,
        "curation_source": curation_source,
        "briefing_question": briefing_question,
        "chat_max_depth": chat_max_depth,
        "chat_top_k": chat_top_k,
        "chat_include_evidence_chains": chat_include_evidence_chains,
        "curation_proposal_limit": curation_proposal_limit,
        "current_user_id": current_user_id,
    }


def queue_supervisor_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    include_chat: bool,
    include_curation: bool,
    curation_source: str,
    briefing_question: str | None,
    chat_max_depth: int,
    chat_top_k: int,
    chat_include_evidence_chains: bool,
    curation_proposal_limit: int,
    current_user_id: UUID | str,
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="supervisor",
        title=title,
        input_payload=build_supervisor_run_input_payload(
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            model_id=model_id,
            include_chat=include_chat,
            include_curation=include_curation,
            curation_source=curation_source,
            briefing_question=briefing_question,
            chat_max_depth=chat_max_depth,
            chat_top_k=chat_top_k,
            chat_include_evidence_chains=chat_include_evidence_chains,
            curation_proposal_limit=curation_proposal_limit,
            current_user_id=str(current_user_id),
        ),
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "workflow": _SUPERVISOR_WORKFLOW,
            "include_chat": include_chat,
            "include_curation": include_curation,
            "curation_source": curation_source,
            "selected_curation_proposal_ids": [],
            "chat_graph_write_proposal_ids": [],
            "skipped_steps": [],
        },
    )
    return run


def _mark_failed_supervisor_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    run_id: str,
    error_message: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    completed_steps: int,
    total_steps: int,
) -> None:
    run_registry.set_run_status(space_id=space_id, run_id=run_id, status="failed")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run_id,
        phase="failed",
        message=error_message,
        progress_percent=_progress_percent(
            completed_steps=completed_steps,
            total_steps=total_steps,
        ),
        completed_steps=completed_steps,
        total_steps=total_steps,
        metadata={"error": error_message},
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={"status": "failed", "error": error_message},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="supervisor_error",
        media_type="application/json",
        content={"error": error_message},
    )


def _child_run_links_payload(  # noqa: PLR0913
    *,
    parent_run_id: str,
    bootstrap_run_id: str,
    chat_run_id: str | None,
    chat_session_id: str | None,
    curation_run_id: str | None,
    curation_status: str | None,
) -> JSONObject:
    return {
        "parent_run_id": parent_run_id,
        "bootstrap_run_id": bootstrap_run_id,
        "chat_run_id": chat_run_id,
        "chat_session_id": chat_session_id,
        "curation_run_id": curation_run_id,
        "curation_status": curation_status,
    }


def _run_response_payload(*, run: HarnessRunRecord) -> JSONObject:
    return {
        "id": run.id,
        "space_id": run.space_id,
        "harness_id": run.harness_id,
        "title": run.title,
        "status": run.status,
        "input_payload": run.input_payload,
        "graph_service_status": run.graph_service_status,
        "graph_service_version": run.graph_service_version,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def _research_bootstrap_response_payload(
    *,
    result: ResearchBootstrapExecutionResult,
) -> JSONObject:
    return {
        "run": _run_response_payload(run=result.run),
        "graph_snapshot": {
            "id": result.graph_snapshot.id,
            "space_id": result.graph_snapshot.space_id,
            "source_run_id": result.graph_snapshot.source_run_id,
            "claim_ids": list(result.graph_snapshot.claim_ids),
            "relation_ids": list(result.graph_snapshot.relation_ids),
            "graph_document_hash": result.graph_snapshot.graph_document_hash,
            "summary": result.graph_snapshot.summary,
            "metadata": result.graph_snapshot.metadata,
            "created_at": result.graph_snapshot.created_at.isoformat(),
            "updated_at": result.graph_snapshot.updated_at.isoformat(),
        },
        "research_state": {
            "space_id": result.research_state.space_id,
            "objective": result.research_state.objective,
            "current_hypotheses": list(result.research_state.current_hypotheses),
            "explored_questions": list(result.research_state.explored_questions),
            "pending_questions": list(result.research_state.pending_questions),
            "last_graph_snapshot_id": result.research_state.last_graph_snapshot_id,
            "last_learning_cycle_at": (
                result.research_state.last_learning_cycle_at.isoformat()
                if result.research_state.last_learning_cycle_at is not None
                else None
            ),
            "active_schedules": list(result.research_state.active_schedules),
            "confidence_model": result.research_state.confidence_model,
            "budget_policy": result.research_state.budget_policy,
            "metadata": result.research_state.metadata,
            "created_at": result.research_state.created_at.isoformat(),
            "updated_at": result.research_state.updated_at.isoformat(),
        },
        "research_brief": result.research_brief,
        "graph_summary": result.graph_summary,
        "source_inventory": result.source_inventory,
        "proposal_count": len(result.proposal_records),
        "pending_questions": list(result.pending_questions),
        "errors": list(result.errors),
    }


def _chat_message_payload(*, message: HarnessChatMessageRecord) -> JSONObject:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "run_id": message.run_id,
        "metadata": message.metadata,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
    }


def _chat_session_response_payload(*, session: HarnessChatSessionRecord) -> JSONObject:
    return {
        "id": session.id,
        "space_id": session.space_id,
        "title": session.title,
        "created_by": session.created_by,
        "last_run_id": session.last_run_id,
        "status": session.status,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def _chat_run_response_payload(
    *,
    execution: GraphChatMessageExecution,
) -> JSONObject:
    return {
        "run": _run_response_payload(run=execution.run),
        "session": _chat_session_response_payload(session=execution.session),
        "user_message": _chat_message_payload(message=execution.user_message),
        "assistant_message": _chat_message_payload(message=execution.assistant_message),
        "result": execution.result.model_dump(mode="json"),
    }


def _curation_selected_proposals_payload(
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
                "proposal_id": item.get("proposal_id"),
                "title": item.get("title"),
                "summary": item.get("summary"),
                "source_key": item.get("source_key"),
                "confidence": item.get("confidence"),
                "ranking_score": item.get("ranking_score"),
                "approval_key": item.get("approval_key"),
                "duplicate_selected_count": item.get("duplicate_selected_count", 0),
                "existing_promoted_proposal_ids": item.get(
                    "existing_promoted_proposal_ids",
                    [],
                ),
                "graph_duplicate_claim_ids": item.get(
                    "graph_duplicate_claim_ids",
                    [],
                ),
                "conflicting_relation_ids": item.get("conflicting_relation_ids", []),
                "invariant_issues": item.get("invariant_issues", []),
                "blocker_reasons": item.get("blocker_reasons", []),
                "eligible_for_approval": item.get("eligible_for_approval", False),
            },
        )
    return selected


def _claim_curation_response_payload(
    *,
    run: HarnessRunRecord,
    review_plan: JSONObject,
    pending_approval_count: int,
) -> JSONObject:
    proposal_count = review_plan.get("proposal_count")
    blocked_proposal_count = review_plan.get("blocked_proposal_count")
    return {
        "run": _run_response_payload(run=run),
        "curation_packet_key": "curation_packet",
        "review_plan_key": "review_plan",
        "approval_intent_key": "approval_intent",
        "proposal_count": proposal_count if isinstance(proposal_count, int) else 0,
        "blocked_proposal_count": (
            blocked_proposal_count if isinstance(blocked_proposal_count, int) else 0
        ),
        "pending_approval_count": pending_approval_count,
        "proposals": _curation_selected_proposals_payload(review_plan=review_plan),
    }


def _supervisor_run_response_payload(
    *,
    run: HarnessRunRecord,
    bootstrap: ResearchBootstrapExecutionResult,
    chat: GraphChatMessageExecution | None,
    curation: ClaimCurationRunExecution | None,
    briefing_question: str | None,
    curation_source: str,
    chat_graph_write_proposal_ids: list[str],
    selected_curation_proposal_ids: list[str],
    steps: list[JSONObject],
) -> JSONObject:
    return {
        "run": _run_response_payload(run=run),
        "bootstrap": _research_bootstrap_response_payload(result=bootstrap),
        "chat": (
            _chat_run_response_payload(execution=chat) if chat is not None else None
        ),
        "curation": (
            _claim_curation_response_payload(
                run=curation.run,
                review_plan=curation.review_plan,
                pending_approval_count=curation.pending_approval_count,
            )
            if curation is not None
            else None
        ),
        "briefing_question": briefing_question,
        "curation_source": curation_source,
        "chat_graph_write_proposal_ids": list(chat_graph_write_proposal_ids),
        "selected_curation_proposal_ids": list(selected_curation_proposal_ids),
        "chat_graph_write_review_count": 0,
        "latest_chat_graph_write_review": None,
        "chat_graph_write_reviews": [],
        "steps": list(steps),
    }


def _summary_steps_with_updated_curation_status(
    *,
    steps: list[JSONObject],
    curation_run_id: str | None,
    status: str,
    detail: str,
) -> list[JSONObject]:
    updated_steps: list[JSONObject] = []
    found_curation_step = False
    for step in steps:
        if step.get("step") == "curation":
            found_curation_step = True
            updated_steps.append(
                {
                    **step,
                    "status": status,
                    "harness_id": (
                        "claim-curation" if curation_run_id is not None else None
                    ),
                    "run_id": curation_run_id,
                    "detail": detail,
                },
            )
            continue
        updated_steps.append(step)
    if not found_curation_step:
        updated_steps.append(
            {
                "step": "curation",
                "status": status,
                "harness_id": "claim-curation" if curation_run_id is not None else None,
                "run_id": curation_run_id,
                "detail": detail,
            },
        )
    return updated_steps


def _load_supervisor_summary(
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> JSONObject:
    summary_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SUPERVISOR_SUMMARY_ARTIFACT_KEY,
    )
    if summary_artifact is None:
        return {}
    return summary_artifact.content


def _supervisor_child_curation_run_id(
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> str | None:
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)
    if workspace is not None:
        value = workspace.snapshot.get("curation_run_id")
        if isinstance(value, str) and value.strip() != "":
            return value
    summary = _load_supervisor_summary(
        space_id=space_id,
        run_id=run_id,
        artifact_store=artifact_store,
    )
    value = summary.get("curation_run_id")
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def _write_supervisor_artifacts(  # noqa: PLR0913
    *,
    space_id: UUID,
    run_id: str,
    bootstrap_run_id: str,
    chat_run_id: str | None,
    chat_session_id: str | None,
    curation_run_id: str | None,
    curation_status: str | None,
    summary_content: JSONObject,
    artifact_store: HarnessArtifactStore,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY,
        media_type="application/json",
        content=_child_run_links_payload(
            parent_run_id=run_id,
            bootstrap_run_id=bootstrap_run_id,
            chat_run_id=chat_run_id,
            chat_session_id=chat_session_id,
            curation_run_id=curation_run_id,
            curation_status=curation_status,
        ),
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SUPERVISOR_SUMMARY_ARTIFACT_KEY,
        media_type="application/json",
        content=summary_content,
    )


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


async def execute_supervisor_run(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    space_id: UUID,
    title: str,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    include_chat: bool,
    include_curation: bool,
    curation_source: str,
    briefing_question: str | None,
    chat_max_depth: int,
    chat_top_k: int,
    chat_include_evidence_chains: bool,
    curation_proposal_limit: int,
    current_user_id: UUID | str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    chat_session_store: HarnessChatSessionStore,
    proposal_store: HarnessProposalStore,
    approval_store: HarnessApprovalStore,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    schedule_store: HarnessScheduleStore,
    graph_connection_runner: HarnessGraphConnectionRunner,
    graph_chat_runner: HarnessGraphChatRunner,
    pubmed_discovery_service: PubMedDiscoveryService,
    runtime: GraphHarnessKernelRuntime,
    parent_graph_api_gateway: GraphTransportBundle,
    bootstrap_graph_api_gateway: GraphTransportBundle,
    chat_graph_api_gateway: GraphTransportBundle,
    curation_graph_api_gateway: GraphTransportBundle,
    existing_run: HarnessRunRecord | None = None,
) -> SupervisorExecutionResult:
    """Run the composed supervisor workflow across bootstrap, chat, and curation."""
    total_steps = 1 + int(include_chat) + int(include_curation)
    completed_steps = 0
    steps: list[JSONObject] = []
    try:
        parent_graph_health = parent_graph_api_gateway.get_health()
    finally:
        parent_graph_api_gateway.close()

    if existing_run is None:
        run = queue_supervisor_run(
            space_id=space_id,
            title=title,
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            model_id=model_id,
            include_chat=include_chat,
            include_curation=include_curation,
            curation_source=curation_source,
            briefing_question=briefing_question,
            chat_max_depth=chat_max_depth,
            chat_top_k=chat_top_k,
            chat_include_evidence_chains=chat_include_evidence_chains,
            curation_proposal_limit=curation_proposal_limit,
            current_user_id=current_user_id,
            graph_service_status=parent_graph_health.status,
            graph_service_version=parent_graph_health.version,
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
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="bootstrap",
        message="Running bootstrap step.",
        progress_percent=0.0,
        completed_steps=0,
        total_steps=total_steps,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="supervisor_plan",
        media_type="application/json",
        content={
            "workflow": _SUPERVISOR_WORKFLOW,
            "include_chat": include_chat,
            "include_curation": include_curation,
            "curation_source": curation_source,
            "briefing_question": briefing_question,
            "curation_proposal_limit": curation_proposal_limit,
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "running",
            "workflow": _SUPERVISOR_WORKFLOW,
            "include_chat": include_chat,
            "include_curation": include_curation,
            "curation_source": curation_source,
            "selected_curation_proposal_ids": [],
            "chat_graph_write_proposal_ids": [],
            "skipped_steps": [],
        },
    )
    append_skill_activity(
        space_id=space_id,
        run_id=run.id,
        skill_names=("graph_harness.supervisor_coordination",),
        source_run_id=run.id,
        source_kind="supervisor",
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )

    try:
        bootstrap = await execute_research_bootstrap_run(
            space_id=space_id,
            title="Research Bootstrap Harness",
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            model_id=model_id,
            run_registry=run_registry,
            artifact_store=artifact_store,
            graph_api_gateway=bootstrap_graph_api_gateway,
            graph_connection_runner=graph_connection_runner,
            proposal_store=proposal_store,
            research_state_store=research_state_store,
            graph_snapshot_store=graph_snapshot_store,
            schedule_store=schedule_store,
            runtime=runtime,
        )
    except Exception as exc:
        _mark_failed_supervisor_run(
            space_id=space_id,
            run_id=run.id,
            error_message=f"Supervisor bootstrap step failed: {exc}",
            run_registry=run_registry,
            artifact_store=artifact_store,
            completed_steps=completed_steps,
            total_steps=total_steps,
        )
        bootstrap_graph_api_gateway.close()
        raise
    bootstrap_graph_api_gateway.close()

    completed_steps += 1
    steps.append(
        {
            "step": "bootstrap",
            "status": "completed",
            "harness_id": bootstrap.run.harness_id,
            "run_id": bootstrap.run.id,
            "detail": f"Bootstrap completed with {len(bootstrap.proposal_records)} proposal(s).",
        },
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="supervisor.bootstrap_completed",
        message="Supervisor bootstrap step completed.",
        payload={
            "bootstrap_run_id": bootstrap.run.id,
            "proposal_count": len(bootstrap.proposal_records),
            "graph_snapshot_id": bootstrap.graph_snapshot.id,
        },
        progress_percent=_progress_percent(
            completed_steps=completed_steps,
            total_steps=total_steps,
        ),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "bootstrap_run_id": bootstrap.run.id,
            "last_graph_snapshot_id": bootstrap.graph_snapshot.id,
            "bootstrap_proposal_count": len(bootstrap.proposal_records),
        },
    )
    _propagate_child_skill_activity(
        space_id=space_id,
        parent_run_id=run.id,
        child_run_id=bootstrap.run.id,
        source_kind="research_bootstrap",
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="bootstrap",
        message="Bootstrap step completed.",
        progress_percent=_progress_percent(
            completed_steps=completed_steps,
            total_steps=total_steps,
        ),
        completed_steps=completed_steps,
        total_steps=total_steps,
        metadata={"bootstrap_run_id": bootstrap.run.id},
    )

    chat_session: HarnessChatSessionRecord | None = None
    chat_execution: GraphChatMessageExecution | None = None
    chat_graph_write_execution: ChatGraphWriteProposalExecution | None = None
    resolved_briefing_question: str | None = None
    skipped_steps: list[str] = []
    if include_chat:
        resolved_briefing_question = (
            briefing_question.strip()
            if isinstance(briefing_question, str) and briefing_question.strip() != ""
            else _derived_briefing_question(
                objective=bootstrap.research_state.objective,
                pending_questions=bootstrap.pending_questions,
                top_proposal_title=(
                    bootstrap.proposal_records[0].title
                    if bootstrap.proposal_records
                    else None
                ),
            )
        )
        chat_session = chat_session_store.create_session(
            space_id=space_id,
            title=DEFAULT_CHAT_SESSION_TITLE,
            created_by=current_user_id,
        )
        try:
            chat_execution = await execute_graph_chat_message(
                space_id=space_id,
                session=chat_session,
                content=resolved_briefing_question,
                model_id=model_id,
                max_depth=chat_max_depth,
                top_k=chat_top_k,
                include_evidence_chains=chat_include_evidence_chains,
                current_user_id=current_user_id,
                chat_session_store=chat_session_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                runtime=runtime,
                graph_api_gateway=chat_graph_api_gateway,
                graph_chat_runner=graph_chat_runner,
                graph_snapshot_store=graph_snapshot_store,
                _pubmed_discovery_service=pubmed_discovery_service,
                research_state_store=research_state_store,
                proposal_store=proposal_store,
                referenced_documents=(),
                refresh_pubmed_if_needed=True,
            )
        except Exception as exc:
            _mark_failed_supervisor_run(
                space_id=space_id,
                run_id=run.id,
                error_message=f"Supervisor chat step failed: {exc}",
                run_registry=run_registry,
                artifact_store=artifact_store,
                completed_steps=completed_steps,
                total_steps=total_steps,
            )
            raise
        completed_steps += 1
        steps.append(
            {
                "step": "chat",
                "status": "completed",
                "harness_id": chat_execution.run.harness_id,
                "run_id": chat_execution.run.id,
                "detail": "Briefing chat completed.",
            },
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="supervisor.chat_completed",
            message="Supervisor chat step completed.",
            payload={
                "chat_run_id": chat_execution.run.id,
                "chat_session_id": chat_execution.session.id,
                "question": resolved_briefing_question,
            },
            progress_percent=_progress_percent(
                completed_steps=completed_steps,
                total_steps=total_steps,
            ),
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "chat_run_id": chat_execution.run.id,
                "chat_session_id": chat_execution.session.id,
                "briefing_question": resolved_briefing_question,
            },
        )
        _propagate_child_skill_activity(
            space_id=space_id,
            parent_run_id=run.id,
            child_run_id=chat_execution.run.id,
            source_kind="graph_chat",
            artifact_store=artifact_store,
            run_registry=run_registry,
            runtime=runtime,
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="chat",
            message="Chat step completed.",
            progress_percent=_progress_percent(
                completed_steps=completed_steps,
                total_steps=total_steps,
            ),
            completed_steps=completed_steps,
            total_steps=total_steps,
            metadata={"chat_run_id": chat_execution.run.id},
        )
    else:
        chat_graph_api_gateway.close()
        skipped_steps.append("chat")
        steps.append(
            {
                "step": "chat",
                "status": "skipped",
                "harness_id": None,
                "run_id": None,
                "detail": "Chat step disabled for this supervisor run.",
            },
        )

    curation_execution: ClaimCurationRunExecution | None = None
    selected_curation_proposal_ids: tuple[str, ...] = ()
    chat_graph_write_proposals = []
    if include_curation and curation_source == "chat_graph_write":
        if chat_execution is None or chat_session is None:
            error_message = (
                "Supervisor chat graph-write curation requires a completed chat step"
            )
            _mark_failed_supervisor_run(
                space_id=space_id,
                run_id=run.id,
                error_message=error_message,
                run_registry=run_registry,
                artifact_store=artifact_store,
                completed_steps=completed_steps,
                total_steps=total_steps,
            )
            raise RuntimeError(error_message)
        try:
            derived_chat_graph_write_candidates = derive_chat_graph_write_candidates(
                space_id=space_id,
                run=chat_execution.run,
                result=chat_execution.result,
                runtime=runtime,
            )
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=run.id,
                patch={
                    "chat_graph_write_candidate_count": len(
                        derived_chat_graph_write_candidates,
                    ),
                },
            )
            if not derived_chat_graph_write_candidates:
                run_registry.record_event(
                    space_id=space_id,
                    run_id=run.id,
                    event_type="supervisor.chat_graph_write_candidates_derived",
                    message="Supervisor found no chat-derived graph-write suggestions.",
                    payload={
                        "chat_run_id": chat_execution.run.id,
                        "candidate_count": 0,
                    },
                    progress_percent=_progress_percent(
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                    ),
                )
            else:
                run_registry.record_event(
                    space_id=space_id,
                    run_id=run.id,
                    event_type="supervisor.chat_graph_write_candidates_derived",
                    message="Supervisor derived chat graph-write suggestions.",
                    payload={
                        "chat_run_id": chat_execution.run.id,
                        "candidate_count": len(derived_chat_graph_write_candidates),
                    },
                    progress_percent=_progress_percent(
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                    ),
                )
            chat_graph_write_execution = stage_chat_graph_write_proposals(
                space_id=space_id,
                session_id=UUID(chat_session.id),
                run_id=chat_execution.run.id,
                candidates=list(derived_chat_graph_write_candidates),
                artifact_store=artifact_store,
                proposal_store=proposal_store,
                run_registry=run_registry,
            )
        except (
            ChatGraphWriteArtifactError,
            ChatGraphWriteCandidateError,
            ChatGraphWriteVerificationError,
        ) as exc:
            _mark_failed_supervisor_run(
                space_id=space_id,
                run_id=run.id,
                error_message=f"Supervisor chat graph-write staging failed: {exc}",
                run_registry=run_registry,
                artifact_store=artifact_store,
                completed_steps=completed_steps,
                total_steps=total_steps,
            )
            curation_graph_api_gateway.close()
            raise
        chat_graph_write_proposals = list(chat_graph_write_execution.proposals)
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="supervisor.chat_graph_write_staged",
            message="Supervisor staged chat-derived graph-write proposals.",
            payload={
                "chat_run_id": chat_execution.run.id,
                "proposal_ids": [
                    proposal.id for proposal in chat_graph_write_execution.proposals
                ],
            },
            progress_percent=_progress_percent(
                completed_steps=completed_steps,
                total_steps=total_steps,
            ),
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "chat_graph_write_run_id": chat_execution.run.id,
                "chat_graph_write_proposal_ids": [
                    proposal.id for proposal in chat_graph_write_execution.proposals
                ],
                "chat_graph_write_proposal_count": len(
                    chat_graph_write_execution.proposals,
                ),
            },
        )
    if include_curation:
        proposal_source_records = (
            chat_graph_write_proposals
            if curation_source == "chat_graph_write"
            else bootstrap.proposal_records
        )
        curatable_proposals = sorted(
            [
                proposal
                for proposal in proposal_source_records
                if proposal.status == "pending_review"
            ],
            key=lambda proposal: proposal.ranking_score,
            reverse=True,
        )[:curation_proposal_limit]
        selected_curation_proposal_ids = tuple(
            proposal.id for proposal in curatable_proposals
        )
        if not curatable_proposals:
            curation_graph_api_gateway.close()
            skipped_steps.append("curation")
            steps.append(
                {
                    "step": "curation",
                    "status": "skipped",
                    "harness_id": None,
                    "run_id": None,
                    "detail": (
                        "No pending-review proposals were available for claim "
                        f"curation from source '{curation_source}'."
                    ),
                },
            )
        else:
            try:
                curation_execution = execute_claim_curation_run_for_proposals(
                    space_id=space_id,
                    proposals=curatable_proposals,
                    title="Claim Curation Harness",
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    proposal_store=proposal_store,
                    approval_store=approval_store,
                    graph_api_gateway=curation_graph_api_gateway,
                    runtime=runtime,
                )
            except ClaimCurationNoEligibleProposalsError as exc:
                skipped_steps.append("curation")
                steps.append(
                    {
                        "step": "curation",
                        "status": "skipped",
                        "harness_id": None,
                        "run_id": None,
                        "detail": str(exc),
                    },
                )
            except Exception as exc:
                _mark_failed_supervisor_run(
                    space_id=space_id,
                    run_id=run.id,
                    error_message=f"Supervisor curation step failed: {exc}",
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                )
                raise
            else:
                steps.append(
                    {
                        "step": "curation",
                        "status": "paused",
                        "harness_id": curation_execution.run.harness_id,
                        "run_id": curation_execution.run.id,
                        "detail": "Claim-curation run created and paused for approval.",
                    },
                )
                run_registry.record_event(
                    space_id=space_id,
                    run_id=run.id,
                    event_type="supervisor.curation_created",
                    message="Supervisor curation step created a paused review run.",
                    payload={
                        "curation_run_id": curation_execution.run.id,
                        "proposal_ids": list(selected_curation_proposal_ids),
                        "pending_approvals": curation_execution.pending_approval_count,
                    },
                    progress_percent=_progress_percent(
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                    ),
                )
                artifact_store.patch_workspace(
                    space_id=space_id,
                    run_id=run.id,
                    patch={
                        "curation_run_id": curation_execution.run.id,
                        "selected_curation_proposal_ids": list(
                            selected_curation_proposal_ids,
                        ),
                        "curation_source": curation_source,
                        "pending_approvals": curation_execution.pending_approval_count,
                        "curation_status": curation_execution.run.status,
                    },
                )
                _propagate_child_skill_activity(
                    space_id=space_id,
                    parent_run_id=run.id,
                    child_run_id=curation_execution.run.id,
                    source_kind="claim_curation",
                    artifact_store=artifact_store,
                    run_registry=run_registry,
                    runtime=runtime,
                )
                run_registry.set_progress(
                    space_id=space_id,
                    run_id=run.id,
                    phase="approval",
                    message="Supervisor workflow paused pending child curation approval.",
                    progress_percent=_progress_percent(
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                    ),
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                    resume_point=_SUPERVISOR_RESUME_POINT,
                    metadata={"curation_run_id": curation_execution.run.id},
                )
    else:
        curation_graph_api_gateway.close()
        skipped_steps.append("curation")
        steps.append(
            {
                "step": "curation",
                "status": "skipped",
                "harness_id": None,
                "run_id": None,
                "detail": "Curation step disabled for this supervisor run.",
            },
        )

    summary_content: JSONObject = {
        "workflow": _SUPERVISOR_WORKFLOW,
        "bootstrap_run_id": bootstrap.run.id,
        "bootstrap_response": _research_bootstrap_response_payload(result=bootstrap),
        "chat_run_id": chat_execution.run.id if chat_execution is not None else None,
        "chat_response": (
            _chat_run_response_payload(execution=chat_execution)
            if chat_execution is not None
            else None
        ),
        "chat_graph_write_run_id": (
            chat_graph_write_execution.run_id
            if chat_graph_write_execution is not None
            else None
        ),
        "chat_graph_write_proposal_ids": [
            proposal.id
            for proposal in (
                chat_graph_write_execution.proposals
                if chat_graph_write_execution is not None
                else []
            )
        ],
        "chat_session_id": (
            chat_execution.session.id
            if chat_execution is not None
            else (chat_session.id if chat_session is not None else None)
        ),
        "curation_run_id": (
            curation_execution.run.id if curation_execution is not None else None
        ),
        "curation_response": (
            _claim_curation_response_payload(
                run=curation_execution.run,
                review_plan=curation_execution.review_plan,
                pending_approval_count=curation_execution.pending_approval_count,
            )
            if curation_execution is not None
            else None
        ),
        "briefing_question": resolved_briefing_question,
        "curation_source": curation_source,
        "selected_curation_proposal_ids": list(selected_curation_proposal_ids),
        "skipped_steps": skipped_steps,
        "curation_status": (
            curation_execution.run.status if curation_execution is not None else None
        ),
        "completed_at": None,
        "steps": steps,
    }
    _write_supervisor_artifacts(
        space_id=space_id,
        run_id=run.id,
        bootstrap_run_id=bootstrap.run.id,
        chat_run_id=chat_execution.run.id if chat_execution is not None else None,
        chat_session_id=(
            chat_execution.session.id
            if chat_execution is not None
            else (chat_session.id if chat_session is not None else None)
        ),
        curation_run_id=(
            curation_execution.run.id if curation_execution is not None else None
        ),
        curation_status=(
            curation_execution.run.status if curation_execution is not None else None
        ),
        summary_content=summary_content,
        artifact_store=artifact_store,
    )
    if curation_execution is not None:
        paused_run = run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="paused",
        )
        paused_progress = run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="approval",
            message="Supervisor workflow paused pending child curation approval.",
            progress_percent=_progress_percent(
                completed_steps=completed_steps,
                total_steps=total_steps,
            ),
            completed_steps=completed_steps,
            total_steps=total_steps,
            resume_point=_SUPERVISOR_RESUME_POINT,
            metadata={
                "curation_run_id": curation_execution.run.id,
                "pending_approvals": curation_execution.pending_approval_count,
            },
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "paused",
                "resume_point": _SUPERVISOR_RESUME_POINT,
                "pending_approvals": curation_execution.pending_approval_count,
                "last_supervisor_summary_key": _SUPERVISOR_SUMMARY_ARTIFACT_KEY,
                "last_child_run_links_key": _SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY,
                "briefing_question": resolved_briefing_question,
                "curation_source": curation_source,
                "selected_curation_proposal_ids": list(selected_curation_proposal_ids),
                "skipped_steps": skipped_steps,
            },
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="supervisor.paused",
            message="Supervisor workflow paused at the child curation approval gate.",
            payload={
                "curation_run_id": curation_execution.run.id,
                "pending_approvals": curation_execution.pending_approval_count,
            },
            progress_percent=(
                paused_progress.progress_percent
                if paused_progress is not None
                else None
            ),
        )
        final_run = paused_run or run
        store_primary_result_artifact(
            artifact_store=artifact_store,
            space_id=space_id,
            run_id=run.id,
            artifact_key="supervisor_run_response",
            content=_supervisor_run_response_payload(
                run=final_run,
                bootstrap=bootstrap,
                chat=chat_execution,
                curation=curation_execution,
                briefing_question=resolved_briefing_question,
                curation_source=curation_source,
                chat_graph_write_proposal_ids=[
                    proposal.id
                    for proposal in (
                        chat_graph_write_execution.proposals
                        if chat_graph_write_execution is not None
                        else []
                    )
                ],
                selected_curation_proposal_ids=list(selected_curation_proposal_ids),
                steps=steps,
            ),
            status_value="paused",
            result_keys=("supervisor_summary", "child_run_links"),
        )
        return SupervisorExecutionResult(
            run=final_run,
            bootstrap=bootstrap,
            chat_session=chat_session,
            chat=chat_execution,
            curation=curation_execution,
            briefing_question=resolved_briefing_question,
            curation_source=curation_source,
            chat_graph_write=chat_graph_write_execution,
            selected_curation_proposal_ids=selected_curation_proposal_ids,
            steps=_json_object_sequence(summary_content.get("steps")),
        )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "last_supervisor_summary_key": _SUPERVISOR_SUMMARY_ARTIFACT_KEY,
            "last_child_run_links_key": _SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY,
            "briefing_question": resolved_briefing_question,
            "curation_source": curation_source,
            "selected_curation_proposal_ids": list(selected_curation_proposal_ids),
            "skipped_steps": skipped_steps,
        },
    )
    completed_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    final_run = completed_run or run
    summary_content["completed_at"] = (
        completed_run.updated_at.isoformat() if completed_run is not None else None
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=_SUPERVISOR_SUMMARY_ARTIFACT_KEY,
        media_type="application/json",
        content=summary_content,
    )
    store_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key="supervisor_run_response",
        content=_supervisor_run_response_payload(
            run=final_run,
            bootstrap=bootstrap,
            chat=chat_execution,
            curation=curation_execution,
            briefing_question=resolved_briefing_question,
            curation_source=curation_source,
            chat_graph_write_proposal_ids=[
                proposal.id
                for proposal in (
                    chat_graph_write_execution.proposals
                    if chat_graph_write_execution is not None
                    else []
                )
            ],
            selected_curation_proposal_ids=list(selected_curation_proposal_ids),
            steps=steps,
        ),
        status_value="completed",
        result_keys=("supervisor_summary", "child_run_links"),
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="completed",
        message="Supervisor workflow completed.",
        progress_percent=1.0,
        completed_steps=total_steps,
        total_steps=total_steps,
        metadata={"skipped_steps": skipped_steps},
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="supervisor.completed",
        message="Supervisor workflow completed.",
        payload=summary_content,
        progress_percent=1.0,
    )
    return SupervisorExecutionResult(
        run=final_run,
        bootstrap=bootstrap,
        chat_session=chat_session,
        chat=chat_execution,
        curation=curation_execution,
        briefing_question=resolved_briefing_question,
        curation_source=curation_source,
        chat_graph_write=chat_graph_write_execution,
        selected_curation_proposal_ids=selected_curation_proposal_ids,
        steps=_json_object_sequence(summary_content.get("steps")),
    )


__all__ = [
    "SupervisorExecutionResult",
    "execute_supervisor_run",
    "is_supervisor_workflow",
    "resume_supervisor_run",
]
