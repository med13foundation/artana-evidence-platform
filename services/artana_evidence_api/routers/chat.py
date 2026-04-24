"""Chat session endpoints for the standalone harness service."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import UUID  # noqa: TC003

from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.auth import (
    HarnessUser,  # noqa: TC001
    get_current_harness_user,
)
from artana_evidence_api.chat_graph_write_workflow import (
    ChatGraphWriteArtifactError,
    ChatGraphWriteCandidateError,
    ChatGraphWriteCandidateRequest,
    ChatGraphWriteVerificationError,
    chat_graph_write_source_key,
    load_graph_chat_artifacts,
    require_verified_graph_chat_result,
    stage_chat_graph_write_proposals,
)
from artana_evidence_api.chat_sessions import (
    HarnessChatMessageRecord,  # noqa: TC001
    HarnessChatSessionRecord,  # noqa: TC001
    HarnessChatSessionStore,  # noqa: TC001
)
from artana_evidence_api.chat_workflow import (
    DEFAULT_CHAT_SESSION_TITLE,
    GraphChatMessageExecution,
    load_chat_memory_context,
    memory_context_artifact,
    queue_graph_chat_message_run,
)
from artana_evidence_api.config import get_settings
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_chat_session_store,
    get_document_store,
    get_graph_api_gateway,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_proposal_store,
    get_research_state_store,
    get_run_registry,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,  # noqa: TC001
    HarnessDocumentStore,  # noqa: TC001
)
from artana_evidence_api.graph_chat_runtime import (
    GraphChatResult,
)
from artana_evidence_api.graph_client import (
    GraphServiceClientError,
    GraphTransportBundle,  # noqa: TC001
)
from artana_evidence_api.graph_snapshot import (  # noqa: TC001
    HarnessGraphSnapshotStore,
)
from artana_evidence_api.proposal_actions import (
    decide_proposal,
    promote_to_graph_claim,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalRecord,  # noqa: TC001
)
from artana_evidence_api.queued_run_support import (
    build_accepted_run_response,
    load_primary_result_artifact,
    maybe_execute_test_worker_run,
    prefers_respond_async,
    raise_for_failed_run,
    require_worker_ready,
    should_require_worker_ready,
    wait_for_terminal_run,
    wake_worker_for_queued_run,
)
from artana_evidence_api.research_state import (  # noqa: TC001
    HarnessResearchStateStore,
)
from artana_evidence_api.response_serialization import (
    serialize_chat_message_record,
    serialize_run_record,
)
from artana_evidence_api.routers.proposals import HarnessProposalResponse
from artana_evidence_api.routers.runs import (
    HarnessRunProgressResponse,
    HarnessRunResponse,
)
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from artana_evidence_api.transparency import (
    append_manual_review_decision,
    ensure_run_transparency_seed,
)
from artana_evidence_api.types.common import (  # noqa: TC001
    JSONObject,
    json_array_or_empty,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessWorkspaceRecord
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.run_registry import (
        HarnessRunEventRecord,
        HarnessRunProgressRecord,
        HarnessRunRecord,
    )

router = APIRouter(
    prefix="/v1/spaces",
    tags=["chat"],
    dependencies=[Depends(require_harness_space_read_access)],
)

_CHAT_SESSION_STORE_DEPENDENCY = Depends(get_chat_session_store)
_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_GRAPH_SNAPSHOT_STORE_DEPENDENCY = Depends(get_graph_snapshot_store)
_DOCUMENT_STORE_DEPENDENCY = Depends(get_document_store)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_CHAT_STREAM_TERMINAL_STATUSES = frozenset({"completed", "failed", "paused"})


@dataclass(frozen=True, slots=True)
class _PreparedChatMessageRun:
    """Prepared chat run state built off the event loop."""

    queued_run: HarnessRunRecord


class ChatSessionCreateRequest(BaseModel):
    """Create one chat session."""

    model_config = ConfigDict(strict=True)

    title: str | None = Field(default=None, min_length=1, max_length=256)


class ChatMessageCreateRequest(BaseModel):
    """Send one message to a graph chat session."""

    model_config = ConfigDict(strict=False)

    content: str = Field(..., min_length=1, max_length=4000)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=10, ge=1, le=25)
    include_evidence_chains: bool = True
    document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    refresh_pubmed_if_needed: bool = True


class ChatMessageResponse(BaseModel):
    """Serialized chat message payload."""

    model_config = ConfigDict(strict=True)

    id: str
    session_id: str
    role: str
    content: str
    run_id: str | None
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessChatMessageRecord) -> ChatMessageResponse:
        return cls(
            id=record.id,
            session_id=record.session_id,
            role=record.role,
            content=record.content,
            run_id=record.run_id,
            metadata=record.metadata,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class ChatGraphWriteProposalRequest(BaseModel):
    """Request payload for converting chat findings into proposals."""

    model_config = ConfigDict(strict=True)

    candidates: list[ChatGraphWriteCandidateRequest] | None = Field(
        default=None,
        max_length=25,
    )


class ChatGraphWriteCandidateDecisionRequest(BaseModel):
    """Promote or reject one inline chat graph-write candidate."""

    model_config = ConfigDict(strict=True)

    decision: Literal["promote", "reject"]
    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: JSONObject = Field(default_factory=dict)


class ChatSessionResponse(BaseModel):
    """Serialized chat session payload."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    title: str
    created_by: str
    last_run_id: str | None
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessChatSessionRecord) -> ChatSessionResponse:
        return cls(
            id=record.id,
            space_id=record.space_id,
            title=record.title,
            created_by=record.created_by,
            last_run_id=record.last_run_id,
            status=record.status,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class ChatGraphWriteProposalRecordResponse(BaseModel):
    """Serialized proposal staged from chat findings."""

    model_config = ConfigDict(strict=True)

    id: str
    run_id: str
    proposal_type: str
    title: str
    summary: str
    status: str
    confidence: float
    ranking_score: float
    payload: JSONObject
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(
        cls,
        record: HarnessProposalRecord,
    ) -> ChatGraphWriteProposalRecordResponse:
        return cls(
            id=record.id,
            run_id=record.run_id,
            proposal_type=record.proposal_type,
            title=record.title,
            summary=record.summary,
            status=record.status,
            confidence=record.confidence,
            ranking_score=record.ranking_score,
            payload=record.payload,
            metadata=record.metadata,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class ChatSessionListResponse(BaseModel):
    """List response for chat sessions."""

    model_config = ConfigDict(strict=True)

    sessions: list[ChatSessionResponse]
    total: int
    offset: int
    limit: int


class ChatSessionDetailResponse(BaseModel):
    """Chat session state including ordered message history."""

    model_config = ConfigDict(strict=True)

    session: ChatSessionResponse
    messages: list[ChatMessageResponse]


class ChatMessageRunResponse(BaseModel):
    """Combined graph-chat run result for one sent message."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    session: ChatSessionResponse
    user_message: ChatMessageResponse
    assistant_message: ChatMessageResponse
    result: GraphChatResult


class ChatMessageAcceptedResponse(BaseModel):
    """Accepted async response for one queued chat message."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    session: ChatSessionResponse
    progress_url: str
    events_url: str
    workspace_url: str
    artifacts_url: str
    stream_url: str


class ChatGraphWriteProposalResponse(BaseModel):
    """Proposals created from the latest graph-chat findings."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    session: ChatSessionResponse
    proposals: list[HarnessProposalResponse]
    proposal_count: int


class ChatGraphWriteCandidateDecisionResponse(BaseModel):
    """Decision result for one inline chat graph-write candidate."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    session: ChatSessionResponse
    candidate_index: int
    candidate: ChatGraphWriteCandidateRequest
    proposal: ChatGraphWriteProposalRecordResponse


def build_chat_message_run_response(
    execution: GraphChatMessageExecution,
) -> ChatMessageRunResponse | JSONResponse:
    """Serialize one graph-chat execution into the public route response."""
    return ChatMessageRunResponse(
        run=HarnessRunResponse.from_record(execution.run),
        session=ChatSessionResponse.from_record(execution.session),
        user_message=ChatMessageResponse.from_record(execution.user_message),
        assistant_message=ChatMessageResponse.from_record(execution.assistant_message),
        result=execution.result,
    )


def _chat_message_stream_url(*, space_id: UUID, session_id: UUID, run_id: str) -> str:
    return f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages/{run_id}/stream"


def _build_chat_message_accepted_response(
    *,
    run: HarnessRunResponse,
    session: ChatSessionResponse,
    stream_url: str,
) -> ChatMessageAcceptedResponse:
    return ChatMessageAcceptedResponse(
        run=run,
        session=session,
        progress_url=f"/v1/spaces/{run.space_id}/runs/{run.id}/progress",
        events_url=f"/v1/spaces/{run.space_id}/runs/{run.id}/events",
        workspace_url=f"/v1/spaces/{run.space_id}/runs/{run.id}/workspace",
        artifacts_url=f"/v1/spaces/{run.space_id}/runs/{run.id}/artifacts",
        stream_url=stream_url,
    )


def _sse_frame(*, event: str, data: JSONObject, event_id: str | None = None) -> str:
    payload = [f"event: {event}"]
    if event_id is not None:
        payload.append(f"id: {event_id}")
    payload.append(f"data: {json.dumps(data, separators=(',', ':'))}")
    return "\n".join(payload) + "\n\n"


def _serialize_progress_for_stream(
    progress: HarnessRunProgressRecord | None,
) -> JSONObject | None:
    if progress is None:
        return None
    return HarnessRunProgressResponse.from_record(progress).model_dump(mode="json")


def _serialize_workspace_for_stream(
    workspace: HarnessWorkspaceRecord | None,
) -> JSONObject | None:
    if workspace is None:
        return None
    return {
        "space_id": workspace.space_id,
        "run_id": workspace.run_id,
        "snapshot": workspace.snapshot,
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
    }


def _serialize_run_event_for_stream(event: HarnessRunEventRecord) -> JSONObject:
    return {
        "id": event.id,
        "run_id": event.run_id,
        "space_id": event.space_id,
        "event_type": event.event_type,
        "status": event.status,
        "message": event.message,
        "progress_percent": event.progress_percent,
        "payload": event.payload,
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }


def _accepted_chat_session_response(
    *,
    space_id: UUID,
    session_id: UUID,
    fallback_session: HarnessChatSessionRecord,
    chat_session_store: HarnessChatSessionStore,
) -> ChatSessionResponse:
    refreshed_session = chat_session_store.get_session(
        space_id=space_id,
        session_id=session_id,
    )
    return ChatSessionResponse.from_record(refreshed_session or fallback_session)


def _require_chat_run_for_session(
    *,
    space_id: UUID,
    session_id: UUID,
    run_id: str,
    run_registry: HarnessRunRegistry,
) -> HarnessRunRecord:
    run = run_registry.get_run(space_id=space_id, run_id=run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat run '{run_id}' not found in space '{space_id}'",
        )
    if run.harness_id != "graph-chat":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' is not a graph-chat run.",
        )
    if str(run.input_payload.get("session_id")) != str(session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(f"Run '{run_id}' does not belong to chat session '{session_id}'."),
        )
    return run


def _require_session(
    *,
    space_id: UUID,
    session_id: UUID,
    chat_session_store: HarnessChatSessionStore,
) -> HarnessChatSessionRecord:
    session = chat_session_store.get_session(space_id=space_id, session_id=session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session '{session_id}' not found in space '{space_id}'",
        )
    return session


def _require_documents(
    *,
    space_id: UUID,
    document_ids: list[UUID],
    document_store: HarnessDocumentStore,
) -> tuple[HarnessDocumentRecord, ...]:
    documents: list[HarnessDocumentRecord] = []
    for document_id in document_ids:
        document = document_store.get_document(
            space_id=space_id,
            document_id=document_id,
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found in space '{space_id}'",
            )
        documents.append(document)
    return tuple(documents)


def _require_latest_chat_run(
    *,
    space_id: UUID,
    session: HarnessChatSessionRecord,
    run_registry: HarnessRunRegistry,
) -> HarnessRunResponse:
    if session.last_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chat session has no graph-chat run to convert into proposals",
        )
    run = run_registry.get_run(space_id=space_id, run_id=session.last_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Latest chat run '{session.last_run_id}' not found in space "
                f"'{space_id}'"
            ),
        )
    return HarnessRunResponse.from_record(run)


