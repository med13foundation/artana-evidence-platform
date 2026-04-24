"""Document source selection helpers for research-init runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.types.common import ResearchSpaceSourcePreferences

if TYPE_CHECKING:
    from artana_evidence_api.document_store import HarnessDocumentRecord


def classify_document_source(record: HarnessDocumentRecord) -> str:
    """Return the logical research-init source bucket for one stored document."""
    if record.source_type == "pubmed":
        return "pubmed"
    metadata_source = record.metadata.get("source")
    if metadata_source == "research-init-pubmed" or isinstance(
        record.metadata.get("pubmed"),
        dict,
    ):
        return "pubmed"
    if record.source_type == "pdf":
        return "pdf"
    if record.source_type == "text":
        return "text"
    return record.source_type


def is_research_init_pubmed_document(record: HarnessDocumentRecord) -> bool:
    """Return whether this document came from the research-init PubMed flow."""
    return record.metadata.get("source") == "research-init-pubmed"


def existing_documents_for_selected_sources(
    *,
    documents: list[HarnessDocumentRecord],
    sources: ResearchSpaceSourcePreferences,
) -> list[HarnessDocumentRecord]:
    """Select existing pending documents that belong to this run's sources."""
    selected: list[HarnessDocumentRecord] = []
    for document in documents:
        if document.extraction_status != "not_started":
            continue
        source_key = classify_document_source(document)
        if (
            (
                source_key == "pubmed"
                and sources.get("pubmed", True)
                and is_research_init_pubmed_document(document)
            )
            or (source_key == "text" and sources.get("text", True))
            or (source_key == "pdf" and sources.get("pdf", True))
        ):
            selected.append(document)
    return selected


def resolve_bootstrap_source_type(
    *,
    sources: ResearchSpaceSourcePreferences,
    document_workset: list[HarnessDocumentRecord],
) -> str | None:
    """Pick the bootstrap source type for the current document-driven run."""
    available_source_types = {
        classify_document_source(document) for document in document_workset
    }
    for source_key in ("pubmed", "text", "pdf"):
        if source_key in available_source_types and sources.get(source_key, True):
            return source_key
    if sources.get("pubmed", True):
        return "pubmed"
    return None
