from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import asc, func, select
from sqlalchemy.exc import IntegrityError

from src.domain.repositories.extraction_queue_repository import (
    ExtractionQueueRepository as ExtractionQueueRepositoryInterface,
)
from src.infrastructure.mappers.extraction_queue_mapper import ExtractionQueueMapper
from src.models.database.extraction_queue import (
    ExtractionQueueItemModel,
    ExtractionStatusEnum,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.domain.entities.extraction_queue_item import ExtractionQueueItem
    from src.domain.repositories.base import QuerySpecification
    from src.type_definitions.common import ExtractionQueueUpdate, JSONObject


class SqlAlchemyExtractionQueueRepository(
    ExtractionQueueRepositoryInterface,
):
    """SQLAlchemy-backed repository for extraction queue items."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session is not configured"
            raise ValueError(message)
        return self._session

    def _to_domain(
        self,
        model: ExtractionQueueItemModel | None,
    ) -> ExtractionQueueItem | None:
        return ExtractionQueueMapper.to_domain(model) if model else None

    def _to_domain_sequence(
        self,
        models: list[ExtractionQueueItemModel],
    ) -> list[ExtractionQueueItem]:
        return ExtractionQueueMapper.to_domain_sequence(models)

    def create(self, entity: ExtractionQueueItem) -> ExtractionQueueItem:
        model = ExtractionQueueMapper.to_model(entity)
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return ExtractionQueueMapper.to_domain(model)

    def enqueue_many(
        self,
        items: list[ExtractionQueueItem],
    ) -> list[ExtractionQueueItem]:
        created: list[ExtractionQueueItem] = []
        for item in items:
            model = ExtractionQueueMapper.to_model(item)
            self.session.add(model)
            try:
                self.session.commit()
                self.session.refresh(model)
                created.append(ExtractionQueueMapper.to_domain(model))
            except IntegrityError:
                self.session.rollback()
        return created

    def get_by_id(self, entity_id: UUID) -> ExtractionQueueItem | None:
        model = self.session.get(ExtractionQueueItemModel, str(entity_id))
        return self._to_domain(model)

    def find_all(
        self,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[ExtractionQueueItem]:
        stmt = select(ExtractionQueueItemModel)
        if offset:
            stmt = stmt.offset(offset)
        if limit:
            stmt = stmt.limit(limit)
        models = list(self.session.execute(stmt).scalars())
        return self._to_domain_sequence(models)

    def exists(self, entity_id: UUID) -> bool:
        return self.session.get(ExtractionQueueItemModel, str(entity_id)) is not None

    def count(self) -> int:
        stmt = select(func.count()).select_from(ExtractionQueueItemModel)
        return int(self.session.execute(stmt).scalar_one())

    def update(
        self,
        entity_id: UUID,
        updates: ExtractionQueueUpdate,
    ) -> ExtractionQueueItem:
        model = self.session.get(ExtractionQueueItemModel, str(entity_id))
        if model is None:
            message = f"Extraction queue item {entity_id} not found"
            raise ValueError(message)
        field_map = {"metadata": "metadata_payload"}
        for field, value in updates.items():
            target_field = field_map.get(field, field)
            if hasattr(model, target_field):
                if target_field == "status" and isinstance(value, str):
                    setattr(model, target_field, ExtractionStatusEnum(value))
                    continue
                setattr(model, target_field, value)
        model.updated_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(model)
        return ExtractionQueueMapper.to_domain(model)

    def delete(self, entity_id: UUID) -> bool:
        model = self.session.get(ExtractionQueueItemModel, str(entity_id))
        if model is None:
            return False
        self.session.delete(model)
        self.session.commit()
        return True

    def find_by_criteria(
        self,
        spec: QuerySpecification,
    ) -> list[ExtractionQueueItem]:
        stmt = select(ExtractionQueueItemModel)
        for field, value in spec.filters.items():
            column = getattr(ExtractionQueueItemModel, field, None)
            if column is not None and value is not None:
                stmt = stmt.where(column == value)
        if spec.sort_by:
            column = getattr(ExtractionQueueItemModel, spec.sort_by, None)
            if column is not None:
                stmt = stmt.order_by(asc(column))
        if spec.offset:
            stmt = stmt.offset(spec.offset)
        if spec.limit:
            stmt = stmt.limit(spec.limit)
        models = list(self.session.execute(stmt).scalars())
        return self._to_domain_sequence(models)

    def list_pending(
        self,
        limit: int,
        *,
        source_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
    ) -> list[ExtractionQueueItem]:
        stmt = select(ExtractionQueueItemModel).where(
            ExtractionQueueItemModel.status == ExtractionStatusEnum.PENDING,
        )
        if source_id:
            stmt = stmt.where(ExtractionQueueItemModel.source_id == str(source_id))
        if ingestion_job_id:
            stmt = stmt.where(
                ExtractionQueueItemModel.ingestion_job_id == str(ingestion_job_id),
            )
        stmt = stmt.order_by(ExtractionQueueItemModel.queued_at.asc()).limit(limit)
        models = list(self.session.execute(stmt).scalars())
        return self._to_domain_sequence(models)

    def claim_pending(
        self,
        limit: int,
        *,
        source_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
    ) -> list[ExtractionQueueItem]:
        stmt = select(ExtractionQueueItemModel).where(
            ExtractionQueueItemModel.status == ExtractionStatusEnum.PENDING,
        )
        if source_id:
            stmt = stmt.where(ExtractionQueueItemModel.source_id == str(source_id))
        if ingestion_job_id:
            stmt = stmt.where(
                ExtractionQueueItemModel.ingestion_job_id == str(ingestion_job_id),
            )
        stmt = (
            stmt.order_by(ExtractionQueueItemModel.queued_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        models = list(self.session.execute(stmt).scalars())
        now = datetime.now(UTC)
        for model in models:
            model.status = ExtractionStatusEnum.PROCESSING
            model.attempts = (model.attempts or 0) + 1
            model.started_at = now
            model.updated_at = now
        if models:
            self.session.commit()
        return self._to_domain_sequence(models)

    def mark_completed(
        self,
        item_id: UUID,
        *,
        metadata: JSONObject | None = None,
    ) -> ExtractionQueueItem:
        model = self.session.get(ExtractionQueueItemModel, str(item_id))
        if model is None:
            message = f"Extraction queue item {item_id} not found"
            raise ValueError(message)
        payload: JSONObject = dict(model.metadata_payload or {})
        if metadata:
            payload.update(metadata)
        model.status = ExtractionStatusEnum.COMPLETED
        model.completed_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)
        model.last_error = None
        model.metadata_payload = payload
        self.session.commit()
        self.session.refresh(model)
        return ExtractionQueueMapper.to_domain(model)

    def mark_failed(
        self,
        item_id: UUID,
        *,
        error_message: str,
    ) -> ExtractionQueueItem:
        model = self.session.get(ExtractionQueueItemModel, str(item_id))
        if model is None:
            message = f"Extraction queue item {item_id} not found"
            raise ValueError(message)
        model.status = ExtractionStatusEnum.FAILED
        model.completed_at = datetime.now(UTC)
        model.updated_at = datetime.now(UTC)
        model.last_error = error_message
        self.session.commit()
        self.session.refresh(model)
        return ExtractionQueueMapper.to_domain(model)


__all__ = ["SqlAlchemyExtractionQueueRepository"]
