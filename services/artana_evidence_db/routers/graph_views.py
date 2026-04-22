"""Graph-view routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_graph_view_extension,
    get_kernel_graph_view_service,
    get_space_access_port,
    verify_space_membership,
)
from artana_evidence_db.graph_domain_config import GraphViewExtension
from artana_evidence_db.kernel_services import (
    KernelGraphViewNotFoundError,
    KernelGraphViewService,
    KernelGraphViewValidationError,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.service_contracts import (
    KernelClaimMechanismChainResponse,
    KernelGraphDomainViewResponse,
)
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/spaces", tags=["graph-views"])


@router.get(
    "/{space_id}/graph/views/{view_type}/{resource_id}",
    response_model=KernelGraphDomainViewResponse,
    summary="Build one claim-aware domain view",
)
def get_graph_domain_view(
    space_id: UUID,
    view_type: str,
    resource_id: UUID,
    *,
    claim_limit: int = Query(default=50, ge=1, le=200),
    relation_limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    graph_view_extension: GraphViewExtension = Depends(get_graph_view_extension),
    graph_view_service: KernelGraphViewService = Depends(get_kernel_graph_view_service),
    session: Session = Depends(get_session),
) -> KernelGraphDomainViewResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        normalized_view_type = graph_view_extension.normalize_view_type(view_type)
        domain_view = graph_view_service.build_domain_view(
            research_space_id=str(space_id),
            view_type=normalized_view_type,
            resource_id=str(resource_id),
            claim_limit=claim_limit,
            relation_limit=relation_limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except KernelGraphViewValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except KernelGraphViewNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return KernelGraphDomainViewResponse.from_domain_view(domain_view)


@router.get(
    "/{space_id}/claims/{claim_id}/mechanism-chain",
    response_model=KernelClaimMechanismChainResponse,
    summary="Traverse a mechanism-style claim chain",
)
def get_claim_mechanism_chain(
    space_id: UUID,
    claim_id: UUID,
    *,
    max_depth: int = Query(default=3, ge=1, le=6),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    graph_view_service: KernelGraphViewService = Depends(get_kernel_graph_view_service),
    session: Session = Depends(get_session),
) -> KernelClaimMechanismChainResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        chain = graph_view_service.build_mechanism_chain(
            research_space_id=str(space_id),
            claim_id=str(claim_id),
            max_depth=max_depth,
        )
    except KernelGraphViewValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except KernelGraphViewNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return KernelClaimMechanismChainResponse.from_chain(chain)


__all__ = ["get_claim_mechanism_chain", "get_graph_domain_view", "router"]
