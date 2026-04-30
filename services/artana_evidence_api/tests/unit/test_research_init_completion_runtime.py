"""Unit tests for research-init completion helpers."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from artana_evidence_api import research_init_brief
from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.research_init_brief import ResearchBrief
from artana_evidence_api.research_init_completion_runtime import (
    _generate_and_store_research_brief,
)
from artana_evidence_api.run_registry import HarnessRunRegistry


@pytest.mark.asyncio
async def test_generate_and_store_research_brief_reports_storage_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_llm_brief(**kwargs: object) -> ResearchBrief:
        return cast("ResearchBrief", kwargs["deterministic_brief"])

    def _raise_store_failure(**_kwargs: object) -> None:
        raise RuntimeError("artifact store unavailable")

    monkeypatch.setattr(
        research_init_brief,
        "generate_llm_research_brief",
        _fake_llm_brief,
    )
    monkeypatch.setattr(
        research_init_brief,
        "store_research_brief",
        _raise_store_failure,
    )

    outcome = await _generate_and_store_research_brief(
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        source_results={"pubmed": {"selected": True, "status": "completed"}},
        documents_ingested=1,
        proposal_count=2,
        entity_count=1,
        errors=[],
        chase_rounds_completed=0,
        proposals=[],
        artifact_store=HarnessArtifactStore(),
        space_id=uuid4(),
        run_id="research-init-run",
    )

    metadata = outcome.to_metadata()
    assert outcome.status == "skipped"
    assert outcome.reason == "storage_failed"
    assert outcome.markdown is not None
    assert metadata["brief_markdown_present"] is True
    assert metadata["llm_status"] == "fallback_deterministic"
    assert metadata["error"] == "artifact store unavailable"
    assert outcome.to_error_message() == (
        "Research brief generation skipped: storage_failed: artifact store unavailable"
    )


@pytest.mark.asyncio
async def test_generate_and_store_research_brief_reports_generation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_generation_failure(**_kwargs: object) -> ResearchBrief:
        raise RuntimeError("brief builder unavailable")

    monkeypatch.setattr(
        research_init_brief,
        "generate_research_brief",
        _raise_generation_failure,
    )

    outcome = await _generate_and_store_research_brief(
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        source_results={},
        documents_ingested=0,
        proposal_count=0,
        entity_count=0,
        errors=[],
        chase_rounds_completed=0,
        proposals=[],
        artifact_store=HarnessArtifactStore(),
        space_id=uuid4(),
        run_id="research-init-run",
    )

    assert outcome.status == "skipped"
    assert outcome.reason == "generation_failed"
    assert outcome.markdown is None
    assert outcome.to_metadata()["llm_status"] == "not_attempted"
    assert outcome.to_metadata()["error"] == "brief builder unavailable"


@pytest.mark.asyncio
async def test_generate_and_store_research_brief_keeps_deterministic_on_bad_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _bad_llm_brief(**_kwargs: object) -> object:
        return None

    monkeypatch.setattr(
        research_init_brief,
        "generate_llm_research_brief",
        _bad_llm_brief,
    )
    space_id = uuid4()
    artifact_store = HarnessArtifactStore()
    run = HarnessRunRegistry().create_run(
        space_id=space_id,
        harness_id="research-init",
        title="Research Init",
        input_payload={},
        graph_service_status="ok",
        graph_service_version="test",
    )
    artifact_store.seed_for_run(run=run)

    outcome = await _generate_and_store_research_brief(
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        source_results={"pubmed": {"selected": True, "status": "completed"}},
        documents_ingested=1,
        proposal_count=2,
        entity_count=1,
        errors=[],
        chase_rounds_completed=0,
        proposals=[],
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
    )

    workspace = artifact_store.get_workspace(space_id=space_id, run_id=run.id)

    assert outcome.status == "completed"
    assert outcome.to_metadata()["llm_status"] == "failed"
    assert outcome.to_metadata()["llm_error"] == (
        "generate_llm_research_brief returned NoneType"
    )
    assert outcome.markdown is not None
    assert workspace is not None
    assert isinstance(workspace.snapshot.get("research_brief"), dict)
