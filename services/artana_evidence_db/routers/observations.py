"""Observation routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_dictionary_service,
    get_kernel_entity_service,
    get_kernel_observation_service,
    get_provenance_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.graph_validation_service import GraphValidationService
from artana_evidence_db.kernel_services import (
    KernelEntityService,
    KernelObservationService,
    ProvenanceService,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.service_contracts import (
    KernelObservationCreateRequest,
    KernelObservationListResponse,
    KernelObservationResponse,
)
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/spaces", tags=["observations"])

def _build_validation_error_detail(validation: object) -> dict[str, object]:
    next_actions = getattr(validation, "next_actions", [])
    serialized_next_actions = [
        action.model_dump(mode="json") for action in next_actions
    ]
    return {
        "code": getattr(validation, "code", "validation_failed"),
        "message": getattr(validation, "message", "Observation validation failed."),
        "severity": getattr(validation, "severity", "blocking"),
        "validation_state": getattr(validation, "validation_state", None),
        "persistability": getattr(validation, "persistability", None),
        "next_actions": serialized_next_actions,
    }


@router.post(
    "/{space_id}/observations",
    response_model=KernelObservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record one observation",
)
def create_observation(
    space_id: UUID,
    request: KernelObservationCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    observation_service: KernelObservationService = Depends(
        get_kernel_observation_service,
    ),
    provenance_service: ProvenanceService = Depends(get_provenance_service),
    session: Session = Depends(get_session),
) -> KernelObservationResponse:
    """Record one observation in one graph space."""
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )

    validation_service = GraphValidationService(
        entity_service=entity_service,
        dictionary_service=dictionary_service,
        provenance_service=provenance_service,
    )
    validation = validation_service.validate_observation_write(
        space_id=str(space_id),
        request=request,
    )
    if not validation.valid or validation.persistability != "PERSISTABLE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_build_validation_error_detail(validation),
        )

    try:
        observation = observation_service.record_observation_value(
            research_space_id=str(space_id),
            subject_id=str(request.subject_id),
            variable_id=request.variable_id,
            value=request.value,
            unit=request.unit,
            observed_at=request.observed_at,
            provenance_id=(
                str(request.provenance_id) if request.provenance_id else None
            ),
            confidence=request.confidence,
        )
        session.commit()
        return KernelObservationResponse.from_model(observation)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record observation: {exc!s}",
        ) from exc


@router.get(
    "/{space_id}/observations",
    response_model=KernelObservationListResponse,
    summary="List observations",
)
def list_observations(
    space_id: UUID,
    *,
    subject_id: UUID | None = Query(default=None),
    variable_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    observation_service: KernelObservationService = Depends(
        get_kernel_observation_service,
    ),
    session: Session = Depends(get_session),
) -> KernelObservationListResponse:
    """List observations in one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    if subject_id is not None:
        subject = entity_service.get_entity(str(subject_id))
        if subject is None or str(subject.research_space_id) != str(space_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Subject entity not found",
            )
        observations = observation_service.get_subject_observations(
            str(subject_id),
            variable_id=variable_id,
            limit=limit,
            offset=offset,
        )
    else:
        observations = observation_service.get_research_space_observations(
            str(space_id),
            limit=limit,
            offset=offset,
        )

    return KernelObservationListResponse(
        observations=[
            KernelObservationResponse.from_model(observation)
            for observation in observations
        ],
        total=len(observations),
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/observations/{observation_id}",
    response_model=KernelObservationResponse,
    summary="Get one observation",
)
def get_observation(
    space_id: UUID,
    observation_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    observation_service: KernelObservationService = Depends(
        get_kernel_observation_service,
    ),
    session: Session = Depends(get_session),
) -> KernelObservationResponse:
    """Get one observation in one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    observation = observation_service.get_observation(str(observation_id))
    if observation is None or str(observation.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Observation not found",
        )

    return KernelObservationResponse.from_model(observation)


__all__ = ["router", "create_observation", "get_observation", "list_observations"]
