"""
SQLAlchemy repository for system status flags.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.repositories.system_status_repository import SystemStatusRepository
from src.models.database.system_status import SystemStatusModel
from src.type_definitions.system_status import MaintenanceModeState

if TYPE_CHECKING:
    from sqlalchemy.sql.schema import Table as SQLATable
else:
    SQLATable = object

SessionFactory = Callable[[], Session]
SYSTEM_STATUS_TABLE: SQLATable = SystemStatusModel.__table__  # type: ignore[assignment]


class SqlAlchemySystemStatusRepository(SystemStatusRepository):
    """Persist and retrieve maintenance mode state via SQLAlchemy."""

    def __init__(self, session_factory: SessionFactory):
        self._session_factory = session_factory

    def _ensure_table(self, session: Session) -> None:
        bind = session.get_bind()
        if bind is not None:
            SYSTEM_STATUS_TABLE.create(bind=bind, checkfirst=True)

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session: Session = self._session_factory()
        try:
            self._ensure_table(session)
            yield session
        finally:
            session.close()

    def _get_or_create_model(self, session: Session) -> SystemStatusModel:
        model = session.get(SystemStatusModel, "maintenance_mode")
        if model is None:
            model = SystemStatusModel(
                key="maintenance_mode",
                value=MaintenanceModeState().model_dump(mode="json"),
            )
            session.add(model)
            session.commit()
            session.refresh(model)
        return model

    def get_maintenance_state(self) -> MaintenanceModeState:
        with self._session() as session:
            stmt = select(SystemStatusModel).where(
                SystemStatusModel.key == "maintenance_mode",
            )
            result = session.execute(stmt).scalar_one_or_none()
            if result is None:
                result = self._get_or_create_model(session)
            return MaintenanceModeState.model_validate(result.value)

    def save_maintenance_state(
        self,
        state: MaintenanceModeState,
    ) -> MaintenanceModeState:
        with self._session() as session:
            model = self._get_or_create_model(session)
            model.value = state.model_dump(mode="json")
            session.add(model)
            session.commit()
            session.refresh(model)
            return MaintenanceModeState.model_validate(model.value)


__all__ = ["SqlAlchemySystemStatusRepository"]
