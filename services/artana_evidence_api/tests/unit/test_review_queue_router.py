"""Unit tests for the unified review-queue router."""

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

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-review-queue@example.com"


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


def _build_client() -> tuple[
    TestClient,
    HarnessApprovalStore,
    HarnessProposalStore,
    HarnessReviewItemStore,
    HarnessResearchSpaceStore,
    HarnessRunRegistry,
]:
    app = create_app()
    artifact_store = HarnessArtifactStore()
    approval_store = HarnessApprovalStore()
    proposal_store = HarnessProposalStore()
    review_item_store = HarnessReviewItemStore()
    research_space_store = HarnessResearchSpaceStore()
    run_registry = HarnessRunRegistry()
    execution_services = _StubExecutionServices()

    app.dependency_overrides[get_approval_store] = lambda: approval_store
    app.dependency_overrides[get_artifact_store] = lambda: artifact_store
    app.dependency_overrides[get_graph_api_gateway] = lambda: _StubGraphApiGateway()
    app.dependency_overrides[get_harness_execution_services] = (
        lambda: execution_services
    )
    app.dependency_overrides[get_proposal_store] = lambda: proposal_store
    app.dependency_overrides[get_research_space_store] = lambda: research_space_store
    app.dependency_overrides[get_review_item_store] = lambda: review_item_store
    app.dependency_overrides[get_run_registry] = lambda: run_registry

    return (
        TestClient(app),
        approval_store,
        proposal_store,
        review_item_store,
        research_space_store,
        run_registry,
    )


def _create_run(
    *,
    space_id: str,
    run_registry: HarnessRunRegistry,
) -> str:
    return run_registry.create_run(
        space_id=space_id,
        harness_id="graph-search",
        title="Review queue test run",
        input_payload={"objective": "review queue"},
        graph_service_status="ok",
        graph_service_version="tests",
    ).id


