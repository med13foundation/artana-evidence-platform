"""Queue-oriented research initialization endpoint and shared helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.auth import (
    HarnessUser,
    HarnessUserRole,
    get_current_harness_user,
)
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_identity_gateway,
    get_run_registry,
    require_harness_space_write_access,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    queue_full_ai_orchestrator_run,
    resolve_guarded_rollout_profile,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    store_pubmed_replay_bundle_artifact as store_full_ai_pubmed_replay_bundle_artifact,
)
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.queued_run import wake_worker_for_queued_run
from artana_evidence_api.research_init_helpers import (
    ResearchInitOrchestrationMode,
    _build_pubmed_queries,
    _build_scope_refinement_questions,
    _candidate_key,
    _merge_candidate,
    _planner_mode_for_research_orchestration,
    _prioritize_marrvel_gene_labels,
    _PubMedCandidate,
    _PubMedCandidateReview,
    _require_worker_ready,
    _resolve_research_init_sources,
    _resolve_research_orchestration_mode,
    _review_candidate_with_heuristics,
    _review_candidate_with_llm,
    _run_marrvel_enrichment,
    _select_candidates_for_ingestion,
    _shortlist_candidates_for_llm_review,
    _unknown_source_preference_keys,
)
from artana_evidence_api.research_init_runtime import (
    deserialize_pubmed_replay_bundle,
    prepare_pubmed_replay_bundle,
    queue_research_init_run,
    store_pubmed_replay_bundle_artifact,
)
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.source_registry import research_plan_source_keys
from artana_evidence_api.types.common import (  # noqa: TC001
    JSONObject,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.identity.contracts import IdentityGateway
    from artana_evidence_api.run_registry import HarnessRunRegistry

router = APIRouter(
    prefix="/v1/spaces",
    tags=["research-init"],
    dependencies=[Depends(require_harness_space_write_access)],
)
LOGGER = logging.getLogger(__name__)
_RUN_PROGRESS_PATH_TEMPLATE = "/v1/spaces/{space_id}/runs/{run_id}/progress"


class ResearchInitRequest(BaseModel):
    """Request for orchestrated research initialization."""

    model_config = ConfigDict(strict=True)

    objective: str = Field(..., min_length=1, max_length=4000)
    seed_terms: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Human-readable seed terms (gene names, drug names, concepts). NOT UUIDs.",
    )
    title: str | None = Field(default=None, min_length=1, max_length=256)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_hypotheses: int = Field(default=20, ge=1, le=100)
    sources: dict[str, bool] | None = Field(
        default=None,
        description="Enabled data sources. Keys: pubmed, marrvel, clinvar, mondo, pdf, text, drugbank, alphafold, uniprot, hgnc, clinical_trials, mgi, zfin.",
    )
    orchestration_mode: ResearchInitOrchestrationMode | None = Field(
        default=None,
        description=(
            "Optional research execution shell. Defaults to full_ai_guarded "
            "with guarded_source_chase. Use deterministic to route this kickoff "
            "through the baseline scripted research-init runtime."
        ),
    )
    guarded_rollout_profile: FullAIOrchestratorGuardedRolloutProfile | None = Field(
        default=None,
        strict=False,
        description=(
            "Optional per-run guarded authority profile. Only applies when "
            "orchestration_mode resolves to full_ai_guarded."
        ),
    )
    pubmed_replay_bundle: JSONObject | None = Field(
        default=None,
        description=(
            "Internal/testing only. Reuse one precomputed PubMed replay bundle "
            "so multiple runs can share the exact same candidate selection."
        ),
    )

    @field_validator("guarded_rollout_profile", mode="before")
    @classmethod
    def _coerce_guarded_rollout_profile(
        cls,
        value: object,
    ) -> FullAIOrchestratorGuardedRolloutProfile | object:
        if isinstance(value, str):
            return FullAIOrchestratorGuardedRolloutProfile(value)
        return value


class ResearchInitPubMedResult(BaseModel):
    """Summary of PubMed search results."""

    model_config = ConfigDict(strict=True)

    query: str
    total_found: int
    abstracts_ingested: int


class ResearchInitResponse(BaseModel):
    """Response from orchestrated research initialization."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    poll_url: str = Field(
        ...,
        min_length=1,
        description=(
            "Relative URL for polling the run progress endpoint until the "
            "queued research-init work completes."
        ),
    )
    pubmed_results: list[ResearchInitPubMedResult]
    documents_ingested: int
    proposal_count: int
    research_state: JSONObject | None
    pending_questions: list[str]
    errors: list[str]


def _build_run_progress_url(*, space_id: UUID, run_id: UUID) -> str:
    return _RUN_PROGRESS_PATH_TEMPLATE.format(space_id=space_id, run_id=run_id)


