"""AI Full Mode governance routes for the standalone graph service."""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID

from artana_evidence_db.ai_full_mode_service import (
    AIFullModeService,
    resolve_ai_full_source_ref,
)
from artana_evidence_db.auth import get_current_active_user, graph_ai_principal_for_user
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_ai_full_mode_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.graph_api_schemas.ai_full_mode_schemas import (
    AIDecisionListResponse,
    AIDecisionResponse,
    AIDecisionSubmitRequest,
    ConceptProposalCreateRequest,
    ConceptProposalDecisionRequest,
    ConceptProposalListResponse,
    ConceptProposalMergeRequest,
    ConceptProposalRejectRequest,
    ConceptProposalResponse,
    ConnectorProposalCreateRequest,
    ConnectorProposalListResponse,
    ConnectorProposalResponse,
    GraphChangeProposalCreateRequest,
    GraphChangeProposalListResponse,
    GraphChangeProposalResponse,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/spaces", tags=["ai-full-mode"])

ConceptProposalStatusFilter = Literal[
    "SUBMITTED",
    "DUPLICATE_CANDIDATE",
    "CHANGES_REQUESTED",
    "APPROVED",
    "REJECTED",
    "MERGED",
    "APPLIED",
]
ConnectorProposalStatusFilter = Literal[
    "SUBMITTED",
    "CHANGES_REQUESTED",
    "APPROVED",
    "REJECTED",
]
AIDecisionTargetTypeFilter = Literal["concept_proposal", "graph_change_proposal"]
GraphChangeProposalStatusFilter = Literal[
    "READY_FOR_REVIEW",
    "CHANGES_REQUESTED",
    "REJECTED",
    "APPLIED",
]


def _manual_actor(current_user: User) -> str:
    return f"manual:{current_user.id}"


def _verify_space_access(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
) -> None:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )


def _require_graph_researcher(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
) -> None:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )


def _require_graph_curator(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
) -> None:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )


def _http_400(error: ValueError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(error),
    )


def _http_phase9_error(error: ValueError) -> HTTPException:
    message = str(error)
    if "not found" in message.lower():
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=message,
        )
    return _http_400(error)


def _external_refs_payload(request: ConceptProposalCreateRequest) -> list[JSONObject]:
    return [
        cast(JSONObject, item.model_dump(mode="json"))
        for item in request.external_refs
    ]


