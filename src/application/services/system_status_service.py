"""
Application service for managing system status flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import anyio
from sqlalchemy import update

from src.domain.entities.session import SessionStatus
from src.models.database.session import SessionModel

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.domain.repositories.system_status_repository import SystemStatusRepository
    from src.type_definitions.system_status import (
        EnableMaintenanceRequest,
        MaintenanceModeState,
    )


@dataclass
class SessionRevocationContext:
    """Lightweight helper for revoking sessions using a synchronous session factory."""

    session_factory: Callable[[], Session]

    def revoke_all(self, *, exclude_user_ids: set[UUID] | None = None) -> int:
        session = self.session_factory()
        try:
            stmt = update(SessionModel).values(status=SessionStatus.REVOKED)
            if exclude_user_ids:
                stmt = stmt.where(~SessionModel.user_id.in_(exclude_user_ids))
            session.execute(stmt)
            session.commit()
            return 0
        finally:
            session.close()


class SystemStatusService:
    """Application service orchestrating maintenance mode operations."""

    def __init__(
        self,
        repository: SystemStatusRepository,
        session_revoker: SessionRevocationContext,
    ) -> None:
        self._repository = repository
        self._session_revoker = session_revoker

    async def get_maintenance_state(self) -> MaintenanceModeState:
        return await anyio.to_thread.run_sync(self._repository.get_maintenance_state)

    async def enable_maintenance(
        self,
        request: EnableMaintenanceRequest,
        *,
        actor_id: UUID,
        exclude_user_ids: Iterable[UUID] | None = None,
    ) -> MaintenanceModeState:
        def _activate() -> MaintenanceModeState:
            state = self._repository.get_maintenance_state()
            return self._repository.save_maintenance_state(
                state.with_activation(message=request.message, actor_id=actor_id),
            )

        new_state = await anyio.to_thread.run_sync(_activate)

        if request.force_logout_users:
            exclude = set(exclude_user_ids or [])
            await anyio.to_thread.run_sync(
                lambda: self._session_revoker.revoke_all(exclude_user_ids=exclude),
            )

        return new_state

    async def disable_maintenance(self, *, actor_id: UUID) -> MaintenanceModeState:
        def _deactivate() -> MaintenanceModeState:
            state = self._repository.get_maintenance_state()
            return self._repository.save_maintenance_state(
                state.with_deactivation(actor_id=actor_id),
            )

        return await anyio.to_thread.run_sync(_deactivate)

    async def require_active(self) -> MaintenanceModeState:
        state = await self.get_maintenance_state()
        if not state.is_active:
            msg = "Maintenance mode must be enabled to perform this action"
            raise PermissionError(msg)
        return state


__all__ = ["SystemStatusService", "SessionRevocationContext"]
