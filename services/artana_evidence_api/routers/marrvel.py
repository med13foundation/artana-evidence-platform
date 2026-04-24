"""MARRVEL discovery and ingestion endpoints for the standalone harness service."""

from __future__ import annotations

import logging
from typing import Literal, cast
from uuid import UUID  # noqa: TC003

from artana_evidence_api.auth import (
    HarnessUser,  # noqa: TC001
    get_current_harness_user,
)
from artana_evidence_api.dependencies import (
    get_graph_api_gateway,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import (
    GraphTransportBundle,  # noqa: TC001
)
from artana_evidence_api.marrvel_discovery import MarrvelDiscoveryService
from artana_evidence_api.types.common import JSONObject, JSONValue
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/spaces",
    tags=["marrvel"],
)

_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)


_MARRVEL_DISCOVERY_SERVICE = MarrvelDiscoveryService()


def get_marrvel_discovery_service() -> MarrvelDiscoveryService:
    return _MARRVEL_DISCOVERY_SERVICE


_MARRVEL_DISCOVERY_SERVICE_DEPENDENCY = Depends(get_marrvel_discovery_service)


MarrvelPanelName = Literal[
    "omim",
    "dbnsfp",
    "clinvar",
    "geno2mp",
    "gnomad",
    "dgv",
    "diopt_orthologs",
    "diopt_alignment",
    "gtex",
    "expression",
    "pharos",
    "mutalyzer",
    "transvar",
    "gnomad_variant",
    "geno2mp_variant",
    "dgv_variant",
    "decipher_variant",
]
MarrvelQueryMode = Literal["gene", "variant_hgvs", "protein_variant"]


class MarrvelSearchRequest(BaseModel):
    """Request payload for a MARRVEL gene discovery search."""

    model_config = ConfigDict(strict=True)

    gene_symbol: str | None = Field(
        default=None,
        min_length=1,
        description="Gene symbol to search in MARRVEL.",
    )
    variant_hgvs: str | None = Field(
        default=None,
        min_length=1,
        description="HGVS-formatted variant to normalize through MARRVEL.",
    )
    protein_variant: str | None = Field(
        default=None,
        min_length=1,
        description="Protein variant to resolve through TransVar in MARRVEL.",
    )
    taxon_id: int = Field(
        default=9606,
        ge=1,
        description="NCBI Taxonomy ID (default: 9606 for Homo sapiens).",
    )
    panels: list[MarrvelPanelName] | None = Field(
        default=None,
        description="Optional subset of MARRVEL panels to fetch.",
    )

    @model_validator(mode="after")
    def _validate_query_input(self) -> MarrvelSearchRequest:
        if self.protein_variant and self.variant_hgvs:
            msg = "Provide either variant_hgvs or protein_variant, not both"
            raise ValueError(msg)
        if self.gene_symbol or self.variant_hgvs or self.protein_variant:
            return self
        msg = "Provide at least one of gene_symbol, variant_hgvs, or protein_variant"
        raise ValueError(msg)