@router.post(
    "/{space_id}/concepts/proposals",
    response_model=ConceptProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a concept without mutating official concept state",
)
def propose_concept(
    space_id: UUID,
    request: ConceptProposalCreateRequest,
    *,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConceptProposalResponse:
    _require_graph_researcher(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.propose_concept(
            research_space_id=str(space_id),
            domain_context=request.domain_context,
            entity_type=request.entity_type,
            canonical_label=request.canonical_label,
            synonyms=request.synonyms,
            external_refs=_external_refs_payload(request),
            evidence_payload=request.evidence_payload,
            rationale=request.rationale,
            proposed_by=_manual_actor(current_user),
            source_ref=resolve_ai_full_source_ref(
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
                actor=_manual_actor(current_user),
            ),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept proposal conflicts with existing idempotency scope",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise _http_400(exc) from exc
    return ConceptProposalResponse.from_model(proposal)


@router.get(
    "/{space_id}/concepts/proposals",
    response_model=ConceptProposalListResponse,
    summary="List concept proposals in one graph space",
)
def list_concept_proposals(
    space_id: UUID,
    *,
    status_filter: ConceptProposalStatusFilter | None = Query(
        default=None,
        alias="status",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConceptProposalListResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    proposals = ai_full_mode_service.list_concept_proposals(
        research_space_id=str(space_id),
        status=status_filter,
        offset=offset,
        limit=limit,
    )
    return ConceptProposalListResponse(
        concept_proposals=[
            ConceptProposalResponse.from_model(proposal) for proposal in proposals
        ],
        total=len(proposals),
    )


@router.get(
    "/{space_id}/concepts/proposals/{proposal_id}",
    response_model=ConceptProposalResponse,
    summary="Get one concept proposal",
)
def get_concept_proposal(
    space_id: UUID,
    proposal_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConceptProposalResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.get_concept_proposal(str(proposal_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if proposal.research_space_id != str(space_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return ConceptProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/concepts/proposals/{proposal_id}/approve",
    response_model=ConceptProposalResponse,
    summary="Approve a new concept proposal and create official concept records",
)
def approve_concept_proposal(
    space_id: UUID,
    proposal_id: UUID,
    request: ConceptProposalDecisionRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConceptProposalResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.approve_concept_proposal(
            str(proposal_id),
            research_space_id=str(space_id),
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_phase9_error(exc) from exc
    return ConceptProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/concepts/proposals/{proposal_id}/merge",
    response_model=ConceptProposalResponse,
    summary="Merge a concept proposal into an existing concept member",
)
def merge_concept_proposal(
    space_id: UUID,
    proposal_id: UUID,
    request: ConceptProposalMergeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConceptProposalResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.merge_concept_proposal(
            str(proposal_id),
            research_space_id=str(space_id),
            target_concept_member_id=str(request.target_concept_member_id),
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_phase9_error(exc) from exc
    return ConceptProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/concepts/proposals/{proposal_id}/reject",
    response_model=ConceptProposalResponse,
    summary="Reject a concept proposal",
)
def reject_concept_proposal(
    space_id: UUID,
    proposal_id: UUID,
    request: ConceptProposalRejectRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConceptProposalResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.reject_concept_proposal(
            str(proposal_id),
            research_space_id=str(space_id),
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_phase9_error(exc) from exc
    return ConceptProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/concepts/proposals/{proposal_id}/request-changes",
    response_model=ConceptProposalResponse,
    summary="Request changes on a concept proposal",
)
def request_concept_changes(
    space_id: UUID,
    proposal_id: UUID,
    request: ConceptProposalRejectRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConceptProposalResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.request_concept_changes(
            str(proposal_id),
            research_space_id=str(space_id),
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_phase9_error(exc) from exc
    return ConceptProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/graph-change-proposals",
    response_model=GraphChangeProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose a bundled mini-graph change",
)
def propose_graph_change(
    space_id: UUID,
    request: GraphChangeProposalCreateRequest,
    *,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> GraphChangeProposalResponse:
    _require_graph_researcher(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    payload = cast(
        JSONObject,
        request.model_dump(mode="json", exclude_none=True, exclude={"source_ref"}),
    )
    try:
        proposal = ai_full_mode_service.propose_graph_change(
            research_space_id=str(space_id),
            proposal_payload=payload,
            proposed_by=_manual_actor(current_user),
            source_ref=resolve_ai_full_source_ref(
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
                actor=_manual_actor(current_user),
            ),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_400(exc) from exc
    return GraphChangeProposalResponse.from_model(proposal)


@router.get(
    "/{space_id}/graph-change-proposals",
    response_model=GraphChangeProposalListResponse,
    summary="List graph-change proposals in one graph space",
)
def list_graph_change_proposals(
    space_id: UUID,
    *,
    status_filter: GraphChangeProposalStatusFilter | None = Query(
        default=None,
        alias="status",
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> GraphChangeProposalListResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    proposals = ai_full_mode_service.list_graph_change_proposals(
        research_space_id=str(space_id),
        status=status_filter,
        offset=offset,
        limit=limit,
    )
    return GraphChangeProposalListResponse(
        graph_change_proposals=[
            GraphChangeProposalResponse.from_model(proposal) for proposal in proposals
        ],
        total=len(proposals),
    )


@router.get(
    "/{space_id}/graph-change-proposals/{proposal_id}",
    response_model=GraphChangeProposalResponse,
    summary="Get one graph-change proposal",
)
def get_graph_change_proposal(
    space_id: UUID,
    proposal_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> GraphChangeProposalResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.get_graph_change_proposal(str(proposal_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if proposal.research_space_id != str(space_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return GraphChangeProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/graph-change-proposals/{proposal_id}/reject",
    response_model=GraphChangeProposalResponse,
    summary="Reject a graph-change proposal as one unit",
)
def reject_graph_change_proposal(
    space_id: UUID,
    proposal_id: UUID,
    request: ConceptProposalRejectRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> GraphChangeProposalResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.reject_graph_change_proposal(
            str(proposal_id),
            research_space_id=str(space_id),
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_phase9_error(exc) from exc
    return GraphChangeProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/graph-change-proposals/{proposal_id}/request-changes",
    response_model=GraphChangeProposalResponse,
    summary="Request changes on a graph-change proposal as one unit",
)
def request_graph_change_changes(
    space_id: UUID,
    proposal_id: UUID,
    request: ConceptProposalRejectRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> GraphChangeProposalResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.request_graph_change_changes(
            str(proposal_id),
            research_space_id=str(space_id),
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_phase9_error(exc) from exc
    return GraphChangeProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/ai-decisions",
    response_model=AIDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an AI decision envelope for DB policy evaluation",
)
def submit_ai_decision(
    space_id: UUID,
    request: AIDecisionSubmitRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> AIDecisionResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        decision = ai_full_mode_service.submit_ai_decision(
            research_space_id=str(space_id),
            target_type=request.target_type,
            target_id=str(request.target_id),
            action=request.action,
            ai_principal=request.ai_principal,
            authenticated_ai_principal=graph_ai_principal_for_user(current_user),
            confidence_assessment=request.confidence_assessment,
            risk_tier=request.risk_tier,
            input_hash=request.input_hash,
            evidence_payload=request.evidence_payload,
            decision_payload=request.decision_payload,
            created_by=_manual_actor(current_user),
        )
        session.commit()
    except ValueError as exc:
        session.commit()
        raise _http_phase9_error(exc) from exc
    return AIDecisionResponse.from_model(decision)


@router.get(
    "/{space_id}/ai-decisions",
    response_model=AIDecisionListResponse,
    summary="List AI decisions in one graph space",
)
def list_ai_decisions(
    space_id: UUID,
    *,
    target_type: AIDecisionTargetTypeFilter | None = Query(default=None),
    target_id: UUID | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> AIDecisionListResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    decisions = ai_full_mode_service.list_ai_decisions(
        research_space_id=str(space_id),
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
    )
    return AIDecisionListResponse(
        ai_decisions=[AIDecisionResponse.from_model(decision) for decision in decisions],
        total=len(decisions),
    )


@router.post(
    "/{space_id}/connector-proposals",
    response_model=ConnectorProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose connector metadata without executing connector runtime code",
)
def propose_connector(
    space_id: UUID,
    request: ConnectorProposalCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConnectorProposalResponse:
    _require_graph_researcher(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.propose_connector(
            research_space_id=str(space_id),
            connector_slug=request.connector_slug,
            display_name=request.display_name,
            connector_kind=request.connector_kind,
            domain_context=request.domain_context,
            metadata_payload=request.metadata_payload,
            mapping_payload=request.mapping_payload,
            rationale=request.rationale,
            evidence_payload=request.evidence_payload,
            proposed_by=_manual_actor(current_user),
            source_ref=request.source_ref,
        )
        session.commit()
    except (IntegrityError, ValueError) as exc:
        session.rollback()
        raise _http_400(ValueError(str(exc))) from exc
    return ConnectorProposalResponse.from_model(proposal)


@router.get(
    "/{space_id}/connector-proposals/{proposal_id}",
    response_model=ConnectorProposalResponse,
    summary="Get one connector metadata proposal",
)
def get_connector_proposal(
    space_id: UUID,
    proposal_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConnectorProposalResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.get_connector_proposal(str(proposal_id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if proposal.research_space_id != str(space_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return ConnectorProposalResponse.from_model(proposal)


@router.get(
    "/{space_id}/connector-proposals",
    response_model=ConnectorProposalListResponse,
    summary="List connector metadata proposals",
)
def list_connector_proposals(
    space_id: UUID,
    *,
    status_filter: ConnectorProposalStatusFilter | None = Query(
        default=None,
        alias="status",
    ),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConnectorProposalListResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    proposals = ai_full_mode_service.list_connector_proposals(
        research_space_id=str(space_id),
        status=status_filter,
    )
    return ConnectorProposalListResponse(
        connector_proposals=[
            ConnectorProposalResponse.from_model(proposal) for proposal in proposals
        ],
        total=len(proposals),
    )


@router.post(
    "/{space_id}/connector-proposals/{proposal_id}/approve",
    response_model=ConnectorProposalResponse,
    summary="Approve connector metadata without executing connector runtime code",
)
def approve_connector(
    space_id: UUID,
    proposal_id: UUID,
    request: ConceptProposalDecisionRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConnectorProposalResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.approve_connector(
            str(proposal_id),
            research_space_id=str(space_id),
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_phase9_error(exc) from exc
    return ConnectorProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/connector-proposals/{proposal_id}/reject",
    response_model=ConnectorProposalResponse,
    summary="Reject connector metadata without executing connector runtime code",
)
def reject_connector(
    space_id: UUID,
    proposal_id: UUID,
    request: ConceptProposalRejectRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConnectorProposalResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.reject_connector(
            str(proposal_id),
            research_space_id=str(space_id),
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_phase9_error(exc) from exc
    return ConnectorProposalResponse.from_model(proposal)


@router.post(
    "/{space_id}/connector-proposals/{proposal_id}/request-changes",
    response_model=ConnectorProposalResponse,
    summary="Request changes on connector metadata without running connector code",
)
def request_connector_changes(
    space_id: UUID,
    proposal_id: UUID,
    request: ConceptProposalRejectRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    ai_full_mode_service: AIFullModeService = Depends(get_ai_full_mode_service),
    session: Session = Depends(get_session),
) -> ConnectorProposalResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        proposal = ai_full_mode_service.request_connector_changes(
            str(proposal_id),
            research_space_id=str(space_id),
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise _http_phase9_error(exc) from exc
    return ConnectorProposalResponse.from_model(proposal)


__all__ = ["router"]
