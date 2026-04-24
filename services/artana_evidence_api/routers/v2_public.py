"""User-facing v2 route names for the evidence workflow API."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_chat_session_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_proposal_store,
    get_run_registry,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import GraphTransportBundle
from artana_evidence_api.harness_runtime import HarnessExecutionServices
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from fastapi import APIRouter, Depends, Query, Request
from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse

from . import (
    authentication,
    chat,
    continuous_learning_runs,
    documents,
    full_ai_orchestrator_runs,
    graph_connection_runs,
    graph_curation_runs,
    graph_explorer,
    graph_search_runs,
    harnesses,
    hypothesis_runs,
    marrvel,
    mechanism_discovery_runs,
    proposals,
    pubmed,
    research_bootstrap_runs,
    research_init,
    research_onboarding_runs,
    research_state,
    review_queue,
    runs,
    schedules,
    spaces,
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
from .artifacts import (
    HarnessArtifactListResponse,
    HarnessArtifactResponse,
    HarnessWorkspaceResponse,
)
from .artifacts import get_artifact as _get_artifact
from .artifacts import get_workspace as _get_workspace
from .artifacts import list_artifacts as _list_artifacts
from .chat import stream_chat_message as _stream_chat_message
from .harnesses import HarnessTemplateResponse
from .harnesses import get_harness as _get_harness
from .runs import (
    HarnessRunEventListResponse,
    HarnessRunProgressResponse,
    HarnessRunResponse,
    HarnessRunResumeRequest,
    HarnessRunResumeResponse,
    RunCapabilitiesResponse,
    RunPolicyDecisionsResponse,
)
from .runs import get_run as _get_run
from .runs import get_run_capabilities as _get_run_capabilities
from .runs import get_run_policy_decisions as _get_run_policy_decisions
from .runs import get_run_progress as _get_run_progress
from .runs import list_run_events as _list_run_events
from .runs import resume_run as _resume_run
from .supervisor_runs import (
    SupervisorChatGraphWriteCandidateDecisionResponse,
    SupervisorRunDetailResponse,
)
from .supervisor_runs import get_supervisor_run as _get_supervisor_run
from .supervisor_runs import (
    review_supervisor_chat_graph_write_candidate as _review_supervisor_update,
)

router = APIRouter()

_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_APPROVAL_STORE_DEPENDENCY = Depends(get_approval_store)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_CHAT_SESSION_STORE_DEPENDENCY = Depends(get_chat_session_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)


def _find_route(source_router: APIRouter, *, path: str, method: str) -> APIRoute:
    for route in source_router.routes:
        if (
            isinstance(route, APIRoute)
            and route.path == path
            and method.upper() in route.methods
        ):
            return route
    msg = f"Missing source route for v2 alias: {method.upper()} {path}"
    raise RuntimeError(msg)


def _add_alias(
    *,
    source_router: APIRouter,
    source_path: str,
    target_path: str,
    method: str,
    summary: str,
    tags: Sequence[str],
) -> None:
    source = _find_route(source_router, path=source_path, method=method)
    router.add_api_route(
        target_path,
        source.endpoint,
        response_model=source.response_model,
        status_code=source.status_code,
        tags=list(tags),
        dependencies=source.dependencies,
        summary=summary,
        description=source.description,
        response_description=source.response_description,
        responses=source.responses,
        deprecated=source.deprecated,
        methods=[method.upper()],
        response_model_include=source.response_model_include,
        response_model_exclude=source.response_model_exclude,
        response_model_by_alias=source.response_model_by_alias,
        response_model_exclude_unset=source.response_model_exclude_unset,
        response_model_exclude_defaults=source.response_model_exclude_defaults,
        response_model_exclude_none=source.response_model_exclude_none,
        include_in_schema=source.include_in_schema,
        response_class=source.response_class,
        name=f"v2_{source.name}",
        callbacks=source.callbacks,
        openapi_extra=source.openapi_extra,
    )


_ALIASES = (
    # Account and space setup.
    (authentication.router, "POST", "/v1/auth/bootstrap", "/v2/auth/bootstrap", "Bootstrap self-hosted access", ("auth",)),
    (authentication.router, "POST", "/v1/auth/testers", "/v2/auth/testers", "Create tester access", ("auth",)),
    (authentication.router, "GET", "/v1/auth/me", "/v2/auth/me", "Get current identity", ("auth",)),
    (authentication.router, "POST", "/v1/auth/api-keys", "/v2/auth/api-keys", "Create API key", ("auth",)),
    (authentication.router, "GET", "/v1/auth/api-keys", "/v2/auth/api-keys", "List API keys", ("auth",)),
    (authentication.router, "DELETE", "/v1/auth/api-keys/{key_id}", "/v2/auth/api-keys/{key_id}", "Revoke API key", ("auth",)),
    (authentication.router, "POST", "/v1/auth/api-keys/{key_id}/rotate", "/v2/auth/api-keys/{key_id}/rotate", "Rotate API key", ("auth",)),
    (spaces.router, "GET", "/v1/spaces", "/v2/spaces", "List research spaces", ("spaces",)),
    (spaces.router, "POST", "/v1/spaces", "/v2/spaces", "Create research space", ("spaces",)),
    (spaces.router, "PATCH", "/v1/spaces/{space_id}/settings", "/v2/spaces/{space_id}/settings", "Update research-space settings", ("spaces",)),
    (spaces.router, "PUT", "/v1/spaces/default", "/v2/spaces/default", "Get or create default research space", ("spaces",)),
    (spaces.router, "DELETE", "/v1/spaces/{space_id}", "/v2/spaces/{space_id}", "Archive research space", ("spaces",)),
    (spaces.router, "GET", "/v1/spaces/{space_id}/members", "/v2/spaces/{space_id}/members", "List research-space members", ("spaces",)),
    (spaces.router, "POST", "/v1/spaces/{space_id}/members", "/v2/spaces/{space_id}/members", "Add research-space member", ("spaces",)),
    (spaces.router, "DELETE", "/v1/spaces/{space_id}/members/{user_id}", "/v2/spaces/{space_id}/members/{user_id}", "Remove research-space member", ("spaces",)),
    # Evidence input and source discovery.
    (documents.router, "GET", "/v1/spaces/{space_id}/documents", "/v2/spaces/{space_id}/documents", "List documents", ("documents",)),
    (documents.router, "GET", "/v1/spaces/{space_id}/documents/{document_id}", "/v2/spaces/{space_id}/documents/{document_id}", "Get document", ("documents",)),
    (documents.router, "POST", "/v1/spaces/{space_id}/documents/text", "/v2/spaces/{space_id}/documents/text", "Add text document", ("documents",)),
    (documents.router, "POST", "/v1/spaces/{space_id}/documents/pdf", "/v2/spaces/{space_id}/documents/pdf", "Upload PDF document", ("documents",)),
    (documents.router, "POST", "/v1/spaces/{space_id}/documents/{document_id}/extract", "/v2/spaces/{space_id}/documents/{document_id}/extraction", "Extract evidence from document", ("documents",)),
    (pubmed.router, "POST", "/v1/spaces/{space_id}/pubmed/searches", "/v2/spaces/{space_id}/sources/pubmed/searches", "Search PubMed", ("sources",)),
    (pubmed.router, "GET", "/v1/spaces/{space_id}/pubmed/searches/{job_id}", "/v2/spaces/{space_id}/sources/pubmed/searches/{job_id}", "Get PubMed search", ("sources",)),
    (marrvel.router, "POST", "/v1/spaces/{space_id}/marrvel/searches", "/v2/spaces/{space_id}/sources/marrvel/searches", "Search MARRVEL", ("sources",)),
    (marrvel.router, "GET", "/v1/spaces/{space_id}/marrvel/searches/{result_id}", "/v2/spaces/{space_id}/sources/marrvel/searches/{result_id}", "Get MARRVEL search", ("sources",)),
    (marrvel.router, "POST", "/v1/spaces/{space_id}/marrvel/ingest", "/v2/spaces/{space_id}/sources/marrvel/ingestion", "Ingest MARRVEL evidence", ("sources",)),
    # Product workflow surfaces.
    (research_init.router, "POST", "/v1/spaces/{space_id}/research-init", "/v2/spaces/{space_id}/research-plan", "Create research plan", ("research",)),
    (research_state.router, "GET", "/v1/spaces/{space_id}/research-state", "/v2/spaces/{space_id}/research-state", "Get research state", ("research",)),
    (review_queue.router, "GET", "/v1/spaces/{space_id}/review-queue", "/v2/spaces/{space_id}/review-items", "List items needing review", ("review",)),
    (review_queue.router, "GET", "/v1/spaces/{space_id}/review-queue/{item_id}", "/v2/spaces/{space_id}/review-items/{item_id}", "Get review item", ("review",)),
    (review_queue.router, "POST", "/v1/spaces/{space_id}/review-queue/{item_id}/actions", "/v2/spaces/{space_id}/review-items/{item_id}/decision", "Decide review item", ("review",)),
    (proposals.router, "GET", "/v1/spaces/{space_id}/proposals", "/v2/spaces/{space_id}/proposed-updates", "List proposed updates", ("review",)),
    (proposals.router, "GET", "/v1/spaces/{space_id}/proposals/{proposal_id}", "/v2/spaces/{space_id}/proposed-updates/{proposal_id}", "Get proposed update", ("review",)),
    (proposals.router, "POST", "/v1/spaces/{space_id}/proposals/{proposal_id}/promote", "/v2/spaces/{space_id}/proposed-updates/{proposal_id}/promote", "Promote proposed update", ("review",)),
    (proposals.router, "POST", "/v1/spaces/{space_id}/proposals/{proposal_id}/reject", "/v2/spaces/{space_id}/proposed-updates/{proposal_id}/reject", "Reject proposed update", ("review",)),
    # Generic task lifecycle.
    (runs.router, "POST", "/v1/spaces/{space_id}/runs", "/v2/spaces/{space_id}/tasks", "Start task", ("tasks",)),
    (runs.router, "GET", "/v1/spaces/{space_id}/runs", "/v2/spaces/{space_id}/tasks", "List tasks", ("tasks",)),
    (graph_explorer.router, "GET", "/v1/spaces/{space_id}/graph-explorer/claims", "/v2/spaces/{space_id}/evidence-map/claims", "List evidence-map claims", ("evidence-map",)),
    (graph_explorer.router, "GET", "/v1/spaces/{space_id}/graph-explorer/entities", "/v2/spaces/{space_id}/evidence-map/entities", "List evidence-map entities", ("evidence-map",)),
    (graph_explorer.router, "GET", "/v1/spaces/{space_id}/graph-explorer/entities/{entity_id}/claims", "/v2/spaces/{space_id}/evidence-map/entities/{entity_id}/claims", "List claims for entity", ("evidence-map",)),
    (graph_explorer.router, "GET", "/v1/spaces/{space_id}/graph-explorer/claims/{claim_id}/evidence", "/v2/spaces/{space_id}/evidence-map/claims/{claim_id}/evidence", "List claim evidence", ("evidence-map",)),
    (graph_explorer.router, "POST", "/v1/spaces/{space_id}/graph-explorer/document", "/v2/spaces/{space_id}/evidence-map/export", "Export evidence map", ("evidence-map",)),
    (chat.router, "GET", "/v1/spaces/{space_id}/chat-sessions", "/v2/spaces/{space_id}/chat-sessions", "List chat sessions", ("chat",)),
    (chat.router, "POST", "/v1/spaces/{space_id}/chat-sessions", "/v2/spaces/{space_id}/chat-sessions", "Create chat session", ("chat",)),
    (chat.router, "GET", "/v1/spaces/{space_id}/chat-sessions/{session_id}", "/v2/spaces/{space_id}/chat-sessions/{session_id}", "Get chat session", ("chat",)),
    (chat.router, "POST", "/v1/spaces/{space_id}/chat-sessions/{session_id}/messages", "/v2/spaces/{space_id}/chat-sessions/{session_id}/messages", "Send chat message", ("chat",)),
    (chat.router, "POST", "/v1/spaces/{space_id}/chat-sessions/{session_id}/proposals/graph-write", "/v2/spaces/{space_id}/chat-sessions/{session_id}/suggested-updates", "Stage suggested updates from chat", ("chat",)),
    (chat.router, "POST", "/v1/spaces/{space_id}/chat-sessions/{session_id}/graph-write-candidates/{candidate_index}/review", "/v2/spaces/{space_id}/chat-sessions/{session_id}/suggested-updates/{candidate_index}/decision", "Decide suggested chat update", ("chat",)),
    # Workflow-specific task creation.
    (research_bootstrap_runs.router, "POST", "/v1/spaces/{space_id}/agents/research-bootstrap/runs", "/v2/spaces/{space_id}/workflows/topic-setup/tasks", "Start topic setup task", ("workflows",)),
    (graph_search_runs.router, "POST", "/v1/spaces/{space_id}/agents/graph-search/runs", "/v2/spaces/{space_id}/workflows/evidence-search/tasks", "Start evidence search task", ("workflows",)),
    (graph_connection_runs.router, "POST", "/v1/spaces/{space_id}/agents/graph-connections/runs", "/v2/spaces/{space_id}/workflows/connection-discovery/tasks", "Start connection discovery task", ("workflows",)),
    (hypothesis_runs.router, "POST", "/v1/spaces/{space_id}/agents/hypotheses/runs", "/v2/spaces/{space_id}/workflows/hypothesis-discovery/tasks", "Start hypothesis discovery task", ("workflows",)),
    (mechanism_discovery_runs.router, "POST", "/v1/spaces/{space_id}/agents/mechanism-discovery/runs", "/v2/spaces/{space_id}/workflows/mechanism-discovery/tasks", "Start mechanism discovery task", ("workflows",)),
    (continuous_learning_runs.router, "POST", "/v1/spaces/{space_id}/agents/continuous-learning/runs", "/v2/spaces/{space_id}/workflows/continuous-review/tasks", "Start continuous review task", ("workflows",)),
    (graph_curation_runs.router, "POST", "/v1/spaces/{space_id}/agents/graph-curation/runs", "/v2/spaces/{space_id}/workflows/evidence-curation/tasks", "Start evidence curation task", ("workflows",)),
    (full_ai_orchestrator_runs.router, "POST", "/v1/spaces/{space_id}/agents/full-ai-orchestrator/runs", "/v2/spaces/{space_id}/workflows/autopilot/tasks", "Start autopilot task", ("workflows",)),
    (research_onboarding_runs.router, "POST", "/v1/spaces/{space_id}/agents/research-onboarding/runs", "/v2/spaces/{space_id}/workflows/research-onboarding/tasks", "Start research onboarding task", ("workflows",)),
    (research_onboarding_runs.router, "POST", "/v1/spaces/{space_id}/agents/research-onboarding/turns", "/v2/spaces/{space_id}/workflows/research-onboarding/turns", "Continue research onboarding", ("workflows",)),
    (supervisor_runs.router, "POST", "/v1/spaces/{space_id}/agents/supervisor/runs", "/v2/spaces/{space_id}/workflows/full-research/tasks", "Start full research task", ("workflows",)),
    (supervisor_runs.router, "GET", "/v1/spaces/{space_id}/agents/supervisor/dashboard", "/v2/spaces/{space_id}/workflows/full-research/dashboard", "Get full research dashboard", ("workflows",)),
    (supervisor_runs.router, "GET", "/v1/spaces/{space_id}/agents/supervisor/runs", "/v2/spaces/{space_id}/workflows/full-research/tasks", "List full research tasks", ("workflows",)),
    # Automation and templates.
    (schedules.router, "GET", "/v1/spaces/{space_id}/schedules", "/v2/spaces/{space_id}/schedules", "List schedules", ("schedules",)),
    (schedules.router, "POST", "/v1/spaces/{space_id}/schedules", "/v2/spaces/{space_id}/schedules", "Create schedule", ("schedules",)),
    (schedules.router, "GET", "/v1/spaces/{space_id}/schedules/{schedule_id}", "/v2/spaces/{space_id}/schedules/{schedule_id}", "Get schedule", ("schedules",)),
    (schedules.router, "PATCH", "/v1/spaces/{space_id}/schedules/{schedule_id}", "/v2/spaces/{space_id}/schedules/{schedule_id}", "Update schedule", ("schedules",)),
    (schedules.router, "POST", "/v1/spaces/{space_id}/schedules/{schedule_id}/pause", "/v2/spaces/{space_id}/schedules/{schedule_id}/pause", "Pause schedule", ("schedules",)),
    (schedules.router, "POST", "/v1/spaces/{space_id}/schedules/{schedule_id}/resume", "/v2/spaces/{space_id}/schedules/{schedule_id}/resume", "Resume schedule", ("schedules",)),
    (schedules.router, "POST", "/v1/spaces/{space_id}/schedules/{schedule_id}/run-now", "/v2/spaces/{space_id}/schedules/{schedule_id}/start-now", "Start scheduled task now", ("schedules",)),
    (harnesses.router, "GET", "/v1/harnesses", "/v2/workflow-templates", "List workflow templates", ("workflows",)),
)

for (
    _source_router,
    _method,
    _source_path,
    _target_path,
    _summary,
    _tags,
) in _ALIASES:
    _add_alias(
        source_router=_source_router,
        source_path=_source_path,
        target_path=_target_path,
        method=_method,
        summary=_summary,
        tags=_tags,
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}",
    response_model=HarnessRunResponse,
    summary="Get task",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> HarnessRunResponse:
    """Return one tracked task."""
    return _get_run(space_id=space_id, run_id=task_id, run_registry=run_registry)


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/progress",
    response_model=HarnessRunProgressResponse,
    summary="Get task progress",
    dependencies=[Depends(require_harness_space_read_access)],
    tags=["tasks"],
)
def get_task_progress(
    space_id: UUID,
    task_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> HarnessRunProgressResponse:
    """Return the latest progress snapshot for one tracked task."""
    return _get_run_progress(
        space_id=space_id,
        run_id=task_id,
        run_registry=run_registry,
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
    response_model=RunCapabilitiesResponse,
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
) -> RunCapabilitiesResponse:
    """Return the frozen tool and policy snapshot for one tracked task."""
    return _get_run_capabilities(
        space_id=space_id,
        run_id=task_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        execution_services=execution_services,
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/decisions",
    response_model=RunPolicyDecisionsResponse,
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
) -> RunPolicyDecisionsResponse:
    """Return declared and observed decisions for one tracked task."""
    return _get_run_policy_decisions(
        space_id=space_id,
        run_id=task_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        execution_services=execution_services,
    )


@router.post(
    "/v2/spaces/{space_id}/tasks/{task_id}/resume",
    response_model=HarnessRunResumeResponse,
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
) -> HarnessRunResumeResponse:
    """Resume one paused tracked task."""
    return await _resume_run(
        space_id=space_id,
        run_id=task_id,
        request=request,
        run_registry=run_registry,
        artifact_store=artifact_store,
        execution_services=execution_services,
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/outputs",
    response_model=HarnessArtifactListResponse,
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
) -> HarnessArtifactListResponse:
    """Return outputs stored for one tracked task."""
    return _list_artifacts(
        space_id=space_id,
        run_id=task_id,
        offset=offset,
        limit=limit,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/outputs/{output_key}",
    response_model=HarnessArtifactResponse,
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
) -> HarnessArtifactResponse:
    """Return one output stored for one tracked task."""
    return _get_artifact(
        space_id=space_id,
        run_id=task_id,
        artifact_key=output_key,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )


@router.get(
    "/v2/spaces/{space_id}/tasks/{task_id}/working-state",
    response_model=HarnessWorkspaceResponse,
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
) -> HarnessWorkspaceResponse:
    """Return the working-state snapshot stored for one tracked task."""
    return _get_workspace(
        space_id=space_id,
        run_id=task_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
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
    response_model=HarnessTemplateResponse,
    summary="Get workflow template",
    tags=["workflows"],
)
def get_workflow_template(template_id: str) -> HarnessTemplateResponse:
    """Return one workflow template by its public template id."""
    return _get_harness(harness_id=template_id)


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
    response_model=SupervisorRunDetailResponse,
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
) -> SupervisorRunDetailResponse:
    """Return one full-research task detail response."""
    return _get_supervisor_run(
        space_id=space_id,
        run_id=task_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )


@router.post(
    "/v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}/suggested-updates/{candidate_index}/decision",
    response_model=SupervisorChatGraphWriteCandidateDecisionResponse,
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
) -> SupervisorChatGraphWriteCandidateDecisionResponse:
    """Promote or reject one suggested update from a full-research task."""
    return _review_supervisor_update(
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


__all__ = ["router"]
