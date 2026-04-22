"""Context for graph-connection agent pipelines."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.domain.agents.contexts.base import BaseAgentContext
from src.type_definitions.common import ResearchSpaceSettings  # noqa: TC001


def _empty_settings() -> ResearchSpaceSettings:
    return {}


class GraphConnectionContext(BaseAgentContext):
    """Context model for graph-connection discovery runs."""

    seed_entity_id: str = Field(..., min_length=1, max_length=64)
    source_type: str = Field(default="clinvar", min_length=1, max_length=64)
    research_space_id: str = Field(..., min_length=1, max_length=64)
    source_id: str | None = Field(default=None, max_length=64)
    pipeline_run_id: str | None = Field(default=None, max_length=128)
    research_space_settings: ResearchSpaceSettings = Field(
        default_factory=_empty_settings,
    )
    max_depth: int = Field(default=2, ge=1, le=4)
    relation_types: list[str] | None = None
    shadow_mode: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["GraphConnectionContext"]
