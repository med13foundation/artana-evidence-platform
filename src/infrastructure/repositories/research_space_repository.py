"""
SQLAlchemy implementation of Research Space repository for Artana Resource Library.

Data access layer for research spaces with specialized queries
and efficient database operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import desc, func, select

from src.domain.entities.research_space import ResearchSpace, SpaceStatus
from src.domain.repositories.research_space_repository import (
    ResearchSpaceRepository as ResearchSpaceRepositoryInterface,
)
from src.infrastructure.mappers.research_space_mapper import ResearchSpaceMapper
from src.models.database.research_space import ResearchSpaceModel, SpaceStatusEnum

if TYPE_CHECKING:  # pragma: no cover - typing only
    from uuid import UUID

    from sqlalchemy.orm import Session


class SqlAlchemyResearchSpaceRepository(ResearchSpaceRepositoryInterface):
    """
    Repository for ResearchSpace entities with specialized space queries.

    Provides data access operations for research spaces including
    ownership-based filtering, status queries, and slug lookups.
    """

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """Get the current database session."""
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session

    def save(self, space: ResearchSpace) -> ResearchSpace:
        """Save a research space to the repository."""
        existing_model: ResearchSpaceModel | None = self.session.get(
            ResearchSpaceModel,
            space.id,
        )

        if existing_model is None:
            model = ResearchSpaceMapper.to_model(space)
            self.session.add(model)
        else:
            # Update existing row in place to avoid duplicate primary keys
            existing_model.slug = space.slug
            existing_model.name = space.name
            existing_model.description = space.description
            existing_model.owner_id = str(space.owner_id)
            existing_model.status = SpaceStatusEnum(space.status.value)
            existing_model.settings = space.settings
            existing_model.tags = space.tags
            existing_model.updated_at = space.updated_at
            model = existing_model

        self.session.commit()
        self.session.refresh(model)
        domain_space = ResearchSpaceMapper.to_domain(model)
        if domain_space is None:
            message = "Failed to convert model to domain entity"
            raise ValueError(message)
        return domain_space

    def find_by_id(self, space_id: UUID) -> ResearchSpace | None:
        """Find a research space by its ID."""
        stmt = select(ResearchSpaceModel).where(
            ResearchSpaceModel.id == space_id,
        )
        result = self.session.execute(stmt).scalar_one_or_none()
        return ResearchSpaceMapper.to_domain(result) if result else None

    def find_by_slug(self, slug: str) -> ResearchSpace | None:
        """Find a research space by its slug."""
        stmt = select(ResearchSpaceModel).where(ResearchSpaceModel.slug == slug)
        result = self.session.execute(stmt).scalar_one_or_none()
        return ResearchSpaceMapper.to_domain(result) if result else None

    def find_by_owner(
        self,
        owner_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """Find all spaces owned by a specific user."""
        stmt = (
            select(ResearchSpaceModel)
            .where(ResearchSpaceModel.owner_id == owner_id)
            .order_by(desc(ResearchSpaceModel.created_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [
            domain_space
            for model in results
            if (domain_space := ResearchSpaceMapper.to_domain(model)) is not None
        ]

    def find_by_status(
        self,
        status: SpaceStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """Find all spaces with a specific status."""
        status_enum = SpaceStatusEnum(status.value)
        stmt = (
            select(ResearchSpaceModel)
            .where(ResearchSpaceModel.status == status_enum)
            .order_by(desc(ResearchSpaceModel.created_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [
            domain_space
            for model in results
            if (domain_space := ResearchSpaceMapper.to_domain(model)) is not None
        ]

    def find_active_spaces(
        self,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """Find all active research spaces."""
        return self.find_by_status(SpaceStatus.ACTIVE, skip=skip, limit=limit)

    def search_by_name(
        self,
        query: str,
        skip: int = 0,
        limit: int = 50,
    ) -> list[ResearchSpace]:
        """Search research spaces by name using fuzzy matching."""
        search_pattern = f"%{query}%"
        stmt = (
            select(ResearchSpaceModel)
            .where(ResearchSpaceModel.name.ilike(search_pattern))
            .order_by(desc(ResearchSpaceModel.created_at))
            .offset(skip)
            .limit(limit)
        )
        results = self.session.execute(stmt).scalars().all()
        return [
            domain_space
            for model in results
            if (domain_space := ResearchSpaceMapper.to_domain(model)) is not None
        ]

    def slug_exists(self, slug: str) -> bool:
        """Check if a slug already exists."""
        stmt = select(func.count()).where(ResearchSpaceModel.slug == slug)
        count = self.session.execute(stmt).scalar_one()
        return int(count) > 0

    def delete(self, space_id: UUID) -> bool:
        """Delete a research space from the repository."""
        model = self.session.get(ResearchSpaceModel, space_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.commit()
        return True

    def exists(self, space_id: UUID) -> bool:
        """Check if a research space exists."""
        stmt = select(func.count()).where(ResearchSpaceModel.id == space_id)
        count = self.session.execute(stmt).scalar_one()
        return int(count) > 0

    def count_by_owner(self, owner_id: UUID) -> int:
        """Count the number of spaces owned by a user."""
        stmt = select(func.count()).where(
            ResearchSpaceModel.owner_id == owner_id,
        )
        return self.session.execute(stmt).scalar_one()
