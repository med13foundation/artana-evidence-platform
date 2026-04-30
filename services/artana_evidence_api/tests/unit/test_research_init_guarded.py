"""Unit tests for guarded-mode research-init helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import pytest
from artana_evidence_api import research_init_guarded
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorChaseCandidate,
)
from artana_evidence_api.harness_runtime import HarnessExecutionServices
from artana_evidence_api.research_init_models import _ChaseRoundPreparation
from artana_evidence_api.types.common import JSONObject


@pytest.mark.asyncio
async def test_select_guarded_chase_round_selection_dispatches_and_coerces() -> None:
    observer = _ChaseSelectionObserver()

    selection = await research_init_guarded.maybe_select_guarded_chase_round_selection(
        services=_services_with_workspace({"pending_chase_round": {"round_number": 1}}),
        space_id=uuid4(),
        run_id="run-1",
        round_number=1,
        preparation=_chase_preparation(),
        progress_observer=cast("object", observer),
    )

    assert selection is not None
    assert selection.selected_entity_ids == ["entity-1", "entity-2"]
    assert selection.selected_labels == ["CDK8", "MED12"]
    assert observer.workspace_snapshot == {"pending_chase_round": {"round_number": 1}}


@pytest.mark.asyncio
async def test_select_guarded_structured_enrichment_sources_filters_observer_result() -> (
    None
):
    space_id = uuid4()
    observer = _StructuredSourceObserver()

    selected = (
        await research_init_guarded.maybe_select_guarded_structured_enrichment_sources(
            services=_services_with_workspace({"pending": "structured"}),
            space_id=space_id,
            run_id="run-1",
            available_source_keys=["clinvar", "drugbank"],
            progress_observer=cast("object", observer),
        )
    )

    assert selected == ("drugbank", "clinvar")
    assert observer.workspace_snapshot == {"pending": "structured"}


@pytest.mark.asyncio
async def test_guarded_verification_hooks_use_workspace_snapshot() -> None:
    observer = _VerificationObserver()

    structured_verified = (
        await research_init_guarded.maybe_verify_guarded_structured_enrichment(
            services=_services_with_workspace({"source_results": {"clinvar": {}}}),
            space_id=uuid4(),
            run_id="run-1",
            progress_observer=cast("object", observer),
        )
    )
    brief_verified = await research_init_guarded.maybe_verify_guarded_brief_generation(
        services=_services_with_workspace({"brief": "ready"}),
        space_id=uuid4(),
        run_id="run-1",
        progress_observer=cast("object", observer),
    )

    assert structured_verified is True
    assert brief_verified is True
    assert observer.structured_snapshot == {"source_results": {"clinvar": {}}}
    assert observer.brief_snapshot == {"brief": "ready"}


@pytest.mark.asyncio
async def test_guarded_chase_skip_uses_observer_snapshot() -> None:
    observer = _ChaseSkipObserver()

    should_skip = await research_init_guarded.maybe_skip_guarded_chase_round(
        services=_services_with_workspace({"pending_chase_round": {"round_number": 2}}),
        space_id=uuid4(),
        run_id="run-1",
        next_round_number=2,
        progress_observer=cast("object", observer),
    )

    assert should_skip is True
    assert observer.next_round_number == 2
    assert observer.workspace_snapshot == {"pending_chase_round": {"round_number": 2}}


class _StructuredSourceObserver:
    workspace_snapshot: JSONObject | None = None

    async def maybe_select_structured_enrichment_sources(
        self,
        *,
        available_source_keys: tuple[str, ...],
        workspace_snapshot: JSONObject,
    ) -> tuple[object, ...]:
        assert available_source_keys == ("clinvar", "drugbank")
        self.workspace_snapshot = workspace_snapshot
        return ("drugbank", "missing", "drugbank", 7, "clinvar")


class _ChaseSelectionObserver:
    workspace_snapshot: JSONObject | None = None

    async def maybe_select_chase_round_selection(
        self,
        *,
        round_number: int,
        chase_candidates: tuple[ResearchOrchestratorChaseCandidate, ...],
        deterministic_selection: research_init_guarded.ResearchOrchestratorChaseSelection,
        workspace_snapshot: JSONObject,
    ) -> dict[str, object]:
        assert round_number == 1
        assert [candidate.display_label for candidate in chase_candidates] == [
            "CDK8",
            "MED12",
        ]
        assert deterministic_selection.selected_entity_ids == ["entity-1", "entity-2"]
        self.workspace_snapshot = workspace_snapshot
        return {
            "selected_entity_ids": ["entity-1", "entity-2"],
            "selected_labels": ["CDK8", "MED12"],
            "stop_instead": False,
            "stop_reason": None,
            "selection_basis": "Keep both bounded chase candidates.",
        }


class _VerificationObserver:
    structured_snapshot: JSONObject | None = None
    brief_snapshot: JSONObject | None = None

    async def verify_guarded_structured_enrichment(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        self.structured_snapshot = workspace_snapshot
        return True

    def verify_guarded_brief_generation(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        self.brief_snapshot = workspace_snapshot
        return True


class _ChaseSkipObserver:
    next_round_number: int | None = None
    workspace_snapshot: JSONObject | None = None

    def maybe_skip_chase_round(
        self,
        *,
        next_round_number: int,
        workspace_snapshot: JSONObject,
    ) -> bool:
        self.next_round_number = next_round_number
        self.workspace_snapshot = workspace_snapshot
        return True


@dataclass(frozen=True, slots=True)
class _WorkspaceRecord:
    snapshot: JSONObject


class _ArtifactStore:
    def __init__(self, snapshot: JSONObject) -> None:
        self._snapshot = snapshot

    def get_workspace(
        self,
        *,
        space_id: UUID,
        run_id: str,
    ) -> _WorkspaceRecord:
        del space_id, run_id
        return _WorkspaceRecord(snapshot=self._snapshot)


@dataclass(frozen=True, slots=True)
class _Services:
    artifact_store: _ArtifactStore


def _services_with_workspace(snapshot: JSONObject) -> HarnessExecutionServices:
    return cast(
        "HarnessExecutionServices",
        _Services(artifact_store=_ArtifactStore(snapshot)),
    )


def _chase_preparation() -> _ChaseRoundPreparation:
    candidates = (
        ResearchOrchestratorChaseCandidate(
            entity_id="entity-1",
            display_label="CDK8",
            normalized_label="CDK8",
            candidate_rank=1,
            observed_round=1,
            available_source_keys=["clinvar"],
            evidence_basis="Candidate one.",
            novelty_basis="not_in_previous_seed_terms",
        ),
        ResearchOrchestratorChaseCandidate(
            entity_id="entity-2",
            display_label="MED12",
            normalized_label="MED12",
            candidate_rank=2,
            observed_round=1,
            available_source_keys=["marrvel"],
            evidence_basis="Candidate two.",
            novelty_basis="not_in_previous_seed_terms",
        ),
    )
    return _ChaseRoundPreparation(
        candidates=candidates,
        filtered_candidates=(),
        deterministic_selection=research_init_guarded.ResearchOrchestratorChaseSelection(
            selected_entity_ids=["entity-1", "entity-2"],
            selected_labels=["CDK8", "MED12"],
            stop_instead=False,
            stop_reason=None,
            selection_basis="Deterministic chase selection.",
        ),
        errors=[],
    )
