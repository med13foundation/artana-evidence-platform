"""Graph explorer endpoints for the standalone harness service."""

from __future__ import annotations

import json
from uuid import UUID  # noqa: TC003

from artana_evidence_api.dependencies import (
    get_graph_api_gateway,
    require_harness_space_read_access,
)
from artana_evidence_api.graph_client import (
    _SEEDED_GRAPH_DOCUMENT_SEEDS_REQUIRED_DETAIL,
    GraphServiceClientError,
    GraphTransportBundle,  # noqa: TC001
)
from artana_evidence_api.types.graph_contracts import (
    KernelClaimEvidenceListResponse,
    KernelEntityListResponse,
    KernelGraphDocumentRequest,  # noqa: TC001
    KernelGraphDocumentResponse,
    KernelRelationClaimListResponse,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status

router = APIRouter(
    prefix="/v1/spaces",
    tags=["graph-explorer"],
    dependencies=[Depends(require_harness_space_read_access)],
)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_UPSTREAM_SERVER_ERROR_STATUS = 500


def _graph_api_error_status(error: GraphServiceClientError) -> int:
    if error.status_code is None or error.status_code >= _UPSTREAM_SERVER_ERROR_STATUS:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return error.status_code


def _graph_api_error_detail(error: GraphServiceClientError) -> str:
    raw_detail = error.detail
    if isinstance(raw_detail, str):
        stripped = raw_detail.strip()
        if stripped == "":
            return str(error)
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        if isinstance(parsed, dict):
            detail_value = parsed.get("detail")
            if isinstance(detail_value, str) and detail_value.strip() != "":
                return detail_value.strip()
        return stripped
    return str(error)


def _raise_graph_api_error(error: GraphServiceClientError) -> None:
    raise HTTPException(
        status_code=_graph_api_error_status(error),
        detail=_graph_api_error_detail(error),
    ) from error


@router.get(
    "/{space_id}/graph-explorer/claims",
    response_model=KernelRelationClaimListResponse,
    summary="List graph claims",
)
def list_claims(
    space_id: UUID,
    claim_status: str | None = Query(default=None, max_length=32),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    *,
    gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> KernelRelationClaimListResponse:
    """Return relation claims for one research space."""
    try:
        return gateway.list_claims(
            space_id=space_id,
            claim_status=claim_status,
            offset=offset,
            limit=limit,
        )
    except GraphServiceClientError as exc:
        _raise_graph_api_error(exc)


@router.get(
    "/{space_id}/graph-explorer/entities",
    response_model=KernelEntityListResponse,
    summary="List graph entities",
)
def list_entities(
    space_id: UUID,
    q: str | None = Query(default=None, max_length=256),
    entity_type: str | None = Query(default=None, max_length=64),
    ids: str | None = Query(default=None, max_length=4000),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    *,
    gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> KernelEntityListResponse:
    """Return entities for one research space with optional search/filter."""
    try:
        parsed_ids = [s.strip() for s in ids.split(",") if s.strip()] if ids else None
        # Graph service requires at least 'type' or 'q'; default to wildcard
        resolved_q = q if (q or entity_type or parsed_ids) else "%"
        return gateway.list_entities(
            space_id=space_id,
            q=resolved_q,
            entity_type=entity_type,
            ids=parsed_ids,
            offset=offset,
            limit=limit,
        )
    except GraphServiceClientError as exc:
        _raise_graph_api_error(exc)


@router.get(
    "/{space_id}/graph-explorer/entities/{entity_id}/claims",
    response_model=KernelRelationClaimListResponse,
    summary="List claims for one entity",
)
def list_claims_by_entity(
    space_id: UUID,
    entity_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    *,
    gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> KernelRelationClaimListResponse:
    """Return relation claims linked to a specific entity."""
    try:
        return gateway.list_claims_by_entity(
            space_id=space_id,
            entity_id=entity_id,
            offset=offset,
            limit=limit,
        )
    except GraphServiceClientError as exc:
        _raise_graph_api_error(exc)


@router.get(
    "/{space_id}/graph-explorer/claims/{claim_id}/evidence",
    response_model=KernelClaimEvidenceListResponse,
    summary="List evidence for one claim",
)
def list_claim_evidence(
    space_id: UUID,
    claim_id: UUID,
    *,
    gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> KernelClaimEvidenceListResponse:
    """Return evidence rows for a specific graph claim."""
    try:
        return gateway.list_claim_evidence(
            space_id=space_id,
            claim_id=claim_id,
        )
    except GraphServiceClientError as exc:
        _raise_graph_api_error(exc)


@router.post(
    "/{space_id}/graph-explorer/document",
    response_model=KernelGraphDocumentResponse,
    summary="Get unified graph document",
)
def get_graph_document(
    space_id: UUID,
    request: KernelGraphDocumentRequest,
    *,
    gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> KernelGraphDocumentResponse:
    """Return unified graph document with claim and evidence overlays."""
    if request.mode == "seeded" and not request.seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_SEEDED_GRAPH_DOCUMENT_SEEDS_REQUIRED_DETAIL,
        )
    try:
        return gateway.get_graph_document(
            space_id=space_id,
            request=request,
        )
    except GraphServiceClientError as exc:
        _raise_graph_api_error(exc)
