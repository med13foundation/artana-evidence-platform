"""Response models for document router endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.document_deletion.contracts import HarnessDocumentDeleteScope
from artana_evidence_api.document_store import normalize_document_title
from artana_evidence_api.routers.proposals import HarnessProposalResponse
from artana_evidence_api.routers.review_queue import HarnessReviewQueueItemResponse
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from artana_evidence_api.document_deletion.contracts import (
        HarnessDocumentDeleteResult,
    )
    from artana_evidence_api.document_store import HarnessDocumentRecord
    from artana_evidence_api.run_registry import HarnessRunRecord

class TextDocumentSubmitRequest(BaseModel):
    """Request payload for raw text document submission."""

    model_config = ConfigDict(strict=True)

    title: str = Field(..., min_length=1, max_length=256)
    text: str = Field(..., min_length=1, max_length=120000)
    metadata: JSONObject = Field(default_factory=dict)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return normalize_document_title(value)


class HarnessDocumentResponse(BaseModel):
    """Serialized summary view for one tracked harness document."""

    model_config = ConfigDict(strict=True)

    id: str
    space_id: str
    created_by: str
    title: str
    source_type: str
    filename: str | None
    media_type: str
    sha256: str
    byte_size: int
    page_count: int | None
    text_excerpt: str
    ingestion_run_id: str
    last_enrichment_run_id: str | None
    last_extraction_run_id: str | None
    enrichment_status: str
    extraction_status: str
    metadata: JSONObject
    created_at: str
    updated_at: str

    @classmethod
    def from_record(cls, record: HarnessDocumentRecord) -> HarnessDocumentResponse:
        return cls(
            id=record.id,
            space_id=record.space_id,
            created_by=record.created_by,
            title=record.title,
            source_type=record.source_type,
            filename=record.filename,
            media_type=record.media_type,
            sha256=record.sha256,
            byte_size=record.byte_size,
            page_count=record.page_count,
            text_excerpt=record.text_excerpt,
            ingestion_run_id=record.ingestion_run_id,
            last_enrichment_run_id=record.last_enrichment_run_id,
            last_extraction_run_id=record.last_extraction_run_id,
            enrichment_status=record.enrichment_status,
            extraction_status=record.extraction_status,
            metadata=record.metadata,
            created_at=record.created_at.isoformat(),
            updated_at=record.updated_at.isoformat(),
        )


class HarnessDocumentDetailResponse(HarnessDocumentResponse):
    """Detailed view for one tracked document."""

    text_content: str

    @classmethod
    def from_record(
        cls,
        record: HarnessDocumentRecord,
    ) -> HarnessDocumentDetailResponse:
        return cls(
            **HarnessDocumentResponse.from_record(record).model_dump(mode="json"),
            text_content=record.text_content,
        )


class HarnessDocumentListResponse(BaseModel):
    """List response for harness-tracked documents."""

    model_config = ConfigDict(strict=True)

    documents: list[HarnessDocumentResponse]
    total: int
    offset: int
    limit: int


class HarnessDocumentIngestionResponse(BaseModel):
    """Response payload for document ingestion endpoints."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    document: HarnessDocumentDetailResponse


class HarnessDocumentDeleteResponse(BaseModel):
    """Response payload for supported document deletion."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    scope: HarnessDocumentDeleteScope
    deleted_documents: list[HarnessDocumentResponse] = Field(default_factory=list)
    deleted_document_count: int = Field(ge=0)
    deleted_proposal_count: int = Field(ge=0)
    deleted_review_item_count: int = Field(ge=0)
    deleted_study_outcome_count: int = Field(ge=0)

    @classmethod
    def from_result(
        cls,
        result: HarnessDocumentDeleteResult,
    ) -> HarnessDocumentDeleteResponse:
        return cls(
            run=HarnessRunResponse.from_record(result.run),
            scope=result.scope,
            deleted_documents=[
                HarnessDocumentResponse.from_record(document)
                for document in result.deleted_documents
            ],
            deleted_document_count=result.deleted_document_count,
            deleted_proposal_count=result.deleted_proposal_count,
            deleted_review_item_count=result.deleted_review_item_count,
            deleted_study_outcome_count=result.deleted_study_outcome_count,
        )


class HarnessDocumentExtractionResponse(BaseModel):
    """Response payload for document extraction runs."""

    model_config = ConfigDict(strict=True)

    run: HarnessRunResponse
    document: HarnessDocumentDetailResponse
    proposals: list[HarnessProposalResponse]
    proposal_count: int
    review_items: list[HarnessReviewQueueItemResponse]
    review_item_count: int
    skipped_candidates: list[JSONObject]


def _document_extraction_response(
    *,
    run: HarnessRunRecord,
    document: HarnessDocumentRecord,
    proposals: list[HarnessProposalResponse],
    review_items: list[HarnessReviewQueueItemResponse],
    skipped_candidates: list[JSONObject],
) -> HarnessDocumentExtractionResponse:
    return HarnessDocumentExtractionResponse(
        run=HarnessRunResponse.from_record(run),
        document=HarnessDocumentDetailResponse.from_record(document),
        proposals=proposals,
        proposal_count=len(proposals),
        review_items=review_items,
        review_item_count=len(review_items),
        skipped_candidates=skipped_candidates,
    )

__all__ = [
    "HarnessDocumentDetailResponse",
    "HarnessDocumentExtractionResponse",
    "HarnessDocumentIngestionResponse",
    "HarnessDocumentListResponse",
    "HarnessDocumentResponse",
    "TextDocumentSubmitRequest",
    "_document_extraction_response",
]