def _require_graph_chat_artifacts(
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> tuple[GraphChatResult, JSONObject]:
    graph_chat_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="graph_chat_result",
    )
    if graph_chat_artifact is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Latest chat run does not have a graph_chat_result artifact",
        )
    chat_summary_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="chat_summary",
    )
    if chat_summary_artifact is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Latest chat run does not have a chat_summary artifact",
        )
    try:
        graph_chat_result = GraphChatResult.model_validate(graph_chat_artifact.content)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stored graph_chat_result artifact is invalid: {exc}",
        ) from exc
    return graph_chat_result, chat_summary_artifact.content


def _resolve_chat_graph_write_candidates(
    *,
    request: ChatGraphWriteProposalRequest,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> list[ChatGraphWriteCandidateRequest]:
    if request.candidates is not None:
        return request.candidates
    graph_chat_result, _ = load_graph_chat_artifacts(
        space_id=space_id,
        run_id=run_id,
        artifact_store=artifact_store,
    )
    return list(graph_chat_result.graph_write_candidates)


def _require_reviewable_chat_graph_write_candidate(
    *,
    space_id: UUID,
    run_id: str,
    candidate_index: int,
    artifact_store: HarnessArtifactStore,
) -> ChatGraphWriteCandidateRequest:
    graph_chat_result, _ = load_graph_chat_artifacts(
        space_id=space_id,
        run_id=run_id,
        artifact_store=artifact_store,
    )
    require_verified_graph_chat_result(graph_chat_result)
    candidates = graph_chat_result.graph_write_candidates
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Graph-write candidate index '{candidate_index}' not found for "
                f"chat run '{run_id}'"
            ),
        )
    return candidates[candidate_index]


