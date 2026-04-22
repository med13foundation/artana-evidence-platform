"""Validation routes for side-effect-free graph and dictionary checks."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_db.auth import (
    get_current_active_user,
    to_graph_principal,
    to_graph_rls_session_context,
)
from artana_evidence_db.database import get_session, set_graph_rls_session_context
from artana_evidence_db.dependencies import (
    get_dictionary_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_provenance_service,
    get_space_access_port,
    require_space_role,
)
from artana_evidence_db.graph_access import evaluate_graph_admin_access
from artana_evidence_db.graph_validation_service import GraphValidationService
from artana_evidence_db.kernel_services import (
    KernelEntityService,
    KernelRelationClaimService,
    ProvenanceService,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.service_contracts import (
    DictionaryEntityTypeValidationRequest,
    DictionaryRelationConstraintValidationRequest,
    DictionaryRelationTypeValidationRequest,
    KernelEntityCreateRequest,
    KernelGraphValidationResponse,
    KernelObservationCreateRequest,
    KernelRelationClaimCreateRequest,
    KernelRelationTripleValidationRequest,
)
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1", tags=["validation"])


def _build_service(
    *,
    entity_service: KernelEntityService,
    dictionary_service: DictionaryPort,
    provenance_service: ProvenanceService | None = None,
    relation_claim_service: KernelRelationClaimService | None = None,
) -> GraphValidationService:
    return GraphValidationService(
        entity_service=entity_service,
        dictionary_service=dictionary_service,
        provenance_service=provenance_service,
        relation_claim_service=relation_claim_service,
    )


def _require_graph_admin(*, current_user: User, session: Session) -> None:
    if not evaluate_graph_admin_access(to_graph_principal(current_user)).allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Graph service admin access is required for this operation",
        )
    set_graph_rls_session_context(
        session,
        context=to_graph_rls_session_context(current_user, bypass_rls=True),
    )


@router.post(
    "/spaces/{space_id}/validate/entity",
    response_model=KernelGraphValidationResponse,
    summary="Validate one graph entity write without writing it",
)
def validate_entity(
    space_id: UUID,
    request: KernelEntityCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> KernelGraphValidationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )
    service = _build_service(
        entity_service=entity_service,
        dictionary_service=dictionary_service,
    )
    return service.validate_entity_write(request=request)


@router.post(
    "/spaces/{space_id}/validate/triple",
    response_model=KernelGraphValidationResponse,
    summary="Validate one graph triple without writing it",
)
def validate_triple(
    space_id: UUID,
    request: KernelRelationTripleValidationRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> KernelGraphValidationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )
    service = _build_service(
        entity_service=entity_service,
        dictionary_service=dictionary_service,
    )
    return service.validate_triple(space_id=str(space_id), request=request)


@router.post(
    "/spaces/{space_id}/validate/observation",
    response_model=KernelGraphValidationResponse,
    summary="Validate one graph observation write without writing it",
)
def validate_observation(
    space_id: UUID,
    request: KernelObservationCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    provenance_service: ProvenanceService = Depends(get_provenance_service),
    session: Session = Depends(get_session),
) -> KernelGraphValidationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )
    service = _build_service(
        entity_service=entity_service,
        dictionary_service=dictionary_service,
        provenance_service=provenance_service,
    )
    return service.validate_observation_write(space_id=str(space_id), request=request)


@router.post(
    "/spaces/{space_id}/validate/claim",
    response_model=KernelGraphValidationResponse,
    summary="Validate one graph claim request without writing it",
)
def validate_claim(
    space_id: UUID,
    request: KernelRelationClaimCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    session: Session = Depends(get_session),
) -> KernelGraphValidationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )
    service = _build_service(
        entity_service=entity_service,
        dictionary_service=dictionary_service,
        relation_claim_service=relation_claim_service,
    )
    return service.validate_claim_request(space_id=str(space_id), request=request)


@router.post(
    "/dictionary/validate/entity-type",
    response_model=KernelGraphValidationResponse,
    summary="Validate one dictionary entity type id",
)
def validate_dictionary_entity_type(
    request: DictionaryEntityTypeValidationRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> KernelGraphValidationResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _build_service(
        entity_service=entity_service,
        dictionary_service=dictionary_service,
    )
    return service.validate_entity_type(request=request)


@router.post(
    "/dictionary/validate/relation-type",
    response_model=KernelGraphValidationResponse,
    summary="Validate one dictionary relation type id",
)
def validate_dictionary_relation_type(
    request: DictionaryRelationTypeValidationRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> KernelGraphValidationResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _build_service(
        entity_service=entity_service,
        dictionary_service=dictionary_service,
    )
    return service.validate_relation_type(request=request)


@router.post(
    "/dictionary/validate/relation-constraint",
    response_model=KernelGraphValidationResponse,
    summary="Validate one dictionary relation constraint triple",
)
def validate_dictionary_relation_constraint(
    request: DictionaryRelationConstraintValidationRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> KernelGraphValidationResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _build_service(
        entity_service=entity_service,
        dictionary_service=dictionary_service,
    )
    return service.validate_relation_constraint(request=request)


__all__ = ["router"]
