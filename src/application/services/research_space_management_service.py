"""
Application service for research space management.

Orchestrates domain services and repositories to implement
research space management use cases with proper business logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from src.domain.entities.research_space import ResearchSpace, SpaceStatus
from src.domain.entities.user import User, UserRole
from src.domain.repositories.research_space_repository import (
    ResearchSpaceRepository,
)
from src.type_definitions.common import JSONObject

if TYPE_CHECKING:
    from src.domain.ports.space_lifecycle_sync_port import SpaceLifecycleSyncPort


@dataclass
class CreateSpaceRequest:
    """Request model for creating a new research space."""

    owner_id: UUID
    name: str
    slug: str
    description: str = ""
    settings: JSONObject | None = None
    tags: list[str] | None = None

    def __post_init__(self) -> None:
        """Normalize fields after initialization."""
        if self.settings is None:
            self.settings = {}
        if self.tags is None:
            self.tags = []


class UpdateSpaceRequest:
    """Request model for updating a research space."""

    def __init__(
        self,
        name: str | None = None,
        description: str | None = None,
        settings: JSONObject | None = None,
        tags: list[str] | None = None,
        status: SpaceStatus | None = None,
    ):
        self.name = name
        self.description = description
        self.settings = settings
        self.tags = tags
        self.status = status


class ResearchSpaceManagementService:
    """
    Application service for research space management.

    Orchestrates research space operations including creation, configuration,
    lifecycle management, and access control.
    """

    def __init__(
        self,
        research_space_repository: ResearchSpaceRepository,
        space_lifecycle_sync: SpaceLifecycleSyncPort | None = None,
    ):
        """
        Initialize the research space management service.

        Args:
            research_space_repository: Repository for research spaces
        """
        self._space_repository = research_space_repository
        self._space_lifecycle_sync = space_lifecycle_sync

    def _sync_space(self, space: ResearchSpace) -> None:
        if self._space_lifecycle_sync is None:
            return
        self._space_lifecycle_sync.sync_space(space)

    def create_space(self, request: CreateSpaceRequest) -> ResearchSpace:
        """
        Create a new research space.

        Args:
            request: Creation request with space details

        Returns:
            The created ResearchSpace entity

        Raises:
            ValueError: If validation fails or slug already exists
        """
        # Check if slug already exists
        if self._space_repository.slug_exists(request.slug):
            msg = f"Slug '{request.slug}' already exists"
            raise ValueError(msg)

        settings = self._normalize_settings(request.settings)
        # Create the space entity
        space = ResearchSpace(
            id=uuid4(),  # Generate new UUID
            slug=request.slug,
            name=request.name,
            description=request.description,
            owner_id=request.owner_id,
            status=SpaceStatus.ACTIVE,
            settings=settings,
            tags=request.tags or [],
        )

        saved_space = self._space_repository.save(space)
        self._sync_space(saved_space)
        return saved_space

    def get_space(
        self,
        space_id: UUID,
        user_id: UUID | None = None,  # noqa: ARG002
    ) -> ResearchSpace | None:
        """
        Get a research space by ID.

        Args:
            space_id: The space ID
            user_id: Optional user filter for authorization checks (reserved for future use)

        Returns:
            The ResearchSpace if found, None otherwise
        """
        return self._space_repository.find_by_id(space_id)

    def get_space_by_slug(
        self,
        slug: str,
        user_id: UUID | None = None,  # noqa: ARG002
    ) -> ResearchSpace | None:
        """
        Get a research space by slug.

        Args:
            slug: The space slug
            user_id: Optional user filter for authorization checks

        Returns:
            The ResearchSpace if found, None otherwise
        """
        return self._space_repository.find_by_slug(slug)

    def get_user_spaces(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """
        Get all research spaces owned by a user.

        Args:
            owner_id: The user ID
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of user's research spaces
        """
        return self._space_repository.find_by_owner(owner_id, skip, limit)

    def update_space(
        self,
        space_id: UUID,
        request: UpdateSpaceRequest,
        user: User,
    ) -> ResearchSpace | None:
        """
        Update a research space.

        Args:
            space_id: The space ID
            request: Update request
            user: The user making the request (for authorization)

        Returns:
            The updated ResearchSpace if successful, None if not found or not authorized
        """
        space = self._space_repository.find_by_id(space_id)
        if not space:
            return None

        # Check authorization - owner or platform admin can update
        if not (space.can_be_modified_by(user.id) or user.role == UserRole.ADMIN):
            return None

        # Apply updates using immutable pattern
        updated_space = space
        if request.name is not None:
            updated_space = updated_space.model_copy(update={"name": request.name})
        if request.description is not None:
            updated_space = updated_space.model_copy(
                update={"description": request.description},
            )
        if request.settings is not None:
            updated_space = updated_space.with_settings(
                self._normalize_settings(request.settings),
            )
        if request.tags is not None:
            updated_space = updated_space.with_tags(request.tags)
        if request.status is not None:
            updated_space = updated_space.with_status(request.status)

        # Update timestamp
        updated_space = updated_space.with_updated_at()

        saved_space = self._space_repository.save(updated_space)
        self._sync_space(saved_space)
        return saved_space

    def delete_space(self, space_id: UUID, user: User) -> bool:
        """
        Delete a research space.

        Args:
            space_id: The space ID
            user: The user making the request (for authorization)

        Returns:
            True if deleted, False if not found or not authorized
        """
        space = self._space_repository.find_by_id(space_id)
        if not space:
            return False

        # Check authorization - owners and platform admins can delete.
        if not (space.can_be_modified_by(user.id) or user.role == UserRole.ADMIN):
            return False

        deleted = self._space_repository.delete(space_id)
        if not deleted:
            return False

        self._sync_space(space.with_status(SpaceStatus.ARCHIVED))
        return True

    def archive_space(self, space_id: UUID, user_id: UUID) -> ResearchSpace | None:
        """
        Archive a research space.

        Args:
            space_id: The space ID
            user_id: The user making the request

        Returns:
            The archived space if successful
        """
        space = self._space_repository.find_by_id(space_id)
        if not space or not space.can_be_modified_by(user_id):
            return None

        archived_space = space.with_status(SpaceStatus.ARCHIVED)
        saved_space = self._space_repository.save(archived_space)
        self._sync_space(saved_space)
        return saved_space

    def activate_space(self, space_id: UUID, user_id: UUID) -> ResearchSpace | None:
        """
        Activate a research space.

        Args:
            space_id: The space ID
            user_id: The user making the request

        Returns:
            The activated space if successful
        """
        space = self._space_repository.find_by_id(space_id)
        if not space or not space.can_be_modified_by(user_id):
            return None

        activated_space = space.with_status(SpaceStatus.ACTIVE)
        saved_space = self._space_repository.save(activated_space)
        self._sync_space(saved_space)
        return saved_space

    def get_active_spaces(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """
        Get all active research spaces.

        Args:
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of active research spaces
        """
        return self._space_repository.find_active_spaces(skip, limit)

    def search_spaces(
        self,
        query: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """
        Search research spaces by name.

        Args:
            query: Search query
            skip: Pagination offset
            limit: Maximum results

        Returns:
            List of matching research spaces
        """
        return self._space_repository.search_by_name(query, skip, limit)

    def get_space_statistics(self, owner_id: UUID) -> JSONObject:
        """
        Get statistics about a user's research spaces.

        Args:
            owner_id: The user ID

        Returns:
            Dictionary with statistics
        """
        total_spaces = self._space_repository.count_by_owner(owner_id)
        active_spaces = len(
            self._space_repository.find_by_status(
                SpaceStatus.ACTIVE,
                skip=0,
                limit=1000,
            ),
        )

        return {
            "total_spaces": total_spaces,
            "active_spaces": active_spaces,
            "archived_spaces": total_spaces - active_spaces,
        }

    @staticmethod
    def _normalize_settings(
        settings: JSONObject | None,
    ) -> JSONObject:
        """Normalize arbitrary dicts into research space settings dict."""
        normalized = dict(settings or {})
        raw_policy = normalized.get("relation_auto_promotion")
        policy = dict(raw_policy) if isinstance(raw_policy, dict) else {}
        if not isinstance(policy.get("enabled"), bool):
            policy["enabled"] = False
        normalized["relation_auto_promotion"] = policy
        return normalized

    def validate_space(self, space: ResearchSpace) -> list[str]:
        """
        Validate a research space.

        Args:
            space: The space to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Basic validation
        if not space.name.strip():
            errors.append("Space name cannot be empty")

        name_max_len = 100
        if len(space.name) > name_max_len:
            errors.append("Space name cannot exceed 100 characters")

        if not space.slug.strip():
            errors.append("Space slug cannot be empty")

        slug_max_len = 50
        if len(space.slug) > slug_max_len:
            errors.append("Space slug cannot exceed 50 characters")

        # Slug format validation (handled by domain entity, but check here too)
        if not re.match(r"^[a-z0-9-]+$", space.slug):
            errors.append(
                "Slug must contain only lowercase letters, numbers, and hyphens",
            )

        desc_max_len = 500
        if len(space.description) > desc_max_len:
            errors.append("Space description cannot exceed 500 characters")

        return errors
