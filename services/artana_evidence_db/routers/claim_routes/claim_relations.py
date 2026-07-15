"""Claim-to-claim relation routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_db._claim_relation_normalization import (
    normalize_relation_type as normalize_claim_relation_type,
)
from artana_evidence_db._claim_relation_normalization import (
    normalize_review_status,
)
from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_kernel_claim_relation_service,
    get_kernel_relation_claim_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.fact_assessment_support import fact_assessment_metadata
from artana_evidence_db.kernel_domain_ports import ClaimRelationConstraintError
from artana_evidence_db.kernel_services import (
    KernelClaimRelationService,
    KernelRelationClaimService,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.routers.claim_routes.write_quarantine import (
    effective_authorship_for_request,
    ensure_ai_claim_persistence_not_ready,
    ensure_claim_relation_update_not_quarantined,
    raise_ai_persistence_violation,
)
from artana_evidence_db.service_contracts import (
    ClaimRelationCreateRequest,
    ClaimRelationListResponse,
    ClaimRelationResponse,
    ClaimRelationReviewUpdateRequest,
)
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from artana_evidence_db.validation.ai_persistence_quarantine import (
    AIPersistenceQuarantineError,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

router = APIRouter()


@router.get(
    "/{space_id}/claim-relations",
    response_model=ClaimRelationListResponse,
    summary="List claim-to-claim relation edges",
)
def list_claim_relations(
    space_id: UUID,
    *,
    relation_type: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    source_claim_id: UUID | None = Query(default=None),
    target_claim_id: UUID | None = Query(default=None),
    claim_id: UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        normalized_relation_type = (
            normalize_claim_relation_type(relation_type)
            if relation_type is not None and relation_type.strip()
            else None
        )
        normalized_review_status = (
            normalize_review_status(review_status)
            if review_status is not None and review_status.strip()
            else None
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    claim_relations = claim_relation_service.list_by_research_space(
        str(space_id),
        relation_type=normalized_relation_type,
        review_status=normalized_review_status,
        source_claim_id=str(source_claim_id) if source_claim_id is not None else None,
        target_claim_id=str(target_claim_id) if target_claim_id is not None else None,
        claim_id=str(claim_id) if claim_id is not None else None,
        limit=limit,
        offset=offset,
    )
    total = claim_relation_service.count_by_research_space(
        str(space_id),
        relation_type=normalized_relation_type,
        review_status=normalized_review_status,
        source_claim_id=str(source_claim_id) if source_claim_id is not None else None,
        target_claim_id=str(target_claim_id) if target_claim_id is not None else None,
        claim_id=str(claim_id) if claim_id is not None else None,
    )
    return ClaimRelationListResponse(
        claim_relations=[
            ClaimRelationResponse.from_model(relation) for relation in claim_relations
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/claim-relations",
    response_model=ClaimRelationResponse,
    summary="Create one claim-to-claim relation edge",
)
def create_claim_relation(
    space_id: UUID,
    request: ClaimRelationCreateRequest,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )
    request = request.model_copy(
        update={
            "authorship": effective_authorship_for_request(
                current_user=current_user,
                requested_authorship=request.authorship,
            ),
        },
    )
    ensure_ai_claim_persistence_not_ready(request)
    source_claim = relation_claim_service.get_claim(str(request.source_claim_id))
    target_claim = relation_claim_service.get_claim(str(request.target_claim_id))
    if source_claim is None or str(source_claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source claim not found",
        )
    if target_claim is None or str(target_claim.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target claim not found",
        )
    try:
        confidence_metadata = fact_assessment_metadata(request.assessment)
        relation = claim_relation_service.create_claim_relation(
            research_space_id=str(space_id),
            source_claim_id=str(request.source_claim_id),
            target_claim_id=str(request.target_claim_id),
            relation_type=normalize_claim_relation_type(request.relation_type),
            agent_run_id=request.agent_run_id,
            source_document_id=(
                str(request.source_document_id)
                if request.source_document_id is not None
                else None
            ),
            source_document_ref=request.source_document_ref,
            authorship=request.authorship,
            confidence=request.derived_confidence,
            review_status=normalize_review_status(request.review_status),
            evidence_summary=request.evidence_summary,
            metadata={
                **request.metadata,
                "authorship": request.authorship,
                **confidence_metadata,
            },
        )
        session.commit()
        return ClaimRelationResponse.from_model(relation)
    except AIPersistenceQuarantineError as exc:
        session.rollback()
        raise_ai_persistence_violation(exc.violation)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ClaimRelationConstraintError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate or invalid claim relation edge",
        ) from exc


@router.patch(
    "/{space_id}/claim-relations/{relation_id}",
    response_model=ClaimRelationResponse,
    summary="Update one claim relation review status",
)
def update_claim_relation_review_status(
    space_id: UUID,
    relation_id: UUID,
    request: ClaimRelationReviewUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    claim_relation_service: KernelClaimRelationService = Depends(
        get_kernel_claim_relation_service,
    ),
    session: Session = Depends(get_session),
) -> ClaimRelationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )
    existing = claim_relation_service.get_claim_relation(str(relation_id))
    if existing is None or str(existing.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Claim relation not found",
        )
    ensure_claim_relation_update_not_quarantined(
        current_user=current_user,
        relation=existing,
    )
    try:
        updated = claim_relation_service.update_review_status(
            str(relation_id),
            review_status=normalize_review_status(request.review_status),
        )
        session.commit()
        return ClaimRelationResponse.from_model(updated)
    except AIPersistenceQuarantineError as exc:
        session.rollback()
        raise_ai_persistence_violation(exc.violation)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


__all__ = [
    "create_claim_relation",
    "list_claim_relations",
    "router",
    "update_claim_relation_review_status",
]
