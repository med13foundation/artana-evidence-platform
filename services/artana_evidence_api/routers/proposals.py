"""Proposal endpoints for the standalone harness service."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_proposal_store,
    get_run_registry,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import GraphTransportBundle  # noqa: TC001
from artana_evidence_api.proposal_actions import (
    decide_proposal,
    promote_to_graph_claim,
    promote_to_graph_entity,
    promote_to_graph_hypothesis,
    promote_to_graph_observation,
    require_proposal,
)
from artana_evidence_api.proposal_store import (  # noqa: TC001
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from artana_evidence_api.transparency import append_manual_review_decision
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(
    prefix="/v1/spaces",
    tags=["proposals"],
    dependencies=[Depends(require_harness_space_read_access)],
)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_STATUS_QUERY = Query(default=None, alias="status", min_length=1, max_length=32)
_PROPOSAL_TYPE_QUERY = Query(default=None, min_length=1, max_length=64)
_RUN_ID_QUERY = Query(default=None)
_DOCUMENT_ID_QUERY = Query(default=None)
_OFFSET_QUERY = Query(default=0, ge=0)
_LIMIT_QUERY = Query(default=200, ge=1, le=1000)


class HarnessProposalResponse(BaseModel):
    """Serialized proposal record."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    run_id: str
    proposal_type: str
    source_kind: str
    source_key: str
    document_id: str | None
    title: str
    summary: str
    status: str
    confidence: float
    ranking_score: float
    reasoning_path: JSONObject
    evidence_bundle: list[JSONObject]
    payload: JSONObject
    metadata: JSONObject
    decision_reason: str | None
    decided_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessProposalRecord) -> HarnessProposalResponse:
        """Serialize one stored proposal."""
        return cls(
            id=record.id,
            space_id=record.space_id,
            run_id=record.run_id,
            proposal_type=record.proposal_type,
            source_kind=record.source_kind,
            source_key=record.source_key,
            document_id=record.document_id,
            title=record.title,
            summary=record.summary,
            status=record.status,
            confidence=record.confidence,
            ranking_score=record.ranking_score,
            reasoning_path=record.reasoning_path,
            evidence_bundle=record.evidence_bundle,
            payload=record.payload,
            metadata=record.metadata,
            decision_reason=record.decision_reason,
            decided_at=(
                record.decided_at.isoformat() if record.decided_at is not None else None
            ),
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessProposalListResponse(BaseModel):
    """List response for proposals."""

    model_config = ConfigDict(strict=True)

    proposals: list[HarnessProposalResponse]
    total: int
    offset: int
    limit: int


class HarnessProposalDecisionRequest(BaseModel):
    """Promote or reject one proposal."""

    model_config = ConfigDict(strict=True)

    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: JSONObject = Field(default_factory=dict)


def _resolve_decision_request(
    request: HarnessProposalDecisionRequest | None,
) -> HarnessProposalDecisionRequest:
    """Return one concrete decision request, even when the body is omitted."""
    if request is not None:
        return request
    return HarnessProposalDecisionRequest()


@router.get(
    "/{space_id}/proposals",
    response_model=HarnessProposalListResponse,
    summary="List staged proposal records",
    description=(
        "Return the lower-level proposal records for one space. Most callers "
        "should start with the unified review queue when they want a single list "
        "of items that need attention."
    ),
)
def list_proposals(
    space_id: UUID,
    status_filter: str | None = _STATUS_QUERY,
    proposal_type: str | None = _PROPOSAL_TYPE_QUERY,
    run_id: UUID | None = _RUN_ID_QUERY,
    document_id: UUID | None = _DOCUMENT_ID_QUERY,
    offset: int = _OFFSET_QUERY,
    limit: int = _LIMIT_QUERY,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
) -> HarnessProposalListResponse:
    """Return proposals for one research space."""
    proposals = proposal_store.list_proposals(
        space_id=space_id,
        status=status_filter,
        proposal_type=proposal_type,
        run_id=run_id,
        document_id=document_id,
    )
    total = len(proposals)
    paged = proposals[offset : offset + limit]
    return HarnessProposalListResponse(
        proposals=[HarnessProposalResponse.from_record(proposal) for proposal in paged],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/proposals/{proposal_id}",
    response_model=HarnessProposalResponse,
    summary="Get one proposal record",
    description=(
        "Return one staged proposal with its evidence, payload, ranking, and "
        "review status. This is the direct proposal primitive behind the unified "
        "review queue."
    ),
)
def get_proposal(
    space_id: UUID,
    proposal_id: UUID,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
) -> HarnessProposalResponse:
    """Return one proposal with evidence and ranking."""
    proposal = require_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        proposal_store=proposal_store,
    )
    return HarnessProposalResponse.from_record(proposal)


