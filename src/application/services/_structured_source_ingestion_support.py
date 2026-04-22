"""Support helpers for structured source ingestion services."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from src.domain.entities.user_data_source import SourceType
from src.type_definitions import json_utils

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from src.domain.services.ingestion import IngestionExtractionTarget
    from src.type_definitions.common import JSONObject, JSONValue


class StructuredFetchResult(Protocol):
    """Gateway response shape shared by structured database connectors."""

    @property
    def records(self) -> Sequence[Mapping[str, object]]:
        """Fetched upstream records."""

    @property
    def fetched_records(self) -> int:
        """Number of upstream records fetched."""

    @property
    def checkpoint_after(self) -> Mapping[str, object] | None:
        """Checkpoint payload after the fetch."""

    @property
    def checkpoint_kind(self) -> str:
        """Checkpoint strategy name."""


class StructuredSourceGateway(Protocol):
    """Synchronous fetch contract used by structured source ingestion services."""

    def fetch_records(
        self,
        *,
        query: str,
        max_results: int,
    ) -> StructuredFetchResult:
        """Fetch records matching a normalized query."""


@dataclass(frozen=True)
class StructuredSourceIngestionConfig:
    """Static per-source mapping config for structured ingestion services."""

    source_type: SourceType
    source_label: str
    query_keys: tuple[str, ...]
    id_keys: tuple[str, ...]
    entity_type: str
    default_max_results: int = 20


@dataclass(frozen=True)
class StructuredSourceIngestionSummary:
    """Aggregate statistics for a structured source ingestion run."""

    source_id: UUID
    fetched_records: int = 0
    parsed_publications: int = 0
    created_publications: int = 0
    updated_publications: int = 0
    extraction_targets: tuple[IngestionExtractionTarget, ...] = ()
    executed_query: str | None = None
    query_signature: str | None = None
    checkpoint_before: JSONObject | None = None
    checkpoint_after: JSONObject | None = None
    checkpoint_kind: str | None = None
    new_records: int = 0
    updated_records: int = 0
    unchanged_records: int = 0
    skipped_records: int = 0
    observations_created: int = 0
    ingestion_job_id: UUID | None = None


def to_json_object(record: Mapping[str, object]) -> JSONObject:
    """Convert an arbitrary mapping into a typed JSON object."""
    payload: JSONObject = {}
    for key, value in record.items():
        payload[str(key)] = to_json_value(value)
    return payload


def to_json_value(value: object) -> JSONValue:
    """Convert an arbitrary object into a typed JSON value."""
    return json_utils.to_json_value(value)


def checkpoint_payload(checkpoint: Mapping[str, object] | None) -> JSONObject | None:
    """Normalize optional gateway checkpoint payloads."""
    if checkpoint is None:
        return None
    return to_json_object(checkpoint)


def compute_payload_hash(record: Mapping[str, JSONValue]) -> str:
    """Return a stable hash for a typed JSON payload."""
    serialized = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def extract_source_updated_at(record: JSONObject) -> datetime | None:
    """Extract a best-effort upstream update timestamp from a record."""
    for key in ("fetched_at", "updated_at", "last_updated"):
        value = record.get(key)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=UTC)
            return parsed
    return None


def source_type_value(source_type: SourceType | str) -> str:
    """Normalize a source type enum/string value to its stored string value."""
    if isinstance(source_type, SourceType):
        return source_type.value
    return str(source_type)


__all__ = [
    "checkpoint_payload",
    "compute_payload_hash",
    "extract_source_updated_at",
    "source_type_value",
    "StructuredFetchResult",
    "StructuredSourceGateway",
    "StructuredSourceIngestionConfig",
    "StructuredSourceIngestionSummary",
    "to_json_object",
    "to_json_value",
]
