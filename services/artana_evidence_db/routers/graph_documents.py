"""Unified graph document and export routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.claim_metrics import (
    emit_graph_filter_preset_usage,
)
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_kernel_claim_evidence_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_source_service,
    get_kernel_relation_service,
    get_space_access_port,
    verify_space_membership,
)
from artana_evidence_db.graph_document_builder import build_kernel_graph_document
from artana_evidence_db.kernel_services import (
    KernelClaimEvidenceService,
    KernelClaimParticipantService,
    KernelEntityService,
    KernelRelationClaimService,
    KernelRelationProjectionSourceService,
    KernelRelationService,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.service_contracts import (
    KernelEntityResponse,
    KernelGraphDocumentRequest,
    KernelGraphDocumentResponse,
    KernelGraphExportResponse,
    KernelRelationResponse,
)
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/spaces", tags=["graph-documents"])


@router.get(
    "/{space_id}/graph/export",
    response_model=KernelGraphExportResponse,
    summary="Export canonical graph nodes and edges",
)
def export_graph(
    space_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelGraphExportResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    relations = relation_service.list_by_research_space(str(space_id))
    entity_ids: set[str] = set()
    for relation in relations:
        entity_ids.add(str(relation.source_id))
        entity_ids.add(str(relation.target_id))

    nodes: list[KernelEntityResponse] = []
    for entity_id in entity_ids:
        entity = entity_service.get_entity(entity_id)
        if entity is None or str(entity.research_space_id) != str(space_id):
            continue
        nodes.append(KernelEntityResponse.from_model(entity))

    return KernelGraphExportResponse(
        nodes=nodes,
        edges=[KernelRelationResponse.from_model(relation) for relation in relations],
    )


@router.post(
    "/{space_id}/graph/document",
    response_model=KernelGraphDocumentResponse,
    summary="Build one unified graph document with claim and evidence overlays",
)
def get_graph_document(
    space_id: UUID,
    request: KernelGraphDocumentRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    relation_projection_source_service: KernelRelationProjectionSourceService = Depends(
        get_kernel_relation_projection_source_service,
    ),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
    session: Session = Depends(get_session),
) -> KernelGraphDocumentResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    emit_graph_filter_preset_usage(
        endpoint="graph_document",
        curation_statuses=request.curation_statuses,
    )
    if request.mode == "starter" and request.seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids must be empty when mode='starter'.",
        )
    if request.mode == "seeded" and not request.seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids is required when mode='seeded'.",
        )
    try:
        return build_kernel_graph_document(
            space_id=str(space_id),
            request=request,
            entity_service=entity_service,
            relation_service=relation_service,
            relation_claim_service=relation_claim_service,
            relation_projection_source_service=relation_projection_source_service,
            claim_participant_service=claim_participant_service,
            claim_evidence_service=claim_evidence_service,
            session=session,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


__all__ = ["export_graph", "get_graph_document", "router"]
