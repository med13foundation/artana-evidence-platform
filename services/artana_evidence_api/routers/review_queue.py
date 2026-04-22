"""Unified review-queue endpoints for proposals, review items, and approvals."""

from __future__ import annotations

from datetime import UTC
from uuid import UUID  # noqa: TC003

from artana_evidence_api.approval_store import (
    HarnessApprovalRecord,
    HarnessApprovalStore,
)
from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_proposal_store,
    get_review_item_store,
    get_run_registry,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.graph_client import GraphTransportBundle  # noqa: TC001
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.review_item_store import (
    HarnessReviewItemRecord,
    HarnessReviewItemStore,
)
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from .approvals import (
    HarnessApprovalDecisionRequest,
)
from .approvals import (
    decide_approval as decide_run_approval,
)
from .proposals import (
    HarnessProposalDecisionRequest,
    promote_proposal,
    reject_proposal,
)

router = APIRouter(
    prefix="/v1/spaces",
    tags=["review-queue"],
    dependencies=[Depends(require_harness_space_read_access)],
)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_REVIEW_ITEM_STORE_DEPENDENCY = Depends(get_review_item_store)
_APPROVAL_STORE_DEPENDENCY = Depends(get_approval_store)
_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_GRAPH_API_GATEWAY_DEPENDENCY = Depends(get_graph_api_gateway)
_HARNESS_EXECUTION_SERVICES_DEPENDENCY = Depends(get_harness_execution_services)
_ITEM_TYPE_QUERY = Query(default=None, min_length=1, max_length=32)
_KIND_QUERY = Query(default=None, min_length=1, max_length=64)
_STATUS_QUERY = Query(default=None, min_length=1, max_length=32)
_RUN_ID_QUERY = Query(default=None)
_DOCUMENT_ID_QUERY = Query(default=None)
_SOURCE_FAMILY_QUERY = Query(default=None, min_length=1, max_length=64)
_OFFSET_QUERY = Query(default=0, ge=0)
_LIMIT_QUERY = Query(default=200, ge=1, le=1000)

_PENDING_QUEUE_STATUSES = frozenset({"pending_review", "pending"})
_RISK_PRIORITY = {"low": "low", "medium": "medium", "high": "high", "critical": "high"}
_PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
_ITEM_TYPE_VALUES = frozenset({"proposal", "review_item", "approval"})


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
    evidence_bundle: list[JSONObject]
    decision_reason: str | None
    decided_at: str | None
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
            evidence_bundle=proposal.evidence_bundle,
            decision_reason=proposal.decision_reason,
            decided_at=(
                proposal.decided_at.isoformat()
                if proposal.decided_at is not None
                else None
            ),
            created_at=proposal.created_at.isoformat(),
            updated_at=proposal.updated_at.isoformat(),
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
            evidence_bundle=review_item.evidence_bundle,
            decision_reason=review_item.decision_reason,
            decided_at=(
                review_item.decided_at.isoformat()
                if review_item.decided_at is not None
                else None
            ),
            created_at=review_item.created_at.isoformat(),
            updated_at=review_item.updated_at.isoformat(),
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
            decided_at = approval.updated_at.replace(tzinfo=UTC).isoformat()
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
            evidence_bundle=[],
            decision_reason=approval.decision_reason,
            decided_at=decided_at,
            created_at=approval.created_at.replace(tzinfo=UTC).isoformat(),
            updated_at=approval.updated_at.replace(tzinfo=UTC).isoformat(),
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


