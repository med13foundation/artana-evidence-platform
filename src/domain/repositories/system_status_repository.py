"""
Repository interface for system status flags.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.system_status import MaintenanceModeState


class SystemStatusRepository(ABC):
    """Abstract repository for system-wide status flags."""

    @abstractmethod
    def get_maintenance_state(self) -> MaintenanceModeState:
        """Retrieve the persisted maintenance mode state."""

    @abstractmethod
    def save_maintenance_state(
        self,
        state: MaintenanceModeState,
    ) -> MaintenanceModeState:
        """Persist the maintenance mode state."""


__all__ = ["SystemStatusRepository"]
