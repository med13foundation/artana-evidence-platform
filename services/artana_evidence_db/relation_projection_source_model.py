"""Service-local relation projection-lineage domain model."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field

RelationProjectionOrigin = Literal[
    "EXTRACTION",
    "CLAIM_RESOLUTION",
    "MANUAL_RELATION",
    "GRAPH_CONNECTION",
]


class KernelRelationProjectionSource(BaseModel):
    """One claim-backed lineage row for a canonical relation projection."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    relation_id: UUID
    claim_id: UUID
    projection_origin: RelationProjectionOrigin
    source_document_id: UUID | None = None
    source_document_ref: str | None = Field(default=None, max_length=512)
    agent_run_id: str | None = Field(default=None, max_length=255)
    metadata_payload: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None


__all__ = [
    "KernelRelationProjectionSource",
    "RelationProjectionOrigin",
]
