# ruff: noqa: TC001,TC003
"""Entity and suggestion schemas for kernel graph routes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.graph_api_schemas.kernel_schema_common import (
    _to_required_utc_datetime,
    _to_uuid,
)
from artana_evidence_db.kernel_domain_models import KernelEntity
from pydantic import BaseModel, ConfigDict, Field


class KernelEntityCreateRequest(BaseModel):
    """Request model for creating (or resolving) a kernel entity."""

    model_config = ConfigDict(strict=True)

    entity_type: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "Dictionary entity type id. The API accepts case-insensitive input and "
            "normalizes values like 'gene' to 'GENE'."
        ),
    )
    display_label: str | None = Field(None, max_length=512)
    aliases: list[str] = Field(default_factory=list)
    metadata: JSONObject = Field(default_factory=dict)
    identifiers: dict[str, str] = Field(
        default_factory=dict,
        description="Namespace -> identifier value (e.g. {'pmid': '12345'})",
    )


class KernelEntityUpdateRequest(BaseModel):
    """Request model for updating a kernel entity."""

    model_config = ConfigDict(strict=True)

    display_label: str | None = Field(None, max_length=512)
    aliases: list[str] | None = None
    metadata: JSONObject | None = None
    identifiers: dict[str, str] | None = Field(
        default=None,
        description="Namespace -> identifier value pairs to add (merge-only).",
    )


class KernelEntityResponse(BaseModel):
    """Response model for a kernel entity."""

    model_config = ConfigDict(strict=True)

    id: UUID
    research_space_id: UUID
    entity_type: str
    display_label: str | None
    aliases: list[str] = Field(default_factory=list)
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: KernelEntity) -> KernelEntityResponse:
        entity_id = _to_uuid(model.id)
        space_id = _to_uuid(model.research_space_id)
        metadata_payload = model.metadata or {}
        return cls(
            id=entity_id,
            research_space_id=space_id,
            entity_type=str(model.entity_type),
            display_label=str(model.display_label) if model.display_label else None,
            aliases=[
                str(alias)
                for alias in model.aliases
                if isinstance(alias, str) and alias.strip()
            ],
            metadata=dict(metadata_payload),
            created_at=_to_required_utc_datetime(
                model.created_at,
                field_name="entity.created_at",
            ),
            updated_at=_to_required_utc_datetime(
                model.updated_at,
                field_name="entity.updated_at",
            ),
        )


class KernelEntityUpsertResponse(BaseModel):
    """Response for create-or-resolve operations."""

    model_config = ConfigDict(strict=True)

    entity: KernelEntityResponse
    created: bool


class KernelEntityBatchCreateRequest(BaseModel):
    """Batch request for creating (or resolving) kernel entities.

    The request body wraps a list of single ``KernelEntityCreateRequest``
    payloads.  The server processes them in order within a single
    transaction so that ontology loaders (MONDO, HPO, UBERON, etc.) can
    avoid the per-entity HTTP + commit overhead that dominates load times.
    """

    model_config = ConfigDict(strict=True)

    entities: list[KernelEntityCreateRequest] = Field(
        ...,
        min_length=1,
        max_length=500,
        description=(
            "Entities to create or resolve, processed in order. Capped at 500 "
            "per request to keep transactions bounded."
        ),
    )


class KernelEntityBatchCreateResponse(BaseModel):
    """Response for batch create-or-resolve operations.

    Returns one ``KernelEntityUpsertResponse`` per input entity in the same
    order as the request, plus aggregate counts so callers can quickly tell
    how much work happened.
    """

    model_config = ConfigDict(strict=True)

    results: list[KernelEntityUpsertResponse]
    created_count: int = Field(ge=0)
    resolved_count: int = Field(ge=0)


class KernelEntityListResponse(BaseModel):
    """List response for entities within a research space."""

    model_config = ConfigDict(strict=True)

    entities: list[KernelEntityResponse]
    total: int
    offset: int
    limit: int


class KernelEntitySimilarityScoreBreakdownResponse(BaseModel):
    """Score components for one similar-entity result row."""

    model_config = ConfigDict(strict=True)

    vector_score: float = Field(ge=0.0, le=1.0)
    graph_overlap_score: float = Field(ge=0.0, le=1.0)


class KernelEntitySimilarityResponse(BaseModel):
    """One similar-entity result row."""

    model_config = ConfigDict(strict=True)

    entity_id: UUID
    entity_type: str = Field(min_length=1, max_length=64)
    display_label: str | None = Field(default=None, max_length=512)
    similarity_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: KernelEntitySimilarityScoreBreakdownResponse


class KernelEntitySimilarityListResponse(BaseModel):
    """List response for similar entities in one research space."""

    model_config = ConfigDict(strict=True)

    source_entity_id: UUID
    results: list[KernelEntitySimilarityResponse]
    total: int
    limit: int
    min_similarity: float = Field(ge=0.0, le=1.0)


class KernelEntityEmbeddingRefreshRequest(BaseModel):
    """Request payload for explicit kernel entity embedding refresh operations."""

    model_config = ConfigDict(strict=False)

    entity_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=500)
    limit: int = Field(default=500, ge=1, le=5000)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    embedding_version: int | None = Field(default=None, ge=1, le=1000)


class KernelEntityEmbeddingRefreshResponse(BaseModel):
    """Response summary for explicit embedding refresh operations."""

    model_config = ConfigDict(strict=True)

    requested: int
    processed: int
    refreshed: int
    unchanged: int
    failed: int
    missing_entities: list[str]


class KernelEntityEmbeddingStatusResponse(BaseModel):
    """Per-entity readiness metadata for graph-owned embedding projections."""

    model_config = ConfigDict(strict=True)

    entity_id: UUID
    state: str = Field(min_length=1, max_length=16)
    desired_fingerprint: str = Field(min_length=64, max_length=64)
    embedding_model: str = Field(min_length=1, max_length=100)
    embedding_version: int = Field(ge=1)
    last_requested_at: datetime
    last_attempted_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    last_error_code: str | None = Field(default=None, max_length=64)
    last_error_message: str | None = Field(default=None, max_length=2000)


class KernelEntityEmbeddingStatusListResponse(BaseModel):
    """List response for graph-owned entity embedding readiness."""

    model_config = ConfigDict(strict=True)

    statuses: list[KernelEntityEmbeddingStatusResponse]
    total: int


class KernelRelationSuggestionRequest(BaseModel):
    """Request payload for dictionary-constrained relation suggestion runs."""

    model_config = ConfigDict(strict=False)

    source_entity_ids: list[UUID] = Field(min_length=1, max_length=50)
    limit_per_source: int = Field(default=10, ge=1, le=50)
    min_score: float = Field(default=0.70, ge=0.0, le=1.0)
    allowed_relation_types: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    target_entity_types: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=200,
    )
    exclude_existing_relations: bool = True
    require_all_ready: bool = False


class KernelRelationSuggestionScoreBreakdownResponse(BaseModel):
    """Score components for one relation suggestion row."""

    model_config = ConfigDict(strict=True)

    vector_score: float = Field(ge=0.0, le=1.0)
    graph_overlap_score: float = Field(ge=0.0, le=1.0)
    relation_prior_score: float = Field(ge=0.0, le=1.0)


class KernelRelationSuggestionConstraintCheckResponse(BaseModel):
    """Constraint trace proving dictionary validation for a suggestion row."""

    model_config = ConfigDict(strict=True)

    passed: bool
    source_entity_type: str = Field(min_length=1, max_length=64)
    relation_type: str = Field(min_length=1, max_length=64)
    target_entity_type: str = Field(min_length=1, max_length=64)


class KernelRelationSuggestionResponse(BaseModel):
    """One relation suggestion row."""

    model_config = ConfigDict(strict=True)

    source_entity_id: UUID
    target_entity_id: UUID
    relation_type: str = Field(min_length=1, max_length=64)
    final_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: KernelRelationSuggestionScoreBreakdownResponse
    constraint_check: KernelRelationSuggestionConstraintCheckResponse


class KernelRelationSuggestionSkippedSourceResponse(BaseModel):
    """One source entity skipped during relation suggestion."""

    model_config = ConfigDict(strict=True)

    entity_id: UUID
    state: str = Field(min_length=1, max_length=16)
    reason: str = Field(min_length=1, max_length=128)


class KernelRelationSuggestionListResponse(BaseModel):
    """List response for constrained relation suggestions."""

    model_config = ConfigDict(strict=True)

    suggestions: list[KernelRelationSuggestionResponse]
    total: int
    limit_per_source: int
    min_score: float = Field(ge=0.0, le=1.0)
    incomplete: bool = False
    skipped_sources: list[KernelRelationSuggestionSkippedSourceResponse] = Field(
        default_factory=list,
    )
