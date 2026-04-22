from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import asc, func, select

from src.domain.repositories.publication_extraction_repository import (
    PublicationExtractionRepository as PublicationExtractionRepositoryInterface,
)
from src.infrastructure.mappers.publication_extraction_mapper import (
    PublicationExtractionMapper,
)
from src.models.database.publication_extraction import (
    ExtractionOutcomeEnum,
    PublicationExtractionModel,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.sql import ColumnElement

    from src.domain.entities.publication_extraction import PublicationExtraction
    from src.domain.repositories.base import QuerySpecification
    from src.type_definitions.common import PublicationExtractionUpdate


class SqlAlchemyPublicationExtractionRepository(
    PublicationExtractionRepositoryInterface,
):
    """SQLAlchemy-backed repository for publication extraction outputs."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session is not configured"
            raise ValueError(message)
        return self._session

    def create(self, entity: PublicationExtraction) -> PublicationExtraction:
        model = PublicationExtractionMapper.to_model(entity)
        self.session.add(model)
        try:
            self.session.commit()
            self.session.refresh(model)
        except Exception:
            self.session.rollback()
            raise
        return PublicationExtractionMapper.to_domain(model)

    def get_by_id(self, entity_id: UUID) -> PublicationExtraction | None:
        model = self.session.get(PublicationExtractionModel, str(entity_id))
        return PublicationExtractionMapper.to_domain(model) if model else None

    def find_by_publication_id(
        self,
        publication_id: int,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[PublicationExtraction]:
        stmt = select(PublicationExtractionModel).where(
            PublicationExtractionModel.publication_id == publication_id,
        )
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        models = list(self.session.execute(stmt).scalars())
        return [PublicationExtractionMapper.to_domain(model) for model in models]

    def find_by_queue_item_id(
        self,
        queue_item_id: UUID,
    ) -> PublicationExtraction | None:
        stmt = select(PublicationExtractionModel).where(
            PublicationExtractionModel.queue_item_id == str(queue_item_id),
        )
        model = self.session.execute(stmt).scalar_one_or_none()
        return PublicationExtractionMapper.to_domain(model) if model else None

    def find_all(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[PublicationExtraction]:
        stmt = select(PublicationExtractionModel)
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        models = list(self.session.execute(stmt).scalars())
        return [PublicationExtractionMapper.to_domain(model) for model in models]

    def exists(self, entity_id: UUID) -> bool:
        return self.session.get(PublicationExtractionModel, str(entity_id)) is not None

    def count(self) -> int:
        stmt = select(func.count()).select_from(PublicationExtractionModel)
        return int(self.session.execute(stmt).scalar_one())

    def update(
        self,
        entity_id: UUID,
        updates: PublicationExtractionUpdate,
    ) -> PublicationExtraction:
        model = self.session.get(PublicationExtractionModel, str(entity_id))
        if model is None:
            message = f"Publication extraction {entity_id} not found"
            raise ValueError(message)
        field_map = {"metadata": "metadata_payload"}
        for field, value in updates.items():
            target_field = field_map.get(field, field)
            if not hasattr(model, target_field):
                continue
            if target_field == "status" and isinstance(value, str):
                setattr(model, target_field, ExtractionOutcomeEnum(value))
                continue
            setattr(model, target_field, value)
        try:
            self.session.commit()
            self.session.refresh(model)
        except Exception:
            self.session.rollback()
            raise
        return PublicationExtractionMapper.to_domain(model)

    def delete(self, entity_id: UUID) -> bool:
        model = self.session.get(PublicationExtractionModel, str(entity_id))
        if model is None:
            return False
        self.session.delete(model)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return True

    def find_by_criteria(
        self,
        spec: QuerySpecification,
    ) -> list[PublicationExtraction]:
        stmt = select(PublicationExtractionModel)
        filters = _build_filters(spec)
        if filters:
            stmt = stmt.where(*filters)
        if spec.sort_by:
            column = getattr(PublicationExtractionModel, spec.sort_by, None)
            if column is not None:
                stmt = stmt.order_by(
                    asc(column) if spec.sort_order != "desc" else column.desc(),
                )
        if spec.offset:
            stmt = stmt.offset(spec.offset)
        if spec.limit:
            stmt = stmt.limit(spec.limit)
        models = list(self.session.execute(stmt).scalars())
        return [PublicationExtractionMapper.to_domain(model) for model in models]

    def count_by_criteria(self, spec: QuerySpecification) -> int:
        stmt = select(func.count()).select_from(PublicationExtractionModel)
        filters = _build_filters(spec)
        if filters:
            stmt = stmt.where(*filters)
        return int(self.session.execute(stmt).scalar_one())


def _build_filters(
    spec: QuerySpecification,
) -> list[ColumnElement[bool]]:
    filters: list[ColumnElement[bool]] = []
    for field, value in spec.filters.items():
        column = getattr(PublicationExtractionModel, field, None)
        if column is None or value is None:
            continue
        normalized_value = _normalize_filter_value(field, value)
        filters.append(column == normalized_value)
    return filters


def _normalize_filter_value(
    field: str,
    value: str | float | bool | None | UUID,
) -> str | int | float | bool | None | ExtractionOutcomeEnum:
    if field == "status" and isinstance(value, str):
        return ExtractionOutcomeEnum(value)
    if field in {"source_id", "ingestion_job_id", "queue_item_id"} and not isinstance(
        value,
        str,
    ):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    return value


__all__ = ["SqlAlchemyPublicationExtractionRepository"]
