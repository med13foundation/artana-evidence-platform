"""Opaque reference construction and strict mapping for proposal reviews."""

from __future__ import annotations

import hashlib
import json

from artana_evidence_api.document_extraction_contracts import (
    DocumentProposalReview,
    ProposalReviewResultLike,
)
from artana_evidence_api.proposal_store import HarnessProposalDraft

_DRAFT_REF_PREFIX = "draft_"


def build_proposal_review_draft_refs(
    *,
    document_sha256: str,
    drafts: tuple[HarnessProposalDraft, ...],
) -> tuple[str, ...]:
    """Return stable opaque references that remain unique for duplicate drafts."""

    references: list[str] = []
    for position, draft in enumerate(drafts):
        payload = "\x1f".join(
            (
                document_sha256,
                draft.source_key,
                draft.claim_fingerprint or "",
                draft.title,
                draft.summary,
                json.dumps(draft.payload, sort_keys=True, separators=(",", ":")),
                str(position),
            ),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        references.append(f"{_DRAFT_REF_PREFIX}{digest}")
    return tuple(references)


def map_proposal_reviews_by_ref(
    *,
    result: ProposalReviewResultLike,
    expected_refs: tuple[str, ...],
    model_id: str,
) -> dict[str, DocumentProposalReview]:
    """Validate exact coverage before attaching any model review to a draft."""

    returned_refs = [item.draft_ref for item in result.reviews]
    if len(returned_refs) != len(expected_refs):
        raise ValueError("proposal review must cover every draft exactly once")
    if len(set(returned_refs)) != len(returned_refs):
        raise ValueError("proposal review contains duplicate draft references")
    if set(returned_refs) != set(expected_refs):
        raise ValueError("proposal review contains missing or unknown draft references")

    return {
        item.draft_ref: DocumentProposalReview(
            factual_support=item.factual_support,
            goal_relevance=item.goal_relevance,
            priority=item.priority,
            rationale=item.rationale.strip(),
            factual_rationale=item.factual_rationale.strip(),
            relevance_rationale=item.relevance_rationale.strip(),
            method="llm_judge_v1",
            model_id=model_id,
        )
        for item in result.reviews
    }


__all__ = ["build_proposal_review_draft_refs", "map_proposal_reviews_by_ref"]
