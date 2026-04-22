"""Shared helpers and protocols for ingestion job repository mixins."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy import Select
    from sqlalchemy.orm import Session

    from src.domain.entities.ingestion_job import IngestionJob
    from src.models.database.ingestion_job import IngestionJobModel
    from src.type_definitions.common import JSONObject

_PIPELINE_CLAIM_SCAN_LIMIT = 200
_PIPELINE_ACTIVE_QUEUE_STATUSES: frozenset[str] = frozenset(
    {"queued", "retrying", "running"},
)
_PIPELINE_CLAIMABLE_QUEUE_STATUSES: frozenset[str] = frozenset(
    {"queued", "retrying"},
)


def _coerce_json_object(raw_value: object) -> JSONObject:
    if not isinstance(raw_value, dict):
        return {}
    return {str(key): value for key, value in raw_value.items()}


def _normalize_optional_string(raw_value: object) -> str | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    return normalized or None


def _parse_timestamp(raw_value: object) -> datetime | None:
    if not isinstance(raw_value, str):
        return None
    normalized = raw_value.strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def is_missing_optional_column_error(exc: Exception) -> bool:
    """Return whether the DB error came from older ingestion-job schemas."""
    message = str(exc).lower()
    return (
        "column ingestion_jobs.job_metadata does not exist" in message
        or "column ingestion_jobs.source_config_snapshot does not exist" in message
        or "column ingestion_jobs.dictionary_version_used does not exist" in message
        or "column ingestion_jobs.replay_policy does not exist" in message
        or "column ingestion_jobs.job_kind does not exist" in message
    )


def resolve_dictionary_version_used(session: Session) -> int:
    """Read the latest dictionary changelog id, tolerating startup schema drift."""
    try:
        value = session.execute(
            text("SELECT COALESCE(MAX(id), 0) FROM dictionary_changelog"),
        ).scalar_one()
    except (OperationalError, ProgrammingError, SQLAlchemyError):
        session.rollback()
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return 0
    return 0


class IngestionJobRepositoryContext(Protocol):
    @property
    def session(self) -> Session: ...

    def _resolve_dictionary_version_used(self) -> int: ...

    def _fetch(self, stmt: Select[tuple[IngestionJobModel]]) -> list[IngestionJob]: ...

    @staticmethod
    def _pipeline_payload_from_job_metadata(job_metadata: object) -> JSONObject: ...

    @classmethod
    def _resolve_pipeline_run_id(cls, job_metadata: object) -> str | None: ...

    @classmethod
    def _resolve_pipeline_queue_status(cls, job_metadata: object) -> str | None: ...

    @classmethod
    def _resolve_pipeline_next_attempt_at(
        cls,
        job_metadata: object,
    ) -> datetime | None: ...

    @staticmethod
    def _build_pipeline_job_metadata_update(  # noqa: PLR0913
        *,
        existing_job_metadata: object,
        status: str,
        queue_status: str,
        updated_at: datetime,
        worker_id: str | None = None,
        next_attempt_at: datetime | None = None,
        last_error: str | None = None,
        error_category: str | None = None,
        attempt_count: int | None = None,
        heartbeat_at: datetime | None = None,
    ) -> JSONObject: ...

    def find_by_id(self, job_id: UUID) -> IngestionJob | None: ...

    def save(self, job: IngestionJob) -> IngestionJob: ...

    def find_by_status(
        self,
        status: object,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]: ...
