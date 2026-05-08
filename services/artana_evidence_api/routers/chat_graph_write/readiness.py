"""Read-only readiness endpoint for chat graph-write staging."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from uuid import UUID  # noqa: TC003

from artana_evidence_api.artifact_store import HarnessArtifactStore  # noqa: TC001
from artana_evidence_api.chat_graph_write_workflow import (
    ChatGraphWriteArtifactError,
    ChatGraphWriteCandidateRequest,
    ChatGraphWriteVerificationError,
    load_graph_chat_artifacts,
    require_verified_graph_chat_result,
)
from artana_evidence_api.chat_sessions import HarnessChatSessionStore  # noqa: TC001
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_chat_session_store,
    get_proposal_store,
    get_run_registry,
    require_harness_space_read_access,
)
from artana_evidence_api.proposal_store import HarnessProposalRecord  # noqa: TC001
from artana_evidence_api.routers.chat import (
    _require_latest_chat_run,
    _require_session,
)
from artana_evidence_api.routers.chat_models import (
    ChatGraphWriteReadinessResponse,
    ChatSessionResponse,
)
from fastapi import APIRouter, Depends

if TYPE_CHECKING:
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.run_registry import HarnessRunRegistry

router = APIRouter(
    prefix="/v1/spaces",
    tags=["chat"],
    dependencies=[Depends(require_harness_space_read_access)],
)

_CHAT_GRAPH_WRITE_READY_MESSAGE = "Review-ready updates are available."
_CHAT_GRAPH_WRITE_EMPTY_MESSAGE = (
    "No review-ready updates found in the latest chat result."
)
_CHAT_GRAPH_WRITE_STAGED_MESSAGE = (
    "Suggested updates have already been staged for review."
)
_CHAT_GRAPH_WRITE_PENDING_MESSAGE = (
    "Latest chat run is still preparing review readiness."
)
_CHAT_GRAPH_WRITE_PENDING_STATUSES = frozenset({"queued", "running"})

_CHAT_SESSION_STORE_DEPENDENCY = Depends(get_chat_session_store)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)


def _read_chat_graph_write_candidates(
    *,
    space_id: UUID,
    run_id: str,
    artifact_store: HarnessArtifactStore,
) -> tuple[ChatGraphWriteCandidateRequest, ...]:
    graph_chat_result, _ = load_graph_chat_artifacts(
        space_id=space_id,
        run_id=run_id,
        artifact_store=artifact_store,
    )
    require_verified_graph_chat_result(graph_chat_result)
    return tuple(graph_chat_result.graph_write_candidates)


def _list_chat_graph_write_proposals(
    *,
    space_id: UUID,
    run_id: str,
    proposal_store: HarnessProposalStore,
) -> tuple[HarnessProposalRecord, ...]:
    proposals = proposal_store.list_proposals(space_id=space_id, run_id=run_id)
    return tuple(
        proposal
        for proposal in proposals
        if proposal.source_kind == "chat_graph_write"
    )


@router.get(
    "/{space_id}/chat-sessions/{session_id}/proposals/graph-write/readiness",
    response_model=ChatGraphWriteReadinessResponse,
    summary="Check whether latest chat findings can be staged",
)
def get_chat_graph_write_readiness(
    space_id: UUID,
    session_id: UUID,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
) -> ChatGraphWriteReadinessResponse:
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
    if run.status in _CHAT_GRAPH_WRITE_PENDING_STATUSES:
        return ChatGraphWriteReadinessResponse(
            run=run,
            session=ChatSessionResponse.from_record(session),
            state="pending",
            candidate_count=0,
            proposal_count=0,
            message=_CHAT_GRAPH_WRITE_PENDING_MESSAGE,
        )

    staged_proposals = _list_chat_graph_write_proposals(
        space_id=space_id,
        run_id=run.id,
        proposal_store=proposal_store,
    )
    try:
        candidates = _read_chat_graph_write_candidates(
            space_id=space_id,
            run_id=run.id,
            artifact_store=artifact_store,
        )
    except (ChatGraphWriteArtifactError, ChatGraphWriteVerificationError):
        candidates = ()

    state: Literal["ready", "empty", "staged", "pending"]
    if staged_proposals:
        state = "staged"
        message = _CHAT_GRAPH_WRITE_STAGED_MESSAGE
    elif candidates:
        state = "ready"
        message = _CHAT_GRAPH_WRITE_READY_MESSAGE
    else:
        state = "empty"
        message = _CHAT_GRAPH_WRITE_EMPTY_MESSAGE

    refreshed_session = chat_session_store.get_session(
        space_id=space_id,
        session_id=session_id,
    )
    return ChatGraphWriteReadinessResponse(
        run=run,
        session=ChatSessionResponse.from_record(refreshed_session or session),
        state=state,
        candidate_count=len(candidates),
        proposal_count=len(staged_proposals),
        message=message,
    )