class MarrvelSearchResponse(BaseModel):
    """Response for a MARRVEL gene discovery search."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    space_id: UUID
    query_mode: MarrvelQueryMode
    query_value: str
    gene_symbol: str | None
    resolved_gene_symbol: str | None = None
    resolved_variant: str | None = None
    taxon_id: int
    status: str
    gene_found: bool
    gene_info: JSONObject | None = None
    omim_count: int
    variant_count: int
    panel_counts: dict[str, int] = Field(default_factory=dict)
    panels: dict[str, JSONValue] = Field(default_factory=dict)
    available_panels: list[str] = Field(default_factory=list)


@router.post(
    "/{space_id}/marrvel/searches",
    response_model=MarrvelSearchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run a MARRVEL gene discovery search for a research space",
    dependencies=[Depends(require_harness_space_write_access)],
)
async def create_marrvel_search(
    space_id: UUID,
    request: MarrvelSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    marrvel_discovery_service: MarrvelDiscoveryService = _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY,
) -> MarrvelSearchResponse:
    try:
        result = await marrvel_discovery_service.search(
            owner_id=current_user.id,
            space_id=space_id,
            gene_symbol=request.gene_symbol,
            variant_hgvs=request.variant_hgvs,
            protein_variant=request.protein_variant,
            taxon_id=request.taxon_id,
            panels=cast("list[str] | None", request.panels),
        )
        return MarrvelSearchResponse(
            id=result.id,
            space_id=result.space_id,
            query_mode=result.query_mode,
            query_value=result.query_value,
            gene_symbol=result.gene_symbol,
            resolved_gene_symbol=result.resolved_gene_symbol,
            resolved_variant=result.resolved_variant,
            taxon_id=result.taxon_id,
            status=result.status,
            gene_found=result.gene_found,
            gene_info=result.gene_info,
            omim_count=result.omim_count,
            variant_count=result.variant_count,
            panel_counts=result.panel_counts,
            panels=result.panels,
            available_panels=result.available_panels,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"MARRVEL discovery unavailable: {exc}",
        ) from exc


@router.get(
    "/{space_id}/marrvel/searches/{result_id}",
    response_model=MarrvelSearchResponse,
    summary="Get a MARRVEL discovery search result",
    dependencies=[Depends(require_harness_space_read_access)],
)
def get_marrvel_search(
    space_id: UUID,
    result_id: UUID,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    marrvel_discovery_service: MarrvelDiscoveryService = _MARRVEL_DISCOVERY_SERVICE_DEPENDENCY,
) -> MarrvelSearchResponse:
    result = marrvel_discovery_service.get_result(
        owner_id=current_user.id,
        result_id=result_id,
    )
    if result is None or result.space_id != space_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MARRVEL search result '{result_id}' not found in space '{space_id}'",
        )
    return MarrvelSearchResponse(
        id=result.id,
        space_id=result.space_id,
        query_mode=result.query_mode,
        query_value=result.query_value,
        gene_symbol=result.gene_symbol,
        resolved_gene_symbol=result.resolved_gene_symbol,
        resolved_variant=result.resolved_variant,
        taxon_id=result.taxon_id,
        status=result.status,
        gene_found=result.gene_found,
        gene_info=result.gene_info,
        omim_count=result.omim_count,
        variant_count=result.variant_count,
        panel_counts=result.panel_counts,
        panels=result.panels,
        available_panels=result.available_panels,
    )


_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)


class MarrvelIngestRequest(BaseModel):
    """Request to ingest MARRVEL gene data into the knowledge graph."""

    model_config = ConfigDict(strict=True)

    gene_symbols: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Gene symbols to ingest from MARRVEL.",
    )
    taxon_id: int = Field(default=9606, ge=1)


class MarrvelIngestResponse(BaseModel):
    """Response from MARRVEL harness ingestion and entity seeding."""

    model_config = ConfigDict(strict=True)

    genes_searched: int
    genes_found: int
    entities_created: int
    claims_created: int
    details: list[str]


@router.post(
    "/{space_id}/marrvel/ingest",
    response_model=MarrvelIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Fetch MARRVEL gene data and seed graph entities",
    dependencies=[Depends(require_harness_space_write_access)],
)
async def ingest_marrvel_genes(
    space_id: UUID,
    request: MarrvelIngestRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> MarrvelIngestResponse:
    """Retired: MARRVEL entity seeding now flows through the shared pipeline.

    Direct entity creation via ``gateway.create_entity()`` has been removed.
    MARRVEL records are ingested as source documents with Tier 1 grounding
    attached, then flow through entity recognition → extraction → governed
    claims like all other connector families.
    """
    del current_user, gateway
    logger.info(
        "MARRVEL direct entity-seeding retired for space %s — "
        "entities now come from the shared extraction pipeline",
        space_id,
    )
    return MarrvelIngestResponse(
        genes_searched=len(request.gene_symbols),
        genes_found=0,
        entities_created=0,
        claims_created=0,
        details=[
            "MARRVEL direct entity seeding is retired. "
            "Entities and claims now flow through the shared extraction pipeline.",
        ],
    )


__all__ = [
    "MarrvelSearchRequest",
    "MarrvelSearchResponse",
    "MarrvelIngestRequest",
    "MarrvelIngestResponse",
    "create_marrvel_search",
    "get_marrvel_discovery_service",
    "get_marrvel_search",
    "ingest_marrvel_genes",
    "router",
]
