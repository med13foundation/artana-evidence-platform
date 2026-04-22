"""
Domain entities representing discovery presets and metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,  # noqa: TC001
)
from src.type_definitions.common import JSONObject  # noqa: TC001


class DiscoveryProvider(StrEnum):
    """Supported discovery providers."""

    PUBMED = "pubmed"


class PresetScope(StrEnum):
    """Scopes for sharing discovery presets."""

    USER = "user"
    SPACE = "space"


class DiscoveryPreset(BaseModel):
    """Represents a saved set of advanced query parameters."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    owner_id: UUID
    provider: DiscoveryProvider
    scope: PresetScope = Field(default=PresetScope.USER)
    name: str = Field(..., max_length=200)
    description: str | None = Field(default=None, max_length=500)
    parameters: AdvancedQueryParameters
    metadata: JSONObject = Field(default_factory=dict)
    research_space_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["DiscoveryPreset", "DiscoveryProvider", "PresetScope"]
