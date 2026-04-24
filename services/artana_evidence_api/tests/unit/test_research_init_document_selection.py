"""Tests for research-init document source selection helpers."""

from __future__ import annotations

from uuid import uuid4

from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.research_init_document_selection import (
    classify_document_source,
    existing_documents_for_selected_sources,
    is_research_init_pubmed_document,
    resolve_bootstrap_source_type,
)
from artana_evidence_api.types.common import JSONObject


def _stored_document(
    store: HarnessDocumentStore,
    *,
    source_type: str,
    extraction_status: str = "not_started",
    metadata: JSONObject | None = None,
) -> HarnessDocumentRecord:
    return store.create_document(
        space_id=uuid4(),
        created_by=uuid4(),
        title=f"{source_type} source",
        source_type=source_type,
        filename=None,
        media_type="text/plain",
        sha256=f"{source_type}-{extraction_status}",
        byte_size=12,
        page_count=None,
        text_content="source text",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=uuid4(),
        enrichment_status="completed",
        extraction_status=extraction_status,
        metadata=metadata,
    )


def test_classify_document_source_uses_research_init_pubmed_metadata() -> None:
    store = HarnessDocumentStore()
    direct_pubmed = _stored_document(store, source_type="pubmed")
    metadata_pubmed = _stored_document(
        store,
        source_type="text",
        metadata={"source": "research-init-pubmed"},
    )
    pubmed_payload = _stored_document(
        store,
        source_type="pdf",
        metadata={"pubmed": {"pmid": "12345"}},
    )

    assert classify_document_source(direct_pubmed) == "pubmed"
    assert classify_document_source(metadata_pubmed) == "pubmed"
    assert classify_document_source(pubmed_payload) == "pubmed"
    assert is_research_init_pubmed_document(metadata_pubmed)
    assert not is_research_init_pubmed_document(pubmed_payload)


def test_existing_documents_for_selected_sources_only_returns_pending_run_sources() -> (
    None
):
    store = HarnessDocumentStore()
    research_pubmed = _stored_document(
        store,
        source_type="pubmed",
        metadata={"source": "research-init-pubmed"},
    )
    external_pubmed = _stored_document(store, source_type="pubmed")
    text_document = _stored_document(store, source_type="text")
    completed_pdf = _stored_document(
        store,
        source_type="pdf",
        extraction_status="completed",
    )

    selected = existing_documents_for_selected_sources(
        documents=[research_pubmed, external_pubmed, text_document, completed_pdf],
        sources={"pubmed": True, "text": True, "pdf": True},
    )

    assert selected == [research_pubmed, text_document]


def test_resolve_bootstrap_source_type_prefers_selected_workset_order() -> None:
    store = HarnessDocumentStore()
    pdf_document = _stored_document(store, source_type="pdf")
    text_document = _stored_document(store, source_type="text")
    pubmed_document = _stored_document(
        store,
        source_type="pubmed",
        metadata={"source": "research-init-pubmed"},
    )

    assert (
        resolve_bootstrap_source_type(
            sources={"pubmed": False, "text": True, "pdf": True},
            document_workset=[pdf_document, text_document, pubmed_document],
        )
        == "text"
    )
    assert (
        resolve_bootstrap_source_type(
            sources={"pubmed": True, "text": True, "pdf": True},
            document_workset=[pdf_document, text_document, pubmed_document],
        )
        == "pubmed"
    )
    assert (
        resolve_bootstrap_source_type(
            sources={"pubmed": True},
            document_workset=[],
        )
        == "pubmed"
    )
    assert (
        resolve_bootstrap_source_type(
            sources={"pubmed": False},
            document_workset=[],
        )
        is None
    )
