"""Unit tests for the Phase 2 shadow planner helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    orchestrator_action_registry,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    ShadowPlannerRecommendationOutput,
    ShadowPlannerRecommendationResult,
    _build_shadow_planner_prompt,
    build_shadow_planner_comparison,
    build_shadow_planner_workspace_summary,
    load_shadow_planner_prompt,
    planner_action_registry_by_state,
    planner_live_action_types,
    recommend_shadow_planner_action,
    shadow_planner_prompt_version,
    validate_shadow_planner_output,
)

from src.infrastructure.llm.costs import calculate_openai_usage_cost_usd


def _install_shadow_planner_test_doubles(
    monkeypatch: pytest.MonkeyPatch,
    *,
    harness_cls: type[object],
    store_factory: object | None = None,
) -> None:
    @dataclass(frozen=True)
    class _FakeModelSpec:
        model_id: str = "gpt-5.4"
        timeout_seconds: float = 30.0

    class _FakeRegistry:
        def get_default_model(self, _capability: object) -> _FakeModelSpec:
            return _FakeModelSpec()

    class _FakeStore:
        async def close(self) -> None:
            return None

    class _FakeKernel:
        def __init__(self, **_: object) -> None:
            return None

        async def close(self) -> None:
            return None

    class _FakeLiteLLMAdapter:
        def __init__(self, **_: object) -> None:
            return None

    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.get_model_registry",
        lambda: _FakeRegistry(),
    )
    selected_store_factory = (
        store_factory if callable(store_factory) else (lambda: _FakeStore())
    )
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.create_artana_postgres_store",
        selected_store_factory,
    )

    import artana.harness
    import artana.kernel
    import artana.ports.model

    monkeypatch.setattr(artana.harness, "StrongModelAgentHarness", harness_cls)
    monkeypatch.setattr(artana.kernel, "ArtanaKernel", _FakeKernel)
    monkeypatch.setattr(artana.ports.model, "LiteLLMAdapter", _FakeLiteLLMAdapter)


def test_planner_registry_exposes_live_context_only_and_reserved_actions() -> None:
    grouped = planner_action_registry_by_state(
        action_registry=orchestrator_action_registry(),
    )
    live_types = planner_live_action_types(
        action_registry=orchestrator_action_registry(),
    )

    assert "live" in grouped
    assert "context_only" in grouped
    assert "reserved" in grouped
    assert ResearchOrchestratorActionType.QUERY_PUBMED in live_types
    assert ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED in live_types
    assert ResearchOrchestratorActionType.RUN_GRAPH_CONNECTION not in live_types


def test_shadow_planner_prompt_includes_source_selection_guidance() -> None:
    prompt = load_shadow_planner_prompt()

    assert "Source selection guidance" in prompt
    assert "INGEST_AND_EXTRACT_PUBMED" in prompt
    assert "`drugbank`" in prompt
    assert "`clinical_trials`" in prompt
    assert "`marrvel`, `mgi`, and `zfin`" in prompt
    assert "`alphafold`" in prompt
    assert "drug repurposing" in prompt
    assert "pending_structured_enrichment_source_keys" in prompt
    assert "objective_routing_hints.preferred_pending_structured_sources" in prompt
    assert "Source taxonomy:" in prompt
    assert "live_evidence=" in prompt
    assert "context_only=" in prompt
    assert "grounding=" in prompt
    assert "reserved=" in prompt
    assert "grounding=ontology or normalization references such as `mondo`" in prompt
    assert "reserved=known but not yet first-class planner sources" in prompt
    assert (
        "Objective-based source hints apply only after literature ingest is complete"
        in prompt
    )
    assert "threshold was not met" in prompt
    assert "synthesis_readiness.ready_for_brief" in prompt
    assert "do not use `synthesis_readiness.ready_for_brief` by itself" in prompt
    assert "prefer a bounded `RUN_CHASE_ROUND` over `STOP`" in prompt
    assert "chase_decision_posture" in prompt
    assert "`continue_objective_relevant`" in prompt
    assert "synthesis_readiness.summary" in prompt


def test_workspace_summary_is_checkpoint_scoped_and_size_bounded() -> None:
    summary = build_shadow_planner_workspace_summary(
        checkpoint_key="after_bootstrap",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=20,
        workspace_snapshot={
            "current_round": 1,
            "documents_ingested": 3,
            "proposal_count": 4,
            "pending_questions": ["q1"],
            "errors": [],
            "evidence_gaps": ["gap1", "gap2", "gap3", "gap4", "gap5", "gap6"],
            "contradictions": ["conflict1", "conflict2"],
            "source_results": {
                "pubmed": {
                    "status": "completed",
                    "documents_discovered": 5,
                    "documents_selected": 5,
                    "documents_ingested": 3,
                },
                "clinvar": {"status": "completed", "records_processed": 2},
            },
        },
        prior_decisions=[{"decision_id": f"d-{index}"} for index in range(12)],
        action_registry=orchestrator_action_registry(),
    )

    assert summary["checkpoint_key"] == "after_bootstrap"
    assert summary["current_round"] == 1
    assert summary["counts"]["proposal_count"] == 4
    assert len(summary["top_evidence_gaps"]) == 5
    assert len(summary["prior_decisions"]) == 10
    assert "live" in summary["planner_actions"]
    assert summary["planner_constraints"]["pubmed_source_key"] == "pubmed"
    assert summary["planner_constraints"]["pubmed_ingest_pending"] is True
    assert summary["source_taxonomy"] == {
        "live_evidence": ["pubmed", "clinvar"],
        "context_only": [],
        "grounding": [],
        "reserved": [],
    }
    assert summary["planner_constraints"]["source_taxonomy"] == {
        "live_evidence": ["pubmed", "clinvar"],
        "context_only": [],
        "grounding": [],
        "reserved": [],
    }
    assert summary["planner_constraints"]["live_action_types"] == [
        "RUN_CHASE_ROUND",
        "STOP",
    ]
    assert summary["planner_constraints"]["source_required_action_types"] == []
    assert "RUN_CHASE_ROUND" in (
        summary["planner_constraints"]["control_action_types_without_source_key"]
    )
    assert "STOP" in (
        summary["planner_constraints"]["control_action_types_without_source_key"]
    )
    assert summary["planner_constraints"]["structured_enrichment_source_keys"] == [
        "clinvar"
    ]
    assert summary["synthesis_readiness"]["ready_for_brief"] is False
    assert summary["synthesis_readiness"]["no_pending_questions"] is False
    assert summary["synthesis_readiness"]["no_evidence_gaps"] is False
    assert summary["chase_decision_posture"]["posture"] == "stop_threshold_not_met"


def test_workspace_summary_exposes_exact_source_taxonomy_membership() -> None:
    summary = build_shadow_planner_workspace_summary(
        checkpoint_key="after_pubmed_ingest_extract",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "clinvar": True,
            "drugbank": True,
            "alphafold": True,
            "clinical_trials": True,
            "mgi": True,
            "zfin": True,
            "marrvel": True,
            "pdf": True,
            "text": True,
            "mondo": True,
            "uniprot": True,
            "hgnc": True,
        },
        max_depth=2,
        max_hypotheses=20,
        workspace_snapshot={},
        prior_decisions=[],
        action_registry=orchestrator_action_registry(),
    )

    expected_taxonomy = {
        "live_evidence": [
            "pubmed",
            "clinvar",
            "drugbank",
            "alphafold",
            "clinical_trials",
            "mgi",
            "zfin",
            "marrvel",
        ],
        "context_only": ["pdf", "text"],
        "grounding": ["mondo"],
        "reserved": ["uniprot", "hgnc"],
    }

    assert summary["source_taxonomy"] == expected_taxonomy
    assert summary["planner_constraints"]["source_taxonomy"] == expected_taxonomy
    assert "mondo" not in summary["source_taxonomy"]["live_evidence"]
    assert summary["source_taxonomy"]["reserved"] == ["uniprot", "hgnc"]


def test_workspace_summary_preserves_deterministic_structured_source_order() -> None:
    summary = build_shadow_planner_workspace_summary(
        checkpoint_key="after_pubmed_ingest_extract",
        objective="Investigate BRCA1 and PARP inhibitor response",
        seed_terms=["BRCA1", "PARP inhibitor"],
        sources={
            "pubmed": True,
            "alphafold": True,
            "drugbank": True,
            "clinvar": True,
            "clinical_trials": True,
        },
        max_depth=1,
        max_hypotheses=5,
        workspace_snapshot={},
        prior_decisions=[],
        action_registry=orchestrator_action_registry(),
    )

    assert summary["planner_constraints"]["structured_enrichment_source_keys"] == [
        "clinvar",
        "drugbank",
        "alphafold",
        "clinical_trials",
    ]
    assert summary["planner_constraints"][
        "pending_structured_enrichment_source_keys"
    ] == [
        "clinvar",
        "drugbank",
        "alphafold",
        "clinical_trials",
    ]


def test_shadow_planner_prompt_keeps_chase_checkpoint_actions_bounded() -> None:
    summary = build_shadow_planner_workspace_summary(
        checkpoint_key="after_bootstrap",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=20,
        workspace_snapshot={
            "pending_chase_round": {
                "chase_candidates": [
                    {
                        "entity_id": "entity-1",
                        "display_label": "PARP1",
                        "normalized_label": "PARP1",
                        "candidate_rank": 1,
                        "observed_round": 1,
                        "available_source_keys": ["clinvar"],
                        "evidence_basis": "Recent graph entity.",
                        "novelty_basis": "not_in_previous_seed_terms",
                    }
                ],
                "filtered_chase_candidates": [
                    {
                        "entity_id": "entity-2",
                        "display_label": "result 1",
                        "normalized_label": "RESULT 1",
                        "observed_rank": 2,
                        "observed_round": 1,
                        "filter_reason": "generic_result_label",
                    }
                ],
                "deterministic_selection": {
                    "selected_entity_ids": ["entity-1"],
                    "selected_labels": ["PARP1"],
                    "selection_basis": "The deterministic chase set is ready.",
                    "stop_instead": False,
                    "stop_reason": None,
                },
                "deterministic_candidate_count": 1,
                "filtered_chase_candidate_count": 1,
                "filtered_chase_filter_reason_counts": {
                    "generic_result_label": 1,
                },
                "deterministic_chase_threshold": 3,
                "deterministic_threshold_met": True,
            }
        },
        prior_decisions=[],
        action_registry=orchestrator_action_registry(),
    )

    assert summary["filtered_chase_candidate_count"] == 1
    assert summary["filtered_chase_filter_reason_counts"] == {
        "generic_result_label": 1,
    }
    assert summary["filtered_chase_candidates"][0]["display_label"] == "result 1"
    assert summary["chase_decision_posture"]["posture"] == "planner_discretion"
    prompt = _build_shadow_planner_prompt(workspace_summary=summary)

    assert "action_type must be exactly one of: RUN_CHASE_ROUND, STOP" in prompt
    assert "instead of switching to GENERATE_BRIEF" in prompt


def test_workspace_summary_marks_objective_relevant_chase_posture() -> None:
    summary = build_shadow_planner_workspace_summary(
        checkpoint_key="after_bootstrap",
        objective="Investigate BRCA1 and PARP inhibitor response",
        seed_terms=["BRCA1", "PARP inhibitor"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=20,
        workspace_snapshot={
            "pending_chase_round": {
                "chase_candidates": [
                    {
                        "entity_id": "entity-1",
                        "display_label": "PARP inhibitor sensitivity",
                        "normalized_label": "PARP INHIBITOR SENSITIVITY",
                        "candidate_rank": 1,
                        "observed_round": 1,
                        "available_source_keys": ["clinvar"],
                        "evidence_basis": "Recent graph entity.",
                        "novelty_basis": "not_in_previous_seed_terms",
                    },
                    {
                        "entity_id": "entity-2",
                        "display_label": "olaparib response",
                        "normalized_label": "OLAPARIB RESPONSE",
                        "candidate_rank": 2,
                        "observed_round": 1,
                        "available_source_keys": ["clinvar"],
                        "evidence_basis": "Recent graph entity.",
                        "novelty_basis": "not_in_previous_seed_terms",
                    },
                ],
                "deterministic_selection": {
                    "selected_entity_ids": ["entity-1", "entity-2"],
                    "selected_labels": [
                        "PARP inhibitor sensitivity",
                        "olaparib response",
                    ],
                    "selection_basis": "The deterministic chase set is ready.",
                    "stop_instead": False,
                    "stop_reason": None,
                },
                "deterministic_threshold_met": True,
            }
        },
        prior_decisions=[],
        action_registry=orchestrator_action_registry(),
    )

    posture = summary["chase_decision_posture"]

    assert posture["posture"] == "continue_objective_relevant"
    assert posture["objective_relevant_labels"] == [
        "PARP inhibitor sensitivity",
        "olaparib response",
    ]


def test_workspace_summary_adds_objective_routing_hints_for_structured_sources() -> (
    None
):
    summary = build_shadow_planner_workspace_summary(
        checkpoint_key="after_pubmed_ingest_extract",
        objective="Investigate BRCA1 and PARP inhibitor response",
        seed_terms=["BRCA1", "PARP inhibitor"],
        sources={
            "pubmed": True,
            "alphafold": True,
            "drugbank": True,
            "clinvar": True,
            "clinical_trials": True,
        },
        max_depth=1,
        max_hypotheses=5,
        workspace_snapshot={},
        prior_decisions=[],
        action_registry=orchestrator_action_registry(),
    )

    assert summary["objective_routing_hints"]["objective_tags"] == ["drug_mechanism"]
    assert summary["objective_routing_hints"]["preferred_structured_sources"] == [
        "drugbank",
        "clinical_trials",
        "clinvar",
        "alphafold",
    ]
    assert summary["objective_routing_hints"][
        "preferred_pending_structured_sources"
    ] == [
        "drugbank",
        "clinical_trials",
        "clinvar",
        "alphafold",
    ]
    assert "therapy or inhibitor questions" in (
        summary["objective_routing_hints"]["summary"]
    )


def test_workspace_summary_defers_objective_source_hints_until_after_pubmed_ingest() -> (
    None
):
    summary = build_shadow_planner_workspace_summary(
        checkpoint_key="after_pubmed_discovery",
        objective="Investigate BRCA1 and PARP inhibitor response",
        seed_terms=["BRCA1", "PARP inhibitor"],
        sources={
            "pubmed": True,
            "drugbank": True,
            "clinvar": True,
        },
        max_depth=1,
        max_hypotheses=5,
        workspace_snapshot={
            "source_results": {
                "pubmed": {
                    "status": "completed",
                    "documents_discovered": 6,
                    "documents_selected": 4,
                    "documents_ingested": 0,
                }
            }
        },
        prior_decisions=[],
        action_registry=orchestrator_action_registry(),
    )

    assert summary["planner_constraints"]["pubmed_ingest_pending"] is True
    assert (
        summary["objective_routing_hints"]["preferred_pending_structured_sources"] == []
    )
    assert "stay inactive until PubMed ingest and extraction are complete" in (
        summary["objective_routing_hints"]["summary"]
    )


def test_validate_shadow_planner_output_rejects_non_live_or_invalid_outputs() -> None:
    reserved_output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.RUN_GRAPH_CONNECTION,
        source_key=None,
        evidence_basis="Need a graph step.",
        qualitative_rationale="The evidence looks ready for a graph connection step.",
    )
    disabled_source_output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
        source_key="clinvar",
        evidence_basis="A structured follow up is available.",
        qualitative_rationale="The run should broaden evidence through a structured source.",
    )
    numeric_style_output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
        source_key="pubmed",
        evidence_basis="Start with literature.",
        qualitative_rationale="PubMed is the top choice with 90 percent confidence.",
    )
    missing_source_output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
        source_key=None,
        evidence_basis="A structured follow up is available.",
        qualitative_rationale="The run should broaden evidence through a structured source.",
    )
    invalid_control_source_output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
        source_key="pubmed",
        evidence_basis="The evidence is ready for synthesis.",
        qualitative_rationale="The current run has enough grounded evidence to produce the brief.",
    )
    stop_without_reason_output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.STOP,
        source_key=None,
        evidence_basis="No grounded action remains.",
        qualitative_rationale="The available live actions would not add meaningful evidence right now.",
    )
    count_based_output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
        source_key="pubmed",
        evidence_basis="PubMed has not been queried yet.",
        qualitative_rationale=(
            "Start with PubMed because the run still has 0 ingested documents and "
            "needs grounded literature before structured follow-up."
        ),
    )

    registry = orchestrator_action_registry()
    assert (
        validate_shadow_planner_output(
            output=reserved_output,
            sources={"pubmed": True, "clinvar": True},
            action_registry=registry,
        )
        == "action_not_live"
    )
    assert (
        validate_shadow_planner_output(
            output=disabled_source_output,
            sources={"pubmed": True, "clinvar": False},
            action_registry=registry,
        )
        == "source_disabled"
    )
    assert (
        validate_shadow_planner_output(
            output=numeric_style_output,
            sources={"pubmed": True},
            action_registry=registry,
        )
        == "numeric_style_ranking_not_allowed"
    )
    assert (
        validate_shadow_planner_output(
            output=missing_source_output,
            sources={"pubmed": True, "clinvar": True},
            action_registry=registry,
        )
        == "source_key_required"
    )
    assert (
        validate_shadow_planner_output(
            output=invalid_control_source_output,
            sources={"pubmed": True},
            action_registry=registry,
        )
        == "source_key_not_allowed"
    )
    assert (
        validate_shadow_planner_output(
            output=stop_without_reason_output,
            sources={"pubmed": True},
            action_registry=registry,
        )
        == "stop_reason_required"
    )
    assert (
        validate_shadow_planner_output(
            output=ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                source_key="clinvar",
                evidence_basis="ClinVar is the strongest structured follow-up source.",
                qualitative_rationale=(
                    "Use ClinVar next because variant evidence will be useful once "
                    "the literature stage is grounded."
                ),
            ),
            workspace_summary={
                "checkpoint_key": "after_pubmed_discovery",
                "planner_constraints": {
                    "pubmed_ingest_pending": True,
                },
            },
            sources={"pubmed": True, "clinvar": True},
            action_registry=registry,
        )
        == "pubmed_ingest_required"
    )
    assert (
        validate_shadow_planner_output(
            output=ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
                source_key=None,
                evidence_basis="The evidence is already sufficient for synthesis.",
                qualitative_rationale=(
                    "Generate the brief because the work is already complete."
                ),
            ),
            workspace_summary={"checkpoint_key": "before_terminal_stop"},
            sources={"pubmed": True},
            action_registry=registry,
        )
        == "terminal_stop_required"
    )
    assert (
        validate_shadow_planner_output(
            output=count_based_output,
            sources={"pubmed": True},
            action_registry=registry,
        )
        is None
    )


@pytest.mark.asyncio
async def test_shadow_planner_fallback_records_prompt_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_first_action",
        objective="Investigate MED13 syndrome",
        workspace_summary={"objective": "Investigate MED13 syndrome", "counts": {}},
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "unavailable"
    assert result.used_fallback is True
    assert result.prompt_version == shadow_planner_prompt_version()
    assert result.decision.metadata["prompt_version"] == shadow_planner_prompt_version()
    assert result.telemetry is not None
    assert result.telemetry.status == "unavailable"


@pytest.mark.asyncio
async def test_shadow_planner_fallback_is_checkpoint_aware_for_chase_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_bootstrap",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "objective": "Investigate BRCA1 and PARP inhibitor response",
            "counts": {"proposal_count": 1},
            "chase_candidates": [
                {
                    "entity_id": "entity-1",
                    "display_label": "PARP1",
                    "normalized_label": "PARP1",
                    "candidate_rank": 1,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar", "drugbank"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
                {
                    "entity_id": "entity-2",
                    "display_label": "ATM",
                    "normalized_label": "ATM",
                    "candidate_rank": 2,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar", "drugbank"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
                {
                    "entity_id": "entity-3",
                    "display_label": "ATR",
                    "normalized_label": "ATR",
                    "candidate_rank": 3,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar", "drugbank"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
            ],
            "deterministic_selection": {
                "selected_entity_ids": ["entity-1", "entity-2", "entity-3"],
                "selected_labels": ["PARP1", "ATM", "ATR"],
                "stop_instead": False,
                "stop_reason": None,
                "selection_basis": "Deterministic chase selection.",
            },
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "unavailable"
    assert result.used_fallback is True
    assert result.decision.action_type is ResearchOrchestratorActionType.RUN_CHASE_ROUND
    assert result.decision.source_key is None
    assert result.decision.action_input["selected_entity_ids"] == [
        "entity-1",
        "entity-2",
        "entity-3",
    ]


@pytest.mark.asyncio
async def test_shadow_planner_fallback_prefers_pubmed_ingest_after_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_pubmed_discovery",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "objective": "Investigate BRCA1 and PARP inhibitor response",
            "source_status_summary": {
                "pubmed": {
                    "status": "completed",
                    "documents_discovered": 6,
                    "documents_selected": 4,
                    "documents_ingested": 0,
                }
            },
            "counts": {"documents_ingested": 0, "proposal_count": 0},
        },
        sources={"pubmed": True, "drugbank": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "unavailable"
    assert result.used_fallback is True
    assert (
        result.decision.action_type
        is ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED
    )
    assert result.decision.source_key == "pubmed"


@pytest.mark.asyncio
async def test_shadow_planner_fallback_prefers_objective_relevant_structured_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_pubmed_ingest_extract",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "objective": "Investigate BRCA1 and PARP inhibitor response",
            "counts": {"documents_ingested": 10, "proposal_count": 17},
        },
        sources={
            "pubmed": True,
            "alphafold": True,
            "drugbank": True,
            "clinvar": True,
        },
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "unavailable"
    assert result.used_fallback is True
    assert (
        result.decision.action_type
        is ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT
    )
    assert result.decision.source_key == "drugbank"


@pytest.mark.asyncio
async def test_shadow_planner_fallback_prefers_model_organism_sources_when_relevant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_driven_terms_ready",
        objective="Investigate MED13 and congenital heart disease",
        workspace_summary={
            "objective": "Investigate MED13 and congenital heart disease",
            "counts": {"documents_ingested": 6, "proposal_count": 9},
        },
        sources={
            "pubmed": True,
            "clinvar": True,
            "marrvel": True,
            "mgi": True,
            "zfin": True,
        },
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "unavailable"
    assert result.used_fallback is True
    assert (
        result.decision.action_type
        is ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT
    )
    assert result.decision.source_key == "marrvel"


@pytest.mark.asyncio
async def test_shadow_planner_fallback_stops_after_skipped_chase_round(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_bootstrap",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "objective": "Investigate BRCA1 and PARP inhibitor response",
            "counts": {"proposal_count": 17},
            "chase_candidates": [
                {
                    "entity_id": "entity-1",
                    "display_label": "PARP1",
                    "normalized_label": "PARP1",
                    "candidate_rank": 1,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                }
            ],
            "deterministic_selection": {
                "selected_entity_ids": [],
                "selected_labels": [],
                "stop_instead": True,
                "stop_reason": "threshold_not_met",
                "selection_basis": "Too few deterministic chase candidates.",
            },
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "unavailable"
    assert result.used_fallback is True
    assert result.decision.action_type is ResearchOrchestratorActionType.STOP
    assert result.decision.source_key is None
    assert result.decision.stop_reason == "threshold_not_met"


@pytest.mark.asyncio
async def test_shadow_planner_fallback_generates_brief_when_workspace_is_ready_for_synthesis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_brief_generation",
        objective="Investigate CFTR and cystic fibrosis",
        workspace_summary={
            "checkpoint_key": "before_brief_generation",
            "objective": "Investigate CFTR and cystic fibrosis",
            "counts": {
                "documents_ingested": 10,
                "proposal_count": 24,
                "pending_question_count": 0,
                "evidence_gap_count": 0,
                "contradiction_count": 0,
                "error_count": 0,
            },
            "source_status_summary": {
                "pubmed": {"status": "completed", "documents_ingested": 10},
                "clinvar": {"status": "completed", "records_processed": 12},
                "drugbank": {"status": "completed", "records_processed": 3},
            },
        },
        sources={"pubmed": True, "clinvar": True, "drugbank": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "unavailable"
    assert result.used_fallback is True
    assert result.decision.action_type is ResearchOrchestratorActionType.GENERATE_BRIEF
    assert result.decision.source_key is None


@pytest.mark.asyncio
async def test_shadow_planner_fallback_keeps_chase_round_when_structured_work_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_bootstrap",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "objective": "Investigate BRCA1 and PARP inhibitor response",
            "counts": {
                "documents_ingested": 10,
                "proposal_count": 24,
                "pending_question_count": 0,
                "evidence_gap_count": 0,
                "contradiction_count": 0,
                "error_count": 0,
            },
            "source_status_summary": {
                "pubmed": {"status": "completed", "documents_ingested": 10},
                "clinvar": {"status": "completed", "records_processed": 12},
                "drugbank": {"status": "pending", "records_processed": 0},
            },
            "chase_candidates": [
                {
                    "entity_id": "entity-1",
                    "display_label": "PARP1",
                    "normalized_label": "PARP1",
                    "candidate_rank": 1,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar", "drugbank"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
                {
                    "entity_id": "entity-2",
                    "display_label": "ATM",
                    "normalized_label": "ATM",
                    "candidate_rank": 2,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar", "drugbank"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
                {
                    "entity_id": "entity-3",
                    "display_label": "ATR",
                    "normalized_label": "ATR",
                    "candidate_rank": 3,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar", "drugbank"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
            ],
            "deterministic_selection": {
                "selected_entity_ids": ["entity-1", "entity-2", "entity-3"],
                "selected_labels": ["PARP1", "ATM", "ATR"],
                "stop_instead": False,
                "stop_reason": None,
                "selection_basis": "Deterministic chase selection.",
            },
        },
        sources={"pubmed": True, "clinvar": True, "drugbank": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "unavailable"
    assert result.used_fallback is True
    assert result.decision.action_type is ResearchOrchestratorActionType.RUN_CHASE_ROUND
    assert result.decision.source_key is None
    assert result.decision.action_input["selected_labels"] == ["PARP1", "ATM", "ATR"]


def test_validate_shadow_planner_output_rejects_unknown_chase_entity() -> None:
    output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        source_key=None,
        evidence_basis="The bounded chase round should continue.",
        qualitative_rationale="Continue with the strongest bounded chase leads.",
        selected_entity_ids=["entity-missing"],
        selected_labels=["PARP1"],
        selection_basis="The candidate remains relevant after bootstrap.",
    )

    assert (
        validate_shadow_planner_output(
            output=output,
            workspace_summary={
                "checkpoint_key": "after_bootstrap",
                "chase_candidates": [
                    {
                        "entity_id": "entity-1",
                        "display_label": "PARP1",
                        "normalized_label": "PARP1",
                        "candidate_rank": 1,
                        "observed_round": 1,
                        "available_source_keys": ["clinvar"],
                        "evidence_basis": "Recent graph entity.",
                        "novelty_basis": "not_in_previous_seed_terms",
                    }
                ],
            },
            sources={"pubmed": True, "clinvar": True},
            action_registry=orchestrator_action_registry(),
        )
        == "chase_selection_unknown_entity"
    )


def test_validate_shadow_planner_output_rejects_empty_chase_selection() -> None:
    output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        source_key=None,
        evidence_basis="The bounded chase round should continue.",
        qualitative_rationale="Continue with the strongest bounded chase leads.",
    )

    assert (
        validate_shadow_planner_output(
            output=output,
            workspace_summary={
                "checkpoint_key": "after_bootstrap",
                "chase_candidates": [
                    {
                        "entity_id": "entity-1",
                        "display_label": "PARP1",
                        "normalized_label": "PARP1",
                        "candidate_rank": 1,
                        "observed_round": 1,
                        "available_source_keys": ["clinvar"],
                        "evidence_basis": "Recent graph entity.",
                        "novelty_basis": "not_in_previous_seed_terms",
                    }
                ],
            },
            sources={"pubmed": True, "clinvar": True},
            action_registry=orchestrator_action_registry(),
        )
        == "chase_selection_required"
    )


def test_validate_shadow_planner_output_allows_stop_when_chase_threshold_is_met() -> (
    None
):
    output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.STOP,
        source_key=None,
        evidence_basis="The chase set still looks weak enough to stop.",
        qualitative_rationale=(
            "Stop because the next chase step does not add enough value."
        ),
        stop_reason="synthesis_ready",
    )

    validation_error = validate_shadow_planner_output(
        output=output,
        workspace_summary={
            "checkpoint_key": "after_bootstrap",
            "chase_candidates": [
                {
                    "entity_id": "entity-1",
                    "display_label": "PARP1",
                    "normalized_label": "PARP1",
                    "candidate_rank": 1,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                }
            ],
            "deterministic_selection": {
                "selected_entity_ids": ["entity-1"],
                "selected_labels": ["PARP1"],
                "selection_basis": "The deterministic chase set is ready.",
                "stop_instead": False,
                "stop_reason": None,
            },
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
    )

    assert validation_error is None


def test_validate_shadow_planner_output_rejects_stop_for_objective_relevant_chase() -> (
    None
):
    output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.STOP,
        source_key=None,
        evidence_basis="The run looks ready for synthesis.",
        qualitative_rationale=(
            "Stop because the workflow appears ready to synthesize."
        ),
        stop_reason="synthesis_ready",
    )

    validation_error = validate_shadow_planner_output(
        output=output,
        workspace_summary={
            "checkpoint_key": "after_bootstrap",
            "objective": "Investigate BRCA1 and PARP inhibitor response",
            "seed_terms": ["BRCA1", "PARP inhibitor"],
            "chase_candidates": [
                {
                    "entity_id": "entity-1",
                    "display_label": "PARP inhibitor sensitivity",
                    "normalized_label": "PARP INHIBITOR SENSITIVITY",
                    "candidate_rank": 1,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                }
            ],
            "deterministic_threshold_met": True,
            "deterministic_selection": {
                "selected_entity_ids": ["entity-1"],
                "selected_labels": ["PARP inhibitor sensitivity"],
                "selection_basis": "The deterministic chase set is ready.",
                "stop_instead": False,
                "stop_reason": None,
            },
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
    )

    assert validation_error == "objective_relevant_chase_required"


def test_validate_shadow_planner_output_rejects_generate_brief_at_chase_checkpoint() -> (
    None
):
    output = ShadowPlannerRecommendationOutput(
        action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
        source_key=None,
        evidence_basis="The run is already synthesis-ready.",
        qualitative_rationale=(
            "The evidence base is already sufficient and should move to synthesis."
        ),
    )

    assert (
        validate_shadow_planner_output(
            output=output,
            workspace_summary={"checkpoint_key": "after_bootstrap"},
            sources={"pubmed": True, "clinvar": True},
            action_registry=orchestrator_action_registry(),
        )
        == "chase_checkpoint_action_not_allowed"
    )


def test_build_shadow_planner_comparison_reads_threshold_stop_from_workspace_summary() -> (
    None
):
    planner_result = ShadowPlannerRecommendationResult(
        decision=ResearchOrchestratorDecision(
            decision_id="planner-after-bootstrap",
            round_number=0,
            action_type=ResearchOrchestratorActionType.STOP,
            action_input={},
            source_key=None,
            evidence_basis="The deterministic threshold was not met for another chase round.",
            stop_reason="threshold_not_met",
            step_key="fixture.shadow.after_bootstrap.stop",
            status="recommended",
            qualitative_rationale=(
                "Stop here because the bounded chase set is too weak for another round."
            ),
        ),
        planner_status="completed",
        model_id="fixture-shadow-model",
        agent_run_id="agent-after-bootstrap",
        prompt_version="fixture-prompt-v1",
        used_fallback=False,
        validation_error=None,
        error=None,
    )
    deterministic_target = ResearchOrchestratorDecision(
        decision_id="deterministic-after-bootstrap",
        round_number=1,
        action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        action_input={"round_number": 1},
        source_key=None,
        evidence_basis="The deterministic run exposes the next chase checkpoint.",
        stop_reason=None,
        step_key="fixture.after_bootstrap.run_chase_round",
        status="pending",
    )

    comparison = build_shadow_planner_comparison(
        checkpoint_key="after_bootstrap",
        planner_result=planner_result,
        deterministic_target=deterministic_target,
        workspace_summary={
            "checkpoint_key": "after_bootstrap",
            "deterministic_selection": {
                "selected_entity_ids": [],
                "selected_labels": [],
                "stop_instead": True,
                "stop_reason": "threshold_not_met",
                "selection_basis": (
                    "Fewer than the deterministic threshold of chase candidates "
                    "were available."
                ),
            },
        },
    )

    assert comparison["deterministic_stop_expected"] is True
    assert comparison["stop_match"] is True
    assert comparison["planner_conservative_stop"] is False
    assert comparison["planner_continued_when_threshold_stop"] is False
    assert comparison["comparison_status"] == "matched"


@pytest.mark.asyncio
async def test_shadow_planner_harness_path_returns_structured_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _FakeHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                source_key="pubmed",
                evidence_basis="Literature should lead the run.",
                qualitative_rationale=(
                    "Begin with PubMed so the next deterministic step is grounded in "
                    "retrieved evidence."
                ),
                expected_value_band="high",
                risk_level="low",
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_FakeHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_first_action",
        objective="Investigate MED13 syndrome",
        workspace_summary={
            "objective": "Investigate MED13 syndrome",
            "counts": {"documents_ingested": 0, "proposal_count": 0},
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "completed"
    assert result.used_fallback is False
    assert result.decision.action_type is ResearchOrchestratorActionType.QUERY_PUBMED
    assert result.decision.source_key == "pubmed"


@pytest.mark.asyncio
async def test_shadow_planner_harness_repairs_pubmed_ingest_stage_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _InvalidAfterDiscoveryHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                source_key="drugbank",
                evidence_basis="Drug mechanism evidence will matter next.",
                qualitative_rationale=(
                    "Use DrugBank because the objective is about inhibitor response."
                ),
                expected_value_band="medium",
                risk_level="low",
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_InvalidAfterDiscoveryHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_pubmed_discovery",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "checkpoint_key": "after_pubmed_discovery",
            "counts": {"documents_ingested": 0, "proposal_count": 0},
            "source_status_summary": {
                "pubmed": {
                    "status": "completed",
                    "documents_discovered": 8,
                    "documents_selected": 5,
                    "documents_ingested": 0,
                }
            },
        },
        sources={"pubmed": True, "clinvar": True, "drugbank": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.used_fallback is True
    assert result.validation_error == "pubmed_ingest_required"
    assert (
        result.decision.action_type
        is ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED
    )
    assert result.decision.source_key == "pubmed"


@pytest.mark.asyncio
async def test_shadow_planner_harness_repairs_terminal_checkpoint_violation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _InvalidTerminalHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
                source_key=None,
                evidence_basis="The evidence is already sufficient for synthesis.",
                qualitative_rationale=(
                    "Generate the brief because the evidence is already assembled."
                ),
                expected_value_band="medium",
                risk_level="low",
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_InvalidTerminalHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_terminal_stop",
        objective="Investigate MED13 and congenital heart disease",
        workspace_summary={
            "checkpoint_key": "before_terminal_stop",
            "counts": {"documents_ingested": 10, "proposal_count": 24},
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.used_fallback is True
    assert result.validation_error == "terminal_stop_required"
    assert result.decision.action_type is ResearchOrchestratorActionType.STOP
    assert result.decision.source_key is None
    assert result.decision.qualitative_rationale is not None
    assert result.telemetry is not None
    assert result.telemetry.status == "unavailable"


@pytest.mark.asyncio
async def test_shadow_planner_harness_repairs_chase_checkpoint_action_family(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _InvalidThenValidChaseHarness:
        def __init__(self, **_: object) -> None:
            self._call_count = 0

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            self._call_count += 1
            if self._call_count == 1:
                return ShadowPlannerRecommendationOutput(
                    action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
                    source_key=None,
                    evidence_basis="The workspace already feels synthesis-ready.",
                    qualitative_rationale=(
                        "Generate the brief because the evidence is already assembled."
                    ),
                    expected_value_band="medium",
                    risk_level="low",
                )
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                source_key=None,
                evidence_basis=(
                    "The bounded chase candidate set already clears the threshold "
                    "for one more chase step."
                ),
                qualitative_rationale=(
                    "Continue with the bounded chase round because the current "
                    "candidate set is still strong enough to justify one more "
                    "targeted follow-up."
                ),
                selected_entity_ids=["entity-1", "entity-2", "entity-3"],
                selected_labels=["PARP1", "ATM", "ATR"],
                selection_basis="The deterministic chase set is ready.",
                expected_value_band="medium",
                risk_level="low",
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_InvalidThenValidChaseHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_bootstrap",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "checkpoint_key": "after_bootstrap",
            "counts": {"proposal_count": 17},
            "chase_candidates": [
                {
                    "entity_id": "entity-1",
                    "display_label": "PARP1",
                    "normalized_label": "PARP1",
                    "candidate_rank": 1,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar", "drugbank"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
                {
                    "entity_id": "entity-2",
                    "display_label": "ATM",
                    "normalized_label": "ATM",
                    "candidate_rank": 2,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar", "drugbank"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
                {
                    "entity_id": "entity-3",
                    "display_label": "ATR",
                    "normalized_label": "ATR",
                    "candidate_rank": 3,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar", "drugbank"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
            ],
            "deterministic_selection": {
                "selected_entity_ids": ["entity-1", "entity-2", "entity-3"],
                "selected_labels": ["PARP1", "ATM", "ATR"],
                "stop_instead": False,
                "stop_reason": None,
                "selection_basis": "The deterministic chase set is ready.",
            },
        },
        sources={"pubmed": True, "clinvar": True, "drugbank": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "completed"
    assert result.used_fallback is False
    assert result.initial_validation_error == "chase_checkpoint_action_not_allowed"
    assert result.repair_attempted is True
    assert result.repair_succeeded is True
    assert result.validation_error is None
    assert result.decision.action_type is ResearchOrchestratorActionType.RUN_CHASE_ROUND
    assert result.decision.action_input["selected_labels"] == ["PARP1", "ATM", "ATR"]


@pytest.mark.asyncio
async def test_shadow_planner_collects_model_terminal_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana.events import EventType, ModelTerminalPayload

    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _FakeStore:
        async def get_events_for_run(self, _run_id: str) -> list[object]:
            return [
                SimpleNamespace(
                    event_type=EventType.MODEL_TERMINAL,
                    payload=ModelTerminalPayload(
                        kind="model_terminal",
                        outcome="completed",
                        model="gpt-5.4",
                        model_cycle_id="cycle-1",
                        source_model_requested_event_id="requested-1",
                        elapsed_ms=250,
                        prompt_tokens=120,
                        completion_tokens=30,
                        cost_usd=0.0042,
                    ),
                ),
            ]

        async def close(self) -> None:
            return None

    class _FakeHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                source_key="pubmed",
                evidence_basis="Literature should lead the run.",
                qualitative_rationale=(
                    "Begin with PubMed so the next deterministic step is grounded in "
                    "retrieved evidence."
                ),
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_FakeHarness,
        store_factory=lambda: _FakeStore(),
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_first_action",
        objective="Investigate MED13 syndrome",
        workspace_summary={
            "objective": "Investigate MED13 syndrome",
            "counts": {"documents_ingested": 0, "proposal_count": 0},
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.telemetry is not None
    assert result.telemetry.status == "available"
    assert result.telemetry.model_terminal_count == 1
    assert result.telemetry.prompt_tokens == 120
    assert result.telemetry.completion_tokens == 30
    assert result.telemetry.total_tokens == 150
    assert result.telemetry.cost_usd == pytest.approx(0.0042)
    assert result.telemetry.latency_seconds == pytest.approx(0.25)
    assert result.decision.metadata["telemetry"]["cost_usd"] == pytest.approx(0.0042)
    assert result.decision.metadata["telemetry"]["total_tokens"] == 150


@pytest.mark.asyncio
async def test_shadow_planner_prefers_trace_summary_cost_when_terminal_cost_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana.events import EventType, ModelTerminalPayload

    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _FakeStore:
        async def get_events_for_run(self, _run_id: str) -> list[object]:
            return [
                SimpleNamespace(
                    event_type=EventType.MODEL_TERMINAL,
                    payload=ModelTerminalPayload(
                        kind="model_terminal",
                        outcome="completed",
                        model="gpt-5.4",
                        model_cycle_id="cycle-1",
                        source_model_requested_event_id="requested-1",
                        elapsed_ms=250,
                        prompt_tokens=120,
                        completion_tokens=30,
                        cost_usd=0.0,
                    ),
                ),
            ]

        async def get_latest_run_summary(
            self,
            _run_id: str,
            summary_type: str,
        ) -> object | None:
            if summary_type != "trace::cost":
                return None
            return SimpleNamespace(
                summary_json=json.dumps(
                    {
                        "total_cost": 0.0042,
                        "budget_usd_limit": 1.0,
                    },
                ),
            )

        async def close(self) -> None:
            return None

    class _FakeHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                source_key="pubmed",
                evidence_basis="Literature should lead the run.",
                qualitative_rationale=(
                    "Begin with PubMed so the next deterministic step is grounded in "
                    "retrieved evidence."
                ),
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_FakeHarness,
        store_factory=lambda: _FakeStore(),
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_first_action",
        objective="Investigate MED13 syndrome",
        workspace_summary={
            "objective": "Investigate MED13 syndrome",
            "counts": {"documents_ingested": 0, "proposal_count": 0},
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.telemetry is not None
    assert result.telemetry.status == "available"
    assert result.telemetry.model_terminal_count == 1
    assert result.telemetry.prompt_tokens == 120
    assert result.telemetry.completion_tokens == 30
    assert result.telemetry.total_tokens == 150
    assert result.telemetry.cost_usd == pytest.approx(0.0042)
    assert result.decision.metadata["telemetry"]["cost_usd"] == pytest.approx(0.0042)


@pytest.mark.asyncio
async def test_shadow_planner_derives_cost_from_tokens_when_provider_reports_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from artana.events import EventType, ModelTerminalPayload

    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    prompt_tokens = 6402
    completion_tokens = 180
    expected_cost_usd = calculate_openai_usage_cost_usd(
        model_id="openai:gpt-5.4-mini",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    assert expected_cost_usd > 0.0

    class _FakeStore:
        async def get_events_for_run(self, _run_id: str) -> list[object]:
            return [
                SimpleNamespace(
                    event_type=EventType.MODEL_TERMINAL,
                    payload=ModelTerminalPayload(
                        kind="model_terminal",
                        outcome="completed",
                        model="openai/gpt-5.4-mini",
                        model_cycle_id="cycle-1",
                        source_model_requested_event_id="requested-1",
                        elapsed_ms=2435,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost_usd=0.0,
                    ),
                ),
            ]

        async def close(self) -> None:
            return None

    class _FakeHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                source_key="pubmed",
                evidence_basis="Literature should lead the run.",
                qualitative_rationale=(
                    "Begin with PubMed so the next deterministic step is grounded in "
                    "retrieved evidence."
                ),
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_FakeHarness,
        store_factory=lambda: _FakeStore(),
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_first_action",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "objective": "Investigate BRCA1 and PARP inhibitor response",
            "counts": {"documents_ingested": 0, "proposal_count": 0},
        },
        sources={"pubmed": True, "clinvar": True, "drugbank": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.telemetry is not None
    assert result.telemetry.status == "available"
    assert result.telemetry.cost_usd == pytest.approx(expected_cost_usd)
    assert result.decision.metadata["telemetry"]["cost_usd"] == pytest.approx(
        expected_cost_usd,
    )


@pytest.mark.asyncio
async def test_shadow_planner_normalizes_thin_workspace_summary_for_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )
    prompt_log: list[str] = []

    class _FakeHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(
            self, **kwargs: object
        ) -> ShadowPlannerRecommendationOutput:
            prompt_value = kwargs.get("prompt")
            if isinstance(prompt_value, str):
                prompt_log.append(prompt_value)
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                source_key="pubmed",
                evidence_basis="Literature should still lead the run.",
                qualitative_rationale=(
                    "Begin with PubMed because the run still needs grounded evidence."
                ),
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_FakeHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_first_action",
        objective="Investigate MED13 syndrome",
        workspace_summary={"objective": "Investigate MED13 syndrome"},
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "completed"
    assert prompt_log
    assert "Checkpoint guidance:" in prompt_log[0]
    assert "QUERY_PUBMED" in prompt_log[0]
    assert "RUN_STRUCTURED_ENRICHMENT" in prompt_log[0]


@pytest.mark.asyncio
async def test_shadow_planner_normalizes_default_pubmed_source_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _FakeHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                source_key=None,
                evidence_basis="Literature should still lead the run.",
                qualitative_rationale=(
                    "Begin with PubMed because the run still needs grounded evidence."
                ),
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_FakeHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_first_action",
        objective="Investigate MED13 syndrome",
        workspace_summary={
            "objective": "Investigate MED13 syndrome",
            "counts": {"documents_ingested": 0, "proposal_count": 0},
            "planner_constraints": {
                "live_action_types": ["QUERY_PUBMED", "RUN_STRUCTURED_ENRICHMENT"],
                "source_required_action_types": [
                    "QUERY_PUBMED",
                    "RUN_STRUCTURED_ENRICHMENT",
                ],
                "control_action_types_without_source_key": [],
                "pubmed_source_key": "pubmed",
                "structured_enrichment_source_keys": ["clinvar"],
            },
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "completed"
    assert result.used_fallback is False
    assert result.decision.source_key == "pubmed"
    assert result.validation_error is None


@pytest.mark.asyncio
async def test_shadow_planner_normalizes_missing_stop_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _FakeHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.STOP,
                source_key=None,
                evidence_basis="The workflow is already at its terminal checkpoint.",
                qualitative_rationale=(
                    "Stop because the workflow has already reached the terminal "
                    "boundary and no further bounded action is justified."
                ),
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_FakeHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_terminal_stop",
        objective="Investigate MED13 syndrome",
        workspace_summary={"objective": "Investigate MED13 syndrome"},
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "completed"
    assert result.used_fallback is False
    assert result.validation_error is None
    assert result.decision.action_type is ResearchOrchestratorActionType.STOP
    assert result.decision.stop_reason == "terminal_checkpoint"


@pytest.mark.asyncio
async def test_shadow_planner_harness_accepts_conservative_stop_when_threshold_is_met(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _InvalidChaseHarness:
        def __init__(self, **_: object) -> None:
            return None

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.STOP,
                source_key=None,
                evidence_basis="The run looks synthesis-ready.",
                qualitative_rationale=(
                    "Stop because the workflow appears ready to synthesize."
                ),
                stop_reason="synthesis_ready",
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_InvalidChaseHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_bootstrap",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "checkpoint_key": "after_bootstrap",
            "chase_candidates": [
                {
                    "entity_id": "entity-1",
                    "display_label": "PARP1",
                    "normalized_label": "PARP1",
                    "candidate_rank": 1,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
                {
                    "entity_id": "entity-2",
                    "display_label": "ATM",
                    "normalized_label": "ATM",
                    "candidate_rank": 2,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
                {
                    "entity_id": "entity-3",
                    "display_label": "ATR",
                    "normalized_label": "ATR",
                    "candidate_rank": 3,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                },
            ],
            "deterministic_selection": {
                "selected_entity_ids": ["entity-1", "entity-2", "entity-3"],
                "selected_labels": ["PARP1", "ATM", "ATR"],
                "selection_basis": "The deterministic chase set is ready.",
                "stop_instead": False,
                "stop_reason": None,
            },
            "planner_constraints": {
                "live_action_types": ["RUN_CHASE_ROUND", "STOP"],
                "source_required_action_types": [],
                "control_action_types_without_source_key": [
                    "RUN_CHASE_ROUND",
                    "STOP",
                ],
            },
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.used_fallback is False
    assert result.validation_error is None
    assert result.decision.action_type is ResearchOrchestratorActionType.STOP
    assert result.decision.stop_reason == "synthesis_ready"


@pytest.mark.asyncio
async def test_shadow_planner_repairs_stop_when_objective_relevant_chase_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _RepairingHarness:
        def __init__(self, **_: object) -> None:
            self._call_count = 0

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            self._call_count += 1
            if self._call_count == 1:
                return ShadowPlannerRecommendationOutput(
                    action_type=ResearchOrchestratorActionType.STOP,
                    source_key=None,
                    evidence_basis="The workflow looks synthesis-ready.",
                    qualitative_rationale=(
                        "Stop because the workflow appears ready to synthesize."
                    ),
                    stop_reason="synthesis_ready",
                )
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                source_key=None,
                evidence_basis=(
                    "The chase set includes an objective-relevant PARP inhibitor "
                    "response candidate."
                ),
                qualitative_rationale=(
                    "Continue with a bounded chase because the candidate directly "
                    "matches the BRCA1 and PARP inhibitor response objective."
                ),
                selected_entity_ids=["entity-1"],
                selected_labels=["PARP inhibitor sensitivity"],
                selection_basis=(
                    "Select the candidate that directly matches the therapy-response "
                    "focus of the objective."
                ),
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_RepairingHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="after_bootstrap",
        objective="Investigate BRCA1 and PARP inhibitor response",
        workspace_summary={
            "checkpoint_key": "after_bootstrap",
            "seed_terms": ["BRCA1", "PARP inhibitor"],
            "chase_candidates": [
                {
                    "entity_id": "entity-1",
                    "display_label": "PARP inhibitor sensitivity",
                    "normalized_label": "PARP INHIBITOR SENSITIVITY",
                    "candidate_rank": 1,
                    "observed_round": 1,
                    "available_source_keys": ["clinvar"],
                    "evidence_basis": "Recent graph entity.",
                    "novelty_basis": "not_in_previous_seed_terms",
                }
            ],
            "deterministic_threshold_met": True,
            "deterministic_selection": {
                "selected_entity_ids": ["entity-1"],
                "selected_labels": ["PARP inhibitor sensitivity"],
                "selection_basis": "The deterministic chase set is ready.",
                "stop_instead": False,
                "stop_reason": None,
            },
            "planner_constraints": {
                "live_action_types": ["RUN_CHASE_ROUND", "STOP"],
                "source_required_action_types": [],
                "control_action_types_without_source_key": [
                    "RUN_CHASE_ROUND",
                    "STOP",
                ],
            },
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "completed"
    assert result.used_fallback is False
    assert result.initial_validation_error == "objective_relevant_chase_required"
    assert result.repair_attempted is True
    assert result.repair_succeeded is True
    assert result.validation_error is None
    assert result.decision.action_type is ResearchOrchestratorActionType.RUN_CHASE_ROUND
    assert result.decision.action_input["selected_entity_ids"] == ["entity-1"]


@pytest.mark.asyncio
async def test_shadow_planner_repairs_invalid_numeric_output_before_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: True,
    )

    class _FakeHarness:
        def __init__(self, **_: object) -> None:
            self._call_count = 0

        async def run_agent(self, **_: object) -> ShadowPlannerRecommendationOutput:
            self._call_count += 1
            if self._call_count == 1:
                return ShadowPlannerRecommendationOutput(
                    action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                    source_key="pubmed",
                    evidence_basis="Start with literature.",
                    qualitative_rationale="PubMed is the top choice with 90 percent confidence.",
                )
            return ShadowPlannerRecommendationOutput(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                source_key="pubmed",
                evidence_basis="Start with literature.",
                qualitative_rationale=(
                    "PubMed should lead because the run still needs grounded "
                    "literature before any structured follow-up."
                ),
            )

    _install_shadow_planner_test_doubles(
        monkeypatch,
        harness_cls=_FakeHarness,
    )

    result = await recommend_shadow_planner_action(
        checkpoint_key="before_first_action",
        objective="Investigate MED13 syndrome",
        workspace_summary={
            "objective": "Investigate MED13 syndrome",
            "counts": {"documents_ingested": 0, "proposal_count": 0},
            "planner_constraints": {
                "live_action_types": ["QUERY_PUBMED", "RUN_STRUCTURED_ENRICHMENT"],
                "source_required_action_types": [
                    "QUERY_PUBMED",
                    "RUN_STRUCTURED_ENRICHMENT",
                ],
                "control_action_types_without_source_key": [],
                "pubmed_source_key": "pubmed",
                "structured_enrichment_source_keys": ["clinvar"],
            },
        },
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "completed"
    assert result.used_fallback is False
    assert result.validation_error is None
    assert result.initial_validation_error == "numeric_style_ranking_not_allowed"
    assert result.repair_attempted is True
    assert result.repair_succeeded is True
    assert (
        result.decision.metadata["initial_validation_error"]
        == "numeric_style_ranking_not_allowed"
    )
    assert result.decision.metadata["repair_attempted"] is True
    assert result.decision.metadata["repair_succeeded"] is True
