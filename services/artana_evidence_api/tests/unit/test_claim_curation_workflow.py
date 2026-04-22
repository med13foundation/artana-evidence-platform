"""Focused unit tests for claim-curation workflow failure handling."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from artana_evidence_api.approval_store import (
    HarnessApprovalAction,
    HarnessApprovalStore,
    HarnessRunIntentRecord,
)
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.graph_client import GraphServiceHealthResponse
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalStore,
)
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import (
    KernelRelationClaimListResponse,
    KernelRelationConflictListResponse,
)


class _StubGraphApiGateway:
    def __init__(self) -> None:
        self.closed = False

    def get_health(self) -> GraphServiceHealthResponse:
        return GraphServiceHealthResponse(status="ok", version="test-graph")

    def close(self) -> None:
        self.closed = True


class _ExplodingApprovalStore(HarnessApprovalStore):
    def upsert_intent(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        summary: str,
        proposed_actions: tuple[HarnessApprovalAction, ...],
        metadata: JSONObject,
    ) -> HarnessRunIntentRecord:
        del space_id, run_id, summary, proposed_actions, metadata
        raise RuntimeError("intent persistence blew up")


def _curatable_candidate_claim_draft(
    *,
    title: str,
    source_key: str,
    subject_id: str,
    object_id: str,
) -> HarnessProposalDraft:
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="document_extraction",
        source_key=source_key,
        title=title,
        summary=f"Evidence summary for {title}",
        confidence=0.88,
        ranking_score=0.91,
        reasoning_path={},
        evidence_bundle=[],
        payload={
            "proposed_subject": subject_id,
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object": object_id,
        },
        metadata={},
    )


def _patch_review_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    from artana_evidence_api import claim_curation_runtime, claim_curation_workflow

    monkeypatch.setattr(
        claim_curation_workflow,
        "ensure_run_transparency_seed",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        claim_curation_runtime,
        "run_list_relation_conflicts",
        lambda **_kwargs: KernelRelationConflictListResponse(
            conflicts=[],
            total=0,
            offset=0,
            limit=50,
        ),
    )
    monkeypatch.setattr(
        claim_curation_runtime,
        "run_list_claims_by_entity",
        lambda **_kwargs: KernelRelationClaimListResponse(
            claims=[],
            total=0,
            offset=0,
            limit=50,
        ),
    )


def _proposal_store_with_one_curatable_claim(*, space_id: UUID) -> HarnessProposalStore:
    proposal_store = HarnessProposalStore()
    proposal_store.create_proposals(
        space_id=space_id,
        run_id="parent-run",
        proposals=(
            _curatable_candidate_claim_draft(
                title="Candidate claim: MED13 ASSOCIATED_WITH phenotype-a",
                source_key="pubmed:1",
                subject_id=str(uuid4()),
                object_id=str(uuid4()),
            ),
        ),
    )
    return proposal_store


def test_execute_claim_curation_run_cleans_new_run_when_skill_activity_append_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import claim_curation_workflow
    from artana_evidence_api.claim_curation_runtime import load_curatable_proposals

    _patch_review_dependencies(monkeypatch)
    monkeypatch.setattr(
        claim_curation_workflow,
        "append_skill_activity",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("skill activity boom")),
    )

    space_id = uuid4()
    proposal_store = _proposal_store_with_one_curatable_claim(space_id=space_id)
    proposal_ids = tuple(
        proposal.id for proposal in proposal_store.list_proposals(space_id=space_id)
    )
    proposals = load_curatable_proposals(
        space_id=space_id,
        proposal_ids=proposal_ids,
        proposal_store=proposal_store,
    )
    artifact_store = HarnessArtifactStore()
    run_registry = HarnessRunRegistry()

    with pytest.raises(RuntimeError, match="skill activity boom"):
        claim_curation_workflow.execute_claim_curation_run_for_proposals(
            space_id=space_id,
            proposals=proposals,
            title="Claim curation",
            run_registry=run_registry,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            approval_store=HarnessApprovalStore(),
            graph_api_gateway=_StubGraphApiGateway(),  # type: ignore[arg-type]
            runtime=object(),  # type: ignore[arg-type]
        )

    assert run_registry.list_runs(space_id=space_id) == []


def test_execute_claim_curation_run_cleans_new_run_when_pause_state_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import claim_curation_workflow
    from artana_evidence_api.claim_curation_runtime import load_curatable_proposals

    _patch_review_dependencies(monkeypatch)
    monkeypatch.setattr(
        claim_curation_workflow,
        "append_skill_activity",
        lambda **_kwargs: None,
    )

    space_id = uuid4()
    proposal_store = _proposal_store_with_one_curatable_claim(space_id=space_id)
    proposal_ids = tuple(
        proposal.id for proposal in proposal_store.list_proposals(space_id=space_id)
    )
    proposals = load_curatable_proposals(
        space_id=space_id,
        proposal_ids=proposal_ids,
        proposal_store=proposal_store,
    )
    artifact_store = HarnessArtifactStore()
    run_registry = HarnessRunRegistry()

    with pytest.raises(RuntimeError, match="intent persistence blew up"):
        claim_curation_workflow.execute_claim_curation_run_for_proposals(
            space_id=space_id,
            proposals=proposals,
            title="Claim curation",
            run_registry=run_registry,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            approval_store=_ExplodingApprovalStore(),
            graph_api_gateway=_StubGraphApiGateway(),  # type: ignore[arg-type]
            runtime=object(),  # type: ignore[arg-type]
        )

    assert run_registry.list_runs(space_id=space_id) == []


def test_execute_claim_curation_run_marks_existing_run_failed_when_skill_activity_append_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import claim_curation_workflow
    from artana_evidence_api.claim_curation_runtime import load_curatable_proposals

    _patch_review_dependencies(monkeypatch)
    monkeypatch.setattr(
        claim_curation_workflow,
        "append_skill_activity",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("skill activity boom")),
    )

    space_id = uuid4()
    proposal_store = _proposal_store_with_one_curatable_claim(space_id=space_id)
    proposal_ids = tuple(
        proposal.id for proposal in proposal_store.list_proposals(space_id=space_id)
    )
    proposals = load_curatable_proposals(
        space_id=space_id,
        proposal_ids=proposal_ids,
        proposal_store=proposal_store,
    )
    artifact_store = HarnessArtifactStore()
    run_registry = HarnessRunRegistry()
    existing_run = claim_curation_workflow.queue_claim_curation_run(
        space_id=space_id,
        title="Claim curation",
        proposal_ids=list(proposal_ids),
        graph_service_status="ok",
        graph_service_version="test-graph",
        run_registry=run_registry,
        artifact_store=artifact_store,
    )

    with pytest.raises(RuntimeError, match="skill activity boom"):
        claim_curation_workflow.execute_claim_curation_run_for_proposals(
            space_id=space_id,
            proposals=proposals,
            title="Claim curation",
            run_registry=run_registry,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            approval_store=HarnessApprovalStore(),
            graph_api_gateway=_StubGraphApiGateway(),  # type: ignore[arg-type]
            runtime=object(),  # type: ignore[arg-type]
            existing_run=existing_run,
        )

    failed_run = run_registry.get_run(space_id=space_id, run_id=existing_run.id)
    assert failed_run is not None
    assert failed_run.status == "failed"
    progress = run_registry.get_progress(space_id=space_id, run_id=existing_run.id)
    assert progress is not None
    assert progress.phase == "failed"
    assert progress.message == "Failed to initialize claim curation: skill activity boom"
    error_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=existing_run.id,
        artifact_key="claim_curation_error",
    )
    assert error_artifact is not None
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=existing_run.id)
    assert workspace is not None
    assert workspace.snapshot["status"] == "failed"
    assert workspace.snapshot["error"] == (
        "Failed to initialize claim curation: skill activity boom"
    )
    event_types = [
        event.event_type
        for event in run_registry.list_events(
            space_id=space_id,
            run_id=existing_run.id,
        )
    ]
    assert "claim_curation.failed" in event_types


def test_execute_claim_curation_run_marks_existing_run_failed_when_pause_state_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana_evidence_api import claim_curation_workflow
    from artana_evidence_api.claim_curation_runtime import load_curatable_proposals

    _patch_review_dependencies(monkeypatch)
    monkeypatch.setattr(
        claim_curation_workflow,
        "append_skill_activity",
        lambda **_kwargs: None,
    )

    space_id = uuid4()
    proposal_store = _proposal_store_with_one_curatable_claim(space_id=space_id)
    proposal_ids = tuple(
        proposal.id for proposal in proposal_store.list_proposals(space_id=space_id)
    )
    proposals = load_curatable_proposals(
        space_id=space_id,
        proposal_ids=proposal_ids,
        proposal_store=proposal_store,
    )
    artifact_store = HarnessArtifactStore()
    run_registry = HarnessRunRegistry()
    existing_run = claim_curation_workflow.queue_claim_curation_run(
        space_id=space_id,
        title="Claim curation",
        proposal_ids=list(proposal_ids),
        graph_service_status="ok",
        graph_service_version="test-graph",
        run_registry=run_registry,
        artifact_store=artifact_store,
    )

    with pytest.raises(RuntimeError, match="intent persistence blew up"):
        claim_curation_workflow.execute_claim_curation_run_for_proposals(
            space_id=space_id,
            proposals=proposals,
            title="Claim curation",
            run_registry=run_registry,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            approval_store=_ExplodingApprovalStore(),
            graph_api_gateway=_StubGraphApiGateway(),  # type: ignore[arg-type]
            runtime=object(),  # type: ignore[arg-type]
            existing_run=existing_run,
        )

    failed_run = run_registry.get_run(space_id=space_id, run_id=existing_run.id)
    assert failed_run is not None
    assert failed_run.status == "failed"
    progress = run_registry.get_progress(space_id=space_id, run_id=existing_run.id)
    assert progress is not None
    assert progress.phase == "failed"
    assert progress.message == (
        "Failed to initialize claim curation: intent persistence blew up"
    )
    workspace = artifact_store.get_workspace(space_id=space_id, run_id=existing_run.id)
    assert workspace is not None
    assert workspace.snapshot["status"] == "failed"
    assert workspace.snapshot["error"] == (
        "Failed to initialize claim curation: intent persistence blew up"
    )
    assert (
        artifact_store.get_artifact(
            space_id=space_id,
            run_id=existing_run.id,
            artifact_key="curation_packet",
        )
        is not None
    )
    assert (
        artifact_store.get_artifact(
            space_id=space_id,
            run_id=existing_run.id,
            artifact_key="review_plan",
        )
        is not None
    )
    assert (
        artifact_store.get_artifact(
            space_id=space_id,
            run_id=existing_run.id,
            artifact_key="claim_curation_error",
        )
        is not None
    )
