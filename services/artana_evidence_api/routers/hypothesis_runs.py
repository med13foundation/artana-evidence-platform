"""Harness-owned hypothesis exploration run endpoints."""

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
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
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
from artana_evidence_api.ranking import rank_candidate_claim
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.transparency import (
    ensure_run_transparency_seed,
)
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from artana_evidence_api.agent_contracts import (
        GraphConnectionContract,
        ProposedRelation,
    )
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.harness_runtime import HarnessExecutionServices
    from artana_evidence_api.run_registry import HarnessRunRegistry
    from artana_evidence_api.types.common import JSONObject

router = APIRouter(
    prefix="/v1/spaces",
    tags=["hypothesis-runs"],
    dependencies=[Depends(require_harness_space_write_access)],
)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)

_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"


class HypothesisRunRequest(BaseModel):
    """Request payload for one harness-owned hypothesis exploration run."""

    model_config = ConfigDict(strict=True)

    seed_entity_ids: list[str] | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=256)
    source_type: str = Field(default="pubmed", min_length=1, max_length=64)
    relation_types: list[str] | None = Field(default=None, max_length=200)
    max_depth: int = Field(default=2, ge=1, le=4)
    max_hypotheses: int = Field(default=20, ge=1, le=100)
    model_id: str | None = Field(default=None, min_length=1, max_length=128)


class HypothesisCandidateResponse(BaseModel):
    """One hypothesis candidate staged by the harness layer."""

    model_config = ConfigDict(strict=True)

    seed_entity_id: str
    source_entity_id: str
    relation_type: str
    target_entity_id: str
    confidence: float
    evidence_summary: str
    reasoning: str
    agent_run_id: str | None = None
    source_type: str

    @classmethod
    def from_relation(
        cls,
        *,
        seed_entity_id: str,
        relation: ProposedRelation,
        agent_run_id: str | None,
        source_type: str,
    ) -> HypothesisCandidateResponse:
        """Build one candidate response from a proposed relation."""
        return cls(
            seed_entity_id=seed_entity_id,
            source_entity_id=relation.source_id,
            relation_type=relation.relation_type,
            target_entity_id=relation.target_id,
            confidence=relation.confidence,
            evidence_summary=relation.evidence_summary,
            reasoning=relation.reasoning,
            agent_run_id=agent_run_id,
            source_type=source_type,
        )


