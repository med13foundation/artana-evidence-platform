"""Workspace snapshot builders for evidence-selection runs."""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from artana_evidence_api.approval_store import (
    HarnessApprovalRecord,
    HarnessApprovalStore,
)
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.review_item_store import (
    HarnessReviewItemRecord,
    HarnessReviewItemStore,
)
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.source_document_selection_identity import (
    source_document_dedup_key,
)
from artana_evidence_api.types.common import JSONObject, json_object_or_empty


def build_evidence_selection_workspace_snapshot(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    goal: str,
    instructions: str | None,
    parent_run_id: UUID | str | None,
    run_registry: HarnessRunRegistry,
    document_store: HarnessDocumentStore,
    proposal_store: HarnessProposalStore,
    review_item_store: HarnessReviewItemStore | None,
    approval_store: HarnessApprovalStore | None,
) -> JSONObject:
    """Return compact prior workspace state for evidence-selection decisions."""

    prior_runs = [
        prior_run
        for prior_run in run_registry.list_runs(space_id=space_id)
        if prior_run.id != run.id
    ][:20]
    prior_documents = document_store.list_documents(space_id=space_id)[:50]
    prior_proposals = proposal_store.list_proposals(space_id=space_id)[:50]
    prior_review_items = (
        review_item_store.list_review_items(space_id=space_id)[:50]
        if review_item_store is not None
        else []
    )
    prior_approvals = (
        approval_store.list_space_approvals(space_id=space_id)[:50]
        if approval_store is not None
        else []
    )
    prior_evidence_runs = [
        prior_run
        for prior_run in prior_runs
        if prior_run.harness_id == "evidence-selection"
    ]
    return {
        "space_id": str(space_id),
        "run_id": run.id,
        "goal": goal,
        "instructions": instructions,
        "parent_run_id": str(parent_run_id) if parent_run_id is not None else None,
        "prior_run_count": len(prior_runs),
        "prior_evidence_run_count": len(prior_evidence_runs),
        "prior_goals": [
            _compact_prior_goal(prior_run) for prior_run in prior_evidence_runs[:10]
        ],
        "document_count": len(prior_documents),
        "source_documents": [
            _document_snapshot(document) for document in prior_documents[:20]
        ],
        "proposal_count": len(prior_proposals),
        "proposal_status_counts": dict(
            sorted(Counter(proposal.status for proposal in prior_proposals).items()),
        ),
        "proposals": [
            _proposal_snapshot(proposal) for proposal in prior_proposals[:20]
        ],
        "review_item_count": len(prior_review_items),
        "review_item_status_counts": dict(
            sorted(Counter(item.status for item in prior_review_items).items()),
        ),
        "review_items": [
            _review_item_snapshot(review_item)
            for review_item in prior_review_items[:20]
        ],
        "approval_count": len(prior_approvals),
        "approval_status_counts": dict(
            sorted(Counter(approval.status for approval in prior_approvals).items()),
        ),
        "approvals": [
            _approval_snapshot(approval) for approval in prior_approvals[:20]
        ],
        "graph_state_summary": _graph_state_summary(
            proposals=prior_proposals,
            approvals=prior_approvals,
        ),
        "deduplication": {
            "source_document_keys": sorted(
                {
                    key
                    for key in (
                        source_document_dedup_key(document)
                        for document in prior_documents
                    )
                    if key is not None
                },
            ),
            "proposal_fingerprints": sorted(
                proposal.claim_fingerprint
                for proposal in prior_proposals
                if proposal.claim_fingerprint is not None
            ),
            "review_fingerprints": sorted(
                review_item.review_fingerprint
                for review_item in prior_review_items
                if review_item.review_fingerprint is not None
            ),
        },
    }


def _compact_prior_goal(run: HarnessRunRecord) -> JSONObject:
    return {
        "run_id": run.id,
        "status": run.status,
        "goal": (
            run.input_payload.get("goal")
            if isinstance(run.input_payload.get("goal"), str)
            else None
        ),
        "instructions": (
            run.input_payload.get("instructions")
            if isinstance(run.input_payload.get("instructions"), str)
            else None
        ),
        "created_at": run.created_at.isoformat(),
    }


def _document_snapshot(document: HarnessDocumentRecord) -> JSONObject:
    source_capture = json_object_or_empty(document.metadata.get("source_capture"))
    return {
        "document_id": document.id,
        "title": document.title,
        "source_type": document.source_type,
        "source_family": document.metadata.get("source_family"),
        "source_search_id": document.metadata.get("source_search_id"),
        "selected_record_index": document.metadata.get("selected_record_index"),
        "extraction_status": document.extraction_status,
        "source_capture": source_capture,
    }


def _proposal_snapshot(proposal: HarnessProposalRecord) -> JSONObject:
    return {
        "proposal_id": proposal.id,
        "title": proposal.title,
        "proposal_type": proposal.proposal_type,
        "source_key": proposal.source_key,
        "status": proposal.status,
        "confidence": proposal.confidence,
        "ranking_score": proposal.ranking_score,
        "claim_fingerprint": proposal.claim_fingerprint,
    }


def _review_item_snapshot(review_item: HarnessReviewItemRecord) -> JSONObject:
    return {
        "review_item_id": review_item.id,
        "title": review_item.title,
        "review_type": review_item.review_type,
        "source_key": review_item.source_key,
        "source_family": review_item.source_family,
        "status": review_item.status,
        "priority": review_item.priority,
        "confidence": review_item.confidence,
        "ranking_score": review_item.ranking_score,
        "review_fingerprint": review_item.review_fingerprint,
    }


def _approval_snapshot(approval: HarnessApprovalRecord) -> JSONObject:
    return {
        "run_id": approval.run_id,
        "approval_key": approval.approval_key,
        "title": approval.title,
        "risk_level": approval.risk_level,
        "target_type": approval.target_type,
        "target_id": approval.target_id,
        "status": approval.status,
        "decision_reason": approval.decision_reason,
    }


def _graph_state_summary(
    *,
    proposals: list[HarnessProposalRecord],
    approvals: list[HarnessApprovalRecord],
) -> JSONObject:
    promoted_proposals = [
        proposal for proposal in proposals if proposal.status == "promoted"
    ]
    approved_actions = [
        approval for approval in approvals if approval.status == "approved"
    ]
    return {
        "approved_evidence_count": len(promoted_proposals),
        "approved_action_count": len(approved_actions),
        "pending_review_count": sum(
            1 for proposal in proposals if proposal.status == "pending_review"
        ),
        "rejected_evidence_count": sum(
            1 for proposal in proposals if proposal.status == "rejected"
        ),
        "summary_basis": (
            "Evidence API proposal and approval state; trusted graph facts are "
            "still read through the graph service."
        ),
    }


__all__ = ["build_evidence_selection_workspace_snapshot"]
