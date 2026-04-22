"""Shared utility helpers for ingestion scheduling service internals."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.type_definitions.common import JSONObject


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def with_failure_metadata(
    metadata: object,
    *,
    failure_payload: JSONObject,
) -> JSONObject:
    if not isinstance(metadata, dict):
        normalized_metadata: JSONObject = {}
    else:
        normalized_metadata = {str(key): value for key, value in metadata.items()}
    normalized_metadata["failure"] = dict(failure_payload)
    return normalized_metadata