class HypothesisRunResponse(BaseModel):
    """Combined run and staged hypothesis candidates."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    candidates: list[HypothesisCandidateResponse]
    candidate_count: int
    errors: list[str]


def _normalize_seed_entity_ids(seed_entity_ids: list[str] | None) -> list[str]:
    if seed_entity_ids is None:
        return []
    normalized_ids: list[str] = []
    for value in seed_entity_ids:
        normalized = value.strip()
        if not normalized:
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        normalized_ids.append(normalized)
    return normalized_ids


def _collect_candidates(
    outcomes: list[GraphConnectionContract],
    *,
    max_hypotheses: int,
) -> tuple[list[HypothesisCandidateResponse], list[str]]:
    candidates: list[HypothesisCandidateResponse] = []
    errors: list[str] = []
    for outcome in outcomes:
        if outcome.decision != "generated" and not outcome.proposed_relations:
            errors.append(
                f"seed:{outcome.seed_entity_id}:no_generated_relations:{outcome.decision}",
            )
        for relation in outcome.proposed_relations:
            if len(candidates) >= max_hypotheses:
                break
            candidates.append(
                HypothesisCandidateResponse.from_relation(
                    seed_entity_id=outcome.seed_entity_id,
                    relation=relation,
                    agent_run_id=outcome.agent_run_id,
                    source_type=outcome.source_type,
                ),
            )
    return candidates, errors


def _build_candidate_claim_proposals(
    outcomes: list[GraphConnectionContract],
    *,
    max_hypotheses: int,
) -> tuple[HarnessProposalDraft, ...]:
    proposals: list[HarnessProposalDraft] = []
    for outcome in outcomes:
        for relation in outcome.proposed_relations:
            if len(proposals) >= max_hypotheses:
                break
            ranking = rank_candidate_claim(
                confidence=relation.confidence,
                supporting_document_count=relation.supporting_document_count,
                evidence_reference_count=len(relation.supporting_provenance_ids),
            )
            evidence_bundle: list[JSONObject] = [
                evidence.model_dump(mode="json") for evidence in outcome.evidence
            ]
            evidence_bundle.append(
                {
                    "source_type": "hypothesis_relation",
                    "locator": (
                        f"{relation.source_id}:{relation.relation_type}:{relation.target_id}"
                    ),
                    "excerpt": relation.evidence_summary,
                    "relevance": relation.confidence,
                },
            )
            proposals.append(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="hypothesis_run",
                    source_key=(
                        f"{outcome.seed_entity_id}:{relation.source_id}:"
                        f"{relation.relation_type}:{relation.target_id}"
                    ),
                    title=(
                        f"Candidate claim: {relation.source_id} "
                        f"{relation.relation_type} {relation.target_id}"
                    ),
                    summary=relation.evidence_summary,
                    confidence=relation.confidence,
                    ranking_score=ranking.score,
                    reasoning_path={
                        "seed_entity_id": outcome.seed_entity_id,
                        "source_entity_id": relation.source_id,
                        "relation_type": relation.relation_type,
                        "target_entity_id": relation.target_id,
                        "reasoning": relation.reasoning,
                        "agent_run_id": outcome.agent_run_id,
                    },
                    evidence_bundle=evidence_bundle,
                    payload={
                        "proposed_claim_type": relation.relation_type,
                        "proposed_subject": relation.source_id,
                        "proposed_object": relation.target_id,
                        "evidence_tier": relation.evidence_tier,
                        "supporting_document_count": relation.supporting_document_count,
                        "supporting_provenance_ids": relation.supporting_provenance_ids,
                    },
                    metadata={
                        "seed_entity_id": outcome.seed_entity_id,
                        "agent_run_id": outcome.agent_run_id,
                        "source_type": outcome.source_type,
                        **ranking.metadata,
                    },
                ),
            )
    return tuple(proposals)


def _proposal_artifact_payload(
    proposals: list[HarnessProposalRecord],
) -> JSONObject:
    return {
        "proposal_count": len(proposals),
        "proposal_ids": [proposal.id for proposal in proposals],
        "proposals": [
            {
                "id": proposal.id,
                "run_id": proposal.run_id,
                "proposal_type": proposal.proposal_type,
                "source_kind": proposal.source_kind,
                "source_key": proposal.source_key,
                "title": proposal.title,
                "summary": proposal.summary,
                "status": proposal.status,
                "confidence": proposal.confidence,
                "ranking_score": proposal.ranking_score,
                "payload": proposal.payload,
                "metadata": proposal.metadata,
                "created_at": proposal.created_at.isoformat(),
            }
            for proposal in proposals
        ],
    }


@router.post(
    "/{space_id}/agents/hypotheses/runs",
    response_model=HypothesisRunResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": HarnessAcceptedRunResponse}},
    summary="Start one harness-owned hypothesis exploration run",
)
async def create_hypothesis_run(  # noqa: PLR0913
    space_id: UUID,
    request: HypothesisRunRequest,
    *,
    prefer: Annotated[str | None, Header()] = None,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services: HarnessExecutionServices = _HARNESS_EXECUTION_SERVICES_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> HypothesisRunResponse:
    """Run hypothesis exploration in the harness layer and stage candidates."""
    try:
        seed_entity_ids = _normalize_seed_entity_ids(request.seed_entity_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if not seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one seed_entity_id is required for harness hypothesis runs",
        )

    resolved_title = (
        request.title.strip() if isinstance(request.title, str) else ""
    ) or "Hypothesis Exploration Run"
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
        "relation_types": request.relation_types or [],
        "max_depth": request.max_depth,
        "max_hypotheses": request.max_hypotheses,
        "model_id": request.model_id,
    }
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="hypotheses",
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
        require_worker_ready(operation_name="Hypothesis")
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
            detail=f"Failed to reload completed hypothesis run '{run.id}'.",
        )
    if wait_outcome.run.status == "failed":
        raise_for_failed_run(run=wait_outcome.run, artifact_store=artifact_store)
    payload = load_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
    )
    return HypothesisRunResponse.model_validate(payload, strict=False)


__all__ = [
    "HypothesisCandidateResponse",
    "HypothesisRunRequest",
    "HypothesisRunResponse",
    "create_hypothesis_run",
    "router",
]
