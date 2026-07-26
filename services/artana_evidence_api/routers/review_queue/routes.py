"""Unified review-queue endpoints for proposals, review items, and approvals."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.approval_store import HarnessApprovalStore  # noqa: TC001
from artana_evidence_api.artifact_store import (
    HarnessArtifactStore,  # noqa: TC001
)
from artana_evidence_api.dependencies import (
    ReviewActorDependency,
    get_approval_store,
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_proposal_store,
    get_review_item_store,
    get_run_registry,
    require_harness_space_read_access,
)
from artana_evidence_api.graph_client import GraphTransportBundle  # noqa: TC001
from artana_evidence_api.proposal_store import HarnessProposalStore  # noqa: TC001
from artana_evidence_api.review_item_store import (
    HarnessReviewItemStore,  # noqa: TC001
)
from artana_evidence_api.routers.approvals import (
    HarnessApprovalDecisionRequest,
)
from artana_evidence_api.routers.approvals import (
    decide_approval as decide_run_approval,
)
from artana_evidence_api.routers.proposals import (
    HarnessProposalDecisionRequest,
    promote_proposal,
    reject_proposal,
)
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status

from .conversion import (
    convert_review_item_to_proposal,
    record_review_item_decision,
)
from .models import (
    HarnessReviewQueueActionRequest,
    HarnessReviewQueueBulkDecisionRequest,
    HarnessReviewQueueBulkDecisionResponse,
    HarnessReviewQueueBulkDecisionResult,
    HarnessReviewQueueBulkDecisionSummary,
    HarnessReviewQueueItemResponse,
    HarnessReviewQueueListResponse,
)

if TYPE_CHECKING:
    from artana_evidence_api.harness_runtime import HarnessExecutionServices

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
_STATUS_QUERY = Query(
    default=None,
    alias="status",
    description=(
        "Statuses to return. Repeat the parameter or comma-join the values, and "
        "use the group name 'pending' or 'decided' for a whole family of them. "
        "Defaults to the pending work in each family."
    ),
)
_LEGACY_STATUS_QUERY = Query(
    default=None,
    alias="status_filter",
    deprecated=True,
    description=(
        "Deprecated spelling of 'status', used only when 'status' is absent. It "
        "now resolves identically, so status_filter=pending returns the whole "
        "pending queue rather than only pending approvals."
    ),
)
_ORDER_BY_QUERY = Query(
    default="ranking",
    min_length=1,
    max_length=32,
    description="Order results by 'ranking' (default) or 'decided_at'.",
)
_RUN_ID_QUERY = Query(default=None)
_DOCUMENT_ID_QUERY = Query(default=None)
_SOURCE_FAMILY_QUERY = Query(default=None, min_length=1, max_length=64)
_EVIDENCE_GRADE_QUERY = Query(default=None, min_length=1, max_length=96)
_OFFSET_QUERY = Query(default=0, ge=0)
_LIMIT_QUERY = Query(default=200, ge=1, le=1000)
_MAX_BULK_DECISIONS = 1000

_RISK_PRIORITY = {"low": "low", "medium": "medium", "high": "high", "critical": "high"}
_PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}
_ITEM_TYPE_VALUES = frozenset({"proposal", "review_item", "approval"})

#: What each backing family calls a decision that has not been made yet.
_PENDING_STATUSES = ("pending_review", "pending")
#: What each backing family calls a decision that has been made.
#:
#: The three stores use disjoint vocabularies for the same idea, so a single
#: scalar filter could only ever name one family's outcome.  Asking for the
#: audit trail -- everything decided, with its written reason -- needs the
#: whole set, which is why status accepts a group name and a comma list.
_DECIDED_STATUSES = (
    "promoted",
    "rejected",
    "approved",
    "resolved",
    "dismissed",
)
#: Held back from review rather than pending or decided.
#:
#: A cross-document fingerprint collision is parked here (ART-DATA-001): a second
#: independent observation whose identity has not been adjudicated against the
#: first.  Nobody can act on it yet, but it is not nothing either, so it needs a
#: name a reviewer can ask for.
_PARKED_STATUSES = ("identity_pending",)
_STATUS_GROUPS = {
    "pending": _PENDING_STATUSES,
    "decided": _DECIDED_STATUSES,
    "parked": _PARKED_STATUSES,
}
#: Every status any queue-backing store can hold.
_KNOWN_STATUSES = frozenset(
    (*_PENDING_STATUSES, *_DECIDED_STATUSES, *_PARKED_STATUSES),
)
_ORDER_BY_VALUES = frozenset({"ranking", "decided_at"})
_MAX_STATUS_VALUES = 8

def _queue_sort_key(item: HarnessReviewQueueItemResponse) -> tuple[float, int, str]:
    ranking = item.ranking_score if item.ranking_score is not None else 0.0
    priority_weight = _PRIORITY_WEIGHT.get(item.priority, 1)
    return (ranking, priority_weight, item.updated_at)


def _decision_sort_key(item: HarnessReviewQueueItemResponse) -> tuple[str, str]:
    """Order a decision trail newest-decision-first.

    Undecided items have no decision time; they sort last rather than being
    dropped, so a mixed query still shows them.
    """
    return (item.decided_at or "", item.updated_at)


def _parse_order_by(raw_value: str) -> str:
    normalized = raw_value.strip().lower()
    if normalized not in _ORDER_BY_VALUES:
        msg = (
            f"Unsupported review queue order_by '{raw_value}'. "
            f"Supported values: {', '.join(sorted(_ORDER_BY_VALUES))}"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return normalized


def _status_tokens(raw_values: list[str] | None) -> list[str]:
    """Flatten repeated and comma-joined status parameters into single tokens.

    Both spellings are accepted because both are natural: ``?status=a,b`` and
    ``?status=a&status=b``.  A scalar parameter would keep only the last
    occurrence, so a caller writing the repeated form would get a silently
    partial answer -- and a typo in any but the last occurrence would never
    reach validation at all.
    """
    if raw_values is None:
        return []
    return [
        token.strip().lower()
        for raw_value in raw_values
        for token in raw_value.split(",")
    ]


def _parse_statuses(raw_values: list[str] | None) -> frozenset[str] | None:
    """Resolve the requested status filter into a concrete set of statuses.

    Returns None only when the parameter was not supplied at all, which the
    caller reads as the pending default.  Anything supplied but unusable -- an
    unknown status, or punctuation that names nothing -- is a 400 rather than
    an empty or defaulted 200: on an audit surface, "no results" and "you asked
    the wrong question" must not look the same.

    Group names expand per token rather than only as the whole value, so
    ``pending`` means the same thing in ``?status=pending`` and in
    ``?status=pending,rejected``.  That matters because ``pending`` is both a
    group name and the approval store's own literal status; resolving it
    differently by position would quietly drop every pending proposal from the
    second query.  To ask for pending approvals alone, filter by
    ``item_type=approval``.
    """
    if raw_values is None:
        return None
    supplied = [token for token in _status_tokens(raw_values) if token != ""]
    if supplied == []:
        msg = (
            "The status parameter was supplied but names no status. Omit it to "
            "get the pending queue."
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    distinct = sorted(set(supplied))
    if len(distinct) > _MAX_STATUS_VALUES:
        msg = (
            f"Too many distinct status values ({len(distinct)}); "
            f"at most {_MAX_STATUS_VALUES} are accepted"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    resolved: set[str] = set()
    unknown: list[str] = []
    for token in distinct:
        group = _STATUS_GROUPS.get(token)
        if group is not None:
            resolved.update(group)
        elif token in _KNOWN_STATUSES:
            resolved.add(token)
        else:
            unknown.append(token)
    if unknown:
        msg = (
            f"Unsupported review queue status {unknown}. Supported values: "
            f"{', '.join(sorted(_KNOWN_STATUSES))}, or the groups "
            f"{', '.join(sorted(_STATUS_GROUPS))}"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return frozenset(resolved)


def _parse_item_type(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    normalized = raw_value.strip().lower()
    if normalized not in _ITEM_TYPE_VALUES:
        msg = f"Unsupported review queue item_type '{raw_value}'"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    return normalized


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _split_review_queue_item_id(item_id: str) -> tuple[str, str]:
    """Split a queue id into its family and resource key.

    The resource key has to be validated here, not downstream.  Every consumer
    of it either interpolates it into a `uuid` column comparison -- where a
    non-UUID reaches Postgres as ``'abc'::UUID`` and raises DataError -- or
    calls ``UUID()`` on it directly.  Both surfaced as a 500 for what is really
    a malformed identifier, so a stale bookmark was indistinguishable from a
    broken service.
    """
    normalized = item_id.strip()
    if normalized.startswith("proposal:"):
        resource_key = normalized.removeprefix("proposal:")
        if _is_uuid(resource_key):
            return "proposal", resource_key
    elif normalized.startswith("review_item:"):
        resource_key = normalized.removeprefix("review_item:")
        if _is_uuid(resource_key):
            return "review_item", resource_key
    elif normalized.startswith("approval:"):
        payload = normalized.removeprefix("approval:")
        run_id, separator, approval_key = payload.partition(":")
        if separator and run_id and approval_key and _is_uuid(run_id):
            return "approval", payload
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Review queue item '{item_id}' was not found",
    )


def _bulk_decision_error_text(detail: object) -> str:
    if isinstance(detail, str):
        return detail
    return str(detail)


def _build_queue_items(
    *,
    space_id: UUID,
    proposal_store: HarnessProposalStore,
    review_item_store: HarnessReviewItemStore,
    approval_store: HarnessApprovalStore,
    statuses: frozenset[str] | None,
    item_type: str | None,
    kind: str | None,
    source_family: str | None,
    run_id: UUID | None,
    document_id: UUID | None,
    evidence_grade: str | None,
    order_by: str,
) -> list[HarnessReviewQueueItemResponse]:
    items: list[HarnessReviewQueueItemResponse] = []
    normalized_kind = kind.strip() if isinstance(kind, str) else None
    requested = statuses if statuses is not None else frozenset(_PENDING_STATUSES)

    if item_type in {None, "proposal"}:
        for proposal_status in sorted(requested):
            items.extend(
                HarnessReviewQueueItemResponse.from_proposal(proposal)
                for proposal in proposal_store.list_proposals(
                    space_id=space_id,
                    status=proposal_status,
                    proposal_type=normalized_kind if item_type == "proposal" else None,
                    run_id=run_id,
                    document_id=document_id,
                    evidence_grade=evidence_grade,
                )
                if normalized_kind is None or proposal.proposal_type == normalized_kind
            )
    if item_type in {None, "review_item"}:
        for review_item_status in sorted(requested):
            items.extend(
                HarnessReviewQueueItemResponse.from_review_item(review_item)
                for review_item in review_item_store.list_review_items(
                    space_id=space_id,
                    status=review_item_status,
                    review_type=normalized_kind if item_type == "review_item" else None,
                    source_family=source_family,
                    run_id=run_id,
                    document_id=document_id,
                    evidence_grade=evidence_grade,
                )
                if normalized_kind is None or review_item.review_type == normalized_kind
            )
    if (
        item_type in {None, "approval"}
        and document_id is None
        and evidence_grade is None
    ):
        for approval_status in sorted(requested):
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
    if order_by == "decided_at":
        return sorted(filtered_items, key=_decision_sort_key, reverse=True)
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



@router.get(
    "/{space_id}/review-queue",
    response_model=HarnessReviewQueueListResponse,
    summary="List items that still need review",
    description=(
        "Return the unified review queue for one space. By default this shows "
        "pending proposals, pending review-only items, and pending approvals. "
        "Pass status=decided to read the audit trail -- everything promoted, "
        "rejected, approved, resolved, or dismissed, each with its written "
        "decision_reason and the reviewer who made it -- or a comma-separated "
        "list such as status=promoted,rejected for one slice of it. Order the "
        "trail with order_by=decided_at. Use the lower-level proposal and "
        "approval routes when you need the specialized primitive records "
        "directly."
    ),
)
def list_review_queue(  # noqa: PLR0913
    space_id: UUID,
    item_type: str | None = _ITEM_TYPE_QUERY,
    kind: str | None = _KIND_QUERY,
    status_filter: list[str] | None = _STATUS_QUERY,
    legacy_status_filter: list[str] | None = _LEGACY_STATUS_QUERY,
    order_by: str = _ORDER_BY_QUERY,
    run_id: UUID | None = _RUN_ID_QUERY,
    document_id: UUID | None = _DOCUMENT_ID_QUERY,
    source_family: str | None = _SOURCE_FAMILY_QUERY,
    evidence_grade: str | None = _EVIDENCE_GRADE_QUERY,
    offset: int = _OFFSET_QUERY,
    limit: int = _LIMIT_QUERY,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
) -> HarnessReviewQueueListResponse:
    """Return the flattened review queue for one research space.

    ``status`` and the deprecated ``status_filter`` mean the same thing.  Only
    the deprecated spelling used to be accepted, so a caller sending the
    obvious ``?status=promoted`` silently got the pending queue back with a
    200 -- the worst possible answer for an audit question.
    """
    items = _build_queue_items(
        space_id=space_id,
        proposal_store=proposal_store,
        review_item_store=review_item_store,
        approval_store=approval_store,
        statuses=_parse_statuses(
            status_filter if status_filter is not None else legacy_status_filter,
        ),
        item_type=_parse_item_type(item_type),
        kind=kind,
        source_family=(
            source_family.strip().lower()
            if isinstance(source_family, str) and source_family.strip() != ""
            else None
        ),
        run_id=run_id,
        document_id=document_id,
        evidence_grade=evidence_grade,
        order_by=_parse_order_by(order_by),
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
)
def act_on_review_queue_item(  # noqa: PLR0913
    space_id: UUID,
    item_id: str,
    request: HarnessReviewQueueActionRequest = Body(...),
    *,
    decided_by: ReviewActorDependency,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = (
        _HARNESS_EXECUTION_SERVICES_DEPENDENCY
    ),
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
                decided_by=decided_by,
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
                decided_by=decided_by,
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
            return convert_review_item_to_proposal(
                space_id=space_id,
                review_item_id=resource_key,
                review_item_store=review_item_store,
                proposal_store=proposal_store,
                reason=request.reason,
                decided_by=decided_by,
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
                decided_by=decided_by,
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
        record_review_item_decision(
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
        decided_by=decided_by,
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


@router.post(
    "/{space_id}/review-queue:bulk-actions",
    response_model=HarnessReviewQueueBulkDecisionResponse,
    summary="Apply many review actions",
    description=(
        "Apply many review-queue decisions through the same dispatch path as the "
        "single-item action endpoint. Each decision is isolated so one failed "
        "item does not block the rest of the batch."
    ),
)
def act_on_review_queue_items_bulk(  # noqa: PLR0913
    space_id: UUID,
    request: HarnessReviewQueueBulkDecisionRequest = Body(...),
    *,
    decided_by: ReviewActorDependency,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    approval_store: HarnessApprovalStore = _APPROVAL_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
    graph_api_gateway: GraphTransportBundle = _GRAPH_API_GATEWAY_DEPENDENCY,
    execution_services: HarnessExecutionServices = (
        _HARNESS_EXECUTION_SERVICES_DEPENDENCY
    ),
) -> HarnessReviewQueueBulkDecisionResponse:
    """Apply a bounded batch of queue actions and return per-item outcomes."""

    results: list[HarnessReviewQueueBulkDecisionResult] = []
    for decision in request.decisions:
        try:
            item = act_on_review_queue_item(
                space_id=space_id,
                item_id=decision.item_id,
                request=HarnessReviewQueueActionRequest(
                    action=decision.action,
                    reason=decision.reason,
                    metadata=decision.metadata,
                ),
                decided_by=decided_by,
                proposal_store=proposal_store,
                review_item_store=review_item_store,
                approval_store=approval_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                graph_api_gateway=graph_api_gateway,
                execution_services=execution_services,
            )
        except HTTPException as exc:
            results.append(
                HarnessReviewQueueBulkDecisionResult(
                    item_id=decision.item_id,
                    status="failed",
                    error=_bulk_decision_error_text(exc.detail),
                ),
            )
            continue
        except ValueError as exc:
            results.append(
                HarnessReviewQueueBulkDecisionResult(
                    item_id=decision.item_id,
                    status="failed",
                    error=str(exc),
                ),
            )
            continue
        results.append(
            HarnessReviewQueueBulkDecisionResult(
                item_id=decision.item_id,
                status="accepted",
                new_state=item.status,
            ),
        )

    accepted_count = sum(1 for result in results if result.status == "accepted")
    return HarnessReviewQueueBulkDecisionResponse(
        results=results,
        summary=HarnessReviewQueueBulkDecisionSummary(
            accepted=accepted_count,
            failed=len(results) - accepted_count,
        ),
    )


__all__ = [
    "act_on_review_queue_item",
    "act_on_review_queue_items_bulk",
    "get_review_queue_item",
    "list_review_queue",
    "router",
]
