"""Harness-owned continuous-learning run endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID  # noqa: TC003

from artana_evidence_api.config import get_settings
from artana_evidence_api.continuous_learning_runtime import (
    ActiveScheduleRunConflictError,
    ContinuousLearningCandidateRecord,
    ScheduleTriggerClaimConflictError,
    normalize_seed_entity_ids,
    queue_continuous_learning_run,
    queue_schedule_bound_continuous_learning_run,
)
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.queued_run_support import (
    HarnessAcceptedRunResponse,
    build_accepted_run_response,
    load_primary_result_artifact,
    maybe_execute_test_worker_run,
    prefers_respond_async,
    raise_for_failed_run,
    require_worker_ready,
    should_require_worker_ready,
    wait_for_terminal_run,
    wake_worker_for_queued_run,
)
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.run_budget import (
    HarnessRunBudget,
    HarnessRunBudgetStatus,
    resolve_continuous_learning_run_budget,
)
from artana_evidence_api.transparency import ensure_run_transparency_seed
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.run_registry import HarnessRunRegistry
    from artana_evidence_api.schedule_store import HarnessScheduleStore

router = APIRouter(
    prefix="/v1/spaces",
    tags=["continuous-learning-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_SCHEDULE_STORE_DEPENDENCY = Depends(get_schedule_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)


class ContinuousLearningRunRequest(BaseModel):
    """Request payload for one continuous-learning cycle."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    source_type: str = Field(default="pubmed", min_length=1, max_length=64)
    relation_types: list[str] | None = Field(default=None, max_length=200)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_new_proposals: int = Field(default=20, ge=1, le=100)
    max_next_questions: int = Field(default=5, ge=1, le=20)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    schedule_id: str | None = Field(default=None, min_length=1, max_length=128)
    run_budget: HarnessRunBudget | None = None


class ContinuousLearningCandidateResponse(BaseModel):
    """One candidate relation observed during a learning cycle."""

    model_config = ConfigDict(strict=True)

    seed_entity_id: str
    source_entity_id: str
    relation_type: str
    target_entity_id: str
    confidence: float
    evidence_summary: str
    reasoning: str
    agent_run_id: str | None
    source_type: str

    @classmethod
    def from_record(
        cls,
        record: ContinuousLearningCandidateRecord,
    ) -> ContinuousLearningCandidateResponse:
        return cls(
            seed_entity_id=record.seed_entity_id,
            source_entity_id=record.source_entity_id,
            relation_type=record.relation_type,
            target_entity_id=record.target_entity_id,
            confidence=record.confidence,
            evidence_summary=record.evidence_summary,
            reasoning=record.reasoning,
            agent_run_id=record.agent_run_id,
            source_type=record.source_type,
        )


