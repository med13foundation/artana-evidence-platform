"""Harness-owned deterministic full AI orchestrator endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from artana_evidence_api.auth import (
    HarnessUser,
    HarnessUserRole,
    get_current_harness_user,
)
from artana_evidence_api.config import get_settings
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_identity_gateway,
    get_run_registry,
    require_harness_space_write_access,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorRunRequest,
    FullAIOrchestratorRunResponse,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    queue_full_ai_orchestrator_run,
    resolve_guarded_rollout_profile,
    store_pubmed_replay_bundle_artifact,
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
from artana_evidence_api.research_init_helpers import _resolve_research_init_sources
from artana_evidence_api.research_init_runtime import (
    deserialize_pubmed_replay_bundle,
    prepare_pubmed_replay_bundle,
)
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.identity.contracts import IdentityGateway
    from artana_evidence_api.run_registry import HarnessRunRegistry

router = APIRouter(
    prefix="/v1/spaces",
    tags=["full-ai-orchestrator-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_IDENTITY_GATEWAY_DEPENDENCY = Depends(get_identity_gateway)


@router.post(
    "/{space_id}/agents/full-ai-orchestrator/runs",
    response_model=FullAIOrchestratorRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one deterministic full AI orchestrator run",
)
async def create_full_ai_orchestrator_run(  # noqa: PLR0913
    space_id: UUID,
    request: FullAIOrchestratorRunRequest,
    *,
    prefer: Annotated[str | None, Header()] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    identity_gateway: IdentityGateway = _IDENTITY_GATEWAY_DEPENDENCY,
) -> FullAIOrchestratorRunResponse | JSONResponse:
    """Queue and execute the deterministic Phase 1 orchestrator baseline."""
    objective = request.objective.strip()
    if objective == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Objective is required.",
        )
    normalized_seed_terms = [
        term.strip()
        for term in (request.seed_terms or [])
        if isinstance(term, str) and term.strip() != ""
    ]
    title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Full AI Orchestrator Harness"
    space_record = identity_gateway.get_space(
        space_id=space_id,
        user_id=current_user.id,
        is_admin=current_user.role == HarnessUserRole.ADMIN,
    )
    sources = _resolve_research_init_sources(
        request_sources=request.sources,
        space_settings=space_record.settings if space_record is not None else None,
    )
    guarded_rollout_profile, guarded_rollout_profile_source = (
        resolve_guarded_rollout_profile(
            planner_mode=request.planner_mode,
            request_profile=request.guarded_rollout_profile,
            space_settings=space_record.settings if space_record is not None else None,
        )
    )
    replay_bundle = None
    try:
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Full AI orchestrator")
        graph_health = graph_api_gateway.get_health()
        if sources.get("pubmed", True):
            if request.pubmed_replay_bundle is not None:
                replay_bundle = deserialize_pubmed_replay_bundle(
                    request.pubmed_replay_bundle,
                )
                if replay_bundle is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid pubmed_replay_bundle payload.",
                    )
            else:
                replay_bundle = await prepare_pubmed_replay_bundle(
                    objective=objective,
                    seed_terms=normalized_seed_terms,
                )
        queued_run = queue_full_ai_orchestrator_run(
            space_id=space_id,
            title=title,
            objective=objective,
            seed_terms=normalized_seed_terms,
            sources=sources,
            planner_mode=request.planner_mode,
            max_depth=request.max_depth,
            max_hypotheses=request.max_hypotheses,
            graph_service_status=graph_health.status,
            graph_service_version=graph_health.version,
            run_registry=run_registry,
            artifact_store=artifact_store,
            execution_services=execution_services,
            guarded_rollout_profile=guarded_rollout_profile,
            guarded_rollout_profile_source=guarded_rollout_profile_source,
        )
        if replay_bundle is not None:
            store_pubmed_replay_bundle_artifact(
                artifact_store=artifact_store,
                space_id=space_id,
                run_id=queued_run.id,
                replay_bundle=replay_bundle,
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
            detail=(
                "Failed to reload completed full AI orchestrator run "
                f"'{queued_run.id}'."
            ),
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
    )
    return FullAIOrchestratorRunResponse.model_validate(payload, strict=False)


__all__ = [
    "FullAIOrchestratorRunRequest",
    "FullAIOrchestratorRunResponse",
    "create_full_ai_orchestrator_run",
    "router",
]
