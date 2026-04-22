"""Service-local graph-space membership models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class MembershipRole(str, Enum):
    """User roles within one graph space."""

    OWNER = "owner"
    ADMIN = "admin"
    CURATOR = "curator"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


UpdatePayload = dict[str, object]


class ResearchSpaceMembership(BaseModel):
    """Immutable graph-space membership record."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    space_id: UUID
    user_id: UUID
    role: MembershipRole
    invited_by: UUID | None = None
    invited_at: datetime | None = None
    joined_at: datetime | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def _clone_with_updates(self, updates: UpdatePayload) -> ResearchSpaceMembership:
        return self.model_copy(update=updates)

    def has_permission(self, required_role: MembershipRole) -> bool:
        """Check whether the member has the required role or higher."""
        role_hierarchy = {
            MembershipRole.VIEWER: 1,
            MembershipRole.RESEARCHER: 2,
            MembershipRole.CURATOR: 3,
            MembershipRole.ADMIN: 4,
            MembershipRole.OWNER: 5,
        }
        return role_hierarchy.get(self.role, 0) >= role_hierarchy.get(
            required_role,
            0,
        )

    def is_owner(self) -> bool:
        return self.role == MembershipRole.OWNER

    def is_admin(self) -> bool:
        return self.role in [MembershipRole.OWNER, MembershipRole.ADMIN]

    def can_invite_members(self) -> bool:
        return self.has_permission(MembershipRole.ADMIN)

    def can_modify_members(self) -> bool:
        return self.has_permission(MembershipRole.ADMIN)

    def can_remove_members(self) -> bool:
        return self.has_permission(MembershipRole.ADMIN)

    def with_role(self, role: MembershipRole) -> ResearchSpaceMembership:
        return self._clone_with_updates(
            {"role": role, "updated_at": datetime.now(UTC)},
        )

    def with_joined_at(self, joined_at: datetime) -> ResearchSpaceMembership:
        return self._clone_with_updates(
            {"joined_at": joined_at, "updated_at": datetime.now(UTC)},
        )

    def with_status(self, *, is_active: bool) -> ResearchSpaceMembership:
        return self._clone_with_updates(
            {"is_active": is_active, "updated_at": datetime.now(UTC)},
        )

    def is_pending_invitation(self) -> bool:
        return self.invited_at is not None and self.joined_at is None

    def is_accepted(self) -> bool:
        return self.joined_at is not None


__all__ = ["MembershipRole", "ResearchSpaceMembership"]