def _convert_review_item_to_proposal(
    *,
    space_id: UUID,
    review_item_id: str,
    review_item_store: HarnessReviewItemStore,
    proposal_store: HarnessProposalStore,
    reason: str | None,
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
    created_proposals = proposal_store.create_proposals(
        space_id=space_id,
        run_id=review_item.run_id,
        proposals=(proposal_draft,),
    )
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

    _record_review_item_decision(
        space_id=space_id,
        review_item=updated_review_item,
        action="convert_to_proposal",
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    return HarnessReviewQueueItemResponse.from_proposal(proposal)


def _queue_sort_key(item: HarnessReviewQueueItemResponse) -> tuple[float, int, str]:
    ranking = item.ranking_score if item.ranking_score is not None else 0.0
    priority_weight = _PRIORITY_WEIGHT.get(item.priority, 1)
    return (ranking, priority_weight, item.updated_at)


def _parse_item_type(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if normalized not in _ITEM_TYPE_VALUES:
        msg = f"Unsupported review queue item_type '{raw_value}'"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return normalized


def _split_review_queue_item_id(item_id: str) -> tuple[str, str]:
    normalized = item_id.strip()
    if normalized.startswith("proposal:"):
        return "proposal", normalized.removeprefix("proposal:")
    if normalized.startswith("review_item:"):
        return "review_item", normalized.removeprefix("review_item:")
    if normalized.startswith("approval:"):
        payload = normalized.removeprefix("approval:")
        run_id, separator, approval_key = payload.partition(":")
        if separator and run_id and approval_key:
            return "approval", payload
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Review queue item '{item_id}' was not found",
    )


def _build_queue_items(
    *,
    space_id: UUID,
    proposal_store: HarnessProposalStore,
    review_item_store: HarnessReviewItemStore,
    approval_store: HarnessApprovalStore,
    status_filter: str | None,
    item_type: str | None,
    kind: str | None,
    source_family: str | None,
    run_id: UUID | None,
    document_id: UUID | None,
) -> list[HarnessReviewQueueItemResponse]:
    items: list[HarnessReviewQueueItemResponse] = []
    normalized_kind = kind.strip() if isinstance(kind, str) else None
    proposal_status = status_filter if status_filter is not None else "pending_review"
    review_item_status = (
        status_filter if status_filter is not None else "pending_review"
    )
    approval_status = status_filter if status_filter is not None else "pending"

    if item_type in {None, "proposal"}:
        items.extend(
            HarnessReviewQueueItemResponse.from_proposal(proposal)
            for proposal in proposal_store.list_proposals(
                space_id=space_id,
                status=proposal_status,
                proposal_type=normalized_kind if item_type == "proposal" else None,
                run_id=run_id,
                document_id=document_id,
            )
            if normalized_kind is None or proposal.proposal_type == normalized_kind
        )
    if item_type in {None, "review_item"}:
        items.extend(
            HarnessReviewQueueItemResponse.from_review_item(review_item)
            for review_item in review_item_store.list_review_items(
                space_id=space_id,
                status=review_item_status,
                review_type=normalized_kind if item_type == "review_item" else None,
                source_family=source_family,
                run_id=run_id,
                document_id=document_id,
            )
            if normalized_kind is None or review_item.review_type == normalized_kind
        )
    if item_type in {None, "approval"} and document_id is None:
        items.extend(
            HarnessReviewQueueItemResponse.from_approval(approval)
            for approval in approval_store.list_space_approvals(
                space_id=space_id,
                status=approval_status,
                run_id=run_id,
            )
            if normalized_kind is None or approval.target_type == normalized_kind
        )
    filtered_items = [
        item
        for item in items
        if source_family is None or item.source_family == source_family
    ]
    return sorted(filtered_items, key=_queue_sort_key, reverse=True)


def _resolve_review_queue_item(
    *,
    space_id: UUID,
    item_id: str,
    proposal_store: HarnessProposalStore,
    review_item_store: HarnessReviewItemStore,
    approval_store: HarnessApprovalStore,
) -> HarnessReviewQueueItemResponse:
    item_type, resource_key = _split_review_queue_item_id(item_id)
    if item_type == "proposal":
        proposal = proposal_store.get_proposal(
            space_id=space_id,
            proposal_id=resource_key,
        )
        if proposal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review queue item '{item_id}' was not found",
            )
        return HarnessReviewQueueItemResponse.from_proposal(proposal)
    if item_type == "review_item":
        review_item = review_item_store.get_review_item(
            space_id=space_id,
            review_item_id=resource_key,
        )
        if review_item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review queue item '{item_id}' was not found",
            )
        return HarnessReviewQueueItemResponse.from_review_item(review_item)
    run_id, _, approval_key = resource_key.partition(":")
    approvals = approval_store.list_approvals(space_id=space_id, run_id=run_id)
    approval = next(
        (record for record in approvals if record.approval_key == approval_key),
        None,
    )
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item '{item_id}' was not found",
        )
    return HarnessReviewQueueItemResponse.from_approval(approval)


