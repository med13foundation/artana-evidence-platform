"""Chat-session creation endpoints that start with a user message."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Annotated, NoReturn
from uuid import UUID

from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.auth import HarnessUser, get_current_harness_user
from artana_evidence_api.chat_sessions import (
    HarnessChatSessionRecord,
    HarnessChatSessionStartRecord,
    HarnessChatSessionStore,
)
from artana_evidence_api.chat_workflow import (
    DEFAULT_CHAT_SESSION_TITLE,
    derive_session_title,
)
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_chat_session_store,
    get_document_store,
    get_graph_api_gateway,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_research_state_store,
    get_run_registry,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_client import (
    GraphServiceClientError,
    GraphTransportBundle,
)
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import HarnessExecutionServices
from artana_evidence_api.queued_run import (
    require_worker_ready,
    should_require_worker_ready,
    wake_worker_for_queued_run,
)
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.routers.chat_message_queue import (
    ChatDocumentNotFoundError,
    prepare_chat_message_run,
    require_chat_documents,
)
from artana_evidence_api.routers.chat_message_responses import (
    accepted_chat_session_response,
    build_chat_message_accepted_response,
    chat_message_stream_url,
)
from artana_evidence_api.routers.chat_models import (
    ChatMessageAcceptedResponse,
    ChatMessageCreateRequest,
)
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.transparency import ensure_run_transparency_seed
from artana_evidence_api.types.common import JSONObject
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

router = APIRouter(
    prefix="/v1/spaces",
    tags=["chat"],
    dependencies=[Depends(require_harness_space_read_access)],
)

_FIRST_MESSAGE_IDEMPOTENCY_KEY = "first_message_idempotency_key"
_FIRST_MESSAGE_REQUEST_SIGNATURE = "first_message_request_signature"
_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_CHAT_SESSION_STORE_DEPENDENCY = Depends(get_chat_session_store)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_GRAPH_SNAPSHOT_STORE_DEPENDENCY = Depends(get_graph_snapshot_store)
_DOCUMENT_STORE_DEPENDENCY = Depends(get_document_store)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_FIRST_MESSAGE_START_METADATA_KEY = "first_message_start"


@dataclass(frozen=True, slots=True)
class _FirstMessageStartServices:
    """Dependencies needed after FastAPI has resolved the request."""

    chat_session_store: HarnessChatSessionStore
    run_registry: HarnessRunRegistry
    artifact_store: HarnessArtifactStore
    graph_api_gateway: GraphTransportBundle
    research_state_store: HarnessResearchStateStore
    graph_snapshot_store: HarnessGraphSnapshotStore
    document_store: HarnessDocumentStore
    execution_services: HarnessExecutionServices


def _request_signature(request: ChatMessageCreateRequest) -> JSONObject:
    return request.model_dump(mode="json")


def _session_id_from_run(run: HarnessRunRecord) -> UUID:
    session_id = run.input_payload.get("session_id")
    try:
        return UUID(str(session_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored first-message chat run is missing its session id.",
        ) from exc


def _accepted_response_for_run(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    chat_session_store: HarnessChatSessionStore,
    session_id: UUID | None = None,
) -> ChatMessageAcceptedResponse:
    resolved_session_id = session_id or _session_id_from_run(run)
    session = chat_session_store.get_session(
        space_id=space_id,
        session_id=resolved_session_id,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored first-message chat session was not found.",
        )
    return build_chat_message_accepted_response(
        run=HarnessRunResponse.from_record(run),
        session=accepted_chat_session_response(
            space_id=space_id,
            session_id=resolved_session_id,
            fallback_session=session,
            chat_session_store=chat_session_store,
        ),
        stream_url=chat_message_stream_url(
            space_id=space_id,
            session_id=resolved_session_id,
            run_id=run.id,
        ),
    )


def _ensure_idempotent_replay_matches(
    *,
    stored_signature: JSONObject,
    request_signature: JSONObject,
) -> None:
    if stored_signature != request_signature:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was already used for a different first message.",
        )


def _require_completed_first_message_start(
    *,
    session_id: str | None,
    run_id: str | None,
) -> tuple[UUID, str]:
    if session_id is None or run_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="First-message chat session creation is already in progress.",
    )
    return UUID(session_id), run_id


def _apply_async_preference(response: Response) -> None:
    response.headers["Preference-Applied"] = "respond-async"


def _raise_first_message_start_error(
    exc: ChatDocumentNotFoundError | GraphServiceClientError | RuntimeError,
) -> NoReturn:
    if isinstance(exc, ChatDocumentNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    if isinstance(exc, GraphServiceClientError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=str(exc),
    ) from exc


def _require_request_documents(
    *,
    space_id: UUID,
    request: ChatMessageCreateRequest,
    services: _FirstMessageStartServices,
) -> None:
    require_chat_documents(
        space_id=space_id,
        document_ids=request.document_ids,
        document_store=services.document_store,
    )


def _delete_first_message_start(
    *,
    space_id: UUID,
    current_user: HarnessUser,
    idempotency_key: str,
    services: _FirstMessageStartServices,
) -> None:
    services.chat_session_store.delete_first_message_start(
        space_id=space_id,
        created_by=current_user.id,
        idempotency_key=idempotency_key,
    )


def _cleanup_unqueued_first_message_start(
    *,
    space_id: UUID,
    current_user: HarnessUser,
    idempotency_key: str,
    services: _FirstMessageStartServices,
    session: HarnessChatSessionRecord | None,
) -> None:
    _delete_first_message_start(
        space_id=space_id,
        current_user=current_user,
        idempotency_key=idempotency_key,
        services=services,
    )
    if session is not None:
        services.chat_session_store.discard_empty_session(
            space_id=space_id,
            session_id=session.id,
        )


def _replay_first_message_start(
    *,
    space_id: UUID,
    reservation: HarnessChatSessionStartRecord,
    request_signature: JSONObject,
    response: Response,
    services: _FirstMessageStartServices,
) -> ChatMessageAcceptedResponse:
    _ensure_idempotent_replay_matches(
        stored_signature=reservation.request_signature,
        request_signature=request_signature,
    )
    reserved_session_id, reserved_run_id = _require_completed_first_message_start(
        session_id=reservation.session_id,
        run_id=reservation.run_id,
    )
    existing_run = services.run_registry.get_run(
        space_id=space_id,
        run_id=reserved_run_id,
    )
    if existing_run is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored first-message chat run was not found.",
        )
    ensure_run_transparency_seed(
        run=existing_run,
        artifact_store=services.artifact_store,
        runtime=services.execution_services.runtime,
    )
    if existing_run.status == "queued":
        wake_worker_for_queued_run(
            run=existing_run,
            execution_services=services.execution_services,
        )
    _apply_async_preference(response)
    return _accepted_response_for_run(
        space_id=space_id,
        run=existing_run,
        chat_session_store=services.chat_session_store,
        session_id=reserved_session_id,
    )


async def _queue_new_first_message_start(  # noqa: PLR0913
    *,
    space_id: UUID,
    request: ChatMessageCreateRequest,
    current_user: HarnessUser,
    idempotency_key: str,
    request_signature: JSONObject,
    services: _FirstMessageStartServices,
) -> HarnessRunRecord:
    queued_run: HarnessRunRecord | None = None
    session: HarnessChatSessionRecord | None = None
    try:
        if should_require_worker_ready(execution_services=services.execution_services):
            require_worker_ready(operation_name="Graph chat")
        session_title = derive_session_title(request.content) or DEFAULT_CHAT_SESSION_TITLE
        session = services.chat_session_store.create_session(
            space_id=space_id,
            title=session_title,
            created_by=current_user.id,
        )
        prepared_run = await asyncio.to_thread(
            prepare_chat_message_run,
            space_id=space_id,
            session=session,
            request=request,
            current_user=current_user,
            chat_session_store=services.chat_session_store,
            run_registry=services.run_registry,
            artifact_store=services.artifact_store,
            graph_api_gateway=services.graph_api_gateway,
            research_state_store=services.research_state_store,
            graph_snapshot_store=services.graph_snapshot_store,
            document_store=services.document_store,
            input_metadata={
                _FIRST_MESSAGE_START_METADATA_KEY: {
                    _FIRST_MESSAGE_IDEMPOTENCY_KEY: idempotency_key,
                    _FIRST_MESSAGE_REQUEST_SIGNATURE: request_signature,
                },
            },
        )
        queued_run = prepared_run.queued_run
        completed = services.chat_session_store.complete_first_message_start(
            space_id=space_id,
            created_by=current_user.id,
            idempotency_key=idempotency_key,
            session_id=session.id,
            run_id=queued_run.id,
        )
        if completed is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store first-message chat idempotency record.",
            )
        ensure_run_transparency_seed(
            run=queued_run,
            artifact_store=services.artifact_store,
            runtime=services.execution_services.runtime,
        )
        wake_worker_for_queued_run(
            run=queued_run,
            execution_services=services.execution_services,
        )
    except HTTPException:
        if queued_run is None:
            _cleanup_unqueued_first_message_start(
                space_id=space_id,
                current_user=current_user,
                idempotency_key=idempotency_key,
                services=services,
                session=session,
            )
        raise
    except (ChatDocumentNotFoundError, GraphServiceClientError, RuntimeError):
        if queued_run is None:
            _cleanup_unqueued_first_message_start(
                space_id=space_id,
                current_user=current_user,
                idempotency_key=idempotency_key,
                services=services,
                session=session,
            )
        raise

    return queued_run


@router.post(
    "/{space_id}/chat-sessions/first-message",
    response_model=ChatMessageAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create chat session with first message",
    dependencies=[Depends(require_harness_space_write_access)],
)
async def create_chat_session_with_first_message(  # noqa: PLR0913
    space_id: UUID,
    message_request: ChatMessageCreateRequest,
    response: Response,
    *,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=256),
    ],
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
    graph_snapshot_store: HarnessGraphSnapshotStore = _GRAPH_SNAPSHOT_STORE_DEPENDENCY,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> ChatMessageAcceptedResponse:
    services = _FirstMessageStartServices(
        chat_session_store=chat_session_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        research_state_store=research_state_store,
        graph_snapshot_store=graph_snapshot_store,
        document_store=document_store,
        execution_services=execution_services,
    )
    request_signature = _request_signature(message_request)
    try:
        _require_request_documents(
            space_id=space_id,
            request=message_request,
            services=services,
        )
        reservation, is_new_reservation = chat_session_store.reserve_first_message_start(
            space_id=space_id,
            created_by=current_user.id,
            idempotency_key=idempotency_key,
            request_signature=request_signature,
        )
        if not is_new_reservation:
            return _replay_first_message_start(
                space_id=space_id,
                reservation=reservation,
                request_signature=request_signature,
                response=response,
                services=services,
            )
        queued_run = await _queue_new_first_message_start(
            space_id=space_id,
            request=message_request,
            current_user=current_user,
            idempotency_key=idempotency_key,
            request_signature=request_signature,
            services=services,
        )
    except (ChatDocumentNotFoundError, GraphServiceClientError, RuntimeError) as exc:
        _raise_first_message_start_error(exc)
    finally:
        graph_api_gateway.close()

    _apply_async_preference(response)
    return _accepted_response_for_run(
        space_id=space_id,
        run=queued_run,
        chat_session_store=services.chat_session_store,
    )


__all__ = ["create_chat_session_with_first_message", "router"]
