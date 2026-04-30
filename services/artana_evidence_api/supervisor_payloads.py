"""Supervisor runtime payload and artifact helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.chat_sessions import (
        HarnessChatMessageRecord,
        HarnessChatSessionRecord,
    )
    from artana_evidence_api.chat_workflow import GraphChatMessageExecution
    from artana_evidence_api.claim_curation_workflow import ClaimCurationRunExecution
    from artana_evidence_api.research_bootstrap_runtime import (
        ResearchBootstrapExecutionResult,
    )
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
    from artana_evidence_api.types.common import JSONObject

_SUPERVISOR_WORKFLOW = "bootstrap_chat_curation"
_SUPERVISOR_RESUME_POINT = "supervisor_child_approval_gate"
_SUPERVISOR_SUMMARY_ARTIFACT_KEY = "supervisor_summary"
_SUPERVISOR_PLAN_ARTIFACT_KEY = "supervisor_plan"
_SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY = "child_run_links"


def _progress_percent(*, completed_steps: int, total_steps: int) -> float:
    if total_steps <= 0:
        return 0.0
    return round(completed_steps / total_steps, 6)


def _json_object_sequence(value: object) -> tuple[JSONObject, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


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




__all__ = [
    "_SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY",
    "_SUPERVISOR_RESUME_POINT",
    "_SUPERVISOR_SUMMARY_ARTIFACT_KEY",
    "_SUPERVISOR_WORKFLOW",
    "_json_object_sequence",
    "_mark_failed_supervisor_run",
    "_progress_percent",
    "_research_bootstrap_response_payload",
    "_supervisor_run_response_payload",
    "_write_supervisor_artifacts",
    "build_supervisor_run_input_payload",
]
