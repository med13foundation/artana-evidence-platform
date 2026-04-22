"""
Request models for discovery configuration operations.
"""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,  # noqa: TC001
)
from src.domain.entities.discovery_preset import PresetScope


class CreatePubmedPresetRequest(BaseModel):
    """Request payload for creating a PubMed preset."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    scope: PresetScope = Field(default=PresetScope.USER)
    parameters: AdvancedQueryParameters
    research_space_id: UUID | None = None

    @field_validator("research_space_id")
    @classmethod
    def ensure_space_id_for_scope(
        cls,
        value: UUID | None,
        info: ValidationInfo,
    ) -> UUID | None:
        scope: PresetScope = info.data.get("scope", PresetScope.USER)
        if scope == PresetScope.SPACE and value is None:
            msg = "research_space_id is required for space-scoped presets"
            raise ValueError(msg)
        return value


__all__ = ["CreatePubmedPresetRequest"]

CreatePubmedPresetRequest.model_rebuild()
