"""Re-proposing a run's intent must not erase decisions already made.

upsert_intent used to delete every approval for the run and recreate them all
as pending, so a second POST of the intent silently destroyed the written
reasons -- and now the reviewer identities -- attached to approvals a person had
already decided.  The durable store is covered alongside this in
test_sqlalchemy_stores.py, since that is the one production loses data through.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

import pytest
from artana_evidence_api.approval_store import (
    HarnessApprovalAction,
    HarnessApprovalStore,
)
from artana_evidence_api.types.review_actor import ReviewActor

_REVIEWER: Final = ReviewActor(
    user_id="66666666-6666-6666-6666-666666666666",
    email="intent-reviewer@example.com",
)


def _action(
    approval_key: str,
    *,
    target_id: str | None = None,
    title: str | None = None,
) -> HarnessApprovalAction:
    """Return one proposed action.

    The target defaults to a value derived from the key rather than a fresh
    UUID: re-proposing the *same* action has to produce an identical action, or
    a test that means "the plan did not change" is silently testing the
    opposite.
    """
    return HarnessApprovalAction(
        approval_key=approval_key,
        title=title or f"Approve {approval_key}",
        risk_level="medium",
        target_type="claim",
        target_id=target_id or f"target-for-{approval_key}",
        requires_approval=True,
        metadata={},
    )


def _upsert(store: HarnessApprovalStore, *, space_id: str, run_id: str) -> None:
    store.upsert_intent(
        space_id=space_id,
        run_id=run_id,
        summary="Review the pending graph mutation.",
        proposed_actions=(_action("decided-key"), _action("pending-key")),
        metadata={},
    )


@pytest.fixture
def store() -> HarnessApprovalStore:
    return HarnessApprovalStore()


def test_reupserting_intent_keeps_a_decided_approval_and_its_reason(
    store: HarnessApprovalStore,
) -> None:
    space_id, run_id = str(uuid4()), str(uuid4())
    _upsert(store, space_id=space_id, run_id=run_id)
    store.decide_approval(
        space_id=space_id,
        run_id=run_id,
        approval_key="decided-key",
        status="approved",
        decision_reason="Checked against the source; safe to write.",
        decided_by=_REVIEWER,
    )

    _upsert(store, space_id=space_id, run_id=run_id)

    approvals = {
        approval.approval_key: approval
        for approval in store.list_approvals(space_id=space_id, run_id=run_id)
    }
    decided = approvals["decided-key"]
    assert decided.status == "approved"
    assert decided.decision_reason == "Checked against the source; safe to write."
    assert decided.decided_by == _REVIEWER


def test_reupserting_intent_still_refreshes_a_pending_approval(
    store: HarnessApprovalStore,
) -> None:
    space_id, run_id = str(uuid4()), str(uuid4())
    _upsert(store, space_id=space_id, run_id=run_id)
    _upsert(store, space_id=space_id, run_id=run_id)

    approvals = {
        approval.approval_key: approval
        for approval in store.list_approvals(space_id=space_id, run_id=run_id)
    }
    assert approvals["pending-key"].status == "pending"
    assert approvals["pending-key"].decision_reason is None


def test_a_decided_approval_survives_being_dropped_from_the_intent(
    store: HarnessApprovalStore,
) -> None:
    """Dropping the action from the plan must not delete the decision either."""
    space_id, run_id = str(uuid4()), str(uuid4())
    _upsert(store, space_id=space_id, run_id=run_id)
    store.decide_approval(
        space_id=space_id,
        run_id=run_id,
        approval_key="decided-key",
        status="rejected",
        decision_reason="Too risky for now.",
        decided_by=_REVIEWER,
    )

    store.upsert_intent(
        space_id=space_id,
        run_id=run_id,
        summary="A narrower plan.",
        proposed_actions=(_action("pending-key"),),
        metadata={},
    )

    approvals = {
        approval.approval_key: approval
        for approval in store.list_approvals(space_id=space_id, run_id=run_id)
    }
    assert approvals["decided-key"].status == "rejected"
    assert approvals["decided-key"].decision_reason == "Too risky for now."


def test_a_changed_action_reopens_the_approval_instead_of_reusing_the_decision(
    store: HarnessApprovalStore,
) -> None:
    """A decision describes one action, not one approval key.

    ``uq_harness_run_approvals_run_id_approval_key`` allows exactly one row per
    (run, key), so keeping the old decided row when a re-proposed action reuses
    the key with different content leaves the run with nothing pending -- it
    proceeds on a human decision that was made about a different action.
    """
    space_id, run_id = str(uuid4()), str(uuid4())
    _upsert(store, space_id=space_id, run_id=run_id)
    store.decide_approval(
        space_id=space_id,
        run_id=run_id,
        approval_key="decided-key",
        status="approved",
        decision_reason="Checked against the source; safe to write.",
        decided_by=_REVIEWER,
    )

    store.upsert_intent(
        space_id=space_id,
        run_id=run_id,
        summary="Now writing somewhere else.",
        proposed_actions=(
            _action(
                "decided-key",
                target_id="a-different-claim",
                title="Approve a different claim",
            ),
        ),
        metadata={},
    )

    reopened = next(
        approval
        for approval in store.list_approvals(space_id=space_id, run_id=run_id)
        if approval.approval_key == "decided-key"
    )
    assert reopened.status == "pending"
    assert reopened.decision_reason is None
    assert reopened.decided_by is None
    assert reopened.target_id == "a-different-claim"
    assert reopened.title == "Approve a different claim"
    assert reopened.metadata["superseded_decisions"] == [
        {
            "status": "approved",
            "decision_reason": "Checked against the source; safe to write.",
            "decided_by_user_id": _REVIEWER.user_id,
            "decided_by_email": _REVIEWER.email,
            "decided_at": reopened.metadata["superseded_decisions"][0]["decided_at"],
            "title": "Approve decided-key",
            "risk_level": "medium",
            "target_type": "claim",
            "target_id": "target-for-decided-key",
        },
    ]


def test_a_superseded_decision_survives_a_later_unchanged_re_proposal(
    store: HarnessApprovalStore,
) -> None:
    """Carrying the decision forward once is not enough.

    A reopened approval is pending, and pending rows are replaced wholesale on
    every re-proposal -- so the next intent upsert would drop the trail that the
    supersede was there to keep, without anyone having decided anything.
    """
    space_id, run_id = str(uuid4()), str(uuid4())
    _upsert(store, space_id=space_id, run_id=run_id)
    store.decide_approval(
        space_id=space_id,
        run_id=run_id,
        approval_key="decided-key",
        status="rejected",
        decision_reason="Writes to the wrong claim.",
        decided_by=_REVIEWER,
    )
    changed = (_action("decided-key", target_id="a-different-claim"),)

    store.upsert_intent(
        space_id=space_id,
        run_id=run_id,
        summary="Replanned.",
        proposed_actions=changed,
        metadata={},
    )
    store.upsert_intent(
        space_id=space_id,
        run_id=run_id,
        summary="Replanned, unchanged.",
        proposed_actions=changed,
        metadata={},
    )

    reopened = store.list_approvals(space_id=space_id, run_id=run_id)[0]
    assert reopened.status == "pending"
    history = reopened.metadata["superseded_decisions"]
    assert isinstance(history, list)
    assert [entry["decision_reason"] for entry in history] == [
        "Writes to the wrong claim.",
    ]


def test_superseding_the_same_key_twice_keeps_both_written_reasons(
    store: HarnessApprovalStore,
) -> None:
    """The point of carrying the decision forward is not losing what a person wrote."""
    space_id, run_id = str(uuid4()), str(uuid4())
    for index, reason in enumerate(("First look; approved.", "Second look; rejected.")):
        store.upsert_intent(
            space_id=space_id,
            run_id=run_id,
            summary="Replanned.",
            proposed_actions=(_action("decided-key", target_id=f"claim-{index}"),),
            metadata={},
        )
        store.decide_approval(
            space_id=space_id,
            run_id=run_id,
            approval_key="decided-key",
            status="approved" if index == 0 else "rejected",
            decision_reason=reason,
            decided_by=_REVIEWER,
        )

    store.upsert_intent(
        space_id=space_id,
        run_id=run_id,
        summary="Replanned again.",
        proposed_actions=(_action("decided-key", target_id="claim-2"),),
        metadata={},
    )

    reopened = store.list_approvals(space_id=space_id, run_id=run_id)[0]
    history = reopened.metadata["superseded_decisions"]
    assert isinstance(history, list)
    assert [entry["decision_reason"] for entry in history] == [
        "First look; approved.",
        "Second look; rejected.",
    ]
    assert [entry["status"] for entry in history] == ["approved", "rejected"]
