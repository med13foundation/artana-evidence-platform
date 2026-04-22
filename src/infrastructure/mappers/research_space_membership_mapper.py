"""
Mapper for ResearchSpaceMembership entities and database models.

Provides bidirectional mapping between domain entities and database models
for the Research Spaces module with strong type safety.
"""

from uuid import UUID

from src.domain.entities.research_space_membership import (
    MembershipRole,
    ResearchSpaceMembership,
)
from src.models.database.research_space import (
    MembershipRoleEnum,
    ResearchSpaceMembershipModel,
)


class ResearchSpaceMembershipMapper:
    """
    Bidirectional mapper between ResearchSpaceMembership domain entities and database models.

    Handles conversion between domain objects and database representations,
    ensuring type safety and data integrity.
    """

    @staticmethod
    def to_domain(
        model: ResearchSpaceMembershipModel | None,
    ) -> ResearchSpaceMembership | None:
        """
        Convert a database model to a domain entity.

        Args:
            model: The ResearchSpaceMembershipModel to convert

        Returns:
            The corresponding ResearchSpaceMembership domain entity, or None if model is None
        """
        if model is None:
            return None

        # Type-safe conversion with explicit type handling
        membership_id = UUID(model.id) if isinstance(model.id, str) else model.id
        space_id = (
            UUID(model.space_id) if isinstance(model.space_id, str) else model.space_id
        )
        user_id = (
            UUID(model.user_id) if isinstance(model.user_id, str) else model.user_id
        )
        role_value = (
            model.role.value if hasattr(model.role, "value") else str(model.role)
        )
        invited_by_uuid = (
            UUID(model.invited_by)
            if model.invited_by and isinstance(model.invited_by, str)
            else (model.invited_by if model.invited_by else None)
        )

        return ResearchSpaceMembership(
            id=membership_id,
            space_id=space_id,
            user_id=user_id,
            role=MembershipRole(role_value),
            invited_by=invited_by_uuid,
            invited_at=model.invited_at,
            joined_at=model.joined_at,
            is_active=bool(model.is_active),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: ResearchSpaceMembership) -> ResearchSpaceMembershipModel:
        """
        Convert a domain entity to a database model.

        Args:
            entity: The ResearchSpaceMembership entity to convert

        Returns:
            The corresponding ResearchSpaceMembershipModel with proper type conversions
        """
        # Type-safe conversion ensuring all fields are properly typed
        # Note: PGUUID(as_uuid=True) expects UUID objects, not strings
        return ResearchSpaceMembershipModel(
            id=entity.id,  # UUID object
            space_id=entity.space_id,  # UUID object
            user_id=entity.user_id,  # UUID object
            role=MembershipRoleEnum(entity.role.value),
            invited_by=entity.invited_by,  # UUID object or None
            invited_at=entity.invited_at,
            joined_at=entity.joined_at,
            is_active=bool(entity.is_active),
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
