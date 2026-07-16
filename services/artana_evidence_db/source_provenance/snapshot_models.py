"""Domain model for immutable source evidence snapshots."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from artana_evidence_db.source_provenance.models import SourceIdentity
from pydantic import BaseModel, ConfigDict, Field


class SourceEvidenceSnapshot(BaseModel):
    """Graph-owned source identity and canonical text captured once."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    research_space_id: UUID
    upstream_service: str
    upstream_research_space_id: UUID
    upstream_document_id: UUID
    attested_at: datetime
    identity_fingerprint: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    source_identity: SourceIdentity
    canonical_text: str
    created_at: datetime


__all__ = ["SourceEvidenceSnapshot"]
