from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class MembershipRole(str, Enum):
    """User roles within a research space."""

    OWNER = "owner"
    ADMIN = "admin"
    CURATOR = "curator"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


UpdatePayload = dict[str, object]


class ResearchSpaceMembership(BaseModel):
    """
    Domain entity representing a user's membership in a research space.

    This entity manages the relationship between users and research spaces,
    including roles, permissions, and invitation workflows.

    Follows Clean Architecture principles:
    - Immutable (frozen=True)
    - Business logic encapsulated
    - No infrastructure dependencies
    - Strong type safety
    """

    model_config = ConfigDict(frozen=True)  # Immutable entity

    # Identity
    id: UUID = Field(default_factory=uuid4)
    space_id: UUID = Field(..., description="Research space ID")
    user_id: UUID = Field(..., description="User ID")

    # Role & Permissions
    role: MembershipRole = Field(..., description="User's role in the space")

    # Invitation Workflow
    invited_by: UUID | None = Field(
        None,
        description="User ID who sent the invitation",
    )
    invited_at: datetime | None = Field(
        None,
        description="When the invitation was sent",
    )
    joined_at: datetime | None = Field(None, description="When the user joined")

    # Status
    is_active: bool = Field(
        default=True,
        description="Whether the membership is active",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def _clone_with_updates(self, updates: UpdatePayload) -> "ResearchSpaceMembership":
        """Internal helper to maintain immutability with typed updates."""
        return self.model_copy(update=updates)

    def has_permission(self, required_role: MembershipRole) -> bool:
        """
        Check if the member has the required role or higher.

        Role hierarchy: OWNER > ADMIN > CURATOR > RESEARCHER > VIEWER
        """
        role_hierarchy = {
            MembershipRole.VIEWER: 1,
            MembershipRole.RESEARCHER: 2,
            MembershipRole.CURATOR: 3,
            MembershipRole.ADMIN: 4,
            MembershipRole.OWNER: 5,
        }

        current_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        return current_level >= required_level

    def is_owner(self) -> bool:
        """Check if the member is the owner."""
        return self.role == MembershipRole.OWNER

    def is_admin(self) -> bool:
        """Check if the member is an admin."""
        return self.role in [MembershipRole.OWNER, MembershipRole.ADMIN]

    def can_invite_members(self) -> bool:
        """Check if the member can invite new members."""
        return self.has_permission(MembershipRole.ADMIN)

    def can_modify_members(self) -> bool:
        """Check if the member can modify other members' roles."""
        return self.has_permission(MembershipRole.ADMIN)

    def can_remove_members(self) -> bool:
        """Check if the member can remove other members."""
        return self.has_permission(MembershipRole.ADMIN)

    def with_role(self, role: MembershipRole) -> "ResearchSpaceMembership":
        """Return a new instance with updated role."""
        update_payload: UpdatePayload = {
            "role": role,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def with_joined_at(self, joined_at: datetime) -> "ResearchSpaceMembership":
        """Return a new instance with joined_at set."""
        update_payload: UpdatePayload = {
            "joined_at": joined_at,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def with_status(self, *, is_active: bool) -> "ResearchSpaceMembership":
        """Return a new instance with updated active status."""
        update_payload: UpdatePayload = {
            "is_active": is_active,
            "updated_at": datetime.now(UTC),
        }
        return self._clone_with_updates(update_payload)

    def is_pending_invitation(self) -> bool:
        """Check if this is a pending invitation."""
        return self.invited_at is not None and self.joined_at is None

    def is_accepted(self) -> bool:
        """Check if the invitation has been accepted."""
        return self.joined_at is not None