class ContinuousLearningRunResponse(BaseModel):
    """Combined response for a completed continuous-learning cycle."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    candidates: list[ContinuousLearningCandidateResponse]
    candidate_count: int
    proposal_count: int
    next_questions: list[str]
    delta_report: JSONObject
    errors: list[str]
    run_budget: HarnessRunBudget
    budget_status: HarnessRunBudgetStatus


def _resolve_continuous_learning_inputs(
    request: ContinuousLearningRunRequest,
) -> tuple[list[str], str]:
    try:
        seed_entity_ids = normalize_seed_entity_ids(request.seed_entity_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if not seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "At least one seed_entity_id is required for continuous-learning runs"
            ),
        )
    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Continuous Learning Harness"
    return seed_entity_ids, resolved_title


@router.post(
    "/{space_id}/agents/continuous-learning/runs",
    response_model=ContinuousLearningRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one harness-owned continuous-learning run",
)
async def create_continuous_learning_run(  # noqa: PLR0913
    space_id: UUID,
    request: ContinuousLearningRunRequest,
    *,
    prefer: Annotated[str | None, Header()] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
    schedule_store: HarnessScheduleStore = _SCHEDULE_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> ContinuousLearningRunResponse:
    """Run one continuous-learning cycle and stage net-new proposals."""
    seed_entity_ids, resolved_title = _resolve_continuous_learning_inputs(request)
    research_state = research_state_store.get_state(space_id=space_id)
    if request.schedule_id is not None:
        existing_schedule = schedule_store.get_schedule(
            space_id=space_id,
            schedule_id=request.schedule_id,
        )
        if existing_schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Schedule '{request.schedule_id}' not found in space "
                    f"'{space_id}'"
                ),
            )
    try:
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Continuous learning")
        graph_health = graph_api_gateway.get_health()
        resolved_run_budget = resolve_continuous_learning_run_budget(request.run_budget)
        previous_graph_snapshot_id = (
            research_state.last_graph_snapshot_id
            if research_state is not None
            else None
        )
        if request.schedule_id is not None:
            queued_run = queue_schedule_bound_continuous_learning_run(
                space_id=space_id,
                title=resolved_title,
                seed_entity_ids=seed_entity_ids,
                source_type=request.source_type,
                relation_types=request.relation_types,
                max_depth=request.max_depth,
                max_new_proposals=request.max_new_proposals,
                max_next_questions=request.max_next_questions,
                model_id=request.model_id,
                schedule_id=request.schedule_id,
                run_budget=resolved_run_budget,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                previous_graph_snapshot_id=previous_graph_snapshot_id,
                schedule_store=schedule_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        else:
            queued_run = queue_continuous_learning_run(
                space_id=space_id,
                title=resolved_title,
                seed_entity_ids=seed_entity_ids,
                source_type=request.source_type,
                relation_types=request.relation_types,
                max_depth=request.max_depth,
                max_new_proposals=request.max_new_proposals,
                max_next_questions=request.max_next_questions,
                model_id=request.model_id,
                schedule_id=None,
                run_budget=resolved_run_budget,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                previous_graph_snapshot_id=previous_graph_snapshot_id,
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        ensure_run_transparency_seed(
            run=queued_run,
            artifact_store=artifact_store,
            runtime=execution_services.runtime,
        )
        wake_worker_for_queued_run(
            run=queued_run,
            execution_services=execution_services,
        )
        if prefers_respond_async(prefer):
            accepted = build_accepted_run_response(
                run=queued_run,
                run_registry=run_registry,
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content=accepted.model_dump(mode="json"),
                headers={"Preference-Applied": "respond-async"},
            )
        await maybe_execute_test_worker_run(
            run=queued_run,
            services=execution_services,
        )
        wait_outcome = await wait_for_terminal_run(
            space_id=space_id,
            run_id=queued_run.id,
            run_registry=run_registry,
            timeout_seconds=get_settings().sync_wait_timeout_seconds,
            poll_interval_seconds=get_settings().sync_wait_poll_seconds,
        )
    except GraphServiceClientError as exc:
        detail = exc.detail or str(exc)
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from exc
    except (
        ActiveScheduleRunConflictError,
        ScheduleTriggerClaimConflictError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    finally:
        graph_api_gateway.close()
    if wait_outcome.timed_out:
        accepted = build_accepted_run_response(
            run=queued_run,
            run_registry=run_registry,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=accepted.model_dump(mode="json"),
        )
    if wait_outcome.run is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reload completed continuous-learning run.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
    )
    response = ContinuousLearningRunResponse.model_validate(payload, strict=False)
    if request.schedule_id is not None:
        schedule_store.update_schedule(
            space_id=space_id,
            schedule_id=request.schedule_id,
            last_run_id=response.run.id,
            last_run_at=wait_outcome.run.updated_at,
        )
    return response


__all__ = [
    "ContinuousLearningCandidateResponse",
    "ContinuousLearningRunRequest",
    "ContinuousLearningRunResponse",
    "create_continuous_learning_run",
    "router",
]
