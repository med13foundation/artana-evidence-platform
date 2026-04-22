import re
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.type_definitions.common import JSONObject


def _default_space_settings() -> JSONObject:
    return {}


class SpaceStatus(str, Enum):
    """Research space lifecycle status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    SUSPENDED = "suspended"


UpdatePayload = dict[str, object]


class ResearchSpace(BaseModel):
    """
    Domain entity representing a research space.

    A research space is an isolated workspace for a specific syndrome or research area,
    with its own data sources, team members, and curation workflows.

    This entity follows Clean Architecture principles:
    - Immutable (frozen=True)
    - Business logic encapsulated
    - No infrastructure dependencies
    - Strong type safety
    """

    model_config = ConfigDict(frozen=True)  # Immutable entity

    # Identity
    id: UUID = Field(default_factory=uuid4)
    slug: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="URL-safe unique identifier",
    )
    name: str = Field(..., min_length=1, max_length=100, description="Display name")

    # Metadata
    description: str = Field(..., max_length=500, description="Space description")
    owner_id: UUID = Field(..., description="User ID of the space owner")
    status: SpaceStatus = Field(default=SpaceStatus.ACTIVE)

    # Configuration
    settings: JSONObject = Field(
        default_factory=_default_space_settings,
        description="Space-specific settings (flexible dict for arbitrary key-value pairs)",
    )

    # Metadata
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def _clone_with_updates(self, updates: UpdatePayload) -> "ResearchSpace":
        """Internal helper to create updated immutable instances."""
        return self.model_copy(update=updates)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Validate slug format - only lowercase letters, numbers, and hyphens."""
        slug_error_msg = (
            "Slug must contain only lowercase letters, numbers, and hyphens"
        )
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(slug_error_msg)
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tags - lowercase, alphanumeric with hyphens."""
        for tag in v:
            tag_error_msg = (
                f'Tag "{tag}" must contain only lowercase letters, numbers, and hyphens'
            )
            if not re.match(r"^[a-z0-9-]+$", tag):
                raise ValueError(tag_error_msg)
        return v

    def is_active(self) -> bool:
        """Check if the space is active."""
        return self.status == SpaceStatus.ACTIVE

    def can_be_modified_by(self, user_id: UUID) -> bool:
        """Check if a user can modify this space."""
        return self.owner_id == user_id

    def with_updated_at(self) -> "ResearchSpace":
        """Return a new instance with updated_at set to now."""
        update_payload: UpdatePayload = {
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def with_status(self, status: SpaceStatus) -> "ResearchSpace":
        """Return a new instance with updated status."""
        update_payload: UpdatePayload = {
            "status": status,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def with_settings(self, settings: JSONObject) -> "ResearchSpace":
        """Return a new instance with updated settings."""
        update_payload: UpdatePayload = {
            "settings": settings,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def with_tags(self, tags: list[str]) -> "ResearchSpace":
        """Return a new instance with updated tags."""
        update_payload: UpdatePayload = {
            "tags": tags,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)
