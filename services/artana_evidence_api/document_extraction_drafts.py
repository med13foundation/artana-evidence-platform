"""Proposal-draft assembly for document extraction candidates."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.document_extraction_contracts import (
    DocumentExtractionReviewContext,
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_entities import (
    build_unresolved_entity_id,
    require_match_display_label,
    require_match_id,
    resolve_entity_label,
    split_compound_entity_label,
)
from artana_evidence_api.document_extraction_review import (
    apply_document_proposal_review,
    build_document_review_context,
    build_fallback_document_review,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle


def build_document_extraction_drafts(
    *,
    space_id: UUID,
    document: HarnessDocumentRecord,
    candidates: list[ExtractedRelationCandidate],
    graph_api_gateway: GraphTransportBundle,
    review_context: DocumentExtractionReviewContext | None = None,
    ai_resolved_entities: dict[str, JSONObject] | None = None,
) -> tuple[tuple[HarnessProposalDraft, ...], list[JSONObject]]:
    """Resolve extracted document relations into staged harness proposals."""

    drafts: list[HarnessProposalDraft] = []
    skipped_candidates: list[JSONObject] = []
    normalized_review_context = review_context or build_document_review_context()
    for index, candidate in enumerate(candidates):
        subject_match = resolve_entity_label(
            space_id=space_id,
            label=candidate.subject_label,
            graph_api_gateway=graph_api_gateway,
            ai_resolved_entities=ai_resolved_entities,
        )
        subject_id = (
            require_match_id(subject_match)
            if subject_match is not None
            else build_unresolved_entity_id(candidate.subject_label)
        )
        resolved_subject_label = (
            candidate.subject_label
            if subject_match is None
            else require_match_display_label(subject_match)
        )
        object_labels = split_compound_entity_label(
            space_id=space_id,
            label=candidate.object_label,
            graph_api_gateway=graph_api_gateway,
        )
        for object_index, object_label in enumerate(object_labels):
            object_match = resolve_entity_label(
                space_id=space_id,
                label=object_label,
                graph_api_gateway=graph_api_gateway,
                ai_resolved_entities=ai_resolved_entities,
            )
            object_id = (
                require_match_id(object_match)
                if object_match is not None
                else build_unresolved_entity_id(object_label)
            )
            resolved_object_label = (
                object_label
                if object_match is None
                else require_match_display_label(object_match)
            )
            review = build_fallback_document_review(
                candidate=ExtractedRelationCandidate(
                    subject_label=candidate.subject_label,
                    relation_type=candidate.relation_type,
                    object_label=object_label,
                    sentence=candidate.sentence,
                ),
                review_context=normalized_review_context,
            )
            split_applied = len(object_labels) > 1
            source_key = (
                f"{document.id}:{index}"
                if not split_applied
                else f"{document.id}:{index}:{object_index}"
            )
            claim_fingerprint = compute_claim_fingerprint(
                resolved_subject_label,
                candidate.relation_type,
                resolved_object_label,
            )
            drafts.append(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="document_extraction",
                    source_key=source_key,
                    document_id=document.id,
                    title=(
                        f"Extracted claim: {resolved_subject_label} "
                        f"{candidate.relation_type} {resolved_object_label}"
                    ),
                    summary=candidate.sentence,
                    confidence=0.5,
                    ranking_score=0.5,
                    reasoning_path={
                        "document_id": document.id,
                        "document_title": document.title,
                        "sentence": candidate.sentence,
                        "resolution_method": (
                            "graph_entity_search"
                            if subject_match is not None and object_match is not None
                            else "deferred_entity_resolution"
                        ),
                        "subject_label": candidate.subject_label,
                        "object_label": object_label,
                        "original_object_label": candidate.object_label,
                    },
                    evidence_bundle=[
                        {
                            "source_type": "paper",
                            "locator": f"document:{document.id}",
                            "excerpt": candidate.sentence,
                            "relevance": 0.5,
                        },
                    ],
                    payload={
                        "proposed_subject": subject_id,
                        "proposed_subject_label": candidate.subject_label,
                        "proposed_claim_type": candidate.relation_type,
                        "proposed_object": object_id,
                        "proposed_object_label": object_label,
                        "evidence_entity_ids": [
                            entity_id
                            for entity_id in (subject_id, object_id)
                            if not entity_id.startswith("unresolved:")
                        ],
                    },
                    metadata={
                        "document_id": document.id,
                        "document_title": document.title,
                        "document_source_type": document.source_type,
                        "subject_label": candidate.subject_label,
                        "object_label": object_label,
                        "original_object_label": candidate.object_label,
                        "resolved_subject_label": resolved_subject_label,
                        "resolved_object_label": resolved_object_label,
                        "subject_resolved": subject_match is not None,
                        "object_resolved": object_match is not None,
                        "object_split_applied": split_applied,
                        "origin": "document_extraction",
                    },
                    claim_fingerprint=claim_fingerprint,
                ),
            )
            drafts[-1] = apply_document_proposal_review(
                draft=drafts[-1],
                review=review,
                review_context=normalized_review_context,
            )
    return tuple(drafts), skipped_candidates


__all__ = ["build_document_extraction_drafts"]
