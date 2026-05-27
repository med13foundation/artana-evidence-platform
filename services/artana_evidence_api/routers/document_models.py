"""Response models for document router endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from artana_evidence_api.document_deletion.contracts import HarnessDocumentDeleteScope
from artana_evidence_api.document_store import normalize_document_title
from artana_evidence_api.routers.proposals import HarnessProposalResponse
from artana_evidence_api.routers.review_queue import HarnessReviewQueueItemResponse
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.types.common import JSONObject
from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

if TYPE_CHECKING:
    from artana_evidence_api.document_deletion.contracts import (
        HarnessDocumentDeleteResult,
    )
    from artana_evidence_api.document_store import HarnessDocumentRecord
    from artana_evidence_api.run_registry import HarnessRunRecord


CallPrepOutreachStatus = Literal[
    "annotation_prepared",
    "outreach_drafted",
    "email_sent",
    "awaiting_response",
    "call_scheduled",
    "call_completed",
    "collaboration_active",
    "declined",
]


class CallPrepOutreachTarget(BaseModel):
    """One contact target attached to a call-prep annotation document."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(..., min_length=1, max_length=256)
    email: EmailStr | None = None
    affiliation: str | None = Field(default=None, max_length=256)
    role: str | None = Field(default=None, max_length=128)

    @field_validator("name", "affiliation", "role")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class CallPrepAnnotationMetadata(BaseModel):
    """Document metadata convention for scientific call-prep annotations."""

    model_config = ConfigDict(strict=True, extra="allow")

    doc_type: Literal["call_prep_annotation"]
    outreach_status: CallPrepOutreachStatus
    ingest_source: str | None = Field(default=None, max_length=256)
    links_to_paper_pmid: str | None = Field(default=None, max_length=32)
    links_to_paper_doc_id: str | None = Field(default=None, max_length=64)
    links_to_workspace_claim: str | None = Field(default=None, max_length=64)
    patient_variant: str | None = Field(default=None, max_length=256)
    patient_name: str | None = Field(default=None, max_length=256)
    outreach_targets: list[CallPrepOutreachTarget] = Field(default_factory=list)
    related_workspace_claims: list[str] = Field(default_factory=list)
    sibling_papers_to_ingest: list[str] = Field(default_factory=list)

    @field_validator(
        "ingest_source",
        "links_to_paper_pmid",
        "links_to_paper_doc_id",
        "links_to_workspace_claim",
        "patient_variant",
        "patient_name",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("related_workspace_claims", "sibling_papers_to_ingest")
    @classmethod
    def normalize_string_list(cls, values: list[str]) -> list[str]:
        return [value for value in (" ".join(item.split()) for item in values) if value]


def normalize_document_metadata(metadata: JSONObject) -> JSONObject:
    """Validate and normalize source-specific document metadata conventions."""

    doc_type = metadata.get("doc_type")
    if doc_type != "call_prep_annotation":
        return dict(metadata)
    try:
        return CallPrepAnnotationMetadata.model_validate(metadata).model_dump(
            mode="json",
            exclude_none=True,
        )
    except ValueError as exc:
        msg = f"Invalid call_prep_annotation metadata: {exc}"
        raise ValueError(msg) from exc


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

    @model_validator(mode="after")
    def normalize_metadata(self) -> TextDocumentSubmitRequest:
        self.metadata = normalize_document_metadata(self.metadata)
        return self


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
    "CallPrepAnnotationMetadata",
    "CallPrepOutreachStatus",
    "CallPrepOutreachTarget",
    "HarnessDocumentDetailResponse",
    "HarnessDocumentExtractionResponse",
    "HarnessDocumentIngestionResponse",
    "HarnessDocumentListResponse",
    "HarnessDocumentResponse",
    "TextDocumentSubmitRequest",
    "normalize_document_metadata",
    "_document_extraction_response",
]
