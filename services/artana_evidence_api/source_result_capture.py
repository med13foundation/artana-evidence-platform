"""Shared source-result capture metadata for evidence-source workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from artana_evidence_api.source_registry import get_source_definition
from artana_evidence_api.types.common import (
    JSONObject,
    json_object_or_empty,
    json_value,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SourceCaptureStage(str, Enum):
    """Lifecycle stage for one source result."""

    SEARCH_RESULT = "search_result"
    SOURCE_DOCUMENT = "source_document"
    PROPOSAL_CANDIDATE = "proposal_candidate"


class SourceResultCapture(BaseModel):
    """Normalized capture/provenance envelope for one source result."""

    model_config = ConfigDict(frozen=True)

    source_key: str = Field(..., min_length=1, pattern=r"^[a-z0-9_]+$")
    source_family: str = Field(..., min_length=1, pattern=r"^[a-z0-9_]+$")
    capture_stage: SourceCaptureStage
    capture_method: str = Field(..., min_length=1)
    locator: str = Field(..., min_length=1)
    external_id: str | None = None
    citation: str | None = None
    retrieved_at: str = Field(..., min_length=1)
    run_id: str | None = None
    search_id: str | None = None
    document_id: str | None = None
    query: str | None = None
    query_payload: JSONObject = Field(default_factory=dict)
    result_count: int | None = Field(default=None, ge=0)
    provenance: JSONObject = Field(default_factory=dict)

    @field_validator("retrieved_at")
    @classmethod
    def _validate_retrieved_at(cls, value: str) -> str:
        return _iso_retrieved_at(value)

    @model_validator(mode="after")
    def _validate_source_family(self) -> SourceResultCapture:
        source = get_source_definition(self.source_key)
        if source is None:
            return self
        if self.source_family != source.source_family:
            msg = (
                f"source_family for {self.source_key} must be "
                f"{source.source_family}"
            )
            raise ValueError(msg)
        return self

    def to_metadata(self) -> JSONObject:
        """Serialize the capture envelope for document/search metadata."""

        return json_object_or_empty(
            self.model_dump(mode="json", exclude_none=True),
        )


class SourceSearchResponse(BaseModel):
    """Generic direct-search response with a required source-capture envelope.

    Source-specific result fields stay at the response root for compatibility
    with existing concrete source-search payloads.
    """

    model_config = ConfigDict(extra="allow")

    source_capture: SourceResultCapture


def source_result_capture_metadata(  # noqa: PLR0913
    *,
    source_key: str,
    capture_stage: SourceCaptureStage,
    capture_method: str,
    locator: str,
    external_id: str | None = None,
    citation: str | None = None,
    retrieved_at: datetime | str | None = None,
    run_id: str | None = None,
    search_id: str | None = None,
    document_id: str | None = None,
    query: str | None = None,
    query_payload: object | None = None,
    result_count: int | None = None,
    provenance: object | None = None,
) -> JSONObject:
    """Return the normalized source-result capture metadata object."""

    source = get_source_definition(source_key)
    if source is None:
        msg = f"Unknown source key: {source_key}"
        raise ValueError(msg)
    resolved_retrieved_at = _iso_retrieved_at(retrieved_at)
    capture = SourceResultCapture(
        source_key=source.source_key,
        source_family=source.source_family,
        capture_stage=capture_stage,
        capture_method=capture_method,
        locator=locator,
        external_id=external_id,
        citation=citation,
        retrieved_at=resolved_retrieved_at,
        run_id=run_id,
        search_id=search_id,
        document_id=document_id,
        query=query,
        query_payload=json_object_or_empty(query_payload),
        result_count=result_count,
        provenance=json_object_or_empty(provenance),
    )
    return capture.to_metadata()


def attach_source_capture_metadata(
    *,
    metadata: JSONObject,
    source_capture: JSONObject,
) -> JSONObject:
    """Return metadata with normalized source capture under one stable key."""

    return {
        **metadata,
        "source_capture": source_capture,
    }


def _iso_retrieved_at(raw_value: datetime | str | None) -> str:
    if raw_value is None:
        return datetime.now(UTC).isoformat()
    if isinstance(raw_value, datetime):
        resolved = raw_value
        if resolved.tzinfo is None or resolved.utcoffset() is None:
            msg = "retrieved_at must be timezone-aware"
            raise ValueError(msg)
        return resolved.isoformat()
    try:
        parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as exc:
        msg = "retrieved_at must be an ISO-8601 timestamp"
        raise ValueError(msg) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        msg = "retrieved_at must be timezone-aware"
        raise ValueError(msg)
    return parsed.isoformat()


def compact_provenance(**fields: object) -> JSONObject:
    """Build a compact JSON provenance object while omitting empty values."""

    provenance: JSONObject = {}
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        provenance[key] = json_value(value)
    return provenance


__all__ = [
    "SourceCaptureStage",
    "SourceResultCapture",
    "SourceSearchResponse",
    "attach_source_capture_metadata",
    "compact_provenance",
    "source_result_capture_metadata",
]
