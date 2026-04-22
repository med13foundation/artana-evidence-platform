"""Service-local SQLAlchemy repository for typed graph observations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.graph_core_models import KernelObservation
from artana_evidence_db.observation_persistence_model import ObservationModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.engine import CursorResult

if TYPE_CHECKING:
    from datetime import datetime

    from artana_evidence_db.common_types import JSONValue
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class SqlAlchemyKernelObservationRepository:
    """SQLAlchemy implementation of the kernel observation repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        subject_id: str,
        variable_id: str,
        value_numeric: float | None = None,
        value_text: str | None = None,
        value_date: datetime | None = None,
        value_coded: str | None = None,
        value_boolean: bool | None = None,
        value_json: JSONValue | None = None,
        unit: str | None = None,
        observed_at: datetime | None = None,
        provenance_id: str | None = None,
        confidence: float = 1.0,
    ) -> KernelObservation:
        obs = ObservationModel(
            id=uuid4(),
            research_space_id=_as_uuid(research_space_id),
            subject_id=_as_uuid(subject_id),
            variable_id=variable_id,
            value_numeric=value_numeric,
            value_text=value_text,
            value_date=value_date,
            value_coded=value_coded,
            value_boolean=value_boolean,
            value_json=value_json,
            unit=unit,
            observed_at=observed_at,
            provenance_id=(
                _as_uuid(provenance_id) if provenance_id is not None else None
            ),
            confidence=confidence,
        )
        self._session.add(obs)
        self._session.flush()
        return KernelObservation.model_validate(obs)

    def create_batch(
        self,
        observations: list[dict[str, object]],
    ) -> int:
        if not observations:
            return 0
        models = []
        for obs_data in observations:
            obs_data.setdefault("id", uuid4())
            for key in ("research_space_id", "subject_id", "provenance_id"):
                value = obs_data.get(key)
                if value is None:
                    continue
                if isinstance(value, UUID):
                    continue
                try:
                    obs_data[key] = _as_uuid(str(value))
                except (TypeError, ValueError):
                    continue
            models.append(ObservationModel(**obs_data))
        self._session.add_all(models)
        self._session.flush()
        return len(models)

    def get_by_id(self, observation_id: str) -> KernelObservation | None:
        model = self._session.get(ObservationModel, _as_uuid(observation_id))
        return KernelObservation.model_validate(model) if model is not None else None

    def find_by_subject(
        self,
        subject_id: str,
        *,
        variable_id: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelObservation]:
        stmt = select(ObservationModel).where(
            ObservationModel.subject_id == _as_uuid(subject_id),
        )
        if variable_id is not None:
            stmt = stmt.where(ObservationModel.variable_id == variable_id)
        stmt = stmt.order_by(ObservationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelObservation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_variable(
        self,
        research_space_id: str,
        variable_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelObservation]:
        stmt = (
            select(ObservationModel)
            .where(
                ObservationModel.research_space_id == _as_uuid(research_space_id),
                ObservationModel.variable_id == variable_id,
            )
            .order_by(ObservationModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelObservation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelObservation]:
        stmt = (
            select(ObservationModel)
            .where(ObservationModel.research_space_id == _as_uuid(research_space_id))
            .order_by(ObservationModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelObservation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def search_by_text(
        self,
        research_space_id: str,
        query: str,
        *,
        limit: int = 20,
    ) -> list[KernelObservation]:
        stmt = select(ObservationModel).where(
            ObservationModel.research_space_id == _as_uuid(research_space_id),
            or_(
                ObservationModel.variable_id.ilike(f"%{query}%"),
                ObservationModel.value_text.ilike(f"%{query}%"),
                ObservationModel.value_coded.ilike(f"%{query}%"),
                ObservationModel.unit.ilike(f"%{query}%"),
            ),
        )
        stmt = stmt.order_by(ObservationModel.created_at.desc()).limit(limit)
        return [
            KernelObservation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def delete(self, observation_id: str) -> bool:
        obs_model = self._session.get(ObservationModel, _as_uuid(observation_id))
        if obs_model is None:
            return False
        self._session.delete(obs_model)
        self._session.flush()
        return True

    def delete_by_provenance(self, provenance_id: str) -> int:
        result = self._session.execute(
            sa_delete(ObservationModel).where(
                ObservationModel.provenance_id == _as_uuid(provenance_id),
            ),
        )
        count = int(result.rowcount or 0) if isinstance(result, CursorResult) else 0
        self._session.flush()
        logger.info(
            "Rolled back %d observations for provenance %s",
            count,
            provenance_id,
        )
        return count

    def count_by_research_space(self, research_space_id: str) -> int:
        result = self._session.execute(
            select(func.count()).where(
                ObservationModel.research_space_id == _as_uuid(research_space_id),
            ),
        )
        return result.scalar_one()


__all__ = ["SqlAlchemyKernelObservationRepository"]
