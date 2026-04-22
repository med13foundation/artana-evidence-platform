"""Context model for content-enrichment agent executions."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.domain.agents.contexts.base import BaseAgentContext
from src.type_definitions.common import JSONObject  # noqa: TC001


def _empty_payload() -> JSONObject:
    return {}


class ContentEnrichmentContext(BaseAgentContext):
    """Typed context for one content-enrichment workflow run."""

    document_id: str = Field(..., min_length=1, max_length=64)
    source_type: str = Field(..., min_length=1, max_length=64)
    external_record_id: str = Field(..., min_length=1, max_length=255)
    research_space_id: str | None = Field(default=None, max_length=64)
    raw_storage_key: str | None = Field(default=None, max_length=500)
    existing_metadata: JSONObject = Field(default_factory=_empty_payload)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["ContentEnrichmentContext"]
