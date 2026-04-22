"""Service-local source document reference entity."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field


class KernelSourceDocumentReference(BaseModel):
    """Graph-local reference to one external source document."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    research_space_id: UUID | None = None
    source_id: UUID
    external_record_id: str = Field(..., min_length=1, max_length=255)
    source_type: str = Field(..., min_length=1, max_length=32)
    document_format: str = Field(..., min_length=1, max_length=64)
    enrichment_status: str = Field(..., min_length=1, max_length=32)
    extraction_status: str = Field(..., min_length=1, max_length=32)
    metadata: JSONObject
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = ["KernelSourceDocumentReference"]
