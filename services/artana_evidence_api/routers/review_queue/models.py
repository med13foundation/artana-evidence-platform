"""Serialized shapes for the unified review queue.

Queue ids are stable wrappers over three disjoint backing families -- staged
proposals, review-only items, and run approvals -- so that one surface can
present them as a single list.
"""

from __future__ import annotations

from typing import Literal

from artana_evidence_api.approval_store import HarnessApprovalRecord  # noqa: TC001
from artana_evidence_api.proposal_store import HarnessProposalRecord  # noqa: TC001
from artana_evidence_api.review_item_store import (
    HarnessReviewItemRecord,  # noqa: TC001
)
from artana_evidence_api.types.common import (  # noqa: TC001
    JSONObject,
    serialize_optional_timestamp,
    serialize_timestamp,
)
from artana_evidence_api.types.review_actor import ReviewActor
from artana_evidence_api.types.source_provenance import ClaimSourceProvenance
from pydantic import BaseModel, ConfigDict, Field

_RISK_PRIORITY = {"low": "low", "medium": "medium", "high": "high", "critical": "high"}
_MAX_BULK_DECISIONS = 1000


def review_queue_item_id_for_proposal(proposal_id: str) -> str:
    """Return the stable queue id for one proposal-backed review item."""
    return f"proposal:{proposal_id}"


def review_queue_item_id_for_review_item(review_item_id: str) -> str:
    """Return the stable queue id for one review-item-backed entry."""
    return f"review_item:{review_item_id}"


def review_queue_item_id_for_approval(*, run_id: str, approval_key: str) -> str:
    """Return the stable queue id for one approval-backed entry."""
    return f"approval:{run_id}:{approval_key}"


class HarnessReviewQueueItemResponse(BaseModel):
    """Serialized queue item for the unified review surface."""

    model_config = ConfigDict(strict=True)

    id: str
    item_type: str
    resource_id: str
    kind: str
    status: str
    title: str
    summary: str
    priority: str
    confidence: float | None
    ranking_score: float | None
    run_id: str | None
    document_id: str | None
    source_family: str
    source_kind: str
    source_key: str
    linked_resource: JSONObject | None
    available_actions: list[str]
    payload: JSONObject
    metadata: JSONObject
    evidence_grade: str | None
    evidence_bundle: list[JSONObject]
    source_provenance: ClaimSourceProvenance | None
    decision_reason: str | None
    decided_at: str | None
    decided_by: ReviewActor | None
    created_at: str
    updated_at: str

    @classmethod
    def from_proposal(
        cls,
        proposal: HarnessProposalRecord,
    ) -> HarnessReviewQueueItemResponse:
        return cls(
            id=review_queue_item_id_for_proposal(proposal.id),
            item_type="proposal",
            resource_id=proposal.id,
            kind=proposal.proposal_type,
            status=proposal.status,
            title=proposal.title,
            summary=proposal.summary,
            priority="medium",
            confidence=proposal.confidence,
            ranking_score=proposal.ranking_score,
            run_id=proposal.run_id,
            document_id=proposal.document_id,
            source_family=proposal.source_kind,
            source_kind=proposal.source_kind,
            source_key=proposal.source_key,
            linked_resource={"proposal_id": proposal.id},
            available_actions=(
                ["promote", "reject"] if proposal.status == "pending_review" else []
            ),
            payload=proposal.payload,
            metadata=proposal.metadata,
            evidence_grade=proposal.evidence_grade,
            evidence_bundle=proposal.evidence_bundle,
            source_provenance=proposal.source_provenance,
            decision_reason=proposal.decision_reason,
            decided_at=serialize_optional_timestamp(proposal.decided_at),
            decided_by=proposal.decided_by,
            created_at=serialize_timestamp(proposal.created_at),
            updated_at=serialize_timestamp(proposal.updated_at),
        )

    @classmethod
    def from_review_item(
        cls,
        review_item: HarnessReviewItemRecord,
    ) -> HarnessReviewQueueItemResponse:
        return cls(
            id=review_queue_item_id_for_review_item(review_item.id),
            item_type="review_item",
            resource_id=review_item.id,
            kind=review_item.review_type,
            status=review_item.status,
            title=review_item.title,
            summary=review_item.summary,
            priority=review_item.priority,
            confidence=review_item.confidence,
            ranking_score=review_item.ranking_score,
            run_id=review_item.run_id,
            document_id=review_item.document_id,
            source_family=review_item.source_family,
            source_kind=review_item.source_kind,
            source_key=review_item.source_key,
            linked_resource=_linked_resource_for_review_item(review_item),
            available_actions=_review_item_available_actions(review_item),
            payload=review_item.payload,
            metadata=review_item.metadata,
            evidence_grade=review_item.evidence_grade,
            evidence_bundle=review_item.evidence_bundle,
            source_provenance=None,
            decision_reason=review_item.decision_reason,
            decided_at=serialize_optional_timestamp(review_item.decided_at),
            decided_by=review_item.decided_by,
            created_at=serialize_timestamp(review_item.created_at),
            updated_at=serialize_timestamp(review_item.updated_at),
        )

    @classmethod
    def from_approval(
        cls,
        approval: HarnessApprovalRecord,
    ) -> HarnessReviewQueueItemResponse:
        metadata_summary = approval.metadata.get("summary")
        summary = (
            metadata_summary
            if isinstance(metadata_summary, str) and metadata_summary.strip() != ""
            else approval.title
        )
        priority = _RISK_PRIORITY.get(approval.risk_level.strip().lower(), "medium")
        decided_at = None
        if approval.status != "pending":
            decided_at = serialize_timestamp(approval.updated_at)
        return cls(
            id=review_queue_item_id_for_approval(
                run_id=approval.run_id,
                approval_key=approval.approval_key,
            ),
            item_type="approval",
            resource_id=approval.approval_key,
            kind=approval.target_type,
            status=approval.status,
            title=approval.title,
            summary=summary,
            priority=priority,
            confidence=None,
            ranking_score=None,
            run_id=approval.run_id,
            document_id=None,
            source_family="run_approval",
            source_kind="run_approval",
            source_key=approval.approval_key,
            linked_resource={
                "run_id": approval.run_id,
                "approval_key": approval.approval_key,
            },
            available_actions=(
                ["approve", "reject"] if approval.status == "pending" else []
            ),
            payload={
                "target_type": approval.target_type,
                "target_id": approval.target_id,
                "risk_level": approval.risk_level,
            },
            metadata=approval.metadata,
            evidence_grade=None,
            evidence_bundle=[],
            source_provenance=None,
            decision_reason=approval.decision_reason,
            decided_at=decided_at,
            decided_by=approval.decided_by,
            created_at=serialize_timestamp(approval.created_at),
            updated_at=serialize_timestamp(approval.updated_at),
        )


