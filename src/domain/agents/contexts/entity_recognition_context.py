"""
Context for entity-recognition agent pipelines.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.domain.agents.contexts.base import BaseAgentContext
from src.type_definitions.common import JSONObject, ResearchSpaceSettings  # noqa: TC001


def _empty_payload() -> JSONObject:
    return {}


def _empty_settings() -> ResearchSpaceSettings:
    return {}


class EntityRecognitionContext(BaseAgentContext):
    """
    Context model for entity-recognition runs.

    Keeps extraction-safe metadata needed for governance and idempotent retries.
    """

    document_id: str = Field(..., min_length=1, max_length=64)
    source_type: str = Field(default="clinvar", min_length=1, max_length=64)
    research_space_id: str | None = Field(default=None)
    research_space_settings: ResearchSpaceSettings = Field(
        default_factory=_empty_settings,
    )
    raw_record: JSONObject = Field(default_factory=_empty_payload)
    shadow_mode: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["EntityRecognitionContext"]
