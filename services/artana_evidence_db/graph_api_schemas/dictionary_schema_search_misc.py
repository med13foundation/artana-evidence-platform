# ruff: noqa: TC001,TC003
"""Search/changelog/reembed schemas for dictionary admin routes."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.kernel_domain_models import (
    DictionaryChangelog,
    DictionaryDomainContext,
    DictionarySearchResult,
)
from pydantic import BaseModel, ConfigDict, Field

from .dictionary_schema_common import KernelDictionaryDimension, KernelSearchMatchMethod


class DictionaryChangelogResponse(BaseModel):
    """Response payload for a dictionary changelog entry."""

    model_config = ConfigDict(strict=True)

    id: int
    table_name: str
    record_id: str
    action: str
    before_snapshot: JSONObject | None
    after_snapshot: JSONObject | None
    changed_by: str | None
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: DictionaryChangelog) -> DictionaryChangelogResponse:
        return cls(
            id=int(model.id),
            table_name=str(model.table_name),
            record_id=str(model.record_id),
            action=str(model.action),
            before_snapshot=(
                dict(model.before_snapshot)
                if model.before_snapshot is not None
                else None
            ),
            after_snapshot=(
                dict(model.after_snapshot) if model.after_snapshot is not None else None
            ),
            changed_by=str(model.changed_by) if model.changed_by else None,
            source_ref=str(model.source_ref) if model.source_ref else None,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class DictionaryChangelogListResponse(BaseModel):
    """List response payload for dictionary changelog entries."""

    model_config = ConfigDict(strict=True)

    changelog_entries: list[DictionaryChangelogResponse]
    total: int


class DictionarySearchResultResponse(BaseModel):
    """Response payload for one dictionary search hit."""

    model_config = ConfigDict(strict=True)

    dimension: KernelDictionaryDimension
    entry_id: str
    display_name: str
    description: str | None
    domain_context: str | None
    match_method: KernelSearchMatchMethod
    similarity_score: float
    metadata: JSONObject

    @classmethod
    def from_model(
        cls,
        model: DictionarySearchResult,
    ) -> DictionarySearchResultResponse:
        return cls(
            dimension=KernelDictionaryDimension(model.dimension),
            entry_id=str(model.entry_id),
            display_name=str(model.display_name),
            description=str(model.description) if model.description else None,
            domain_context=str(model.domain_context) if model.domain_context else None,
            match_method=KernelSearchMatchMethod(model.match_method),
            similarity_score=float(model.similarity_score),
            metadata=dict(model.metadata) if model.metadata else {},
        )


class DictionarySearchListResponse(BaseModel):
    """List response payload for dictionary search endpoints."""

    model_config = ConfigDict(strict=True)

    results: list[DictionarySearchResultResponse]
    total: int


class DictionaryDomainContextResponse(BaseModel):
    """Response payload for one dictionary domain context."""

    model_config = ConfigDict(strict=True)

    id: str
    display_name: str
    description: str | None
    is_active: bool
    valid_from: datetime | None
    valid_to: datetime | None
    superseded_by: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(
        cls,
        model: DictionaryDomainContext,
    ) -> DictionaryDomainContextResponse:
        return cls(
            id=str(model.id),
            display_name=str(model.display_name),
            description=str(model.description) if model.description else None,
            is_active=bool(model.is_active),
            valid_from=model.valid_from,
            valid_to=model.valid_to,
            superseded_by=str(model.superseded_by) if model.superseded_by else None,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class DictionaryDomainContextListResponse(BaseModel):
    """List response payload for dictionary domain contexts."""

    model_config = ConfigDict(strict=True)

    domain_contexts: list[DictionaryDomainContextResponse]
    total: int


class DictionaryReembedRequest(BaseModel):
    """Request payload for dictionary embedding refresh jobs."""

    model_config = ConfigDict(strict=False)

    model_name: str | None = Field(
        default=None,
        max_length=64,
        description="Embedding model to use (defaults to service setting)",
    )
    limit_per_dimension: int | None = Field(
        default=None,
        ge=1,
        le=5000,
        description="Optional cap per dimension for partial re-embed runs",
    )
    source_ref: str | None = Field(
        default=None,
        max_length=1024,
        description="Optional provenance pointer for the refresh request",
    )


class DictionaryReembedResponse(BaseModel):
    """Response payload for dictionary embedding refresh jobs."""

    model_config = ConfigDict(strict=True)

    updated_records: int
    model_name: str | None


__all__ = [
    "DictionaryChangelogListResponse",
    "DictionaryChangelogResponse",
    "DictionaryDomainContextListResponse",
    "DictionaryDomainContextResponse",
    "DictionaryReembedRequest",
    "DictionaryReembedResponse",
    "DictionarySearchListResponse",
    "DictionarySearchResultResponse",
]
