"""A parked proposal must not claim someone decided it.

A cross-document fingerprint collision is held in identity_pending
(ART-DATA-001) and cannot be acted on until its identity is adjudicated. Every
decision route reported that as "is already decided with status
'identity_pending'", which sends a reviewer looking for a decision and a
decider that do not exist. The conflict is real; the explanation was not.

These tests pin the reporting, not a new capability: a parked proposal still
cannot be promoted or rejected.
"""

from __future__ import annotations

from typing import Final
from uuid import uuid4

from artana_evidence_api.app import create_app
from artana_evidence_api.approval_store import HarnessApprovalStore
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
    IDENTITY_PENDING_STATUS,
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.review_item_store import HarnessReviewItemStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.tests.support import FakeKernelRuntime
from fastapi.testclient import TestClient

_TEST_USER_ID: Final[str] = "77777777-7777-7777-7777-777777777777"
_TEST_USER_EMAIL: Final[str] = "parked-reviewer@example.com"
_FINGERPRINT: Final[str] = "parkedfingerprint00000000000001"
_HTTP_OK: Final[int] = 200
_HTTP_CONFLICT: Final[int] = 409


class _StubExecutionServices:
    def __init__(self) -> None:
        self.runtime = FakeKernelRuntime()


class _StubGraphApiGateway:
    def close(self) -> None:
        return None


def _auth_headers() -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": "researcher",
    }


class _Fixture:
    def __init__(self) -> None:
        app = create_app()
        self.proposal_store = HarnessProposalStore()
        self.space_store = HarnessResearchSpaceStore()
        self.run_registry = HarnessRunRegistry()

        app.dependency_overrides[get_approval_store] = lambda: HarnessApprovalStore()
        app.dependency_overrides[get_artifact_store] = lambda: HarnessArtifactStore()
        app.dependency_overrides[get_graph_api_gateway] = lambda: _StubGraphApiGateway()
        app.dependency_overrides[get_harness_execution_services] = (
            lambda: _StubExecutionServices()
        )
        app.dependency_overrides[get_proposal_store] = lambda: self.proposal_store
        app.dependency_overrides[get_research_space_store] = lambda: self.space_store
        app.dependency_overrides[get_review_item_store] = (
            lambda: HarnessReviewItemStore()
        )
        app.dependency_overrides[get_run_registry] = lambda: self.run_registry

        self.client = TestClient(app)
        self.space_id = self.space_store.create_space(
            owner_id=_TEST_USER_ID,
            name="Parked Proposal Space",
            description="Used for identity-pending reporting tests.",
        ).id
        self.run_id = self.run_registry.create_run(
            space_id=self.space_id,
            harness_id="graph-search",
            title="Parked proposal run",
            input_payload={},
            graph_service_status="ok",
            graph_service_version="tests",
        ).id

    def draft(self, *, document_id: str) -> HarnessProposalDraft:
        return HarnessProposalDraft(
            proposal_type="candidate_claim",
            source_kind="document_extraction",
            source_key=f"doc:{document_id}:claim",
            document_id=document_id,
            title="Candidate claim",
            summary="Synthetic candidate claim",
            confidence=0.8,
            ranking_score=0.9,
            reasoning_path={},
            evidence_bundle=[],
            payload={"proposed_claim_type": "ASSOCIATED_WITH"},
            metadata={},
            claim_fingerprint=_FINGERPRINT,
        )

    def park_a_second_observation(self) -> str:
        """Create the same fingerprint from two documents, parking the second."""
        self.proposal_store.create_proposals(
            space_id=self.space_id,
            run_id=self.run_id,
            proposals=(self.draft(document_id=str(uuid4())),),
        )
        created = self.proposal_store.create_proposals(
            space_id=self.space_id,
            run_id=self.run_id,
            proposals=(self.draft(document_id=str(uuid4())),),
        )
        parked = created[0]
        assert parked.status == IDENTITY_PENDING_STATUS, parked.status
        return parked.id


def test_a_parked_proposal_is_not_reported_as_decided() -> None:
    fixture = _Fixture()
    parked_id = fixture.park_a_second_observation()

    for path in (
        f"/v1/spaces/{fixture.space_id}/proposals/{parked_id}/promote",
        f"/v1/spaces/{fixture.space_id}/proposals/{parked_id}/reject",
    ):
        response = fixture.client.post(
            path,
            json={"reason": "probe"},
            headers=_auth_headers(),
        )
        assert response.status_code == _HTTP_CONFLICT, response.text
        detail = response.json()["detail"]
        assert "already decided" not in detail, detail
        assert "parked awaiting identity adjudication" in detail
        assert "ART-DATA-001" in detail


def test_the_queue_action_route_reports_it_the_same_way() -> None:
    fixture = _Fixture()
    parked_id = fixture.park_a_second_observation()

    response = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/review-queue/proposal:{parked_id}/actions",
        json={"action": "reject", "reason": "probe"},
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_CONFLICT, response.text
    assert "parked awaiting identity adjudication" in response.json()["detail"]


