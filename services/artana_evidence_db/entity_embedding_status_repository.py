"""Persistence adapter for graph-owned entity embedding readiness state."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.embedding_models import (
    KernelEntityEmbeddingState,
    KernelEntityEmbeddingStatus,
)
from artana_evidence_db.entity_embedding_status_model import EntityEmbeddingStatusModel
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class SqlAlchemyEntityEmbeddingStatusRepository:
    """Persist and query graph-owned embedding readiness records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_status(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> KernelEntityEmbeddingStatus | None:
        model = self._session.get(
            EntityEmbeddingStatusModel,
            {
                "research_space_id": _as_uuid(research_space_id),
                "entity_id": _as_uuid(entity_id),
            },
        )
        return (
            KernelEntityEmbeddingStatus.model_validate(model)
            if model is not None
            else None
        )

    def list_statuses(
        self,
        *,
        research_space_id: str,
        entity_ids: list[str] | None = None,
        states: Iterable[KernelEntityEmbeddingState] | None = None,
        limit: int | None = None,
    ) -> list[KernelEntityEmbeddingStatus]:
        stmt = select(EntityEmbeddingStatusModel).where(
            EntityEmbeddingStatusModel.research_space_id == _as_uuid(research_space_id),
        )
        if entity_ids:
            stmt = stmt.where(
                EntityEmbeddingStatusModel.entity_id.in_(
                    [_as_uuid(entity_id) for entity_id in entity_ids],
                ),
            )
        if states:
            stmt = stmt.where(
                EntityEmbeddingStatusModel.state.in_([state.value for state in states]),
            )
        stmt = stmt.order_by(
            EntityEmbeddingStatusModel.last_requested_at.desc(),
            EntityEmbeddingStatusModel.entity_id.asc(),
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        models = self._session.scalars(stmt).all()
        return [KernelEntityEmbeddingStatus.model_validate(model) for model in models]

    def upsert_status(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_id: str,
        state: KernelEntityEmbeddingState,
        desired_fingerprint: str,
        embedding_model: str,
        embedding_version: int,
        last_requested_at: datetime | None = None,
        last_attempted_at: datetime | None = None,
        last_refreshed_at: datetime | None = None,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
    ) -> KernelEntityEmbeddingStatus:
        resolved_requested_at = last_requested_at or datetime.now(UTC)
        model = self._session.get(
            EntityEmbeddingStatusModel,
            {
                "research_space_id": _as_uuid(research_space_id),
                "entity_id": _as_uuid(entity_id),
            },
        )
        if model is None:
            model = EntityEmbeddingStatusModel(
                research_space_id=_as_uuid(research_space_id),
                entity_id=_as_uuid(entity_id),
                state=state.value,
                desired_fingerprint=desired_fingerprint,
                embedding_model=embedding_model,
                embedding_version=embedding_version,
                last_requested_at=resolved_requested_at,
                last_attempted_at=last_attempted_at,
                last_refreshed_at=last_refreshed_at,
                last_error_code=last_error_code,
                last_error_message=last_error_message,
            )
            self._session.add(model)
            self._session.flush()
            return KernelEntityEmbeddingStatus.model_validate(model)

        model.state = state.value
        model.desired_fingerprint = desired_fingerprint
        model.embedding_model = embedding_model
        model.embedding_version = embedding_version
        model.last_requested_at = resolved_requested_at
        model.last_attempted_at = last_attempted_at
        model.last_refreshed_at = last_refreshed_at
        model.last_error_code = last_error_code
        model.last_error_message = last_error_message
        self._session.flush()
        return KernelEntityEmbeddingStatus.model_validate(model)


__all__ = ["SqlAlchemyEntityEmbeddingStatusRepository"]
