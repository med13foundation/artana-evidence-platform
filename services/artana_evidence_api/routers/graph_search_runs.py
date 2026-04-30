"""Harness-owned graph-search AI run endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.agent_contracts import GraphSearchContract
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

router = APIRouter(
    prefix="/v1/spaces",
    tags=["graph-search-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)


class GraphSearchRunRequest(BaseModel):
    """Request payload for one harness-owned graph-search run."""

    model_config = ConfigDict(strict=True)

    question: str = Field(..., min_length=1, max_length=2000)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    max_depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    curation_statuses: list[str] | None = None
    include_evidence_chains: bool = True


class GraphSearchRunResponse(BaseModel):
    """Combined run and graph-search result payload."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    result: GraphSearchContract


@router.post(
    "/{space_id}/agents/graph-search/runs",
    response_model=GraphSearchRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one harness-owned graph-search AI run",
)
async def create_graph_search_run(  # noqa: PLR0913
    space_id: UUID,
    request: GraphSearchRunRequest,
    prefer: str | None = Header(default=None, alias="Prefer"),
    *,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> GraphSearchRunResponse | JSONResponse:
    """Execute one AI-backed graph-search run from the harness service."""
    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Graph Search Agent Run"
    wait_outcome = None
    try:
        graph_health = graph_api_gateway.get_health()
        run = run_registry.create_run(
            space_id=space_id,
            harness_id="graph-search",
            title=resolved_title,
            input_payload={
                "question": request.question,
                "model_id": request.model_id,
                "max_depth": request.max_depth,
                "top_k": request.top_k,
                "curation_statuses": request.curation_statuses or [],
                "include_evidence_chains": request.include_evidence_chains,
            },
            graph_service_status=graph_health.status,
            graph_service_version=graph_health.version,
        )
        artifact_store.seed_for_run(run=run)
        ensure_run_transparency_seed(
            run=run,
            artifact_store=artifact_store,
            runtime=execution_services.runtime,
        )
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="queued")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={"status": "queued"},
        )
        wake_worker_for_queued_run(
            run=run,
            execution_services=execution_services,
        )
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
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Graph search")
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
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    finally:
        graph_api_gateway.close()
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
            detail="Failed to reload completed graph-search run.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
    )
    return GraphSearchRunResponse.model_validate(payload, strict=False)


__all__ = [
    "GraphSearchRunRequest",
    "GraphSearchRunResponse",
    "create_graph_search_run",
    "router",
]
