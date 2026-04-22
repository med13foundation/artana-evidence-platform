"""Service-local models for research-query intent parsing and planning."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchQueryIntent(BaseModel):
    """Parsed intent from a natural-language research question."""

    original_query: str = Field(..., min_length=1, max_length=2000)
    normalized_terms: list[str] = Field(default_factory=list)
    requested_entity_types: list[str] = Field(default_factory=list)
    requested_relation_types: list[str] = Field(default_factory=list)
    requested_variable_ids: list[str] = Field(default_factory=list)
    domain_context: str | None = Field(default=None, max_length=64)
    ambiguous: bool = Field(default=False)
    notes: list[str] = Field(default_factory=list)


class ResearchQueryPlan(BaseModel):
    """Executable graph query plan derived from parsed intent."""

    query_terms: list[str] = Field(default_factory=list)
    entity_types: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    variable_ids: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=2, ge=1, le=4)
    top_k: int = Field(default=25, ge=1, le=100)
    plan_summary: str = Field(..., min_length=1, max_length=4000)


__all__ = ["ResearchQueryIntent", "ResearchQueryPlan"]
