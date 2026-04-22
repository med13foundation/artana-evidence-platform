"""
System status and maintenance mode type definitions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field


class MaintenanceModeState(BaseModel):
    """Represents the current maintenance mode state."""

    model_config = ConfigDict(frozen=True)

    is_active: bool = False
    message: str | None = None
    activated_at: datetime | None = None
    activated_by: UUID | None = None
    last_updated_by: UUID | None = None
    last_updated_at: datetime | None = None

    def with_activation(
        self,
        *,
        message: str | None,
        actor_id: UUID,
    ) -> MaintenanceModeState:
        """Return a new state representing an activated maintenance window."""
        timestamp = datetime.now(UTC)
        return self.model_copy(
            update={
                "is_active": True,
                "message": message,
                "activated_at": timestamp,
                "activated_by": actor_id,
                "last_updated_at": timestamp,
                "last_updated_by": actor_id,
            },
        )

    def with_deactivation(self, *, actor_id: UUID) -> MaintenanceModeState:
        """Return a new state representing a deactivated maintenance window."""
        timestamp = datetime.now(UTC)
        return self.model_copy(
            update={
                "is_active": False,
                "message": None,
                "last_updated_at": timestamp,
                "last_updated_by": actor_id,
            },
        )


class EnableMaintenanceRequest(BaseModel):
    """Request payload for enabling maintenance mode."""

    message: str | None = Field(
        default=None,
        max_length=500,
        description="Optional message displayed to users during maintenance.",
    )
    force_logout_users: bool = Field(
        default=True,
        description="Whether to revoke all active sessions immediately.",
    )


class MaintenanceModeResponse(BaseModel):
    """Response payload for returning maintenance mode state."""

    state: MaintenanceModeState


__all__ = [
    "EnableMaintenanceRequest",
    "MaintenanceModeResponse",
    "MaintenanceModeState",
]
