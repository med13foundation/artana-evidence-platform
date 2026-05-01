"""Shared capture helpers for direct source-search records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.types.common import JSONObject, json_object_or_empty


def build_direct_search_capture(
    *,
    source_key: str,
    search_id: UUID,
    completed_at: datetime,
    query: str,
    query_payload: object,
    result_count: int,
    provider: str,
    external_id: str | None = None,
    provenance: object | None = None,
) -> JSONObject:
    """Build normalized capture metadata for a completed direct source search."""

    return source_result_capture_metadata(
        source_key=source_key,
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"{source_key}:search:{search_id}",
        external_id=external_id,
        retrieved_at=completed_at,
        search_id=str(search_id),
        query=query,
        query_payload=query_payload,
        result_count=result_count,
        provenance=compact_provenance(
            **{
                **json_object_or_empty(provenance),
                "provider": provider,
            },
        ),
    )


def json_records(records: list[dict[str, object]]) -> list[JSONObject]:
    """Normalize gateway records into JSON object payloads."""

    return [json_object_or_empty(record) for record in records]


def next_page_token(fetch_result: object) -> str | None:
    """Return a non-empty pagination token from a gateway result."""

    raw_token = getattr(fetch_result, "next_page_token", None)
    if isinstance(raw_token, str) and raw_token.strip():
        return raw_token.strip()
    return None


def single_record_external_id(
    records: list[JSONObject],
    *,
    keys: tuple[str, ...],
    expected: str | None = None,
) -> str | None:
    """Return one external identifier only when the result set is unambiguous."""

    if len(records) != 1:
        return None
    expected_value = expected.strip().casefold() if expected is not None else None
    record = records[0]
    for key in keys:
        raw_value = record.get(key)
        if raw_value is None:
            continue
        candidate = str(raw_value).strip()
        if not candidate:
            continue
        if expected_value is not None and candidate.casefold() != expected_value:
            return None
        return candidate
    return None


__all__ = [
    "build_direct_search_capture",
    "json_records",
    "next_page_token",
    "single_record_external_id",
]
