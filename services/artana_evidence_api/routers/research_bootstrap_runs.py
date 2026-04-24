"""Harness-owned research-bootstrap run endpoints."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING, Annotated
from uuid import UUID  # noqa: TC003

from artana_evidence_api.config import get_settings
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_run_registry,
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
from artana_evidence_api.research_bootstrap_runtime import (
    ResearchBootstrapExecutionResult,
    normalize_bootstrap_seed_entity_ids,
    queue_research_bootstrap_run,
)
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.transparency import ensure_run_transparency_seed
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.run_registry import HarnessRunRegistry

router = APIRouter(
    prefix="/v1/spaces",
    tags=["research-bootstrap-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)


class ResearchBootstrapRunRequest(BaseModel):
    """Request payload for one research-bootstrap run."""

    model_config = ConfigDict(strict=True)

    objective: str | None = Field(default=None, min_length=1, max_length=4000)
    seed_entity_ids: list[str] | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    source_type: str = Field(default="pubmed", min_length=1, max_length=64)
    relation_types: list[str] | None = Field(default=None, max_length=200)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_hypotheses: int = Field(default=20, ge=1, le=100)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)


class HarnessResearchStateResponse(BaseModel):
    """Serialized structured research-state snapshot."""

    model_config = ConfigDict(strict=True)

    space_id: str
    objective: str | None
    current_hypotheses: list[str]
    explored_questions: list[str]
    pending_questions: list[str]
    last_graph_snapshot_id: str | None
    last_learning_cycle_at: datetime | None
    active_schedules: list[str]
    confidence_model: JSONObject
    budget_policy: JSONObject
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


class HarnessGraphSnapshotResponse(BaseModel):
    """Serialized graph-context snapshot payload."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    source_run_id: str
    claim_ids: list[str]
    relation_ids: list[str]
    graph_document_hash: str
    summary: JSONObject
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


class ResearchBootstrapRunResponse(BaseModel):
    """Combined response for a completed research-bootstrap run."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    graph_snapshot: HarnessGraphSnapshotResponse
    research_state: HarnessResearchStateResponse
    research_brief: JSONObject
    graph_summary: JSONObject
    source_inventory: JSONObject
    proposal_count: int
    pending_questions: list[str]
    errors: list[str]
    claim_curation: JSONObject | None = None


def build_research_bootstrap_run_response(
    result: ResearchBootstrapExecutionResult,
) -> ResearchBootstrapRunResponse | JSONResponse:
    """Serialize one research-bootstrap execution result for HTTP responses."""
    return ResearchBootstrapRunResponse(
        run=HarnessRunResponse.from_record(result.run),
        graph_snapshot=HarnessGraphSnapshotResponse(
            id=result.graph_snapshot.id,
            space_id=result.graph_snapshot.space_id,
            source_run_id=result.graph_snapshot.source_run_id,
            claim_ids=list(result.graph_snapshot.claim_ids),
            relation_ids=list(result.graph_snapshot.relation_ids),
            graph_document_hash=result.graph_snapshot.graph_document_hash,
            summary=result.graph_snapshot.summary,
            metadata=result.graph_snapshot.metadata,
            created_at=result.graph_snapshot.created_at,
            updated_at=result.graph_snapshot.updated_at,
        ),
        research_state=HarnessResearchStateResponse(
            space_id=result.research_state.space_id,
            objective=result.research_state.objective,
            current_hypotheses=list(result.research_state.current_hypotheses),
            explored_questions=list(result.research_state.explored_questions),
            pending_questions=list(result.research_state.pending_questions),
            last_graph_snapshot_id=result.research_state.last_graph_snapshot_id,
            last_learning_cycle_at=result.research_state.last_learning_cycle_at,
            active_schedules=list(result.research_state.active_schedules),
            confidence_model=result.research_state.confidence_model,
            budget_policy=result.research_state.budget_policy,
            metadata=result.research_state.metadata,
            created_at=result.research_state.created_at,
            updated_at=result.research_state.updated_at,
        ),
        research_brief=result.research_brief,
        graph_summary=result.graph_summary,
        source_inventory=result.source_inventory,
        proposal_count=len(result.proposal_records),
        pending_questions=result.pending_questions,
        errors=result.errors,
        claim_curation=(
            {
                "status": result.claim_curation.status,
                "run_id": result.claim_curation.run_id,
                "proposal_ids": list(result.claim_curation.proposal_ids),
                "proposal_count": result.claim_curation.proposal_count,
                "blocked_proposal_count": result.claim_curation.blocked_proposal_count,
                "pending_approval_count": result.claim_curation.pending_approval_count,
                "reason": result.claim_curation.reason,
            }
            if result.claim_curation is not None
            else None
        ),
    )


@router.post(
    "/{space_id}/agents/research-bootstrap/runs",
    response_model=ResearchBootstrapRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one harness-owned research-bootstrap run",
)
async def create_research_bootstrap_run(  # noqa: PLR0913
    space_id: UUID,
    request: ResearchBootstrapRunRequest,
    *,
    prefer: Annotated[str | None, Header()] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> ResearchBootstrapRunResponse | JSONResponse:
    """Bootstrap a research space into a durable harness memory state."""
    objective = (
        request.objective.strip() if isinstance(request.objective, str) else None
    )
    try:
        seed_entity_ids = normalize_bootstrap_seed_entity_ids(request.seed_entity_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if objective is None and not seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either objective or at least one seed_entity_id.",
        )
    title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Research Bootstrap Harness"
    try:
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Research bootstrap")
        graph_health = graph_api_gateway.get_health()
        queued_run = queue_research_bootstrap_run(
            space_id=space_id,
            title=title,
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=request.source_type,
            relation_types=request.relation_types,
            max_depth=request.max_depth,
            max_hypotheses=request.max_hypotheses,
            model_id=request.model_id,
            graph_service_status=graph_health.status,
            graph_service_version=graph_health.version,
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
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
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
            detail=f"Failed to reload completed research-bootstrap run '{queued_run.id}'.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
    )
    return ResearchBootstrapRunResponse.model_validate(payload, strict=False)


__all__ = [
    "ResearchBootstrapRunRequest",
    "ResearchBootstrapRunResponse",
    "build_research_bootstrap_run_response",
    "create_research_bootstrap_run",
    "router",
]
