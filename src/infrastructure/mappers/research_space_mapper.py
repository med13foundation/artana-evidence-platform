"""
Mapper for ResearchSpace entities and database models.

Provides bidirectional mapping between domain entities and database models
for the Research Spaces module with strong type safety.
"""

from uuid import UUID

from src.domain.entities.research_space import ResearchSpace, SpaceStatus
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum
from src.type_definitions.common import JSONObject  # noqa: TC001


class ResearchSpaceMapper:
    """
    Bidirectional mapper between ResearchSpace domain entities and database models.

    Handles conversion between domain objects and database representations,
    ensuring type safety and data integrity.
    """

    @staticmethod
    def to_domain(model: ResearchSpaceModel | None) -> ResearchSpace | None:
        """
        Convert a database model to a domain entity.

        Args:
            model: The ResearchSpaceModel to convert

        Returns:
            The corresponding ResearchSpace domain entity, or None if model is None
        """
        if model is None:
            return None

        # Type-safe conversion with explicit type handling
        space_id = UUID(model.id) if isinstance(model.id, str) else model.id
        owner_id = (
            UUID(model.owner_id) if isinstance(model.owner_id, str) else model.owner_id
        )
        status_value = (
            model.status.value if hasattr(model.status, "value") else str(model.status)
        )
        settings_dict: JSONObject = dict(model.settings) if model.settings else {}
        tags_list = [t.replace("_", "-") for t in model.tags] if model.tags else []

        return ResearchSpace(
            id=space_id,
            slug=str(model.slug),
            name=str(model.name),
            description=str(model.description),
            owner_id=owner_id,
            status=SpaceStatus(status_value),
            settings=settings_dict,
            tags=tags_list,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: ResearchSpace) -> ResearchSpaceModel:
        """
        Convert a domain entity to a database model.

        Args:
            entity: The ResearchSpace entity to convert

        Returns:
            The corresponding ResearchSpaceModel with proper type conversions
        """
        # Type-safe conversion ensuring all fields are properly typed
        # Note: PGUUID(as_uuid=True) expects UUID objects, not strings
        return ResearchSpaceModel(
            id=entity.id,  # UUID object
            slug=str(entity.slug),
            name=str(entity.name),
            description=str(entity.description),
            owner_id=entity.owner_id,  # UUID object
            status=SpaceStatusEnum(entity.status.value),
            settings=entity.settings,
            tags=entity.tags,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
