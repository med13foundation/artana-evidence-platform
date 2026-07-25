"""Turning a review-only item into a staged proposal, and recording that it happened.

A review item carries a `proposal_draft` template describing the proposal it
would become.  Converting is the one queue action that creates new state rather
than closing existing state, so it lives apart from the routing layer.
"""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,  # noqa: TC001
    HarnessProposalStore,  # noqa: TC001
)
from artana_evidence_api.review_item_store import (
    HarnessReviewItemRecord,  # noqa: TC001
    HarnessReviewItemStore,  # noqa: TC001
)
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from artana_evidence_api.types.review_actor import ReviewActor  # noqa: TC001
from fastapi import HTTPException, status

from .models import HarnessReviewQueueItemResponse


def _json_object_or_none(value: object) -> JSONObject | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _json_object_list_or_none(value: object) -> list[JSONObject] | None:
    if not isinstance(value, list):
        return None
    items: list[JSONObject] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        items.append({str(key): nested for key, nested in item.items()})
    return items


def _text_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _proposal_draft_from_review_item(
    review_item: HarnessReviewItemRecord,
) -> HarnessProposalDraft:
    raw_proposal_draft = _json_object_or_none(review_item.payload.get("proposal_draft"))
    if raw_proposal_draft is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Review item '{review_item.id}' cannot be converted into a proposal "
                "because it does not carry a proposal template yet"
            ),
        )

    proposal_type = _text_or_none(raw_proposal_draft.get("proposal_type"))
    if proposal_type is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Review item '{review_item.id}' is missing 'proposal_type' in its "
                "proposal template"
            ),
        )
    payload = _json_object_or_none(raw_proposal_draft.get("payload"))
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Review item '{review_item.id}' is missing proposal payload data "
                "for conversion"
            ),
        )

    title = _text_or_none(raw_proposal_draft.get("title")) or review_item.title
    summary = _text_or_none(raw_proposal_draft.get("summary")) or review_item.summary
    confidence_override = _float_or_none(raw_proposal_draft.get("confidence"))
    ranking_override = _float_or_none(raw_proposal_draft.get("ranking_score"))
    confidence = (
        confidence_override
        if confidence_override is not None
        else review_item.confidence
    )
    ranking_score = (
        ranking_override if ranking_override is not None else review_item.ranking_score
    )
    reasoning_path = _json_object_or_none(raw_proposal_draft.get("reasoning_path")) or {
        "kind": "review_item_conversion",
        "review_item_id": review_item.id,
        "review_type": review_item.review_type,
    }
    evidence_bundle = (
        _json_object_list_or_none(raw_proposal_draft.get("evidence_bundle"))
        or review_item.evidence_bundle
    )
    proposal_metadata = _json_object_or_none(raw_proposal_draft.get("metadata")) or {}
    return HarnessProposalDraft(
        proposal_type=proposal_type,
        source_kind=(
            _text_or_none(raw_proposal_draft.get("source_kind"))
            or review_item.source_kind
        ),
        source_key=(
            _text_or_none(raw_proposal_draft.get("source_key"))
            or f"{review_item.source_key}:proposal"
        ),
        document_id=(
            _text_or_none(raw_proposal_draft.get("document_id"))
            or review_item.document_id
        ),
        title=title,
        summary=summary,
        confidence=confidence,
        ranking_score=ranking_score,
        reasoning_path=reasoning_path,
        evidence_bundle=evidence_bundle,
        payload=payload,
        metadata={
            **review_item.metadata,
            **proposal_metadata,
            "review_item_id": review_item.id,
            "source_review_type": review_item.review_type,
            "source_family": review_item.source_family,
        },
        claim_fingerprint=_text_or_none(raw_proposal_draft.get("claim_fingerprint")),
        evidence_grade=(
            _text_or_none(raw_proposal_draft.get("evidence_grade"))
            or review_item.evidence_grade
        ),
    )


def _find_existing_proposal_by_fingerprint(
    *,
    space_id: UUID,
    claim_fingerprint: str,
    proposal_store: HarnessProposalStore,
) -> HarnessProposalRecord | None:
    proposals = proposal_store.list_proposals(space_id=space_id)
    preferred_match = next(
        (
            proposal
            for proposal in proposals
            if proposal.claim_fingerprint == claim_fingerprint
            and proposal.status in {"pending_review", "promoted"}
        ),
        None,
    )
    if preferred_match is not None:
        return preferred_match
    return next(
        (
            proposal
            for proposal in proposals
            if proposal.claim_fingerprint == claim_fingerprint
        ),
        None,
    )


def convert_review_item_to_proposal(
    *,
    space_id: UUID,
    review_item_id: str,
    review_item_store: HarnessReviewItemStore,
    proposal_store: HarnessProposalStore,
    reason: str | None,
    decided_by: ReviewActor | None,
    metadata: JSONObject,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessReviewQueueItemResponse:
    review_item = review_item_store.get_review_item(
        space_id=space_id,
        review_item_id=review_item_id,
    )
    if review_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item 'review_item:{review_item_id}' was not found",
        )
    if review_item.status != "pending_review":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Review item '{review_item.id}' is already decided with status "
                f"'{review_item.status}'"
            ),
        )

    proposal_draft = _proposal_draft_from_review_item(review_item)
    try:
        created_proposals = proposal_store.create_proposals(
            space_id=space_id,
            run_id=review_item.run_id,
            proposals=(proposal_draft,),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    proposal = created_proposals[0] if created_proposals else None
    if proposal is None and proposal_draft.claim_fingerprint is not None:
        proposal = _find_existing_proposal_by_fingerprint(
            space_id=space_id,
            claim_fingerprint=proposal_draft.claim_fingerprint,
            proposal_store=proposal_store,
        )
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Review item '{review_item.id}' did not create a new proposal and no "
                "existing matching proposal could be found"
            ),
        )

    try:
        updated_review_item = review_item_store.decide_review_item(
            space_id=space_id,
            review_item_id=review_item_id,
            status="resolved",
            decision_reason=reason or "Converted to proposal",
            decided_by=decided_by,
            metadata={
                **metadata,
                "converted_to_proposal": True,
                "linked_proposal_id": proposal.id,
            },
            linked_proposal_id=proposal.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_409_CONFLICT
                if "already decided" in str(exc)
                else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        ) from exc
    if updated_review_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item 'review_item:{review_item_id}' was not found",
        )

    record_review_item_decision(
        space_id=space_id,
        review_item=updated_review_item,
        action="convert_to_proposal",
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    return HarnessReviewQueueItemResponse.from_proposal(proposal)


def record_review_item_decision(
    *,
    space_id: UUID,
    review_item: HarnessReviewItemRecord,
    action: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> None:
    run = run_registry.get_run(space_id=space_id, run_id=review_item.run_id)
    if run is None:
        return
    run_registry.record_event(
        space_id=space_id,
        run_id=review_item.run_id,
        event_type="run.review_item_decided",
        message=f"Review item '{review_item.id}' marked {review_item.status}.",
        payload={
            "review_item_id": review_item.id,
            "review_type": review_item.review_type,
            "decision": review_item.status,
            "action": action,
            "linked_proposal_id": review_item.linked_proposal_id,
            "linked_approval_key": review_item.linked_approval_key,
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=review_item.run_id,
        patch={
            "last_review_item_id": review_item.id,
            "last_review_item_action": action,
            "last_review_item_status": review_item.status,
            "last_review_item_linked_proposal_id": review_item.linked_proposal_id,
        },
    )


__all__ = [
    "convert_review_item_to_proposal",
    "record_review_item_decision",
]
