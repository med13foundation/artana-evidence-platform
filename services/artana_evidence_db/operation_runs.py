"""Service-local persistence helpers for graph operation history."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.operation_run_models import (
    GraphOperationRunModel,
    GraphOperationRunStatusEnum,
    GraphOperationRunTypeEnum,
)
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session


class GraphOperationRunStore:
    """Persist and query standalone graph-service operation history."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        *,
        operation_type: GraphOperationRunTypeEnum,
        status: GraphOperationRunStatusEnum,
        research_space_id: UUID | None,
        actor_user_id: UUID | None,
        actor_email: str | None,
        dry_run: bool,
        request_payload: JSONObject,
        summary_payload: JSONObject,
        started_at: datetime,
        completed_at: datetime,
        failure_detail: str | None = None,
    ) -> GraphOperationRunModel:
        """Insert one operation-history row into the graph service store."""
        model = GraphOperationRunModel(
            operation_type=operation_type,
            status=status,
            research_space_id=research_space_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            dry_run=dry_run,
            request_payload=dict(request_payload),
            summary_payload=dict(summary_payload),
            failure_detail=failure_detail,
            started_at=started_at,
            completed_at=completed_at,
        )
        self._session.add(model)
        self._session.flush()
        return model

    def list_runs(
        self,
        *,
        limit: int,
        offset: int,
        operation_type: GraphOperationRunTypeEnum | None = None,
        status: GraphOperationRunStatusEnum | None = None,
        research_space_id: UUID | None = None,
    ) -> tuple[list[GraphOperationRunModel], int]:
        """List recorded graph operation runs with filters."""
        base_statement = self._filtered_statement(
            operation_type=operation_type,
            status=status,
            research_space_id=research_space_id,
        )
        total = int(
            self._session.execute(
                select(func.count()).select_from(base_statement.subquery()),
            ).scalar_one(),
        )
        items = list(
            self._session.scalars(
                base_statement.order_by(GraphOperationRunModel.started_at.desc())
                .offset(offset)
                .limit(limit),
            ),
        )
        return items, total

    def get_run(self, run_id: UUID) -> GraphOperationRunModel | None:
        """Fetch one recorded graph operation run by identifier."""
        return self._session.get(GraphOperationRunModel, run_id)

    def _filtered_statement(
        self,
        *,
        operation_type: GraphOperationRunTypeEnum | None,
        status: GraphOperationRunStatusEnum | None,
        research_space_id: UUID | None,
    ) -> Select[tuple[GraphOperationRunModel]]:
        statement: Select[tuple[GraphOperationRunModel]] = select(
            GraphOperationRunModel,
        )
        if operation_type is not None:
            statement = statement.where(
                GraphOperationRunModel.operation_type == operation_type,
            )
        if status is not None:
            statement = statement.where(GraphOperationRunModel.status == status)
        if research_space_id is not None:
            statement = statement.where(
                GraphOperationRunModel.research_space_id == research_space_id,
            )
        return statement


__all__ = ["GraphOperationRunStore"]
