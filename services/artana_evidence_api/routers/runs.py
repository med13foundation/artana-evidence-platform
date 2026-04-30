"""Run lifecycle endpoints for the standalone harness service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.approval_store import (
    HarnessApprovalStore,  # noqa: TC001
)
from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_run_registry,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import (
    GraphServiceClientError,
    GraphTransportBundle,  # noqa: TC001
)
from artana_evidence_api.harness_registry import get_harness_template
from artana_evidence_api.queued_run import (
    maybe_execute_test_worker_run,
    require_worker_ready,
    should_require_worker_ready,
    wake_worker_for_queued_run,
)
from artana_evidence_api.run_registry import (  # noqa: TC001
    HarnessRunEventRecord,
    HarnessRunProgressRecord,
    HarnessRunRecord,
    HarnessRunRegistry,
)
from artana_evidence_api.supervisor_runtime import is_supervisor_workflow
from artana_evidence_api.transparency import (
    active_skill_names_from_policy_content,
    ensure_run_transparency_seed,
    sync_policy_decisions_artifact,
)
from artana_evidence_api.types.common import (  # noqa: TC001
    JSONObject,
    json_object_or_empty,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.harness_runtime import HarnessExecutionServices

router = APIRouter(
    prefix="/v1/spaces",
    tags=["runs"],
    dependencies=[Depends(require_harness_space_read_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_APPROVAL_STORE_DEPENDENCY = Depends(get_approval_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)


def _content_string_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


class HarnessRunCreateRequest(BaseModel):
    """Create one harness run."""

    model_config = ConfigDict(strict=True)

    harness_id: str = Field(..., min_length=1, max_length=128)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    input_payload: JSONObject = Field(default_factory=dict)


class HarnessRunResponse(BaseModel):
    """Serialized harness run record."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    harness_id: str
    title: str
    status: str
    input_payload: JSONObject
    graph_service_status: str
    graph_service_version: str
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessRunRecord) -> HarnessRunResponse:
        """Serialize one run record."""
        return cls(
            id=record.id,
            space_id=record.space_id,
            harness_id=record.harness_id,
            title=record.title,
            status=record.status,
            input_payload=record.input_payload,
            graph_service_status=record.graph_service_status,
            graph_service_version=record.graph_service_version,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessRunListResponse(BaseModel):
    """List response for harness runs."""

    model_config = ConfigDict(strict=True)

    runs: list[HarnessRunResponse]
    total: int
    offset: int
    limit: int


class HarnessRunProgressResponse(BaseModel):
    """Serialized run progress snapshot."""

    model_config = ConfigDict(strict=True)

    run_id: str
    status: str
    phase: str
    message: str
    progress_percent: float
    completed_steps: int
    total_steps: int | None
    resume_point: str | None
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(
        cls,
        record: HarnessRunProgressRecord,
    ) -> HarnessRunProgressResponse:
        """Serialize one run progress snapshot."""
        return cls(
            run_id=record.run_id,
            status=record.status,
            phase=record.phase,
            message=record.message,
            progress_percent=record.progress_percent,
            completed_steps=record.completed_steps,
            total_steps=record.total_steps,
            resume_point=record.resume_point,
            metadata=record.metadata,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessRunEventResponse(BaseModel):
    """Serialized lifecycle event for one run."""

    model_config = ConfigDict(strict=True)

    id: str
    event_type: str
    status: str
    message: str
    progress_percent: float | None
    payload: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessRunEventRecord) -> HarnessRunEventResponse:
        """Serialize one run event."""
        return cls(
            id=record.id,
            event_type=record.event_type,
            status=record.status,
            message=record.message,
            progress_percent=record.progress_percent,
            payload=record.payload,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessRunEventListResponse(BaseModel):
    """List response for run lifecycle events."""

    model_config = ConfigDict(strict=True)

    events: list[HarnessRunEventResponse]
    total: int
    offset: int
    limit: int


class HarnessRunResumeRequest(BaseModel):
    """Resume a paused run."""

    model_config = ConfigDict(strict=True)

    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: JSONObject = Field(default_factory=dict)


class HarnessRunResumeResponse(BaseModel):
    """Combined run summary and progress after a resume request."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    progress: HarnessRunProgressResponse


class ToolCapabilityDescriptor(BaseModel):
    """One declared tool capability for a run."""

    model_config = ConfigDict(strict=True)

    tool_name: str
    display_name: str
    description: str
    tool_groups: list[str] = Field(default_factory=list)
    required_capability: str | None = None
    risk_level: str
    side_effect: bool
    approval_mode: str
    idempotency_policy: str
    output_summary: str
    input_schema: JSONObject
    required_fields: list[str] = Field(default_factory=list)
    decision: str
    reason: str


class RunCapabilitiesResponse(BaseModel):
    """Serialized run-level capability snapshot."""

    model_config = ConfigDict(strict=True)

    run_id: str
    space_id: str
    harness_id: str
    tool_groups: list[str] = Field(default_factory=list)
    preloaded_skill_names: list[str] = Field(default_factory=list)
    allowed_skill_names: list[str] = Field(default_factory=list)
    active_skill_names: list[str] = Field(default_factory=list)
    policy_profile: JSONObject
    artifact_key: str
    created_at: str
    updated_at: str
    visible_tools: list[ToolCapabilityDescriptor] = Field(default_factory=list)
    filtered_tools: list[ToolCapabilityDescriptor] = Field(default_factory=list)

    @classmethod
    def from_content(cls, content: JSONObject) -> RunCapabilitiesResponse:
        visible_raw = content.get("visible_tools")
        filtered_raw = content.get("filtered_tools")
        policy_profile = content.get("policy_profile")
        return cls(
            run_id=str(content.get("run_id")),
            space_id=str(content.get("space_id")),
            harness_id=str(content.get("harness_id")),
            tool_groups=_content_string_list(content.get("tool_groups")),
            preloaded_skill_names=_content_string_list(
                content.get("preloaded_skill_names"),
            ),
            allowed_skill_names=_content_string_list(content.get("allowed_skill_names")),
            active_skill_names=_content_string_list(content.get("active_skill_names")),
            policy_profile=(
                {str(key): value for key, value in policy_profile.items()}
                if isinstance(policy_profile, dict)
                else {}
            ),
            artifact_key=str(content.get("artifact_key", "run_capabilities")),
            created_at=str(content.get("created_at")),
            updated_at=str(content.get("updated_at")),
            visible_tools=(
                [
                    ToolCapabilityDescriptor.model_validate(item)
                    for item in visible_raw
                    if isinstance(item, dict)
                ]
                if isinstance(visible_raw, list)
                else []
            ),
            filtered_tools=(
                [
                    ToolCapabilityDescriptor.model_validate(item)
                    for item in filtered_raw
                    if isinstance(item, dict)
                ]
                if isinstance(filtered_raw, list)
                else []
            ),
        )


class ToolDecisionRecord(BaseModel):
    """One observed tool or manual-review policy decision."""

    model_config = ConfigDict(strict=True)

    decision_source: str
    tool_name: str
    decision: str
    reason: str
    status: str
    event_id: str | None = None
    approval_id: str | None = None
    artifact_key: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    metadata: JSONObject = Field(default_factory=dict)


class RunPolicyDecisionsResponse(BaseModel):
    """Serialized run-level policy decision log."""

    model_config = ConfigDict(strict=True)

    run_id: str
    space_id: str
    harness_id: str
    artifact_key: str
    declared_policy: list[JSONObject] = Field(default_factory=list)
    records: list[ToolDecisionRecord] = Field(default_factory=list)
    summary: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_content(cls, content: JSONObject) -> RunPolicyDecisionsResponse:
        records_raw = content.get("records")
        declared_raw = content.get("declared_policy")
        return cls(
            run_id=str(content.get("run_id")),
            space_id=str(content.get("space_id")),
            harness_id=str(content.get("harness_id")),
            artifact_key=str(content.get("artifact_key", "policy_decisions")),
            declared_policy=(
                [item for item in declared_raw if isinstance(item, dict)]
                if isinstance(declared_raw, list)
                else []
            ),
            records=(
                [
                    ToolDecisionRecord.model_validate(item)
                    for item in records_raw
                    if isinstance(item, dict)
                ]
                if isinstance(records_raw, list)
                else []
            ),
            summary=json_object_or_empty(content.get("summary")),
            created_at=str(content.get("created_at")),
            updated_at=str(content.get("updated_at")),
        )


def _require_run_record(
    *,
    space_id: UUID,
    run_id: UUID,
    run_registry: HarnessRunRegistry,
) -> HarnessRunRecord:
    run = run_registry.get_run(space_id=space_id, run_id=run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in space '{space_id}'",
        )
    return run


@router.post(
    "/{space_id}/runs",
    response_model=HarnessRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start one harness run",
    dependencies=[Depends(require_harness_space_write_access)],
)
def create_run(  # noqa: PLR0913
    space_id: UUID,
    request: HarnessRunCreateRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> HarnessRunResponse:
    """Queue one harness run after validating graph service availability."""
    template = get_harness_template(request.harness_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown harness '{request.harness_id}'",
        )

    title = request.title.strip() if isinstance(request.title, str) else ""
    resolved_title = title or template.display_name
    try:
        graph_health = graph_api_gateway.get_health()
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()

    run = run_registry.create_run(
        space_id=space_id,
        harness_id=template.id,
        title=resolved_title,
        input_payload=request.input_payload,
        graph_service_status=graph_health.status,
        graph_service_version=graph_health.version,
    )
    artifact_store.seed_for_run(run=run)
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    return HarnessRunResponse.from_record(run)


@router.get(
    "/{space_id}/runs",
    response_model=HarnessRunListResponse,
    summary="List harness runs",
)
def list_runs(
    space_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> HarnessRunListResponse:
    """Return harness runs for one research space."""
    runs = run_registry.list_runs(space_id=space_id)
    total = len(runs)
    paged = runs[offset : offset + limit]
    return HarnessRunListResponse(
        runs=[HarnessRunResponse.from_record(run) for run in paged],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/runs/{run_id}",
    response_model=HarnessRunResponse,
    summary="Get one harness run",
)
def get_run(
    space_id: UUID,
    run_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> HarnessRunResponse:
    """Return one harness run from the service-local registry."""
    run = _require_run_record(
        space_id=space_id,
        run_id=run_id,
        run_registry=run_registry,
    )
    return HarnessRunResponse.from_record(run)


@router.get(
    "/{space_id}/runs/{run_id}/progress",
    response_model=HarnessRunProgressResponse,
    summary="Get run progress",
)
def get_run_progress(
    space_id: UUID,
    run_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> HarnessRunProgressResponse:
    """Return the current progress snapshot for one run."""
    if not run_registry.has_run(space_id=space_id, run_id=run_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in space '{space_id}'",
        )
    progress = run_registry.get_progress(space_id=space_id, run_id=run_id)
    if progress is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Progress for run '{run_id}' not found in space '{space_id}'",
        )
    return HarnessRunProgressResponse.from_record(progress)


@router.get(
    "/{space_id}/runs/{run_id}/events",
    response_model=HarnessRunEventListResponse,
    summary="List run lifecycle events",
)
def list_run_events(
    space_id: UUID,
    run_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> HarnessRunEventListResponse:
    """Return lifecycle events for one run."""
    if not run_registry.has_run(space_id=space_id, run_id=run_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found in space '{space_id}'",
        )
    events = run_registry.list_events(space_id=space_id, run_id=run_id, limit=limit)
    total = len(events)
    paged = events[offset : offset + limit]
    return HarnessRunEventListResponse(
        events=[HarnessRunEventResponse.from_record(record) for record in paged],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/runs/{run_id}/capabilities",
    response_model=RunCapabilitiesResponse,
    summary="Get run capabilities",
)
def get_run_capabilities(
    space_id: UUID,
    run_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> RunCapabilitiesResponse:
    """Return the frozen capability snapshot for one run."""
    run = _require_run_record(
        space_id=space_id,
        run_id=run_id,
        run_registry=run_registry,
    )
    policy_content = sync_policy_decisions_artifact(
        space_id=space_id,
        run_id=run_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="run_capabilities",
    )
    if artifact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Capability snapshot for run '{run_id}' was not found",
        )
    content = dict(artifact.content)
    content["active_skill_names"] = (
        active_skill_names_from_policy_content(policy_content)
        if policy_content is not None
        else []
    )
    return RunCapabilitiesResponse.from_content(content)


@router.get(
    "/{space_id}/runs/{run_id}/policy-decisions",
    response_model=RunPolicyDecisionsResponse,
    summary="Get run policy decisions",
)
def get_run_policy_decisions(
    space_id: UUID,
    run_id: UUID,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> RunPolicyDecisionsResponse:
    """Return declared and observed policy decisions for one run."""
    _require_run_record(space_id=space_id, run_id=run_id, run_registry=run_registry)
    content = sync_policy_decisions_artifact(
        space_id=space_id,
        run_id=run_id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    if content is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy decisions for run '{run_id}' were not found",
        )
    return RunPolicyDecisionsResponse.from_content(content)


@router.post(
    "/{space_id}/runs/{run_id}/resume",
    response_model=HarnessRunResumeResponse,
    summary="Resume a paused run",
    dependencies=[Depends(require_harness_space_write_access)],
)
async def resume_run(  # noqa: PLR0913
    space_id: UUID,
    run_id: UUID,
    request: HarnessRunResumeRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> HarnessRunResumeResponse:
    """Mark a paused run as resumable after approvals are resolved."""
    run = _require_run_record(
        space_id=space_id,
        run_id=run_id,
        run_registry=run_registry,
    )
    if run.status != "paused":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' is not paused",
        )

    approvals = approval_store.list_approvals(space_id=space_id, run_id=run_id)
    pending_approvals = [
        approval.approval_key for approval in approvals if approval.status == "pending"
    ]
    if pending_approvals:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Run '{run_id}' cannot resume while approvals are pending: "
                + ", ".join(pending_approvals)
            ),
        )
    if is_supervisor_workflow(run):
        workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)
        child_curation_run_id = (
            workspace.snapshot.get("curation_run_id") if workspace is not None else None
        )
        if (
            isinstance(child_curation_run_id, str)
            and child_curation_run_id.strip() != ""
        ):
            child_pending_approvals = [
                approval.approval_key
                for approval in approval_store.list_approvals(
                    space_id=space_id,
                    run_id=child_curation_run_id,
                )
                if approval.status == "pending"
            ]
            if child_pending_approvals:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Run '{run_id}' cannot resume while child curation "
                        "approvals are pending: " + ", ".join(child_pending_approvals)
                    ),
                )
    if should_require_worker_ready(execution_services=execution_services):
        require_worker_ready(operation_name="Run resume")

    current_progress = run_registry.get_progress(space_id=space_id, run_id=run_id)
    updated_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run_id,
        status="queued",
        existing_progress=current_progress,
    )
    updated_progress = run_registry.set_progress(
        space_id=space_id,
        run_id=run_id,
        phase="queued",
        message="Run resume requested; awaiting worker pickup.",
        progress_percent=(
            current_progress.progress_percent if current_progress is not None else 0.0
        ),
        completed_steps=(
            current_progress.completed_steps if current_progress is not None else 0
        ),
        total_steps=(
            current_progress.total_steps if current_progress is not None else None
        ),
        clear_resume_point=True,
        metadata={
            **request.metadata,
            "resume_reason": request.reason or "manual_resume",
        },
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run_id,
        event_type="run.resumed",
        message="Run resume requested.",
        payload={
            "reason": request.reason,
            "metadata": request.metadata,
            "approval_count": len(approvals),
        },
        progress_percent=(
            updated_progress.progress_percent if updated_progress is not None else None
        ),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={
            "status": "queued",
            "resume_requested": True,
            "resume_reason": request.reason,
            "resume_metadata": request.metadata,
            "resume_point": None,
        },
    )
    if updated_run is None or updated_progress is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume run '{run_id}'",
        )
    if getattr(execution_services, "execution_override", None) is not None:
        await maybe_execute_test_worker_run(
            run=updated_run,
            services=execution_services,
        )
        refreshed_run = run_registry.get_run(space_id=space_id, run_id=run_id)
        refreshed_progress = run_registry.get_progress(space_id=space_id, run_id=run_id)
        if refreshed_run is not None and refreshed_progress is not None:
            updated_run = refreshed_run
            updated_progress = refreshed_progress
    else:
        wake_worker_for_queued_run(
            run=updated_run,
            execution_services=execution_services,
        )
    return HarnessRunResumeResponse(
        run=HarnessRunResponse.from_record(updated_run),
        progress=HarnessRunProgressResponse.from_record(updated_progress),
    )


__all__ = [
    "HarnessRunCreateRequest",
    "HarnessRunEventListResponse",
    "HarnessRunEventResponse",
    "HarnessRunListResponse",
    "HarnessRunProgressResponse",
    "HarnessRunResumeRequest",
    "HarnessRunResumeResponse",
    "HarnessRunResponse",
    "create_run",
    "get_run",
    "get_run_progress",
    "list_runs",
    "list_run_events",
    "resume_run",
    "router",
]
