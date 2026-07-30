"""Unit tests for proposal-level deduplication via claim fingerprints."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.proposal_store import (
    IDENTITY_PENDING_STATUS,
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


class TestSameDocumentRederivation:
    """A fingerprint collision means different things across and within documents.

    Two documents asserting the same claim are two independent sources, and
    losing either destroys evidence.  One document extracted twice is a single
    observation arriving again, and retaining it would grow the table on every
    re-extraction.  `document_id` is what separates the two cases.
    """

    def test_same_document_reextraction_is_deduplicated(self) -> None:
        store = HarnessProposalStore()
        draft = replace(_make_draft(), document_id="doc-abc")

        first = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft,),
        )
        again = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_B,
            proposals=(draft,),
        )

        assert len(first) == 1
        assert again == [], "re-extracting one document must not accumulate rows"
        assert len(store.list_proposals(space_id=SPACE_ID)) == 1

    def test_second_document_with_the_same_claim_is_retained(self) -> None:
        store = HarnessProposalStore()
        first_document = replace(_make_draft(), document_id="doc-abc")
        second_document = replace(_make_draft(), document_id="doc-xyz")

        store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(first_document,),
        )
        corroborating = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_B,
            proposals=(second_document,),
        )

        assert len(corroborating) == 1, "a second source must never be dropped"
        assert corroborating[0].status == IDENTITY_PENDING_STATUS
        assert corroborating[0].document_id == "doc-xyz"
        assert len(store.list_proposals(space_id=SPACE_ID)) == 2

    def test_two_drafts_of_one_pass_over_one_document_are_both_kept(self) -> None:
        """One pass emitting two colliding claims is not a re-extraction.

        The re-derivation rule reads a shared document_id as "this observation
        already arrived".  That is only true against an already-stored proposal.
        Within a single call the two drafts were produced together, each with
        its own evidence, so dropping the second deletes evidence that the first
        does not carry -- and it would do so with no row and no log.
        """

        store = HarnessProposalStore()
        first = replace(_make_draft(source_key="doc:1"), document_id="doc-abc")
        second = replace(_make_draft(source_key="doc:2"), document_id="doc-abc")

        created = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(first, second),
        )

        assert len(created) == 2, "nothing may be dropped"
        by_source_key = {record.source_key: record for record in created}
        assert by_source_key["doc:1"].status == "pending_review"
        parked = by_source_key["doc:2"]
        assert parked.status == IDENTITY_PENDING_STATUS
        assert parked.claim_fingerprint == first.claim_fingerprint
        assert parked.decision_reason is not None
        assert "the same document" in parked.decision_reason
        assert len(store.list_proposals(space_id=SPACE_ID)) == 2

    def test_unknown_provenance_is_retained_rather_than_assumed_duplicate(
        self,
    ) -> None:
        """Absent document ids could be one source or two; keep the record."""

        store = HarnessProposalStore()
        draft = _make_draft()

        store.create_proposals(space_id=SPACE_ID, run_id=RUN_A, proposals=(draft,))
        unknown = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_B,
            proposals=(draft,),
        )

        assert len(unknown) == 1
        assert unknown[0].status == IDENTITY_PENDING_STATUS


class TestCreationTimeDedup:
    """Proposals with matching fingerprint are skipped at creation time."""

    def test_duplicate_proposal_retained_as_identity_pending(self) -> None:
        """ART-DATA-001: a collision is retained, not dropped.

        The duplicate is a second independent observation. Whether it is the
        same assertion needs an identity model that does not exist yet, so it
        is held outside the review queue rather than discarded.
        """
        store = HarnessProposalStore()
        draft = _make_draft()
        # Create first
        created = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft,),
        )
        assert len(created) == 1
        assert created[0].status == "pending_review"

        duplicates = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft,),
        )

        assert len(duplicates) == 1, "the second observation must survive"
        assert duplicates[0].status == IDENTITY_PENDING_STATUS
        assert duplicates[0].decision_reason is not None
        assert created[0].id in duplicates[0].decision_reason

        # Both are queryable; only the first is actionable.
        all_proposals = store.list_proposals(space_id=SPACE_ID)
        assert len(all_proposals) == 2
        actionable = [p for p in all_proposals if p.status == "pending_review"]
        assert len(actionable) == 1

    def test_duplicate_proposal_retained_when_original_promoted(self) -> None:
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
            decided_by=None,
        )
        # Try to create same claim — should be skipped (status=promoted)
        duplicates = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_B,
            proposals=(draft,),
        )
        assert len(duplicates) == 1
        assert duplicates[0].status == IDENTITY_PENDING_STATUS

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
            decided_by=None,
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

    def test_cross_run_collision_is_retained(self) -> None:
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
        assert len(duplicates) == 1
        assert duplicates[0].status == IDENTITY_PENDING_STATUS

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
            decided_by=None,
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
        fp = compute_claim_fingerprint("A", "ASSOCIATED_WITH", "B")
        # Create two proposals with same fingerprint by inserting directly
        draft1 = _make_draft(
            subject="A",
            relation="ASSOCIATED_WITH",
            obj="B",
            source_key="s1",
        )
        p1 = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(draft1,),
        )
        assert len(p1) == 1
        # Second would be blocked by dedup. Force-insert by clearing fingerprint
        # then manually set it. We'll just test reject_pending_duplicates logic.
        # Create a different proposal first
        draft_diff = _make_draft(
            subject="X",
            relation="ASSOCIATED_WITH",
            obj="Y",
            source_key="s2",
        )
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
            decided_by=None,
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
            decided_by=None,
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


class TestBulkRejectRefusesAnAbsentFingerprint:
    """No fingerprint must mean "reject nothing", not "reject the unfingerprinted".

    Both stores matched every fingerprint-less pending proposal when handed no
    fingerprint -- the in-memory one because ``None == None``, the durable one
    because SQLAlchemy renders ``column == None`` as ``IS NULL`` rather than as
    a comparison that never matches.  They agreed on the wrong answer, which is
    why nobody caught it: a single call rejected unrelated evidence in bulk and
    stamped each row with a reason saying it duplicated something.
    """

    def test_a_null_fingerprint_is_refused_before_anything_is_rejected(
        self,
    ) -> None:
        store = HarnessProposalStore()
        created = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(
                _make_draft(source_key="no-fp-1", fingerprint=False),
                _make_draft(source_key="no-fp-2", fingerprint=False),
                _make_draft(source_key="no-fp-3", fingerprint=False),
            ),
        )
        assert len(created) == 3

        with pytest.raises(ValueError, match="requires a non-empty"):
            store.reject_pending_duplicates(
                space_id=SPACE_ID,
                claim_fingerprint=cast("str", None),
                exclude_id=created[0].id,
                reason="Auto-rejected: equivalent claim promoted",
            )

        assert [
            record.status
            for record in store.list_proposals(space_id=SPACE_ID)
        ] == ["pending_review"] * 3, "nothing may be rejected"

    def test_a_blank_fingerprint_is_refused_too(self) -> None:
        store = HarnessProposalStore()
        created = store.create_proposals(
            space_id=SPACE_ID,
            run_id=RUN_A,
            proposals=(_make_draft(source_key="no-fp-1", fingerprint=False),),
        )

        with pytest.raises(ValueError, match="requires a non-empty"):
            store.reject_pending_duplicates(
                space_id=SPACE_ID,
                claim_fingerprint="   ",
                exclude_id=created[0].id,
                reason="Auto-rejected",
            )
