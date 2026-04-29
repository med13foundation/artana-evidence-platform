"""Unit coverage for extracted evidence-selection artifact helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from artana_evidence_api.approval_store import HarnessApprovalRecord
from artana_evidence_api.document_store import HarnessDocumentRecord
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateSearch,
)
from artana_evidence_api.evidence_selection_result_serialization import (
    proposal_result_payload,
    review_item_result_payload,
)
from artana_evidence_api.evidence_selection_source_plan_artifact import (
    build_source_plan,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
)
from artana_evidence_api.evidence_selection_workspace_snapshot import (
    build_evidence_selection_workspace_snapshot,
)
from artana_evidence_api.proposal_store import HarnessProposalRecord
from artana_evidence_api.review_item_store import HarnessReviewItemRecord
from artana_evidence_api.run_registry import HarnessRunRecord


@dataclass(frozen=True, slots=True)
class _ListStore:
    records: list[object]

    def list_runs(self, *, space_id):  # noqa: ANN001
        del space_id
        return list(self.records)

    def list_documents(self, *, space_id):  # noqa: ANN001
        del space_id
        return list(self.records)

    def list_proposals(self, *, space_id):  # noqa: ANN001
        del space_id
        return list(self.records)

    def list_review_items(self, *, space_id):  # noqa: ANN001
        del space_id
        return list(self.records)

    def list_space_approvals(self, *, space_id):  # noqa: ANN001
        del space_id
        return list(self.records)


def test_build_source_plan_summarizes_requested_live_and_saved_sources() -> None:
    search_id = uuid4()

    plan = build_source_plan(
        goal="Find MED13 evidence",
        instructions="Prioritize variants.",
        requested_sources=("pubmed", "clinvar"),
        source_searches=(
            EvidenceSelectionLiveSourceSearch(
                source_key="clinvar",
                query_payload={"gene_symbol": "MED13"},
            ),
        ),
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="pubmed",
                search_id=search_id,
            ),
        ),
        inclusion_criteria=("MED13",),
        exclusion_criteria=("unrelated",),
        population_context="cardiac",
        evidence_types=("variant",),
        priority_outcomes=("pathogenicity",),
        planner_kind="model",
        planner_mode="guarded",
        planner_reason="test",
        model_id="model-1",
        planner_version="v1",
        planned_searches=({"source_key": "clinvar"},),
        deferred_sources=({"source_key": "uniprot"},),
        validation_decisions=({"source_key": "clinvar", "status": "accepted"},),
        fallback_reason=None,
        agent_run_id="agent-1",
    )

    assert plan["sources"] == [
        {
            "source_key": "pubmed",
            "source_family": "literature",
            "candidate_search_count": 1,
            "live_search_count": 0,
            "action": "screen_saved_searches",
            "reason": "Saved source-search results were supplied for this source.",
        },
        {
            "source_key": "clinvar",
            "source_family": "variant",
            "candidate_search_count": 0,
            "live_search_count": 1,
            "action": "run_and_screen_source_searches",
            "reason": (
                "The harness will create and screen source-search results for this "
                "source."
            ),
        },
    ]
    assert plan["planner"]["agent_invoked"] is True
    assert plan["selection_policy"]["inclusion_criteria"] == ["MED13"]


def test_result_serializers_keep_artifact_payloads_small() -> None:
    now = datetime.now(UTC)
    proposal = HarnessProposalRecord(
        id="proposal-1",
        space_id="space-1",
        run_id="run-1",
        proposal_type="candidate_claim",
        source_kind="source_search",
        source_key="pubmed:1",
        document_id="document-1",
        title="MED13 evidence",
        summary="summary",
        status="pending_review",
        confidence=0.8,
        ranking_score=0.7,
        reasoning_path={"step": "screen"},
        evidence_bundle=[{"locator": "pmid:1"}],
        payload={"claim": "payload"},
        metadata={"extra": "ignored"},
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
        claim_fingerprint="fingerprint-1",
    )
    review_item = HarnessReviewItemRecord(
        id="review-1",
        space_id="space-1",
        run_id="run-1",
        review_type="source_record",
        source_family="literature",
        source_kind="source_search",
        source_key="pubmed:1",
        document_id="document-1",
        title="Review MED13",
        summary="summary",
        priority="high",
        status="pending_review",
        confidence=0.6,
        ranking_score=0.5,
        evidence_bundle=[],
        payload={},
        metadata={},
        decision_reason=None,
        decided_at=None,
        linked_proposal_id=None,
        linked_approval_key=None,
        created_at=now,
        updated_at=now,
        review_fingerprint="review-fingerprint-1",
    )

    assert proposal_result_payload(proposal) == {
        "proposal_id": "proposal-1",
        "proposal_type": "candidate_claim",
        "source_key": "pubmed:1",
        "document_id": "document-1",
        "title": "MED13 evidence",
        "status": "pending_review",
        "claim_fingerprint": "fingerprint-1",
    }
    assert review_item_result_payload(review_item) == {
        "review_item_id": "review-1",
        "review_type": "source_record",
        "source_key": "pubmed:1",
        "document_id": "document-1",
        "title": "Review MED13",
        "priority": "high",
        "status": "pending_review",
        "review_fingerprint": "review-fingerprint-1",
    }


def test_workspace_snapshot_captures_prior_state_and_dedup_keys() -> None:
    now = datetime.now(UTC)
    space_id = uuid4()
    current_run = HarnessRunRecord(
        id="run-current",
        space_id=str(space_id),
        harness_id="evidence-selection",
        title="Current run",
        status="running",
        input_payload={"goal": "current"},
        graph_service_status="ok",
        graph_service_version="test",
        created_at=now,
        updated_at=now,
    )
    prior_run = HarnessRunRecord(
        id="run-prior",
        space_id=str(space_id),
        harness_id="evidence-selection",
        title="Prior run",
        status="completed",
        input_payload={"goal": "prior", "instructions": "old"},
        graph_service_status="ok",
        graph_service_version="test",
        created_at=now,
        updated_at=now,
    )
    document = HarnessDocumentRecord(
        id="document-1",
        space_id=str(space_id),
        created_by="user-1",
        title="MED13 paper",
        source_type="pubmed",
        filename=None,
        media_type="application/json",
        sha256="sha",
        byte_size=1,
        page_count=None,
        text_content="MED13 evidence",
        text_excerpt="MED13 evidence",
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id="ingest-1",
        last_enrichment_run_id=None,
        last_extraction_run_id=None,
        enrichment_status="completed",
        extraction_status="completed",
        metadata={
            "source_capture": {
                "source_key": "pubmed",
                "provider_record_id": "PMID1",
            },
            "source_family": "literature",
            "source_search_id": "search-1",
            "selected_record_index": 0,
        },
        created_at=now,
        updated_at=now,
    )
    proposal = HarnessProposalRecord(
        id="proposal-1",
        space_id=str(space_id),
        run_id="run-prior",
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key="document-1:0",
        document_id="document-1",
        title="MED13 claim",
        summary="summary",
        status="promoted",
        confidence=0.9,
        ranking_score=0.8,
        reasoning_path={},
        evidence_bundle=[],
        payload={},
        metadata={},
        decision_reason=None,
        decided_at=None,
        created_at=now,
        updated_at=now,
        claim_fingerprint="claim-fingerprint",
    )
    review_item = HarnessReviewItemRecord(
        id="review-1",
        space_id=str(space_id),
        run_id="run-prior",
        review_type="source_record",
        source_family="literature",
        source_kind="source_search",
        source_key="pubmed:1",
        document_id="document-1",
        title="Review",
        summary="summary",
        priority="medium",
        status="pending_review",
        confidence=0.7,
        ranking_score=0.6,
        evidence_bundle=[],
        payload={},
        metadata={},
        decision_reason=None,
        decided_at=None,
        linked_proposal_id=None,
        linked_approval_key=None,
        created_at=now,
        updated_at=now,
        review_fingerprint="review-fingerprint",
    )
    approval = HarnessApprovalRecord(
        space_id=str(space_id),
        run_id="run-prior",
        approval_key="approval-1",
        title="Approve",
        risk_level="low",
        target_type="proposal",
        target_id="proposal-1",
        status="approved",
        decision_reason="ok",
        metadata={},
        created_at=now,
        updated_at=now,
    )

    snapshot = build_evidence_selection_workspace_snapshot(
        space_id=space_id,
        run=current_run,
        goal="current",
        instructions=None,
        parent_run_id=None,
        run_registry=_ListStore([current_run, prior_run]),
        document_store=_ListStore([document]),
        proposal_store=_ListStore([proposal]),
        review_item_store=_ListStore([review_item]),
        approval_store=_ListStore([approval]),
    )

    assert snapshot["prior_evidence_run_count"] == 1
    assert snapshot["proposal_status_counts"] == {"promoted": 1}
    assert snapshot["review_item_status_counts"] == {"pending_review": 1}
    assert snapshot["approval_status_counts"] == {"approved": 1}
    assert snapshot["graph_state_summary"]["approved_evidence_count"] == 1
    assert snapshot["deduplication"]["proposal_fingerprints"] == [
        "claim-fingerprint",
    ]
    assert snapshot["deduplication"]["review_fingerprints"] == [
        "review-fingerprint",
    ]
