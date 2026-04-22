"""Repository interface for append-only pipeline trace events."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from src.domain.entities.pipeline_run_event import PipelineRunEvent


class PipelineRunEventRepository(ABC):
    """Persistence contract for pipeline trace events."""

    @abstractmethod
    def append(self, event: PipelineRunEvent) -> PipelineRunEvent:
        """Persist a new pipeline trace event."""

    @abstractmethod
    def list_events(  # noqa: PLR0913
        self,
        *,
        research_space_id: UUID | None = None,
        source_id: UUID | None = None,
        pipeline_run_id: str | None = None,
        stage: str | None = None,
        level: str | None = None,
        scope_kind: str | None = None,
        scope_id: str | None = None,
        agent_kind: str | None = None,
        limit: int = 200,
    ) -> list[PipelineRunEvent]:
        """List persisted pipeline trace events ordered newest first."""


__all__ = ["PipelineRunEventRepository"]
