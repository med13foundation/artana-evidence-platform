"""Service-local models for relation-suggestion workflows."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_db.embedding_models import KernelEntityEmbeddingState
from pydantic import BaseModel, ConfigDict, Field


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


class KernelRelationSuggestionSkippedSource(BaseModel):
    """One source entity skipped during relation suggestion."""

    model_config = ConfigDict(frozen=True)

    entity_id: UUID
    state: KernelEntityEmbeddingState
    reason: str = Field(min_length=1, max_length=128)


class KernelRelationSuggestionBatchResult(BaseModel):
    """Complete relation-suggestion result including skipped-source metadata."""

    model_config = ConfigDict(frozen=True)

    suggestions: list[KernelRelationSuggestionResult]
    incomplete: bool
    skipped_sources: list[KernelRelationSuggestionSkippedSource] = Field(
        default_factory=list,
    )


__all__ = [
    "KernelRelationSuggestionBatchResult",
    "KernelRelationSuggestionConstraintCheck",
    "KernelRelationSuggestionResult",
    "KernelRelationSuggestionScoreBreakdown",
    "KernelRelationSuggestionSkippedSource",
]
