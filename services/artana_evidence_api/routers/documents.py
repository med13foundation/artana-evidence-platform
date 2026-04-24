"""Document ingestion and extraction endpoints for the standalone harness service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import (
    UUID,  # noqa: TC003
    uuid4,
)

from artana_evidence_api.artifact_store import HarnessArtifactStore  # noqa: TC001
from artana_evidence_api.auth import (
    HarnessUser,  # noqa: TC001
    get_current_harness_user,
)
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_document_binary_store,
    get_document_store,
    get_graph_api_gateway,
    get_proposal_store,
    get_research_state_store,
    get_review_item_store,
    get_run_registry,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.document_binary_store import (
    HarnessDocumentBinaryStore,  # noqa: TC001
)
from artana_evidence_api.document_extraction import (
    DocumentCandidateExtractionDiagnostics,
    DocumentProposalReviewDiagnostics,
    build_document_extraction_drafts,
    build_document_review_context,
    extract_relation_candidates,
    extract_relation_candidates_with_diagnostics,
    normalize_text_document,
    review_document_extraction_drafts_with_diagnostics,
    sha256_hex,
)
from artana_evidence_api.document_ingestion_support import (
    _complete_document_run,
    _create_document_run,
    _enrich_pdf_document,
    _fail_document_run,
    _validate_uploaded_pdf_payload,
)
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,  # noqa: TC001
    HarnessDocumentStore,  # noqa: TC001
    normalize_document_title,
)
from artana_evidence_api.graph_client import (
    GraphTransportBundle,  # noqa: TC001
)
from artana_evidence_api.proposal_store import HarnessProposalStore  # noqa: TC001
from artana_evidence_api.research_state import (
    HarnessResearchStateStore,  # noqa: TC001
)
from artana_evidence_api.review_item_store import HarnessReviewItemStore  # noqa: TC001
from artana_evidence_api.routers.proposals import HarnessProposalResponse
from artana_evidence_api.routers.review_queue import HarnessReviewQueueItemResponse
from artana_evidence_api.routers.runs import HarnessRunResponse
from artana_evidence_api.run_registry import (
    HarnessRunRecord,
    HarnessRunRegistry,
)  # noqa: TC001
from artana_evidence_api.storage_types import StorageUseCase
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from artana_evidence_api.variant_aware_document_extraction import (
    document_supports_variant_aware_extraction,
    extract_variant_aware_document,
)
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from artana_evidence_api.proposal_store import (
        HarnessProposalDraft,
        HarnessProposalRecord,
    )
    from artana_evidence_api.review_item_store import (
        HarnessReviewItemDraft,
        HarnessReviewItemRecord,
    )

router = APIRouter(
    prefix="/v1/spaces",
    tags=["documents"],
)
_PDF_SIGNATURE = b"%PDF-"

_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_DOCUMENT_BINARY_STORE_DEPENDENCY = Depends(get_document_binary_store)
_DOCUMENT_STORE_DEPENDENCY = Depends(get_document_store)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_REVIEW_ITEM_STORE_DEPENDENCY = Depends(get_review_item_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_RESEARCH_STATE_STORE_DEPENDENCY = Depends(get_research_state_store)
_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)


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


def _extraction_diagnostics_metadata(
    *,
    candidate_diagnostics: DocumentCandidateExtractionDiagnostics,
    review_diagnostics: DocumentProposalReviewDiagnostics,
) -> JSONObject:
    return {
        **candidate_diagnostics.as_metadata(),
        **review_diagnostics.as_metadata(),
    }


def _candidate_discovery_metadata(
    *,
    method: str,
    regex_candidate_count: int,
    llm_diagnostics: JSONObject,
) -> JSONObject:
    llm_status = llm_diagnostics.get("llm_candidate_status")
    llm_attempted = llm_diagnostics.get("llm_candidate_attempted")
    llm_candidate_count = llm_diagnostics.get("llm_candidate_count")
    payload: JSONObject = {
        "method": method,
        "regex_candidate_count": regex_candidate_count,
        "llm_attempted": bool(llm_attempted),
        "llm_candidate_count": (
            int(llm_candidate_count) if isinstance(llm_candidate_count, int) else 0
        ),
        "llm_status": llm_status if isinstance(llm_status, str) else "not_needed",
    }
    llm_error = llm_diagnostics.get("llm_candidate_error")
    if isinstance(llm_error, str) and llm_error != "":
        payload["llm_error"] = llm_error
    fallback_candidate_count = llm_diagnostics.get("fallback_candidate_count")
    if isinstance(fallback_candidate_count, int) and fallback_candidate_count > 0:
        payload["fallback_candidate_count"] = fallback_candidate_count
    return payload


def _match_effective_proposal(
    *,
    proposals: list[HarnessProposalRecord],
    draft: HarnessProposalDraft,
) -> HarnessProposalRecord | None:
    if draft.claim_fingerprint:
        fingerprint_matches = [
            proposal
            for proposal in proposals
            if proposal.claim_fingerprint == draft.claim_fingerprint
        ]
        preferred_match = next(
            (
                proposal
                for proposal in fingerprint_matches
                if proposal.status in {"pending_review", "promoted"}
            ),
            None,
        )
        if preferred_match is not None:
            return preferred_match
        if fingerprint_matches:
            return fingerprint_matches[0]
    source_matches = [
        proposal
        for proposal in proposals
        if proposal.proposal_type == draft.proposal_type
        and proposal.source_key == draft.source_key
    ]
    preferred_source_match = next(
        (
            proposal
            for proposal in source_matches
            if proposal.status in {"pending_review", "promoted"}
        ),
        None,
    )
    if preferred_source_match is not None:
        return preferred_source_match
    if source_matches:
        return source_matches[0]
    return None


def _effective_proposals_for_drafts(
    *,
    space_id: UUID,
    document_id: str,
    created_proposals: list[HarnessProposalRecord],
    proposal_drafts: tuple[HarnessProposalDraft, ...],
    proposal_store: HarnessProposalStore,
) -> tuple[list[HarnessProposalRecord], int]:
    if not proposal_drafts:
        return [], 0
    available_proposals = proposal_store.list_proposals(
        space_id=space_id,
        document_id=document_id,
    )
    created_ids = {proposal.id for proposal in created_proposals}
    ordered_records: list[HarnessProposalRecord] = []
    seen_ids: set[str] = set()
    reused_existing_count = 0
    for draft in proposal_drafts:
        matched = _match_effective_proposal(proposals=available_proposals, draft=draft)
        if matched is None or matched.id in seen_ids:
            continue
        seen_ids.add(matched.id)
        ordered_records.append(matched)
        if matched.id not in created_ids:
            reused_existing_count += 1
    return ordered_records, reused_existing_count


def _match_effective_review_item(
    *,
    review_items: list[HarnessReviewItemRecord],
    draft: HarnessReviewItemDraft,
) -> HarnessReviewItemRecord | None:
    if draft.review_fingerprint:
        fingerprint_matches = [
            review_item
            for review_item in review_items
            if review_item.review_fingerprint == draft.review_fingerprint
        ]
        preferred_match = next(
            (
                review_item
                for review_item in fingerprint_matches
                if review_item.status == "pending_review"
            ),
            None,
        )
        if preferred_match is not None:
            return preferred_match
        if fingerprint_matches:
            return fingerprint_matches[0]
    source_matches = [
        review_item
        for review_item in review_items
        if review_item.review_type == draft.review_type
        and review_item.source_key == draft.source_key
    ]
    preferred_source_match = next(
        (
            review_item
            for review_item in source_matches
            if review_item.status == "pending_review"
        ),
        None,
    )
    if preferred_source_match is not None:
        return preferred_source_match
    if source_matches:
        return source_matches[0]
    return None


def _effective_review_items_for_drafts(
    *,
    space_id: UUID,
    document_id: str,
    created_review_items: list[HarnessReviewItemRecord],
    review_item_drafts: tuple[HarnessReviewItemDraft, ...],
    review_item_store: HarnessReviewItemStore,
) -> tuple[list[HarnessReviewItemRecord], int]:
    if not review_item_drafts:
        return [], 0
    available_review_items = review_item_store.list_review_items(
        space_id=space_id,
        document_id=document_id,
    )
    created_ids = {review_item.id for review_item in created_review_items}
    ordered_records: list[HarnessReviewItemRecord] = []
    seen_ids: set[str] = set()
    reused_existing_count = 0
    for draft in review_item_drafts:
        matched = _match_effective_review_item(
            review_items=available_review_items,
            draft=draft,
        )
        if matched is None or matched.id in seen_ids:
            continue
        seen_ids.add(matched.id)
        ordered_records.append(matched)
        if matched.id not in created_ids:
            reused_existing_count += 1
    return ordered_records, reused_existing_count


def _require_document(
    *,
    space_id: UUID,
    document_id: UUID,
    document_store: HarnessDocumentStore,
) -> HarnessDocumentRecord:
    record = document_store.get_document(space_id=space_id, document_id=document_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found in space '{space_id}'",
        )
    return record


def _duplicate_document_response(
    document: HarnessDocumentRecord,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Document already exists",
            "existing_document": HarnessDocumentDetailResponse.from_record(
                document,
            ).model_dump(mode="json"),
        },
    )


def _parse_metadata_json(raw_value: str | None) -> JSONObject:
    if raw_value is None or raw_value.strip() == "":
        return {}
    import json

    try:
        decoded = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="metadata_json must be valid JSON",
        ) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="metadata_json must decode to an object",
        )
    return decoded


def _build_raw_pdf_storage_key(
    *,
    document_id: str,
    sha256: str,
) -> str:
    return f"documents/{document_id}/raw/{sha256}.pdf"




@router.get(
    "/{space_id}/documents",
    response_model=HarnessDocumentListResponse,
    summary="List tracked documents",
    dependencies=[Depends(require_harness_space_read_access)],
)
def list_documents(
    space_id: UUID,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    *,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
) -> HarnessDocumentListResponse:
    documents = document_store.list_documents(space_id=space_id)
    total = len(documents)
    paged = documents[offset : offset + limit]
    return HarnessDocumentListResponse(
        documents=[HarnessDocumentResponse.from_record(record) for record in paged],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/documents/{document_id}",
    response_model=HarnessDocumentDetailResponse,
    summary="Get one tracked document",
    dependencies=[Depends(require_harness_space_read_access)],
)
def get_document(
    space_id: UUID,
    document_id: UUID,
    *,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
) -> HarnessDocumentDetailResponse:
    record = _require_document(
        space_id=space_id,
        document_id=document_id,
        document_store=document_store,
    )
    return HarnessDocumentDetailResponse.from_record(record)


@router.post(
    "/{space_id}/documents/text",
    response_model=HarnessDocumentIngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit one raw text document",
    dependencies=[Depends(require_harness_space_write_access)],
)
def submit_text_document(  # noqa: PLR0913
    space_id: UUID,
    request: TextDocumentSubmitRequest,
    *,
    force: bool = Query(default=False),
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> HarnessDocumentIngestionResponse | JSONResponse:
    normalized_text = normalize_text_document(request.text)
    if normalized_text == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document text cannot be blank",
        )
    content_sha256 = sha256_hex(normalized_text.encode("utf-8"))
    existing_document = (
        None
        if force
        else document_store.find_document_by_sha256(
            space_id=space_id,
            sha256=content_sha256,
        )
    )
    if existing_document is not None:
        return _duplicate_document_response(existing_document)
    run = _create_document_run(
        space_id=space_id,
        title=f"Document Ingestion: {request.title}",
        harness_id="document-ingestion",
        input_payload={
            "title": request.title,
            "source_type": "text",
            "byte_size": len(normalized_text.encode("utf-8")),
        },
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
    )
    try:
        record = document_store.create_document(
            space_id=space_id,
            created_by=current_user.id,
            title=request.title,
            source_type="text",
            filename=None,
            media_type="text/plain",
            sha256=content_sha256,
            byte_size=len(normalized_text.encode("utf-8")),
            page_count=None,
            text_content=normalized_text,
            raw_storage_key=None,
            enriched_storage_key=None,
            ingestion_run_id=run.id,
            last_enrichment_run_id=None,
            enrichment_status="skipped",
            extraction_status="not_started",
            metadata=request.metadata,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="document_ingestion",
            media_type="application/json",
            content={
                "document_id": record.id,
                "title": record.title,
                "source_type": record.source_type,
                "text_excerpt": record.text_excerpt,
            },
        )
        updated_run = _complete_document_run(
            space_id=space_id,
            run=run,
            artifact_store=artifact_store,
            run_registry=run_registry,
            workspace_patch={
                "document_id": record.id,
                "document_title": record.title,
                "document_source_type": record.source_type,
            },
        )
    except Exception as exc:
        _fail_document_run(
            space_id=space_id,
            run=run,
            message=str(exc),
            artifact_store=artifact_store,
            run_registry=run_registry,
        )
        raise
    finally:
        graph_api_gateway.close()
    return HarnessDocumentIngestionResponse(
        run=HarnessRunResponse.from_record(updated_run),
        document=HarnessDocumentDetailResponse.from_record(record),
    )


@router.post(
    "/{space_id}/documents/pdf",
    response_model=HarnessDocumentIngestionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload one PDF document",
    dependencies=[Depends(require_harness_space_write_access)],
)
async def upload_pdf_document(  # noqa: PLR0913
    space_id: UUID,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    metadata_json: str | None = Form(default=None),
    *,
    force: bool = Query(default=False),
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    binary_store: HarnessDocumentBinaryStore = _DOCUMENT_BINARY_STORE_DEPENDENCY,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
) -> HarnessDocumentIngestionResponse | JSONResponse:
    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded PDF payload was empty",
        )
    _validate_uploaded_pdf_payload(payload)
    resolved_title = (
        title.strip()
        if isinstance(title, str) and title.strip() != ""
        else (file.filename or "Uploaded PDF")
    )
    try:
        resolved_title = normalize_document_title(resolved_title)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    payload_sha256 = sha256_hex(payload)
    existing_document = (
        None
        if force
        else document_store.find_document_by_sha256(
            space_id=space_id,
            sha256=payload_sha256,
        )
    )
    if existing_document is not None:
        return _duplicate_document_response(existing_document)
    metadata = _parse_metadata_json(metadata_json)
    run = _create_document_run(
        space_id=space_id,
        title=f"Document Ingestion: {resolved_title}",
        harness_id="document-ingestion",
        input_payload={
            "title": resolved_title,
            "source_type": "pdf",
            "filename": file.filename,
            "byte_size": len(payload),
        },
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
    )
    try:
        document_id = str(uuid4())
        raw_storage_key = _build_raw_pdf_storage_key(
            document_id=document_id,
            sha256=payload_sha256,
        )
        await binary_store.store_bytes(
            use_case=StorageUseCase.PDF,
            key=raw_storage_key,
            payload=payload,
            content_type=file.content_type or "application/pdf",
        )
        record = document_store.create_document(
            document_id=document_id,
            space_id=space_id,
            created_by=current_user.id,
            title=resolved_title,
            source_type="pdf",
            filename=file.filename,
            media_type=file.content_type or "application/pdf",
            sha256=payload_sha256,
            byte_size=len(payload),
            page_count=None,
            text_content="",
            raw_storage_key=raw_storage_key,
            enriched_storage_key=None,
            ingestion_run_id=run.id,
            last_enrichment_run_id=None,
            enrichment_status="not_started",
            extraction_status="not_started",
            metadata=metadata,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="document_ingestion",
            media_type="application/json",
            content={
                "document_id": record.id,
                "title": record.title,
                "source_type": record.source_type,
                "filename": record.filename,
                "raw_storage_key": record.raw_storage_key,
            },
        )
        updated_run = _complete_document_run(
            space_id=space_id,
            run=run,
            artifact_store=artifact_store,
            run_registry=run_registry,
            workspace_patch={
                "document_id": record.id,
                "document_title": record.title,
                "document_source_type": record.source_type,
                "raw_storage_key": record.raw_storage_key,
            },
        )
    except Exception as exc:
        _fail_document_run(
            space_id=space_id,
            run=run,
            message=str(exc),
            artifact_store=artifact_store,
            run_registry=run_registry,
        )
        raise
    finally:
        graph_api_gateway.close()
    return HarnessDocumentIngestionResponse(
        run=HarnessRunResponse.from_record(updated_run),
        document=HarnessDocumentDetailResponse.from_record(record),
    )


@router.post(
    "/{space_id}/documents/{document_id}/extract",
    response_model=HarnessDocumentExtractionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Extract reviewable findings from one document",
    description=(
        "Read one tracked document and stage governed review outputs. The response "
        "can include promotable proposals, review-only items for human follow-up, "
        "and skipped diagnostics for anything the extraction layer chose not to "
        "stage."
    ),
    dependencies=[Depends(require_harness_space_write_access)],
)
async def extract_document(  # noqa: PLR0913, PLR0915
    space_id: UUID,
    document_id: UUID,
    use_llm: bool = Query(  # noqa: FBT001
        default=False,
        description="Force LLM-first candidate discovery before heuristic extraction.",
    ),
    *,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    binary_store: HarnessDocumentBinaryStore = _DOCUMENT_BINARY_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    research_state_store: HarnessResearchStateStore = _RESEARCH_STATE_STORE_DEPENDENCY,
) -> HarnessDocumentExtractionResponse:
    document = _require_document(
        space_id=space_id,
        document_id=document_id,
        document_store=document_store,
    )
    if (
        document.extraction_status == "completed"
        and document.last_extraction_run_id is not None
    ):
        existing_run = run_registry.get_run(
            space_id=space_id,
            run_id=document.last_extraction_run_id,
        )
        if existing_run is not None:
            existing_proposals = [
                HarnessProposalResponse.from_record(record)
                for record in proposal_store.list_proposals(
                    space_id=space_id,
                    run_id=existing_run.id,
                    document_id=document.id,
                )
            ]
            existing_review_items = [
                HarnessReviewQueueItemResponse.from_review_item(record)
                for record in review_item_store.list_review_items(
                    space_id=space_id,
                    run_id=existing_run.id,
                    document_id=document.id,
                )
            ]
            extraction_result = artifact_store.get_artifact(
                space_id=space_id,
                run_id=existing_run.id,
                artifact_key="document_extraction_result",
            )
            skipped_candidates = []
            if extraction_result is not None:
                artifact_skips = extraction_result.content.get("skipped_candidates")
                if isinstance(artifact_skips, list):
                    skipped_candidates = [
                        candidate
                        for candidate in artifact_skips
                        if isinstance(candidate, dict)
                    ]
            graph_api_gateway.close()
            return _document_extraction_response(
                run=existing_run,
                document=document,
                proposals=existing_proposals,
                review_items=existing_review_items,
                skipped_candidates=skipped_candidates,
            )
    if document.source_type == "pdf" and document.enrichment_status != "completed":
        document = await _enrich_pdf_document(
            space_id=space_id,
            document=document,
            run_registry=run_registry,
            artifact_store=artifact_store,
            binary_store=binary_store,
            document_store=document_store,
            graph_api_gateway=graph_api_gateway,
        )
    if document.text_content.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document does not yet have extractable text content",
        )
    run = _create_document_run(
        space_id=space_id,
        title=f"Document Extraction: {document.title}",
        harness_id="document-extraction",
        input_payload={
            "document_id": document.id,
            "title": document.title,
            "source_type": document.source_type,
            "last_enrichment_run_id": document.last_enrichment_run_id,
            "use_llm": use_llm,
        },
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
    )
    document_store.update_document(
        space_id=space_id,
        document_id=document.id,
        last_extraction_run_id=run.id,
        extraction_status="running",
    )
    try:
        research_state = research_state_store.get_state(space_id=space_id)
        review_context = build_document_review_context(
            objective=(
                research_state.objective if research_state is not None else None
            ),
            current_hypotheses=(
                research_state.current_hypotheses
                if research_state is not None
                else None
            ),
            pending_questions=(
                research_state.pending_questions if research_state is not None else None
            ),
            explored_questions=(
                research_state.explored_questions
                if research_state is not None
                else None
            ),
        )
        if document_supports_variant_aware_extraction(document=document):
            variant_result = await extract_variant_aware_document(
                space_id=space_id,
                document=document,
                graph_api_gateway=graph_api_gateway,
                review_context=review_context,
            )
            created_proposals = proposal_store.create_proposals(
                space_id=space_id,
                run_id=run.id,
                proposals=variant_result.proposal_drafts,
            )
            created_review_items = review_item_store.create_review_items(
                space_id=space_id,
                run_id=run.id,
                review_items=variant_result.review_item_drafts,
            )
            proposals, reused_existing_proposal_count = _effective_proposals_for_drafts(
                space_id=space_id,
                document_id=document.id,
                created_proposals=created_proposals,
                proposal_drafts=variant_result.proposal_drafts,
                proposal_store=proposal_store,
            )
            effective_review_items, reused_existing_review_item_count = (
                _effective_review_items_for_drafts(
                    space_id=space_id,
                    document_id=document.id,
                    created_review_items=created_review_items,
                    review_item_drafts=variant_result.review_item_drafts,
                    review_item_store=review_item_store,
                )
            )
            skipped_candidates = variant_result.skipped_items
            updated_document = document_store.update_document(
                space_id=space_id,
                document_id=document.id,
                last_extraction_run_id=run.id,
                extraction_status="completed",
                metadata_patch={
                    "candidate_count": (
                        len(variant_result.contract.entities)
                        + len(variant_result.contract.observations)
                        + len(variant_result.contract.relations)
                    ),
                    "proposal_count": len(proposals),
                    "review_item_count": len(effective_review_items),
                    "skipped_candidate_count": len(skipped_candidates),
                    "reused_existing_proposal_count": reused_existing_proposal_count,
                    "reused_existing_review_item_count": (
                        reused_existing_review_item_count
                    ),
                    "candidate_discovery": variant_result.candidate_discovery,
                    "extraction_diagnostics": variant_result.extraction_diagnostics,
                    "variant_aware_extraction": True,
                    "last_enrichment_run_id": document.last_enrichment_run_id,
                },
            )
            if updated_document is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update extracted document state",
                )
            artifact_store.put_artifact(
                space_id=space_id,
                run_id=run.id,
                artifact_key="document_extraction_result",
                media_type="application/json",
                content={
                    "document_id": document.id,
                    "candidate_count": (
                        len(variant_result.contract.entities)
                        + len(variant_result.contract.observations)
                        + len(variant_result.contract.relations)
                    ),
                    "proposal_count": len(proposals),
                    "proposal_ids": [proposal.id for proposal in proposals],
                    "review_item_count": len(effective_review_items),
                    "review_item_ids": [
                        review_item.id for review_item in effective_review_items
                    ],
                    "skipped_candidates": skipped_candidates,
                    "reused_existing_proposal_count": reused_existing_proposal_count,
                    "reused_existing_review_item_count": (
                        reused_existing_review_item_count
                    ),
                    "candidate_discovery": variant_result.candidate_discovery,
                    "extraction_diagnostics": variant_result.extraction_diagnostics,
                    "variant_aware_extraction": True,
                    "last_enrichment_run_id": document.last_enrichment_run_id,
                },
            )
            updated_run = _complete_document_run(
                space_id=space_id,
                run=run,
                artifact_store=artifact_store,
                run_registry=run_registry,
                workspace_patch={
                    "document_id": document.id,
                    "proposal_count": len(proposals),
                    "review_item_count": len(effective_review_items),
                    "skipped_candidate_count": len(skipped_candidates),
                    "reused_existing_proposal_count": reused_existing_proposal_count,
                    "reused_existing_review_item_count": (
                        reused_existing_review_item_count
                    ),
                    "candidate_discovery": variant_result.candidate_discovery,
                    "extraction_diagnostics": variant_result.extraction_diagnostics,
                    "variant_aware_extraction": True,
                    "last_enrichment_run_id": document.last_enrichment_run_id,
                    "last_document_extraction_result_key": "document_extraction_result",
                },
            )
            return _document_extraction_response(
                run=updated_run,
                document=updated_document,
                proposals=[
                    HarnessProposalResponse.from_record(record) for record in proposals
                ],
                review_items=[
                    HarnessReviewQueueItemResponse.from_review_item(record)
                    for record in effective_review_items
                ],
                skipped_candidates=skipped_candidates,
            )
        if use_llm:
            candidates, candidate_diagnostics = (
                await extract_relation_candidates_with_diagnostics(
                    document.text_content,
                    space_context=review_context.objective or "",
                )
            )
            candidate_discovery = _candidate_discovery_metadata(
                method=(
                    "llm"
                    if candidate_diagnostics.llm_candidate_status == "completed"
                    else "regex"
                ),
                regex_candidate_count=(
                    candidate_diagnostics.fallback_candidate_count
                    if candidate_diagnostics.llm_candidate_status != "completed"
                    else 0
                ),
                llm_diagnostics=candidate_diagnostics.as_metadata(),
            )
        else:
            candidates = extract_relation_candidates(document.text_content)
            if candidates:
                candidate_diagnostics = DocumentCandidateExtractionDiagnostics(
                    llm_candidate_status="not_needed",
                )
                candidate_discovery = {
                    "method": "regex",
                    "regex_candidate_count": len(candidates),
                    "llm_attempted": False,
                    "llm_candidate_count": 0,
                    "llm_status": "not_needed",
                }
            else:
                candidates, candidate_diagnostics = (
                    await extract_relation_candidates_with_diagnostics(
                        document.text_content,
                        space_context=review_context.objective or "",
                    )
                )
                candidate_discovery = _candidate_discovery_metadata(
                    method=(
                        "llm"
                        if candidate_diagnostics.llm_candidate_status == "completed"
                        else "regex"
                    ),
                    regex_candidate_count=0,
                    llm_diagnostics=candidate_diagnostics.as_metadata(),
                )
        drafts, skipped_candidates = build_document_extraction_drafts(
            space_id=space_id,
            document=document,
            candidates=candidates,
            graph_api_gateway=graph_api_gateway,
            review_context=review_context,
        )
        (
            drafts,
            review_diagnostics,
        ) = await review_document_extraction_drafts_with_diagnostics(
            document=document,
            candidates=candidates,
            drafts=drafts,
            review_context=review_context,
        )
        extraction_diagnostics = _extraction_diagnostics_metadata(
            candidate_diagnostics=candidate_diagnostics,
            review_diagnostics=review_diagnostics,
        )
        if not candidates:
            skipped_candidates.append(
                {
                    "document_id": document.id,
                    "document_title": document.title,
                    "reason": (
                        "No relation candidates matched the current extraction "
                        "heuristics."
                    ),
                },
            )
        created_proposals = proposal_store.create_proposals(
            space_id=space_id,
            run_id=run.id,
            proposals=drafts,
        )
        proposals, reused_existing_proposal_count = _effective_proposals_for_drafts(
            space_id=space_id,
            document_id=document.id,
            created_proposals=created_proposals,
            proposal_drafts=drafts,
            proposal_store=proposal_store,
        )
        review_item_responses: list[HarnessReviewQueueItemResponse] = []
        updated_document = document_store.update_document(
            space_id=space_id,
            document_id=document.id,
            last_extraction_run_id=run.id,
            extraction_status="completed",
            metadata_patch={
                "candidate_count": len(candidates),
                "proposal_count": len(proposals),
                "review_item_count": len(review_item_responses),
                "skipped_candidate_count": len(skipped_candidates),
                "reused_existing_proposal_count": reused_existing_proposal_count,
                "candidate_discovery": candidate_discovery,
                "extraction_diagnostics": extraction_diagnostics,
                "last_enrichment_run_id": document.last_enrichment_run_id,
            },
        )
        if updated_document is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update extracted document state",
            )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="document_extraction_result",
            media_type="application/json",
            content={
                "document_id": document.id,
                "candidate_count": len(candidates),
                "proposal_count": len(proposals),
                "proposal_ids": [proposal.id for proposal in proposals],
                "review_item_count": len(review_item_responses),
                "review_item_ids": [],
                "skipped_candidates": skipped_candidates,
                "reused_existing_proposal_count": reused_existing_proposal_count,
                "candidate_discovery": candidate_discovery,
                "extraction_diagnostics": extraction_diagnostics,
                "last_enrichment_run_id": document.last_enrichment_run_id,
            },
        )
        updated_run = _complete_document_run(
            space_id=space_id,
            run=run,
            artifact_store=artifact_store,
            run_registry=run_registry,
            workspace_patch={
                "document_id": document.id,
                "proposal_count": len(proposals),
                "review_item_count": len(review_item_responses),
                "skipped_candidate_count": len(skipped_candidates),
                "reused_existing_proposal_count": reused_existing_proposal_count,
                "candidate_discovery": candidate_discovery,
                "extraction_diagnostics": extraction_diagnostics,
                "last_enrichment_run_id": document.last_enrichment_run_id,
                "last_document_extraction_result_key": "document_extraction_result",
            },
        )
    except Exception as exc:
        document_store.update_document(
            space_id=space_id,
            document_id=document.id,
            last_extraction_run_id=run.id,
            extraction_status="failed",
        )
        _fail_document_run(
            space_id=space_id,
            run=run,
            message=str(exc),
            artifact_store=artifact_store,
            run_registry=run_registry,
        )
        raise
    finally:
        graph_api_gateway.close()
    return _document_extraction_response(
        run=updated_run,
        document=updated_document,
        proposals=[HarnessProposalResponse.from_record(record) for record in proposals],
        review_items=review_item_responses,
        skipped_candidates=skipped_candidates,
    )


__all__ = [
    "HarnessDocumentDetailResponse",
    "HarnessDocumentExtractionResponse",
    "HarnessDocumentIngestionResponse",
    "HarnessDocumentListResponse",
    "HarnessDocumentResponse",
    "TextDocumentSubmitRequest",
    "extract_document",
    "get_document",
    "list_documents",
    "router",
    "submit_text_document",
    "upload_pdf_document",
]