def _find_existing_chat_graph_write_proposal(
    *,
    space_id: UUID,
    run_id: str,
    session_id: UUID,
    candidate: ChatGraphWriteCandidateRequest,
    proposal_store: HarnessProposalStore,
) -> HarnessProposalRecord | None:
    candidate_source_key = chat_graph_write_source_key(
        session_id=session_id,
        candidate=candidate,
    )
    proposals = proposal_store.list_proposals(space_id=space_id, run_id=run_id)
    for proposal in proposals:
        if (
            proposal.source_kind == "chat_graph_write"
            and proposal.source_key == candidate_source_key
        ):
            return proposal
    return None


def _ensure_pending_chat_graph_write_proposal(  # noqa: PLR0913
    *,
    space_id: UUID,
    run_id: str,
    session_id: UUID,
    candidate: ChatGraphWriteCandidateRequest,
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    run_registry: HarnessRunRegistry,
) -> HarnessProposalRecord:
    existing = _find_existing_chat_graph_write_proposal(
        space_id=space_id,
        run_id=run_id,
        session_id=session_id,
        candidate=candidate,
        proposal_store=proposal_store,
    )
    if existing is not None:
        if existing.status != "pending_review":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Chat graph-write candidate is already decided with status "
                    f"'{existing.status}'"
                ),
            )
        return existing
    execution = stage_chat_graph_write_proposals(
        space_id=space_id,
        session_id=session_id,
        run_id=run_id,
        candidates=[candidate],
        artifact_store=artifact_store,
        proposal_store=proposal_store,
        run_registry=run_registry,
    )
    if not execution.proposals:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to stage chat graph-write proposal for direct review",
        )
    return execution.proposals[0]


