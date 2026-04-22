"""Context for graph-search agent pipelines."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.domain.agents.contexts.base import BaseAgentContext


class GraphSearchContext(BaseAgentContext):
    """Typed context for graph-search executions."""

    question: str = Field(..., min_length=1, max_length=2000)
    research_space_id: str = Field(..., min_length=1, max_length=64)
    max_depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    curation_statuses: list[str] | None = None
    include_evidence_chains: bool = Field(default=True)
    force_agent: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["GraphSearchContext"]
