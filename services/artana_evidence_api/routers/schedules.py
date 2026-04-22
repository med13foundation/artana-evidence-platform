"""Schedule endpoints for graph-harness continuous-learning workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.auth import (
    HarnessUser,  # noqa: TC001
    get_current_harness_user,
)
from artana_evidence_api.continuous_learning_runtime import (
    normalize_seed_entity_ids,
)
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.queued_run_support import HarnessAcceptedRunResponse
from artana_evidence_api.routers.continuous_learning_runs import (
    ContinuousLearningRunRequest,
    ContinuousLearningRunResponse,
    create_continuous_learning_run,
)
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.run_budget import (
    HarnessRunBudget,
    budget_from_json,
    budget_to_json,
    resolve_continuous_learning_run_budget,
)
from artana_evidence_api.schedule_policy import normalize_schedule_cadence
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.run_registry import HarnessRunRegistry
    from artana_evidence_api.schedule_store import (
        HarnessScheduleRecord,
        HarnessScheduleStore,
    )
router = APIRouter(
    prefix="/v1/spaces",
    tags=["schedules"],
    dependencies=[Depends(require_harness_space_read_access)],
)
_SCHEDULE_STORE_DEPENDENCY = Depends(get_schedule_store)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_CONTINUOUS_LEARNING_HARNESS_ID = "continuous-learning"


class HarnessScheduleCreateRequest(BaseModel):
    """Create one continuous-learning schedule."""

    model_config = ConfigDict(strict=True)

    title: str | None = Field(default=None, min_length=1, max_length=256)
    cadence: str = Field(..., min_length=1, max_length=128)
    seed_entity_ids: list[str] | None = Field(default=None, max_length=100)
    source_type: str = Field(default="pubmed", min_length=1, max_length=64)
    relation_types: list[str] | None = Field(default=None, max_length=200)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_new_proposals: int = Field(default=20, ge=1, le=100)
    max_next_questions: int = Field(default=5, ge=1, le=20)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    run_budget: HarnessRunBudget | None = None
    metadata: JSONObject = Field(default_factory=dict)

    @field_validator("cadence")
    @classmethod
    def _validate_cadence(cls, value: str) -> str:
        return normalize_schedule_cadence(value)


class HarnessScheduleUpdateRequest(BaseModel):
    """Update one continuous-learning schedule."""

    model_config = ConfigDict(strict=True)

    title: str | None = Field(default=None, min_length=1, max_length=256)
    cadence: str | None = Field(default=None, min_length=1, max_length=128)
    seed_entity_ids: list[str] | None = Field(default=None, max_length=100)
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    relation_types: list[str] | None = Field(default=None, max_length=200)
    max_depth: int | None = Field(default=None, ge=1, le=4)
    max_new_proposals: int | None = Field(default=None, ge=1, le=100)
    max_next_questions: int | None = Field(default=None, ge=1, le=20)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    run_budget: HarnessRunBudget | None = None
    metadata: JSONObject | None = None

    @field_validator("cadence")
    @classmethod
    def _validate_cadence(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_schedule_cadence(value)


class HarnessScheduleResponse(BaseModel):
    """Serialized schedule definition."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    harness_id: str
    title: str
    cadence: str
    status: str
    created_by: str
    configuration: JSONObject
    metadata: JSONObject
    last_run_id: str | None
    last_run_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessScheduleRecord) -> HarnessScheduleResponse:
        return cls(
            id=record.id,
            space_id=record.space_id,
            harness_id=record.harness_id,
            title=record.title,
            cadence=record.cadence,
            status=record.status,
            created_by=record.created_by,
            configuration=record.configuration,
            metadata=record.metadata,
            last_run_id=record.last_run_id,
            last_run_at=(
                record.last_run_at.isoformat()
                if record.last_run_at is not None
                else None
            ),
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessScheduleListResponse(BaseModel):
    """List response for schedule definitions."""

    model_config = ConfigDict(strict=True)

    schedules: list[HarnessScheduleResponse]
    total: int
    offset: int
    limit: int


class HarnessScheduleDetailResponse(BaseModel):
    """Schedule detail including recent runs."""

    model_config = ConfigDict(strict=True)

    schedule: HarnessScheduleResponse
    recent_runs: list[HarnessRunResponse]


class HarnessScheduleRunNowResponse(BaseModel):
    """Combined schedule state and immediate run result."""

    model_config = ConfigDict(strict=True)

    schedule: HarnessScheduleResponse
    result: ContinuousLearningRunResponse


def _default_schedule_title(request: HarnessScheduleCreateRequest) -> str:
    title = request.title.strip() if isinstance(request.title, str) else ""
    return title or "Continuous Learning Schedule"


def _schedule_configuration_from_create(
    request: HarnessScheduleCreateRequest,
) -> JSONObject:
    return {
        "seed_entity_ids": request.seed_entity_ids or [],
        "source_type": request.source_type,
        "relation_types": request.relation_types or [],
        "max_depth": request.max_depth,
        "max_new_proposals": request.max_new_proposals,
        "max_next_questions": request.max_next_questions,
        "model_id": request.model_id,
        "run_budget": budget_to_json(
            resolve_continuous_learning_run_budget(request.run_budget),
        ),
    }


def _validated_schedule_seed_ids(seed_entity_ids: list[str] | None) -> list[str]:
    try:
        normalized_ids = normalize_seed_entity_ids(seed_entity_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if not normalized_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one seed_entity_id is required for continuous-learning schedules",
        )
    return normalized_ids


def _schedule_configuration_from_update(
    *,
    existing: JSONObject,
    request: HarnessScheduleUpdateRequest,
) -> JSONObject:
    updated = dict(existing)
    if request.seed_entity_ids is not None:
        updated["seed_entity_ids"] = request.seed_entity_ids
    if request.source_type is not None:
        updated["source_type"] = request.source_type
    if request.relation_types is not None:
        updated["relation_types"] = request.relation_types
    if request.max_depth is not None:
        updated["max_depth"] = request.max_depth
    if request.max_new_proposals is not None:
        updated["max_new_proposals"] = request.max_new_proposals
    if request.max_next_questions is not None:
        updated["max_next_questions"] = request.max_next_questions
    if request.model_id is not None:
        updated["model_id"] = request.model_id
    if request.run_budget is not None:
        updated["run_budget"] = budget_to_json(request.run_budget)
    return updated


def _require_schedule(
    *,
    space_id: UUID,
    schedule_id: UUID,
    schedule_store: HarnessScheduleStore,
) -> HarnessScheduleRecord:
    schedule = schedule_store.get_schedule(space_id=space_id, schedule_id=schedule_id)
    if schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found in space '{space_id}'",
        )
    return schedule


