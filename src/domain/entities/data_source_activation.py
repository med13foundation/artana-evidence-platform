"""Domain entities for data source activation policies."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import Enum
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ActivationScope(str, Enum):
    """Scope types for data source activation policies."""

    GLOBAL = "global"
    RESEARCH_SPACE = "research_space"


class PermissionLevel(str, Enum):
    """Permission levels for catalog entries."""

    BLOCKED = "blocked"
    VISIBLE = "visible"
    AVAILABLE = "available"


class DataSourceActivation(BaseModel):
    """Represents a system-level activation policy for a catalog entry."""

    id: UUID
    catalog_entry_id: str
    scope: ActivationScope
    permission_level: PermissionLevel = Field(
        ...,
        description="Permission level applied to this scope",
    )
    research_space_id: UUID | None = Field(
        None,
        description="Target research space when scope is research_space",
    )
    updated_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(frozen=True)

    @property
    def is_active(self) -> bool:
        """Compatibility helper indicating if entry should be surfaced."""
        return self.permission_level != PermissionLevel.BLOCKED

    @property
    def allows_testing(self) -> bool:
        """Return True when tests and ingestion may run for this scope."""
        return self.permission_level == PermissionLevel.AVAILABLE

    @property
    def allows_visibility(self) -> bool:
        """Return True when the entry may be displayed in catalogs."""
        return self.permission_level in (
            PermissionLevel.VISIBLE,
            PermissionLevel.AVAILABLE,
        )

    @model_validator(mode="after")
    def validate_scope(self) -> DataSourceActivation:
        """Ensure research space relationships align with the scope."""
        if (
            self.scope == ActivationScope.RESEARCH_SPACE
            and self.research_space_id is None
        ):
            msg = "research_space_id is required when scope is research_space"
            raise ValueError(msg)
        if self.scope == ActivationScope.GLOBAL and self.research_space_id is not None:
            msg = "research_space_id must be null for global scope"
            raise ValueError(msg)
        return self
