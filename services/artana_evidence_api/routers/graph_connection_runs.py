"""Harness-owned graph-connection AI run endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.agent_contracts import GraphConnectionContract
from artana_evidence_api.config import get_settings
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_run_registry,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.queued_run import (
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
from artana_evidence_api.transparency import ensure_run_transparency_seed
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.run_registry import HarnessRunRegistry
    from artana_evidence_api.types.common import JSONObject

router = APIRouter(
    prefix="/v1/spaces",
    tags=["graph-connection-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)

_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"


class GraphConnectionRunRequest(BaseModel):
    """Request payload for one harness-owned graph-connection run."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] = Field(..., min_length=1, max_length=200)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    source_type: str | None = Field(default=None, min_length=1, max_length=64)
    source_id: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    relation_types: list[str] | None = None
    max_depth: int = Field(default=2, ge=1, le=4)
    shadow_mode: bool = True
    pipeline_run_id: str | None = Field(default=None, min_length=1, max_length=128)


class GraphConnectionRunResponse(BaseModel):
    """Combined run and graph-connection result payload."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    outcomes: list[GraphConnectionContract]


def _normalize_seed_entity_ids(seed_entity_ids: list[str]) -> list[str]:
    normalized_ids: list[str] = []
    for value in seed_entity_ids:
        normalized = value.strip()
        if not normalized:
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        normalized_ids.append(normalized)
    return normalized_ids


@router.post(
    "/{space_id}/agents/graph-connections/runs",
    response_model=GraphConnectionRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one harness-owned graph-connection AI run",
)
async def create_graph_connection_run(  # noqa: PLR0913
    space_id: UUID,
    request: GraphConnectionRunRequest,
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    prefer: str | None = Header(default=None),
) -> GraphConnectionRunResponse | JSONResponse:
    """Execute one AI-backed graph-connection run from the harness service."""
    try:
        seed_entity_ids = _normalize_seed_entity_ids(request.seed_entity_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Graph Connection Agent Run"
    try:
        graph_health = graph_api_gateway.get_health()
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()

    run_input_payload: JSONObject = {
        "seed_entity_ids": seed_entity_ids,
        "source_type": request.source_type,
        "source_id": request.source_id,
        "model_id": request.model_id,
        "relation_types": request.relation_types or [],
        "max_depth": request.max_depth,
        "shadow_mode": request.shadow_mode,
        "pipeline_run_id": request.pipeline_run_id,
    }
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="graph-connections",
        title=resolved_title,
        input_payload=run_input_payload,
        graph_service_status=graph_health.status,
        graph_service_version=graph_health.version,
    )
    artifact_store.seed_for_run(run=run)
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    wake_worker_for_queued_run(
        run=run,
        execution_services=execution_services,
    )
    if should_require_worker_ready(execution_services=execution_services):
        require_worker_ready(operation_name="Graph-connection")
    if prefers_respond_async(prefer):
        accepted = build_accepted_run_response(
            run=run,
            run_registry=run_registry,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=accepted.model_dump(mode="json"),
            headers={"Preference-Applied": "respond-async"},
        )
    await maybe_execute_test_worker_run(
        run=run,
        services=execution_services,
    )
    wait_outcome = await wait_for_terminal_run(
        space_id=space_id,
        run_id=run.id,
        run_registry=run_registry,
        timeout_seconds=get_settings().sync_wait_timeout_seconds,
        poll_interval_seconds=get_settings().sync_wait_poll_seconds,
    )
    if wait_outcome.timed_out:
        accepted = build_accepted_run_response(
            run=run,
            run_registry=run_registry,
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=accepted.model_dump(mode="json"),
        )
    if wait_outcome.run is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload completed graph-connection run '{run.id}'.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
    )
    return GraphConnectionRunResponse.model_validate(payload, strict=False)


__all__ = [
    "GraphConnectionRunRequest",
    "GraphConnectionRunResponse",
    "create_graph_connection_run",
    "router",
]
