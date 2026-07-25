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


def _action(approval_key: str) -> HarnessApprovalAction:
    return HarnessApprovalAction(
        approval_key=approval_key,
        title=f"Approve {approval_key}",
        risk_level="medium",
        target_type="claim",
        target_id=str(uuid4()),
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
