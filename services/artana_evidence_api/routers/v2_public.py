"""User-facing v2 route names for the evidence workflow API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.auth import (
    HarnessUser,
    get_current_harness_user,
    require_harness_read_access,
)
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_chat_session_store,
    get_direct_source_search_store,
    get_document_binary_store,
    get_document_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_identity_gateway,
    get_proposal_store,
    get_research_state_store,
    get_review_item_store,
    get_run_registry,
    get_source_search_handoff_store,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.direct_source_search import (
    DirectSourceSearchStore,
)
from artana_evidence_api.document_binary_store import HarnessDocumentBinaryStore
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_client import GraphTransportBundle
from artana_evidence_api.harness_runtime import HarnessExecutionServices
from artana_evidence_api.identity.contracts import IdentityGateway
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.queued_run import HarnessAcceptedRunResponse
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.review_item_store import HarnessReviewItemStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_registry import (
    SourceDefinition,
    SourceListResponse,
    direct_search_source_keys,
    get_source_definition,
    list_source_definitions,
)
from artana_evidence_api.source_result_capture import (
    SourceSearchResponse,
)
from artana_evidence_api.source_route_contracts import (
    DirectSourceRouteDependencies,
)
from artana_evidence_api.source_route_dependencies import (
    direct_source_route_dependencies,
)
from artana_evidence_api.source_route_plugins import (
    create_direct_source_search_payload,
    get_direct_source_search_payload,
    register_direct_source_typed_routes,
)
from artana_evidence_api.source_search_handoff import (
    SourceSearchHandoffConflictError,
    SourceSearchHandoffNotFoundError,
    SourceSearchHandoffRequest,
    SourceSearchHandoffResponse,
    SourceSearchHandoffSelectionError,
    SourceSearchHandoffService,
    SourceSearchHandoffStore,
    SourceSearchHandoffUnsupportedError,
)
from artana_evidence_api.types.common import (
    JSONObject,
    json_object_or_empty,
)
from fastapi import (
    APIRouter,
    Body,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse, StreamingResponse

from . import (
    chat,
    documents,
    evidence_selection_runs,
    graph_curation_runs,
    harnesses,
    research_bootstrap_runs,
    research_init,
    runs,
    supervisor_runs,
)
from .approvals import (
    HarnessApprovalDecisionRequest,
    HarnessApprovalListResponse,
    HarnessApprovalResponse,
    HarnessRunIntentRequest,
    HarnessRunIntentResponse,
)
from .approvals import decide_approval as _decide_approval
from .approvals import list_approvals as _list_approvals
from .approvals import record_intent as _record_intent
from .artifacts import get_artifact as _get_artifact
from .artifacts import get_workspace as _get_workspace
from .artifacts import list_artifacts as _list_artifacts
from .chat import stream_chat_message as _stream_chat_message
from .harnesses import get_harness as _get_harness
from .runs import (
    HarnessRunEventListResponse,
    HarnessRunResumeRequest,
)
from .runs import get_run as _get_run
from .runs import get_run_capabilities as _get_run_capabilities
from .runs import get_run_policy_decisions as _get_run_policy_decisions
from .runs import get_run_progress as _get_run_progress
from .runs import list_run_events as _list_run_events
from .runs import resume_run as _resume_run
from .supervisor_runs import get_supervisor_run as _get_supervisor_run
from .supervisor_runs import (
    review_supervisor_chat_graph_write_candidate as _review_supervisor_update,
)
from .v2_public_aliases import _ALIASES, _find_route, register_v2_public_aliases
from .v2_public_payloads import (
    AcceptedTaskResponse,
    ResearchPlanResponse,
    TaskCapabilitiesResponse,
    TaskCreateRequest,
    TaskDecisionsResponse,
    TaskListResponse,
    TaskOutputListResponse,
    TaskOutputResponse,
    TaskProgressResponse,
    TaskResponse,
    TaskResumeResponse,
    TaskWorkingStateResponse,
    WorkflowTemplateListResponse,
    WorkflowTemplateResponse,
    _publicize_json,
    _publicize_json_object,
    _publicized_json_response,
)

router = APIRouter()

_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_APPROVAL_STORE_DEPENDENCY = Depends(get_approval_store)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_CHAT_SESSION_STORE_DEPENDENCY = Depends(get_chat_session_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY = Depends(get_direct_source_search_store)
_SOURCE_SEARCH_HANDOFF_STORE_DEPENDENCY = Depends(get_source_search_handoff_store)
_DOCUMENT_STORE_DEPENDENCY = Depends(get_document_store)
_DOCUMENT_BINARY_STORE_DEPENDENCY = Depends(get_document_binary_store)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_REVIEW_ITEM_STORE_DEPENDENCY = Depends(get_review_item_store)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_OpenAPIResponses = dict[int | str, dict[str, Any]]
_SOURCE_NOT_FOUND_RESPONSE: _OpenAPIResponses = {
    status.HTTP_404_NOT_FOUND: {"description": "Source is not registered."},
}
_DIRECT_SOURCE_SEARCH_RESPONSES: _OpenAPIResponses = {
    status.HTTP_404_NOT_FOUND: {"description": "Source is not registered."},
    status.HTTP_501_NOT_IMPLEMENTED: {
        "description": "Source does not support direct search yet.",
    },
}


def _require_source(source_key: str) -> SourceDefinition:
    source = get_source_definition(source_key)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Source '{source_key}' is not registered.",
        )
    return source


def _require_direct_search_source(source_key: str) -> SourceDefinition:
    source = _require_source(source_key)
    if not source.direct_search_enabled:
        direct_sources = ", ".join(direct_search_source_keys())
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                f"Source '{source.source_key}' is available through research-plan "
                "or enrichment, but direct source search is not enabled yet. "
                f"Direct search sources: {direct_sources}."
            ),
        )
    return source


register_v2_public_aliases(router)


@router.get(
    "/v2/sources",
    response_model=SourceListResponse,
    summary="List evidence sources",
    dependencies=[Depends(require_harness_read_access)],
    tags=["sources"],
)
def list_sources() -> SourceListResponse:
    """Return public evidence source capabilities."""

    sources = list(list_source_definitions())
    return SourceListResponse(sources=sources, total=len(sources))


@router.get(
    "/v2/sources/{source_key}",
    response_model=SourceDefinition,
    summary="Get evidence source",
    dependencies=[Depends(require_harness_read_access)],
    tags=["sources"],
    responses=_SOURCE_NOT_FOUND_RESPONSE,
)
def get_source(source_key: str) -> SourceDefinition:
    """Return one public evidence source capability definition."""

    return _require_source(source_key)


register_direct_source_typed_routes(router)


@router.post(
    "/v2/spaces/{space_id}/sources/{source_key}/searches",
    response_model=SourceSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Search evidence source",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
    responses=_DIRECT_SOURCE_SEARCH_RESPONSES,
)
async def create_source_search(
    space_id: UUID,
    source_key: str,
    request_payload: JSONObject = Body(...),
    *,
    route_dependencies: DirectSourceRouteDependencies = Depends(
        direct_source_route_dependencies,
    ),
) -> JSONObject:
    """Run a direct source search through the source registry."""

    source = _require_direct_search_source(source_key)
    return await create_direct_source_search_payload(
        source_key=source.source_key,
        space_id=space_id,
        request_payload=request_payload,
        dependencies=route_dependencies,
    )


@router.get(
    "/v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}",
    response_model=SourceSearchResponse,
    summary="Get evidence source search",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["sources"],
    responses=_DIRECT_SOURCE_SEARCH_RESPONSES,
)
def get_source_search(
    space_id: UUID,
    source_key: str,
    search_id: UUID,
    *,
    route_dependencies: DirectSourceRouteDependencies = Depends(
        direct_source_route_dependencies,
    ),
) -> JSONObject:
    """Return one direct source search result through the source registry."""

    source = _require_direct_search_source(source_key)
    return get_direct_source_search_payload(
        source_key=source.source_key,
        space_id=space_id,
        search_id=search_id,
        dependencies=route_dependencies,
    )


@router.post(
    "/v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}/handoffs",
    response_model=SourceSearchHandoffResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Hand off a captured source search",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["sources"],
    responses={
        **_DIRECT_SOURCE_SEARCH_RESPONSES,
        status.HTTP_409_CONFLICT: {
            "description": "Idempotency key was reused with different input.",
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "The request did not select exactly one source record.",
        },
    },
)
async def create_source_search_handoff(
    space_id: UUID,
    source_key: str,
    search_id: UUID,
    request: SourceSearchHandoffRequest,
    *,
    current_user: HarnessUser = Depends(get_current_harness_user),
    direct_source_search_store: DirectSourceSearchStore = (
        _DIRECT_SOURCE_SEARCH_STORE_DEPENDENCY
    ),
    source_search_handoff_store: SourceSearchHandoffStore = (
        _SOURCE_SEARCH_HANDOFF_STORE_DEPENDENCY
    ),
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    binary_store: HarnessDocumentBinaryStore = _DOCUMENT_BINARY_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
) -> SourceSearchHandoffResponse:
    """Create an idempotent handoff from a saved source-search result."""

    source = _require_direct_search_source(source_key)
    service = SourceSearchHandoffService(
        search_store=direct_source_search_store,
        handoff_store=source_search_handoff_store,
        document_store=document_store,
        run_registry=run_registry,
    )
    try:
        response = service.create_handoff(
            space_id=space_id,
            source_key=source.source_key,
            search_id=search_id,
            created_by=current_user.id,
            request=request,
        )
    except SourceSearchHandoffNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SourceSearchHandoffUnsupportedError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc
    except SourceSearchHandoffConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except SourceSearchHandoffSelectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    target_document = (
        document_store.get_document(
            space_id=space_id,
            document_id=response.target_document_id,
        )
        if response.target_document_id is not None
        else None
    )
    if (
        request.extract_now
        and response.target_document_id is not None
        and target_document is not None
        and target_document.extraction_status != "completed"
    ):
        extraction = await documents.extract_document(
            space_id=space_id,
            document_id=response.target_document_id,
            use_llm=False,
            document_store=document_store,
            proposal_store=proposal_store,
            review_item_store=review_item_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            binary_store=binary_store,
            graph_api_gateway=graph_api_gateway,
            research_state_store=research_state_store,
        )
        response = response.model_copy(
            update={"extraction": json_object_or_empty(jsonable_encoder(extraction))},
        )
    return response


@router.post(
    "/v2/spaces/{space_id}/evidence-runs",
    response_model=evidence_selection_runs.EvidenceSelectionRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start evidence run",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["research"],
)
async def create_evidence_run(
    space_id: UUID,
    request: evidence_selection_runs.EvidenceSelectionRunRequest,
    *,
    prefer: str | None = Header(default=None, alias="Prefer"),
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    current_user: HarnessUser = Depends(get_current_harness_user),
) -> evidence_selection_runs.EvidenceSelectionRunResponse | JSONResponse:
    """Start the goal-driven evidence-selection front door."""

    return await evidence_selection_runs.create_evidence_selection_run(
        space_id=space_id,
        request=request,
        prefer=prefer,
        run_registry=run_registry,
        artifact_store=artifact_store,
        execution_services=execution_services,
        current_user=current_user,
    )


@router.post(
    "/v2/spaces/{space_id}/evidence-runs/{evidence_run_id}/follow-ups",
    response_model=evidence_selection_runs.EvidenceSelectionRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start evidence-run follow-up",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["research"],
)
async def create_evidence_run_follow_up(
    space_id: UUID,
    evidence_run_id: UUID,
    request: evidence_selection_runs.EvidenceSelectionFollowUpRequest,
    *,
    prefer: str | None = Header(default=None, alias="Prefer"),
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    current_user: HarnessUser = Depends(get_current_harness_user),
) -> evidence_selection_runs.EvidenceSelectionRunResponse | JSONResponse:
    """Continue an existing evidence run inside the same research space."""

    return await evidence_selection_runs.create_evidence_selection_follow_up_run(
        space_id=space_id,
        parent_run_id=evidence_run_id,
        request=request,
        prefer=prefer,
        run_registry=run_registry,
        artifact_store=artifact_store,
        execution_services=execution_services,
        current_user=current_user,
    )


@router.get(
    "/v2/workflow-templates",
    response_model=WorkflowTemplateListResponse,
    summary="List workflow templates",
    dependencies=[Depends(require_harness_read_access)],
    tags=["workflows"],
)
def list_workflow_templates() -> WorkflowTemplateListResponse:
    """Return the public workflow template catalog."""
    response = harnesses.list_harnesses()
    return WorkflowTemplateListResponse(
        workflow_templates=[
            WorkflowTemplateResponse.from_v1(template)
            for template in response.harnesses
        ],
        total=response.total,
    )


@router.post(
    "/v2/spaces/{space_id}/research-plan",
    response_model=ResearchPlanResponse,
    status_code=201,
    summary="Create research plan",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["research"],
)
async def create_research_plan(
    space_id: UUID,
    request: research_init.ResearchInitRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    current_user: HarnessUser = Depends(get_current_harness_user),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> ResearchPlanResponse:
    """Queue research planning work using public task language."""
    response = await research_init.create_research_init(
        space_id=space_id,
        request=request,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
        current_user=current_user,
        identity_gateway=identity_gateway,
    )
    return ResearchPlanResponse.from_v1(response)


@router.post(
    "/v2/spaces/{space_id}/tasks",
    response_model=TaskResponse,
    status_code=201,
    summary="Start task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["tasks"],
)
def create_task(
    space_id: UUID,
    request: TaskCreateRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> TaskResponse:
    """Create one public task from a workflow template."""
    response = runs.create_run(
        space_id=space_id,
        request=request.to_v1(),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
    )
    return TaskResponse.from_v1(response)


@router.post(
    "/v2/spaces/{space_id}/workflows/topic-setup/tasks",
    response_model=JSONObject,
    responses={202: {"model": AcceptedTaskResponse}},
    summary="Start topic setup task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["workflows"],
)
async def create_topic_setup_task(
    space_id: UUID,
    request: research_bootstrap_runs.ResearchBootstrapRunRequest,
    *,
    prefer: str | None = Header(default=None),
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> JSONObject | JSONResponse:
    """Start one topic-setup task with public payload naming."""
    result = await research_bootstrap_runs.create_research_bootstrap_run(
        space_id=space_id,
        request=request,
        prefer=prefer,
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
    )
    if isinstance(result, JSONResponse):
        return _publicized_json_response(result)
    payload = _publicize_json_object(result.model_dump(mode="json"))
    return payload or {}


@router.post(
    "/v2/spaces/{space_id}/workflows/evidence-curation/tasks",
    response_model=JSONObject,
    responses={202: {"model": AcceptedTaskResponse}},
    summary="Start evidence curation task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["workflows"],
)
async def create_evidence_curation_task(
    space_id: UUID,
    request: graph_curation_runs.ClaimCurationRunRequest,
    *,
    prefer: str | None = Header(default=None),
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = Depends(get_proposal_store),
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> JSONObject | JSONResponse:
    """Start one evidence-curation task with public payload naming."""
    result = await graph_curation_runs.create_claim_curation_run(
        space_id=space_id,
        request=request,
        prefer=prefer,
        run_registry=run_registry,
        artifact_store=artifact_store,
        proposal_store=proposal_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
    )
    if isinstance(result, JSONResponse):
        return _publicized_json_response(result)
    payload = _publicize_json_object(result.model_dump(mode="json"))
    return payload or {}


@router.post(
    "/v2/spaces/{space_id}/workflows/full-research/tasks",
    response_model=JSONObject,
    responses={202: {"model": AcceptedTaskResponse}},
    summary="Start full research task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["workflows"],
)
async def create_full_research_task(
    space_id: UUID,
    request: supervisor_runs.SupervisorRunRequest,
    *,
    prefer: str | None = Header(default=None),
    current_user: HarnessUser = Depends(get_current_harness_user),
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    parent_graph_api_gateway: GraphTransportBundle = Depends(
        get_graph_api_gateway, use_cache=False
    ),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> JSONObject | JSONResponse:
    """Start one full-research task with public payload naming."""
    result = await supervisor_runs.create_supervisor_run(
        space_id=space_id,
        request=request,
        prefer=prefer,
        current_user=current_user,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_graph_api_gateway=parent_graph_api_gateway,
        execution_services=execution_services,
    )
    if isinstance(result, JSONResponse):
        return _publicized_json_response(result)
    payload = _publicize_json_object(result.model_dump(mode="json"))
    return payload or {}


@router.get(
    "/v2/spaces/{space_id}/tasks",
    response_model=TaskListResponse,
    summary="List tasks",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def list_tasks(
    space_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> TaskListResponse:
    """Return tracked tasks for one research space."""
    response = runs.list_runs(
        space_id=space_id,
        offset=offset,
        limit=limit,
        run_registry=run_registry,
    )
    return TaskListResponse.from_v1(response)


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Get task",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> TaskResponse:
    """Return one tracked task."""
    return TaskResponse.from_v1(
        _get_run(space_id=space_id, run_id=task_id, run_registry=run_registry),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/progress",
    response_model=TaskProgressResponse,
    summary="Get task progress",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_progress(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> TaskProgressResponse:
    """Return the latest progress snapshot for one tracked task."""
    return TaskProgressResponse.from_v1(
        _get_run_progress(
            space_id=space_id,
            run_id=task_id,
            run_registry=run_registry,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/events",
    response_model=HarnessRunEventListResponse,
    summary="List task events",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def list_task_events(
    space_id: UUID,
    task_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> HarnessRunEventListResponse:
    """Return lifecycle events for one tracked task."""
    return _list_run_events(
        space_id=space_id,
        run_id=task_id,
        offset=offset,
        limit=limit,
        run_registry=run_registry,
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/capabilities",
    response_model=TaskCapabilitiesResponse,
    summary="Get task capabilities",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_capabilities(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> TaskCapabilitiesResponse:
    """Return the frozen tool and policy snapshot for one tracked task."""
    return TaskCapabilitiesResponse.from_v1(
        _get_run_capabilities(
            space_id=space_id,
            run_id=task_id,
            run_registry=run_registry,
            artifact_store=artifact_store,
            execution_services=execution_services,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/decisions",
    response_model=TaskDecisionsResponse,
    summary="Get task decisions",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_decisions(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> TaskDecisionsResponse:
    """Return declared and observed decisions for one tracked task."""
    return TaskDecisionsResponse.from_v1(
        _get_run_policy_decisions(
            space_id=space_id,
            run_id=task_id,
            run_registry=run_registry,
            artifact_store=artifact_store,
            execution_services=execution_services,
        ),
    )


@router.post(
    "/v2/spaces/{space_id}/tasks/{task_id}/resume",
    response_model=TaskResumeResponse,
    summary="Resume paused task",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["tasks"],
)
async def resume_task(
    space_id: UUID,
    task_id: UUID,
    request: HarnessRunResumeRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> TaskResumeResponse:
    """Resume one paused tracked task."""
    return TaskResumeResponse.from_v1(
        await _resume_run(
            space_id=space_id,
            run_id=task_id,
            request=request,
            run_registry=run_registry,
            artifact_store=artifact_store,
            execution_services=execution_services,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/outputs",
    response_model=TaskOutputListResponse,
    summary="List task outputs",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def list_task_outputs(
    space_id: UUID,
    task_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> TaskOutputListResponse:
    """Return outputs stored for one tracked task."""
    return TaskOutputListResponse.from_v1(
        _list_artifacts(
            space_id=space_id,
            run_id=task_id,
            offset=offset,
            limit=limit,
            run_registry=run_registry,
            artifact_store=artifact_store,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/outputs/{output_key}",
    response_model=TaskOutputResponse,
    summary="Get task output",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_output(
    space_id: UUID,
    task_id: UUID,
    output_key: str,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> TaskOutputResponse:
    """Return one output stored for one tracked task."""
    return TaskOutputResponse.from_v1(
        _get_artifact(
            space_id=space_id,
            run_id=task_id,
            artifact_key=output_key,
            run_registry=run_registry,
            artifact_store=artifact_store,
        ),
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/working-state",
    response_model=TaskWorkingStateResponse,
    summary="Get task working state",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_working_state(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> TaskWorkingStateResponse:
    """Return the working-state snapshot stored for one tracked task."""
    return TaskWorkingStateResponse.from_v1(
        _get_workspace(
            space_id=space_id,
            run_id=task_id,
            run_registry=run_registry,
            artifact_store=artifact_store,
        ),
    )


@router.post(
    "/v2/spaces/{space_id}/tasks/{task_id}/planned-actions",
    response_model=HarnessRunIntentResponse,
    summary="Record planned task actions",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["tasks"],
)
def record_task_plan(
    space_id: UUID,
    task_id: UUID,
    request: HarnessRunIntentRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessRunIntentResponse:
    """Record actions a task wants to take before user approval."""
    return _record_intent(
        space_id=space_id,
        run_id=task_id,
        request=request,
        run_registry=run_registry,
        approval_store=approval_store,
        artifact_store=artifact_store,
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/approvals",
    response_model=HarnessApprovalListResponse,
    summary="List task approvals",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def list_task_approvals(
    space_id: UUID,
    task_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
) -> HarnessApprovalListResponse:
    """Return approvals for one tracked task."""
    return _list_approvals(
        space_id=space_id,
        run_id=task_id,
        offset=offset,
        limit=limit,
        run_registry=run_registry,
        approval_store=approval_store,
    )


@router.post(
    "/v2/spaces/{space_id}/tasks/{task_id}/approvals/{approval_key}/decision",
    response_model=HarnessApprovalResponse,
    summary="Decide task approval",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["tasks"],
)
def decide_task_approval(
    space_id: UUID,
    task_id: UUID,
    approval_key: str,
    request: HarnessApprovalDecisionRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessApprovalResponse:
    """Approve or reject one gated task action."""
    return _decide_approval(
        space_id=space_id,
        run_id=task_id,
        approval_key=approval_key,
        request=request,
        run_registry=run_registry,
        approval_store=approval_store,
        artifact_store=artifact_store,
    )


@router.get(
    "/v2/workflow-templates/{template_id}",
    response_model=WorkflowTemplateResponse,
    summary="Get workflow template",
    dependencies=[Depends(require_harness_read_access)],
    tags=["workflows"],
)
def get_workflow_template(template_id: str) -> WorkflowTemplateResponse:
    """Return one workflow template by its public template id."""
    return WorkflowTemplateResponse.from_v1(_get_harness(harness_id=template_id))


@router.get(
    "/v2/spaces/{space_id}/chat-sessions/{session_id}/messages/{task_id}/stream",
    summary="Stream chat task events",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["chat"],
)
async def stream_chat_task_message(
    space_id: UUID,
    session_id: UUID,
    task_id: str,
    request: Request,
    *,
    chat_session_store: HarnessChatSessionStore = _CHAT_SESSION_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> StreamingResponse:
    """Stream events for one chat task."""
    return await _stream_chat_message(
        space_id=space_id,
        session_id=session_id,
        run_id=task_id,
        request=request,
        chat_session_store=chat_session_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )


@router.get(
    "/v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}",
    response_model=JSONObject,
    summary="Get full research task",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["workflows"],
)
def get_full_research_task(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> JSONObject:
    """Return one full-research task detail response."""
    payload = _get_supervisor_run(
        space_id=space_id,
        run_id=task_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    return _publicize_json_object(payload.model_dump(mode="json")) or {}


@router.post(
    "/v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}/suggested-updates/{candidate_index}/decision",
    response_model=JSONObject,
    summary="Decide full research suggested update",
    dependencies=[Depends(require_harness_space_write_access)],
    tags=["workflows"],
)
def decide_full_research_suggested_update(
    space_id: UUID,
    task_id: UUID,
    candidate_index: int,
    request: chat.ChatGraphWriteCandidateDecisionRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = Depends(get_proposal_store),
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> JSONObject:
    """Promote or reject one suggested update from a full-research task."""
    payload = _review_supervisor_update(
        space_id=space_id,
        run_id=task_id,
        candidate_index=candidate_index,
        request=request,
        run_registry=run_registry,
        artifact_store=artifact_store,
        proposal_store=proposal_store,
        graph_api_gateway=graph_api_gateway,
        execution_services=execution_services,
    )
    return _publicize_json_object(payload.model_dump(mode="json")) or {}


__all__ = ["_ALIASES", "_find_route", "_publicize_json", "router"]
