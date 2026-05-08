"""Shared graph-chat message queueing helpers for chat routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from artana_evidence_api.chat_workflow import (
    load_chat_memory_context,
    memory_context_artifact,
    queue_graph_chat_message_run,
)
from artana_evidence_api.types.common import JSONObject, json_array_or_empty

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.auth import HarnessUser
    from artana_evidence_api.chat_sessions import (
        HarnessChatSessionRecord,
        HarnessChatSessionStore,
    )
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry


@dataclass(frozen=True, slots=True)
class PreparedChatMessageRun:
    """Prepared chat run state built off the event loop."""

    queued_run: HarnessRunRecord


class ChatDocumentNotFoundError(Exception):
    """Raised when a chat request references a missing document."""

    def __init__(self, document_id: UUID, space_id: UUID) -> None:
        super().__init__(f"Document '{document_id}' not found in space '{space_id}'")


class ChatMessageRunRequest(Protocol):
    """Shape needed to queue a chat-message run."""

    content: str
    model_id: str | None
    max_depth: int
    top_k: int
    include_evidence_chains: bool
    document_ids: list[UUID]
    refresh_pubmed_if_needed: bool


def require_chat_documents(
    *,
    space_id: UUID,
    document_ids: list[UUID],
    document_store: HarnessDocumentStore,
) -> tuple[HarnessDocumentRecord, ...]:
    """Load all referenced documents or raise a typed missing-document error."""
    documents: list[HarnessDocumentRecord] = []
    for document_id in document_ids:
        document = document_store.get_document(
            space_id=space_id,
            document_id=document_id,
        )
        if document is None:
            raise ChatDocumentNotFoundError(document_id=document_id, space_id=space_id)
        documents.append(document)
    return tuple(documents)


def prepare_chat_message_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    session: HarnessChatSessionRecord,
    request: ChatMessageRunRequest,
    current_user: HarnessUser,
    chat_session_store: HarnessChatSessionStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphTransportBundle,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    document_store: HarnessDocumentStore,
    input_metadata: JSONObject | None = None,
) -> PreparedChatMessageRun:
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
    referenced_documents = require_chat_documents(
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
        input_metadata=input_metadata,
    )
    return PreparedChatMessageRun(queued_run=queued_run)


__all__ = [
    "ChatDocumentNotFoundError",
    "ChatMessageRunRequest",
    "PreparedChatMessageRun",
    "prepare_chat_message_run",
    "require_chat_documents",
]
