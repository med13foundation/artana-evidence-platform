"""Helpers for claim-evidence paper-link normalization within the graph service."""

from __future__ import annotations

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.paper_links import resolve_paper_links
from artana_evidence_db.service_contracts import KernelRelationPaperLinkResponse
from artana_evidence_db.source_document_model import SourceDocumentModel


def _normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _external_document_ref_link(
    source_document_ref: str | None,
) -> KernelRelationPaperLinkResponse | None:
    normalized_ref = _normalize_optional_text(source_document_ref)
    if normalized_ref is None:
        return None
    if not normalized_ref.startswith(("http://", "https://")):
        return None
    return KernelRelationPaperLinkResponse(
        label="External document",
        url=normalized_ref,
        source="external_ref",
    )


def resolve_claim_evidence_paper_links(
    *,
    source_document: SourceDocumentModel | None,
    evidence_metadata: JSONObject,
    source_document_ref: str | None = None,
) -> list[KernelRelationPaperLinkResponse]:
    """Resolve normalized paper links from claim evidence metadata and source docs."""
    combined_links: list[JSONObject] = []
    metadata_links = resolve_paper_links(
        source_type=None,
        external_record_id=None,
        metadata=evidence_metadata,
    )
    combined_links.extend(metadata_links)

    if source_document is not None:
        source_document_metadata_payload = source_document.metadata_payload
        source_document_metadata: JSONObject = (
            source_document_metadata_payload
            if isinstance(source_document_metadata_payload, dict)
            else {}
        )
        source_document_links = resolve_paper_links(
            source_type=source_document.source_type,
            external_record_id=source_document.external_record_id,
            metadata=source_document_metadata,
        )
        combined_links.extend(source_document_links)
    external_ref_link = _external_document_ref_link(source_document_ref)
    if external_ref_link is not None:
        combined_links.append(
            {
                "label": external_ref_link.label,
                "url": external_ref_link.url,
                "source": external_ref_link.source,
            },
        )

    normalized_links: list[KernelRelationPaperLinkResponse] = []
    seen_urls: set[str] = set()
    for link in combined_links:
        label = _normalize_optional_text(link.get("label"))
        url = _normalize_optional_text(link.get("url"))
        source = _normalize_optional_text(link.get("source"))
        if label is None or url is None or source is None:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        normalized_links.append(
            KernelRelationPaperLinkResponse(
                label=label,
                url=url,
                source=source,
            ),
        )
    return normalized_links


__all__ = ["resolve_claim_evidence_paper_links"]
