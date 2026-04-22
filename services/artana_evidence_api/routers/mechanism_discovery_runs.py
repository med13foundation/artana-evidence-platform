"""Harness-owned mechanism-discovery run endpoints."""

from __future__ import annotations

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
from artana_evidence_api.mechanism_discovery_runtime import (
    MechanismCandidateRecord,
    MechanismDiscoveryRunExecutionResult,
    queue_mechanism_discovery_run,
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
    tags=["mechanism-discovery-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"
_INVALID_SEED_ENTITY_ID_ERROR = "seed_entity_ids must contain valid UUID values"


class MechanismDiscoveryRunRequest(BaseModel):
    """Request payload for one harness-owned mechanism-discovery run."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] = Field(..., min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    max_candidates: int = Field(default=10, ge=1, le=50)
    max_reasoning_paths: int = Field(default=50, ge=1, le=200)
    max_path_depth: int = Field(default=4, ge=1, le=8)
    min_path_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class MechanismCandidateResponse(BaseModel):
    """One ranked mechanism candidate surfaced to the caller."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str]
    end_entity_id: str
    relation_type: str
    source_label: str | None
    target_label: str | None
    source_type: str | None
    target_type: str | None
    path_count: int
    supporting_claim_count: int
    evidence_reference_count: int
    max_path_confidence: float
    average_path_confidence: float
    average_path_length: float
    ranking_score: float
    summary: str
    hypothesis_statement: str
    hypothesis_rationale: str

    @classmethod
    def from_record(
        cls,
        record: MechanismCandidateRecord,
    ) -> MechanismCandidateResponse:
        return cls(
            seed_entity_ids=list(record.seed_entity_ids),
            end_entity_id=record.end_entity_id,
            relation_type=record.relation_type,
            source_label=record.source_label,
            target_label=record.target_label,
            source_type=record.source_type,
            target_type=record.target_type,
            path_count=len(record.path_ids),
            supporting_claim_count=len(record.supporting_claim_ids),
            evidence_reference_count=record.evidence_reference_count,
            max_path_confidence=record.max_path_confidence,
            average_path_confidence=record.average_path_confidence,
            average_path_length=record.average_path_length,
            ranking_score=record.ranking_score,
            summary=record.summary,
            hypothesis_statement=record.hypothesis_statement,
            hypothesis_rationale=record.hypothesis_rationale,
        )


class MechanismDiscoveryRunResponse(BaseModel):
    """Combined run summary and ranked mechanism candidates."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    candidates: list[MechanismCandidateResponse]
    candidate_count: int
    proposal_count: int
    scanned_path_count: int


def _normalize_seed_entity_ids(seed_entity_ids: list[str]) -> tuple[str, ...]:
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for value in seed_entity_ids:
        normalized = value.strip()
        if normalized == "":
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        try:
            UUID(normalized)
        except ValueError as exc:
            raise ValueError(_INVALID_SEED_ENTITY_ID_ERROR) from exc
        if normalized in seen_ids:
            continue
        normalized_ids.append(normalized)
        seen_ids.add(normalized)
    return tuple(normalized_ids)


def build_mechanism_discovery_run_response(
    result: MechanismDiscoveryRunExecutionResult,
) -> MechanismDiscoveryRunResponse:
    """Serialize one completed mechanism-discovery execution."""
    return MechanismDiscoveryRunResponse(
        run=HarnessRunResponse.from_record(result.run),
        candidates=[
            MechanismCandidateResponse.from_record(candidate)
            for candidate in result.candidates
        ],
        candidate_count=len(result.candidates),
        proposal_count=len(result.proposal_records),
        scanned_path_count=result.scanned_path_count,
    )


@router.post(
    "/{space_id}/agents/mechanism-discovery/runs",
    response_model=MechanismDiscoveryRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one harness-owned mechanism-discovery run",
)
async def create_mechanism_discovery_run(  # noqa: PLR0913
    space_id: UUID,
    request: MechanismDiscoveryRunRequest,
    *,
    prefer: Annotated[str | None, Header()] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> MechanismDiscoveryRunResponse:
    """Read reasoning paths, rank converging mechanisms, and stage hypotheses."""
    try:
        seed_entity_ids = _normalize_seed_entity_ids(request.seed_entity_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Mechanism Discovery Run"
    try:
        if should_require_worker_ready(execution_services=execution_services):
            require_worker_ready(operation_name="Mechanism discovery")
        graph_health = graph_api_gateway.get_health()
        queued_run = queue_mechanism_discovery_run(
            space_id=space_id,
            title=resolved_title,
            seed_entity_ids=seed_entity_ids,
            max_candidates=request.max_candidates,
            max_reasoning_paths=request.max_reasoning_paths,
            max_path_depth=request.max_path_depth,
            min_path_confidence=request.min_path_confidence,
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
        detail = exc.detail or str(exc)
        raise HTTPException(
            status_code=exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
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
            detail="Failed to reload completed mechanism-discovery run.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=queued_run.id,
    )
    return MechanismDiscoveryRunResponse.model_validate(payload, strict=False)


__all__ = [
    "MechanismCandidateResponse",
    "MechanismDiscoveryRunRequest",
    "MechanismDiscoveryRunResponse",
    "build_mechanism_discovery_run_response",
    "create_mechanism_discovery_run",
    "router",
]
