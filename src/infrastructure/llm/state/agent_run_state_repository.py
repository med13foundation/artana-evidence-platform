"""SQLAlchemy implementation for inspecting agent runtime state tables."""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.application.services.ports.agent_run_state_port import AgentRunStatePort
from src.type_definitions.common import JSONObject, JSONValue  # noqa: TCH001
from src.type_definitions.data_sources import AgentRunTableSummary
from src.type_definitions.json_utils import to_json_value

if TYPE_CHECKING:
    from sqlalchemy.engine import RowMapping
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_SAMPLE_ROW_LIMIT = 3
_MAX_SAMPLE_STRING_LENGTH = 1000

_RUN_TABLE_QUERIES = {
    "runs": text(
        """
        SELECT COUNT(*) AS row_count,
               MAX(created_at) AS latest_created_at
        FROM artana.runs
        WHERE run_id = :run_id
        """,
    ),
    "workflow_state": text(
        """
        SELECT COUNT(*) AS row_count,
               MAX(created_at) AS latest_created_at
        FROM artana.workflow_state
        WHERE run_id = :run_id
        """,
    ),
    "steps": text(
        """
        SELECT COUNT(*) AS row_count,
               MAX(created_at) AS latest_created_at
        FROM artana.steps
        WHERE run_id = :run_id
        """,
    ),
    "spans": text(
        """
        SELECT COUNT(*) AS row_count,
               MAX(created_at) AS latest_created_at
        FROM artana.spans
        WHERE run_id = :run_id
        """,
    ),
    "traces": text(
        """
        SELECT COUNT(*) AS row_count,
               MAX(created_at) AS latest_created_at
        FROM artana.traces
        WHERE run_id = :run_id
        """,
    ),
    "evaluations": text(
        """
        SELECT COUNT(*) AS row_count,
               MAX(created_at) AS latest_created_at
        FROM artana.evaluations
        WHERE run_id = :run_id
        """,
    ),
}

_RUN_TABLE_SAMPLE_QUERIES = {
    "runs": text(
        """
        SELECT *
        FROM artana.runs
        WHERE run_id = :run_id
        ORDER BY created_at DESC
        LIMIT :limit
        """,
    ),
    "workflow_state": text(
        """
        SELECT *
        FROM artana.workflow_state
        WHERE run_id = :run_id
        ORDER BY created_at DESC
        LIMIT :limit
        """,
    ),
    "steps": text(
        """
        SELECT *
        FROM artana.steps
        WHERE run_id = :run_id
        ORDER BY created_at DESC
        LIMIT :limit
        """,
    ),
    "spans": text(
        """
        SELECT *
        FROM artana.spans
        WHERE run_id = :run_id
        ORDER BY created_at DESC
        LIMIT :limit
        """,
    ),
    "traces": text(
        """
        SELECT *
        FROM artana.traces
        WHERE run_id = :run_id
        ORDER BY created_at DESC
        LIMIT :limit
        """,
    ),
    "evaluations": text(
        """
        SELECT *
        FROM artana.evaluations
        WHERE run_id = :run_id
        ORDER BY created_at DESC
        LIMIT :limit
        """,
    ),
}


class SqlAlchemyAgentRunStateRepository(AgentRunStatePort):
    """Read-only agent runtime state inspector backed by SQLAlchemy."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_latest_run_id(self, *, since: datetime) -> str | None:
        try:
            result = self._session.execute(
                text(
                    """
                    SELECT run_id
                    FROM artana.runs
                    WHERE created_at >= :since
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                ),
                {"since": since},
            ).scalar_one_or_none()
        except SQLAlchemyError as exc:  # pragma: no cover - optional enrichment
            logger.warning(
                "Runtime state schema not available for run lookup; skipping run metadata. %s",
                exc,
            )
            return None
        return result if isinstance(result, str) and result.strip() else None

    def get_run_table_summaries(self, run_id: str) -> list[AgentRunTableSummary]:
        summaries: list[AgentRunTableSummary] = []
        for table, query in _RUN_TABLE_QUERIES.items():
            try:
                row = self._session.execute(query, {"run_id": run_id}).mappings().one()
            except SQLAlchemyError as exc:  # pragma: no cover - optional enrichment
                logger.warning(
                    "Runtime state schema not available for table summaries; returning empty. %s",
                    exc,
                )
                return []
            sample_rows = self._fetch_sample_rows(table, run_id)
            summaries.append(
                AgentRunTableSummary(
                    table_name=table,
                    row_count=_coerce_row_count(row.get("row_count")),
                    latest_created_at=_coerce_datetime(row.get("latest_created_at")),
                    sample_rows=sample_rows,
                ),
            )
        return summaries

    def _fetch_sample_rows(self, table: str, run_id: str) -> list[JSONObject]:
        query = _RUN_TABLE_SAMPLE_QUERIES.get(table)
        if query is None:
            return []
        try:
            rows = (
                self._session.execute(
                    query,
                    {"run_id": run_id, "limit": _SAMPLE_ROW_LIMIT},
                )
                .mappings()
                .all()
            )
        except SQLAlchemyError as exc:  # pragma: no cover - optional enrichment
            logger.warning(
                "Failed to fetch runtime sample rows for %s; returning empty. %s",
                table,
                exc,
            )
            return []
        return [_row_to_json_object(_normalize_row(row)) for row in rows]


def _coerce_row_count(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float | Decimal):
        return int(value)
    return 0


def _coerce_datetime(value: object) -> datetime | None:
    return value if isinstance(value, datetime) else None


def _normalize_row(row: RowMapping) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in row.items():
        payload[str(key)] = value
    return payload


def _row_to_json_object(row: dict[str, object]) -> JSONObject:
    payload: JSONObject = {}
    for key, value in row.items():
        json_value = to_json_value(value)
        payload[str(key)] = _truncate_json_value(json_value)
    return payload


def _truncate_json_value(value: JSONValue) -> JSONValue:
    if isinstance(value, str):
        if len(value) <= _MAX_SAMPLE_STRING_LENGTH:
            return value
        return f"{value[:_MAX_SAMPLE_STRING_LENGTH]}..."
    if isinstance(value, list):
        return [_truncate_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _truncate_json_value(item) for key, item in value.items()}
    return value


__all__ = ["SqlAlchemyAgentRunStateRepository"]