def test_review_queue_lists_proposals_review_items_and_approvals() -> None:
    (
        client,
        approval_store,
        proposal_store,
        review_item_store,
        research_space_store,
        run_registry,
    ) = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Review Queue Space",
        description="Used for review queue routing tests.",
    )
    run_id = _create_run(space_id=space.id, run_registry=run_registry)
    proposal_store.create_proposals(
        space_id=space.id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="doc:claim:1",
                title="Candidate claim",
                summary="Synthetic candidate claim",
                confidence=0.81,
                ranking_score=0.91,
                reasoning_path={"source": "unit-test"},
                evidence_bundle=[],
                payload={"proposed_claim_type": "ASSOCIATED_WITH"},
                metadata={"source": "unit-test"},
            ),
        ),
    )
    review_item_store.create_review_items(
        space_id=space.id,
        run_id=run_id,
        review_items=(
            HarnessReviewItemDraft(
                review_type="phenotype_claim_review",
                source_family="document_extraction",
                source_kind="document_extraction",
                source_key="doc:review:1",
                title="Review phenotype link",
                summary="developmental delay",
                priority="medium",
                confidence=0.66,
                ranking_score=0.66,
                evidence_bundle=[],
                payload={
                    "phenotype_span": "developmental delay",
                    "proposal_draft": {
                        "proposal_type": "candidate_claim",
                        "payload": {
                            "proposed_subject": "unresolved:med13_variant",
                            "proposed_subject_label": "MED13 c.977C>A",
                            "proposed_claim_type": "CAUSES",
                            "proposed_object": "unresolved:developmental_delay",
                            "proposed_object_label": "developmental delay",
                            "evidence_entity_ids": [],
                        },
                    },
                },
                metadata={"source": "unit-test"},
            ),
        ),
    )
    approval_store.upsert_intent(
        space_id=space.id,
        run_id=run_id,
        summary="Review the pending graph mutation.",
        proposed_actions=(
            HarnessApprovalAction(
                approval_key="approval-1",
                title="Approve claim write",
                risk_level="high",
                target_type="claim",
                target_id=str(uuid4()),
                requires_approval=True,
                metadata={"summary": "Needs curator review."},
            ),
        ),
        metadata={},
    )

    response = client.get(
        f"/v1/spaces/{space.id}/review-queue",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    item_types = {item["item_type"] for item in payload["items"]}
    assert item_types == {"proposal", "review_item", "approval"}
    actions_by_type = {
        item["item_type"]: set(item["available_actions"]) for item in payload["items"]
    }
    assert actions_by_type["proposal"] == {"promote", "reject"}
    assert actions_by_type["review_item"] == {
        "convert_to_proposal",
        "mark_resolved",
        "dismiss",
    }
    assert actions_by_type["approval"] == {"approve", "reject"}
    assert {item["source_family"] for item in payload["items"]} == {
        "document_extraction",
        "run_approval",
    }


def test_review_queue_action_rejects_proposal_via_unified_surface() -> None:
    (
        client,
        _approval_store,
        proposal_store,
        _review_item_store,
        research_space_store,
        run_registry,
    ) = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Proposal Review Space",
        description="Used for unified proposal review tests.",
    )
    run_id = _create_run(space_id=space.id, run_registry=run_registry)
    proposal = proposal_store.create_proposals(
        space_id=space.id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="doc:claim:reject",
                title="Rejectable proposal",
                summary="Synthetic candidate claim",
                confidence=0.71,
                ranking_score=0.77,
                reasoning_path={"source": "unit-test"},
                evidence_bundle=[],
                payload={
                    "proposed_subject": str(uuid4()),
                    "proposed_object": str(uuid4()),
                    "proposed_claim_type": "ASSOCIATED_WITH",
                    "evidence_entity_ids": [],
                },
                metadata={"source": "unit-test"},
            ),
        ),
    )[0]

    response = client.post(
        f"/v1/spaces/{space.id}/review-queue/proposal:{proposal.id}/actions",
        headers=_auth_headers(),
        json={"action": "reject", "reason": "Not strong enough", "metadata": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_type"] == "proposal"
    assert payload["status"] == "rejected"
    assert payload["decision_reason"] == "Not strong enough"


def test_review_queue_action_resolves_review_item() -> None:
    (
        client,
        _approval_store,
        _proposal_store,
        review_item_store,
        research_space_store,
        run_registry,
    ) = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Review Item Space",
        description="Used for review-item queue tests.",
    )
    run_id = _create_run(space_id=space.id, run_registry=run_registry)
    review_item = review_item_store.create_review_items(
        space_id=space.id,
        run_id=run_id,
        review_items=(
            HarnessReviewItemDraft(
                review_type="variant_anchor_review",
                source_family="document_extraction",
                source_kind="document_extraction",
                source_key="doc:variant:1",
                title="Review incomplete variant",
                summary="Missing transcript anchor",
                priority="high",
                confidence=0.74,
                ranking_score=0.74,
                evidence_bundle=[],
                payload={"missing_anchors": ["hgvs_notation"]},
                metadata={"source": "unit-test"},
            ),
        ),
    )[0]

    response = client.post(
        f"/v1/spaces/{space.id}/review-queue/review_item:{review_item.id}/actions",
        headers=_auth_headers(),
        json={
            "action": "mark_resolved",
            "reason": "Anchors confirmed",
            "metadata": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_type"] == "review_item"
    assert payload["status"] == "resolved"
    assert payload["decision_reason"] == "Anchors confirmed"


def test_review_queue_action_converts_review_item_to_proposal() -> None:
    (
        client,
        _approval_store,
        proposal_store,
        review_item_store,
        research_space_store,
        run_registry,
    ) = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Review Item Conversion Space",
        description="Used for review-item conversion tests.",
    )
    run_id = _create_run(space_id=space.id, run_registry=run_registry)
    review_item = review_item_store.create_review_items(
        space_id=space.id,
        run_id=run_id,
        review_items=(
            HarnessReviewItemDraft(
                review_type="phenotype_claim_review",
                source_family="document_extraction",
                source_kind="document_extraction",
                source_key="doc:review:convert",
                title="Review phenotype link",
                summary="developmental delay",
                priority="medium",
                confidence=0.8,
                ranking_score=0.82,
                evidence_bundle=[],
                payload={
                    "phenotype_span": "developmental delay",
                    "proposal_draft": {
                        "proposal_type": "candidate_claim",
                        "title": "Extracted claim: MED13 variant CAUSES developmental delay",
                        "summary": "The variant was described alongside developmental delay.",
                        "payload": {
                            "proposed_subject": "unresolved:med13_variant",
                            "proposed_subject_label": "MED13 c.977C>A",
                            "proposed_claim_type": "CAUSES",
                            "proposed_object": "unresolved:developmental_delay",
                            "proposed_object_label": "developmental delay",
                            "evidence_entity_ids": [],
                        },
                        "claim_fingerprint": "review-item-conversion-fp",
                    },
                },
                metadata={"source": "unit-test"},
            ),
        ),
    )[0]

    response = client.post(
        f"/v1/spaces/{space.id}/review-queue/review_item:{review_item.id}/actions",
        headers=_auth_headers(),
        json={
            "action": "convert_to_proposal",
            "reason": "This is ready for proposal review",
            "metadata": {"reviewer_note": "promote later if it still holds"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_type"] == "proposal"
    assert payload["kind"] == "candidate_claim"
    assert payload["status"] == "pending_review"
    assert payload["linked_resource"] == {"proposal_id": payload["resource_id"]}

    refreshed_review_item = review_item_store.get_review_item(
        space_id=space.id,
        review_item_id=review_item.id,
    )
    assert refreshed_review_item is not None
    assert refreshed_review_item.status == "resolved"
    assert refreshed_review_item.linked_proposal_id == payload["resource_id"]
    assert refreshed_review_item.metadata["converted_to_proposal"] is True
    assert (
        proposal_store.get_proposal(
            space_id=space.id,
            proposal_id=payload["resource_id"],
        )
        is not None
    )


def test_review_queue_action_approves_run_gate() -> None:
    (
        client,
        approval_store,
        _proposal_store,
        _review_item_store,
        research_space_store,
        run_registry,
    ) = _build_client()
    space = research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Approval Review Space",
        description="Used for approval review tests.",
    )
    run_id = _create_run(space_id=space.id, run_registry=run_registry)
    approval_store.upsert_intent(
        space_id=space.id,
        run_id=run_id,
        summary="Approval needed before continuing.",
        proposed_actions=(
            HarnessApprovalAction(
                approval_key="approval-queue-1",
                title="Approve staged graph write",
                risk_level="medium",
                target_type="claim",
                target_id=str(uuid4()),
                requires_approval=True,
                metadata={"summary": "Review the pending graph write."},
            ),
        ),
        metadata={},
    )

    response = client.post(
        f"/v1/spaces/{space.id}/review-queue/approval:{run_id}:approval-queue-1/actions",
        headers=_auth_headers(),
        json={"action": "approve", "reason": "Looks good", "metadata": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["item_type"] == "approval"
    assert payload["status"] == "approved"
    assert payload["decision_reason"] == "Looks good"
