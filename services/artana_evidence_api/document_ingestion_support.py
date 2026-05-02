"""Document ingestion run and PDF enrichment helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.document_extraction import (
    extract_pdf_text,
    sha256_hex,
)
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.runtime.pdf_text_diagnostics import (
    PdfTextDiagnosticError,
    require_extracted_pdf_text,
)
from artana_evidence_api.storage_types import StorageUseCase
from artana_evidence_api.types.common import JSONObject
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_binary_store import HarnessDocumentBinaryStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

_PDF_SIGNATURE = b"%PDF-"
_DOCUMENT_RUN_ERROR_RESERVED_KEYS = frozenset({"error", "status"})


def _require_updated_enriched_document(
    document: HarnessDocumentRecord | None,
) -> HarnessDocumentRecord:
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist enriched document content",
        )
    return document


def _resolve_graph_health(
    graph_api_gateway: GraphTransportBundle,
) -> tuple[str, str]:
    try:
        health = graph_api_gateway.get_health()
    except GraphServiceClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Graph API unavailable: {exc}",
        ) from exc
    return health.status, health.version


def _create_document_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    harness_id: str,
    input_payload: JSONObject,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphTransportBundle,
) -> HarnessRunRecord:
    graph_status, graph_version = _resolve_graph_health(graph_api_gateway)
    run = run_registry.create_run(
        space_id=space_id,
        harness_id=harness_id,
        title=title,
        input_payload=input_payload,
        graph_service_status=graph_status,
        graph_service_version=graph_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "running"},
    )
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    return run


def _complete_document_run(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    workspace_patch: JSONObject,
) -> HarnessRunRecord:
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "completed", **workspace_patch},
    )
    updated_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    return updated_run or run


def _fail_document_run(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    message: str,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    error_metadata: JSONObject | None = None,
) -> None:
    safe_error_metadata = {
        key: value
        for key, value in ({} if error_metadata is None else error_metadata).items()
        if key not in _DOCUMENT_RUN_ERROR_RESERVED_KEYS
    }
    error_content: JSONObject = {
        "error": message,
        **safe_error_metadata,
    }
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "failed", **error_content},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="document_error",
        media_type="application/json",
        content=error_content,
    )
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")


def _build_enriched_text_storage_key(
    *,
    document_id: str,
    text_content: str,
) -> str:
    content_hash = sha256_hex(text_content.encode("utf-8"))
    return f"documents/{document_id}/enriched/{content_hash}.txt"


def _validate_uploaded_pdf_payload(payload: bytes) -> None:
    if not payload.lstrip().startswith(_PDF_SIGNATURE):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded payload is not a PDF",
        )


async def _enrich_pdf_document(  # noqa: PLR0913
    *,
    space_id: UUID,
    document: HarnessDocumentRecord,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    binary_store: HarnessDocumentBinaryStore,
    document_store: HarnessDocumentStore,
    graph_api_gateway: GraphTransportBundle,
) -> HarnessDocumentRecord:
    if not isinstance(document.raw_storage_key, str) or document.raw_storage_key == "":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PDF raw payload is unavailable for enrichment",
        )
    enrichment_run = _create_document_run(
        space_id=space_id,
        title=f"Document Enrichment: {document.title}",
        harness_id="document-enrichment",
        input_payload={
            "document_id": document.id,
            "title": document.title,
            "source_type": document.source_type,
            "raw_storage_key": document.raw_storage_key,
        },
        run_registry=run_registry,
        artifact_store=artifact_store,
        graph_api_gateway=graph_api_gateway,
    )
    document_store.update_document(
        space_id=space_id,
        document_id=document.id,
        last_enrichment_run_id=enrichment_run.id,
        enrichment_status="running",
    )
    try:
        raw_payload = await binary_store.read_bytes(key=document.raw_storage_key)
        extraction = extract_pdf_text(raw_payload)
        normalized_text = require_extracted_pdf_text(extraction)
        enriched_storage_key = _build_enriched_text_storage_key(
            document_id=document.id,
            text_content=normalized_text,
        )
        await binary_store.store_bytes(
            use_case=StorageUseCase.DOCUMENT_CONTENT,
            key=enriched_storage_key,
            payload=normalized_text.encode("utf-8"),
            content_type="text/plain",
        )
        updated_document = _require_updated_enriched_document(
            document_store.update_document(
                space_id=space_id,
                document_id=document.id,
                page_count=extraction.page_count,
                text_content=normalized_text,
                enriched_storage_key=enriched_storage_key,
                last_enrichment_run_id=enrichment_run.id,
                enrichment_status="completed",
                metadata_patch={
                    "enriched_character_count": len(normalized_text),
                },
            ),
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=enrichment_run.id,
            artifact_key="document_enrichment_result",
            media_type="application/json",
            content={
                "document_id": document.id,
                "page_count": updated_document.page_count,
                "enriched_storage_key": enriched_storage_key,
                "text_excerpt": updated_document.text_excerpt,
            },
        )
        _complete_document_run(
            space_id=space_id,
            run=enrichment_run,
            artifact_store=artifact_store,
            run_registry=run_registry,
            workspace_patch={
                "document_id": document.id,
                "document_title": document.title,
                "document_source_type": document.source_type,
                "page_count": updated_document.page_count,
                "enriched_storage_key": enriched_storage_key,
            },
        )
    except PdfTextDiagnosticError as exc:
        document_store.update_document(
            space_id=space_id,
            document_id=document.id,
            last_enrichment_run_id=enrichment_run.id,
            page_count=exc.diagnostic.page_count,
            enrichment_status="failed",
            metadata_patch=exc.diagnostic.as_metadata(),
        )
        _fail_document_run(
            space_id=space_id,
            run=enrichment_run,
            message=exc.diagnostic.message,
            artifact_store=artifact_store,
            run_registry=run_registry,
            error_metadata={
                "reason_code": exc.diagnostic.reason_code,
                "ocr_required": exc.diagnostic.ocr_required,
                "page_count": exc.diagnostic.page_count,
                "pages_without_text": list(exc.diagnostic.pages_without_text),
            },
        )
        raise
    except Exception as exc:
        document_store.update_document(
            space_id=space_id,
            document_id=document.id,
            last_enrichment_run_id=enrichment_run.id,
            enrichment_status="failed",
        )
        _fail_document_run(
            space_id=space_id,
            run=enrichment_run,
            message=str(exc),
            artifact_store=artifact_store,
            run_registry=run_registry,
        )
        raise
    else:
        return updated_document


__all__ = [
    "_build_enriched_text_storage_key",
    "_complete_document_run",
    "_create_document_run",
    "_enrich_pdf_document",
    "_fail_document_run",
    "_resolve_graph_health",
    "_validate_uploaded_pdf_payload",
]