def _prepare_chat_message_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    session: HarnessChatSessionRecord,
    request: ChatMessageCreateRequest,
    current_user: HarnessUser,
    chat_session_store: HarnessChatSessionStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphTransportBundle,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    document_store: HarnessDocumentStore,
) -> _PreparedChatMessageRun:
    """Build the queued chat run using a sync preflight path."""
    research_state, graph_snapshot = load_chat_memory_context(
        space_id=space_id,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
    )
    memory_context = memory_context_artifact(
        research_state=research_state,
        graph_snapshot=graph_snapshot,
    )
    referenced_documents = _require_documents(
        space_id=space_id,
        document_ids=request.document_ids,
        document_store=document_store,
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
    graph_health = graph_api_gateway.get_health()
    queued_run = queue_graph_chat_message_run(
        space_id=space_id,
        session=session,
        title=session.title,
        content=request.content,
        current_user_id=current_user.id,
        model_id=request.model_id,
        max_depth=request.max_depth,
        top_k=request.top_k,
        include_evidence_chains=request.include_evidence_chains,
        memory_context=memory_context,
        document_ids=[str(document_id) for document_id in request.document_ids],
        document_context=[
            item
            for item in json_array_or_empty(memory_context.get("referenced_documents"))
            if isinstance(item, dict)
        ],
        refresh_pubmed_if_needed=request.refresh_pubmed_if_needed,
        graph_service_status=graph_health.status,
        graph_service_version=graph_health.version,
        chat_session_store=chat_session_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    return _PreparedChatMessageRun(queued_run=queued_run)


@router.get(
    "/{space_id}/chat-sessions",
    response_model=ChatSessionListResponse,
    summary="List chat sessions",
)
def list_chat_sessions(
    space_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
) -> ChatSessionListResponse:
    sessions = chat_session_store.list_sessions(space_id=space_id)
    total = len(sessions)
    paged = sessions[offset : offset + limit]
    return ChatSessionListResponse(
        sessions=[ChatSessionResponse.from_record(record) for record in paged],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/chat-sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create chat session",
    dependencies=[Depends(require_harness_space_write_access)],
)
def create_chat_session(
    space_id: UUID,
    request: ChatSessionCreateRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
) -> ChatSessionResponse:
    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or DEFAULT_CHAT_SESSION_TITLE
    session = chat_session_store.create_session(
        space_id=space_id,
        title=resolved_title,
        created_by=current_user.id,
    )
    return ChatSessionResponse.from_record(session)


@router.get(
    "/{space_id}/chat-sessions/{session_id}",
    response_model=ChatSessionDetailResponse,
    summary="Get chat session state",
)
def get_chat_session(
    space_id: UUID,
    session_id: UUID,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
) -> ChatSessionDetailResponse:
    session = _require_session(
        space_id=space_id,
        session_id=session_id,
        chat_session_store=chat_session_store,
    )
    messages = chat_session_store.list_messages(
        space_id=space_id,
        session_id=session_id,
    )
    return ChatSessionDetailResponse(
        session=ChatSessionResponse.from_record(session),
        messages=[ChatMessageResponse.from_record(record) for record in messages],
    )


@router.post(
    "/{space_id}/chat-sessions/{session_id}/messages",
    response_model=ChatMessageRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": ChatMessageAcceptedResponse}},
    summary="Send message and run graph chat",
    dependencies=[Depends(require_harness_space_write_access)],
)
async def send_chat_message(  # noqa: C901, PLR0912, PLR0913, PLR0915
    space_id: UUID,
    session_id: UUID,
    message_request: ChatMessageCreateRequest,
    *,
    prefer: Annotated[str | None, Header()] = None,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
    graph_snapshot_store: HarnessGraphSnapshotStore = _GRAPH_SNAPSHOT_STORE_DEPENDENCY,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> ChatMessageRunResponse | JSONResponse:
    session = _require_session(
        space_id=space_id,
        session_id=session_id,
        chat_session_store=chat_session_store,
    )
    if message_request.document_ids:
        _require_documents(
            space_id=space_id,
            document_ids=message_request.document_ids,
            document_store=document_store,
        )
    try:
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Graph chat")
        prepared_run = await asyncio.to_thread(
            _prepare_chat_message_run,
            space_id=space_id,
            session=session,
            request=message_request,
            current_user=current_user,
            chat_session_store=chat_session_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            graph_api_gateway=graph_api_gateway,
            research_state_store=research_state_store,
            graph_snapshot_store=graph_snapshot_store,
            document_store=document_store,
        )
        ensure_run_transparency_seed(
            run=prepared_run.queued_run,
            artifact_store=artifact_store,
            runtime=execution_services.runtime,
        )
        wake_worker_for_queued_run(
            run=prepared_run.queued_run,
            execution_services=execution_services,
        )
        accepted_session = _accepted_chat_session_response(
            space_id=space_id,
            session_id=session_id,
            fallback_session=session,
            chat_session_store=chat_session_store,
        )
        if prefers_respond_async(prefer):
            accepted = _build_chat_message_accepted_response(
                run=HarnessRunResponse.from_record(prepared_run.queued_run),
                session=accepted_session,
                stream_url=_chat_message_stream_url(
                    space_id=space_id,
                    session_id=session_id,
                    run_id=prepared_run.queued_run.id,
                ),
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=accepted.model_dump(mode="json"),
                headers={"Preference-Applied": "respond-async"},
            )
        await maybe_execute_test_worker_run(
            run=prepared_run.queued_run,
            services=execution_services,
        )
        wait_outcome = await wait_for_terminal_run(
            space_id=space_id,
            run_id=prepared_run.queued_run.id,
            run_registry=run_registry,
            timeout_seconds=get_settings().sync_wait_timeout_seconds,
            poll_interval_seconds=get_settings().sync_wait_poll_seconds,
        )
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    finally:
        graph_api_gateway.close()
    if wait_outcome.timed_out:
        accepted_run_response = build_accepted_run_response(
            run=prepared_run.queued_run,
            run_registry=run_registry,
            stream_url=_chat_message_stream_url(
                space_id=space_id,
                session_id=session_id,
                run_id=prepared_run.queued_run.id,
            ),
            session=accepted_session.model_dump(mode="json"),
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=accepted_run_response.model_dump(mode="json"),
        )
    if wait_outcome.run is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reload completed graph-chat run.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=prepared_run.queued_run.id,
    )
    return ChatMessageRunResponse.model_validate(payload, strict=False)


@router.get(
    "/{space_id}/chat-sessions/{session_id}/messages/{run_id}/stream",
    summary="Stream chat run events",
    dependencies=[Depends(require_harness_space_read_access)],
)
async def stream_chat_message(
    space_id: UUID,
    session_id: UUID,
    run_id: str,
    *,
    request: Request,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> StreamingResponse:
    session = _require_session(
        space_id=space_id,
        session_id=session_id,
        chat_session_store=chat_session_store,
    )
    run = _require_chat_run_for_session(
        space_id=space_id,
        session_id=session_id,
        run_id=run_id,
        run_registry=run_registry,
    )
    progress = run_registry.get_progress(space_id=space_id, run_id=run_id)
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)

    async def event_stream() -> AsyncIterator[str]:
        seen_event_ids: set[str] = set()
        seen_message_ids: set[str] = set()
        emitted_result_ids: set[str] = set()
        yield _sse_frame(
            event="run.snapshot",
            data={
                "run": HarnessRunResponse.from_record(run).model_dump(mode="json"),
                "session": ChatSessionResponse.from_record(session).model_dump(
                    mode="json",
                ),
                "progress": _serialize_progress_for_stream(progress),
                "workspace": _serialize_workspace_for_stream(workspace),
            },
            event_id=f"snapshot:{run_id}",
        )
        poll_interval = get_settings().sync_wait_poll_seconds
        while True:
            if await request.is_disconnected():
                break
            current_run = _require_chat_run_for_session(
                space_id=space_id,
                session_id=session_id,
                run_id=run_id,
                run_registry=run_registry,
            )
            current_progress = run_registry.get_progress(
                space_id=space_id,
                run_id=run_id,
            )
            current_workspace = artifact_store.get_workspace(
                space_id=space_id,
                run_id=run_id,
            )
            current_events = run_registry.list_events(
                space_id=space_id,
                run_id=run_id,
                limit=1000,
            )
            for current_event in current_events:
                if current_event.id in seen_event_ids:
                    continue
                seen_event_ids.add(current_event.id)
                yield _sse_frame(
                    event=current_event.event_type,
                    event_id=current_event.id,
                    data=_serialize_run_event_for_stream(current_event),
                )
            current_messages = chat_session_store.list_messages(
                space_id=space_id,
                session_id=session_id,
            )
            for message in current_messages:
                if message.run_id != run_id or message.id in seen_message_ids:
                    continue
                seen_message_ids.add(message.id)
                yield _sse_frame(
                    event="chat.message",
                    event_id=message.id,
                    data=serialize_chat_message_record(message=message),
                )
            primary_result_key = (
                current_workspace.snapshot.get("primary_result_key")
                if current_workspace is not None
                else None
            )
            if isinstance(primary_result_key, str) and primary_result_key.strip() != "":
                primary_result = artifact_store.get_artifact(
                    space_id=space_id,
                    run_id=run_id,
                    artifact_key=primary_result_key,
                )
                if primary_result is not None:
                    result_event_id = (
                        f"{primary_result.key}:{primary_result.updated_at.isoformat()}"
                    )
                    if result_event_id not in emitted_result_ids:
                        emitted_result_ids.add(result_event_id)
                        yield _sse_frame(
                            event="chat.result",
                            event_id=result_event_id,
                            data=primary_result.content,
                        )
            if current_run.status in _CHAT_STREAM_TERMINAL_STATUSES:
                terminal_payload: JSONObject = {
                    "run": serialize_run_record(run=current_run),
                    "progress": _serialize_progress_for_stream(current_progress),
                    "workspace": _serialize_workspace_for_stream(current_workspace),
                }
                yield _sse_frame(
                    event=f"run.{current_run.status}",
                    event_id=f"terminal:{current_run.id}:{current_run.updated_at.isoformat()}",
                    data=terminal_payload,
                )
                yield _sse_frame(
                    event="stream.complete",
                    event_id=f"stream.complete:{current_run.id}",
                    data={"run_id": current_run.id, "status": current_run.status},
                )
                break
            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform"},
    )


@router.post(
    "/{space_id}/chat-sessions/{session_id}/proposals/graph-write",
    response_model=ChatGraphWriteProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Convert chat findings into graph proposals",
    dependencies=[Depends(require_harness_space_write_access)],
)
def create_chat_graph_write_proposals(  # noqa: PLR0913
    space_id: UUID,
    session_id: UUID,
    request: ChatGraphWriteProposalRequest,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
) -> ChatGraphWriteProposalResponse:
    session = _require_session(
        space_id=space_id,
        session_id=session_id,
        chat_session_store=chat_session_store,
    )
    run = _require_latest_chat_run(
        space_id=space_id,
        session=session,
        run_registry=run_registry,
    )
    try:
        resolved_candidates = _resolve_chat_graph_write_candidates(
            request=request,
            space_id=space_id,
            run_id=run.id,
            artifact_store=artifact_store,
        )
        execution = stage_chat_graph_write_proposals(
            space_id=space_id,
            session_id=session_id,
            run_id=run.id,
            candidates=resolved_candidates,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            run_registry=run_registry,
        )
    except ChatGraphWriteCandidateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except (ChatGraphWriteArtifactError, ChatGraphWriteVerificationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    refreshed_session = chat_session_store.get_session(
        space_id=space_id,
        session_id=session_id,
    )
    return ChatGraphWriteProposalResponse(
        run=run,
        session=ChatSessionResponse.from_record(refreshed_session or session),
        proposals=[
            HarnessProposalResponse.from_record(record)
            for record in execution.proposals
        ],
        proposal_count=len(execution.proposals),
    )


@router.post(
    "/{space_id}/chat-sessions/{session_id}/graph-write-candidates/{candidate_index}/review",
    response_model=ChatGraphWriteCandidateDecisionResponse,
    summary="Promote or reject one inline graph-write candidate",
    dependencies=[Depends(require_harness_space_write_access)],
)
def review_chat_graph_write_candidate(  # noqa: PLR0913
    space_id: UUID,
    session_id: UUID,
    candidate_index: int,
    request: ChatGraphWriteCandidateDecisionRequest,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> ChatGraphWriteCandidateDecisionResponse:
    session = _require_session(
        space_id=space_id,
        session_id=session_id,
        chat_session_store=chat_session_store,
    )
    run = _require_latest_chat_run(
        space_id=space_id,
        session=session,
        run_registry=run_registry,
    )
    try:
        candidate = _require_reviewable_chat_graph_write_candidate(
            space_id=space_id,
            run_id=run.id,
            candidate_index=candidate_index,
            artifact_store=artifact_store,
        )
        proposal = _ensure_pending_chat_graph_write_proposal(
            space_id=space_id,
            run_id=run.id,
            session_id=session_id,
            candidate=candidate,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            run_registry=run_registry,
        )
        request_metadata: JSONObject = {
            **request.metadata,
            "chat_candidate_index": candidate_index,
            "chat_session_id": str(session_id),
        }
        workspace_patch: JSONObject = {
            "last_chat_graph_write_candidate_index": candidate_index,
            "last_chat_graph_write_candidate_source_key": proposal.source_key,
            "last_chat_graph_write_candidate_decision": request.decision,
        }
        if request.decision == "promote":
            promotion_metadata = promote_to_graph_claim(
                space_id=space_id,
                proposal=proposal,
                request_metadata=request_metadata,
                graph_api_gateway=graph_api_gateway,
            )
            updated_proposal = decide_proposal(
                space_id=space_id,
                proposal_id=proposal.id,
                decision_status="promoted",
                decision_reason=request.reason,
                request_metadata=request_metadata,
                proposal_store=proposal_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                decision_metadata=promotion_metadata,
                event_payload={
                    "candidate_index": candidate_index,
                    "source_key": proposal.source_key,
                    **promotion_metadata,
                },
                workspace_patch={
                    **workspace_patch,
                    "last_promoted_graph_claim_id": promotion_metadata[
                        "graph_claim_id"
                    ],
                    "last_promoted_graph_relation_id": promotion_metadata.get(
                        "graph_relation_id",
                    ),
                },
            )
            append_manual_review_decision(
                space_id=space_id,
                run_id=run.id,
                tool_name="create_graph_claim",
                decision="promote",
                reason=request.reason,
                artifact_key="graph_write_candidate_suggestions",
                metadata={
                    "candidate_index": candidate_index,
                    "proposal_id": updated_proposal.id,
                    "chat_session_id": str(session_id),
                    "source_key": proposal.source_key,
                    "graph_claim_id": promotion_metadata["graph_claim_id"],
                },
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=execution_services.runtime,
            )
        else:
            updated_proposal = decide_proposal(
                space_id=space_id,
                proposal_id=proposal.id,
                decision_status="rejected",
                decision_reason=request.reason,
                request_metadata=request_metadata,
                proposal_store=proposal_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                event_payload={
                    "candidate_index": candidate_index,
                    "source_key": proposal.source_key,
                },
                workspace_patch=workspace_patch,
            )
            append_manual_review_decision(
                space_id=space_id,
                run_id=run.id,
                tool_name="chat_graph_write_review",
                decision="reject",
                reason=request.reason,
                artifact_key="graph_write_candidate_suggestions",
                metadata={
                    "candidate_index": candidate_index,
                    "proposal_id": updated_proposal.id,
                    "chat_session_id": str(session_id),
                    "source_key": proposal.source_key,
                },
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=execution_services.runtime,
            )
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    except (ChatGraphWriteArtifactError, ChatGraphWriteVerificationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    finally:
        graph_api_gateway.close()
    refreshed_session = chat_session_store.get_session(
        space_id=space_id,
        session_id=session_id,
    )
    return ChatGraphWriteCandidateDecisionResponse(
        run=run,
        session=ChatSessionResponse.from_record(refreshed_session or session),
        candidate_index=candidate_index,
        candidate=candidate,
        proposal=ChatGraphWriteProposalRecordResponse.from_record(updated_proposal),
    )


__all__ = [
    "ChatGraphWriteCandidateDecisionRequest",
    "ChatGraphWriteCandidateDecisionResponse",
    "ChatGraphWriteCandidateRequest",
    "ChatGraphWriteProposalRecordResponse",
    "ChatGraphWriteProposalRequest",
    "ChatGraphWriteProposalResponse",
    "ChatMessageCreateRequest",
    "ChatMessageResponse",
    "ChatMessageRunResponse",
    "ChatSessionCreateRequest",
    "ChatSessionDetailResponse",
    "ChatSessionListResponse",
    "ChatSessionResponse",
    "build_chat_message_run_response",
    "create_chat_graph_write_proposals",
    "create_chat_session",
    "get_chat_session",
    "list_chat_sessions",
    "review_chat_graph_write_candidate",
    "router",
    "send_chat_message",
]
