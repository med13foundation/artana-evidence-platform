"""SQLAlchemy repository for append-only pipeline trace events."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import desc, select

from src.domain.entities.pipeline_run_event import (
    PipelineRunEvent,
    resolve_pipeline_run_event_level,
    resolve_pipeline_run_event_scope_kind,
)
from src.domain.repositories.pipeline_run_event_repository import (
    PipelineRunEventRepository,
)
from src.models.database.pipeline_run_event import PipelineRunEventModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SqlAlchemyPipelineRunEventRepository(PipelineRunEventRepository):
    """Persist and query pipeline trace events via SQLAlchemy."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            msg = "Session not provided"
            raise ValueError(msg)
        return self._session

    @staticmethod
    def _to_domain(model: PipelineRunEventModel) -> PipelineRunEvent:
        return PipelineRunEvent(
            seq=model.seq,
            research_space_id=UUID(model.research_space_id),
            source_id=UUID(model.source_id),
            pipeline_run_id=model.pipeline_run_id,
            event_type=model.event_type,
            stage=model.stage,
            scope_kind=resolve_pipeline_run_event_scope_kind(model.scope_kind),
            scope_id=model.scope_id,
            level=resolve_pipeline_run_event_level(model.level),
            status=model.status,
            agent_kind=model.agent_kind,
            agent_run_id=model.agent_run_id,
            error_code=model.error_code,
            message=model.message,
            occurred_at=model.occurred_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
            duration_ms=model.duration_ms,
            queue_wait_ms=model.queue_wait_ms,
            timeout_budget_ms=model.timeout_budget_ms,
            payload=dict(model.payload),
        )

    def append(self, event: PipelineRunEvent) -> PipelineRunEvent:
        model = PipelineRunEventModel(
            research_space_id=str(event.research_space_id),
            source_id=str(event.source_id),
            pipeline_run_id=event.pipeline_run_id,
            event_type=event.event_type,
            stage=event.stage,
            scope_kind=event.scope_kind,
            scope_id=event.scope_id,
            level=event.level,
            status=event.status,
            agent_kind=event.agent_kind,
            agent_run_id=event.agent_run_id,
            error_code=event.error_code,
            message=event.message,
            occurred_at=event.occurred_at,
            started_at=event.started_at,
            completed_at=event.completed_at,
            duration_ms=event.duration_ms,
            queue_wait_ms=event.queue_wait_ms,
            timeout_budget_ms=event.timeout_budget_ms,
            payload=dict(event.payload),
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return self._to_domain(model)

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
        statement = select(PipelineRunEventModel)
        if research_space_id is not None:
            statement = statement.where(
                PipelineRunEventModel.research_space_id == str(research_space_id),
            )
        if source_id is not None:
            statement = statement.where(
                PipelineRunEventModel.source_id == str(source_id),
            )
        if isinstance(pipeline_run_id, str) and pipeline_run_id.strip():
            statement = statement.where(
                PipelineRunEventModel.pipeline_run_id == pipeline_run_id.strip(),
            )
        if isinstance(stage, str) and stage.strip():
            statement = statement.where(PipelineRunEventModel.stage == stage.strip())
        if isinstance(level, str) and level.strip():
            statement = statement.where(PipelineRunEventModel.level == level.strip())
        if isinstance(scope_kind, str) and scope_kind.strip():
            statement = statement.where(
                PipelineRunEventModel.scope_kind == scope_kind.strip(),
            )
        if isinstance(scope_id, str) and scope_id.strip():
            statement = statement.where(
                PipelineRunEventModel.scope_id == scope_id.strip(),
            )
        if isinstance(agent_kind, str) and agent_kind.strip():
            statement = statement.where(
                PipelineRunEventModel.agent_kind == agent_kind.strip(),
            )
        rows = (
            self.session.execute(
                statement.order_by(
                    desc(PipelineRunEventModel.occurred_at),
                    desc(PipelineRunEventModel.seq),
                ).limit(max(limit, 1)),
            )
            .scalars()
            .all()
        )
        return [self._to_domain(row) for row in rows]


__all__ = ["SqlAlchemyPipelineRunEventRepository"]
