"""Lifecycle endpoints for harness chat sessions."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.dependencies import (
    get_chat_session_store,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.routers.chat_models import ChatSessionDiscardResponse
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(
    prefix="/v1/spaces",
    tags=["chat"],
    dependencies=[Depends(require_harness_space_read_access)],
)


@router.delete(
    "/{space_id}/chat-sessions/{session_id}",
    response_model=ChatSessionDiscardResponse,
    summary="Discard empty chat session",
    dependencies=[Depends(require_harness_space_write_access)],
)
def discard_empty_chat_session(
    space_id: UUID,
    session_id: UUID,
    *,
    chat_session_store: HarnessChatSessionStore = Depends(get_chat_session_store),
) -> ChatSessionDiscardResponse:
    result = chat_session_store.discard_empty_session(
        space_id=space_id,
        session_id=session_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )
    if result is False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only empty chat sessions can be discarded.",
        )
    return ChatSessionDiscardResponse(id=str(session_id), status="discarded")


__all__ = ["discard_empty_chat_session", "router"]
