"""Unit tests for graph-harness transparency helpers."""

from __future__ import annotations

from uuid import UUID, uuid4

from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.tests.support import FakeKernelRuntime
from artana_evidence_api.tool_catalog import RunPubMedSearchToolArgs
from artana_evidence_api.transparency import (
    active_skill_names_from_policy_content,
    append_manual_review_decision,
    append_skill_activity,
    build_run_capabilities_snapshot,
    ensure_run_transparency_seed,
    sync_policy_decisions_artifact,
)


def test_build_run_capabilities_snapshot_freezes_visible_and_filtered_tools() -> None:
    run_registry = HarnessRunRegistry()
    run = run_registry.create_run(
        space_id=uuid4(),
        harness_id="graph-chat",
        title="Transparency snapshot",
        input_payload={"question": "What is known about MED13?"},
        graph_service_status="ok",
        graph_service_version="test-graph",
    )

    snapshot = build_run_capabilities_snapshot(run=run, runtime=FakeKernelRuntime())

    assert snapshot["artifact_key"] == "run_capabilities"
    assert snapshot["harness_id"] == "graph-chat"
    assert snapshot["preloaded_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.graph_write_review",
    ]
    assert snapshot["allowed_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.graph_write_review",
        "graph_harness.literature_refresh",
        "graph_harness.relation_discovery",
    ]
    visible_tool_names = {
        str(entry["tool_name"])
        for entry in snapshot["visible_tools"]
        if isinstance(entry, dict)
    }
    filtered_tool_names = {
        str(entry["tool_name"])
        for entry in snapshot["filtered_tools"]
        if isinstance(entry, dict)
    }
    assert "run_pubmed_search" in visible_tool_names
    assert "suggest_relations" in visible_tool_names
    assert "create_graph_claim" in filtered_tool_names


def test_policy_decisions_sync_includes_tool_and_manual_review_records() -> None:
    runtime = FakeKernelRuntime()
    run_registry = HarnessRunRegistry()
    artifact_store = HarnessArtifactStore()
    run = run_registry.create_run(
        space_id=uuid4(),
        harness_id="graph-chat",
        title="Transparency decision log",
        input_payload={"question": "What is known about MED13?"},
        graph_service_status="ok",
        graph_service_version="test-graph",
    )
    artifact_store.seed_for_run(run=run)
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=runtime,
    )

    runtime.step_tool(
        run_id=run.id,
        tenant_id=run.space_id,
        tool_name="run_pubmed_search",
        arguments=RunPubMedSearchToolArgs(
            search_term="MED13 congenital heart disease",
            max_results=5,
        ),
        step_key="graph_chat.pubmed_search",
    )
    synced = sync_policy_decisions_artifact(
        space_id=run.space_id,
        run_id=run.id,
        run_registry=run_registry,
        artifact_store=artifact_store,
        runtime=runtime,
    )

    assert synced is not None
    assert synced["summary"]["tool_record_count"] == 1
    assert synced["summary"]["skill_record_count"] == 0
    tool_record = synced["records"][0]
    assert tool_record["decision_source"] == "tool"
    assert tool_record["tool_name"] == "run_pubmed_search"
    assert tool_record["status"] == "success"

    append_manual_review_decision(
        space_id=UUID(run.space_id),
        run_id=run.id,
        tool_name="create_graph_claim",
        decision="promote",
        reason="Approved after review",
        artifact_key="graph_write_candidate_suggestions",
        metadata={"proposal_id": "proposal-1"},
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )
    append_skill_activity(
        space_id=UUID(run.space_id),
        run_id=run.id,
        skill_names=(
            "graph_harness.graph_grounding",
            "graph_harness.literature_refresh",
        ),
        source_run_id="graph_chat:test-search",
        source_kind="graph_chat",
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )

    updated = artifact_store.get_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="policy_decisions",
    )

    assert updated is not None
    assert updated.content["summary"]["total_records"] == 4
    assert updated.content["summary"]["manual_review_count"] == 1
    assert updated.content["summary"]["skill_record_count"] == 2
    assert active_skill_names_from_policy_content(updated.content) == [
        "graph_harness.graph_grounding",
        "graph_harness.literature_refresh",
    ]
    manual_records = [
        record
        for record in updated.content["records"]
        if record["decision_source"] == "manual_review"
    ]
    assert len(manual_records) == 1
    assert manual_records[0]["tool_name"] == "create_graph_claim"
    assert manual_records[0]["decision"] == "promote"
