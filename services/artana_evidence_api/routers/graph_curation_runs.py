"""Harness-owned claim-curation run endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated
from uuid import UUID  # noqa: TC003

from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.claim_curation_runtime import (
    load_curatable_proposals,
    normalize_requested_proposal_ids,
)
from artana_evidence_api.claim_curation_workflow import (
    ClaimCurationNoEligibleProposalsError,
    ClaimCurationRunExecution,
    queue_claim_curation_run,
)
from artana_evidence_api.config import get_settings
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_proposal_store,
    get_run_registry,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import (
    GraphServiceClientError,
    GraphTransportBundle,  # noqa: TC001
)
from artana_evidence_api.proposal_store import (
    HarnessProposalStore,  # noqa: TC001
)
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
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from artana_evidence_api.transparency import ensure_run_transparency_seed
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.harness_runtime import HarnessExecutionServices

router = APIRouter(
    prefix="/v1/spaces",
    tags=["graph-curation-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)


class ClaimCurationRunRequest(BaseModel):
    """Request payload for one claim-curation harness run."""

    model_config = ConfigDict(strict=False)

    proposal_ids: list[UUID] = Field(min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=256)


class ClaimCurationSelectedProposalResponse(BaseModel):
    """One proposal selected for a curation run."""

    model_config = ConfigDict(strict=True)

    proposal_id: str
    title: str
    summary: str
    source_key: str
    confidence: float
    ranking_score: float
    approval_key: str
    duplicate_selected_count: int
    existing_promoted_proposal_ids: list[str]
    graph_duplicate_claim_ids: list[str]
    conflicting_relation_ids: list[str]
    invariant_issues: list[str]
    blocker_reasons: list[str]
    eligible_for_approval: bool


class ClaimCurationRunResponse(BaseModel):
    """Combined response for one paused claim-curation run."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    curation_packet_key: str
    review_plan_key: str
    approval_intent_key: str
    proposal_count: int
    blocked_proposal_count: int
    pending_approval_count: int
    proposals: list[ClaimCurationSelectedProposalResponse]


def _selected_proposals_response(
    review_plan: JSONObject,
) -> list[ClaimCurationSelectedProposalResponse]:
    proposals_value = review_plan.get("proposals")
    if not isinstance(proposals_value, list):
        return []
    selected: list[ClaimCurationSelectedProposalResponse] = []
    for item in proposals_value:
        if not isinstance(item, dict):
            continue
        selected.append(
            ClaimCurationSelectedProposalResponse(
                proposal_id=str(item["proposal_id"]),
                title=str(item["title"]),
                summary=str(item["summary"]),
                source_key=str(item["source_key"]),
                confidence=float(item["confidence"]),
                ranking_score=float(item["ranking_score"]),
                approval_key=str(item["approval_key"]),
                duplicate_selected_count=int(item["duplicate_selected_count"]),
                existing_promoted_proposal_ids=[
                    str(value)
                    for value in item.get("existing_promoted_proposal_ids", [])
                    if isinstance(value, str)
                ],
                graph_duplicate_claim_ids=[
                    str(value)
                    for value in item.get("graph_duplicate_claim_ids", [])
                    if isinstance(value, str)
                ],
                conflicting_relation_ids=[
                    str(value)
                    for value in item.get("conflicting_relation_ids", [])
                    if isinstance(value, str)
                ],
                invariant_issues=[
                    str(value)
                    for value in item.get("invariant_issues", [])
                    if isinstance(value, str)
                ],
                blocker_reasons=[
                    str(value)
                    for value in item.get("blocker_reasons", [])
                    if isinstance(value, str)
                ],
                eligible_for_approval=bool(item.get("eligible_for_approval", False)),
            ),
        )
    return selected


def build_claim_curation_run_response(
    execution: ClaimCurationRunExecution,
) -> ClaimCurationRunResponse:
    """Serialize one claim-curation execution into the public route response."""
    return ClaimCurationRunResponse(
        run=HarnessRunResponse.from_record(execution.run),
        curation_packet_key="curation_packet",
        review_plan_key="review_plan",
        approval_intent_key="approval_intent",
        proposal_count=execution.proposal_count,
        blocked_proposal_count=execution.blocked_proposal_count,
        pending_approval_count=execution.pending_approval_count,
        proposals=_selected_proposals_response(execution.review_plan),
    )


@router.post(
    "/{space_id}/agents/graph-curation/runs",
    response_model=ClaimCurationRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one claim-curation harness run",
)
async def create_claim_curation_run(  # noqa: PLR0913
    space_id: UUID,
    request: ClaimCurationRunRequest,
    *,
    prefer: Annotated[str | None, Header()] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> ClaimCurationRunResponse:
    """Create a governed curation run that pauses for explicit approval."""
    proposal_ids = normalize_requested_proposal_ids(request.proposal_ids)
    _ = load_curatable_proposals(
        space_id=space_id,
        proposal_ids=proposal_ids,
        proposal_store=proposal_store,
    )

    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Claim Curation Harness"
    try:
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Claim curation")
        graph_health = graph_api_gateway.get_health()
        queued_run = queue_claim_curation_run(
            space_id=space_id,
            title=resolved_title,
            proposal_ids=list(proposal_ids),
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
    except ClaimCurationNoEligibleProposalsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
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
            detail="Failed to reload paused claim-curation run.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
    )
    return ClaimCurationRunResponse.model_validate(payload, strict=False)


__all__ = [
    "ClaimCurationRunRequest",
    "ClaimCurationRunResponse",
    "ClaimCurationSelectedProposalResponse",
    "build_claim_curation_run_response",
    "create_claim_curation_run",
    "router",
]
