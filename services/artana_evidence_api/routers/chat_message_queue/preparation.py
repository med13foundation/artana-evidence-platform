"""Preflight helpers for graph-chat message runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from artana_evidence_api.chat_workflow import (
    load_chat_memory_context,
    memory_context_artifact,
    queue_graph_chat_message_run,
)
from artana_evidence_api.database import SessionLocal, set_session_rls_context
from artana_evidence_api.sqlalchemy_stores import (
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessDocumentStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessResearchStateStore,
)
from artana_evidence_api.types.common import json_array_or_empty
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.auth import HarnessUser
    from artana_evidence_api.chat_sessions import (
        HarnessChatSessionRecord,
        HarnessChatSessionStore,
    )
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.routers.chat_models import ChatMessageCreateRequest
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
    from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class PreparedChatMessageRun:
    """Prepared chat run state built off the event loop."""

    queued_run: HarnessRunRecord


def require_documents(
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


def prepare_chat_message_run(  # noqa: PLR0913
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
    referenced_documents = require_documents(
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
    return PreparedChatMessageRun(queued_run=queued_run)


def uses_thread_bound_session(*stores: object) -> bool:
    return any(getattr(store, "_session", None) is not None for store in stores)


def _bound_session(store: object) -> Session | None:
    session = getattr(store, "_session", None)
    if session is None:
        return None
    return session if hasattr(session, "get_bind") else None


def uses_sqlite_session_bound_store(*stores: object) -> bool:
    """Return true when stores are bound to an injected SQLite test session."""
    for store in stores:
        session = _bound_session(store)
        if session is None:
            continue
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            return True
    return False


def prepare_chat_message_run_threadsafe(  # noqa: PLR0913
    *,
    space_id: UUID,
    session_id: UUID,
    session: HarnessChatSessionRecord,
    request: ChatMessageCreateRequest,
    current_user: HarnessUser,
    runtime: GraphHarnessKernelRuntime,
    graph_api_gateway: GraphTransportBundle,
    chat_session_store: HarnessChatSessionStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    document_store: HarnessDocumentStore,
) -> PreparedChatMessageRun:
    """Build a queued chat run without sharing SQLAlchemy sessions across threads."""
    if not uses_thread_bound_session(
        chat_session_store,
        run_registry,
        research_state_store,
        graph_snapshot_store,
        document_store,
    ):
        return prepare_chat_message_run(
            space_id=space_id,
            session=session,
            request=request,
            current_user=current_user,
            chat_session_store=chat_session_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            graph_api_gateway=graph_api_gateway,
            research_state_store=research_state_store,
            graph_snapshot_store=graph_snapshot_store,
            document_store=document_store,
        )

    with SessionLocal() as thread_session:
        set_session_rls_context(thread_session, bypass_rls=False)
        thread_run_registry = ArtanaBackedHarnessRunRegistry(
            session=thread_session,
            runtime=runtime,
        )
        thread_chat_session_store = SqlAlchemyHarnessChatSessionStore(thread_session)
        thread_session_record = thread_chat_session_store.get_session(
            space_id=space_id,
            session_id=session_id,
        )
        if thread_session_record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chat session '{session_id}' not found in space '{space_id}'",
            )
        return prepare_chat_message_run(
            space_id=space_id,
            session=thread_session_record,
            request=request,
            current_user=current_user,
            chat_session_store=thread_chat_session_store,
            run_registry=thread_run_registry,
            artifact_store=ArtanaBackedHarnessArtifactStore(runtime=runtime),
            graph_api_gateway=graph_api_gateway,
            research_state_store=SqlAlchemyHarnessResearchStateStore(
                thread_session,
            ),
            graph_snapshot_store=SqlAlchemyHarnessGraphSnapshotStore(
                thread_session,
            ),
            document_store=SqlAlchemyHarnessDocumentStore(thread_session),
        )
