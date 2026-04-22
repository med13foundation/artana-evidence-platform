"""Reusable graph-chat workflow helpers for composed harness runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.chat_graph_write_workflow import (
    ChatGraphWriteCandidateError,
    build_chat_graph_write_answer_supplement,
    derive_chat_graph_write_candidates,
)
from artana_evidence_api.chat_literature import (
    build_chat_literature_answer_supplement,
    build_chat_literature_request,
)
from artana_evidence_api.document_extraction import summarize_document_context
from artana_evidence_api.graph_chat_runtime import (
    GraphChatLiteratureRefresh,
    GraphChatResult,
    HarnessGraphChatRequest,
    HarnessGraphChatRunner,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.response_serialization import (
    serialize_chat_message_record,
    serialize_chat_session_record,
    serialize_run_record,
)
from artana_evidence_api.tool_runtime import run_pubmed_search
from artana_evidence_api.transparency import (
    append_skill_activity,
    ensure_run_transparency_seed,
)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.chat_sessions import (
        HarnessChatMessageRecord,
        HarnessChatSessionRecord,
        HarnessChatSessionStore,
    )
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.document_store import HarnessDocumentRecord
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_snapshot import (
        HarnessGraphSnapshotRecord,
        HarnessGraphSnapshotStore,
    )
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
    from artana_evidence_api.research_state import (
        HarnessResearchStateRecord,
        HarnessResearchStateStore,
    )
    from artana_evidence_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.types.common import JSONObject

DEFAULT_CHAT_SESSION_TITLE = "New Graph Chat"
_SESSION_TITLE_MAX_LENGTH = 80


@dataclass(frozen=True, slots=True)
class GraphChatMessageExecution:
    """One completed graph-chat message execution."""

    run: HarnessRunRecord
    session: HarnessChatSessionRecord
    user_message: HarnessChatMessageRecord
    assistant_message: HarnessChatMessageRecord
    result: GraphChatResult


def build_graph_chat_run_input_payload(  # noqa: PLR0913
    *,
    session_id: str,
    question: str,
    current_user_id: str,
    model_id: str | None,
    max_depth: int,
    top_k: int,
    include_evidence_chains: bool,
    memory_context: JSONObject,
    document_ids: list[str] | None = None,
    document_context: list[JSONObject] | None = None,
    refresh_pubmed_if_needed: bool = True,
) -> JSONObject:
    """Build the canonical queued-run payload for graph chat."""
    return {
        "session_id": session_id,
        "question": question,
        "current_user_id": current_user_id,
        "model_id": model_id,
        "max_depth": max_depth,
        "top_k": top_k,
        "include_evidence_chains": include_evidence_chains,
        "memory_context": memory_context,
        "document_ids": [] if document_ids is None else list(document_ids),
        "document_context": [] if document_context is None else list(document_context),
        "refresh_pubmed_if_needed": refresh_pubmed_if_needed,
    }


def derive_session_title(content: str) -> str:
    """Return the default title derived from the first user message."""
    normalized = content.strip().replace("\n", " ")
    if len(normalized) <= _SESSION_TITLE_MAX_LENGTH:
        return normalized
    return normalized[: _SESSION_TITLE_MAX_LENGTH - 3].rstrip() + "..."


def _normalized_unique_strings(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized == "" or normalized in seen_values:
            continue
        normalized_values.append(normalized)
        seen_values.add(normalized)
    return normalized_values


def load_chat_memory_context(
    *,
    space_id: UUID,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
) -> tuple[HarnessResearchStateRecord | None, HarnessGraphSnapshotRecord | None]:
    """Load the current research-memory and snapshot context for one space."""
    research_state = research_state_store.get_state(space_id=space_id)
    if research_state is not None and research_state.last_graph_snapshot_id is not None:
        graph_snapshot = graph_snapshot_store.get_snapshot(
            space_id=space_id,
            snapshot_id=research_state.last_graph_snapshot_id,
        )
    else:
        latest_snapshots = graph_snapshot_store.list_snapshots(
            space_id=space_id,
            limit=1,
        )
        graph_snapshot = latest_snapshots[0] if latest_snapshots else None
    return research_state, graph_snapshot


def memory_context_artifact(
    *,
    research_state: HarnessResearchStateRecord | None,
    graph_snapshot: HarnessGraphSnapshotRecord | None,
) -> JSONObject:
    """Return the chat memory-context artifact payload."""
    return {
        "objective": research_state.objective if research_state is not None else None,
        "current_hypotheses": (
            list(research_state.current_hypotheses)
            if research_state is not None
            else []
        ),
        "explored_questions": (
            list(research_state.explored_questions)
            if research_state is not None
            else []
        ),
        "pending_questions": (
            list(research_state.pending_questions) if research_state is not None else []
        ),
        "last_graph_snapshot_id": (
            research_state.last_graph_snapshot_id
            if research_state is not None
            else (graph_snapshot.id if graph_snapshot is not None else None)
        ),
        "graph_snapshot_summary": (
            graph_snapshot.summary if graph_snapshot is not None else {}
        ),
        "graph_snapshot_metadata": (
            graph_snapshot.metadata if graph_snapshot is not None else {}
        ),
    }


def pending_question_count(memory_context: JSONObject) -> int:
    """Return the number of pending questions recorded in chat memory."""
    pending_questions = memory_context.get("pending_questions")
    if not isinstance(pending_questions, list):
        return 0
    return len(pending_questions)


def queue_graph_chat_message_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    session: HarnessChatSessionRecord,
    title: str,
    content: str,
    current_user_id: UUID | str,
    model_id: str | None,
    max_depth: int,
    top_k: int,
    include_evidence_chains: bool,
    memory_context: JSONObject,
    document_ids: list[str] | None,
    document_context: list[JSONObject] | None,
    refresh_pubmed_if_needed: bool,
    graph_service_status: str,
    graph_service_version: str,
    chat_session_store: HarnessChatSessionStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    """Create a queued graph-chat run without executing it yet."""
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title=title,
        input_payload=build_graph_chat_run_input_payload(
            session_id=session.id,
            question=content,
            current_user_id=str(current_user_id),
            model_id=model_id,
            max_depth=max_depth,
            top_k=top_k,
            include_evidence_chains=include_evidence_chains,
            memory_context=memory_context,
            document_ids=document_ids,
            document_context=document_context,
            refresh_pubmed_if_needed=refresh_pubmed_if_needed,
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
            "chat_session_id": session.id,
            "research_objective": memory_context.get("objective"),
            "research_state_last_graph_snapshot_id": memory_context.get(
                "last_graph_snapshot_id",
            ),
            "pending_question_count": pending_question_count(memory_context),
            "document_reference_count": len(document_ids or []),
        },
    )
    chat_session_store.update_session(
        space_id=space_id,
        session_id=session.id,
        last_run_id=run.id,
        status="queued",
        title=title,
    )
    return run


def _pending_review_proposal_count(
    proposal_store: HarnessProposalStore,
    *,
    space_id: UUID,
) -> int:
    """Count pending-review proposals that are still awaiting human review."""
    return len(
        proposal_store.list_proposals(
            space_id=space_id,
            status="pending_review",
        ),
    )


def _preview_record_list(value: object) -> list[JSONObject]:
    if not isinstance(value, list):
        return []
    return [record for record in value if isinstance(record, dict)]


def _graph_write_candidate_artifact(
    *,
    session_id: str,
    run_id: str,
    result: GraphChatResult,
) -> JSONObject:
    return {
        "session_id": session_id,
        "run_id": run_id,
        "candidate_count": len(result.graph_write_candidates),
        "verification_status": result.verification.status,
        "candidates": [
            candidate.model_dump(mode="json")
            for candidate in result.graph_write_candidates
        ],
    }


def _mark_failed_chat_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    session_id: UUID,
    run_id: str,
    error_message: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    chat_session_store: HarnessChatSessionStore,
) -> None:
    run_registry.set_run_status(space_id=space_id, run_id=run_id, status="failed")
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={"status": "failed", "error": error_message},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="graph_chat_error",
        media_type="application/json",
        content={"error": error_message},
    )
    chat_session_store.update_session(
        space_id=space_id,
        session_id=session_id,
        last_run_id=run_id,
        status="error",
    )


async def execute_graph_chat_message(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    space_id: UUID,
    session: HarnessChatSessionRecord,
    content: str,
    model_id: str | None,
    max_depth: int,
    top_k: int,
    include_evidence_chains: bool,
    current_user_id: UUID | str,
    chat_session_store: HarnessChatSessionStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    runtime: GraphHarnessKernelRuntime,
    graph_api_gateway: GraphTransportBundle,
    graph_chat_runner: HarnessGraphChatRunner,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    _pubmed_discovery_service: PubMedDiscoveryService,
    research_state_store: HarnessResearchStateStore,
    proposal_store: HarnessProposalStore,
    referenced_documents: tuple[HarnessDocumentRecord, ...] = (),
    refresh_pubmed_if_needed: bool = True,
    existing_run: HarnessRunRecord | None = None,
) -> GraphChatMessageExecution:
    """Execute one graph-chat message against an existing chat session."""
    research_state, graph_snapshot = load_chat_memory_context(
        space_id=space_id,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
    )
    memory_context = memory_context_artifact(
        research_state=research_state,
        graph_snapshot=graph_snapshot,
    )
    if referenced_documents:
        memory_context["referenced_documents"] = [
            {
                "document_id": document.id,
                "title": document.title,
                "source_type": document.source_type,
                "text_excerpt": document.text_excerpt,
            }
            for document in referenced_documents
        ]
    pending_review_proposal_count = _pending_review_proposal_count(
        proposal_store,
        space_id=space_id,
    )
    try:
        graph_health = graph_api_gateway.get_health()
        resolved_title = session.title
        existing_messages = chat_session_store.list_messages(
            space_id=space_id,
            session_id=session.id,
        )
        if session.title == DEFAULT_CHAT_SESSION_TITLE and not existing_messages:
            resolved_title = derive_session_title(content)
            updated_session = chat_session_store.update_session(
                space_id=space_id,
                session_id=session.id,
                title=resolved_title,
            )
            if updated_session is not None:
                session = updated_session

        if existing_run is None:
            run = run_registry.create_run(
                space_id=space_id,
                harness_id="graph-chat",
                title=resolved_title,
                input_payload=build_graph_chat_run_input_payload(
                    session_id=session.id,
                    question=content,
                    current_user_id=str(current_user_id),
                    model_id=model_id,
                    max_depth=max_depth,
                    top_k=top_k,
                    include_evidence_chains=include_evidence_chains,
                    memory_context=memory_context,
                    document_ids=[document.id for document in referenced_documents],
                    document_context=(
                        list(memory_context["referenced_documents"])
                        if isinstance(memory_context.get("referenced_documents"), list)
                        else []
                    ),
                    refresh_pubmed_if_needed=refresh_pubmed_if_needed,
                ),
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
            )
            artifact_store.seed_for_run(run=run)
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
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "running",
                "chat_session_id": session.id,
                "research_objective": memory_context["objective"],
                "research_state_last_graph_snapshot_id": memory_context[
                    "last_graph_snapshot_id"
                ],
                "pending_question_count": pending_question_count(memory_context),
                "document_reference_count": len(referenced_documents),
            },
        )
        chat_session_store.update_session(
            space_id=space_id,
            session_id=session.id,
            last_run_id=run.id,
            status="running",
            title=resolved_title,
        )
        user_message = chat_session_store.add_message(
            space_id=space_id,
            session_id=session.id,
            role="user",
            content=content,
            run_id=run.id,
            metadata={
                "message_kind": "question",
                "document_ids": [document.id for document in referenced_documents],
            },
        )
        if user_message is None:
            error_message = "Failed to persist user chat message"
            _mark_failed_chat_run(
                space_id=space_id,
                session_id=UUID(session.id),
                run_id=run.id,
                error_message=error_message,
                run_registry=run_registry,
                artifact_store=artifact_store,
                chat_session_store=chat_session_store,
            )
            raise RuntimeError(error_message)

        try:
            result = await graph_chat_runner.run(
                HarnessGraphChatRequest(
                    question=content,
                    research_space_id=str(space_id),
                    model_id=model_id,
                    max_depth=max_depth,
                    top_k=top_k,
                    include_evidence_chains=include_evidence_chains,
                    objective=(
                        research_state.objective if research_state is not None else None
                    ),
                    current_hypotheses=(
                        tuple(research_state.current_hypotheses)
                        if research_state is not None
                        else ()
                    ),
                    pending_questions=(
                        tuple(research_state.pending_questions)
                        if research_state is not None
                        else ()
                    ),
                    graph_snapshot_summary=(
                        graph_snapshot.summary if graph_snapshot is not None else {}
                    ),
                    pending_review_proposal_count=pending_review_proposal_count,
                ),
            )
        except Exception as exc:
            workflow_error = f"Graph chat run failed: {exc}"
            _mark_failed_chat_run(
                space_id=space_id,
                session_id=UUID(session.id),
                run_id=run.id,
                error_message=str(exc),
                run_registry=run_registry,
                artifact_store=artifact_store,
                chat_session_store=chat_session_store,
            )
            raise RuntimeError(workflow_error) from exc
        append_skill_activity(
            space_id=space_id,
            run_id=run.id,
            skill_names=result.active_skill_names,
            source_run_id=result.search.agent_run_id,
            source_kind="graph_chat",
            artifact_store=artifact_store,
            run_registry=run_registry,
            runtime=runtime,
        )

        literature_refresh: GraphChatLiteratureRefresh | None = None
        if refresh_pubmed_if_needed and result.verification.status != "verified":
            try:
                search_job = run_pubmed_search(
                    runtime=runtime,
                    run=run,
                    request=build_chat_literature_request(
                        question=content,
                        objective=(
                            research_state.objective
                            if research_state is not None
                            else None
                        ),
                        result=result,
                    ),
                    step_key="graph_chat.pubmed_search",
                )
            except Exception as exc:  # noqa: BLE001
                result = result.model_copy(
                    update={
                        "warnings": [
                            *result.warnings,
                            f"Fresh literature refresh failed: {exc}",
                        ],
                    },
                )
            else:
                literature_refresh = GraphChatLiteratureRefresh(
                    source="pubmed",
                    trigger_reason=(
                        "needs_review"
                        if result.verification.status == "needs_review"
                        else "unverified"
                    ),
                    search_job_id=str(search_job.id),
                    query_preview=search_job.query_preview,
                    total_results=search_job.total_results,
                    preview_records=_preview_record_list(
                        search_job.result_metadata.get("preview_records"),
                    ),
                )
                answer_supplement = build_chat_literature_answer_supplement(
                    query_preview=literature_refresh.query_preview,
                    preview_records=literature_refresh.preview_records,
                )
                result = result.model_copy(
                    update={
                        **(
                            {
                                "answer_text": (
                                    f"{result.answer_text}\n\n{answer_supplement}"
                                ),
                            }
                            if answer_supplement is not None
                            else {}
                        ),
                        "fresh_literature": literature_refresh,
                        "chat_summary": (
                            f"{result.chat_summary} Literature refresh: "
                            f"{literature_refresh.total_results} PubMed results."
                        ),
                    },
                )
        elif not refresh_pubmed_if_needed and result.verification.status != "verified":
            result = result.model_copy(
                update={
                    "warnings": [
                        *result.warnings,
                        "Fresh literature refresh was skipped for this chat request.",
                    ],
                },
            )
        elif result.evidence_bundle:
            try:
                graph_write_candidates = derive_chat_graph_write_candidates(
                    space_id=space_id,
                    run=run,
                    result=result,
                    runtime=runtime,
                )
            except ChatGraphWriteCandidateError as exc:
                result = result.model_copy(
                    update={
                        "warnings": [
                            *result.warnings,
                            f"Graph-write candidate derivation failed: {exc}",
                        ],
                    },
                )
            except Exception as exc:  # noqa: BLE001
                result = result.model_copy(
                    update={
                        "warnings": [
                            *result.warnings,
                            f"Graph-write candidate derivation failed: {exc}",
                        ],
                    },
                )
            else:
                answer_supplement = build_chat_graph_write_answer_supplement(
                    list(graph_write_candidates),
                )
                result = result.model_copy(
                    update={
                        **(
                            {
                                "answer_text": (
                                    f"{result.answer_text}\n\n{answer_supplement}"
                                ),
                            }
                            if answer_supplement is not None
                            else {}
                        ),
                        "graph_write_candidates": list(graph_write_candidates),
                        "chat_summary": (
                            f"{result.chat_summary} Graph-write candidates: "
                            f"{len(graph_write_candidates)}."
                        ),
                    },
                )

        if referenced_documents:
            proposals_by_document_id = {
                document.id: [
                    {
                        "id": proposal.id,
                        "summary": proposal.summary,
                        "status": proposal.status,
                    }
                    for proposal in proposal_store.list_proposals(
                        space_id=space_id,
                        document_id=document.id,
                    )
                ]
                for document in referenced_documents
            }
            document_supplement = summarize_document_context(
                documents=referenced_documents,
                proposals_by_document_id=proposals_by_document_id,
            )
            if document_supplement is not None:
                result = result.model_copy(
                    update={
                        "answer_text": f"{result.answer_text}\n\n{document_supplement}",
                        "chat_summary": (
                            f"{result.chat_summary} Referenced documents: "
                            f"{len(referenced_documents)}."
                        ),
                    },
                )

        updated_research_state = research_state_store.upsert_state(
            space_id=space_id,
            objective=research_state.objective if research_state is not None else None,
            current_hypotheses=(
                list(research_state.current_hypotheses)
                if research_state is not None
                else []
            ),
            explored_questions=_normalized_unique_strings(
                (
                    list(research_state.explored_questions)
                    if research_state is not None
                    else []
                )
                + [content],
            ),
            pending_questions=(
                [
                    question
                    for question in research_state.pending_questions
                    if question.strip() != content.strip()
                ]
                if research_state is not None
                else []
            ),
            last_graph_snapshot_id=(
                graph_snapshot.id
                if graph_snapshot is not None
                else (
                    research_state.last_graph_snapshot_id
                    if research_state is not None
                    else None
                )
            ),
            last_learning_cycle_at=(
                research_state.last_learning_cycle_at
                if research_state is not None
                else None
            ),
            active_schedules=(
                list(research_state.active_schedules)
                if research_state is not None
                else []
            ),
            confidence_model=(
                research_state.confidence_model if research_state is not None else {}
            ),
            budget_policy=(
                research_state.budget_policy if research_state is not None else {}
            ),
            metadata={
                "last_chat_run_id": run.id,
                "last_chat_session_id": session.id,
            },
        )
        updated_memory_context = memory_context_artifact(
            research_state=updated_research_state,
            graph_snapshot=graph_snapshot,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="memory_context",
            media_type="application/json",
            content=updated_memory_context,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="grounded_answer_verification",
            media_type="application/json",
            content=result.verification.model_dump(mode="json"),
        )
        if literature_refresh is not None:
            artifact_store.put_artifact(
                space_id=space_id,
                run_id=run.id,
                artifact_key="fresh_literature",
                media_type="application/json",
                content=literature_refresh.model_dump(mode="json"),
            )
        if result.verification.status == "verified":
            artifact_store.put_artifact(
                space_id=space_id,
                run_id=run.id,
                artifact_key="graph_write_candidate_suggestions",
                media_type="application/json",
                content=_graph_write_candidate_artifact(
                    session_id=session.id,
                    run_id=run.id,
                    result=result,
                ),
            )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_chat_result",
            media_type="application/json",
            content=result.model_dump(mode="json"),
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="chat_summary",
            media_type="application/json",
            content={
                "session_id": session.id,
                "summary": result.chat_summary,
                "question": content,
                "answer": result.answer_text,
                "memory_context": updated_memory_context,
                "verification": result.verification.model_dump(mode="json"),
                "fresh_literature": (
                    literature_refresh.model_dump(mode="json")
                    if literature_refresh is not None
                    else None
                ),
                "document_ids": [document.id for document in referenced_documents],
                "graph_write_candidates": [
                    candidate.model_dump(mode="json")
                    for candidate in result.graph_write_candidates
                ],
            },
        )
        workspace_patch: JSONObject = {
            "status": "completed",
            "chat_session_id": session.id,
            "last_graph_chat_result_key": "graph_chat_result",
            "last_chat_summary_key": "chat_summary",
            "last_grounded_answer_verification_key": "grounded_answer_verification",
            "last_memory_context_key": "memory_context",
            "grounded_answer_verification_status": result.verification.status,
            "research_objective": updated_memory_context["objective"],
            "research_state_last_graph_snapshot_id": updated_memory_context[
                "last_graph_snapshot_id"
            ],
            "pending_question_count": pending_question_count(updated_memory_context),
            "document_reference_count": len(referenced_documents),
        }
        if result.verification.status == "verified":
            workspace_patch["last_graph_write_candidate_suggestions_key"] = (
                "graph_write_candidate_suggestions"
            )
            workspace_patch["graph_write_candidate_count"] = len(
                result.graph_write_candidates,
            )
        if literature_refresh is not None:
            workspace_patch["last_fresh_literature_key"] = "fresh_literature"
            workspace_patch["fresh_literature_result_count"] = (
                literature_refresh.total_results
            )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch=workspace_patch,
        )
        if literature_refresh is not None:
            run_registry.record_event(
                space_id=space_id,
                run_id=run.id,
                event_type="chat.literature_refreshed",
                message=(
                    f"Loaded {literature_refresh.total_results} PubMed results for "
                    "fresh literature review."
                ),
                payload=literature_refresh.model_dump(mode="json"),
            )
        if result.verification.status == "verified":
            run_registry.record_event(
                space_id=space_id,
                run_id=run.id,
                event_type="chat.graph_write_candidates_derived",
                message=(
                    "Derived "
                    f"{len(result.graph_write_candidates)} graph-write candidate(s) "
                    "from verified chat evidence."
                ),
                payload={
                    "candidate_count": len(result.graph_write_candidates),
                    "artifact_key": "graph_write_candidate_suggestions",
                },
            )
        updated_run = run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="completed",
        )
        assistant_message = chat_session_store.add_message(
            space_id=space_id,
            session_id=session.id,
            role="assistant",
            content=result.answer_text,
            run_id=run.id,
            metadata={
                "chat_summary": result.chat_summary,
                "graph_chat_result_key": "graph_chat_result",
                "chat_summary_key": "chat_summary",
                "grounded_answer_verification_key": "grounded_answer_verification",
                "memory_context_key": "memory_context",
                "document_ids": [document.id for document in referenced_documents],
                **(
                    {
                        "graph_write_candidate_suggestions_key": "graph_write_candidate_suggestions",
                    }
                    if result.verification.status == "verified"
                    else {}
                ),
                **(
                    {"fresh_literature_key": "fresh_literature"}
                    if literature_refresh is not None
                    else {}
                ),
            },
        )
        if assistant_message is None:
            error_message = "Failed to persist assistant chat message"
            raise RuntimeError(error_message)
        updated_session = chat_session_store.update_session(
            space_id=space_id,
            session_id=session.id,
            last_run_id=run.id,
            status="active",
        )
        final_run = updated_run or run
        final_session = updated_session or session
        result_keys: list[str] = [
            "graph_chat_result",
            "chat_summary",
            "grounded_answer_verification",
            "memory_context",
        ]
        if result.verification.status == "verified":
            result_keys.append("graph_write_candidate_suggestions")
        if literature_refresh is not None:
            result_keys.append("fresh_literature")
        store_primary_result_artifact(
            artifact_store=artifact_store,
            space_id=space_id,
            run_id=run.id,
            artifact_key="chat_run_response",
            content={
                "run": serialize_run_record(run=final_run),
                "session": serialize_chat_session_record(session=final_session),
                "user_message": serialize_chat_message_record(message=user_message),
                "assistant_message": serialize_chat_message_record(
                    message=assistant_message,
                ),
                "result": result.model_dump(mode="json"),
            },
            status_value="completed",
            result_keys=tuple(result_keys),
        )
        return GraphChatMessageExecution(
            run=final_run,
            session=final_session,
            user_message=user_message,
            assistant_message=assistant_message,
            result=result,
        )
    finally:
        graph_api_gateway.close()


__all__ = [
    "DEFAULT_CHAT_SESSION_TITLE",
    "GraphChatMessageExecution",
    "build_graph_chat_run_input_payload",
    "derive_session_title",
    "execute_graph_chat_message",
    "load_chat_memory_context",
    "memory_context_artifact",
    "pending_question_count",
    "queue_graph_chat_message_run",
]