def _recent_runs_for_schedule(
    *,
    space_id: UUID,
    schedule_id: str,
    run_registry: HarnessRunRegistry,
) -> list[HarnessRunResponse]:
    recent_runs = [
        run
        for run in run_registry.list_runs(space_id=space_id)
        if run.input_payload.get("schedule_id") == schedule_id
    ]
    return [HarnessRunResponse.from_record(run) for run in recent_runs[:10]]


def _configuration_string(
    configuration: JSONObject,
    key: str,
    *,
    default: str,
) -> str:
    value = configuration.get(key)
    return value if isinstance(value, str) else default


def _configuration_optional_string(
    configuration: JSONObject,
    key: str,
) -> str | None:
    value = configuration.get(key)
    return value if isinstance(value, str) else None


def _configuration_string_list(
    configuration: JSONObject,
    key: str,
) -> list[str]:
    value = configuration.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _configuration_int(
    configuration: JSONObject,
    key: str,
    *,
    default: int,
) -> int:
    value = configuration.get(key)
    return value if isinstance(value, int) else default


def _continuous_learning_request_for_schedule(
    schedule: HarnessScheduleRecord,
) -> ContinuousLearningRunRequest:
    configuration = schedule.configuration
    return ContinuousLearningRunRequest(
        seed_entity_ids=_configuration_string_list(configuration, "seed_entity_ids"),
        title=schedule.title,
        source_type=_configuration_string(
            configuration,
            "source_type",
            default="pubmed",
        ),
        relation_types=_configuration_string_list(configuration, "relation_types"),
        max_depth=_configuration_int(configuration, "max_depth", default=2),
        max_new_proposals=_configuration_int(
            configuration,
            "max_new_proposals",
            default=20,
        ),
        max_next_questions=_configuration_int(
            configuration,
            "max_next_questions",
            default=5,
        ),
        model_id=_configuration_optional_string(configuration, "model_id"),
        schedule_id=schedule.id,
        run_budget=budget_from_json(configuration.get("run_budget")),
    )


@router.get(
    "/{space_id}/schedules",
    response_model=HarnessScheduleListResponse,
    summary="List schedules",
)
def list_schedules(
    space_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_DEPENDENCY,
) -> HarnessScheduleListResponse:
    schedules = schedule_store.list_schedules(space_id=space_id)
    total = len(schedules)
    paged = schedules[offset : offset + limit]
    return HarnessScheduleListResponse(
        schedules=[HarnessScheduleResponse.from_record(schedule) for schedule in paged],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/schedules",
    response_model=HarnessScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create schedule",
    dependencies=[Depends(require_harness_space_write_access)],
)
def create_schedule(
    space_id: UUID,
    request: HarnessScheduleCreateRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_DEPENDENCY,
) -> HarnessScheduleResponse:
    validated_seed_ids = _validated_schedule_seed_ids(request.seed_entity_ids)
    schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id=_CONTINUOUS_LEARNING_HARNESS_ID,
        title=_default_schedule_title(request),
        cadence=request.cadence,
        created_by=current_user.id,
        configuration={
            **_schedule_configuration_from_create(request),
            "seed_entity_ids": validated_seed_ids,
        },
        metadata=request.metadata,
        status="active",
    )
    return HarnessScheduleResponse.from_record(schedule)