class HarnessReviewQueueListResponse(BaseModel):
    """List response for the unified review queue."""

    model_config = ConfigDict(strict=True)

    items: list[HarnessReviewQueueItemResponse]
    total: int
    offset: int
    limit: int


class HarnessReviewQueueActionRequest(BaseModel):
    """Apply one action to a review-queue item."""

    model_config = ConfigDict(strict=True)

    action: str = Field(..., min_length=1, max_length=64)
    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: JSONObject = Field(default_factory=dict)


class HarnessReviewQueueBulkDecisionItem(BaseModel):
    """One review-queue action inside a bulk decision request."""

    model_config = ConfigDict(strict=True)

    item_id: str = Field(..., min_length=1, max_length=256)
    action: str = Field(..., min_length=1, max_length=64)
    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    metadata: JSONObject = Field(default_factory=dict)


class HarnessReviewQueueBulkDecisionRequest(BaseModel):
    """Apply many review-queue decisions in one request."""

    model_config = ConfigDict(strict=True)

    decisions: list[HarnessReviewQueueBulkDecisionItem] = Field(
        ...,
        min_length=1,
        max_length=_MAX_BULK_DECISIONS,
    )


class HarnessReviewQueueBulkDecisionResult(BaseModel):
    """Per-item outcome for a bulk review-queue decision request."""

    model_config = ConfigDict(strict=True)

    item_id: str
    status: Literal["accepted", "failed"]
    new_state: str | None = None
    error: str | None = None


class HarnessReviewQueueBulkDecisionSummary(BaseModel):
    """Aggregate outcome counters for a bulk review-queue decision request."""

    model_config = ConfigDict(strict=True)

    accepted: int
    failed: int


class HarnessReviewQueueBulkDecisionResponse(BaseModel):
    """Bulk decision response for high-volume review cleanup."""

    model_config = ConfigDict(strict=True)

    results: list[HarnessReviewQueueBulkDecisionResult]
    summary: HarnessReviewQueueBulkDecisionSummary


def _linked_resource_for_review_item(
    review_item: HarnessReviewItemRecord,
) -> JSONObject | None:
    linked_resource: JSONObject = {}
    if review_item.linked_proposal_id is not None:
        linked_resource["proposal_id"] = review_item.linked_proposal_id
    if review_item.linked_approval_key is not None:
        linked_resource["approval_key"] = review_item.linked_approval_key
    return linked_resource or None


def _review_item_can_convert_to_proposal(
    review_item: HarnessReviewItemRecord,
) -> bool:
    proposal_payload = review_item.payload.get("proposal_draft")
    return isinstance(proposal_payload, dict) and bool(proposal_payload)


def _review_item_available_actions(
    review_item: HarnessReviewItemRecord,
) -> list[str]:
    if review_item.status != "pending_review":
        return []
    actions = ["dismiss", "mark_resolved"]
    if _review_item_can_convert_to_proposal(review_item):
        actions.insert(0, "convert_to_proposal")
    return actions



__all__ = [
    "HarnessReviewQueueActionRequest",
    "HarnessReviewQueueBulkDecisionItem",
    "HarnessReviewQueueBulkDecisionRequest",
    "HarnessReviewQueueBulkDecisionResponse",
    "HarnessReviewQueueBulkDecisionResult",
    "HarnessReviewQueueBulkDecisionSummary",
    "HarnessReviewQueueItemResponse",
    "HarnessReviewQueueListResponse",
    "review_queue_item_id_for_approval",
    "review_queue_item_id_for_proposal",
    "review_queue_item_id_for_review_item",
]