def test_a_genuinely_decided_proposal_still_says_so() -> None:
    fixture = _Fixture()
    created = fixture.proposal_store.create_proposals(
        space_id=fixture.space_id,
        run_id=fixture.run_id,
        proposals=(fixture.draft(document_id=str(uuid4())),),
    )
    proposal_id = created[0].id
    first = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/proposals/{proposal_id}/reject",
        json={"reason": "Not supported by the passage."},
        headers=_auth_headers(),
    )
    assert first.status_code == _HTTP_OK, first.text

    second = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/proposals/{proposal_id}/reject",
        json={"reason": "Again."},
        headers=_auth_headers(),
    )

    assert second.status_code == _HTTP_CONFLICT, second.text
    assert "already decided with status 'rejected'" in second.json()["detail"]


def test_parked_proposals_are_reachable_by_name_and_by_group() -> None:
    fixture = _Fixture()
    parked_id = fixture.park_a_second_observation()

    for value in ("parked", "identity_pending"):
        response = fixture.client.get(
            f"/v1/spaces/{fixture.space_id}/review-queue",
            params={"status": value},
            headers=_auth_headers(),
        )
        assert response.status_code == _HTTP_OK, response.text
        body = response.json()
        assert [item["id"] for item in body["items"]] == [f"proposal:{parked_id}"]
        assert body["items"][0]["available_actions"] == [
            "resolve_as_duplicate",
            "release_as_distinct",
        ]
        assert body["items"][0]["decided_by"] is None


def test_a_parked_proposal_can_be_resolved_as_a_duplicate() -> None:
    """"These are the same fact" must be sayable, and must record what it names."""
    fixture = _Fixture()
    parked_id = fixture.park_a_second_observation()
    counterpart_id = next(
        proposal.id
        for proposal in fixture.proposal_store.list_proposals(
            space_id=fixture.space_id,
            status="pending_review",
        )
    )

    response = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/review-queue/proposal:{parked_id}/actions",
        json={
            "action": "resolve_as_duplicate",
            "reason": "Same assertion, two papers.",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_OK, response.text
    body = response.json()
    assert body["status"] == "duplicate"
    assert body["available_actions"] == []
    assert body["decided_by"]["user_id"] == _TEST_USER_ID
    adjudication = body["identity_adjudication"]
    assert adjudication["resolution"] == "duplicate"
    assert adjudication["duplicate_of_proposal_id"] == counterpart_id
    assert adjudication["decided_by_email"] == _TEST_USER_EMAIL
    assert adjudication["reason"] == "Same assertion, two papers."

    parked = fixture.proposal_store.get_proposal(
        space_id=fixture.space_id,
        proposal_id=parked_id,
    )
    assert parked is not None
    assert parked.claim_fingerprint == _FINGERPRINT, (
        "a duplicate keeps its fingerprint; it is outside the active unique index"
    )


def test_a_parked_proposal_can_be_released_as_a_distinct_fact() -> None:
    """"These are different facts" must return it to the ordinary queue."""
    fixture = _Fixture()
    parked_id = fixture.park_a_second_observation()

    response = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/review-queue/proposal:{parked_id}/actions",
        json={
            "action": "release_as_distinct",
            "reason": "Different chemicals; the fingerprint collided.",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_OK, response.text
    body = response.json()
    assert body["status"] == "pending_review"
    assert body["available_actions"] == ["promote", "reject"]
    assert body["decided_by"] is None, "released, not decided"
    adjudication = body["identity_adjudication"]
    assert adjudication["resolution"] == "distinct"
    assert adjudication["released_claim_fingerprint"] == _FINGERPRINT
    assert adjudication["decided_by_email"] == _TEST_USER_EMAIL

    released = fixture.proposal_store.get_proposal(
        space_id=fixture.space_id,
        proposal_id=parked_id,
    )
    assert released is not None
    assert released.claim_fingerprint is None, (
        "the reviewer said this fingerprint groups two different facts, so it "
        "no longer identifies this one"
    )
    assert adjudication["duplicate_of_proposal_id"] is not None, (
        "releasing clears the fingerprint, so this pointer is the only surviving "
        "record of what the reviewer was comparing against"
    )
    assert (
        adjudication["duplicate_of_proposal_id"]
        == body["identity_collision"]["proposal_id"]
    )

    decided = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/proposals/{parked_id}/reject",
        json={"reason": "Weak support once read on its own."},
        headers=_auth_headers(),
    )
    assert decided.status_code == _HTTP_OK, decided.text
    assert decided.json()["status"] == "rejected"
    assert decided.json()["identity_adjudication"]["resolution"] == "distinct", (
        "the adjudication trail must outlive the later decision"
    )
    assert decided.json()["identity_collision"] is not None, (
        "so must what it was adjudicated against"
    )


def test_a_duplicate_cannot_be_claimed_without_a_counterpart() -> None:
    """Nothing left to duplicate means the reference would be invented."""
    fixture = _Fixture()
    parked_id = fixture.park_a_second_observation()
    counterpart_id = next(
        proposal.id
        for proposal in fixture.proposal_store.list_proposals(
            space_id=fixture.space_id,
            status="pending_review",
        )
    )
    rejected = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/proposals/{counterpart_id}/reject",
        json={"reason": "Withdrawn."},
        headers=_auth_headers(),
    )
    assert rejected.status_code == _HTTP_OK, rejected.text

    response = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/review-queue/proposal:{parked_id}/actions",
        json={"action": "resolve_as_duplicate", "reason": "Same fact."},
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_CONFLICT, response.text
    assert "nothing left for it to duplicate" in response.json()["detail"]


