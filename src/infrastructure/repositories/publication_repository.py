"""SQLAlchemy repository for publication entities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import desc, func, select

from src.domain.repositories.publication_repository import (
    PublicationRepository as PublicationRepositoryInterface,
)
from src.infrastructure.mappers.publication_mapper import PublicationMapper
from src.infrastructure.repositories._publication_repository_query_mixins import (
    _PublicationRepositoryQueryMixin,
)
from src.models.database.publication import PublicationModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.orm import Session

    from src.domain.entities.publication import Publication
    from src.type_definitions.common import PublicationUpdate


class SqlAlchemyPublicationRepository(
    _PublicationRepositoryQueryMixin,
    PublicationRepositoryInterface,
):
    """SQLAlchemy-backed repository for publication records."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        """Return the configured SQLAlchemy session."""
        if self._session is None:
            message = "Session is not configured"
            raise ValueError(message)
        return self._session

    def get_by_id(self, entity_id: int) -> Publication | None:
        model = self.session.get(PublicationModel, entity_id)
        return PublicationMapper.to_domain(model) if model else None

    def find_all(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[Publication]:
        stmt = select(PublicationModel).order_by(
            desc(PublicationModel.publication_year),
            desc(PublicationModel.id),
        )
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        models = list(self.session.execute(stmt).scalars())
        return PublicationMapper.to_domain_sequence(models)

    def exists(self, entity_id: int) -> bool:
        return self.session.get(PublicationModel, entity_id) is not None

    def count(self) -> int:
        stmt = select(func.count()).select_from(PublicationModel)
        return int(self.session.execute(stmt).scalar_one())

    def create(self, entity: Publication) -> Publication:
        model = PublicationMapper.to_model(entity)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return PublicationMapper.to_domain(model)

    def update(self, entity_id: int, updates: PublicationUpdate) -> Publication:
        model = self.session.get(PublicationModel, entity_id)
        if model is None:
            message = f"Publication {entity_id} not found"
            raise ValueError(message)

        self._apply_updates(model=model, updates=updates)
        model.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(model)
        return PublicationMapper.to_domain(model)

    def delete(self, entity_id: int) -> bool:
        model = self.session.get(PublicationModel, entity_id)
        if model is None:
            return False
        self.session.delete(model)
        self.session.commit()
        return True


__all__ = ["SqlAlchemyPublicationRepository"]
