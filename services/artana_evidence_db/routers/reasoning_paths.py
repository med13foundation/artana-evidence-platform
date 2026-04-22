"""Reasoning-path read routes for the standalone graph service."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_kernel_reasoning_path_service,
    get_space_access_port,
    verify_space_membership,
)
from artana_evidence_db.kernel_services import KernelReasoningPathService
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.service_contracts import (
    KernelReasoningPathDetailResponse,
    KernelReasoningPathListResponse,
    KernelReasoningPathResponse,
)
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/spaces", tags=["reasoning-paths"])

_ReasoningPathStatus = Literal["ACTIVE", "STALE"]
_ReasoningPathKind = Literal["MECHANISM"]


@router.get(
    "/{space_id}/reasoning-paths",
    response_model=KernelReasoningPathListResponse,
    summary="List derived reasoning paths in one graph space",
)
def list_reasoning_paths(
    space_id: UUID,
    *,
    start_entity_id: UUID | None = Query(default=None),
    end_entity_id: UUID | None = Query(default=None),
    status_filter: _ReasoningPathStatus | None = Query(default=None, alias="status"),
    path_kind: _ReasoningPathKind | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> KernelReasoningPathListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    result = reasoning_path_service.list_paths(
        research_space_id=str(space_id),
        start_entity_id=str(start_entity_id) if start_entity_id is not None else None,
        end_entity_id=str(end_entity_id) if end_entity_id is not None else None,
        status=status_filter,
        path_kind=path_kind,
        limit=limit,
        offset=offset,
    )
    return KernelReasoningPathListResponse(
        paths=[KernelReasoningPathResponse.from_model(path) for path in result.paths],
        total=result.total,
        offset=result.offset,
        limit=result.limit,
    )


@router.get(
    "/{space_id}/reasoning-paths/{path_id}",
    response_model=KernelReasoningPathDetailResponse,
    summary="Retrieve one explained reasoning path",
)
def get_reasoning_path(
    space_id: UUID,
    path_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    reasoning_path_service: KernelReasoningPathService = Depends(
        get_kernel_reasoning_path_service,
    ),
    session: Session = Depends(get_session),
) -> KernelReasoningPathDetailResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    detail = reasoning_path_service.get_path(str(path_id), str(space_id))
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Reasoning path {path_id} not found",
        )
    return KernelReasoningPathDetailResponse.from_detail(detail)


__all__ = ["get_reasoning_path", "list_reasoning_paths", "router"]
