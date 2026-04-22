"""Unit tests for space-isolation and proposal-conflict edge cases."""

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
    get_harness_execution_services,
    get_proposal_store,
    get_research_space_store,
    get_run_registry,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.tests.support import FakeKernelRuntime
from fastapi.testclient import TestClient

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-isolation@example.com"


class _StubExecutionServices:
    def __init__(self) -> None:
        self.runtime = FakeKernelRuntime()


def _auth_headers(*, role: str = "researcher") -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": role,
    }


def _build_client() -> tuple[
    TestClient,
    HarnessArtifactStore,
    HarnessApprovalStore,
    HarnessProposalStore,
    HarnessResearchSpaceStore,
    HarnessRunRegistry,
]:
    app = create_app()
    artifact_store = HarnessArtifactStore()
    approval_store = HarnessApprovalStore()
    proposal_store = HarnessProposalStore()
    research_space_store = HarnessResearchSpaceStore()
    run_registry = HarnessRunRegistry()
    execution_services = _StubExecutionServices()

    app.dependency_overrides[get_approval_store] = lambda: approval_store
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_harness_execution_services] = (
        lambda: execution_services
    )
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry

    return (
        TestClient(app),
        artifact_store,
        approval_store,
        proposal_store,
        research_space_store,
        run_registry,
    )


def _create_run(
    *,
    space_id: str,
    run_registry: HarnessRunRegistry,
) -> HarnessRunRecord:
    return run_registry.create_run(
        space_id=space_id,
        harness_id="graph-search",
        title="Isolation test run",
        input_payload={"objective": "validate isolation"},
        graph_service_status="ok",
        graph_service_version="tests",
    )


def _create_candidate_claim_proposal(
    *,
    space_id: str,
    run_id: str,
    proposal_store: HarnessProposalStore,
) -> str:
    return proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key=f"doc:{uuid4()}",
                document_id=None,
                title="MED13 regulates transcription",
                summary="Synthetic candidate claim for router edge testing.",
                confidence=0.82,
                ranking_score=0.91,
                reasoning_path={"source": "unit-test"},
                evidence_bundle=[],
                payload={
                    "proposed_subject": str(uuid4()),
                    "proposed_object": str(uuid4()),
                    "proposed_claim_type": "REGULATES",
                    "evidence_entity_ids": [],
                },
                metadata={"source": "unit-test"},
            ),
        ),
    )[0].id


def test_get_proposal_returns_404_for_cross_space_lookup() -> None:
    client, _, _, proposal_store, research_space_store, run_registry = _build_client()
    first_space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Primary Space",
        description="Owns the proposal.",
    )
    second_space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Second Space",
        description="Used for cross-space lookups.",
    )
    run = _create_run(space_id=first_space.id, run_registry=run_registry)
    proposal_id = _create_candidate_claim_proposal(
        space_id=first_space.id,
        run_id=run.id,
        proposal_store=proposal_store,
    )

    response = client.get(
        f"/v1/spaces/{second_space.id}/proposals/{proposal_id}",
        headers=_auth_headers(),
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_reject_proposal_returns_409_when_already_decided() -> None:
    client, _, _, proposal_store, research_space_store, run_registry = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Proposal Space",
        description="Used for proposal conflict checks.",
    )
    run = _create_run(space_id=space.id, run_registry=run_registry)
    proposal_id = _create_candidate_claim_proposal(
        space_id=space.id,
        run_id=run.id,
        proposal_store=proposal_store,
    )

    first_response = client.post(
        f"/v1/spaces/{space.id}/proposals/{proposal_id}/reject",
        headers=_auth_headers(),
        json={"reason": "Reject once", "metadata": {"source": "unit-test"}},
    )
    second_response = client.post(
        f"/v1/spaces/{space.id}/proposals/{proposal_id}/reject",
        headers=_auth_headers(),
        json={"reason": "Reject twice", "metadata": {"source": "unit-test"}},
    )

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "rejected"
    assert second_response.status_code == 409
    assert "already decided" in second_response.json()["detail"]


