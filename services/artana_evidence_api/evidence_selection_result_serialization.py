"""Result payload serializers for evidence-selection runs."""

from __future__ import annotations

from artana_evidence_api.proposal_store import HarnessProposalRecord
from artana_evidence_api.review_item_store import HarnessReviewItemRecord
from artana_evidence_api.types.common import JSONObject


def proposal_result_payload(proposal: HarnessProposalRecord) -> JSONObject:
    """Return one proposal summary for evidence-selection artifacts."""

    return {
        "proposal_id": proposal.id,
        "proposal_type": proposal.proposal_type,
        "source_key": proposal.source_key,
        "document_id": proposal.document_id,
        "title": proposal.title,
        "status": proposal.status,
        "claim_fingerprint": proposal.claim_fingerprint,
    }


def review_item_result_payload(review_item: HarnessReviewItemRecord) -> JSONObject:
    """Return one review-item summary for evidence-selection artifacts."""

    return {
        "review_item_id": review_item.id,
        "review_type": review_item.review_type,
        "source_key": review_item.source_key,
        "document_id": review_item.document_id,
        "title": review_item.title,
        "priority": review_item.priority,
        "status": review_item.status,
        "review_fingerprint": review_item.review_fingerprint,
    }


__all__ = ["proposal_result_payload", "review_item_result_payload"]