@router.post(
    "/{space_id}/proposals/{proposal_id}/promote",
    response_model=HarnessProposalResponse,
    summary="Promote one approved proposal",
    description=(
        "Promote one proposal into official graph state after review. Use the "
        "review-queue action endpoint when you want the product-facing review "
        "surface; use this route when you need the raw proposal primitive."
    ),
    dependencies=[Depends(require_harness_space_write_access)],
)
def promote_proposal(  # noqa: PLR0913
    space_id: UUID,
    proposal_id: UUID,
    request: HarnessProposalDecisionRequest | None = Body(default=None),
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services=_HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> HarnessProposalResponse:
    """Promote one proposal into the reviewed state."""
    decision_request = _resolve_decision_request(request)
    proposal = require_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        proposal_store=proposal_store,
    )
    if proposal.status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Proposal '{proposal.id}' is already decided with status "
                f"'{proposal.status}'"
            ),
        )
    try:
        if proposal.proposal_type == "candidate_claim":
            promotion_metadata = promote_to_graph_claim(
                space_id=space_id,
                proposal=proposal,
                request_metadata=decision_request.metadata,
                graph_api_gateway=graph_api_gateway,
            )
            workspace_patch = {
                "last_promoted_graph_claim_id": promotion_metadata["graph_claim_id"],
                "last_promoted_graph_relation_id": promotion_metadata.get(
                    "graph_relation_id",
                ),
            }
        elif proposal.proposal_type == "mechanism_candidate":
            promotion_metadata = promote_to_graph_hypothesis(
                space_id=space_id,
                proposal=proposal,
                graph_api_gateway=graph_api_gateway,
            )
            workspace_patch = {
                "last_promoted_hypothesis_claim_id": promotion_metadata[
                    "graph_hypothesis_claim_id"
                ],
            }
        elif proposal.proposal_type == "entity_candidate":
            promotion_metadata = promote_to_graph_entity(
                space_id=space_id,
                proposal=proposal,
                graph_api_gateway=graph_api_gateway,
            )
            workspace_patch = {
                "last_promoted_graph_entity_id": promotion_metadata["graph_entity_id"],
            }
        elif proposal.proposal_type == "observation_candidate":
            promotion_metadata = promote_to_graph_observation(
                space_id=space_id,
                proposal=proposal,
                graph_api_gateway=graph_api_gateway,
            )
            workspace_patch = {
                "last_promoted_graph_observation_id": promotion_metadata[
                    "graph_observation_id"
                ],
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Proposal type '{proposal.proposal_type}' is not supported for "
                    "promotion"
                ),
            )
    finally:
        graph_api_gateway.close()
    updated = decide_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        decision_status="promoted",
        decision_reason=decision_request.reason,
        request_metadata=decision_request.metadata,
        proposal_store=proposal_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        decision_metadata=promotion_metadata,
        event_payload=promotion_metadata,
        workspace_patch=workspace_patch,
    )
    append_manual_review_decision(
        space_id=space_id,
        run_id=proposal.run_id,
        tool_name=(
            "create_manual_hypothesis"
            if proposal.proposal_type == "mechanism_candidate"
            else (
                "create_graph_entity"
                if proposal.proposal_type == "entity_candidate"
                else (
                    "create_graph_observation"
                    if proposal.proposal_type == "observation_candidate"
                    else "create_graph_claim"
                )
            )
        ),
        decision="promote",
        reason=decision_request.reason,
        artifact_key=(
            "candidate_hypothesis_pack"
            if proposal.proposal_type == "mechanism_candidate"
            else (
                "document_extraction_entities"
                if proposal.proposal_type == "entity_candidate"
                else (
                    "document_extraction_observations"
                    if proposal.proposal_type == "observation_candidate"
                    else "candidate_claim_pack"
                )
            )
        ),
        metadata={
            "proposal_id": updated.id,
            "proposal_type": proposal.proposal_type,
            **promotion_metadata,
        },
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=execution_services.runtime,
    )
    return HarnessProposalResponse.from_record(updated)


@router.post(
    "/{space_id}/proposals/{proposal_id}/reject",
    response_model=HarnessProposalResponse,
    summary="Reject one proposal",
    description=(
        "Reject one staged proposal without promoting it into graph state. Use "
        "the review-queue action endpoint when you want the unified review "
        "surface."
    ),
    dependencies=[Depends(require_harness_space_write_access)],
)
def reject_proposal(  # noqa: PLR0913
    space_id: UUID,
    proposal_id: UUID,
    request: HarnessProposalDecisionRequest | None = Body(default=None),
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    execution_services=_HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> HarnessProposalResponse:
    """Reject one proposal without touching the graph ledger."""
    decision_request = _resolve_decision_request(request)
    updated = decide_proposal(
        space_id=space_id,
        proposal_id=proposal_id,
        decision_status="rejected",
        decision_reason=decision_request.reason,
        request_metadata=decision_request.metadata,
        proposal_store=proposal_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    append_manual_review_decision(
        space_id=space_id,
        run_id=updated.run_id,
        tool_name="proposal_review",
        decision="reject",
        reason=decision_request.reason,
        artifact_key=(
            "candidate_hypothesis_pack"
            if updated.proposal_type == "mechanism_candidate"
            else "candidate_claim_pack"
        ),
        metadata={
            "proposal_id": updated.id,
            "proposal_type": updated.proposal_type,
            "status": updated.status,
        },
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=execution_services.runtime,
    )
    return HarnessProposalResponse.from_record(updated)


__all__ = [
    "HarnessProposalDecisionRequest",
    "HarnessProposalListResponse",
    "HarnessProposalResponse",
    "get_proposal",
    "list_proposals",
    "promote_proposal",
    "reject_proposal",
    "router",
]