@router.get(
    "/{space_id}/schedules/{schedule_id}",
    response_model=HarnessScheduleDetailResponse,
    summary="Get one schedule",
)
def get_schedule(
    space_id: UUID,
    schedule_id: UUID,
    *,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
) -> HarnessScheduleDetailResponse:
    schedule = _require_schedule(
        space_id=space_id,
        schedule_id=schedule_id,
        schedule_store=schedule_store,
    )
    return HarnessScheduleDetailResponse(
        schedule=HarnessScheduleResponse.from_record(schedule),
        recent_runs=_recent_runs_for_schedule(
            space_id=space_id,
            schedule_id=schedule.id,
            run_registry=run_registry,
        ),
    )


@router.patch(
    "/{space_id}/schedules/{schedule_id}",
    response_model=HarnessScheduleResponse,
    summary="Update schedule",
    dependencies=[Depends(require_harness_space_write_access)],
)
def update_schedule(
    space_id: UUID,
    schedule_id: UUID,
    request: HarnessScheduleUpdateRequest,
    *,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_DEPENDENCY,
) -> HarnessScheduleResponse:
    schedule = _require_schedule(
        space_id=space_id,
        schedule_id=schedule_id,
        schedule_store=schedule_store,
    )
    configuration = _schedule_configuration_from_update(
        existing=schedule.configuration,
        request=request,
    )
    if request.seed_entity_ids is not None:
        configuration["seed_entity_ids"] = _validated_schedule_seed_ids(
            request.seed_entity_ids,
        )
    updated = schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=schedule_id,
        title=request.title,
        cadence=request.cadence,
        configuration=configuration,
        metadata=(
            request.metadata if request.metadata is not None else schedule.metadata
        ),
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found in space '{space_id}'",
        )
    return HarnessScheduleResponse.from_record(updated)


@router.post(
    "/{space_id}/schedules/{schedule_id}/pause",
    response_model=HarnessScheduleResponse,
    summary="Pause schedule",
    dependencies=[Depends(require_harness_space_write_access)],
)
def pause_schedule(
    space_id: UUID,
    schedule_id: UUID,
    *,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_DEPENDENCY,
) -> HarnessScheduleResponse:
    _require_schedule(
        space_id=space_id,
        schedule_id=schedule_id,
        schedule_store=schedule_store,
    )
    updated = schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=schedule_id,
        status="paused",
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found in space '{space_id}'",
        )
    return HarnessScheduleResponse.from_record(updated)


@router.post(
    "/{space_id}/schedules/{schedule_id}/resume",
    response_model=HarnessScheduleResponse,
    summary="Resume schedule",
    dependencies=[Depends(require_harness_space_write_access)],
)
def resume_schedule(
    space_id: UUID,
    schedule_id: UUID,
    *,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_DEPENDENCY,
) -> HarnessScheduleResponse:
    _require_schedule(
        space_id=space_id,
        schedule_id=schedule_id,
        schedule_store=schedule_store,
    )
    updated = schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=schedule_id,
        status="active",
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found in space '{space_id}'",
        )
    return HarnessScheduleResponse.from_record(updated)


@router.post(
    "/{space_id}/schedules/{schedule_id}/run-now",
    response_model=HarnessScheduleRunNowResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Trigger immediate schedule run",
    dependencies=[Depends(require_harness_space_write_access)],
)
async def run_schedule_now(  # noqa: PLR0913
    space_id: UUID,
    schedule_id: UUID,
    *,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> HarnessScheduleRunNowResponse | JSONResponse:
    schedule = _require_schedule(
        space_id=space_id,
        schedule_id=schedule_id,
        schedule_store=schedule_store,
    )
    result = await create_continuous_learning_run(
        space_id=space_id,
        request=_continuous_learning_request_for_schedule(schedule),
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
        research_state_store=research_state_store,
        schedule_store=schedule_store,
        execution_services=execution_services,
    )
    if isinstance(result, JSONResponse):
        return result
    updated_schedule = schedule_store.get_schedule(
        space_id=space_id,
        schedule_id=schedule_id,
    )
    if updated_schedule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule '{schedule_id}' not found in space '{space_id}'",
        )
    return HarnessScheduleRunNowResponse(
        schedule=HarnessScheduleResponse.from_record(updated_schedule),
        result=result,
    )


__all__ = [
    "HarnessScheduleCreateRequest",
    "HarnessScheduleDetailResponse",
    "HarnessScheduleListResponse",
    "HarnessScheduleResponse",
    "HarnessScheduleRunNowResponse",
    "HarnessScheduleUpdateRequest",
    "create_schedule",
    "get_schedule",
    "list_schedules",
    "pause_schedule",
    "resume_schedule",
    "router",
    "run_schedule_now",
    "update_schedule",
]
