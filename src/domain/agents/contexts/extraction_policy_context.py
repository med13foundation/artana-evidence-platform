"""Context for extraction relation-policy pipelines."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.domain.agents.contexts.base import BaseAgentContext
from src.domain.agents.contracts.extraction_policy import (  # noqa: TC001
    UnknownRelationPattern,
)
from src.type_definitions.common import JSONObject  # noqa: TC001


class ExtractionPolicyContext(BaseAgentContext):
    """Context model for policy proposals over undefined relation patterns."""

    document_id: str = Field(..., min_length=1, max_length=64)
    source_type: str = Field(..., min_length=1, max_length=64)
    research_space_id: str | None = Field(default=None)
    unknown_relation_patterns: list[UnknownRelationPattern] = Field(
        default_factory=list,
    )
    current_constraints: list[JSONObject] = Field(default_factory=list)
    existing_relation_types: list[str] = Field(default_factory=list)
    shadow_mode: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["ExtractionPolicyContext"]
