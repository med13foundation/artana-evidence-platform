"""Context model for PubMed semantic relevance classification."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from src.domain.agents.contexts.base import BaseAgentContext


class PubMedRelevanceContext(BaseAgentContext):
    """Execution context for one PubMed title/abstract relevance decision."""

    source_type: str = Field(
        default="pubmed",
        min_length=1,
        max_length=64,
    )
    query: str = Field(
        ...,
        min_length=1,
        max_length=4000,
    )
    title: str | None = Field(default=None, max_length=8000)
    abstract: str | None = Field(default=None, max_length=32000)
    domain_context: str | None = Field(default=None, max_length=64)
    pubmed_id: str | None = Field(default=None, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = ["PubMedRelevanceContext"]
