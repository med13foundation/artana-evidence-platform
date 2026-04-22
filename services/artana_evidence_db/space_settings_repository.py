"""Service-local SQLAlchemy adapter for graph space settings."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.common_types import ResearchSpaceSettings
from artana_evidence_db.ports import SpaceRegistryPort
from artana_evidence_db.space_registry_repository import (
    SqlAlchemyKernelSpaceRegistryRepository,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SqlAlchemyKernelSpaceSettingsRepository:
    """Resolve graph-space settings from the graph-owned registry."""

    def __init__(
        self,
        session: Session,
        *,
        space_registry: SpaceRegistryPort | None = None,
    ) -> None:
        self._session = session
        self._space_registry = space_registry

    def get_settings(
        self,
        space_id: UUID,
    ) -> ResearchSpaceSettings | None:
        registry = self._space_registry or SqlAlchemyKernelSpaceRegistryRepository(
            self._session,
        )
        space = registry.get_by_id(space_id)
        if space is None:
            return None
        return space.settings


__all__ = ["SqlAlchemyKernelSpaceSettingsRepository"]
