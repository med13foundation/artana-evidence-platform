"""Proposal-draft assembly for document extraction candidates."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.document_extraction_contracts import (
    CurieSource,
    DocumentCandidateExtractionDiagnostics,
    DocumentExtractionReviewContext,
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_entities import (
    build_unresolved_entity_id,
    canonical_entity_label_rejection_reason,
    require_match_display_label,
    require_match_id,
    resolve_entity_label,
    split_compound_entity_label,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    LLM_PROPOSE_NEW_RELATION_TYPE,
    canonicalize_extraction_relation_type,
    normalize_relation_type_label,
)
from artana_evidence_api.document_extraction_review import (
    apply_document_proposal_review,
    build_document_review_context,
    build_fallback_document_review,
)
from artana_evidence_api.document_extraction_support.entity_curie_linking import (
    entity_candidate_payload_from_curie,
    normalize_entity_curie,
)
from artana_evidence_api.document_extraction_support.evidence_grounding import (
    EvidenceGroundingResult,
    ground_relation_sentence,
)
from artana_evidence_api.document_extraction_support.evidence_support_verifier import (
    TripleSupportResult,
    verify_triple_support,
)
from artana_evidence_api.document_extraction_support.relation_specificity_pruning import (
    PrunedGenericRelationCandidate,
    WeakGenericRelationCandidate,
    prune_redundant_generic_relation_candidates,
)
from artana_evidence_api.document_extraction_support.trust_ladder import (
    candidate_trust_ladder_metadata,
)
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.evidence_grade import (
    evidence_grade_for_document,
    metadata_with_evidence_grade,
)

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle

_CANDIDATE_TRUST_METADATA_KEYS = (
    "agent_extraction_completed",
    "fallback_output_used",
    "trusted_evidence_eligible",
)


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
    evidence_grade = evidence_grade_for_document(document)
    specificity_pruning = prune_redundant_generic_relation_candidates(candidates)
    pruned_candidate_by_index = {
        pruned.candidate_index: pruned
        for pruned in specificity_pruning.pruned_candidates
    }
    weak_generic_candidate_by_index = {
        weak_candidate.candidate_index: weak_candidate
        for weak_candidate in specificity_pruning.weak_generic_candidates
    }
    for index, raw_candidate in enumerate(candidates):
        weak_generic_candidate = weak_generic_candidate_by_index.get(index)
        if weak_generic_candidate is not None:
            skipped_candidates.append(
                _skipped_weak_generic_relation_candidate(
                    document=document,
                    weak_candidate=weak_generic_candidate,
                ),
            )
            continue
        pruned_candidate = pruned_candidate_by_index.get(index)
        if pruned_candidate is not None:
            skipped_candidates.append(
                _skipped_redundant_generic_relation_candidate(
                    document=document,
                    pruned_candidate=pruned_candidate,
                ),
            )
            continue
        if _is_relation_type_governance_candidate(raw_candidate):
            drafts.append(
                _relation_type_governance_draft(
                    document=document,
                    candidate=raw_candidate,
                    candidate_index=index,
                    evidence_grade=evidence_grade,
                ),
            )
            continue
        canonical_relation_type = canonicalize_extraction_relation_type(
            raw_candidate.relation_type,
        )
        if canonical_relation_type is None:
            skipped_candidates.append(
                _skipped_unknown_relation_type_candidate(
                    document=document,
                    candidate=raw_candidate,
                    candidate_index=index,
                ),
            )
            continue
        candidate = replace(raw_candidate, relation_type=canonical_relation_type)
        subject_rejection_reason = canonical_entity_label_rejection_reason(
            candidate.subject_label,
        )
        if subject_rejection_reason is not None:
            skipped_candidates.append(
                _skipped_non_canonical_candidate(
                    document=document,
                    candidate=candidate,
                    candidate_index=index,
                    reason="non_canonical_subject_label",
                    label=candidate.subject_label,
                    rejection_reason=subject_rejection_reason,
                ),
            )
            continue
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
        subject_curie_link = normalize_entity_curie(
            candidate.subject_curie,
            label=candidate.subject_label,
            source=_curie_source_for_candidate(candidate.subject_curie_source),
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
            object_rejection_reason = canonical_entity_label_rejection_reason(
                object_label,
            )
            if object_rejection_reason is not None:
                skipped_candidates.append(
                    _skipped_non_canonical_candidate(
                        document=document,
                        candidate=candidate,
                        candidate_index=index,
                        reason="non_canonical_object_label",
                        label=object_label,
                        rejection_reason=object_rejection_reason,
                        object_index=object_index,
                    ),
                )
                continue
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
            object_curie_link = normalize_entity_curie(
                candidate.object_curie if len(object_labels) == 1 else None,
                label=object_label,
                source=_curie_source_for_candidate(candidate.object_curie_source),
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
                    review_status=candidate.review_status,
                    review_reason_codes=candidate.review_reason_codes,
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
            evidence_grounding = ground_relation_sentence(
                source_text=document.text_content,
                sentence=candidate.sentence,
                subject=candidate.subject_label,
                object_=object_label,
            )
            support_verification = _verify_grounded_candidate_support(
                evidence_grounding=evidence_grounding,
                sentence=candidate.sentence,
                subject=candidate.subject_label,
                relation_type=candidate.relation_type,
                object_=object_label,
            )
            support_metadata = _support_verification_metadata(
                support_verification,
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
                    confidence=_candidate_confidence_for_support(
                        support_verification,
                    ),
                    ranking_score=_candidate_ranking_for_support(
                        support_verification,
                    ),
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
                        "proposed_subject_entity_candidate": (
                            entity_candidate_payload_from_curie(
                                label=candidate.subject_label,
                                link=subject_curie_link,
                                evidence_excerpt=candidate.sentence,
                                evidence_locator=(
                                    f"document:{document.id}:candidate:{index}:subject"
                                ),
                            )
                        ),
                        "proposed_claim_type": candidate.relation_type,
                        "proposed_object": object_id,
                        "proposed_object_label": object_label,
                        "proposed_object_entity_candidate": (
                            entity_candidate_payload_from_curie(
                                label=object_label,
                                link=object_curie_link,
                                evidence_excerpt=candidate.sentence,
                                evidence_locator=(
                                    f"document:{document.id}:candidate:{index}:object:{object_index}"
                                ),
                            )
                        ),
                        "evidence_entity_ids": [
                            entity_id
                            for entity_id in (subject_id, object_id)
                            if not entity_id.startswith("unresolved:")
                        ],
                    },
                    metadata=metadata_with_evidence_grade(
                        {
                            "document_id": document.id,
                            "document_title": document.title,
                            "document_source_type": document.source_type,
                            "subject_label": candidate.subject_label,
                            "object_label": object_label,
                            "original_object_label": candidate.object_label,
                            **_candidate_review_metadata(candidate),
                            "resolved_subject_label": resolved_subject_label,
                            "resolved_object_label": resolved_object_label,
                            "subject_resolved": subject_match is not None,
                            "object_resolved": object_match is not None,
                            "subject_curie": subject_curie_link.curie,
                            "object_curie": object_curie_link.curie,
                            "entity_linking": {
                                "subject": subject_curie_link.to_metadata(),
                                "object": object_curie_link.to_metadata(),
                            },
                            "object_split_applied": split_applied,
                            "origin": "document_extraction",
                            "evidence_grounding": evidence_grounding.to_metadata(),
                            **support_metadata,
                        },
                        evidence_grade,
                    ),
                    claim_fingerprint=claim_fingerprint,
                    evidence_grade=evidence_grade,
                ),
            )
            drafts[-1] = _apply_support_verification_floor(
                draft=apply_document_proposal_review(
                    draft=drafts[-1],
                    review=review,
                    review_context=normalized_review_context,
                ),
                support_verification=support_verification,
            )
    return tuple(drafts), skipped_candidates


def candidate_extraction_trust_metadata(
    diagnostics: DocumentCandidateExtractionDiagnostics,
) -> JSONObject:
    """Return proposal-safe trust flags from candidate extraction diagnostics."""

    diagnostics_metadata = diagnostics.as_metadata()
    return {
        key: diagnostics_metadata[key]
        for key in _CANDIDATE_TRUST_METADATA_KEYS
    }


def with_candidate_extraction_trust_metadata(
    *,
    drafts: tuple[HarnessProposalDraft, ...],
    diagnostics: DocumentCandidateExtractionDiagnostics,
) -> tuple[HarnessProposalDraft, ...]:
    """Attach candidate-extraction trust flags to proposal drafts."""

    trust_metadata = candidate_extraction_trust_metadata(diagnostics)
    return tuple(
        replace(
            draft,
            metadata={
                **draft.metadata,
                **_trust_metadata_for_candidate(
                    draft=draft,
                    trust_metadata=trust_metadata,
                ),
            },
        )
        for draft in drafts
    )


def _verify_grounded_candidate_support(
    *,
    evidence_grounding: EvidenceGroundingResult,
    sentence: str,
    subject: str,
    relation_type: str,
    object_: str,
) -> TripleSupportResult | None:
    if not evidence_grounding.grounded:
        return None
    return verify_triple_support(
        sentence=sentence,
        subject=subject,
        relation_type=relation_type,
        object_=object_,
    )


def _support_verification_metadata(
    support_verification: TripleSupportResult | None,
) -> JSONObject:
    if support_verification is None:
        return {}
    return {"support_verification": support_verification.to_metadata()}


def _candidate_confidence_for_support(
    support_verification: TripleSupportResult | None,
) -> float:
    if (
        support_verification is not None
        and support_verification.support == "CONTRADICTS"
    ):
        return 0.1
    return 0.5


def _candidate_ranking_for_support(
    support_verification: TripleSupportResult | None,
) -> float:
    if (
        support_verification is not None
        and support_verification.support == "CONTRADICTS"
    ):
        return 0.1
    return 0.5


def _apply_support_verification_floor(
    *,
    draft: HarnessProposalDraft,
    support_verification: TripleSupportResult | None,
) -> HarnessProposalDraft:
    if support_verification is None or support_verification.support != "CONTRADICTS":
        return draft
    return replace(
        draft,
        confidence=0.1,
        ranking_score=0.1,
        metadata={
            **draft.metadata,
            "support_verification": support_verification.to_metadata(),
            "support_verification_floor": "contradiction",
        },
    )


def _trust_metadata_for_candidate(
    *,
    draft: HarnessProposalDraft,
    trust_metadata: JSONObject,
) -> JSONObject:
    combined_metadata: JSONObject = {
        **draft.metadata,
        **trust_metadata,
    }
    return {
        **trust_metadata,
        **candidate_trust_ladder_metadata(
            metadata=combined_metadata,
            payload=draft.payload,
        ),
    }


def _skipped_non_canonical_candidate(
    *,
    document: HarnessDocumentRecord,
    candidate: ExtractedRelationCandidate,
    candidate_index: int,
    reason: str,
    label: str,
    rejection_reason: str,
    object_index: int | None = None,
) -> JSONObject:
    payload: JSONObject = {
        "document_id": document.id,
        "document_title": document.title,
        "candidate_index": candidate_index,
        "reason": reason,
        "label": label,
        "label_rejection_reason": rejection_reason,
        "subject_label": candidate.subject_label,
        "object_label": candidate.object_label,
        "relation_type": candidate.relation_type,
        "sentence": candidate.sentence,
    }
    if object_index is not None:
        payload["object_index"] = object_index
    return payload


def _skipped_unknown_relation_type_candidate(
    *,
    document: HarnessDocumentRecord,
    candidate: ExtractedRelationCandidate,
    candidate_index: int,
) -> JSONObject:
    return {
        "document_id": document.id,
        "document_title": document.title,
        "candidate_index": candidate_index,
        "reason": "unknown_relation_type",
        "relation_type": candidate.relation_type,
        "subject_label": candidate.subject_label,
        "object_label": candidate.object_label,
        "sentence": candidate.sentence,
    }


def _curie_source_for_candidate(source: CurieSource) -> CurieSource:
    if source == "none":
        return "model"
    return source


def _candidate_review_metadata(candidate: ExtractedRelationCandidate) -> JSONObject:
    return {
        "review_status": candidate.review_status,
        "review_reason_codes": list(candidate.review_reason_codes),
    }


def _is_relation_type_governance_candidate(
    candidate: ExtractedRelationCandidate,
) -> bool:
    return (
        candidate.relation_governance_status == "requires_relation_review"
        and normalize_relation_type_label(candidate.relation_type)
        == LLM_PROPOSE_NEW_RELATION_TYPE
        and candidate.proposed_relation_type is not None
        and candidate.proposed_relation_type.strip() != ""
    )


def _relation_type_governance_draft(
    *,
    document: HarnessDocumentRecord,
    candidate: ExtractedRelationCandidate,
    candidate_index: int,
    evidence_grade: str | None,
) -> HarnessProposalDraft:
    proposed_relation_type = normalize_relation_type_label(
        candidate.proposed_relation_type or "",
    )
    rationale = (
        candidate.new_relation_type_rationale
        or "The extracted relation type is not in the governed dictionary."
    )
    metadata = metadata_with_evidence_grade(
        {
            "document_id": document.id,
            "document_title": document.title,
            "document_source_type": document.source_type,
            "origin": "document_extraction",
            "relation_governance_status": candidate.relation_governance_status,
            "trusted_evidence_eligible": False,
            "subject_label": candidate.subject_label,
            "object_label": candidate.object_label,
            "proposed_relation_type": proposed_relation_type,
        },
        evidence_grade,
    )
    return HarnessProposalDraft(
        proposal_type="relation_type_candidate",
        source_kind="document_extraction",
        source_key=f"{document.id}:{candidate_index}:relation_type",
        document_id=document.id,
        title=f"Review relation type: {proposed_relation_type}",
        summary=rationale,
        confidence=0.0,
        ranking_score=0.0,
        reasoning_path={
            "document_id": document.id,
            "document_title": document.title,
            "sentence": candidate.sentence,
            "subject_label": candidate.subject_label,
            "object_label": candidate.object_label,
            "proposed_relation_type": proposed_relation_type,
            "new_relation_type_rationale": rationale,
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
            "proposed_relation_type": proposed_relation_type,
            "new_relation_type_rationale": rationale,
            "source_relation_type": candidate.relation_type,
            "subject_label": candidate.subject_label,
            "object_label": candidate.object_label,
            "evidence_sentence": candidate.sentence,
            "trusted_evidence_eligible": False,
        },
        metadata=metadata,
        evidence_grade=evidence_grade,
    )


def _skipped_redundant_generic_relation_candidate(
    *,
    document: HarnessDocumentRecord,
    pruned_candidate: PrunedGenericRelationCandidate,
) -> JSONObject:
    candidate = pruned_candidate.candidate
    return {
        "document_id": document.id,
        "document_title": document.title,
        "candidate_index": pruned_candidate.candidate_index,
        "reason": "redundant_generic_relation_sibling",
        "relation_type": candidate.relation_type,
        "suppressing_relation_type": pruned_candidate.suppressing_relation_type,
        "subject_label": candidate.subject_label,
        "object_label": candidate.object_label,
        "sentence": candidate.sentence,
    }


def _skipped_weak_generic_relation_candidate(
    *,
    document: HarnessDocumentRecord,
    weak_candidate: WeakGenericRelationCandidate,
) -> JSONObject:
    candidate = weak_candidate.candidate
    return {
        "document_id": document.id,
        "document_title": document.title,
        "candidate_index": weak_candidate.candidate_index,
        "reason": "weak_generic_relation",
        "relation_type": candidate.relation_type,
        "subject_label": candidate.subject_label,
        "object_label": candidate.object_label,
        "sentence": candidate.sentence,
    }


__all__ = [
    "build_document_extraction_drafts",
    "candidate_extraction_trust_metadata",
    "with_candidate_extraction_trust_metadata",
]