def test_an_unparked_proposal_cannot_be_adjudicated() -> None:
    """Adjudication settles a parked identity; there is none to settle here."""
    fixture = _Fixture()
    created = fixture.proposal_store.create_proposals(
        space_id=fixture.space_id,
        run_id=fixture.run_id,
        proposals=(fixture.draft(document_id=str(uuid4())),),
    )

    response = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/review-queue/proposal:{created[0].id}/actions",
        json={"action": "release_as_distinct"},
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_CONFLICT, response.text
    assert "no parked identity to adjudicate" in response.json()["detail"]


def test_the_conflict_message_names_the_way_out() -> None:
    """The 409 said a parked proposal cannot be decided, and stopped there."""
    fixture = _Fixture()
    parked_id = fixture.park_a_second_observation()

    response = fixture.client.post(
        f"/v1/spaces/{fixture.space_id}/proposals/{parked_id}/promote",
        json={"reason": "probe"},
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_CONFLICT, response.text
    detail = response.json()["detail"]
    assert "resolve_as_duplicate" in detail
    assert "release_as_distinct" in detail


def test_a_parked_proposal_reports_what_it_collided_with() -> None:
    """An action without the evidence to take it manufactures a decision record.

    `resolve_as_duplicate` asks a reviewer whether two proposals assert the same
    fact. Until this field existed the queue showed them one of the two: the
    counterpart appeared only as a bare UUID inside a prose `decision_reason`,
    and on the intra-batch path it appeared nowhere at all.
    """
    fixture = _Fixture()
    parked_id = fixture.park_a_second_observation()
    counterpart = next(
        proposal
        for proposal in fixture.proposal_store.list_proposals(
            space_id=fixture.space_id,
            status="pending_review",
        )
    )

    response = fixture.client.get(
        f"/v1/spaces/{fixture.space_id}/review-queue",
        params={"status": "parked"},
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_OK, response.text
    item = next(
        entry
        for entry in response.json()["items"]
        if entry["resource_id"] == parked_id
    )
    collision = item["identity_collision"]
    assert collision["proposal_id"] == counterpart.id
    assert collision["title"] == counterpart.title
    assert collision["document_id"] == counterpart.document_id
    assert collision["status"] == "pending_review"
    assert collision["claim_fingerprint"] == _FINGERPRINT
    assert collision["origin"] == "already_persisted"


def test_an_intra_batch_collision_names_its_counterpart_too() -> None:
    """The path with no evidence at all was the one every extraction takes.

    Two drafts of one pass collide before either has a row, so the counterpart
    could not be looked up and was never recorded. The id is assigned when the
    batch is planned, which is what makes it nameable.
    """
    fixture = _Fixture()
    document_id = str(uuid4())
    created = fixture.proposal_store.create_proposals(
        space_id=fixture.space_id,
        run_id=fixture.run_id,
        proposals=(
            fixture.draft(document_id=document_id),
            fixture.draft(document_id=document_id),
        ),
    )
    assert len(created) == 2, "nothing may be dropped"
    by_status = {record.status: record for record in created}
    parked = by_status[IDENTITY_PENDING_STATUS]
    kept = by_status["pending_review"]

    response = fixture.client.get(
        f"/v1/spaces/{fixture.space_id}/review-queue",
        params={"status": "parked"},
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_OK, response.text
    item = next(
        entry
        for entry in response.json()["items"]
        if entry["resource_id"] == parked.id
    )
    collision = item["identity_collision"]
    assert collision["proposal_id"] == kept.id
    assert collision["title"] == kept.title
    assert collision["document_id"] == document_id
    assert collision["origin"] == "same_batch", (
        "one pass saying it twice is a different question from the space "
        "already holding it"
    )


def test_an_uncontested_proposal_reports_no_collision() -> None:
    """The field must mean "this collided", not "this exists"."""
    fixture = _Fixture()
    created = fixture.proposal_store.create_proposals(
        space_id=fixture.space_id,
        run_id=fixture.run_id,
        proposals=(fixture.draft(document_id=str(uuid4())),),
    )

    response = fixture.client.get(
        f"/v1/spaces/{fixture.space_id}/review-queue",
        headers=_auth_headers(),
    )

    assert response.status_code == _HTTP_OK, response.text
    item = next(
        entry
        for entry in response.json()["items"]
        if entry["resource_id"] == created[0].id
    )
    assert item["identity_collision"] is None