def _record_review_item_decision(
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


@router.get(
    "/{space_id}/review-queue",
    response_model=HarnessReviewQueueListResponse,
    summary="List items that still need review",
    description=(
        "Return the unified review queue for one space. By default this shows "
        "pending proposals, pending review-only items, and pending approvals. "
        "Use filters such as kind, run_id, document_id, or source_family when "
        "you want one slice of the queue. Use the lower-level proposal and "
        "approval routes when you need the specialized primitive records "
        "directly."
    ),
)
def list_review_queue(
    space_id: UUID,
    item_type: str | None = _ITEM_TYPE_QUERY,
    kind: str | None = _KIND_QUERY,
    status_filter: str | None = _STATUS_QUERY,
    run_id: UUID | None = _RUN_ID_QUERY,
    document_id: UUID | None = _DOCUMENT_ID_QUERY,
    source_family: str | None = _SOURCE_FAMILY_QUERY,
    offset: int = _OFFSET_QUERY,
    limit: int = _LIMIT_QUERY,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
) -> HarnessReviewQueueListResponse:
    """Return the flattened review queue for one research space."""
    items = _build_queue_items(
        space_id=space_id,
        proposal_store=proposal_store,
        review_item_store=review_item_store,
        approval_store=approval_store,
        status_filter=status_filter,
        item_type=_parse_item_type(item_type),
        kind=kind,
        source_family=(
            source_family.strip().lower()
            if isinstance(source_family, str) and source_family.strip() != ""
            else None
        ),
        run_id=run_id,
        document_id=document_id,
    )
    total = len(items)
    paged = items[offset : offset + limit]
    return HarnessReviewQueueListResponse(
        items=paged,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/review-queue/{item_id}",
    response_model=HarnessReviewQueueItemResponse,
    summary="Get one review queue item",
    description=(
        "Return one review queue item with its queue id, evidence, payload, and "
        "available actions. Queue ids are stable wrappers over proposals, "
        "review-only items, and run approvals."
    ),
)
def get_review_queue_item(
    space_id: UUID,
    item_id: str,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
) -> HarnessReviewQueueItemResponse:
    """Return one queue item by its stable review-queue id."""
    return _resolve_review_queue_item(
        space_id=space_id,
        item_id=item_id,
        proposal_store=proposal_store,
        review_item_store=review_item_store,
        approval_store=approval_store,
    )


@router.post(
    "/{space_id}/review-queue/{item_id}/actions",
    response_model=HarnessReviewQueueItemResponse,
    summary="Apply one review action",
    description=(
        "Apply a review action through the unified queue surface. Proposal items "
        "dispatch to proposal promotion or rejection, review-only items dispatch "
        "to conversion, resolution, or dismissal, and approval items dispatch "
        "to run approval decisions. Use 'mark_resolved' as the canonical "
        "review-item resolve action; 'resolve' remains accepted as a "
        "compatibility alias."
    ),
    dependencies=[Depends(require_harness_space_write_access)],
)
def act_on_review_queue_item(  # noqa: PLR0913
    space_id: UUID,
    item_id: str,
    request: HarnessReviewQueueActionRequest = Body(...),
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services=_HARNESS_EXECUTION_SERVICES_DEPENDENCY,
) -> HarnessReviewQueueItemResponse:
    """Apply one action to a queue item and return the refreshed queue view."""
    item_type, resource_key = _split_review_queue_item_id(item_id)
    normalized_action = request.action.strip().lower()

    if item_type == "proposal":
        proposal_id = UUID(resource_key)
        if normalized_action == "promote":
            promote_proposal(
                space_id=space_id,
                proposal_id=proposal_id,
                request=HarnessProposalDecisionRequest(
                    reason=request.reason,
                    metadata=request.metadata,
                ),
                proposal_store=proposal_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                graph_api_gateway=graph_api_gateway,
                execution_services=execution_services,
            )
        elif normalized_action == "reject":
            reject_proposal(
                space_id=space_id,
                proposal_id=proposal_id,
                request=HarnessProposalDecisionRequest(
                    reason=request.reason,
                    metadata=request.metadata,
                ),
                proposal_store=proposal_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                execution_services=execution_services,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Proposal-backed queue items only support the actions "
                    "'promote' and 'reject'"
                ),
            )
        refreshed_proposal = proposal_store.get_proposal(
            space_id=space_id,
            proposal_id=proposal_id,
        )
        if refreshed_proposal is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review queue item '{item_id}' was not found",
            )
        return HarnessReviewQueueItemResponse.from_proposal(refreshed_proposal)

    if item_type == "review_item":
        if normalized_action == "convert_to_proposal":
            return _convert_review_item_to_proposal(
                space_id=space_id,
                review_item_id=resource_key,
                review_item_store=review_item_store,
                proposal_store=proposal_store,
                reason=request.reason,
                metadata=request.metadata,
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        decision_status = {
            "resolve": "resolved",
            "mark_resolved": "resolved",
            "dismiss": "dismissed",
        }.get(normalized_action)
        if decision_status is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Review-only queue items only support the actions "
                    "'convert_to_proposal', 'mark_resolved', and 'dismiss' "
                    "(with 'resolve' accepted as a compatibility alias)"
                ),
            )
        try:
            updated_review_item = review_item_store.decide_review_item(
                space_id=space_id,
                review_item_id=resource_key,
                status=decision_status,
                decision_reason=request.reason,
                metadata=request.metadata,
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
                detail=f"Review queue item '{item_id}' was not found",
            )
        _record_review_item_decision(
            space_id=space_id,
            review_item=updated_review_item,
            action=normalized_action,
            run_registry=run_registry,
            artifact_store=artifact_store,
        )
        return HarnessReviewQueueItemResponse.from_review_item(updated_review_item)

    run_id_text, _, approval_key = resource_key.partition(":")
    if normalized_action not in {"approve", "reject"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Approval-backed queue items only support the actions 'approve' "
                "and 'reject'"
            ),
        )
    decide_run_approval(
        space_id=space_id,
        run_id=UUID(run_id_text),
        approval_key=approval_key,
        request=HarnessApprovalDecisionRequest(
            decision="approved" if normalized_action == "approve" else "rejected",
            reason=request.reason,
        ),
        run_registry=run_registry,
        approval_store=approval_store,
        artifact_store=artifact_store,
    )
    refreshed_approval = next(
        (
            approval
            for approval in approval_store.list_approvals(
                space_id=space_id,
                run_id=run_id_text,
            )
            if approval.approval_key == approval_key
        ),
        None,
    )
    if refreshed_approval is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item '{item_id}' was not found",
        )
    return HarnessReviewQueueItemResponse.from_approval(refreshed_approval)


__all__ = [
    "HarnessReviewQueueActionRequest",
    "HarnessReviewQueueItemResponse",
    "HarnessReviewQueueListResponse",
    "act_on_review_queue_item",
    "get_review_queue_item",
    "list_review_queue",
    "review_queue_item_id_for_approval",
    "review_queue_item_id_for_proposal",
    "review_queue_item_id_for_review_item",
    "router",
]
