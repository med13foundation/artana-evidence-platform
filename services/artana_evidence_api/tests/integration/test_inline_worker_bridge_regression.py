"""Integration regression coverage for queue-first supervisor execution."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.artana_stores import ArtanaBackedHarnessArtifactStore
from artana_evidence_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from artana_evidence_api.mechanism_discovery_runtime import (
    MechanismCandidateRecord,
    MechanismDiscoveryRunExecutionResult,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.routers.mechanism_discovery_runs import (
    build_mechanism_discovery_run_response,
)
from artana_evidence_api.run_registry import HarnessRunRecord
from artana_evidence_api.tests.integration.test_runtime_paths import (
    _build_client,
    _build_services,
    _supervisor_execution_override,
)
from artana_evidence_api.tests.support import FakeKernelRuntime, auth_headers
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


async def _mechanism_discovery_execution_override(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    if run.harness_id != "mechanism-discovery":
        return await _supervisor_execution_override(run, services)
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="running",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="reasoning",
        message="Ranking converging reasoning paths.",
        progress_percent=0.6,
        completed_steps=2,
        total_steps=3,
        metadata={"candidate_count": 1},
    )
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="completed",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="completed",
        message="Mechanism discovery completed.",
        progress_percent=1.0,
        completed_steps=3,
        total_steps=3,
        clear_resume_point=True,
        metadata={"candidate_count": 1},
    )
    completed_run = services.run_registry.get_run(space_id=run.space_id, run_id=run.id)
    if completed_run is None:
        msg = "Failed to reload completed mechanism-discovery run."
        raise RuntimeError(msg)
    seed_entity_id = _first_seed_entity_id(completed_run.input_payload)
    candidate = MechanismCandidateRecord(
        seed_entity_ids=(seed_entity_id,),
        end_entity_id=str(uuid4()),
        relation_type="REGULATES",
        source_label="MED13",
        target_label="CDK8",
        source_type="GENE",
        target_type="GENE",
        path_ids=("path-1", "path-2"),
        root_claim_ids=("claim-root-1",),
        supporting_claim_ids=("claim-support-1",),
        evidence_reference_count=2,
        max_path_confidence=0.94,
        average_path_confidence=0.91,
        average_path_length=2.5,
        ranking_score=0.93,
        ranking_metadata={"strategy": "integration-test"},
        summary="Synthetic converging mechanism candidate.",
        hypothesis_statement="MED13 may regulate CDK8 through a converging path.",
        hypothesis_rationale="Synthetic ranking rationale for queue-and-wait coverage.",
        evidence_bundle=(
            {
                "source_type": "note",
                "locator": "path-1",
                "excerpt": "Synthetic evidence.",
            },
        ),
    )
    result = MechanismDiscoveryRunExecutionResult(
        run=completed_run,
        candidates=(candidate,),
        proposal_records=[],
        scanned_path_count=2,
    )
    store_primary_result_artifact(
        artifact_store=services.artifact_store,
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="mechanism_discovery_response",
        content=build_mechanism_discovery_run_response(result).model_dump(mode="json"),
        status_value="completed",
        result_keys=["mechanism_candidates", "mechanism_candidate_proposals"],
        workspace_patch={"candidate_count": 1, "scanned_path_count": 2},
    )
    return result


def _first_seed_entity_id(input_payload: object) -> str:
    if not isinstance(input_payload, dict):
        return str(uuid4())
    seed_entity_ids = input_payload.get("seed_entity_ids")
    if not isinstance(seed_entity_ids, list) or len(seed_entity_ids) == 0:
        return str(uuid4())
    first = seed_entity_ids[0]
    if not isinstance(first, str) or first == "":
        return str(uuid4())
    return first


def test_supervisor_route_returns_paused_response_and_primary_result_artifacts(
    db_session: Session,
) -> None:
    """Supervisor should queue through the worker path and persist typed results."""
    runtime = FakeKernelRuntime()
    services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_supervisor_execution_override,
    )
    client = _build_client(session=db_session, runtime=runtime, services=services)
    artifact_store = services.artifact_store
    assert isinstance(artifact_store, ArtanaBackedHarnessArtifactStore)

    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        headers=auth_headers(),
        json={
            "objective": "Compose bootstrap and governed review",
            "seed_entity_ids": [seed_entity_id],
            "include_chat": False,
            "include_curation": True,
            "curation_source": "bootstrap",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    parent_run_id = payload["run"]["id"]
    child_curation_run_id = payload["curation"]["run"]["id"]

    assert payload["run"]["harness_id"] == "supervisor"
    assert payload["run"]["status"] == "paused"
    assert payload["bootstrap"]["run"]["status"] == "completed"
    assert payload["curation"]["run"]["status"] == "paused"
    assert payload["curation"]["pending_approval_count"] == 1
    assert payload["steps"][0]["step"] == "bootstrap"
    assert payload["steps"][1]["step"] == "curation"

    parent_workspace = artifact_store.get_workspace(
        space_id=space_id,
        run_id=parent_run_id,
    )
    assert parent_workspace is not None
    assert parent_workspace.snapshot["status"] == "paused"
    assert parent_workspace.snapshot["primary_result_key"] == "supervisor_run_response"
    assert "supervisor_run_response" in parent_workspace.snapshot["result_keys"]

    parent_result = artifact_store.get_artifact(
        space_id=space_id,
        run_id=parent_run_id,
        artifact_key="supervisor_run_response",
    )
    assert parent_result is not None
    assert parent_result.content["run"]["id"] == parent_run_id
    assert parent_result.content["curation"]["run"]["id"] == child_curation_run_id

    child_workspace = artifact_store.get_workspace(
        space_id=space_id,
        run_id=child_curation_run_id,
    )
    assert child_workspace is not None
    assert child_workspace.snapshot["status"] == "paused"
    assert child_workspace.snapshot["primary_result_key"] == "claim_curation_response"
    assert "claim_curation_response" in child_workspace.snapshot["result_keys"]

    child_result = artifact_store.get_artifact(
        space_id=space_id,
        run_id=child_curation_run_id,
        artifact_key="claim_curation_response",
    )
    assert child_result is not None
    assert child_result.content["run"]["id"] == child_curation_run_id


def test_mechanism_discovery_route_returns_completed_response_and_primary_result_artifact(
    db_session: Session,
) -> None:
    """Mechanism discovery should use the same queue-and-wait persistence path."""
    runtime = FakeKernelRuntime()
    services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_mechanism_discovery_execution_override,
    )
    client = _build_client(session=db_session, runtime=runtime, services=services)
    artifact_store = services.artifact_store
    assert isinstance(artifact_store, ArtanaBackedHarnessArtifactStore)

    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/mechanism-discovery/runs",
        headers=auth_headers(),
        json={
            "seed_entity_ids": [seed_entity_id],
            "title": "Queue-backed mechanism discovery",
            "max_candidates": 5,
            "max_reasoning_paths": 10,
            "max_path_depth": 3,
            "min_path_confidence": 0.2,
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    run_id = payload["run"]["id"]

    assert payload["run"]["harness_id"] == "mechanism-discovery"
    assert payload["run"]["status"] == "completed"
    assert payload["candidate_count"] == 1
    assert payload["proposal_count"] == 0
    assert payload["scanned_path_count"] == 2
    assert payload["candidates"][0]["seed_entity_ids"] == [seed_entity_id]
    assert payload["candidates"][0]["relation_type"] == "REGULATES"

    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run_id)
    assert workspace is not None
    assert workspace.snapshot["status"] == "completed"
    assert workspace.snapshot["primary_result_key"] == "mechanism_discovery_response"
    assert "mechanism_discovery_response" in workspace.snapshot["result_keys"]
    assert workspace.snapshot["candidate_count"] == 1

    result_artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key="mechanism_discovery_response",
    )
    assert result_artifact is not None
    assert result_artifact.content["run"]["id"] == run_id
    assert result_artifact.content["candidate_count"] == 1
