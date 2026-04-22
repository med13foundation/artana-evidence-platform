"""Service-local claim-participant domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from pydantic import BaseModel, ConfigDict, Field, model_validator

ClaimParticipantRole = Literal[
    "SUBJECT",
    "OBJECT",
    "CONTEXT",
    "QUALIFIER",
    "MODIFIER",
    "OUTCOME",
]


class KernelClaimParticipant(BaseModel):
    """One structured participant linked to a relation claim."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    claim_id: UUID
    research_space_id: UUID
    label: str | None = Field(default=None, max_length=512)
    entity_id: UUID | None = None
    role: ClaimParticipantRole
    position: int | None = Field(default=None, ge=-32768, le=32767)
    qualifiers: JSONObject = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_anchor(self) -> KernelClaimParticipant:
        """Require either a free-text label or a resolved entity anchor."""
        has_label = isinstance(self.label, str) and bool(self.label.strip())
        if has_label or self.entity_id is not None:
            return self
        msg = "Claim participant requires either label or entity_id"
        raise ValueError(msg)


__all__ = ["ClaimParticipantRole", "KernelClaimParticipant"]
