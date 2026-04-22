"""Mapper utilities for ingestion job entities."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionJobKind,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from src.domain.value_objects import Provenance
from src.models.database.ingestion_job import (
    IngestionJobKindEnum,
    IngestionJobModel,
    IngestionStatusEnum,
    IngestionTriggerEnum,
)
from src.type_definitions.data_sources import normalize_ingestion_job_metadata

if TYPE_CHECKING:
    from src.infrastructure.llm.config.runtime_policy import ReplayPolicy
    from src.type_definitions.common import JSONObject
else:
    JSONObject = dict[str, object]  # Runtime type stub


def _from_iso_required(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _from_iso_optional(value: str | None) -> datetime | None:
    if not value:
        return None
    return _from_iso_required(value)


def _to_iso_seconds(value: datetime | None) -> str | None:
    if not value:
        return None
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat(timespec="seconds")


def _normalize_replay_policy(value: str) -> ReplayPolicy:
    normalized = value.strip().lower()
    if normalized == "strict":
        return "strict"
    if normalized == "allow_prompt_drift":
        return "allow_prompt_drift"
    if normalized == "fork_on_drift":
        return "fork_on_drift"
    return "strict"


class IngestionJobMapper:
    """Bidirectional mapper between domain ingestion jobs and SQLAlchemy models."""

    @staticmethod
    def to_domain(model: IngestionJobModel) -> IngestionJob:
        """Convert a SQLAlchemy model instance into a domain entity."""
        metrics_payload = model.metrics or {}
        errors_payload = model.errors or []
        # Type: model.job_metadata is already dict[str, object] from SQLAlchemy JSON
        metadata_payload = normalize_ingestion_job_metadata(model.job_metadata)
        # Type: model.source_config_snapshot is already dict[str, object] from SQLAlchemy JSON
        snapshot_payload: JSONObject = dict(model.source_config_snapshot or {})

        return IngestionJob(
            id=UUID(model.id),
            source_id=UUID(model.source_id),
            job_kind=IngestionJobKind(model.job_kind.value),
            trigger=IngestionTrigger(model.trigger.value),
            triggered_by=(UUID(model.triggered_by) if model.triggered_by else None),
            triggered_at=_from_iso_required(model.triggered_at),
            status=IngestionStatus(model.status.value),
            started_at=_from_iso_optional(model.started_at),
            completed_at=_from_iso_optional(model.completed_at),
            metrics=JobMetrics.model_validate(metrics_payload),
            errors=[
                IngestionError.model_validate(error_payload)
                for error_payload in errors_payload
            ],
            provenance=Provenance.model_validate(model.provenance),
            metadata=metadata_payload,
            source_config_snapshot=snapshot_payload,
            dictionary_version_used=int(model.dictionary_version_used),
            replay_policy=_normalize_replay_policy(str(model.replay_policy)),
        )

    @staticmethod
    def to_model_dict(job: IngestionJob) -> dict[str, object]:
        """Convert a domain entity into keyword arguments for SQLAlchemy models."""
        return {
            "id": str(job.id),
            "source_id": str(job.source_id),
            "job_kind": IngestionJobKindEnum(job.job_kind.value),
            "trigger": IngestionTriggerEnum(job.trigger.value),
            "triggered_by": str(job.triggered_by) if job.triggered_by else None,
            "triggered_at": _to_iso_seconds(job.triggered_at),
            "status": IngestionStatusEnum(job.status.value),
            "started_at": _to_iso_seconds(job.started_at),
            "completed_at": _to_iso_seconds(job.completed_at),
            "metrics": job.metrics.model_dump(mode="json"),
            "errors": [error.model_dump(mode="json") for error in job.errors],
            "provenance": job.provenance.model_dump(mode="json"),
            "job_metadata": normalize_ingestion_job_metadata(job.metadata),
            "source_config_snapshot": dict(job.source_config_snapshot),
            "dictionary_version_used": int(job.dictionary_version_used),
            "replay_policy": job.replay_policy,
        }

    @staticmethod
    def serialize_timestamp(value: datetime) -> str:
        """Serialize timestamps to the same format stored in the database."""
        serialized = _to_iso_seconds(value)
        if serialized is None:
            msg = "Timestamp serialization failed"
            raise ValueError(msg)
        return serialized
