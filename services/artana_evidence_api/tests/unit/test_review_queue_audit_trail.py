"""The reviewer-facing audit trail: who decided what, and can anyone read it.

These cover the promoted-and-rejected trail that issue #85 asked for, and the
attribution that makes it an audit trail rather than a list of anonymous
outcomes.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

from artana_evidence_api.app import create_app
from artana_evidence_api.approval_store import (
    HarnessApprovalAction,
    HarnessApprovalStore,
)
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_proposal_store,
    get_research_space_store,
    get_review_item_store,
    get_run_registry,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.review_item_store import (
    HarnessReviewItemDraft,
    HarnessReviewItemStore,
)
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.tests.support import FakeKernelRuntime
from fastapi.testclient import TestClient

_TEST_USER_ID: Final[str] = "22222222-2222-2222-2222-222222222222"
_TEST_USER_EMAIL: Final[str] = "audit-trail-reviewer@example.com"
_HTTP_OK: Final[int] = 200
_HTTP_BAD_REQUEST: Final[int] = 400
_HTTP_NOT_FOUND: Final[int] = 404


class _StubExecutionServices:
    def __init__(self) -> None:
        self.runtime = FakeKernelRuntime()


class _StubGraphApiGateway:
    def close(self) -> None:
        return None


def _auth_headers(*, role: str = "researcher") -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": role,
    }


class _Fixture:
    """One wired app plus the in-memory stores backing it."""

    def __init__(self) -> None:
        app = create_app()
        self.approval_store = HarnessApprovalStore()
        self.proposal_store = HarnessProposalStore()
        self.review_item_store = HarnessReviewItemStore()
        self.research_space_store = HarnessResearchSpaceStore()
        self.run_registry = HarnessRunRegistry()
        artifact_store = HarnessArtifactStore()
        execution_services = _StubExecutionServices()

        app.dependency_overrides[get_approval_store] = lambda: self.approval_store
        app.dependency_overrides[get_artifact_store] = lambda: artifact_store
        app.dependency_overrides[get_graph_api_gateway] = lambda: _StubGraphApiGateway()
        app.dependency_overrides[get_harness_execution_services] = (
            lambda: execution_services
        )
        app.dependency_overrides[get_proposal_store] = lambda: self.proposal_store
        app.dependency_overrides[get_research_space_store] = (
            lambda: self.research_space_store
        )
        app.dependency_overrides[get_review_item_store] = lambda: self.review_item_store
        app.dependency_overrides[get_run_registry] = lambda: self.run_registry

        self.client = TestClient(app)
        self.space_id = self.research_space_store.create_space(
            owner_id=_TEST_USER_ID,
            name="Audit Trail Space",
            description="Used for reviewer audit-trail tests.",
        ).id
        self.run_id = self.run_registry.create_run(
            space_id=self.space_id,
            harness_id="graph-search",
            title="Audit trail test run",
            input_payload={"objective": "audit trail"},
            graph_service_status="ok",
            graph_service_version="tests",
        ).id

    def add_proposal(self, *, source_key: str) -> str:
        created = self.proposal_store.create_proposals(
            space_id=self.space_id,
            run_id=self.run_id,
            proposals=(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="document_extraction",
                    source_key=source_key,
                    title=f"Candidate claim {source_key}",
                    summary="Synthetic candidate claim",
                    confidence=0.8,
                    ranking_score=0.9,
                    reasoning_path={"source": "unit-test"},
                    evidence_bundle=[],
                    payload={"proposed_claim_type": "ASSOCIATED_WITH"},
                    metadata={"source": "unit-test"},
                ),
            ),
        )
        return created[0].id

    def add_review_item(self, *, source_key: str) -> str:
        created = self.review_item_store.create_review_items(
            space_id=self.space_id,
            run_id=self.run_id,
            review_items=(
                HarnessReviewItemDraft(
                    review_type="phenotype_claim_review",
                    source_family="document_extraction",
                    source_kind="document_extraction",
                    source_key=source_key,
                    title="Review phenotype link",
                    summary="developmental delay",
                    priority="medium",
                    confidence=0.6,
                    ranking_score=0.6,
                    evidence_bundle=[],
                    payload={"phenotype_span": "developmental delay"},
                    metadata={"source": "unit-test"},
                ),
            ),
        )
        return created[0].id

    def add_approval(self, *, approval_key: str) -> None:
        self.approval_store.upsert_intent(
            space_id=self.space_id,
            run_id=self.run_id,
            summary="Review the pending graph mutation.",
            proposed_actions=(
                HarnessApprovalAction(
                    approval_key=approval_key,
                    title="Approve claim write",
                    risk_level="medium",
                    target_type="claim",
                    target_id=str(uuid4()),
                    requires_approval=True,
                    metadata={"summary": "Needs curator review."},
                ),
            ),
            metadata={},
        )

    def act(self, *, item_id: str, action: str, reason: str) -> object:
        return self.client.post(
            f"/v1/spaces/{self.space_id}/review-queue/{item_id}/actions",
            json={"action": action, "reason": reason},
            headers=_auth_headers(),
        )

    def queue(self, **params: str) -> dict[str, object]:
        response = self.client.get(
            f"/v1/spaces/{self.space_id}/review-queue",
            params=params,
            headers=_auth_headers(),
        )
        assert response.status_code == _HTTP_OK, response.text
        return response.json()


def test_rejecting_a_proposal_records_the_authenticated_reviewer() -> None:
    fixture = _Fixture()
    proposal_id = fixture.add_proposal(source_key="doc:claim:reject")

    response = fixture.act(
        item_id=f"proposal:{proposal_id}",
        action="reject",
        reason="Hallucinated relation; not in the cited passage.",
    )

    assert response.status_code == _HTTP_OK, response.text
    body = response.json()
    assert body["status"] == "rejected"
    assert body["decision_reason"] == "Hallucinated relation; not in the cited passage."
    assert body["decided_by"] == {
        "user_id": _TEST_USER_ID,
        "email": _TEST_USER_EMAIL,
    }

    stored = fixture.proposal_store.get_proposal(
        space_id=fixture.space_id,
        proposal_id=proposal_id,
    )
    assert stored is not None
    assert stored.decided_by is not None
    assert stored.decided_by.email == _TEST_USER_EMAIL


def test_review_item_and_approval_decisions_record_the_reviewer() -> None:
    fixture = _Fixture()
    review_item_id = fixture.add_review_item(source_key="doc:review:dismiss")
    fixture.add_approval(approval_key="approval-audit-1")

    dismissed = fixture.act(
        item_id=f"review_item:{review_item_id}",
        action="dismiss",
        reason="Already covered by an existing claim.",
    )
    approved = fixture.act(
        item_id=f"approval:{fixture.run_id}:approval-audit-1",
        action="approve",
        reason="Checked against the source; safe to write.",
    )

    assert dismissed.status_code == _HTTP_OK, dismissed.text
    assert approved.status_code == _HTTP_OK, approved.text
    assert dismissed.json()["decided_by"]["email"] == _TEST_USER_EMAIL
    assert approved.json()["decided_by"]["email"] == _TEST_USER_EMAIL


def test_status_decided_returns_every_family_of_decision_in_one_request() -> None:
    fixture = _Fixture()
    rejected_id = fixture.add_proposal(source_key="doc:claim:rejected")
    dismissed_id = fixture.add_review_item(source_key="doc:review:dismissed")
    fixture.add_approval(approval_key="approval-decided-1")

    fixture.act(
        item_id=f"proposal:{rejected_id}",
        action="reject",
        reason="Not supported by the passage.",
    )
    fixture.act(
        item_id=f"review_item:{dismissed_id}",
        action="dismiss",
        reason="Duplicate of an existing review.",
    )
    fixture.act(
        item_id=f"approval:{fixture.run_id}:approval-decided-1",
        action="reject",
        reason="Too risky for now.",
    )

    body = fixture.queue(status="decided")

    assert body["total"] == 3
    returned = {item["id"] for item in body["items"]}
    assert returned == {
        f"proposal:{rejected_id}",
        f"review_item:{dismissed_id}",
        f"approval:{fixture.run_id}:approval-decided-1",
    }
    assert all(item["decision_reason"] for item in body["items"])
    assert all(
        item["decided_by"]["email"] == _TEST_USER_EMAIL for item in body["items"]
    )


def test_status_accepts_a_comma_separated_slice_of_the_trail() -> None:
    fixture = _Fixture()
    rejected_id = fixture.add_proposal(source_key="doc:claim:rejected")
    pending_id = fixture.add_proposal(source_key="doc:claim:pending")
    fixture.act(
        item_id=f"proposal:{rejected_id}",
        action="reject",
        reason="Not supported by the passage.",
    )

    body = fixture.queue(status="pending_review,rejected")

    returned = {item["id"] for item in body["items"]}
    assert returned == {f"proposal:{rejected_id}", f"proposal:{pending_id}"}


def test_status_defaults_to_pending_work() -> None:
    fixture = _Fixture()
    pending_id = fixture.add_proposal(source_key="doc:claim:pending")
    decided_id = fixture.add_proposal(source_key="doc:claim:decided")
    fixture.act(
        item_id=f"proposal:{decided_id}",
        action="reject",
        reason="Not supported by the passage.",
    )

    body = fixture.queue()

    assert [item["id"] for item in body["items"]] == [f"proposal:{pending_id}"]


def test_legacy_status_filter_spelling_still_works() -> None:
    fixture = _Fixture()
    rejected_id = fixture.add_proposal(source_key="doc:claim:rejected")
    fixture.act(
        item_id=f"proposal:{rejected_id}",
        action="reject",
        reason="Not supported by the passage.",
    )

    body = fixture.queue(status_filter="rejected")

    assert [item["id"] for item in body["items"]] == [f"proposal:{rejected_id}"]


def test_a_group_name_means_the_same_thing_alone_and_in_a_list() -> None:
    """'pending' is both a group name and the approval store's own status.

    Resolving it per position would silently drop every pending proposal from
    a list query while still returning 200.
    """
    fixture = _Fixture()
    pending_proposal = fixture.add_proposal(source_key="doc:claim:pending")
    pending_review_item = fixture.add_review_item(source_key="doc:review:pending")
    fixture.add_approval(approval_key="approval-group-1")
    rejected_id = fixture.add_proposal(source_key="doc:claim:rejected")
    fixture.act(
        item_id=f"proposal:{rejected_id}",
        action="reject",
        reason="Not supported by the passage.",
    )

    alone = {item["id"] for item in fixture.queue(status="pending")["items"]}
    combined = {item["id"] for item in fixture.queue(status="pending,rejected")["items"]}

    assert alone == {
        f"proposal:{pending_proposal}",
        f"review_item:{pending_review_item}",
        f"approval:{fixture.run_id}:approval-group-1",
    }
    assert combined == alone | {f"proposal:{rejected_id}"}


def test_a_group_name_can_be_combined_with_a_literal_status() -> None:
    fixture = _Fixture()
    rejected_id = fixture.add_proposal(source_key="doc:claim:rejected")
    fixture.act(
        item_id=f"proposal:{rejected_id}",
        action="reject",
        reason="Not supported by the passage.",
    )

    body = fixture.queue(status="decided,promoted")

    assert [item["id"] for item in body["items"]] == [f"proposal:{rejected_id}"]


def test_repeating_the_status_parameter_unions_rather_than_overwrites() -> None:
    fixture = _Fixture()
    pending_id = fixture.add_proposal(source_key="doc:claim:pending")
    rejected_id = fixture.add_proposal(source_key="doc:claim:rejected")
    fixture.act(
        item_id=f"proposal:{rejected_id}",
        action="reject",
        reason="Not supported by the passage.",
    )

    response = fixture.client.get(
        f"/v1/spaces/{fixture.space_id}/review-queue",
        params=[("status", "pending_review"), ("status", "rejected")],
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_OK, response.text
    returned = {item["id"] for item in response.json()["items"]}
    assert returned == {f"proposal:{pending_id}", f"proposal:{rejected_id}"}


def test_an_unknown_status_in_any_position_is_rejected() -> None:
    """A scalar parameter would keep only the last value, so a typo in an
    earlier occurrence would never reach validation."""
    fixture = _Fixture()

    for params in (
        [("status", "rejected"), ("status", "bogus")],
        [("status", "bogus"), ("status", "rejected")],
    ):
        response = fixture.client.get(
            f"/v1/spaces/{fixture.space_id}/review-queue",
            params=params,
            headers=_auth_headers(),
        )
        assert response.status_code == _HTTP_BAD_REQUEST, f"{params}: {response.text}"
        assert "bogus" in response.json()["detail"]


def test_a_status_that_names_nothing_is_rejected_rather_than_defaulted() -> None:
    fixture = _Fixture()
    fixture.add_proposal(source_key="doc:claim:pending")

    for value in ("", "   ", ",", " , , "):
        response = fixture.client.get(
            f"/v1/spaces/{fixture.space_id}/review-queue",
            params={"status": value},
            headers=_auth_headers(),
        )
        assert response.status_code == _HTTP_BAD_REQUEST, f"{value!r}: {response.text}"


def test_repeated_identical_values_do_not_trip_the_value_limit() -> None:
    fixture = _Fixture()
    rejected_id = fixture.add_proposal(source_key="doc:claim:rejected")
    fixture.act(
        item_id=f"proposal:{rejected_id}",
        action="reject",
        reason="Not supported by the passage.",
    )

    body = fixture.queue(status="rejected,rejected,rejected,rejected,rejected")

    assert [item["id"] for item in body["items"]] == [f"proposal:{rejected_id}"]


def test_unknown_status_is_a_bad_request_not_an_empty_success() -> None:
    fixture = _Fixture()

    response = fixture.client.get(
        f"/v1/spaces/{fixture.space_id}/review-queue",
        params={"status": "promotted"},
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_BAD_REQUEST, response.text
    assert "promotted" in response.json()["detail"]


def test_unknown_order_by_is_a_bad_request() -> None:
    fixture = _Fixture()

    response = fixture.client.get(
        f"/v1/spaces/{fixture.space_id}/review-queue",
        params={"order_by": "whenever"},
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_BAD_REQUEST, response.text


def test_order_by_decided_at_sorts_the_trail_newest_first() -> None:
    fixture = _Fixture()
    first_id = fixture.add_proposal(source_key="doc:claim:first")
    second_id = fixture.add_proposal(source_key="doc:claim:second")
    fixture.act(
        item_id=f"proposal:{first_id}",
        action="reject",
        reason="Decided first.",
    )
    fixture.act(
        item_id=f"proposal:{second_id}",
        action="reject",
        reason="Decided second.",
    )

    body = fixture.queue(status="decided", order_by="decided_at")

    assert [item["id"] for item in body["items"]] == [
        f"proposal:{second_id}",
        f"proposal:{first_id}",
    ]


def test_serialized_timestamps_are_explicitly_utc() -> None:
    fixture = _Fixture()
    proposal_id = fixture.add_proposal(source_key="doc:claim:timestamps")
    fixture.add_approval(approval_key="approval-timestamps-1")
    fixture.act(
        item_id=f"proposal:{proposal_id}",
        action="reject",
        reason="Not supported by the passage.",
    )
    fixture.act(
        item_id=f"approval:{fixture.run_id}:approval-timestamps-1",
        action="reject",
        reason="Too risky for now.",
    )

    body = fixture.queue(status="decided")

    assert len(body["items"]) == 2
    for item in body["items"]:
        assert item["created_at"].endswith("+00:00")
        assert item["updated_at"].endswith("+00:00")
        assert item["decided_at"].endswith("+00:00")


def test_malformed_queue_item_id_is_not_found_rather_than_a_server_error() -> None:
    fixture = _Fixture()

    for item_id in (
        "proposal:abc",
        "review_item:abc",
        f"approval:notauuid:{uuid4()}",
        "nonsense",
    ):
        read = fixture.client.get(
            f"/v1/spaces/{fixture.space_id}/review-queue/{item_id}",
            headers=_auth_headers(),
        )
        assert read.status_code == _HTTP_NOT_FOUND, f"{item_id}: {read.text}"

        written = fixture.act(
            item_id=item_id,
            action="reject",
            reason="Should never be applied.",
        )
        assert written.status_code == _HTTP_NOT_FOUND, f"{item_id}: {written.text}"
