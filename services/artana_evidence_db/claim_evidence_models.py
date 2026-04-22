"""Service-local claim-evidence domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field

ClaimEvidenceSentenceSource = Literal["verbatim_span", "artana_generated"]
ClaimEvidenceSentenceConfidence = Literal["low", "medium", "high"]


class KernelClaimEvidence(BaseModel):
    """One evidence row attached to a relation claim."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    claim_id: UUID
    source_document_id: UUID | None = None
    source_document_ref: str | None = Field(default=None, max_length=512)
    agent_run_id: str | None = Field(default=None, max_length=255)
    sentence: str | None = None
    sentence_source: ClaimEvidenceSentenceSource | None = None
    sentence_confidence: ClaimEvidenceSentenceConfidence | None = None
    sentence_rationale: str | None = None
    figure_reference: str | None = None
    table_reference: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    metadata_payload: JSONObject = Field(default_factory=dict)
    created_at: datetime


__all__ = [
    "ClaimEvidenceSentenceConfidence",
    "ClaimEvidenceSentenceSource",
    "KernelClaimEvidence",
]
