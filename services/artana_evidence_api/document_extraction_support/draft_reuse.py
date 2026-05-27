"""Helpers for matching newly extracted drafts to effective persisted records."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from artana_evidence_api.proposal_store import (
        HarnessProposalDraft,
        HarnessProposalRecord,
        HarnessProposalStore,
    )
    from artana_evidence_api.review_item_store import (
        HarnessReviewItemDraft,
        HarnessReviewItemRecord,
        HarnessReviewItemStore,
    )


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


def effective_proposals_for_drafts(
    *,
    space_id: UUID,
    document_id: str,
    created_proposals: list[HarnessProposalRecord],
    proposal_drafts: tuple[HarnessProposalDraft, ...],
    proposal_store: HarnessProposalStore,
) -> tuple[list[HarnessProposalRecord], int]:
    """Return proposal records corresponding to extraction drafts."""

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


def effective_review_items_for_drafts(
    *,
    space_id: UUID,
    document_id: str,
    created_review_items: list[HarnessReviewItemRecord],
    review_item_drafts: tuple[HarnessReviewItemDraft, ...],
    review_item_store: HarnessReviewItemStore,
) -> tuple[list[HarnessReviewItemRecord], int]:
    """Return review-item records corresponding to extraction drafts."""

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


__all__ = [
    "effective_proposals_for_drafts",
    "effective_review_items_for_drafts",
]
