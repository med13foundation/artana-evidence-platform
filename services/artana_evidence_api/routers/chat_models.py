"""Pydantic contracts for chat session routes."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from artana_evidence_api.chat_graph_write_workflow import (
    ChatGraphWriteCandidateRequest,
)
from artana_evidence_api.chat_sessions import (
    HarnessChatMessageRecord,
    HarnessChatSessionRecord,
)
from artana_evidence_api.graph_chat_runtime import GraphChatResult
from artana_evidence_api.proposal_store import HarnessProposalRecord
from artana_evidence_api.routers.proposals import HarnessProposalResponse
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field


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


__all__ = [
    "ChatGraphWriteCandidateDecisionRequest",
    "ChatGraphWriteCandidateDecisionResponse",
    "ChatGraphWriteProposalRecordResponse",
    "ChatGraphWriteProposalRequest",
    "ChatGraphWriteProposalResponse",
    "ChatMessageAcceptedResponse",
    "ChatMessageCreateRequest",
    "ChatMessageResponse",
    "ChatMessageRunResponse",
    "ChatSessionCreateRequest",
    "ChatSessionDetailResponse",
    "ChatSessionListResponse",
    "ChatSessionResponse",
]
