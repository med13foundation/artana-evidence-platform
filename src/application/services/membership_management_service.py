"""
Application service for research space membership management.

Orchestrates domain services and repositories to implement
membership management use cases with proper business logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.domain.entities.research_space_membership import (
    MembershipRole,
    ResearchSpaceMembership,
)
from src.domain.repositories.research_space_repository import (
    ResearchSpaceMembershipRepository,
    ResearchSpaceRepository,
)

if TYPE_CHECKING:
    from src.domain.entities.research_space import ResearchSpace
    from src.domain.ports.space_lifecycle_sync_port import SpaceLifecycleSyncPort


class InviteMemberRequest:
    """Request model for inviting a member to a research space."""

    def __init__(
        self,
        space_id: UUID,
        user_id: UUID,
        role: MembershipRole,
        invited_by: UUID,
        *,
        invited_by_is_platform_admin: bool = False,
    ):
        self.space_id = space_id
        self.user_id = user_id
        self.role = role
        self.invited_by = invited_by
        self.invited_by_is_platform_admin = invited_by_is_platform_admin


class UpdateMemberRoleRequest:
    """Request model for updating a member's role."""

    def __init__(self, role: MembershipRole):
        self.role = role


class MembershipManagementService:
    """
    Application service for research space membership management.

    Orchestrates membership operations including invitations, role management,
    and access control.
    """

    def __init__(
        self,
        membership_repository: ResearchSpaceMembershipRepository,
        research_space_repository: ResearchSpaceRepository,
        space_lifecycle_sync: SpaceLifecycleSyncPort | None = None,
    ):
        """
        Initialize the membership management service.

        Args:
            membership_repository: Repository for memberships
            research_space_repository: Repository for research spaces
        """
        self._membership_repository = membership_repository
        self._space_repository = research_space_repository
        self._space_lifecycle_sync = space_lifecycle_sync

    def _load_space(self, space_id: UUID) -> ResearchSpace:
        space = self._space_repository.find_by_id(space_id)
        if space is None:
            msg = f"Research space {space_id} not found"
            raise ValueError(msg)
        return space

    def _sync_space(self, space_id: UUID) -> None:
        if self._space_lifecycle_sync is None:
            return
        self._space_lifecycle_sync.sync_space(self._load_space(space_id))

    def _get_requester_membership(
        self,
        space_id: UUID,
        requester_id: UUID,
        *,
        requester_is_platform_admin: bool = False,
    ) -> ResearchSpaceMembership | None:
        """Resolve the effective requester membership, including implicit roles."""
        if requester_is_platform_admin:
            return ResearchSpaceMembership(
                space_id=space_id,
                user_id=requester_id,
                role=MembershipRole.ADMIN,
                invited_by=None,
                invited_at=None,
                joined_at=datetime.now(UTC),
                is_active=True,
            )

        return self.get_membership_for_user(space_id, requester_id)

    def invite_member(self, request: InviteMemberRequest) -> ResearchSpaceMembership:
        """
        Invite a user to join a research space.

        Args:
            request: Invitation request with member details

        Returns:
            The created ResearchSpaceMembership entity

        Raises:
            ValueError: If validation fails or user is already a member
        """
        # Check if space exists
        self._load_space(request.space_id)

        # Check if user is already a member
        existing = self._membership_repository.find_by_space_and_user(
            request.space_id,
            request.user_id,
        )
        if existing:
            msg = f"User {request.user_id} is already a member of this space"
            raise ValueError(msg)

        # Check if inviter has permission (must be admin or owner)
        inviter_membership = self._get_requester_membership(
            request.space_id,
            request.invited_by,
            requester_is_platform_admin=request.invited_by_is_platform_admin,
        )
        if not inviter_membership or not inviter_membership.can_invite_members():
            msg = "Only admins and owners can invite members"
            raise ValueError(msg)

        # Create the membership entity with invitation
        now = datetime.now(UTC)
        membership = ResearchSpaceMembership(
            id=uuid4(),  # Repository may replace this during persistence.
            space_id=request.space_id,
            user_id=request.user_id,
            role=request.role,
            invited_by=request.invited_by,
            invited_at=now,
            joined_at=None,
            is_active=False,  # Inactive until accepted
        )

        # Save to repository
        saved_membership = self._membership_repository.save(membership)
        self._sync_space(saved_membership.space_id)
        return saved_membership

    def accept_invitation(
        self,
        membership_id: UUID,
        user_id: UUID,
    ) -> ResearchSpaceMembership | None:
        """
        Accept a pending invitation.

        Args:
            membership_id: The membership ID
            user_id: The user accepting the invitation

        Returns:
            The updated ResearchSpaceMembership if successful, None otherwise
        """
        membership = self._membership_repository.find_by_id(membership_id)
        if not membership:
            return None

        # Verify it's the correct user
        if membership.user_id != user_id:
            return None

        # Verify it's a pending invitation
        if not membership.is_pending_invitation():
            return None

        # Accept the invitation
        now = datetime.now(UTC)
        accepted_membership = membership.with_joined_at(now).with_status(is_active=True)

        saved_membership = self._membership_repository.save(accepted_membership)
        self._sync_space(saved_membership.space_id)
        return saved_membership

    def get_membership(
        self,
        membership_id: UUID,
    ) -> ResearchSpaceMembership | None:
        """
        Get a membership by ID.

        Args:
            membership_id: The membership ID

        Returns:
            The ResearchSpaceMembership if found, None otherwise
        """
        return self._membership_repository.find_by_id(membership_id)

    def get_space_members(
        self,
        space_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """
        Get all members of a research space.

        Args:
            space_id: The research space ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of memberships for the space
        """
        return self._membership_repository.find_by_space(space_id, skip, limit)

    def get_user_memberships(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """
        Get all memberships for a user.

        Args:
            user_id: The user ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of memberships for the user
        """
        return self._membership_repository.find_by_user(user_id, skip, limit)

    def get_membership_for_user(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> ResearchSpaceMembership | None:
        """
        Get a specific user's membership for a space.

        Args:
            space_id: The research space ID
            user_id: The user ID

        Returns:
            The active ResearchSpaceMembership if found and active, None otherwise
        """
        membership = self._membership_repository.find_by_space_and_user(
            space_id,
            user_id,
        )
        if membership is not None and membership.is_active:
            return membership

        # Treat owner as implicit membership to keep role resolution consistent
        space = self._space_repository.find_by_id(space_id)
        if space and space.owner_id == user_id:
            return ResearchSpaceMembership(
                space_id=space_id,
                user_id=user_id,
                role=MembershipRole.OWNER,
                invited_by=None,
                invited_at=None,
                joined_at=datetime.now(UTC),
                is_active=True,
            )

        return None

    def get_pending_invitations(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """
        Get pending invitations for a user.

        Args:
            user_id: The user ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of pending invitations
        """
        return self._membership_repository.find_pending_invitations(
            user_id,
            skip,
            limit,
        )

    def update_member_role(
        self,
        membership_id: UUID,
        request: UpdateMemberRoleRequest,
        requester_id: UUID,
        *,
        requester_is_platform_admin: bool = False,
    ) -> ResearchSpaceMembership | None:
        """
        Update a member's role in a research space.

        Args:
            membership_id: The membership ID
            request: Update request with new role
            requester_id: The user making the request (for authorization)

        Returns:
            The updated ResearchSpaceMembership if successful, None otherwise
        """
        membership = self._membership_repository.find_by_id(membership_id)
        if not membership:
            return None

        # Check if requester has permission (must be admin or owner)
        requester_membership = self._get_requester_membership(
            membership.space_id,
            requester_id,
            requester_is_platform_admin=requester_is_platform_admin,
        )
        if not requester_membership or not requester_membership.can_modify_members():
            return None

        # Prevent changing owner role
        if membership.is_owner():
            return None

        # Update the role
        updated_membership = membership.with_role(request.role)
        saved_membership = self._membership_repository.save(updated_membership)
        self._sync_space(saved_membership.space_id)
        return saved_membership

    def remove_member(
        self,
        membership_id: UUID,
        requester_id: UUID,
        *,
        requester_is_platform_admin: bool = False,
    ) -> bool:
        """
        Remove a member from a research space.

        Args:
            membership_id: The membership ID
            requester_id: The user making the request (for authorization)

        Returns:
            True if removed, False if not found or not authorized
        """
        membership = self._membership_repository.find_by_id(membership_id)
        if not membership:
            return False

        # Check if requester has permission (must be admin or owner)
        requester_membership = self._get_requester_membership(
            membership.space_id,
            requester_id,
            requester_is_platform_admin=requester_is_platform_admin,
        )
        if not requester_membership or not requester_membership.can_remove_members():
            return False

        # Prevent removing owner
        if membership.is_owner():
            return False

        # Deactivate membership instead of deleting (soft delete)
        deactivated_membership = membership.with_status(is_active=False)
        saved_membership = self._membership_repository.save(deactivated_membership)
        self._sync_space(saved_membership.space_id)
        return True

    def get_user_role(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> MembershipRole | None:
        """
        Get a user's role in a research space.

        Args:
            space_id: The research space ID
            user_id: The user ID

        Returns:
            The user's role if found, None otherwise
        """
        return self._membership_repository.get_user_role(space_id, user_id)

    def is_user_member(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> bool:
        """
        Check if a user is a member of a research space.

        Args:
            space_id: The research space ID
            user_id: The user ID

        Returns:
            True if user is a member, False otherwise
        """
        return self._membership_repository.is_user_member(space_id, user_id)

    def get_space_member_count(self, space_id: UUID) -> int:
        """
        Get the count of active members in a research space.

        Args:
            space_id: The research space ID

        Returns:
            The count of active members
        """
        return self._membership_repository.count_by_space(space_id)

    def get_members_by_role(
        self,
        space_id: UUID,
        role: MembershipRole,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """
        Get members with a specific role in a research space.

        Args:
            space_id: The research space ID
            role: The role to filter by
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of memberships with the specified role
        """
        return self._membership_repository.find_by_role(space_id, role, skip, limit)
