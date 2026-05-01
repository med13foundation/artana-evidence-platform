"""gnomAD direct source-search contracts and runner."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from artana_evidence_api.direct_sources.capture import (
    build_direct_search_capture,
    json_records,
    single_record_external_id,
)
from artana_evidence_api.source_enrichment_bridges import GnomADGatewayProtocol
from artana_evidence_api.source_result_capture import SourceResultCapture
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

GnomADDataset = Literal[
    "gnomad_r4",
    "gnomad_r4_non_ukb",
    "gnomad_r3",
    "gnomad_r3_controls_and_biobanks",
    "gnomad_r3_non_cancer",
    "gnomad_r3_non_neuro",
    "gnomad_r3_non_topmed",
    "gnomad_r3_non_v2",
    "gnomad_r2_1",
    "gnomad_r2_1_controls",
    "gnomad_r2_1_non_neuro",
    "gnomad_r2_1_non_cancer",
    "gnomad_r2_1_non_topmed",
    "exac",
]
GnomADReferenceGenome = Literal["GRCh37", "GRCh38"]
GnomADQueryKind = Literal["gene", "variant"]
_GNOMAD_VARIANT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.]+-\d+-[ACGTN]+-[ACGTN]+$")


def is_gnomad_variant_id(value: str) -> bool:
    """Return whether a value looks like a gnomAD variant ID."""

    return bool(_GNOMAD_VARIANT_ID_PATTERN.fullmatch(value.strip()))


class GnomADSourceSearchRequest(BaseModel):
    """Request payload for a direct gnomAD gene or variant lookup."""

    model_config = ConfigDict(strict=True)

    gene_symbol: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Gene symbol for gnomAD constraint lookup.",
    )
    variant_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="gnomAD variant ID, for example '17-5982158-C-T'.",
    )
    reference_genome: GnomADReferenceGenome = Field(
        default="GRCh38",
        description="Reference genome used for gene constraint lookup.",
    )
    dataset: GnomADDataset = Field(
        default="gnomad_r4",
        description="gnomAD dataset used for variant lookup.",
    )
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator("gene_symbol")
    @classmethod
    def _normalize_gene_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        return normalized or None

    @field_validator("variant_id")
    @classmethod
    def _normalize_variant_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if normalized and not is_gnomad_variant_id(normalized):
            msg = "variant_id must use gnomAD format like '17-5982158-C-T'"
            raise ValueError(msg)
        return normalized or None

    @model_validator(mode="after")
    def _validate_query_input(self) -> GnomADSourceSearchRequest:
        if self.gene_symbol and self.variant_id:
            msg = "Provide either gene_symbol or variant_id, not both"
            raise ValueError(msg)
        if self.gene_symbol or self.variant_id:
            return self
        msg = "Provide one of gene_symbol or variant_id"
        raise ValueError(msg)

    def query_kind(self) -> GnomADQueryKind:
        """Return whether this request is a gene or variant lookup."""

        return "variant" if self.variant_id is not None else "gene"

    def query_text(self) -> str:
        """Return the public query string for capture metadata."""

        return self.variant_id or self.gene_symbol or ""


class GnomADSourceSearchResponse(BaseModel):
    """Response payload for one captured gnomAD direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["gnomad"] = "gnomad"
    status: Literal["completed"] = "completed"
    query: str
    query_kind: GnomADQueryKind
    gene_symbol: str | None = None
    variant_id: str | None = None
    reference_genome: GnomADReferenceGenome = "GRCh38"
    dataset: GnomADDataset = "gnomad_r4"
    max_results: int
    fetched_records: int
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class GnomADDirectSourceSearchStore(Protocol):
    """Storage contract needed by the gnomAD direct-source runner."""

    def save(
        self,
        record: GnomADSourceSearchResponse,
        *,
        created_by: UUID | str,
    ) -> GnomADSourceSearchResponse:
        """Store a gnomAD direct source-search result."""
        ...


async def run_gnomad_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: GnomADSourceSearchRequest,
    gateway: GnomADGatewayProtocol,
    store: GnomADDirectSourceSearchStore,
) -> GnomADSourceSearchResponse:
    """Fetch gnomAD records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await asyncio.to_thread(
        gateway.fetch_records,
        gene_symbol=request.gene_symbol,
        variant_id=request.variant_id,
        reference_genome=request.reference_genome,
        dataset=request.dataset,
        max_results=request.max_results,
    )
    records = json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    query = request.query_text()
    query_kind = request.query_kind()
    capture = build_direct_search_capture(
        source_key="gnomad",
        search_id=search_id,
        completed_at=completed_at,
        query=query,
        query_payload=request.model_dump(mode="json", exclude_none=True),
        result_count=len(records),
        provider="gnomAD GraphQL API",
        external_id=single_record_external_id(
            records,
            keys=("variant_id", "variantId", "gene_id", "gene_symbol"),
        ),
        provenance={
            "dataset": request.dataset,
            "reference_genome": request.reference_genome,
            "query_kind": query_kind,
            "fetched_records": fetch_result.fetched_records,
        },
    )
    result = GnomADSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=query,
        query_kind=query_kind,
        gene_symbol=request.gene_symbol,
        variant_id=request.variant_id,
        reference_genome=request.reference_genome,
        dataset=request.dataset,
        max_results=request.max_results,
        fetched_records=fetch_result.fetched_records,
        record_count=len(records),
        records=records,
        created_at=created_at,
        completed_at=completed_at,
        source_capture=SourceResultCapture.model_validate(capture),
    )
    return store.save(result, created_by=created_by)


__all__ = [
    "GnomADDataset",
    "GnomADDirectSourceSearchStore",
    "GnomADQueryKind",
    "GnomADReferenceGenome",
    "GnomADSourceSearchRequest",
    "GnomADSourceSearchResponse",
    "is_gnomad_variant_id",
    "run_gnomad_direct_search",
]
