"""Orphanet direct source-search contracts and runner."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

from artana_evidence_api.direct_sources.capture import (
    build_direct_search_capture,
    json_records,
    single_record_external_id,
)
from artana_evidence_api.source_enrichment_bridges import OrphanetGatewayProtocol
from artana_evidence_api.source_result_capture import SourceResultCapture
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OrphanetLanguage = Literal["CS", "DE", "EN", "ES", "FR", "IT", "NL", "PL", "PT"]


class OrphanetSourceSearchRequest(BaseModel):
    """Request payload for a direct Orphanet disease lookup."""

    model_config = ConfigDict(strict=True)

    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=512,
        description="Rare-disease name or approximate preferred term to search.",
    )
    orphacode: int | None = Field(
        default=None,
        ge=1,
        description="Exact ORPHAcode to fetch from Orphanet.",
    )
    language: OrphanetLanguage = Field(
        default="EN",
        description="ORPHAcodes API language code.",
    )
    max_results: int = Field(default=20, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @model_validator(mode="after")
    def _validate_query_input(self) -> OrphanetSourceSearchRequest:
        if self.query and self.orphacode is not None:
            msg = "Provide either query or orphacode, not both"
            raise ValueError(msg)
        if self.query or self.orphacode is not None:
            return self
        msg = "Provide one of query or orphacode"
        raise ValueError(msg)

    def query_text(self) -> str:
        """Return the public query string for capture metadata."""

        return (
            f"ORPHA:{self.orphacode}"
            if self.orphacode is not None
            else self.query or ""
        )


class OrphanetSourceSearchResponse(BaseModel):
    """Response payload for one captured Orphanet direct search."""

    id: UUID
    space_id: UUID
    source_key: Literal["orphanet"] = "orphanet"
    status: Literal["completed"] = "completed"
    query: str
    orphacode: int | None = None
    language: OrphanetLanguage = "EN"
    max_results: int
    fetched_records: int
    record_count: int
    records: list[JSONObject] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    source_capture: SourceResultCapture


class OrphanetDirectSourceSearchStore(Protocol):
    """Storage contract needed by the Orphanet direct-source runner."""

    def save(
        self,
        record: OrphanetSourceSearchResponse,
        *,
        created_by: UUID | str,
    ) -> OrphanetSourceSearchResponse:
        """Store an Orphanet direct source-search result."""
        ...


async def run_orphanet_direct_search(
    *,
    space_id: UUID,
    created_by: UUID | str,
    request: OrphanetSourceSearchRequest,
    gateway: OrphanetGatewayProtocol,
    store: OrphanetDirectSourceSearchStore,
) -> OrphanetSourceSearchResponse:
    """Fetch Orphanet records and capture them as a direct source search."""

    created_at = datetime.now(UTC)
    fetch_result = await gateway.fetch_records_async(
        query=request.query,
        orphacode=request.orphacode,
        language=request.language,
        max_results=request.max_results,
    )
    records = json_records(fetch_result.records)
    completed_at = datetime.now(UTC)
    search_id = uuid4()
    query = request.query_text()
    capture = build_direct_search_capture(
        source_key="orphanet",
        search_id=search_id,
        completed_at=completed_at,
        query=query,
        query_payload=request.model_dump(mode="json", exclude_none=True),
        result_count=len(records),
        provider="ORPHAcodes API / Orphanet Nomenclature Pack",
        external_id=single_record_external_id(
            records,
            keys=("orphanet_id", "orpha_code", "ORPHAcode"),
            expected=f"ORPHA:{request.orphacode}"
            if request.orphacode is not None
            else None,
        ),
        provenance={
            "language": request.language,
            "fetched_records": fetch_result.fetched_records,
        },
    )
    result = OrphanetSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        query=query,
        orphacode=request.orphacode,
        language=request.language,
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
    "OrphanetDirectSourceSearchStore",
    "OrphanetLanguage",
    "OrphanetSourceSearchRequest",
    "OrphanetSourceSearchResponse",
    "run_orphanet_direct_search",
]
