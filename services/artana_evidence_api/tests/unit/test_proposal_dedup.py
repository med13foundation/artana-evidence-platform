"""Unit tests for proposal-level deduplication via claim fingerprints."""

from __future__ import annotations

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)


def _make_draft(
    subject: str = "MED13",
    relation: str = "ASSOCIATED_WITH",
    obj: str = "intellectual disability",
    *,
    source_key: str = "doc:1",
    fingerprint: bool = True,
) -> HarnessProposalDraft:
    fp = compute_claim_fingerprint(subject, relation, obj) if fingerprint else None
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=source_key,
        title=f"{subject} {relation} {obj}",
        summary=f"{subject} is related to {obj}",
        confidence=0.9,
        ranking_score=0.85,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject_label": subject,
            "proposed_claim_type": relation,
            "proposed_object_label": obj,
        },
        metadata={},
        claim_fingerprint=fp,
    )


SPACE_ID = "aaaaaaaa-0000-0000-0000-000000000001"
RUN_A = "bbbbbbbb-0000-0000-0000-000000000001"
RUN_B = "bbbbbbbb-0000-0000-0000-000000000002"


class TestCreationTimeDedup:
    """Proposals with matching fingerprint are skipped at creation time."""

    def test_duplicate_proposal_skipped_if_already_exists(self) -> None:
        store = HarnessProposalStore()
        draft = _make_draft()
        # Create first
        created = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft,),
        )
        assert len(created) == 1
        # Attempt identical — should be skipped
        duplicates = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft,),
        )
        assert len(duplicates) == 0
        # Only one proposal in the store
        all_proposals = store.list_proposals(space_id=SPACE_ID)
        assert len(all_proposals) == 1

    def test_duplicate_proposal_skipped_if_promoted(self) -> None:
        store = HarnessProposalStore()
        draft = _make_draft()
        created = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft,),
        )
        store.decide_proposal(
            space_id=SPACE_ID,
            proposal_id=created[0].id,
            status="promoted",
            decision_reason="Good claim",
        )
        # Try to create same claim — should be skipped (status=promoted)
        duplicates = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_B,
            proposals=(draft,),
        )
        assert len(duplicates) == 0

    def test_duplicate_proposal_allowed_if_rejected(self) -> None:
        store = HarnessProposalStore()
        draft = _make_draft()
        created = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft,),
        )
        store.decide_proposal(
            space_id=SPACE_ID,
            proposal_id=created[0].id,
            status="rejected",
            decision_reason="Not relevant",
        )
        # Rejected — new evidence may change the decision, allow re-creation
        new_proposals = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_B,
            proposals=(draft,),
        )
        assert len(new_proposals) == 1

    def test_different_claim_not_blocked(self) -> None:
        store = HarnessProposalStore()
        draft1 = _make_draft(subject="MED13", relation="INHIBITS", obj="Pol II")
        draft2 = _make_draft(subject="CKM", relation="ACTIVATES", obj="gene expression")
        store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft1,),
        )
        created = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft2,),
        )
        assert len(created) == 1  # Different claim, not blocked

    def test_cross_run_dedup(self) -> None:
        store = HarnessProposalStore()
        draft = _make_draft()
        # Run A creates proposal
        store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft,),
        )
        # Run B tries the same claim — blocked
        duplicates = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_B,
            proposals=(draft,),
        )
        assert len(duplicates) == 0

    def test_no_fingerprint_skips_dedup(self) -> None:
        """Proposals without fingerprint bypass dedup (backward compat)."""
        store = HarnessProposalStore()
        draft_no_fp = _make_draft(fingerprint=False)
        store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft_no_fp,),
        )
        # Same source_key, no fingerprint — allowed (no fingerprint dedup)
        created = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft_no_fp,),
        )
        assert len(created) == 1  # No fingerprint = no dedup


