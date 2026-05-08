"""Shared response builders for graph-chat routes."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.chat_sessions import (
    HarnessChatSessionRecord,
    HarnessChatSessionStore,
)
from artana_evidence_api.routers.chat_models import (
    ChatMessageAcceptedResponse,
    ChatSessionResponse,
)
from artana_evidence_api.routers.runs import HarnessRunResponse


def chat_message_stream_url(*, space_id: UUID, session_id: UUID, run_id: str) -> str:
    """Build the public stream URL for one chat run."""
    return f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages/{run_id}/stream"


def build_chat_message_accepted_response(
    *,
    run: HarnessRunResponse,
    session: ChatSessionResponse,
    stream_url: str,
) -> ChatMessageAcceptedResponse:
    """Serialize an accepted async graph-chat run."""
    return ChatMessageAcceptedResponse(
        run=run,
        session=session,
        progress_url=f"/v1/spaces/{run.space_id}/runs/{run.id}/progress",
        events_url=f"/v1/spaces/{run.space_id}/runs/{run.id}/events",
        workspace_url=f"/v1/spaces/{run.space_id}/runs/{run.id}/workspace",
        artifacts_url=f"/v1/spaces/{run.space_id}/runs/{run.id}/artifacts",
        stream_url=stream_url,
    )


def accepted_chat_session_response(
    *,
    space_id: UUID,
    session_id: UUID,
    fallback_session: HarnessChatSessionRecord,
    chat_session_store: HarnessChatSessionStore,
) -> ChatSessionResponse:
    """Return the refreshed session state after queueing when available."""
    refreshed_session = chat_session_store.get_session(
        space_id=space_id,
        session_id=session_id,
    )
    return ChatSessionResponse.from_record(refreshed_session or fallback_session)


__all__ = [
    "accepted_chat_session_response",
    "build_chat_message_accepted_response",
    "chat_message_stream_url",
]