@router.post(
    "/{space_id}/research-init",
    response_model=ResearchInitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initialize a research space from natural language",
    description=(
        "Queues research-init work and returns immediately. The response "
        "includes a `poll_url` for the run progress endpoint, which callers "
        "should poll to observe async completion."
    ),
)
async def create_research_init(  # noqa: PLR0913, PLR0915
    space_id: UUID,
    request: ResearchInitRequest,
    *,
    run_registry: HarnessRunRegistry = Depends(get_run_registry),
    artifact_store: HarnessArtifactStore = Depends(get_artifact_store),
    graph_api_gateway: GraphTransportBundle = Depends(get_graph_api_gateway),
    execution_services: HarnessExecutionServices = Depends(
        get_harness_execution_services,
    ),
    current_user: HarnessUser = Depends(get_current_harness_user),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> ResearchInitResponse:
    """Queue a research-init run and return immediately."""
    space_record = identity_gateway.get_space(
        space_id=space_id,
        user_id=current_user.id,
        is_admin=current_user.role == HarnessUserRole.ADMIN,
    )
    sources = _resolve_research_init_sources(
        request_sources=request.sources,
        space_settings=space_record.settings if space_record is not None else None,
    )
    unknown_sources = _unknown_source_preference_keys(request.sources)
    if unknown_sources:
        supported_sources = ", ".join(research_plan_source_keys())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unknown research source(s): "
                f"{', '.join(unknown_sources)}. Supported sources: {supported_sources}."
            ),
        )
    orchestration_mode = _resolve_research_orchestration_mode(
        request_mode=request.orchestration_mode,
        space_settings=space_record.settings if space_record is not None else None,
    )
    replay_bundle = None

    try:
        _require_worker_ready()
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
                    objective=request.objective,
                    seed_terms=list(request.seed_terms),
                )
        title = (request.title or "").strip() or "Research Init Bootstrap"
        planner_mode = _planner_mode_for_research_orchestration(orchestration_mode)
        if planner_mode is None:
            queued_run = queue_research_init_run(
                space_id=space_id,
                title=title,
                objective=request.objective,
                seed_terms=list(request.seed_terms),
                sources=sources,
                max_depth=request.max_depth,
                max_hypotheses=request.max_hypotheses,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
                run_registry=run_registry,
                artifact_store=artifact_store,
                execution_services=execution_services,
            )
        else:
            guarded_rollout_profile, guarded_rollout_profile_source = (
                resolve_guarded_rollout_profile(
                    planner_mode=planner_mode,
                    request_profile=request.guarded_rollout_profile,
                    space_settings=(
                        space_record.settings if space_record is not None else None
                    ),
                )
            )
            queued_run = queue_full_ai_orchestrator_run(
                space_id=space_id,
                title=title,
                objective=request.objective,
                seed_terms=list(request.seed_terms),
                sources=sources,
                planner_mode=planner_mode,
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
            store_replay_bundle = (
                store_pubmed_replay_bundle_artifact
                if planner_mode is None
                else store_full_ai_pubmed_replay_bundle_artifact
            )
            store_replay_bundle(
                artifact_store=artifact_store,
                space_id=space_id,
                run_id=queued_run.id,
                replay_bundle=replay_bundle,
            )
        wake_worker_for_queued_run(run=queued_run)
        return ResearchInitResponse(
            run=HarnessRunResponse.from_record(queued_run),
            poll_url=_build_run_progress_url(
                space_id=space_id,
                run_id=UUID(queued_run.id),
            ),
            pubmed_results=[],
            documents_ingested=0,
            proposal_count=0,
            research_state=None,
            pending_questions=[],
            errors=[],
        )

    except HTTPException:
        raise
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    except Exception as exc:
        LOGGER.exception(
            "research-init request failed",
            extra={
                "space_id": str(space_id),
                "user_id": str(current_user.id),
                "title": request.title,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Research initialization failed: {exc}",
        ) from exc


__all__ = [
    "ResearchInitOrchestrationMode",
    "ResearchInitPubMedResult",
    "ResearchInitRequest",
    "ResearchInitResponse",
    "_PubMedCandidate",
    "_PubMedCandidateReview",
    "_build_pubmed_queries",
    "_build_scope_refinement_questions",
    "_candidate_key",
    "_merge_candidate",
    "_planner_mode_for_research_orchestration",
    "_prioritize_marrvel_gene_labels",
    "_require_worker_ready",
    "_resolve_research_init_sources",
    "_resolve_research_orchestration_mode",
    "_review_candidate_with_heuristics",
    "_review_candidate_with_llm",
    "_run_marrvel_enrichment",
    "_select_candidates_for_ingestion",
    "_shortlist_candidates_for_llm_review",
    "create_research_init",
    "router",
]