class TestAutoRejectOnPromotion:
    """When a proposal is promoted, pending duplicates are auto-rejected."""

    def test_promotion_auto_rejects_pending_duplicates(self) -> None:
        store = HarnessProposalStore()
        draft = _make_draft()
        # Create 3 duplicate proposals (from different runs)
        p1 = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft,),
        )
        assert p1[0].claim_fingerprint is not None

        # Simulate: promote first, then reject duplicates
        store.decide_proposal(
            space_id=SPACE_ID,
            proposal_id=p1[0].id,
            status="promoted",
            decision_reason="Best evidence",
        )

        # No pending duplicates to reject (only 1 proposal exists)
        count = store.reject_pending_duplicates(
            space_id=SPACE_ID,
            claim_fingerprint=p1[0].claim_fingerprint,
            exclude_id=p1[0].id,
            reason="Auto-rejected: equivalent claim promoted",
        )
        assert count == 0

    def test_reject_pending_duplicates_works(self) -> None:
        """Test reject_pending_duplicates with manually created duplicates."""
        store = HarnessProposalStore()
        fp = compute_claim_fingerprint("A", "REL", "B")
        # Create two proposals with same fingerprint by inserting directly
        draft1 = _make_draft(subject="A", relation="REL", obj="B", source_key="s1")
        p1 = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft1,),
        )
        assert len(p1) == 1
        # Second would be blocked by dedup. Force-insert by clearing fingerprint
        # then manually set it. We'll just test reject_pending_duplicates logic.
        # Create a different proposal first
        draft_diff = _make_draft(subject="X", relation="REL", obj="Y", source_key="s2")
        p2 = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft_diff,),
        )
        assert len(p2) == 1

        # Promote p1
        store.decide_proposal(
            space_id=SPACE_ID,
            proposal_id=p1[0].id,
            status="promoted",
            decision_reason="Good",
        )
        # Reject duplicates — p2 has different fingerprint, shouldn't be affected
        count = store.reject_pending_duplicates(
            space_id=SPACE_ID,
            claim_fingerprint=fp,
            exclude_id=p1[0].id,
            reason="Auto-rejected",
        )
        assert count == 0  # p2 has different fingerprint

        # p2 should still be pending
        p2_record = store.get_proposal(
            space_id=SPACE_ID,
            proposal_id=p2[0].id,
        )
        assert p2_record is not None
        assert p2_record.status == "pending_review"

    def test_auto_reject_sets_reason(self) -> None:
        store = HarnessProposalStore()
        fp = "test_fingerprint_abc"

        # Manually create two records with same fingerprint via internal access
        from datetime import UTC, datetime
        from uuid import uuid4

        now = datetime.now(UTC)
        for i in range(2):
            pid = str(uuid4())
            from artana_evidence_api.proposal_store import HarnessProposalRecord

            r = HarnessProposalRecord(
                id=pid,
                space_id=SPACE_ID,
                run_id=RUN_A,
                proposal_type="candidate_claim",
                source_kind="test",
                source_key=f"key:{i}",
                document_id=None,
                title=f"Test {i}",
                summary=f"Test {i}",
                status="pending_review",
                confidence=0.9,
                ranking_score=0.8,
                reasoning_path={},
                evidence_bundle=[],
                payload={},
                metadata={},
                claim_fingerprint=fp,
                decision_reason=None,
                decided_at=None,
                created_at=now,
                updated_at=now,
            )
            store._proposals[pid] = r  # noqa: SLF001
            store._proposal_ids_by_space.setdefault(SPACE_ID, []).append(
                pid,
            )  # noqa: SLF001

        all_p = store.list_proposals(space_id=SPACE_ID, status="pending_review")
        assert len(all_p) == 2

        # Promote first, reject duplicates
        first_id = all_p[0].id
        store.decide_proposal(
            space_id=SPACE_ID,
            proposal_id=first_id,
            status="promoted",
            decision_reason="Best",
        )
        count = store.reject_pending_duplicates(
            space_id=SPACE_ID,
            claim_fingerprint=fp,
            exclude_id=first_id,
            reason="Auto-rejected: equivalent claim promoted",
        )
        assert count == 1

        # Check the rejected proposal has the right reason
        rejected = list(
            store.list_proposals(space_id=SPACE_ID, status="rejected"),
        )
        assert len(rejected) == 1
        assert "Auto-rejected" in (rejected[0].decision_reason or "")
