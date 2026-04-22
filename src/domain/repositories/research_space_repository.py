"""
Repository interfaces for Research Space entities.

Defines the contract for data access operations on research spaces and memberships,
providing a clean separation between domain logic and data persistence.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from src.domain.entities.research_space import ResearchSpace, SpaceStatus
from src.domain.entities.research_space_membership import (
    MembershipRole,
    ResearchSpaceMembership,
)


class ResearchSpaceRepository(ABC):
    """
    Abstract repository for ResearchSpace entities.

    Defines the interface for CRUD operations and specialized queries
    related to research spaces.
    """

    @abstractmethod
    def save(self, space: ResearchSpace) -> ResearchSpace:
        """
        Save a research space to the repository.

        Args:
            space: The ResearchSpace entity to save

        Returns:
            The saved ResearchSpace with any generated fields populated
        """

    @abstractmethod
    def find_by_id(self, space_id: UUID) -> ResearchSpace | None:
        """
        Find a research space by its ID.

        Args:
            space_id: The unique identifier of the space

        Returns:
            The ResearchSpace if found, None otherwise
        """

    @abstractmethod
    def find_by_slug(self, slug: str) -> ResearchSpace | None:
        """
        Find a research space by its slug.

        Args:
            slug: The URL-safe identifier

        Returns:
            The ResearchSpace if found, None otherwise
        """

    @abstractmethod
    def find_by_owner(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """
        Find all spaces owned by a specific user.

        Args:
            owner_id: The user ID of the owner
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of ResearchSpace entities owned by the user
        """

    @abstractmethod
    def find_by_status(
        self,
        status: SpaceStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """
        Find all spaces with a specific status.

        Args:
            status: The status to filter by
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of ResearchSpace entities with the specified status
        """

    @abstractmethod
    def find_active_spaces(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """
        Find all active research spaces.

        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of active ResearchSpace entities
        """

    @abstractmethod
    def search_by_name(
        self,
        query: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """
        Search research spaces by name using fuzzy matching.

        Args:
            query: The search query string
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of ResearchSpace entities matching the search
        """

    @abstractmethod
    def slug_exists(self, slug: str) -> bool:
        """
        Check if a slug already exists.

        Args:
            slug: The slug to check

        Returns:
            True if slug exists, False otherwise
        """

    @abstractmethod
    def delete(self, space_id: UUID) -> bool:
        """
        Delete a research space from the repository.

        Args:
            space_id: The ID of the space to delete

        Returns:
            True if deleted, False if not found
        """

    @abstractmethod
    def exists(self, space_id: UUID) -> bool:
        """
        Check if a research space exists.

        Args:
            space_id: The ID to check

        Returns:
            True if exists, False otherwise
        """

    @abstractmethod
    def count_by_owner(self, owner_id: UUID) -> int:
        """
        Count the number of spaces owned by a user.

        Args:
            owner_id: The user ID

        Returns:
            The count of spaces owned by the user
        """


class ResearchSpaceMembershipRepository(ABC):
    """
    Abstract repository for ResearchSpaceMembership entities.

    Defines the interface for CRUD operations and specialized queries
    related to research space memberships.
    """

    @abstractmethod
    def save(self, membership: ResearchSpaceMembership) -> ResearchSpaceMembership:
        """
        Save a membership to the repository.

        Args:
            membership: The ResearchSpaceMembership entity to save

        Returns:
            The saved ResearchSpaceMembership with any generated fields populated
        """

    @abstractmethod
    def find_by_id(self, membership_id: UUID) -> ResearchSpaceMembership | None:
        """
        Find a membership by its ID.

        Args:
            membership_id: The unique identifier of the membership

        Returns:
            The ResearchSpaceMembership if found, None otherwise
        """

    @abstractmethod
    def find_by_space(
        self,
        space_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """
        Find all memberships for a research space.

        Args:
            space_id: The research space ID
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of ResearchSpaceMembership entities for the space
        """

    @abstractmethod
    def find_by_user(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """
        Find all memberships for a user.

        Args:
            user_id: The user ID
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of ResearchSpaceMembership entities for the user
        """

    @abstractmethod
    def find_by_space_and_user(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> ResearchSpaceMembership | None:
        """
        Find membership for a specific space and user.

        Args:
            space_id: The research space ID
            user_id: The user ID

        Returns:
            The ResearchSpaceMembership if found, None otherwise
        """

    @abstractmethod
    def find_pending_invitations(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """
        Find pending invitations for a user.

        Args:
            user_id: The user ID
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of pending ResearchSpaceMembership invitations
        """

    @abstractmethod
    def find_by_role(
        self,
        space_id: UUID,
        role: MembershipRole,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpaceMembership]:
        """
        Find memberships with a specific role in a space.

        Args:
            space_id: The research space ID
            role: The role to filter by
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of ResearchSpaceMembership entities with the specified role
        """

    @abstractmethod
    def update_role(
        self,
        membership_id: UUID,
        role: MembershipRole,
    ) -> ResearchSpaceMembership | None:
        """
        Update the role of a membership.

        Args:
            membership_id: The ID of the membership to update
            role: The new role

        Returns:
            The updated ResearchSpaceMembership if found, None otherwise
        """

    @abstractmethod
    def accept_invitation(
        self,
        membership_id: UUID,
    ) -> ResearchSpaceMembership | None:
        """
        Accept a pending invitation.

        Args:
            membership_id: The ID of the membership invitation

        Returns:
            The updated ResearchSpaceMembership if found, None otherwise
        """

    @abstractmethod
    def delete(self, membership_id: UUID) -> bool:
        """
        Delete a membership from the repository.

        Args:
            membership_id: The ID of the membership to delete

        Returns:
            True if deleted, False if not found
        """

    @abstractmethod
    def exists(self, membership_id: UUID) -> bool:
        """
        Check if a membership exists.

        Args:
            membership_id: The ID to check

        Returns:
            True if exists, False otherwise
        """

    @abstractmethod
    def count_by_space(self, space_id: UUID) -> int:
        """
        Count active members in a research space.

        Args:
            space_id: The research space ID

        Returns:
            The count of active members
        """

    @abstractmethod
    def is_user_member(self, space_id: UUID, user_id: UUID) -> bool:
        """
        Check if a user is a member of a research space.

        Args:
            space_id: The research space ID
            user_id: The user ID

        Returns:
            True if user is a member, False otherwise
        """

    @abstractmethod
    def get_user_role(
        self,
        space_id: UUID,
        user_id: UUID,
    ) -> MembershipRole | None:
        """
        Get user's role in a research space.

        Args:
            space_id: The research space ID
            user_id: The user ID

        Returns:
            The user's role if found, None otherwise
        """
