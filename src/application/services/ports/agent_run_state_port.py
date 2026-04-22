"""Port interface for agent-run state inspection."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from src.type_definitions.data_sources import AgentRunTableSummary


class AgentRunStatePort(ABC):
    """Abstraction for reading agent runtime state details."""

    @abstractmethod
    def find_latest_run_id(self, *, since: datetime) -> str | None:
        """Return the latest agent run id created since the provided timestamp."""
        ...

    @abstractmethod
    def get_run_table_summaries(self, run_id: str) -> list[AgentRunTableSummary]:
        """Return per-table summaries for a specific agent run."""
        ...
