"""Dictionary transform-registry routes for the standalone graph service."""

from __future__ import annotations

from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import get_dictionary_service
from artana_evidence_db.dictionary_router_support import (
    _manual_actor,
    _require_graph_admin,
)
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.service_contracts import (
    TransformRegistryListResponse,
    TransformRegistryResponse,
    TransformVerificationResponse,
)
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/dictionary", tags=["dictionary"])


@router.get(
    "/transforms",
    response_model=TransformRegistryListResponse,
    summary="List graph dictionary transforms",
)
def list_transform_registry(
    *,
    status_filter: str = Query("ACTIVE", alias="status"),
    include_inactive: bool = Query(False),
    production_only: bool = Query(False),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> TransformRegistryListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    transforms = dictionary_service.list_transforms(
        status=status_filter,
        include_inactive=include_inactive,
        production_only=production_only,
    )
    return TransformRegistryListResponse(
        transforms=[
            TransformRegistryResponse.from_model(transform) for transform in transforms
        ],
        total=len(transforms),
    )


@router.post(
    "/transforms/{transform_id}/verify",
    response_model=TransformVerificationResponse,
    summary="Run transform fixture verification",
)
def verify_transform_registry_entry(
    transform_id: str,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> TransformVerificationResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        verification = dictionary_service.verify_transform(transform_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return TransformVerificationResponse.from_model(verification)


@router.patch(
    "/transforms/{transform_id}/promote",
    response_model=TransformRegistryResponse,
    summary="Promote one graph dictionary transform to production use",
)
def promote_transform_registry_entry(
    transform_id: str,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> TransformRegistryResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        transform = dictionary_service.promote_transform(
            transform_id,
            reviewed_by=_manual_actor(current_user),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return TransformRegistryResponse.from_model(transform)


__all__ = ["router"]