def test_reject_proposal_rejects_viewer_role() -> None:
    client, _, _, proposal_store, research_space_store, run_registry = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Viewer Space",
        description="Used for role enforcement checks.",
    )
    run = _create_run(space_id=space.id, run_registry=run_registry)
    proposal_id = _create_candidate_claim_proposal(
        space_id=space.id,
        run_id=run.id,
        proposal_store=proposal_store,
    )

    response = client.post(
        f"/v1/spaces/{space.id}/proposals/{proposal_id}/reject",
        headers=_auth_headers(role="viewer"),
        json={"reason": "Viewer should not reject", "metadata": {}},
    )

    assert response.status_code == 403
    proposal = proposal_store.get_proposal(space_id=space.id, proposal_id=proposal_id)
    assert proposal is not None
    assert proposal.status == "pending_review"


def test_workspace_and_artifact_return_404_for_cross_space_run_lookup() -> None:
    client, artifact_store, _, _, research_space_store, run_registry = _build_client()
    first_space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Run Source Space",
        description="Owns the run artifacts.",
    )
    second_space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Run Lookup Space",
        description="Used for cross-space run lookups.",
    )
    run = _create_run(space_id=first_space.id, run_registry=run_registry)
    artifact_store.put_artifact(
        space_id=first_space.id,
        run_id=run.id,
        artifact_key="result",
        media_type="application/json",
        content={"status": "completed"},
    )
    artifact_store.patch_workspace(
        space_id=first_space.id,
        run_id=run.id,
        patch={"status": "completed"},
    )

    artifact_response = client.get(
        f"/v1/spaces/{second_space.id}/runs/{run.id}/artifacts/result",
        headers=_auth_headers(),
    )
    workspace_response = client.get(
        f"/v1/spaces/{second_space.id}/runs/{run.id}/workspace",
        headers=_auth_headers(),
    )

    assert artifact_response.status_code == 404
    assert workspace_response.status_code == 404


def test_decide_approval_returns_409_when_already_decided() -> None:
    client, _, approval_store, _, research_space_store, run_registry = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Approval Space",
        description="Used for approval conflict checks.",
    )
    run = _create_run(space_id=space.id, run_registry=run_registry)
    approval_store.upsert_intent(
        space_id=space.id,
        run_id=run.id,
        summary="Review one promoted claim.",
        proposed_actions=(
            HarnessApprovalAction(
                approval_key="promote-claim-1",
                title="Promote candidate claim",
                risk_level="high",
                target_type="claim",
                target_id=str(uuid4()),
                requires_approval=True,
                metadata={"source": "unit-test"},
            ),
        ),
        metadata={"source": "unit-test"},
    )

    first_response = client.post(
        f"/v1/spaces/{space.id}/runs/{run.id}/approvals/promote-claim-1",
        headers=_auth_headers(),
        json={"decision": "approved", "reason": "Approve once"},
    )
    second_response = client.post(
        f"/v1/spaces/{space.id}/runs/{run.id}/approvals/promote-claim-1",
        headers=_auth_headers(),
        json={"decision": "approved", "reason": "Approve twice"},
    )

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "approved"
    assert second_response.status_code == 409
    assert "already decided" in second_response.json()["detail"]


def test_decide_approval_rejects_viewer_role_without_side_effects() -> None:
    client, _, approval_store, _, research_space_store, run_registry = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Viewer Approval Space",
        description="Used for approval role enforcement checks.",
    )
    run = _create_run(space_id=space.id, run_registry=run_registry)
    approval_store.upsert_intent(
        space_id=space.id,
        run_id=run.id,
        summary="Review one promoted claim.",
        proposed_actions=(
            HarnessApprovalAction(
                approval_key="promote-claim-1",
                title="Promote candidate claim",
                risk_level="high",
                target_type="claim",
                target_id=str(uuid4()),
                requires_approval=True,
                metadata={"source": "unit-test"},
            ),
        ),
        metadata={"source": "unit-test"},
    )

    response = client.post(
        f"/v1/spaces/{space.id}/runs/{run.id}/approvals/promote-claim-1",
        headers=_auth_headers(role="viewer"),
        json={"decision": "approved", "reason": "Viewer should not approve"},
    )

    assert response.status_code == 403
    approvals = approval_store.list_approvals(space_id=space.id, run_id=run.id)
    assert len(approvals) == 1
    assert approvals[0].status == "pending"
    assert approvals[0].decision_reason is None
