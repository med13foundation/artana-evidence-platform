"""Result payload serializers for evidence-selection runs."""

from __future__ import annotations

from artana_evidence_api.evidence_selection.ranking.contracts import (
    CalibratedRankingProbability,
    DeterministicRankingWeight,
)
from artana_evidence_api.proposal_store import HarnessProposalRecord
from artana_evidence_api.review_item_store import HarnessReviewItemRecord
from artana_evidence_api.types.common import JSONObject


def proposal_result_payload(proposal: HarnessProposalRecord) -> JSONObject:
    """Return one proposal summary for evidence-selection artifacts."""

    payload: JSONObject = {
        "proposal_id": proposal.id,
        "proposal_type": proposal.proposal_type,
        "source_key": proposal.source_key,
        "document_id": proposal.document_id,
        "title": proposal.title,
        "status": proposal.status,
        "ranking_score": proposal.ranking_score,
        "claim_fingerprint": proposal.claim_fingerprint,
    }
    _add_governed_ranking(payload=payload, record_payload=proposal.payload)
    return payload


def review_item_result_payload(review_item: HarnessReviewItemRecord) -> JSONObject:
    """Return one review-item summary for evidence-selection artifacts."""

    payload: JSONObject = {
        "review_item_id": review_item.id,
        "review_type": review_item.review_type,
        "source_key": review_item.source_key,
        "document_id": review_item.document_id,
        "title": review_item.title,
        "priority": review_item.priority,
        "status": review_item.status,
        "ranking_score": review_item.ranking_score,
        "review_fingerprint": review_item.review_fingerprint,
    }
    _add_governed_ranking(payload=payload, record_payload=review_item.payload)
    return payload


def _add_governed_ranking(
    *,
    payload: JSONObject,
    record_payload: JSONObject,
) -> None:
    selection = record_payload.get("selection")
    if not isinstance(selection, dict):
        return
    operational = selection.get("operational_ranking")
    if operational is not None:
        payload["operational_ranking"] = DeterministicRankingWeight.model_validate(
            operational,
        ).model_dump(mode="json")
    calibrated = selection.get("calibrated_probability")
    if calibrated is not None:
        payload["calibrated_probability"] = (
            CalibratedRankingProbability.model_validate(calibrated).model_dump(
                mode="json",
            )
        )


__all__ = ["proposal_result_payload", "review_item_result_payload"]
