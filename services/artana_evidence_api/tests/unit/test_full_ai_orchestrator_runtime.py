"""Unit tests for the deterministic full AI orchestrator baseline."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from artana_evidence_api import full_ai_orchestrator_runtime
from artana_evidence_api.approval_store import HarnessApprovalStore
from artana_evidence_api.artifact_store import (
    HarnessArtifactRecord,
    HarnessArtifactStore,
    HarnessWorkspaceRecord,
)
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
    ResearchOrchestratorDecision,
    ResearchOrchestratorGuardedDecisionProof,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    build_step_key,
    execute_full_ai_orchestrator_run,
    is_control_action,
    is_source_action,
    load_pubmed_replay_bundle_artifact,
    orchestrator_action_registry,
    queue_full_ai_orchestrator_run,
    require_action_enabled_for_sources,
    store_pubmed_replay_bundle_artifact,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    ShadowPlannerRecommendationResult,
)
from artana_evidence_api.graph_client import GraphTransportBundle
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.harness_runtime import HarnessExecutionServices
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.research_init_runtime import (
    ResearchInitExecutionResult,
    ResearchInitPubMedReplayBundle,
    ResearchInitStructuredEnrichmentReplayBundle,
)
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.tests.support import FakeKernelRuntime
from artana_evidence_api.tests.unit.test_harness_runtime import (
    _fake_pubmed_discovery_service_factory,
    _FakeGraphChatRunner,
    _FakeGraphConnectionRunner,
)
from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences


@pytest.fixture
def services() -> HarnessExecutionServices:
    return HarnessExecutionServices(
        runtime=FakeKernelRuntime(),
        run_registry=HarnessRunRegistry(),
        artifact_store=HarnessArtifactStore(),
        chat_session_store=HarnessChatSessionStore(),
        document_store=HarnessDocumentStore(),
        proposal_store=HarnessProposalStore(),
        approval_store=HarnessApprovalStore(),
        research_state_store=HarnessResearchStateStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        schedule_store=HarnessScheduleStore(),
        graph_connection_runner=_FakeGraphConnectionRunner(),
        graph_chat_runner=_FakeGraphChatRunner(),
        graph_api_gateway_factory=GraphTransportBundle,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_service_factory,
    )


class _ProgressArtifactTimeoutStore(HarnessArtifactStore):
    def __init__(self) -> None:
        super().__init__()
        self.put_attempts = 0

    def put_artifact(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        artifact_key: str,
        media_type: str,
        content: JSONObject,
    ) -> HarnessArtifactRecord:
        self.put_attempts += 1
        raise TimeoutError

    def patch_workspace(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        patch: JSONObject,
    ) -> HarnessWorkspaceRecord | None:
        return None


def test_progress_observer_artifact_timeout_is_best_effort() -> None:
    space_id = uuid4()
    run_id = str(uuid4())
    artifact_store = _ProgressArtifactTimeoutStore()
    sources: ResearchSpaceSourcePreferences = {"pubmed": True, "clinvar": True}
    decisions = full_ai_orchestrator_runtime._build_initial_decision_history(
        objective="Investigate CFTR",
        seed_terms=["CFTR"],
        sources=sources,
        max_depth=1,
        max_hypotheses=5,
    )
    observer = full_ai_orchestrator_runtime._FullAIOrchestratorProgressObserver(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run_id,
        objective="Investigate CFTR",
        seed_terms=["CFTR"],
        max_depth=1,
        max_hypotheses=5,
        sources=sources,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        action_registry=orchestrator_action_registry(),
        decisions=decisions,
        initial_workspace_summary={},
        phase_records={},
    )

    observer.on_progress(
        phase="pubmed_discovery",
        message="Discovering candidate papers from PubMed.",
        progress_percent=0.1,
        completed_steps=1,
        metadata={"sources": sources},
        workspace_snapshot={
            "source_results": {
                "pubmed": {
                    "selected": True,
                    "status": "pending",
                },
            },
        },
    )

    assert artifact_store.put_attempts >= 2
    assert any(
        decision.action_type == ResearchOrchestratorActionType.QUERY_PUBMED
        and decision.status == "running"
        for decision in observer.decisions
    )


def test_progress_observer_timeout_backoff_suppresses_repeat_attempts() -> None:
    space_id = uuid4()
    run_id = str(uuid4())
    artifact_store = _ProgressArtifactTimeoutStore()
    sources: ResearchSpaceSourcePreferences = {"pubmed": True, "clinvar": True}
    decisions = full_ai_orchestrator_runtime._build_initial_decision_history(
        objective="Investigate CFTR",
        seed_terms=["CFTR"],
        sources=sources,
        max_depth=1,
        max_hypotheses=5,
    )
    observer = full_ai_orchestrator_runtime._FullAIOrchestratorProgressObserver(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run_id,
        objective="Investigate CFTR",
        seed_terms=["CFTR"],
        max_depth=1,
        max_hypotheses=5,
        sources=sources,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        action_registry=orchestrator_action_registry(),
        decisions=decisions,
        initial_workspace_summary={},
        phase_records={},
    )

    payload = {
        "source_results": {
            "pubmed": {
                "selected": True,
                "status": "pending",
            },
        },
    }

    observer.on_progress(
        phase="pubmed_discovery",
        message="Discovering candidate papers from PubMed.",
        progress_percent=0.1,
        completed_steps=1,
        metadata={"sources": sources},
        workspace_snapshot=payload,
    )
    first_attempt_count = artifact_store.put_attempts

    observer.on_progress(
        phase="pubmed_discovery",
        message="Still discovering candidate papers from PubMed.",
        progress_percent=0.11,
        completed_steps=1,
        metadata={"sources": sources},
        workspace_snapshot=payload,
    )

    assert first_attempt_count == 2
    assert artifact_store.put_attempts == first_attempt_count


@pytest.fixture(autouse=True)
def _disable_shadow_planner_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner.has_configured_openai_api_key",
        lambda: False,
    )


@pytest.fixture(autouse=True)
def _disable_guarded_chase_rollout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT", raising=False)
    monkeypatch.delenv("ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE", raising=False)


def test_decision_contract_requires_phase1_fields() -> None:
    decision = ResearchOrchestratorDecision(
        decision_id="decision-1",
        round_number=0,
        action_type=ResearchOrchestratorActionType.INITIALIZE_WORKSPACE,
        action_input={"objective": "Investigate MED13"},
        source_key=None,
        evidence_basis="Deterministic baseline.",
        stop_reason=None,
        step_key="full-ai-orchestrator.v1.round_0.control.initialize_workspace",
        status="completed",
        metadata={},
    )

    assert decision.action_type is ResearchOrchestratorActionType.INITIALIZE_WORKSPACE
    assert decision.evidence_basis == "Deterministic baseline."
    assert decision.qualitative_rationale is None
    assert decision.expected_value_band is None


def test_decision_contract_accepts_shadow_planner_fields() -> None:
    decision = ResearchOrchestratorDecision(
        decision_id="shadow-decision-1",
        round_number=0,
        action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
        action_input={"mode": "shadow"},
        source_key="pubmed",
        evidence_basis="Literature discovery should start the run.",
        stop_reason=None,
        step_key="full-ai-orchestrator.v1.shadow.round_0.pubmed.query_pubmed",
        status="recommended",
        expected_value_band="high",
        qualitative_rationale="PubMed gives the run grounded literature before enrichment.",
        risk_level="low",
        requires_approval=False,
        budget_estimate={"relative_size": "small"},
        fallback_reason="openai_api_key_not_configured",
        metadata={"planner_status": "unavailable"},
    )

    assert decision.qualitative_rationale is not None
    assert decision.expected_value_band == "high"
    assert decision.fallback_reason == "openai_api_key_not_configured"


def test_checkpoint_target_decision_uses_synthetic_stop_when_chase_threshold_not_met() -> (
    None
):
    deterministic_target = full_ai_orchestrator_runtime._checkpoint_target_decision(
        checkpoint_key="after_bootstrap",
        decisions=[
            ResearchOrchestratorDecision(
                decision_id="decision-chase-1",
                round_number=1,
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                action_input={"checkpoint_key": "after_bootstrap"},
                source_key=None,
                evidence_basis="Deterministic chase would run when candidates exist.",
                stop_reason=None,
                step_key="full-ai-orchestrator.v1.round_1.control.run_chase_round",
                status="pending",
                expected_value_band="medium",
                qualitative_rationale="Open one bounded chase round when the threshold is met.",
                risk_level="low",
                requires_approval=False,
            ),
        ],
        workspace_summary={
            "checkpoint_key": "after_bootstrap",
            "deterministic_threshold_met": False,
            "chase_candidates": [],
            "deterministic_selection": {},
        },
    )

    assert deterministic_target is not None
    assert deterministic_target.action_type is ResearchOrchestratorActionType.STOP
    assert deterministic_target.stop_reason == "threshold_not_met"
    assert deterministic_target.metadata == {"synthetic_deterministic_target": True}


def test_checkpoint_target_decision_keeps_chase_round_when_candidates_are_available() -> (
    None
):
    deterministic_target = full_ai_orchestrator_runtime._checkpoint_target_decision(
        checkpoint_key="after_bootstrap",
        decisions=[
            ResearchOrchestratorDecision(
                decision_id="decision-chase-1",
                round_number=1,
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                action_input={"checkpoint_key": "after_bootstrap"},
                source_key=None,
                evidence_basis="Deterministic chase baseline keeps the bounded candidate set.",
                stop_reason=None,
                step_key="full-ai-orchestrator.v1.round_1.control.run_chase_round",
                status="pending",
                expected_value_band="medium",
                qualitative_rationale="Continue with a bounded chase round.",
                risk_level="low",
                requires_approval=False,
            ),
        ],
        workspace_summary={
            "checkpoint_key": "after_bootstrap",
            "deterministic_threshold_met": True,
            "chase_candidates": [
                {
                    "entity_id": "entity-1",
                    "display_label": "BRCA2",
                },
            ],
            "deterministic_selection": {
                "selected_entity_ids": ["entity-1"],
                "selected_labels": ["BRCA2"],
                "stop_instead": False,
                "stop_reason": None,
                "selection_basis": "Keep the strongest bounded lead.",
            },
        },
    )

    assert deterministic_target is not None
    assert (
        deterministic_target.action_type
        is ResearchOrchestratorActionType.RUN_CHASE_ROUND
    )
    assert deterministic_target.stop_reason is None


def test_guarded_decision_proof_contract_requires_audit_fields() -> None:
    proof = ResearchOrchestratorGuardedDecisionProof(
        proof_id="guarded-proof-001-after_bootstrap",
        artifact_key="full_ai_orchestrator_guarded_decision_proof_001",
        checkpoint_key="after_bootstrap",
        guarded_strategy="chase_selection",
        planner_mode="guarded",
        guarded_rollout_profile="guarded_chase_only",
        guarded_rollout_profile_source="request",
        guarded_policy_version="guarded-rollout.v1",
        decision_outcome="blocked",
        outcome_reason="invalid_planner_output",
        deterministic_action_type="RUN_CHASE_ROUND",
        deterministic_source_key=None,
        recommended_action_type="RUN_CHASE_ROUND",
        recommended_source_key=None,
        applied_action_type=None,
        applied_source_key=None,
        planner_status="completed",
        used_fallback=False,
        fallback_reason=None,
        validation_error="selected entity is outside the candidate set",
        qualitative_rationale_present=True,
        budget_violation=False,
        disabled_source_violation=False,
        policy_allowed=False,
        comparison_status="diverged",
        verification_status=None,
        verification_reason=None,
        model_id="fixture-model",
        prompt_version="prompt-v1",
        agent_run_id="agent-run-1",
        decision_id="decision-1",
        step_key="full-ai-orchestrator.v1.shadow.after_bootstrap",
        qualitative_rationale="The selected chase candidates should stay bounded.",
        evidence_basis="Planner compared candidates against the workspace.",
        comparison={"checkpoint_key": "after_bootstrap"},
        recommendation={"planner_status": "completed"},
        guarded_action=None,
    )

    assert proof.decision_outcome == "blocked"
    assert proof.policy_allowed is False
    assert proof.qualitative_rationale_present is True


def test_guarded_readiness_blocks_on_blocked_proof_receipts() -> None:
    proof = ResearchOrchestratorGuardedDecisionProof(
        proof_id="guarded-proof-001-after_bootstrap",
        artifact_key="full_ai_orchestrator_guarded_decision_proof_001",
        checkpoint_key="after_bootstrap",
        guarded_strategy="chase_selection",
        planner_mode="guarded",
        guarded_rollout_profile="guarded_low_risk",
        guarded_rollout_profile_source="environment",
        guarded_policy_version="guarded-rollout.v1",
        decision_outcome="blocked",
        outcome_reason="invalid_planner_output",
        deterministic_action_type="RUN_CHASE_ROUND",
        deterministic_source_key=None,
        recommended_action_type="RUN_CHASE_ROUND",
        recommended_source_key=None,
        applied_action_type=None,
        applied_source_key=None,
        planner_status="invalid",
        used_fallback=False,
        fallback_reason=None,
        validation_error="chase_selection_unknown_entity",
        qualitative_rationale_present=True,
        budget_violation=False,
        disabled_source_violation=False,
        policy_allowed=False,
        comparison_status="invalid",
        verification_status=None,
        verification_reason=None,
        model_id="test-model",
        prompt_version="prompt-v1",
        agent_run_id=None,
        decision_id="decision-1",
        step_key="full-ai-orchestrator.v1.round_1.control.run_chase_round",
        qualitative_rationale=(
            "The planner selected a candidate outside the supplied set."
        ),
        evidence_basis="The candidate set is bounded by the workspace.",
        comparison={},
        recommendation={},
        guarded_action=None,
    )

    readiness = full_ai_orchestrator_runtime._guarded_readiness_summary(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        guarded_rollout_profile="guarded_low_risk",
        actions=[],
        proofs=[proof],
    )

    assert readiness["status"] == "blocked_guarded_decision_proofs"
    assert readiness["ready_for_wider_rollout"] is False
    assert readiness["proofs"]["proof_count"] == 1
    assert readiness["proofs"]["blocked_count"] == 1


def test_guarded_readiness_reports_intervention_counts_for_source_chase() -> None:
    actions: list[JSONObject] = [
        {
            "guarded_strategy": "prioritized_structured_sequence",
            "applied_action_type": "RUN_STRUCTURED_ENRICHMENT",
            "verification_status": "verified",
        },
        {
            "guarded_strategy": "chase_selection",
            "applied_action_type": "RUN_CHASE_ROUND",
            "verification_status": "verified",
        },
        {
            "guarded_strategy": "terminal_control_flow",
            "applied_action_type": "STOP",
            "verification_status": "verified",
        },
    ]

    readiness = full_ai_orchestrator_runtime._guarded_readiness_summary(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        guarded_rollout_profile="guarded_source_chase",
        actions=actions,
        proofs=[],
    )

    assert readiness["applied_strategy_counts"] == {
        "prioritized_structured_sequence": 1,
        "chase_selection": 1,
        "terminal_control_flow": 1,
        "brief_generation": 0,
    }
    assert readiness["intervention_counts"] == {
        "source_selection": 1,
        "chase_or_stop": 2,
        "brief_generation": 0,
    }
    assert readiness["profile_allowed_strategies"] == [
        "chase_selection",
        "prioritized_structured_sequence",
        "terminal_control_flow",
    ]
    assert readiness["profile_authority_exercised"] is True


def test_guarded_readiness_marks_source_chase_partial_when_only_one_category() -> None:
    actions: list[JSONObject] = [
        {
            "guarded_strategy": "chase_selection",
            "applied_action_type": "RUN_CHASE_ROUND",
            "verification_status": "verified",
        },
    ]

    readiness = full_ai_orchestrator_runtime._guarded_readiness_summary(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        guarded_rollout_profile="guarded_source_chase",
        actions=actions,
        proofs=[],
    )

    assert readiness["intervention_counts"]["source_selection"] == 0
    assert readiness["intervention_counts"]["chase_or_stop"] == 1
    assert readiness["profile_authority_exercised"] is False


def test_guarded_readiness_terminal_non_stop_not_counted_as_chase_or_stop() -> None:
    actions: list[JSONObject] = [
        {
            "guarded_strategy": "terminal_control_flow",
            "applied_action_type": "ESCALATE_TO_HUMAN",
            "verification_status": "verified",
        },
    ]

    readiness = full_ai_orchestrator_runtime._guarded_readiness_summary(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        guarded_rollout_profile="guarded_source_chase",
        actions=actions,
        proofs=[],
    )

    assert readiness["intervention_counts"]["chase_or_stop"] == 0
    assert readiness["profile_authority_exercised"] is False


def test_guarded_readiness_profile_authority_not_applicable_for_dry_run() -> None:
    readiness = full_ai_orchestrator_runtime._guarded_readiness_summary(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        guarded_rollout_profile="guarded_dry_run",
        actions=[],
        proofs=[],
    )

    assert readiness["profile_authority_exercised"] is None
    assert readiness["profile_allowed_strategies"] == []


def test_guarded_readiness_profile_authority_for_low_risk_any_intervention() -> None:
    actions: list[JSONObject] = [
        {
            "guarded_strategy": "brief_generation",
            "applied_action_type": "GENERATE_BRIEF",
            "verification_status": "verified",
        },
    ]

    readiness = full_ai_orchestrator_runtime._guarded_readiness_summary(
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        guarded_rollout_profile="guarded_low_risk",
        actions=actions,
        proofs=[],
    )

    assert readiness["intervention_counts"]["brief_generation"] == 1
    assert readiness["profile_authority_exercised"] is True


def test_accepted_guarded_control_flow_action_accepts_matched_synthetic_stop_target() -> (
    None
):
    decision = ResearchOrchestratorDecision(
        decision_id="planner-after_bootstrap",
        round_number=1,
        action_type=ResearchOrchestratorActionType.STOP,
        action_input={"checkpoint_key": "after_bootstrap"},
        source_key=None,
        evidence_basis="The chase threshold is not met after bootstrap.",
        stop_reason="threshold_not_met",
        step_key="full-ai-orchestrator.v1.shadow.after_bootstrap.control.stop",
        status="recommended",
        expected_value_band="low",
        qualitative_rationale=(
            "The current workspace does not justify another chase round."
        ),
        risk_level="low",
        requires_approval=False,
    )
    recommendation_payload: JSONObject = {
        "decision": decision.model_dump(mode="json"),
        "planner_status": "completed",
        "model_id": "fixture-shadow-model",
        "agent_run_id": "agent-after_bootstrap",
        "prompt_version": "test-shadow-prompt",
        "used_fallback": False,
        "validation_error": None,
        "error": None,
    }

    guarded_action = full_ai_orchestrator_runtime._accepted_guarded_control_flow_action(
        recommendation_payload=recommendation_payload,
        comparison={
            "checkpoint_key": "after_bootstrap",
            "comparison_status": "matched",
            "target_action_type": "STOP",
            "target_source_key": None,
        },
    )

    assert guarded_action is not None
    assert guarded_action["applied_action_type"] == "STOP"
    assert guarded_action["guarded_strategy"] == "terminal_control_flow"
    assert guarded_action["target_action_type"] == "STOP"
    assert guarded_action["verification_status"] == "pending"


def test_accepted_guarded_control_flow_action_rejects_escalation_when_target_is_stop() -> (
    None
):
    decision = ResearchOrchestratorDecision(
        decision_id="planner-after_bootstrap",
        round_number=1,
        action_type=ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
        action_input={"checkpoint_key": "after_bootstrap"},
        source_key=None,
        evidence_basis="The workspace should go to a human reviewer.",
        stop_reason="guarded_escalate_to_human",
        step_key=(
            "full-ai-orchestrator.v1.shadow.after_bootstrap.control.escalate_to_human"
        ),
        status="recommended",
        expected_value_band="low",
        qualitative_rationale=(
            "A human review would add caution, but the deterministic target is stop."
        ),
        risk_level="low",
        requires_approval=False,
    )
    recommendation_payload: JSONObject = {
        "decision": decision.model_dump(mode="json"),
        "planner_status": "completed",
        "model_id": "fixture-shadow-model",
        "agent_run_id": "agent-after_bootstrap",
        "prompt_version": "test-shadow-prompt",
        "used_fallback": False,
        "validation_error": None,
        "error": None,
    }

    guarded_action = full_ai_orchestrator_runtime._accepted_guarded_control_flow_action(
        recommendation_payload=recommendation_payload,
        comparison={
            "checkpoint_key": "after_bootstrap",
            "comparison_status": "diverged",
            "target_action_type": "STOP",
            "target_source_key": None,
        },
    )

    assert guarded_action is None


@pytest.mark.asyncio
async def test_maybe_select_chase_round_selection_accepts_matched_synthetic_stop_target(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        guarded_rollout_profile="guarded_source_chase",
    )
    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    assert workspace is not None

    observer = full_ai_orchestrator_runtime._FullAIOrchestratorProgressObserver(
        artifact_store=services.artifact_store,
        space_id=space_id,
        run_id=run.id,
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        max_depth=2,
        max_hypotheses=5,
        sources={"pubmed": True, "clinvar": True},
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        action_registry=orchestrator_action_registry(),
        decisions=full_ai_orchestrator_runtime._build_initial_decision_history(
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            sources={"pubmed": True, "clinvar": True},
            max_depth=2,
            max_hypotheses=5,
        ),
        initial_workspace_summary=dict(workspace.snapshot),
        phase_records={},
        guarded_rollout_profile="guarded_source_chase",
        guarded_rollout_profile_source="request",
        guarded_chase_rollout_enabled=True,
    )

    async def _fake_checkpoint(
        *,
        checkpoint_key: str,
        workspace_summary: JSONObject,
        deterministic_decisions: list[ResearchOrchestratorDecision],
    ) -> tuple[JSONObject, JSONObject]:
        del workspace_summary, deterministic_decisions
        decision = ResearchOrchestratorDecision(
            decision_id=f"planner-{checkpoint_key}",
            round_number=1,
            action_type=ResearchOrchestratorActionType.STOP,
            action_input={"checkpoint_key": checkpoint_key},
            source_key=None,
            evidence_basis="The candidate set is below the chase threshold.",
            stop_reason="threshold_not_met",
            step_key=("full-ai-orchestrator.v1.shadow.after_bootstrap.control.stop"),
            status="recommended",
            expected_value_band="low",
            qualitative_rationale=(
                "The workspace does not have enough fresh chase leads to continue."
            ),
            risk_level="low",
            requires_approval=False,
        )
        recommendation_payload: JSONObject = {
            "decision": decision.model_dump(mode="json"),
            "planner_status": "completed",
            "model_id": "fixture-shadow-model",
            "agent_run_id": f"agent-{checkpoint_key}",
            "prompt_version": "test-shadow-prompt",
            "used_fallback": False,
            "validation_error": None,
            "error": None,
        }
        comparison = {
            "checkpoint_key": checkpoint_key,
            "comparison_status": "matched",
            "target_action_type": "STOP",
            "target_source_key": None,
        }
        return recommendation_payload, comparison

    observer._get_or_emit_shadow_checkpoint = _fake_checkpoint  # type: ignore[method-assign]

    selection = await observer.maybe_select_chase_round_selection(
        round_number=1,
        chase_candidates=(),
        deterministic_selection=ResearchOrchestratorChaseSelection(
            selected_entity_ids=[],
            selected_labels=[],
            stop_instead=True,
            stop_reason="threshold_not_met",
            selection_basis="Deterministic baseline stops when the threshold is not met.",
        ),
        workspace_snapshot={
            "status": "running",
            "current_round": 0,
            "source_results": {
                "pubmed": {"selected": True, "status": "completed"},
                "clinvar": {"selected": True, "status": "completed"},
            },
            "bootstrap_summary": {"proposal_count": 1},
            "pending_chase_round": {
                "round_number": 1,
                "chase_candidates": [],
                "available_chase_source_keys": ["pubmed", "clinvar"],
                "deterministic_candidate_count": 0,
                "deterministic_chase_threshold": 3,
                "deterministic_threshold_met": False,
                "deterministic_selection": {
                    "selected_entity_ids": [],
                    "selected_labels": [],
                    "stop_instead": True,
                    "stop_reason": "threshold_not_met",
                    "selection_basis": (
                        "Deterministic baseline stops when the threshold is not met."
                    ),
                },
                "filtered_chase_candidates": [],
                "filtered_chase_filter_reason_counts": {},
            },
        },
    )

    assert selection is not None
    assert selection.stop_instead is True
    assert selection.stop_reason == "guarded_stop_requested"

    updated_workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run.id,
    )
    assert updated_workspace is not None
    assert updated_workspace.snapshot["guarded_terminal_control_after_chase_round"] == 0
    assert (
        updated_workspace.snapshot["guarded_terminal_control_action"]["action_type"]
        == "STOP"
    )
    assert (
        observer.verify_guarded_terminal_control_flow(
            workspace_snapshot=updated_workspace.snapshot,
        )
        is True
    )
    assert observer.guarded_execution_log[0]["verification_status"] == "verified"
    assert observer.guarded_decision_proofs[0].decision_outcome == "allowed"
    assert observer.guarded_decision_proofs[0].verification_status == "verified"


def test_action_registry_exposes_only_allowlisted_phase1_actions() -> None:
    registry = orchestrator_action_registry()
    action_types = {spec.action_type for spec in registry}
    planner_states = {spec.action_type: spec.planner_state for spec in registry}

    assert ResearchOrchestratorActionType.QUERY_PUBMED in action_types
    assert ResearchOrchestratorActionType.RUN_GRAPH_CONNECTION in action_types
    assert ResearchOrchestratorActionType.ESCALATE_TO_HUMAN in action_types
    assert planner_states[ResearchOrchestratorActionType.QUERY_PUBMED] == "live"
    assert (
        planner_states[ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED]
        == "live"
    )
    assert (
        planner_states[ResearchOrchestratorActionType.RUN_GRAPH_CONNECTION]
        == "reserved"
    )


def test_source_capability_checks_reject_disabled_source_actions() -> None:
    with pytest.raises(ValueError, match="source 'clinvar' is disabled"):
        require_action_enabled_for_sources(
            action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
            source_key="clinvar",
            sources={"clinvar": False},
        )


def test_workspace_state_round_trips_through_artifact_store(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    sources: ResearchSpaceSourcePreferences = {"pubmed": True, "clinvar": True}

    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources=sources,
        max_depth=2,
        max_hypotheses=20,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)

    assert workspace is not None
    assert workspace.snapshot["objective"] == "Investigate MED13 syndrome"
    assert workspace.snapshot["enabled_sources"] == {"pubmed": True, "clinvar": True}
    assert workspace.snapshot["decision_history_key"] == (
        "full_ai_orchestrator_decision_history"
    )
    assert workspace.snapshot["decision_count"] == 9
    assert workspace.snapshot["shadow_planner_mode"] == "shadow"
    assert workspace.snapshot["shadow_planner_workspace_key"] == (
        "full_ai_orchestrator_shadow_planner_workspace"
    )
    assert workspace.snapshot["shadow_planner_timeline_key"] == (
        "full_ai_orchestrator_shadow_planner_timeline"
    )


def test_queue_run_records_guarded_planner_mode(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()

    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=20,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    guarded_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_execution",
    )
    readiness_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_readiness",
    )
    proof_summary_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_decision_proofs",
    )

    assert workspace is not None
    assert workspace.snapshot["shadow_planner_mode"] == "guarded"
    assert workspace.snapshot["planner_execution_mode"] == "guarded"
    assert workspace.snapshot["guarded_rollout_profile"] == "guarded_source_chase"
    assert workspace.snapshot["guarded_rollout_profile_source"] == "default"
    assert workspace.snapshot["guarded_rollout_policy"]["fail_closed"] is True
    assert workspace.snapshot["guarded_rollout_policy"]["profile_source"] == "default"
    assert workspace.snapshot["guarded_rollout_policy"][
        "eligible_guarded_strategies"
    ] == [
        "chase_selection",
        "prioritized_structured_sequence",
        "terminal_control_flow",
    ]
    assert workspace.snapshot["guarded_chase_rollout_enabled"] is True
    assert workspace.snapshot["guarded_execution"]["mode"] == "guarded"
    assert workspace.snapshot["guarded_execution"]["applied_count"] == 0
    assert workspace.snapshot["guarded_readiness"]["status"] == (
        "ready_no_guarded_actions_applied"
    )
    assert guarded_artifact is not None
    assert guarded_artifact.content["mode"] == "guarded"
    assert guarded_artifact.content["applied_count"] == 0
    assert readiness_artifact is not None
    assert readiness_artifact.content["policy"]["profile"] == "guarded_source_chase"
    assert readiness_artifact.content["policy"]["profile_source"] == "default"
    assert readiness_artifact.content["proofs"]["proof_count"] == 0
    assert readiness_artifact.content["policy"]["checks"] == {
        "reject_invalid_planner_output": True,
        "reject_fallback_recommendations": True,
        "reject_disabled_or_unavailable_actions": True,
        "require_non_empty_qualitative_rationale": True,
        "require_post_execution_verification": True,
    }
    assert proof_summary_artifact is not None
    assert proof_summary_artifact.content["proof_count"] == 0
    assert workspace.snapshot["guarded_decision_proofs_key"] == (
        "full_ai_orchestrator_guarded_decision_proofs"
    )
    assert workspace.snapshot["guarded_decision_proofs"]["blocked_count"] == 0


def test_queue_shadow_run_does_not_seed_guarded_decision_proofs(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()

    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=20,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.SHADOW,
    )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    proof_summary_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_decision_proofs",
    )

    assert workspace is not None
    assert proof_summary_artifact is None
    assert "guarded_decision_proofs_key" not in workspace.snapshot
    assert "guarded_decision_proofs" not in workspace.snapshot


def test_queue_run_maps_legacy_chase_flag_to_chase_only_profile(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT", "1")
    space_id = uuid4()

    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=20,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)

    assert workspace is not None
    assert workspace.snapshot["guarded_rollout_profile"] == "guarded_chase_only"
    assert workspace.snapshot["guarded_rollout_profile_source"] == "legacy_chase_env"
    assert workspace.snapshot["guarded_chase_rollout_enabled"] is True
    assert workspace.snapshot["guarded_rollout_policy"][
        "eligible_guarded_strategies"
    ] == ["brief_generation", "chase_selection", "terminal_control_flow"]


def test_queue_run_request_profile_overrides_environment_profile(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE",
        "guarded_chase_only",
    )
    space_id = uuid4()

    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=20,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        guarded_rollout_profile="guarded_source_chase",
    )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)

    assert workspace is not None
    assert workspace.snapshot["guarded_rollout_profile"] == "guarded_source_chase"
    assert workspace.snapshot["guarded_rollout_profile_source"] == "request"
    assert workspace.snapshot["guarded_rollout_policy"][
        "eligible_guarded_strategies"
    ] == [
        "chase_selection",
        "prioritized_structured_sequence",
        "terminal_control_flow",
    ]


def test_queue_run_seeds_durable_decision_history_and_action_placeholders(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    sources: ResearchSpaceSourcePreferences = {"pubmed": True, "clinvar": True}

    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources=sources,
        max_depth=2,
        max_hypotheses=20,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    decision_history = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_decision_history",
    )
    assert decision_history is not None
    assert decision_history.content["decision_count"] == 9
    decisions = decision_history.content["decisions"]
    assert isinstance(decisions, list)
    assert decisions[0]["action_type"] == "INITIALIZE_WORKSPACE"
    assert decisions[0]["status"] == "completed"
    assert decisions[-1]["action_type"] == "GENERATE_BRIEF"
    assert decisions[-1]["status"] == "pending"

    pubmed_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_pubmed_summary",
    )
    source_execution_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_source_execution_summary",
    )
    brief_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_brief_metadata",
    )
    shadow_workspace_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_shadow_planner_workspace",
    )
    shadow_recommendation_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_shadow_planner_recommendation",
    )
    shadow_comparison_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_shadow_planner_comparison",
    )
    shadow_timeline_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_shadow_planner_timeline",
    )

    assert pubmed_artifact is not None
    assert pubmed_artifact.content["status"] == "pending"
    assert source_execution_artifact is not None
    assert source_execution_artifact.content["selected_sources"] == {
        "pubmed": True,
        "clinvar": True,
    }
    assert brief_artifact is not None
    assert brief_artifact.content["status"] == "pending"
    assert shadow_workspace_artifact is not None
    assert shadow_workspace_artifact.content["mode"] == "shadow"
    assert shadow_recommendation_artifact is not None
    assert shadow_recommendation_artifact.content["planner_status"] == "pending"
    assert shadow_comparison_artifact is not None
    assert shadow_comparison_artifact.content["comparison_status"] == "pending"
    assert shadow_timeline_artifact is not None
    assert shadow_timeline_artifact.content["checkpoint_count"] == 0


@pytest.mark.asyncio
async def test_execute_run_updates_decision_history_during_progress_callbacks(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    sources: ResearchSpaceSourcePreferences = {"pubmed": True, "clinvar": True}
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources=sources,
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    snapshots: dict[str, object] = {}

    async def _fake_execute_research_init_run(**kwargs):
        progress_observer = kwargs["progress_observer"]
        assert progress_observer is not None
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        current_workspace = artifact_store.get_workspace(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert current_workspace is not None
        source_results = dict(current_workspace.snapshot["source_results"])
        source_results["pubmed"] = {
            **dict(source_results["pubmed"]),
            "status": "completed",
            "documents_discovered": 3,
            "documents_selected": 2,
            "documents_ingested": 0,
        }
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={"source_results": source_results},
        )
        progress_observer.on_progress(
            phase="document_ingestion",
            message="Ingesting selected documents.",
            progress_percent=0.35,
            completed_steps=2,
            metadata={"candidate_count": 2, "source_results": source_results},
            workspace_snapshot=artifact_store.get_workspace(
                space_id=space_id,
                run_id=existing_run.id,
            ).snapshot,
        )
        decision_history = artifact_store.get_artifact(
            space_id=space_id,
            run_id=existing_run.id,
            artifact_key="full_ai_orchestrator_decision_history",
        )
        await progress_observer.wait_for_shadow_planner_updates()
        pubmed_summary = artifact_store.get_artifact(
            space_id=space_id,
            run_id=existing_run.id,
            artifact_key="full_ai_orchestrator_pubmed_summary",
        )
        shadow_timeline = artifact_store.get_artifact(
            space_id=space_id,
            run_id=existing_run.id,
            artifact_key="full_ai_orchestrator_shadow_planner_timeline",
        )
        assert decision_history is not None
        assert pubmed_summary is not None
        assert shadow_timeline is not None
        snapshots["after_document_ingestion"] = decision_history.content
        snapshots["pubmed_summary"] = pubmed_summary.content
        snapshots["shadow_timeline_after_document_ingestion"] = shadow_timeline.content

        source_results["clinvar"] = {
            "selected": True,
            "status": "completed",
            "records_processed": 4,
        }
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "documents_ingested": 2,
                "driven_terms": ["MED13", "MED13L"],
                "driven_genes_from_pubmed": ["MED13L"],
                "source_results": source_results,
            },
        )
        progress_observer.on_progress(
            phase="structured_enrichment",
            message="Running structured enrichment.",
            progress_percent=0.45,
            completed_steps=3,
            metadata={"source_results": source_results},
            workspace_snapshot=artifact_store.get_workspace(
                space_id=space_id,
                run_id=existing_run.id,
            ).snapshot,
        )
        await progress_observer.wait_for_shadow_planner_updates()
        shadow_timeline = artifact_store.get_artifact(
            space_id=space_id,
            run_id=existing_run.id,
            artifact_key="full_ai_orchestrator_shadow_planner_timeline",
        )
        assert shadow_timeline is not None
        snapshots["shadow_timeline_after_structured_enrichment"] = (
            shadow_timeline.content
        )

        progress_observer.on_progress(
            phase="bootstrap",
            message="Running research bootstrap and enrichment.",
            progress_percent=0.85,
            completed_steps=4,
            metadata={
                "created_entity_count": 2,
                "documents_ingested": 2,
                "selected_document_count": 2,
                "source_results": source_results,
            },
            workspace_snapshot=artifact_store.get_workspace(
                space_id=space_id,
                run_id=existing_run.id,
            ).snapshot,
        )
        decision_history = artifact_store.get_artifact(
            space_id=space_id,
            run_id=existing_run.id,
            artifact_key="full_ai_orchestrator_decision_history",
        )
        assert decision_history is not None
        snapshots["after_bootstrap"] = decision_history.content

        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "completed",
                "bootstrap_run_id": "bootstrap-run-1",
                "bootstrap_source_type": "pubmed",
                "bootstrap_summary": {"proposal_count": 1},
                "research_brief": {
                    "title": "Research Brief: MED13",
                    "markdown": "# Brief",
                    "sections": [{"heading": "What matters", "body": "Evidence"}],
                },
                "pending_questions": [],
            },
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=2,
            proposal_count=1,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original = full_ai_orchestrator_runtime.execute_research_init_run
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    try:
        await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=1,
            max_hypotheses=5,
            sources=sources,
            execution_services=services,
            existing_run=run,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original

    after_document_ingestion = snapshots["after_document_ingestion"]
    assert isinstance(after_document_ingestion, dict)
    ingestion_decisions = after_document_ingestion["decisions"]
    assert isinstance(ingestion_decisions, list)
    query_decision = next(
        item for item in ingestion_decisions if item["action_type"] == "QUERY_PUBMED"
    )
    ingest_decision = next(
        item
        for item in ingestion_decisions
        if item["action_type"] == "INGEST_AND_EXTRACT_PUBMED"
    )
    assert query_decision["status"] == "completed"
    assert ingest_decision["status"] == "running"

    pubmed_summary = snapshots["pubmed_summary"]
    assert isinstance(pubmed_summary, dict)
    assert pubmed_summary["status"] == "running"
    assert pubmed_summary["pubmed_source_summary"]["documents_discovered"] == 3

    shadow_timeline_after_document_ingestion = snapshots[
        "shadow_timeline_after_document_ingestion"
    ]
    assert isinstance(shadow_timeline_after_document_ingestion, dict)
    assert shadow_timeline_after_document_ingestion["checkpoint_count"] >= 2

    shadow_timeline_after_structured_enrichment = snapshots[
        "shadow_timeline_after_structured_enrichment"
    ]
    assert isinstance(shadow_timeline_after_structured_enrichment, dict)
    assert shadow_timeline_after_structured_enrichment["checkpoint_count"] >= 4

    after_bootstrap = snapshots["after_bootstrap"]
    assert isinstance(after_bootstrap, dict)
    bootstrap_decisions = after_bootstrap["decisions"]
    assert isinstance(bootstrap_decisions, list)
    ingest_decision = next(
        item
        for item in bootstrap_decisions
        if item["action_type"] == "INGEST_AND_EXTRACT_PUBMED"
    )
    bootstrap_decision = next(
        item for item in bootstrap_decisions if item["action_type"] == "RUN_BOOTSTRAP"
    )
    structured_decision = next(
        item
        for item in bootstrap_decisions
        if item["action_type"] == "RUN_STRUCTURED_ENRICHMENT"
        and item["source_key"] == "clinvar"
    )
    assert ingest_decision["status"] == "completed"
    assert bootstrap_decision["status"] == "running"
    assert structured_decision["status"] == "completed"


@pytest.mark.asyncio
async def test_shadow_checkpoint_queue_skips_duplicate_checkpoint_replay(
    services: HarnessExecutionServices,
) -> None:
    from artana_evidence_api import full_ai_orchestrator_runtime

    space_id = uuid4()
    sources: ResearchSpaceSourcePreferences = {"pubmed": True, "clinvar": True}
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources=sources,
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    shadow_workspace_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_shadow_planner_workspace",
    )
    assert shadow_workspace_artifact is not None

    recommendations: list[str] = []

    async def _fake_recommend_shadow_planner_action(**kwargs):
        checkpoint_key = kwargs["checkpoint_key"]
        recommendations.append(checkpoint_key)
        return ShadowPlannerRecommendationResult(
            decision=ResearchOrchestratorDecision(
                decision_id=f"planner-{checkpoint_key}",
                round_number=0,
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                action_input={"checkpoint_key": checkpoint_key},
                source_key=None,
                evidence_basis="The current workspace supports continuing to the next chase round.",
                stop_reason=None,
                step_key=f"full-ai-orchestrator.v1.shadow.{checkpoint_key}",
                status="recommended",
                expected_value_band="medium",
                qualitative_rationale=(
                    "The workspace has enough evidence to continue with the next deterministic step."
                ),
                risk_level="low",
                requires_approval=False,
                metadata={"checkpoint_key": checkpoint_key},
            ),
            planner_status="completed",
            model_id="fixture-shadow-model",
            agent_run_id=f"agent-{checkpoint_key}",
            prompt_version="test-shadow-prompt",
            used_fallback=False,
            validation_error=None,
            error=None,
        )

    original_recommend = full_ai_orchestrator_runtime.recommend_shadow_planner_action
    full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
        _fake_recommend_shadow_planner_action
    )
    try:
        observer = full_ai_orchestrator_runtime._FullAIOrchestratorProgressObserver(
            artifact_store=services.artifact_store,
            space_id=space_id,
            run_id=run.id,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources=sources,
            planner_mode=FullAIOrchestratorPlannerMode.SHADOW,
            action_registry=orchestrator_action_registry(),
            decisions=full_ai_orchestrator_runtime._build_initial_decision_history(
                objective="Investigate MED13 syndrome",
                seed_terms=["MED13"],
                sources=sources,
                max_depth=2,
                max_hypotheses=5,
            ),
            initial_workspace_summary=dict(shadow_workspace_artifact.content),
            phase_records={},
        )
        observer._enqueue_shadow_checkpoint(
            checkpoint_key="after_bootstrap",
            workspace_summary=dict(shadow_workspace_artifact.content),
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in observer.decisions
            ],
        )
        observer._enqueue_shadow_checkpoint(
            checkpoint_key="after_bootstrap",
            workspace_summary=dict(shadow_workspace_artifact.content),
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in observer.decisions
            ],
        )

        await observer.wait_for_shadow_planner_updates()
    finally:
        full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
            original_recommend
        )

    assert recommendations == ["after_bootstrap"]
    assert observer.shadow_timeline[-1]["checkpoint_key"] == "after_bootstrap"
    assert "after_bootstrap" in observer.emitted_shadow_checkpoints


@pytest.mark.asyncio
async def test_execute_run_forwards_pubmed_replay_bundle(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True},
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )
    replay_bundle = ResearchInitPubMedReplayBundle(
        query_executions=(),
        selected_candidates=(),
        selection_errors=(),
    )
    captured_bundle: ResearchInitPubMedReplayBundle | None = None

    async def _fake_execute_research_init_run(**kwargs):
        nonlocal captured_bundle
        captured_bundle = kwargs.get("pubmed_replay_bundle")
        return ResearchInitExecutionResult(
            run=kwargs["existing_run"],
            pubmed_results=(),
            documents_ingested=0,
            proposal_count=0,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown=None,
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original = full_ai_orchestrator_runtime.execute_research_init_run
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    try:
        await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=1,
            max_hypotheses=5,
            sources={"pubmed": True},
            execution_services=services,
            existing_run=run,
            pubmed_replay_bundle=replay_bundle,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original

    assert captured_bundle is replay_bundle


@pytest.mark.asyncio
async def test_execute_run_loads_pubmed_replay_bundle_from_artifact(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True},
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )
    replay_bundle = ResearchInitPubMedReplayBundle(
        query_executions=(),
        selected_candidates=(),
        selection_errors=("captured before queue wake",),
    )
    store_pubmed_replay_bundle_artifact(
        artifact_store=services.artifact_store,
        space_id=space_id,
        run_id=run.id,
        replay_bundle=replay_bundle,
    )
    stored_bundle = load_pubmed_replay_bundle_artifact(
        artifact_store=services.artifact_store,
        space_id=space_id,
        run_id=run.id,
    )
    assert stored_bundle is not None
    assert stored_bundle.selection_errors == ("captured before queue wake",)

    captured_bundle: ResearchInitPubMedReplayBundle | None = None

    async def _fake_execute_research_init_run(**kwargs):
        nonlocal captured_bundle
        captured_bundle = kwargs.get("pubmed_replay_bundle")
        return ResearchInitExecutionResult(
            run=kwargs["existing_run"],
            pubmed_results=(),
            documents_ingested=0,
            proposal_count=0,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown=None,
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original = full_ai_orchestrator_runtime.execute_research_init_run
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    try:
        await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=1,
            max_hypotheses=5,
            sources={"pubmed": True},
            execution_services=services,
            existing_run=run,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original

    assert captured_bundle is not None
    assert captured_bundle.selection_errors == ("captured before queue wake",)


@pytest.mark.asyncio
async def test_execute_run_forwards_structured_replay_bundle(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True},
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )
    replay_bundle = ResearchInitStructuredEnrichmentReplayBundle(sources=())
    captured_bundle: ResearchInitStructuredEnrichmentReplayBundle | None = None

    async def _fake_execute_research_init_run(**kwargs):
        nonlocal captured_bundle
        captured_bundle = kwargs.get("structured_enrichment_replay_bundle")
        return ResearchInitExecutionResult(
            run=kwargs["existing_run"],
            pubmed_results=(),
            documents_ingested=0,
            proposal_count=0,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown=None,
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original = full_ai_orchestrator_runtime.execute_research_init_run
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    try:
        await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=1,
            max_hypotheses=5,
            sources={"pubmed": True},
            execution_services=services,
            existing_run=run,
            structured_enrichment_replay_bundle=replay_bundle,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original

    assert captured_bundle is replay_bundle


@pytest.mark.asyncio
async def test_execute_run_persists_shadow_planner_artifacts(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "completed",
                "documents_ingested": 1,
                "proposal_count": 1,
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {
                        "selected": True,
                        "status": "completed",
                        "record_count": 1,
                    },
                },
                "bootstrap_summary": {"proposal_count": 1},
                "research_brief": {
                    "title": "Research Brief: MED13",
                    "markdown": "# Brief",
                    "sections": [{"heading": "What matters", "body": "Evidence"}],
                },
                "pending_questions": [],
            },
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=1,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original = full_ai_orchestrator_runtime.execute_research_init_run
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={"pubmed": True, "clinvar": True},
            execution_services=services,
            existing_run=run,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original

    assert result.shadow_planner is not None
    evaluation = result.shadow_planner["evaluation"]
    latest_comparison = result.shadow_planner["latest_comparison"]
    latest_recommendation = result.shadow_planner["latest_recommendation"]
    assert result.shadow_planner["summary"]["checkpoint_count"] >= 3
    assert latest_comparison["comparison_status"] == "matched"
    assert latest_comparison["recommended_action_type"] == "STOP"
    assert latest_comparison["used_fallback"] is True
    assert latest_comparison["qualitative_rationale_present"] is True
    assert latest_recommendation["planner_status"] == "unavailable"
    assert latest_recommendation["used_fallback"] is True
    assert latest_recommendation["telemetry"]["status"] == "unavailable"
    assert result.shadow_planner["cost_tracking"]["status"] == "unavailable"
    assert evaluation["total_checkpoints"] >= 3
    assert evaluation["fallback_recommendations"] >= 1
    assert evaluation["qualitative_rationale_present_count"] >= 3

    shadow_recommendation_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_shadow_planner_recommendation",
    )
    shadow_comparison_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_shadow_planner_comparison",
    )
    shadow_timeline_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_shadow_planner_timeline",
    )
    assert shadow_recommendation_artifact is not None
    assert shadow_recommendation_artifact.content["decision"]["fallback_reason"] == (
        "openai_api_key_not_configured"
    )
    assert shadow_comparison_artifact is not None
    assert shadow_comparison_artifact.content["action_match"] is True
    assert shadow_timeline_artifact is not None
    assert shadow_timeline_artifact.content["checkpoint_count"] >= 3


@pytest.mark.asyncio
async def test_execute_run_guarded_mode_keeps_deterministic_chase_without_application(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        progress_observer = kwargs["progress_observer"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "running",
                "current_round": 1,
                "documents_ingested": 1,
                "proposal_count": 1,
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {
                        "selected": True,
                        "status": "completed",
                        "record_count": 1,
                    },
                },
                "bootstrap_run_id": "bootstrap-run-1",
                "bootstrap_source_type": "pubmed",
                "bootstrap_summary": {"proposal_count": 1},
                "chase_round_1": {
                    "status": "completed",
                    "selection_mode": "deterministic",
                    "selected_entity_ids": ["entity-1", "entity-2", "entity-3"],
                    "selected_labels": ["MED13L", "MED13IP1", "CDK8"],
                    "selection_basis": (
                        "Deterministic baseline keeps the full candidate set."
                    ),
                    "created_entity_count": 0,
                    "seed_entity_count": 1,
                },
                "pending_questions": [],
            },
        )
        workspace = artifact_store.get_workspace(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert workspace is not None
        skipped = await progress_observer.maybe_skip_chase_round(
            next_round_number=2,
            workspace_snapshot=workspace.snapshot,
        )
        assert skipped is False
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "completed",
                "pending_questions": [],
            },
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=1,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original_execute = full_ai_orchestrator_runtime.execute_research_init_run
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={"pubmed": True, "clinvar": True},
            execution_services=services,
            existing_run=run,
            planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original_execute

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)

    assert workspace is not None
    assert result.workspace_summary["guarded_chase_rollout_enabled"] is True
    assert workspace.snapshot["guarded_chase_rollout_enabled"] is True
    assert result.guarded_execution is not None
    assert result.guarded_execution["applied_count"] == 0
    assert "guarded_stop_after_chase_round" not in workspace.snapshot
    assert workspace.snapshot["chase_round_1"]["selection_mode"] == "deterministic"


@pytest.mark.asyncio
async def test_execute_run_guarded_mode_skips_second_chase_round(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT", "1")
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    def _planner_result(
        *,
        checkpoint_key: str,
        action_type: ResearchOrchestratorActionType,
        source_key: str | None,
        stop_reason: str | None = None,
    ) -> ShadowPlannerRecommendationResult:
        return ShadowPlannerRecommendationResult(
            decision=ResearchOrchestratorDecision(
                decision_id=f"planner-{checkpoint_key}",
                round_number=0,
                action_type=action_type,
                action_input={"checkpoint_key": checkpoint_key},
                source_key=source_key,
                evidence_basis=(
                    "The observed evidence supports the recommended next step."
                ),
                stop_reason=stop_reason,
                step_key=f"full-ai-orchestrator.v1.shadow.{checkpoint_key}",
                status="recommended",
                expected_value_band="medium",
                qualitative_rationale=(
                    "The current workspace already has enough grounded evidence for "
                    "this recommendation."
                ),
                risk_level="low",
                requires_approval=False,
                metadata={"checkpoint_key": checkpoint_key},
            ),
            planner_status="completed",
            model_id="fixture-shadow-model",
            agent_run_id=f"agent-{checkpoint_key}",
            prompt_version="test-shadow-prompt",
            used_fallback=False,
            validation_error=None,
            error=None,
        )

    async def _fake_recommend_shadow_planner_action(**kwargs):
        checkpoint_key = kwargs["checkpoint_key"]
        mapping = {
            "before_first_action": (
                ResearchOrchestratorActionType.QUERY_PUBMED,
                "pubmed",
                None,
            ),
            "after_bootstrap": (
                ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                None,
                None,
            ),
            "after_chase_round_1": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
            ),
            "before_brief_generation": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
            ),
            "before_terminal_stop": (
                ResearchOrchestratorActionType.STOP,
                None,
                "completed",
            ),
        }
        action_type, source_key, stop_reason = mapping.get(
            checkpoint_key,
            (
                ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                None,
                None,
            ),
        )
        return _planner_result(
            checkpoint_key=checkpoint_key,
            action_type=action_type,
            source_key=source_key,
            stop_reason=stop_reason,
        )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        progress_observer = kwargs["progress_observer"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "running",
                "current_round": 1,
                "documents_ingested": 1,
                "proposal_count": 1,
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {
                        "selected": True,
                        "status": "completed",
                        "record_count": 1,
                    },
                },
                "bootstrap_run_id": "bootstrap-run-1",
                "bootstrap_source_type": "pubmed",
                "bootstrap_summary": {"proposal_count": 1},
                "chase_round_1": {
                    "status": "completed",
                    "created_entity_count": 0,
                    "seed_entity_count": 1,
                },
                "pending_chase_round": {
                    "round_number": 2,
                    "chase_candidates": [
                        {
                            "entity_id": "entity-4",
                            "display_label": "MED13L",
                            "normalized_label": "med13l",
                            "candidate_rank": 1,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Strong follow-up lead from chase round 1.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-5",
                            "display_label": "CDK8",
                            "normalized_label": "cdk8",
                            "candidate_rank": 2,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Mechanistically connected follow-up lead.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-6",
                            "display_label": "Cyclin C",
                            "normalized_label": "cyclin c",
                            "candidate_rank": 3,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Third bounded lead keeps deterministic chase open.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                    ],
                    "available_chase_source_keys": ["pubmed", "clinvar"],
                    "deterministic_candidate_count": 3,
                    "deterministic_chase_threshold": 3,
                    "deterministic_threshold_met": True,
                    "deterministic_selection": {
                        "selected_entity_ids": ["entity-4", "entity-5", "entity-6"],
                        "selected_labels": ["MED13L", "CDK8", "Cyclin C"],
                        "stop_instead": False,
                        "stop_reason": None,
                        "selection_basis": (
                            "Deterministic baseline keeps all bounded chase candidates."
                        ),
                    },
                    "filtered_chase_candidates": [],
                    "filtered_chase_filter_reason_counts": {},
                },
                "pending_questions": [],
            },
        )
        await progress_observer.wait_for_shadow_planner_updates()
        workspace = artifact_store.get_workspace(
            space_id=space_id, run_id=existing_run.id
        )
        assert workspace is not None
        skipped = await progress_observer.maybe_skip_chase_round(
            next_round_number=2,
            workspace_snapshot=workspace.snapshot,
        )
        assert skipped is True
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "completed",
                "research_brief": {
                    "title": "Research Brief: MED13",
                    "markdown": "# Brief",
                    "sections": [{"heading": "What matters", "body": "Evidence"}],
                },
                "pending_questions": [],
            },
        )
        updated_workspace = artifact_store.get_workspace(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert updated_workspace is not None
        assert (
            progress_observer.verify_guarded_brief_generation(
                workspace_snapshot=updated_workspace.snapshot,
            )
            is True
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=1,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original_execute = full_ai_orchestrator_runtime.execute_research_init_run
    original_recommend = full_ai_orchestrator_runtime.recommend_shadow_planner_action
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
        _fake_recommend_shadow_planner_action
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={"pubmed": True, "clinvar": True},
            execution_services=services,
            existing_run=run,
            planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original_execute
        full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
            original_recommend
        )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    guarded_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_execution",
    )
    proof_summary_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_decision_proofs",
    )
    decision_history = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_decision_history",
    )

    assert workspace is not None
    assert result.planner_mode is FullAIOrchestratorPlannerMode.GUARDED
    assert result.workspace_summary["planner_execution_mode"] == "guarded"
    assert result.guarded_execution is not None
    assert result.guarded_execution["applied_count"] == 1
    assert result.guarded_execution["verified_count"] == 1
    assert result.guarded_execution["pending_verification_count"] == 0
    assert result.guarded_execution["actions"][0]["checkpoint_key"] == (
        "after_chase_round_1"
    )
    assert result.guarded_execution["actions"][0]["stop_reason"] == (
        "guarded_generate_brief"
    )
    assert result.guarded_execution["actions"][0]["verification_status"] == "verified"
    assert workspace.snapshot["guarded_stop_after_chase_round"] == 1
    assert workspace.snapshot["guarded_execution"]["applied_count"] == 1
    assert workspace.snapshot["guarded_execution"]["verified_count"] == 1
    assert guarded_artifact is not None
    assert guarded_artifact.content["applied_count"] == 1
    assert guarded_artifact.content["verified_count"] == 1
    assert proof_summary_artifact is not None
    assert proof_summary_artifact.content["proof_count"] == 1
    assert proof_summary_artifact.content["allowed_count"] == 1
    assert proof_summary_artifact.content["verified_count"] == 1
    allowed_proof = proof_summary_artifact.content["proofs"][0]
    assert allowed_proof["decision_outcome"] == "allowed"
    assert allowed_proof["guarded_strategy"] == "brief_generation"
    assert allowed_proof["applied_action_type"] == "GENERATE_BRIEF"
    assert allowed_proof["verification_status"] == "verified"
    assert result.workspace_summary["guarded_decision_proofs"]["allowed_count"] == 1
    assert decision_history is not None
    skipped_round = next(
        decision
        for decision in decision_history.content["decisions"]
        if decision["action_type"] == "RUN_CHASE_ROUND"
        and decision["round_number"] == 2
    )
    assert skipped_round["status"] == "skipped"
    assert skipped_round["stop_reason"] == "guarded_generate_brief"


@pytest.mark.asyncio
async def test_execute_run_guarded_mode_records_terminal_stop_branch(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT", "1")
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    def _planner_result(
        *,
        checkpoint_key: str,
        action_type: ResearchOrchestratorActionType,
        source_key: str | None,
        stop_reason: str | None = None,
    ) -> ShadowPlannerRecommendationResult:
        return ShadowPlannerRecommendationResult(
            decision=ResearchOrchestratorDecision(
                decision_id=f"planner-{checkpoint_key}",
                round_number=0,
                action_type=action_type,
                action_input={"checkpoint_key": checkpoint_key},
                source_key=source_key,
                evidence_basis="The observed evidence supports the recommended next step.",
                stop_reason=stop_reason,
                step_key=f"full-ai-orchestrator.v1.shadow.{checkpoint_key}",
                status="recommended",
                expected_value_band="medium",
                qualitative_rationale=(
                    "The workspace is stable enough to stop after the first chase round."
                ),
                risk_level="low",
                requires_approval=False,
                metadata={"checkpoint_key": checkpoint_key},
            ),
            planner_status="completed",
            model_id="fixture-shadow-model",
            agent_run_id=f"agent-{checkpoint_key}",
            prompt_version="test-shadow-prompt",
            used_fallback=False,
            validation_error=None,
            error=None,
        )

    async def _fake_recommend_shadow_planner_action(**kwargs):
        checkpoint_key = kwargs["checkpoint_key"]
        mapping = {
            "before_first_action": (
                ResearchOrchestratorActionType.QUERY_PUBMED,
                "pubmed",
                None,
            ),
            "after_bootstrap": (
                ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                None,
                None,
            ),
            "after_chase_round_1": (
                ResearchOrchestratorActionType.STOP,
                None,
                "guarded_stop_requested",
            ),
            "before_brief_generation": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
            ),
            "before_terminal_stop": (
                ResearchOrchestratorActionType.STOP,
                None,
                "completed",
            ),
        }
        action_type, source_key, stop_reason = mapping.get(
            checkpoint_key,
            (
                ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                None,
                None,
            ),
        )
        return _planner_result(
            checkpoint_key=checkpoint_key,
            action_type=action_type,
            source_key=source_key,
            stop_reason=stop_reason,
        )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        progress_observer = kwargs["progress_observer"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "running",
                "current_round": 0,
                "documents_ingested": 1,
                "proposal_count": 1,
                "driven_terms": ["MED13"],
                "driven_genes_from_pubmed": ["MED13"],
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {"selected": True, "status": "pending"},
                },
                "bootstrap_run_id": "bootstrap-run-1",
                "bootstrap_source_type": "pubmed",
                "bootstrap_summary": {"proposal_count": 1},
                "chase_round_1": {
                    "status": "completed",
                    "created_entity_count": 0,
                    "seed_entity_count": 1,
                },
                "pending_chase_round": {
                    "round_number": 2,
                    "chase_candidates": [
                        {
                            "entity_id": "entity-4",
                            "display_label": "MED13L",
                            "normalized_label": "med13l",
                            "candidate_rank": 1,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Strong follow-up lead from chase round 1.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-5",
                            "display_label": "CDK8",
                            "normalized_label": "cdk8",
                            "candidate_rank": 2,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Mechanistically connected follow-up lead.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-6",
                            "display_label": "Cyclin C",
                            "normalized_label": "cyclin c",
                            "candidate_rank": 3,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Third bounded lead keeps deterministic chase open.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                    ],
                    "available_chase_source_keys": ["pubmed", "clinvar"],
                    "deterministic_candidate_count": 3,
                    "deterministic_chase_threshold": 3,
                    "deterministic_threshold_met": True,
                    "deterministic_selection": {
                        "selected_entity_ids": ["entity-4", "entity-5", "entity-6"],
                        "selected_labels": ["MED13L", "CDK8", "Cyclin C"],
                        "stop_instead": False,
                        "stop_reason": None,
                        "selection_basis": (
                            "Deterministic baseline keeps all bounded chase candidates."
                        ),
                    },
                    "filtered_chase_candidates": [],
                    "filtered_chase_filter_reason_counts": {},
                },
                "pending_questions": [],
            },
        )
        workspace = artifact_store.get_workspace(
            space_id=space_id, run_id=existing_run.id
        )
        assert workspace is not None
        skipped = await progress_observer.maybe_skip_chase_round(
            next_round_number=2,
            workspace_snapshot=workspace.snapshot,
        )
        assert skipped is True
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "completed",
                "research_brief": {
                    "title": "Research Brief: MED13",
                    "markdown": "# Brief",
                    "sections": [{"heading": "What matters", "body": "Evidence"}],
                },
                "pending_questions": [],
            },
        )
        updated_workspace = artifact_store.get_workspace(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert updated_workspace is not None
        assert (
            progress_observer.verify_guarded_terminal_control_flow(
                workspace_snapshot=updated_workspace.snapshot,
            )
            is True
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=1,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original_execute = full_ai_orchestrator_runtime.execute_research_init_run
    original_recommend = full_ai_orchestrator_runtime.recommend_shadow_planner_action
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
        _fake_recommend_shadow_planner_action
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={"pubmed": True, "clinvar": True},
            execution_services=services,
            existing_run=run,
            planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original_execute
        full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
            original_recommend
        )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    guarded_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_execution",
    )
    decision_history = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_decision_history",
    )

    assert workspace is not None
    assert result.guarded_execution is not None
    assert result.guarded_execution["applied_count"] == 1
    assert result.guarded_execution["stop_action_count"] == 1
    assert result.guarded_execution["control_action_count"] == 1
    assert result.guarded_execution["brief_action_count"] == 0
    assert result.guarded_execution["verified_count"] == 1
    guarded_action = result.guarded_execution["actions"][0]
    assert guarded_action["applied_action_type"] == "STOP"
    assert guarded_action["stop_reason"] == "guarded_stop_requested"
    assert guarded_action["verification_status"] == "verified"
    assert workspace.snapshot["guarded_terminal_control_after_chase_round"] == 1
    assert (
        workspace.snapshot["guarded_terminal_control_action"]["action_type"] == "STOP"
    )
    assert (
        workspace.snapshot["guarded_terminal_control_action"]["stop_reason"]
        == "guarded_stop_requested"
    )
    assert guarded_artifact is not None
    assert guarded_artifact.content["stop_action_count"] == 1
    assert decision_history is not None
    skipped_round = next(
        decision
        for decision in decision_history.content["decisions"]
        if decision["action_type"] == "RUN_CHASE_ROUND"
        and decision["round_number"] == 2
    )
    assert skipped_round["status"] == "skipped"
    assert skipped_round["stop_reason"] == "guarded_stop_requested"
    terminal_stop = next(
        decision
        for decision in decision_history.content["decisions"]
        if decision["action_type"] == "STOP"
    )
    assert terminal_stop["stop_reason"] == "guarded_stop_requested"


def test_verify_guarded_terminal_control_flow_accepts_after_bootstrap_stop(
    services: HarnessExecutionServices,
) -> None:
    from artana_evidence_api import full_ai_orchestrator_runtime

    space_id = uuid4()
    sources = {"pubmed": True, "drugbank": True}
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate PCSK9 repurposing",
        seed_terms=["PCSK9"],
        sources=sources,
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )
    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    assert workspace is not None

    observer = full_ai_orchestrator_runtime._FullAIOrchestratorProgressObserver(
        artifact_store=services.artifact_store,
        space_id=space_id,
        run_id=run.id,
        objective="Investigate PCSK9 repurposing",
        seed_terms=["PCSK9"],
        max_depth=2,
        max_hypotheses=5,
        sources=sources,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        action_registry=orchestrator_action_registry(),
        decisions=full_ai_orchestrator_runtime._build_initial_decision_history(
            objective="Investigate PCSK9 repurposing",
            seed_terms=["PCSK9"],
            sources=sources,
            max_depth=2,
            max_hypotheses=5,
        ),
        initial_workspace_summary=dict(workspace.snapshot),
        phase_records={},
    )
    observer.guarded_execution_log = [
        {
            "status": "applied",
            "checkpoint_key": "after_bootstrap",
            "applied_action_type": "STOP",
            "applied_source_key": None,
            "guarded_strategy": "terminal_control_flow",
            "comparison_status": "matched",
            "target_action_type": "RUN_CHASE_ROUND",
            "target_source_key": None,
            "planner_status": "completed",
            "model_id": "fixture-shadow-model",
            "agent_run_id": "agent-after_bootstrap",
            "prompt_version": "test-shadow-prompt",
            "decision_id": "planner-after_bootstrap",
            "step_key": "full-ai-orchestrator.v1.shadow.after_bootstrap.control.stop",
            "evidence_basis": (
                "The workspace is synthesis-ready and does not need a chase round."
            ),
            "qualitative_rationale": (
                "Qualitatively, the run is complete enough to stop after bootstrap."
            ),
            "expected_value_band": "low",
            "risk_level": "low",
            "stop_reason": "guarded_stop_requested",
            "verification_status": "pending",
            "verification_reason": None,
            "verification_summary": None,
            "verified_at_phase": None,
        },
    ]
    observer._persist_guarded_execution_state(
        extra_patch={
            "guarded_terminal_control_after_chase_round": 0,
            "guarded_terminal_control_action": {
                "action_type": "STOP",
                "stop_reason": "guarded_stop_requested",
                "checkpoint_key": "after_bootstrap",
                "human_review_required": False,
            },
            "guarded_human_review_required": False,
        },
    )

    updated_workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run.id,
    )
    assert updated_workspace is not None
    assert (
        observer.verify_guarded_terminal_control_flow(
            workspace_snapshot=updated_workspace.snapshot,
        )
        is True
    )

    verified_workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run.id,
    )
    assert verified_workspace is not None
    guarded_action = observer.guarded_execution_log[0]
    assert guarded_action["verification_status"] == "verified"
    assert guarded_action["verification_reason"] == "terminal_control_action_verified"
    assert guarded_action["verified_at_phase"] == "control_flow"
    assert verified_workspace.snapshot["guarded_execution"]["verified_count"] == 1
    assert (
        verified_workspace.snapshot["guarded_execution"]["pending_verification_count"]
        == 0
    )


@pytest.mark.asyncio
async def test_execute_run_guarded_mode_records_terminal_escalation_branch(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT", "1")
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    def _planner_result(
        *,
        checkpoint_key: str,
        action_type: ResearchOrchestratorActionType,
        source_key: str | None,
        stop_reason: str | None = None,
    ) -> ShadowPlannerRecommendationResult:
        return ShadowPlannerRecommendationResult(
            decision=ResearchOrchestratorDecision(
                decision_id=f"planner-{checkpoint_key}",
                round_number=0,
                action_type=action_type,
                action_input={"checkpoint_key": checkpoint_key},
                source_key=source_key,
                evidence_basis="The observed evidence supports the recommended next step.",
                stop_reason=stop_reason,
                step_key=f"full-ai-orchestrator.v1.shadow.{checkpoint_key}",
                status="recommended",
                expected_value_band="medium",
                qualitative_rationale=(
                    "The workspace should escalate to a human before another chase."
                ),
                risk_level="low",
                requires_approval=False,
                metadata={"checkpoint_key": checkpoint_key},
            ),
            planner_status="completed",
            model_id="fixture-shadow-model",
            agent_run_id=f"agent-{checkpoint_key}",
            prompt_version="test-shadow-prompt",
            used_fallback=False,
            validation_error=None,
            error=None,
        )

    async def _fake_recommend_shadow_planner_action(**kwargs):
        checkpoint_key = kwargs["checkpoint_key"]
        mapping = {
            "before_first_action": (
                ResearchOrchestratorActionType.QUERY_PUBMED,
                "pubmed",
                None,
            ),
            "after_bootstrap": (
                ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                None,
                None,
            ),
            "after_chase_round_1": (
                ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
                None,
                "guarded_escalate_to_human",
            ),
            "before_brief_generation": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
            ),
            "before_terminal_stop": (
                ResearchOrchestratorActionType.STOP,
                None,
                "completed",
            ),
        }
        action_type, source_key, stop_reason = mapping.get(
            checkpoint_key,
            (
                ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                None,
                None,
            ),
        )
        return _planner_result(
            checkpoint_key=checkpoint_key,
            action_type=action_type,
            source_key=source_key,
            stop_reason=stop_reason,
        )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        progress_observer = kwargs["progress_observer"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "running",
                "current_round": 0,
                "documents_ingested": 1,
                "proposal_count": 1,
                "driven_terms": ["MED13"],
                "driven_genes_from_pubmed": ["MED13"],
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {"selected": True, "status": "pending"},
                },
                "bootstrap_run_id": "bootstrap-run-1",
                "bootstrap_source_type": "pubmed",
                "bootstrap_summary": {"proposal_count": 1},
                "chase_round_1": {
                    "status": "completed",
                    "created_entity_count": 0,
                    "seed_entity_count": 1,
                },
                "pending_chase_round": {
                    "round_number": 2,
                    "chase_candidates": [
                        {
                            "entity_id": "entity-4",
                            "display_label": "MED13L",
                            "normalized_label": "med13l",
                            "candidate_rank": 1,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Strong follow-up lead from chase round 1.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-5",
                            "display_label": "CDK8",
                            "normalized_label": "cdk8",
                            "candidate_rank": 2,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Mechanistically connected follow-up lead.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-6",
                            "display_label": "Cyclin C",
                            "normalized_label": "cyclin c",
                            "candidate_rank": 3,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Third bounded lead keeps deterministic chase open.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                    ],
                    "available_chase_source_keys": ["pubmed", "clinvar"],
                    "deterministic_candidate_count": 3,
                    "deterministic_chase_threshold": 3,
                    "deterministic_threshold_met": True,
                    "deterministic_selection": {
                        "selected_entity_ids": ["entity-4", "entity-5", "entity-6"],
                        "selected_labels": ["MED13L", "CDK8", "Cyclin C"],
                        "stop_instead": False,
                        "stop_reason": None,
                        "selection_basis": (
                            "Deterministic baseline keeps all bounded chase candidates."
                        ),
                    },
                    "filtered_chase_candidates": [],
                    "filtered_chase_filter_reason_counts": {},
                },
                "pending_questions": [],
            },
        )
        workspace = artifact_store.get_workspace(
            space_id=space_id, run_id=existing_run.id
        )
        assert workspace is not None
        skipped = await progress_observer.maybe_skip_chase_round(
            next_round_number=2,
            workspace_snapshot=workspace.snapshot,
        )
        assert skipped is True
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "completed",
                "research_brief": {
                    "title": "Research Brief: MED13",
                    "markdown": "# Brief",
                    "sections": [{"heading": "What matters", "body": "Evidence"}],
                },
                "pending_questions": [],
            },
        )
        updated_workspace = artifact_store.get_workspace(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert updated_workspace is not None
        assert (
            progress_observer.verify_guarded_terminal_control_flow(
                workspace_snapshot=updated_workspace.snapshot,
            )
            is True
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=1,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original_execute = full_ai_orchestrator_runtime.execute_research_init_run
    original_recommend = full_ai_orchestrator_runtime.recommend_shadow_planner_action
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
        _fake_recommend_shadow_planner_action
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={"pubmed": True, "clinvar": True},
            execution_services=services,
            existing_run=run,
            planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original_execute
        full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
            original_recommend
        )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    guarded_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_execution",
    )
    decision_history = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_decision_history",
    )

    assert workspace is not None
    assert result.guarded_execution is not None
    assert result.guarded_execution["applied_count"] == 1
    assert result.guarded_execution["escalate_action_count"] == 1
    assert result.guarded_execution["control_action_count"] == 1
    assert result.guarded_execution["brief_action_count"] == 0
    assert result.guarded_execution["verified_count"] == 1
    guarded_action = result.guarded_execution["actions"][0]
    assert guarded_action["applied_action_type"] == "ESCALATE_TO_HUMAN"
    assert guarded_action["stop_reason"] == "guarded_escalate_to_human"
    assert guarded_action["verification_status"] == "verified"
    assert workspace.snapshot["guarded_terminal_control_after_chase_round"] == 1
    assert (
        workspace.snapshot["guarded_terminal_control_action"]["action_type"]
        == "ESCALATE_TO_HUMAN"
    )
    assert workspace.snapshot["guarded_human_review_required"] is True
    assert guarded_artifact is not None
    assert guarded_artifact.content["escalate_action_count"] == 1
    assert decision_history is not None
    skipped_round = next(
        decision
        for decision in decision_history.content["decisions"]
        if decision["action_type"] == "RUN_CHASE_ROUND"
        and decision["round_number"] == 2
    )
    assert skipped_round["status"] == "skipped"
    assert skipped_round["stop_reason"] == "guarded_escalate_to_human"
    terminal_stop = next(
        decision
        for decision in decision_history.content["decisions"]
        if decision["action_type"] == "STOP"
    )
    assert terminal_stop["stop_reason"] == "guarded_escalate_to_human"


@pytest.mark.asyncio
async def test_execute_run_guarded_mode_falls_back_when_chase_selection_is_subset(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT", "1")
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    def _planner_result(
        *,
        checkpoint_key: str,
        action_type: ResearchOrchestratorActionType,
        source_key: str | None,
        action_input: dict[str, object] | None = None,
        stop_reason: str | None = None,
    ) -> ShadowPlannerRecommendationResult:
        payload: dict[str, object] = {"checkpoint_key": checkpoint_key}
        if action_input is not None:
            payload.update(action_input)
        return ShadowPlannerRecommendationResult(
            decision=ResearchOrchestratorDecision(
                decision_id=f"planner-{checkpoint_key}",
                round_number=0,
                action_type=action_type,
                action_input=payload,
                source_key=source_key,
                evidence_basis=(
                    "The observed evidence supports the recommended next step."
                ),
                stop_reason=stop_reason,
                step_key=f"full-ai-orchestrator.v1.shadow.{checkpoint_key}",
                status="recommended",
                expected_value_band="medium",
                qualitative_rationale=(
                    "Select the strongest chase leads before widening the search."
                ),
                risk_level="low",
                requires_approval=False,
                metadata={"checkpoint_key": checkpoint_key},
            ),
            planner_status="completed",
            model_id="fixture-shadow-model",
            agent_run_id=f"agent-{checkpoint_key}",
            prompt_version="test-shadow-prompt",
            used_fallback=False,
            validation_error=None,
            error=None,
        )

    async def _fake_recommend_shadow_planner_action(**kwargs):
        checkpoint_key = kwargs["checkpoint_key"]
        mapping = {
            "before_first_action": (
                ResearchOrchestratorActionType.QUERY_PUBMED,
                "pubmed",
                None,
                None,
            ),
            "after_bootstrap": (
                ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                None,
                {
                    "selected_entity_ids": ["entity-1", "entity-3"],
                    "selected_labels": ["MED13L", "CDK8"],
                    "selection_basis": (
                        "The first and third candidates remain the strongest chase leads."
                    ),
                },
                None,
            ),
            "after_chase_round_1": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
                None,
            ),
            "before_brief_generation": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
                None,
            ),
            "before_terminal_stop": (
                ResearchOrchestratorActionType.STOP,
                None,
                None,
                "completed",
            ),
        }
        action_type, source_key, action_input, stop_reason = mapping.get(
            checkpoint_key,
            (
                ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                None,
                None,
                None,
            ),
        )
        return _planner_result(
            checkpoint_key=checkpoint_key,
            action_type=action_type,
            source_key=source_key,
            action_input=action_input,
            stop_reason=stop_reason,
        )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        progress_observer = kwargs["progress_observer"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "running",
                "current_round": 1,
                "documents_ingested": 1,
                "proposal_count": 2,
                "driven_terms": ["MED13", "MED13L", "CDK8"],
                "driven_genes_from_pubmed": ["MED13L"],
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {
                        "selected": True,
                        "status": "completed",
                        "record_count": 1,
                    },
                },
                "bootstrap_run_id": "bootstrap-run-1",
                "bootstrap_source_type": "pubmed",
                "bootstrap_summary": {"proposal_count": 2},
                "pending_chase_round": {
                    "round_number": 1,
                    "chase_candidates": [
                        {
                            "entity_id": "entity-1",
                            "display_label": "MED13L",
                            "normalized_label": "med13l",
                            "candidate_rank": 1,
                            "observed_round": 1,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Most directly supported by the workspace evidence.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-2",
                            "display_label": "MED13IP1",
                            "normalized_label": "med13ip1",
                            "candidate_rank": 2,
                            "observed_round": 1,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Secondary candidate with weaker support.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-3",
                            "display_label": "CDK8",
                            "normalized_label": "cdk8",
                            "candidate_rank": 3,
                            "observed_round": 1,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "A distinct chase lead still worth tracking.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                    ],
                    "available_chase_source_keys": ["pubmed", "clinvar"],
                    "deterministic_candidate_count": 3,
                    "deterministic_chase_threshold": 3,
                    "deterministic_threshold_met": True,
                    "deterministic_selection": {
                        "selected_entity_ids": ["entity-1", "entity-2", "entity-3"],
                        "selected_labels": ["MED13L", "MED13IP1", "CDK8"],
                        "stop_instead": False,
                        "stop_reason": None,
                        "selection_basis": "Deterministic baseline keeps the full candidate set.",
                    },
                    "filtered_chase_candidates": [],
                    "filtered_chase_filter_reason_counts": {},
                },
                "pending_questions": [],
            },
        )
        workspace = artifact_store.get_workspace(
            space_id=space_id, run_id=existing_run.id
        )
        assert workspace is not None
        await progress_observer.wait_for_shadow_planner_updates()
        selected = await progress_observer.maybe_select_chase_round_selection(
            round_number=1,
            chase_candidates=(
                ResearchOrchestratorChaseCandidate(
                    entity_id="entity-1",
                    display_label="MED13L",
                    normalized_label="med13l",
                    candidate_rank=1,
                    observed_round=1,
                    available_source_keys=["pubmed", "clinvar"],
                    evidence_basis="Most directly supported by the workspace evidence.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
                ResearchOrchestratorChaseCandidate(
                    entity_id="entity-2",
                    display_label="MED13IP1",
                    normalized_label="med13ip1",
                    candidate_rank=2,
                    observed_round=1,
                    available_source_keys=["pubmed", "clinvar"],
                    evidence_basis="Secondary candidate with weaker support.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
                ResearchOrchestratorChaseCandidate(
                    entity_id="entity-3",
                    display_label="CDK8",
                    normalized_label="cdk8",
                    candidate_rank=3,
                    observed_round=1,
                    available_source_keys=["pubmed", "clinvar"],
                    evidence_basis="A distinct chase lead still worth tracking.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
            ),
            deterministic_selection=ResearchOrchestratorChaseSelection(
                selected_entity_ids=["entity-1", "entity-2", "entity-3"],
                selected_labels=["MED13L", "MED13IP1", "CDK8"],
                stop_instead=False,
                stop_reason=None,
                selection_basis="Deterministic baseline keeps the full candidate set.",
            ),
            workspace_snapshot=workspace.snapshot,
        )
        assert selected is not None
        effective_selection = selected

        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "chase_round_1": {
                    "status": "completed",
                    "selection_mode": "guarded",
                    "selected_entity_ids": effective_selection.selected_entity_ids,
                    "selected_labels": effective_selection.selected_labels,
                    "selection_basis": effective_selection.selection_basis,
                    "created_entity_count": 2,
                    "seed_entity_count": 1,
                },
                "status": "completed",
                "pending_questions": [],
            },
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=2,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original_execute = full_ai_orchestrator_runtime.execute_research_init_run
    original_recommend = full_ai_orchestrator_runtime.recommend_shadow_planner_action
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
        _fake_recommend_shadow_planner_action
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={"pubmed": True, "clinvar": True},
            execution_services=services,
            existing_run=run,
            planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original_execute
        full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
            original_recommend
        )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    guarded_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_execution",
    )
    decision_history = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_decision_history",
    )

    assert workspace is not None
    assert result.guarded_execution is not None
    assert result.guarded_execution["applied_count"] == 1
    assert result.guarded_execution["verified_count"] == 1
    assert result.guarded_execution["pending_verification_count"] == 0
    assert len(result.guarded_execution["actions"]) == 1
    assert workspace.snapshot["guarded_chase_round_1"] == {
        "selected_entity_ids": ["entity-1", "entity-3"],
        "selected_labels": ["MED13L", "CDK8"],
        "selection_basis": (
            "The first and third candidates remain the strongest chase leads."
        ),
    }
    assert workspace.snapshot["chase_round_1"]["selection_mode"] == "guarded"
    assert workspace.snapshot["chase_round_1"]["selected_entity_ids"] == [
        "entity-1",
        "entity-3",
    ]
    assert workspace.snapshot["chase_round_1"]["selected_labels"] == [
        "MED13L",
        "CDK8",
    ]
    assert guarded_artifact is not None
    assert guarded_artifact.content["applied_count"] == 1
    assert guarded_artifact.content["verified_count"] == 1
    assert decision_history is not None
    chase_round = next(
        decision
        for decision in decision_history.content["decisions"]
        if decision["action_type"] == "RUN_CHASE_ROUND"
        and decision["round_number"] == 1
    )
    assert chase_round["status"] == "completed"
    assert chase_round["action_input"]["selected_entity_ids"] == [
        "entity-1",
        "entity-3",
    ]
    assert chase_round["action_input"]["selected_labels"] == [
        "MED13L",
        "CDK8",
    ]
    assert chase_round["action_input"]["selection_basis"] == (
        "The first and third candidates remain the strongest chase leads."
    )
    assert chase_round["stop_reason"] is None


@pytest.mark.asyncio
async def test_guarded_terminal_hook_defers_chase_round_recommendation_to_chase_selection(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT", "1")
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        guarded_rollout_profile="guarded_source_chase",
    )

    def _planner_result(
        *,
        checkpoint_key: str,
        action_type: ResearchOrchestratorActionType,
        action_input: dict[str, object] | None = None,
    ) -> ShadowPlannerRecommendationResult:
        payload: dict[str, object] = {"checkpoint_key": checkpoint_key}
        if action_input is not None:
            payload.update(action_input)
        return ShadowPlannerRecommendationResult(
            decision=ResearchOrchestratorDecision(
                decision_id=f"planner-{checkpoint_key}",
                round_number=0,
                action_type=action_type,
                action_input=payload,
                source_key=None,
                evidence_basis="Workspace evidence supports this recommendation.",
                stop_reason=None,
                step_key=f"full-ai-orchestrator.v1.shadow.{checkpoint_key}",
                status="recommended",
                expected_value_band="medium",
                qualitative_rationale=(
                    "Select the strongest chase leads before widening the search."
                ),
                risk_level="low",
                requires_approval=False,
                metadata={"checkpoint_key": checkpoint_key},
            ),
            planner_status="completed",
            model_id="fixture-shadow-model",
            agent_run_id=f"agent-{checkpoint_key}",
            prompt_version="test-shadow-prompt",
            used_fallback=False,
            validation_error=None,
            error=None,
        )

    async def _fake_recommend_shadow_planner_action(**kwargs):
        checkpoint_key = str(kwargs["checkpoint_key"])
        if checkpoint_key == "after_chase_round_1":
            return _planner_result(
                checkpoint_key=checkpoint_key,
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                action_input={
                    "selected_entity_ids": ["entity-4", "entity-5"],
                    "selected_labels": ["MED13L", "CDK8"],
                    "selection_basis": (
                        "These two entities remain the strongest second-round chase leads."
                    ),
                },
            )
        return _planner_result(
            checkpoint_key=checkpoint_key,
            action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
        )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        progress_observer = kwargs["progress_observer"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "running",
                "current_round": 2,
                "documents_ingested": 1,
                "proposal_count": 2,
                "source_results": {
                    "pubmed": {"selected": True, "status": "completed"},
                    "clinvar": {"selected": True, "status": "completed"},
                },
                "bootstrap_run_id": "bootstrap-run-1",
                "bootstrap_summary": {"proposal_count": 2},
                "chase_round_1": {
                    "status": "completed",
                    "selection_mode": "guarded",
                    "selected_entity_ids": ["entity-1", "entity-3"],
                    "selected_labels": ["MED13L", "CDK8"],
                    "selection_basis": "First guarded chase kept the best leads.",
                },
                "pending_chase_round": {
                    "round_number": 2,
                    "chase_candidates": [
                        {
                            "entity_id": "entity-4",
                            "display_label": "MED13L",
                            "normalized_label": "med13l",
                            "candidate_rank": 1,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Directly connected to the current objective.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-5",
                            "display_label": "CDK8",
                            "normalized_label": "cdk8",
                            "candidate_rank": 2,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Mechanistically connected and still actionable.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                        {
                            "entity_id": "entity-6",
                            "display_label": "generic result",
                            "normalized_label": "generic result",
                            "candidate_rank": 3,
                            "observed_round": 2,
                            "available_source_keys": ["pubmed", "clinvar"],
                            "evidence_basis": "Less specific generic result label.",
                            "novelty_basis": "not_in_previous_seed_terms",
                        },
                    ],
                    "available_chase_source_keys": ["pubmed", "clinvar"],
                    "deterministic_candidate_count": 3,
                    "deterministic_chase_threshold": 3,
                    "deterministic_threshold_met": True,
                    "deterministic_selection": {
                        "selected_entity_ids": ["entity-4", "entity-5", "entity-6"],
                        "selected_labels": ["MED13L", "CDK8", "generic result"],
                        "stop_instead": False,
                        "stop_reason": None,
                        "selection_basis": "Deterministic baseline keeps all candidates.",
                    },
                    "filtered_chase_candidates": [],
                    "filtered_chase_filter_reason_counts": {},
                },
                "pending_questions": [],
            },
        )
        workspace = artifact_store.get_workspace(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert workspace is not None
        await progress_observer.wait_for_shadow_planner_updates()
        skipped = await progress_observer.maybe_skip_chase_round(
            next_round_number=2,
            workspace_snapshot=workspace.snapshot,
        )
        assert skipped is False
        selected = await progress_observer.maybe_select_chase_round_selection(
            round_number=2,
            chase_candidates=(
                ResearchOrchestratorChaseCandidate(
                    entity_id="entity-4",
                    display_label="MED13L",
                    normalized_label="med13l",
                    candidate_rank=1,
                    observed_round=2,
                    available_source_keys=["pubmed", "clinvar"],
                    evidence_basis="Directly connected to the current objective.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
                ResearchOrchestratorChaseCandidate(
                    entity_id="entity-5",
                    display_label="CDK8",
                    normalized_label="cdk8",
                    candidate_rank=2,
                    observed_round=2,
                    available_source_keys=["pubmed", "clinvar"],
                    evidence_basis="Mechanistically connected and still actionable.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
                ResearchOrchestratorChaseCandidate(
                    entity_id="entity-6",
                    display_label="generic result",
                    normalized_label="generic result",
                    candidate_rank=3,
                    observed_round=2,
                    available_source_keys=["pubmed", "clinvar"],
                    evidence_basis="Less specific generic result label.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
            ),
            deterministic_selection=ResearchOrchestratorChaseSelection(
                selected_entity_ids=["entity-4", "entity-5", "entity-6"],
                selected_labels=["MED13L", "CDK8", "generic result"],
                stop_instead=False,
                stop_reason=None,
                selection_basis="Deterministic baseline keeps all candidates.",
            ),
            workspace_snapshot=workspace.snapshot,
        )
        assert selected is not None
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "chase_round_2": {
                    "status": "completed",
                    "selection_mode": "guarded",
                    "selected_entity_ids": selected.selected_entity_ids,
                    "selected_labels": selected.selected_labels,
                    "selection_basis": selected.selection_basis,
                },
                "status": "completed",
                "pending_questions": [],
            },
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=2,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original_execute = full_ai_orchestrator_runtime.execute_research_init_run
    original_recommend = full_ai_orchestrator_runtime.recommend_shadow_planner_action
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
        _fake_recommend_shadow_planner_action
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={"pubmed": True, "clinvar": True},
            execution_services=services,
            existing_run=run,
            planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
            guarded_rollout_profile="guarded_source_chase",
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original_execute
        full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
            original_recommend
        )

    assert result.guarded_execution is not None
    assert result.guarded_execution["applied_count"] == 1
    proof_summary = result.guarded_decision_proofs
    assert proof_summary is not None
    assert proof_summary["proof_count"] == 1
    proof = proof_summary["proofs"][0]
    assert proof["checkpoint_key"] == "after_chase_round_1"
    assert proof["decision_outcome"] == "allowed"
    assert proof["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_execute_run_guarded_mode_falls_back_on_invalid_chase_selection(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT", "1")
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    def _planner_result(
        *,
        checkpoint_key: str,
        action_type: ResearchOrchestratorActionType,
        source_key: str | None,
        action_input: dict[str, object] | None = None,
        stop_reason: str | None = None,
    ) -> ShadowPlannerRecommendationResult:
        payload: dict[str, object] = {"checkpoint_key": checkpoint_key}
        if action_input is not None:
            payload.update(action_input)
        return ShadowPlannerRecommendationResult(
            decision=ResearchOrchestratorDecision(
                decision_id=f"planner-{checkpoint_key}",
                round_number=0,
                action_type=action_type,
                action_input=payload,
                source_key=source_key,
                evidence_basis=(
                    "The observed evidence supports the recommended next step."
                ),
                stop_reason=stop_reason,
                step_key=f"full-ai-orchestrator.v1.shadow.{checkpoint_key}",
                status="recommended",
                expected_value_band="medium",
                qualitative_rationale=(
                    "Follow only the strongest chase candidates from the current workspace."
                ),
                risk_level="low",
                requires_approval=False,
                metadata={"checkpoint_key": checkpoint_key},
            ),
            planner_status="completed",
            model_id="fixture-shadow-model",
            agent_run_id=f"agent-{checkpoint_key}",
            prompt_version="test-shadow-prompt",
            used_fallback=False,
            validation_error=None,
            error=None,
        )

    async def _fake_recommend_shadow_planner_action(**kwargs):
        checkpoint_key = kwargs["checkpoint_key"]
        mapping = {
            "before_first_action": (
                ResearchOrchestratorActionType.QUERY_PUBMED,
                "pubmed",
                None,
                None,
            ),
            "after_bootstrap": (
                ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                None,
                {
                    "selected_entity_ids": ["entity-missing"],
                    "selected_labels": ["NOT_A_REAL_CANDIDATE"],
                    "selection_basis": "This recommendation should be rejected.",
                },
                None,
            ),
            "after_chase_round_1": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
                None,
            ),
            "before_brief_generation": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
                None,
            ),
            "before_terminal_stop": (
                ResearchOrchestratorActionType.STOP,
                None,
                None,
                "completed",
            ),
        }
        action_type, source_key, action_input, stop_reason = mapping.get(
            checkpoint_key,
            (
                ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                None,
                None,
                None,
            ),
        )
        return _planner_result(
            checkpoint_key=checkpoint_key,
            action_type=action_type,
            source_key=source_key,
            action_input=action_input,
            stop_reason=stop_reason,
        )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        progress_observer = kwargs["progress_observer"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "running",
                "current_round": 1,
                "documents_ingested": 1,
                "proposal_count": 2,
                "driven_terms": ["MED13", "MED13L", "CDK8"],
                "driven_genes_from_pubmed": ["MED13L"],
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {
                        "selected": True,
                        "status": "completed",
                        "record_count": 1,
                    },
                },
                "bootstrap_run_id": "bootstrap-run-1",
                "bootstrap_source_type": "pubmed",
                "bootstrap_summary": {"proposal_count": 2},
                "pending_questions": [],
            },
        )
        workspace = artifact_store.get_workspace(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert workspace is not None
        selected = await progress_observer.maybe_select_chase_round_selection(
            round_number=1,
            chase_candidates=(
                ResearchOrchestratorChaseCandidate(
                    entity_id="entity-1",
                    display_label="MED13L",
                    normalized_label="med13l",
                    candidate_rank=1,
                    observed_round=1,
                    available_source_keys=["pubmed", "clinvar"],
                    evidence_basis="Most directly supported by the workspace evidence.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
                ResearchOrchestratorChaseCandidate(
                    entity_id="entity-2",
                    display_label="MED13IP1",
                    normalized_label="med13ip1",
                    candidate_rank=2,
                    observed_round=1,
                    available_source_keys=["pubmed", "clinvar"],
                    evidence_basis="Secondary candidate with weaker support.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
                ResearchOrchestratorChaseCandidate(
                    entity_id="entity-3",
                    display_label="CDK8",
                    normalized_label="cdk8",
                    candidate_rank=3,
                    observed_round=1,
                    available_source_keys=["pubmed", "clinvar"],
                    evidence_basis="A distinct chase lead still worth tracking.",
                    novelty_basis="not_in_previous_seed_terms",
                ),
            ),
            deterministic_selection=ResearchOrchestratorChaseSelection(
                selected_entity_ids=["entity-1", "entity-2", "entity-3"],
                selected_labels=["MED13L", "MED13IP1", "CDK8"],
                stop_instead=False,
                stop_reason=None,
                selection_basis="Deterministic baseline keeps the full candidate set.",
            ),
            workspace_snapshot=workspace.snapshot,
        )
        assert selected is None
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "chase_round_1": {
                    "status": "completed",
                    "selection_mode": "deterministic",
                    "selected_entity_ids": ["entity-1", "entity-2", "entity-3"],
                    "selected_labels": ["MED13L", "MED13IP1", "CDK8"],
                    "selection_basis": (
                        "Deterministic baseline keeps the full candidate set."
                    ),
                    "created_entity_count": 3,
                    "seed_entity_count": 1,
                },
                "status": "completed",
                "pending_questions": [],
            },
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=2,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original_execute = full_ai_orchestrator_runtime.execute_research_init_run
    original_recommend = full_ai_orchestrator_runtime.recommend_shadow_planner_action
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
        _fake_recommend_shadow_planner_action
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={"pubmed": True, "clinvar": True},
            execution_services=services,
            existing_run=run,
            planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original_execute
        full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
            original_recommend
        )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    proof_summary_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_decision_proofs",
    )
    decision_history = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_decision_history",
    )

    assert workspace is not None
    assert result.workspace_summary["guarded_chase_rollout_enabled"] is True
    assert result.guarded_execution is not None
    assert result.guarded_execution["applied_count"] == 0
    assert result.guarded_decision_proofs is not None
    assert result.guarded_decision_proofs["blocked_count"] == 1
    assert "guarded_chase_round_1" not in workspace.snapshot
    assert workspace.snapshot["chase_round_1"]["selection_mode"] == "deterministic"
    assert proof_summary_artifact is not None
    assert proof_summary_artifact.content["proof_count"] == 1
    assert proof_summary_artifact.content["blocked_count"] == 1
    blocked_proof = proof_summary_artifact.content["proofs"][0]
    assert blocked_proof["decision_outcome"] == "blocked"
    assert blocked_proof["guarded_strategy"] == "chase_selection"
    assert blocked_proof["recommended_action_type"] == "RUN_CHASE_ROUND"
    assert blocked_proof["applied_action_type"] is None
    assert blocked_proof["policy_allowed"] is False
    assert blocked_proof["outcome_reason"] == "not_an_eligible_guarded_chase_action"
    blocked_artifact_key = proof_summary_artifact.content["artifact_keys"][0]
    blocked_proof_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=blocked_artifact_key,
    )
    assert blocked_proof_artifact is not None
    assert blocked_proof_artifact.content["proof_id"] == blocked_proof["proof_id"]
    assert decision_history is not None
    chase_round = next(
        decision
        for decision in decision_history.content["decisions"]
        if decision["action_type"] == "RUN_CHASE_ROUND"
        and decision["round_number"] == 1
    )
    assert chase_round["status"] == "completed"
    assert chase_round["action_input"]["selected_entity_ids"] == [
        "entity-1",
        "entity-2",
        "entity-3",
    ]


@pytest.mark.asyncio
async def test_execute_run_guarded_mode_prioritizes_structured_source_sequence(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE",
        "guarded_low_risk",
    )
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "clinvar": True,
            "drugbank": True,
            "alphafold": True,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    def _planner_result(
        *,
        checkpoint_key: str,
        action_type: ResearchOrchestratorActionType,
        source_key: str | None,
        stop_reason: str | None = None,
    ) -> ShadowPlannerRecommendationResult:
        return ShadowPlannerRecommendationResult(
            decision=ResearchOrchestratorDecision(
                decision_id=f"planner-{checkpoint_key}",
                round_number=0,
                action_type=action_type,
                action_input={"checkpoint_key": checkpoint_key},
                source_key=source_key,
                evidence_basis=(
                    "The observed evidence supports the recommended next step."
                ),
                stop_reason=stop_reason,
                step_key=f"full-ai-orchestrator.v1.shadow.{checkpoint_key}",
                status="recommended",
                expected_value_band="medium",
                qualitative_rationale=(
                    "Choose the best remaining structured source before bootstrap."
                ),
                risk_level="low",
                requires_approval=False,
                metadata={"checkpoint_key": checkpoint_key},
            ),
            planner_status="completed",
            model_id="fixture-shadow-model",
            agent_run_id=f"agent-{checkpoint_key}",
            prompt_version="test-shadow-prompt",
            used_fallback=False,
            validation_error=None,
            error=None,
        )

    async def _fake_recommend_shadow_planner_action(**kwargs):
        checkpoint_key = kwargs["checkpoint_key"]
        mapping = {
            "before_first_action": (
                ResearchOrchestratorActionType.QUERY_PUBMED,
                "pubmed",
                None,
            ),
            "after_pubmed_ingest_extract": (
                ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                "drugbank",
                None,
            ),
            "after_driven_terms_ready": (
                ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                "drugbank",
                None,
            ),
            "before_brief_generation": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
            ),
            "before_terminal_stop": (
                ResearchOrchestratorActionType.STOP,
                None,
                "completed",
            ),
        }
        action_type, source_key, stop_reason = mapping.get(
            checkpoint_key,
            (
                ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                None,
                None,
            ),
        )
        return _planner_result(
            checkpoint_key=checkpoint_key,
            action_type=action_type,
            source_key=source_key,
            stop_reason=stop_reason,
        )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        progress_observer = kwargs["progress_observer"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "running",
                "current_round": 0,
                "documents_ingested": 1,
                "proposal_count": 1,
                "driven_terms": ["MED13"],
                "driven_genes_from_pubmed": ["MED13"],
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {"selected": True, "status": "pending"},
                    "drugbank": {"selected": True, "status": "pending"},
                    "alphafold": {"selected": True, "status": "pending"},
                },
                "pending_questions": [],
            },
        )
        workspace = artifact_store.get_workspace(
            space_id=space_id, run_id=existing_run.id
        )
        assert workspace is not None
        progress_observer.on_progress(
            phase="structured_enrichment",
            message="Querying structured sources.",
            progress_percent=0.45,
            completed_steps=2,
            metadata={
                "enrichment_sources": ["clinvar", "drugbank", "alphafold"],
                "driven_terms_count": 1,
                "driven_genes_from_pubmed": ["MED13"],
            },
            workspace_snapshot=workspace.snapshot,
        )
        selected_sources = (
            await progress_observer.maybe_select_structured_enrichment_sources(
                available_source_keys=("clinvar", "drugbank", "alphafold"),
                workspace_snapshot=workspace.snapshot,
            )
        )
        assert selected_sources == ("drugbank", "clinvar", "alphafold")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {
                        "selected": True,
                        "status": "completed",
                        "records_processed": 1,
                    },
                    "drugbank": {
                        "selected": True,
                        "status": "completed",
                        "records_processed": 2,
                    },
                    "alphafold": {
                        "selected": True,
                        "status": "completed",
                        "records_processed": 1,
                    },
                    "enrichment_orchestration": {
                        "execution_mode": "guarded_prioritized_sequence",
                        "selected_enrichment_sources": [
                            "drugbank",
                            "clinvar",
                            "alphafold",
                        ],
                        "deferred_enrichment_sources": [],
                    },
                },
            },
        )
        updated_workspace = artifact_store.get_workspace(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert updated_workspace is not None
        assert (
            progress_observer.verify_guarded_structured_enrichment(
                workspace_snapshot=updated_workspace.snapshot,
            )
            is True
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "completed",
                "research_brief": {
                    "title": "Research Brief: MED13",
                    "markdown": "# Brief",
                    "sections": [{"heading": "What matters", "body": "Evidence"}],
                },
                "pending_questions": [],
            },
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=1,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original_execute = full_ai_orchestrator_runtime.execute_research_init_run
    original_recommend = full_ai_orchestrator_runtime.recommend_shadow_planner_action
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
        _fake_recommend_shadow_planner_action
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={
                "pubmed": True,
                "clinvar": True,
                "drugbank": True,
                "alphafold": True,
            },
            execution_services=services,
            existing_run=run,
            planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original_execute
        full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
            original_recommend
        )

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    guarded_artifact = services.artifact_store.get_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="full_ai_orchestrator_guarded_execution",
    )

    assert workspace is not None
    assert result.guarded_execution is not None
    assert result.guarded_execution["applied_count"] == 1
    assert result.guarded_execution["verified_count"] == 1
    assert result.guarded_execution["pending_verification_count"] == 0
    guarded_action = result.guarded_execution["actions"][0]
    assert guarded_action["applied_action_type"] == "RUN_STRUCTURED_ENRICHMENT"
    assert guarded_action["applied_source_key"] == "drugbank"
    assert guarded_action["ordered_source_keys"] == [
        "drugbank",
        "clinvar",
        "alphafold",
    ]
    assert guarded_action["deferred_source_keys"] == []
    assert guarded_action["guarded_strategy"] == "prioritized_structured_sequence"
    assert guarded_action["guarded_policy_version"] == "guarded-rollout.v1"
    assert guarded_action["guarded_rollout_profile"] == "guarded_low_risk"
    assert guarded_action["guarded_policy_allowed"] is True
    assert guarded_action["verification_status"] == "verified"
    assert guarded_action["verification_reason"] == "ordered_sources_completed"
    assert workspace.snapshot["guarded_structured_enrichment_selection"] == {
        "selected_source_key": "drugbank",
        "ordered_source_keys": ["drugbank", "clinvar", "alphafold"],
        "deferred_source_keys": [],
    }
    assert guarded_artifact is not None
    assert guarded_artifact.content["applied_count"] == 1
    assert guarded_artifact.content["verified_count"] == 1
    assert result.workspace_summary["guarded_readiness"]["status"] == "ready_verified"


@pytest.mark.asyncio
async def test_execute_run_guarded_mode_marks_failed_verification_when_ordered_source_is_deferred(
    services: HarnessExecutionServices,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE",
        "guarded_low_risk",
    )
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={
            "pubmed": True,
            "clinvar": True,
            "drugbank": True,
            "alphafold": True,
        },
        max_depth=2,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
        planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
    )

    def _planner_result(
        *,
        checkpoint_key: str,
        action_type: ResearchOrchestratorActionType,
        source_key: str | None,
        stop_reason: str | None = None,
    ) -> ShadowPlannerRecommendationResult:
        return ShadowPlannerRecommendationResult(
            decision=ResearchOrchestratorDecision(
                decision_id=f"planner-{checkpoint_key}",
                round_number=0,
                action_type=action_type,
                action_input={"checkpoint_key": checkpoint_key},
                source_key=source_key,
                evidence_basis=(
                    "The observed evidence supports the recommended next step."
                ),
                stop_reason=stop_reason,
                step_key=f"full-ai-orchestrator.v1.shadow.{checkpoint_key}",
                status="recommended",
                expected_value_band="medium",
                qualitative_rationale=(
                    "Choose the best remaining structured source before bootstrap."
                ),
                risk_level="low",
                requires_approval=False,
                metadata={"checkpoint_key": checkpoint_key},
            ),
            planner_status="completed",
            model_id="fixture-shadow-model",
            agent_run_id=f"agent-{checkpoint_key}",
            prompt_version="test-shadow-prompt",
            used_fallback=False,
            validation_error=None,
            error=None,
        )

    async def _fake_recommend_shadow_planner_action(**kwargs):
        checkpoint_key = kwargs["checkpoint_key"]
        mapping = {
            "before_first_action": (
                ResearchOrchestratorActionType.QUERY_PUBMED,
                "pubmed",
                None,
            ),
            "after_pubmed_ingest_extract": (
                ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                "drugbank",
                None,
            ),
            "after_driven_terms_ready": (
                ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                "drugbank",
                None,
            ),
            "before_brief_generation": (
                ResearchOrchestratorActionType.GENERATE_BRIEF,
                None,
                None,
            ),
            "before_terminal_stop": (
                ResearchOrchestratorActionType.STOP,
                None,
                "completed",
            ),
        }
        action_type, source_key, stop_reason = mapping.get(
            checkpoint_key,
            (
                ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                None,
                None,
            ),
        )
        return _planner_result(
            checkpoint_key=checkpoint_key,
            action_type=action_type,
            source_key=source_key,
            stop_reason=stop_reason,
        )

    async def _fake_execute_research_init_run(**kwargs):
        artifact_store = kwargs["execution_services"].artifact_store
        existing_run = kwargs["existing_run"]
        progress_observer = kwargs["progress_observer"]
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "running",
                "current_round": 0,
                "documents_ingested": 1,
                "proposal_count": 1,
                "driven_terms": ["MED13"],
                "driven_genes_from_pubmed": ["MED13"],
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {"selected": True, "status": "pending"},
                    "drugbank": {"selected": True, "status": "pending"},
                    "alphafold": {"selected": True, "status": "pending"},
                },
                "pending_questions": [],
            },
        )
        workspace = artifact_store.get_workspace(
            space_id=space_id, run_id=existing_run.id
        )
        assert workspace is not None
        selected_sources = (
            await progress_observer.maybe_select_structured_enrichment_sources(
                available_source_keys=("clinvar", "drugbank", "alphafold"),
                workspace_snapshot=workspace.snapshot,
            )
        )
        assert selected_sources == ("drugbank", "clinvar", "alphafold")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "source_results": {
                    "pubmed": {
                        "selected": True,
                        "status": "completed",
                        "documents_ingested": 1,
                    },
                    "clinvar": {
                        "selected": True,
                        "status": "deferred",
                        "deferred_reason": "guarded_source_selection",
                        "guarded_selected_source_key": "drugbank",
                    },
                    "drugbank": {
                        "selected": True,
                        "status": "completed",
                        "records_processed": 2,
                    },
                    "alphafold": {
                        "selected": True,
                        "status": "completed",
                        "records_processed": 1,
                    },
                    "enrichment_orchestration": {
                        "execution_mode": "guarded_prioritized_sequence",
                        "selected_enrichment_sources": [
                            "drugbank",
                            "clinvar",
                            "alphafold",
                        ],
                        "deferred_enrichment_sources": [],
                    },
                },
            },
        )
        updated_workspace = artifact_store.get_workspace(
            space_id=space_id,
            run_id=existing_run.id,
        )
        assert updated_workspace is not None
        assert (
            progress_observer.verify_guarded_structured_enrichment(
                workspace_snapshot=updated_workspace.snapshot,
            )
            is True
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=existing_run.id,
            patch={
                "status": "completed",
                "research_brief": {
                    "title": "Research Brief: MED13",
                    "markdown": "# Brief",
                    "sections": [{"heading": "What matters", "body": "Evidence"}],
                },
                "pending_questions": [],
            },
        )
        return ResearchInitExecutionResult(
            run=existing_run,
            pubmed_results=(),
            documents_ingested=1,
            proposal_count=1,
            research_state=None,
            pending_questions=[],
            errors=[],
            claim_curation=None,
            research_brief_markdown="# Brief",
        )

    from artana_evidence_api import full_ai_orchestrator_runtime

    original_execute = full_ai_orchestrator_runtime.execute_research_init_run
    original_recommend = full_ai_orchestrator_runtime.recommend_shadow_planner_action
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fake_execute_research_init_run
    )
    full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
        _fake_recommend_shadow_planner_action
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=2,
            max_hypotheses=5,
            sources={
                "pubmed": True,
                "clinvar": True,
                "drugbank": True,
                "alphafold": True,
            },
            execution_services=services,
            existing_run=run,
            planner_mode=FullAIOrchestratorPlannerMode.GUARDED,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original_execute
        full_ai_orchestrator_runtime.recommend_shadow_planner_action = (
            original_recommend
        )

    assert result.guarded_execution is not None
    assert result.guarded_execution["applied_count"] == 1
    assert result.guarded_execution["verified_count"] == 0
    assert result.guarded_execution["verification_failed_count"] == 1
    assert result.workspace_summary["guarded_readiness"]["status"] == (
        "blocked_verification_failed"
    )
    guarded_action = result.guarded_execution["actions"][0]
    assert guarded_action["verification_status"] == "verification_failed"
    assert guarded_action["verification_reason"] == "ordered_sources_not_completed"
    assert guarded_action["verification_summary"]["incomplete_ordered_sources"] == [
        {
            "source_key": "clinvar",
            "status": "deferred",
        },
    ]
    assert guarded_action["verification_summary"]["unexpected_deferred_sources"] == [
        {
            "source_key": "clinvar",
            "status": "deferred",
        },
    ]


@pytest.mark.asyncio
async def test_execute_run_can_finalize_from_replayed_research_init_result(
    services: HarnessExecutionServices,
) -> None:
    space_id = uuid4()
    run = queue_full_ai_orchestrator_run(
        space_id=space_id,
        title="Full AI Orchestrator Harness",
        objective="Investigate MED13 syndrome",
        seed_terms=["MED13"],
        sources={"pubmed": True, "clinvar": True},
        max_depth=1,
        max_hypotheses=5,
        graph_service_status="ok",
        graph_service_version="test",
        run_registry=services.run_registry,
        artifact_store=services.artifact_store,
        execution_services=services,
    )
    replayed_snapshot = {
        "status": "completed",
        "documents_ingested": 2,
        "proposal_count": 3,
        "pending_questions": [],
        "errors": [],
        "pubmed_results": [{"query": "MED13", "total_found": 2}],
        "driven_terms": ["MED13", "MED13L"],
        "driven_genes_from_pubmed": ["MED13L"],
        "source_results": {
            "pubmed": {
                "selected": True,
                "status": "completed",
                "documents_ingested": 2,
            },
            "clinvar": {
                "selected": True,
                "status": "completed",
                "records_processed": 1,
            },
        },
        "bootstrap_run_id": "bootstrap-run-1",
        "bootstrap_source_type": "pubmed",
        "bootstrap_summary": {"proposal_count": 1},
        "research_brief": {
            "title": "Research Brief: MED13",
            "markdown": "# Brief",
            "sections": [{"heading": "What matters", "body": "Evidence"}],
        },
        "artifact_keys": ["research_init_result"],
        "result_keys": ["research_init_result"],
        "primary_result_key": "research_init_result",
    }
    replayed_result = ResearchInitExecutionResult(
        run=run,
        pubmed_results=(),
        documents_ingested=2,
        proposal_count=3,
        research_state=None,
        pending_questions=[],
        errors=[],
        claim_curation=None,
        research_brief_markdown="# Brief",
    )

    from artana_evidence_api import full_ai_orchestrator_runtime

    async def _fail_execute_research_init_run(**_kwargs):
        raise AssertionError("execute_research_init_run should not be called")

    original = full_ai_orchestrator_runtime.execute_research_init_run
    full_ai_orchestrator_runtime.execute_research_init_run = (
        _fail_execute_research_init_run
    )
    try:
        result = await execute_full_ai_orchestrator_run(
            space_id=space_id,
            title=run.title,
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
            max_depth=1,
            max_hypotheses=5,
            sources={"pubmed": True, "clinvar": True},
            execution_services=services,
            existing_run=run,
            replayed_research_init_result=replayed_result,
            replayed_workspace_snapshot=replayed_snapshot,
        )
    finally:
        full_ai_orchestrator_runtime.execute_research_init_run = original

    workspace = services.artifact_store.get_workspace(space_id=space_id, run_id=run.id)
    assert workspace is not None
    assert result.run.id == run.id
    assert workspace.snapshot["status"] == "completed"
    assert workspace.snapshot["documents_ingested"] == 2
    assert workspace.snapshot["proposal_count"] == 3
    assert workspace.snapshot["primary_result_key"] == "full_ai_orchestrator_result"
    assert (
        "full_ai_orchestrator_decision_history" in workspace.snapshot["artifact_keys"]
    )


def test_step_key_generation_is_stable_for_deterministic_sequence() -> None:
    assert build_step_key(
        action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
        round_number=0,
        source_key="pubmed",
    ) == ("full-ai-orchestrator.v1.round_0.pubmed.query_pubmed")
    assert build_step_key(
        action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        round_number=2,
        source_key=None,
    ) == ("full-ai-orchestrator.v1.round_2.control.run_chase_round")


def test_source_action_and_control_flow_action_separation() -> None:
    assert is_source_action(ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT)
    assert not is_control_action(
        ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
    )
    assert is_control_action(ResearchOrchestratorActionType.STOP)
    assert not is_source_action(ResearchOrchestratorActionType.STOP)


def test_final_stop_decision_always_includes_reason() -> None:
    decision = ResearchOrchestratorDecision(
        decision_id="decision-stop",
        round_number=0,
        action_type=ResearchOrchestratorActionType.STOP,
        action_input={"error_count": 0},
        source_key=None,
        evidence_basis="Run completed.",
        stop_reason="completed",
        step_key="full-ai-orchestrator.v1.round_0.control.stop",
        status="completed",
        metadata={},
    )

    assert decision.stop_reason == "completed"
