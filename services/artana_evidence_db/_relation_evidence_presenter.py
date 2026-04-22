"""Evidence-presentation helpers for graph relation list responses."""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from artana_evidence_db.kernel_relation_models import RelationEvidenceModel
from artana_evidence_db.paper_links import resolve_paper_links
from artana_evidence_db.service_contracts import KernelRelationPaperLinkResponse
from artana_evidence_db.source_document_model import SourceDocumentModel
from sqlalchemy import select
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class RelationEvidencePresentation:
    """Latest evidence payload to enrich relation list rows."""

    evidence_summary: str | None
    evidence_sentence: str | None
    evidence_sentence_source: str | None
    evidence_sentence_confidence: str | None
    evidence_sentence_rationale: str | None
    paper_links: list[KernelRelationPaperLinkResponse]


def _normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _resolve_relation_paper_links(
    *,
    source_document: SourceDocumentModel | None,
    source_document_ref: str | None = None,
) -> list[KernelRelationPaperLinkResponse]:
    normalized_ref = _normalize_optional_text(source_document_ref)
    external_ref_link = (
        KernelRelationPaperLinkResponse(
            label="External document",
            url=normalized_ref,
            source="external_ref",
        )
        if normalized_ref is not None
        and normalized_ref.startswith(("http://", "https://"))
        else None
    )
    if source_document is None:
        return [] if external_ref_link is None else [external_ref_link]
    metadata_payload = source_document.metadata_payload
    metadata = metadata_payload if isinstance(metadata_payload, dict) else {}
    links = resolve_paper_links(
        source_type=source_document.source_type,
        external_record_id=source_document.external_record_id,
        metadata=metadata,
    )
    normalized: list[KernelRelationPaperLinkResponse] = []
    seen_urls: set[str] = set()
    for link in links:
        label = _normalize_optional_text(link.get("label"))
        url = _normalize_optional_text(link.get("url"))
        source = _normalize_optional_text(link.get("source"))
        if label is None or url is None or source is None:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        normalized.append(
            KernelRelationPaperLinkResponse(
                label=label,
                url=url,
                source=source,
            ),
        )
    if external_ref_link is not None and external_ref_link.url not in seen_urls:
        normalized.append(external_ref_link)
    return normalized


def _merge_paper_links(
    *,
    existing: list[KernelRelationPaperLinkResponse],
    incoming: list[KernelRelationPaperLinkResponse],
) -> list[KernelRelationPaperLinkResponse]:
    merged = list(existing)
    seen_urls = {link.url for link in existing}
    for link in incoming:
        if link.url in seen_urls:
            continue
        seen_urls.add(link.url)
        merged.append(link)
    return merged


def load_relation_evidence_presentation(
    *,
    session: Session,
    relation_ids: list[UUID],
) -> dict[str, RelationEvidencePresentation]:
    """Load relation evidence details for list-response enrichment.

    The latest evidence row controls the summary and sentence fields, while
    paper links are merged across all evidence rows for the relation so list
    responses consistently surface external document references.
    """
    if not relation_ids:
        return {}
    evidence_rows = session.scalars(
        select(RelationEvidenceModel)
        .where(RelationEvidenceModel.relation_id.in_(relation_ids))
        .order_by(
            RelationEvidenceModel.relation_id,
            RelationEvidenceModel.created_at.desc(),
            RelationEvidenceModel.id.desc(),
        ),
    ).all()
    if not evidence_rows:
        return {}

    source_document_ids = {
        str(evidence.source_document_id)
        for evidence in evidence_rows
        if evidence.source_document_id is not None
    }
    source_documents_by_id: dict[str, SourceDocumentModel] = {}
    if source_document_ids:
        source_documents = session.scalars(
            select(SourceDocumentModel).where(
                SourceDocumentModel.id.in_(source_document_ids),
            ),
        ).all()
        source_documents_by_id = {
            str(document.id): document for document in source_documents
        }

    presentation_by_relation_id: dict[str, RelationEvidencePresentation] = {}
    for evidence in evidence_rows:
        relation_id = str(evidence.relation_id)
        source_document = (
            source_documents_by_id.get(str(evidence.source_document_id))
            if evidence.source_document_id is not None
            else None
        )
        paper_links = _resolve_relation_paper_links(
            source_document=source_document,
            source_document_ref=evidence.source_document_ref,
        )
        existing = presentation_by_relation_id.get(relation_id)
        if existing is None:
            presentation_by_relation_id[relation_id] = RelationEvidencePresentation(
                evidence_summary=evidence.evidence_summary,
                evidence_sentence=evidence.evidence_sentence,
                evidence_sentence_source=evidence.evidence_sentence_source,
                evidence_sentence_confidence=evidence.evidence_sentence_confidence,
                evidence_sentence_rationale=evidence.evidence_sentence_rationale,
                paper_links=paper_links,
            )
            continue
        presentation_by_relation_id[relation_id] = replace(
            existing,
            paper_links=_merge_paper_links(
                existing=existing.paper_links,
                incoming=paper_links,
            ),
        )
    return presentation_by_relation_id


__all__ = ["RelationEvidencePresentation", "load_relation_evidence_presentation"]
