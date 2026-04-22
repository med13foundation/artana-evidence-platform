"""Contract model for PubMed semantic relevance classification."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from src.domain.agents.contracts.base import BaseAgentContract


class PubMedRelevanceContract(BaseAgentContract):
    """Structured output for title/abstract semantic relevance classification."""

    relevance: Literal["relevant", "non_relevant"] = Field(
        ...,
        description="Semantic relevance label for the research topic/query.",
    )
    source_type: str = Field(
        default="pubmed",
        min_length=1,
        max_length=64,
        description="Source type the classification applies to.",
    )
    query: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Resolved search topic/query used during classification.",
    )
    agent_run_id: str | None = Field(
        default=None,
        max_length=128,
        description="Deterministic Artana run identifier for audit and replay.",
    )


__all__ = ["PubMedRelevanceContract"]
