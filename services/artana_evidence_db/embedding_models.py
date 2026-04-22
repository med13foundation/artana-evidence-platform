"""Service-local embedding domain models for hybrid graph workflows."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class KernelEntityEmbedding(BaseModel):
    """Stored embedding vector metadata for one graph entity."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    id: UUID
    research_space_id: UUID
    entity_id: UUID
    embedding: list[float] = Field(min_length=1)
    embedding_model: str = Field(min_length=1, max_length=100)
    embedding_version: int = Field(ge=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    created_at: datetime
    updated_at: datetime


class KernelEntityEmbeddingState(StrEnum):
    """Lifecycle state for graph-owned entity embedding readiness."""

    FAILED = "failed"
    PENDING = "pending"
    READY = "ready"
    STALE = "stale"


class KernelEntityEmbeddingStatus(BaseModel):
    """Graph-owned readiness state for one entity embedding projection."""

    model_config = ConfigDict(from_attributes=True, frozen=True)

    research_space_id: UUID
    entity_id: UUID
    state: KernelEntityEmbeddingState
    desired_fingerprint: str = Field(min_length=64, max_length=64)
    embedding_model: str = Field(min_length=1, max_length=100)
    embedding_version: int = Field(ge=1)
    last_requested_at: datetime
    last_attempted_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    last_error_code: str | None = Field(default=None, max_length=64)
    last_error_message: str | None = Field(default=None, max_length=2000)


class KernelEntityEmbeddingRefreshSummary(BaseModel):
    """Batch summary for explicit embedding refresh runs."""

    model_config = ConfigDict(frozen=True)

    requested: int = Field(ge=0)
    processed: int = Field(ge=0)
    refreshed: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    failed: int = Field(ge=0)
    missing_entities: list[str] = Field(default_factory=list)


class KernelEntitySimilarityCandidate(BaseModel):
    """Vector-search candidate used by hybrid similarity and suggestion services."""

    model_config = ConfigDict(frozen=True)

    entity_id: UUID
    entity_type: str = Field(min_length=1, max_length=64)
    display_label: str | None = Field(default=None, max_length=512)
    vector_score: float = Field(ge=0.0, le=1.0)


class KernelEntitySimilarityScoreBreakdown(BaseModel):
    """Explainable score components for entity similarity responses."""

    model_config = ConfigDict(frozen=True)

    vector_score: float = Field(ge=0.0, le=1.0)
    graph_overlap_score: float = Field(ge=0.0, le=1.0)


class KernelEntitySimilarityResult(BaseModel):
    """One ranked similar-entity response row."""

    model_config = ConfigDict(frozen=True)

    entity_id: UUID
    entity_type: str = Field(min_length=1, max_length=64)
    display_label: str | None = Field(default=None, max_length=512)
    similarity_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: KernelEntitySimilarityScoreBreakdown


class KernelRelationSuggestionScoreBreakdown(BaseModel):
    """Explainable score components for relation suggestion responses."""

    model_config = ConfigDict(frozen=True)

    vector_score: float = Field(ge=0.0, le=1.0)
    graph_overlap_score: float = Field(ge=0.0, le=1.0)
    relation_prior_score: float = Field(ge=0.0, le=1.0)


class KernelRelationSuggestionConstraintCheck(BaseModel):
    """Constraint trace proving dictionary validation for a suggestion."""

    model_config = ConfigDict(frozen=True)

    passed: bool
    source_entity_type: str = Field(min_length=1, max_length=64)
    relation_type: str = Field(min_length=1, max_length=64)
    target_entity_type: str = Field(min_length=1, max_length=64)


class KernelRelationSuggestionResult(BaseModel):
    """One ranked constrained relation suggestion row."""

    model_config = ConfigDict(frozen=True)

    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: str = Field(min_length=1, max_length=64)
    final_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: KernelRelationSuggestionScoreBreakdown
    constraint_check: KernelRelationSuggestionConstraintCheck


__all__ = [
    "KernelEntityEmbedding",
    "KernelEntityEmbeddingRefreshSummary",
    "KernelEntityEmbeddingState",
    "KernelEntityEmbeddingStatus",
    "KernelEntitySimilarityCandidate",
    "KernelEntitySimilarityResult",
    "KernelEntitySimilarityScoreBreakdown",
    "KernelRelationSuggestionConstraintCheck",
    "KernelRelationSuggestionResult",
    "KernelRelationSuggestionScoreBreakdown",
]
