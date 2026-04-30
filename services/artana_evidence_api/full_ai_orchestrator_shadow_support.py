"""Shadow planner summary helpers for the full AI orchestrator."""

from __future__ import annotations

import logging
import os
from typing import cast

from artana_evidence_api.full_ai_orchestrator_common_support import (
    _SHADOW_PLANNER_CHECKPOINT_ORDER,
    _normalized_source_key_list,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    ShadowPlannerRecommendationResult,
    build_shadow_planner_comparison,
    build_shadow_planner_workspace_summary,
    recommend_shadow_planner_action,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_array_or_empty,
    json_object,
)

_LOGGER = logging.getLogger(__name__)
_PROGRESS_PERSISTENCE_BACKOFF_SECONDS = float(
    os.getenv(
        "ARTANA_EVIDENCE_API_ORCHESTRATOR_PROGRESS_BACKOFF_SECONDS",
        "30.0",
    ).strip()
    or "30.0",
)

_HARNESS_ID = "full-ai-orchestrator"
_ACTION_REGISTRY_ARTIFACT_KEY = "full_ai_orchestrator_action_registry"
_DECISION_HISTORY_ARTIFACT_KEY = "full_ai_orchestrator_decision_history"
_RESULT_ARTIFACT_KEY = "full_ai_orchestrator_result"
_INITIALIZE_ARTIFACT_KEY = "full_ai_orchestrator_initialize_workspace"
_PUBMED_ARTIFACT_KEY = "full_ai_orchestrator_pubmed_summary"
_DRIVEN_TERMS_ARTIFACT_KEY = "full_ai_orchestrator_driven_terms"
_SOURCE_EXECUTION_ARTIFACT_KEY = "full_ai_orchestrator_source_execution_summary"
_BOOTSTRAP_ARTIFACT_KEY = "full_ai_orchestrator_bootstrap_summary"
_CHASE_ROUNDS_ARTIFACT_KEY = "full_ai_orchestrator_chase_rounds"
_BRIEF_METADATA_ARTIFACT_KEY = "full_ai_orchestrator_brief_metadata"
_PUBMED_REPLAY_ARTIFACT_KEY = "full_ai_orchestrator_pubmed_replay_bundle"
_GUARDED_EXECUTION_ARTIFACT_KEY = "full_ai_orchestrator_guarded_execution"
_GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY = (
    "full_ai_orchestrator_guarded_decision_proofs"
)
_GUARDED_DECISION_PROOF_ARTIFACT_PREFIX = "full_ai_orchestrator_guarded_decision_proof"
_SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY = "full_ai_orchestrator_shadow_planner_workspace"
_SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY = (
    "full_ai_orchestrator_shadow_planner_recommendation"
)
_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY = (
    "full_ai_orchestrator_shadow_planner_comparison"
)
_SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY = "full_ai_orchestrator_shadow_planner_timeline"
_STEP_KEY_VERSION = "v1"
_GUARDED_SKIP_CHASE_ROUND_NUMBER = 2
_GUARDED_CHASE_ROLLOUT_ENV = "ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT"
_GUARDED_ROLLOUT_PROFILE_ENV = "ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE"
_GUARDED_ROLLOUT_POLICY_VERSION = "guarded-rollout.v1"
_GUARDED_READINESS_ARTIFACT_KEY = "full_ai_orchestrator_guarded_readiness"
_TRUE_ENV_VALUES = frozenset({"1", "true", "yes", "on"})
_GUARDED_PROFILE_SHADOW_ONLY = "shadow_only"
_GUARDED_PROFILE_DRY_RUN = FullAIOrchestratorGuardedRolloutProfile.GUARDED_DRY_RUN.value
_GUARDED_PROFILE_CHASE_ONLY = (
    FullAIOrchestratorGuardedRolloutProfile.GUARDED_CHASE_ONLY.value
)
_GUARDED_PROFILE_SOURCE_CHASE = (
    FullAIOrchestratorGuardedRolloutProfile.GUARDED_SOURCE_CHASE.value
)
_GUARDED_PROFILE_LOW_RISK = (
    FullAIOrchestratorGuardedRolloutProfile.GUARDED_LOW_RISK.value
)
_VALID_GUARDED_ROLLOUT_PROFILES = frozenset(
    {
        _GUARDED_PROFILE_SHADOW_ONLY,
        _GUARDED_PROFILE_DRY_RUN,
        _GUARDED_PROFILE_CHASE_ONLY,
        _GUARDED_PROFILE_SOURCE_CHASE,
        _GUARDED_PROFILE_LOW_RISK,
    },
)
_GUARDED_STRATEGY_STRUCTURED_SOURCE = "prioritized_structured_sequence"
_GUARDED_STRATEGY_CHASE_SELECTION = "chase_selection"
_GUARDED_STRATEGY_TERMINAL_CONTROL = "terminal_control_flow"
_GUARDED_STRATEGY_BRIEF_GENERATION = "brief_generation"
_GUARDED_PROFILE_ALLOWED_STRATEGIES = {
    _GUARDED_PROFILE_SHADOW_ONLY: frozenset[str](),
    _GUARDED_PROFILE_DRY_RUN: frozenset[str](),
    _GUARDED_PROFILE_CHASE_ONLY: frozenset(
        {
            _GUARDED_STRATEGY_CHASE_SELECTION,
            _GUARDED_STRATEGY_TERMINAL_CONTROL,
            _GUARDED_STRATEGY_BRIEF_GENERATION,
        },
    ),
    _GUARDED_PROFILE_SOURCE_CHASE: frozenset(
        {
            _GUARDED_STRATEGY_STRUCTURED_SOURCE,
            _GUARDED_STRATEGY_CHASE_SELECTION,
            _GUARDED_STRATEGY_TERMINAL_CONTROL,
        },
    ),
    _GUARDED_PROFILE_LOW_RISK: frozenset(
        {
            _GUARDED_STRATEGY_STRUCTURED_SOURCE,
            _GUARDED_STRATEGY_CHASE_SELECTION,
            _GUARDED_STRATEGY_TERMINAL_CONTROL,
            _GUARDED_STRATEGY_BRIEF_GENERATION,
        },
    ),
}
_CONTROL_ACTIONS = frozenset(
    {
        ResearchOrchestratorActionType.INITIALIZE_WORKSPACE,
        ResearchOrchestratorActionType.DERIVE_DRIVEN_TERMS,
        ResearchOrchestratorActionType.RUN_BOOTSTRAP,
        ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        ResearchOrchestratorActionType.GENERATE_BRIEF,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
        ResearchOrchestratorActionType.STOP,
    },
)
_SOURCE_ACTIONS = frozenset(
    {
        ResearchOrchestratorActionType.QUERY_PUBMED,
        ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
        ResearchOrchestratorActionType.REVIEW_PDF_WORKSET,
        ResearchOrchestratorActionType.REVIEW_TEXT_WORKSET,
        ResearchOrchestratorActionType.LOAD_MONDO_GROUNDING,
        ResearchOrchestratorActionType.RUN_UNIPROT_GROUNDING,
        ResearchOrchestratorActionType.RUN_HGNC_GROUNDING,
        ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
    },
)
_ACTION_REGISTRY: tuple[ResearchOrchestratorActionSpec, ...] = (
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.INITIALIZE_WORKSPACE,
        planner_state="context_only",
        summary="Initialize the durable workspace from request inputs.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="pubmed",
        planner_state="live",
        summary="Run deterministic PubMed discovery queries.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="pubmed",
        planner_state="live",
        summary="Ingest selected PubMed documents and extract evidence-backed proposals.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.DERIVE_DRIVEN_TERMS,
        planner_state="context_only",
        summary="Derive Round 2 driven terms from PubMed findings plus seed terms.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.REVIEW_PDF_WORKSET,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="pdf",
        planner_state="context_only",
        summary="Review the current PDF workset as existing user-supplied evidence.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.REVIEW_TEXT_WORKSET,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="text",
        planner_state="context_only",
        summary="Review the current text workset as existing user-supplied evidence.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.LOAD_MONDO_GROUNDING,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="mondo",
        planner_state="context_only",
        summary="Load MONDO grounding context as a deferred ontology step.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_UNIPROT_GROUNDING,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="uniprot",
        planner_state="reserved",
        summary="Reserve an explicit UniProt grounding action for later phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_HGNC_GROUNDING,
        source_bound=True,
        requires_enabled_source=True,
        default_source_key="hgnc",
        planner_state="reserved",
        summary="Reserve an explicit HGNC grounding action for later phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
        source_bound=True,
        requires_enabled_source=True,
        planner_state="live",
        summary="Run deterministic structured enrichment for one enabled source.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
        planner_state="live",
        summary="Queue and execute governed research bootstrap as a child run.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
        planner_state="live",
        summary="Run one deterministic chase round over newly created entities.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_GRAPH_CONNECTION,
        planner_state="reserved",
        summary="Reserve a graph-connection action for later planner-led phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_HYPOTHESIS_GENERATION,
        planner_state="reserved",
        summary="Reserve a hypothesis-generation action for later planner-led phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.RUN_GRAPH_SEARCH,
        planner_state="reserved",
        summary="Reserve a graph-search action for later planner-led phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.SEARCH_DISCONFIRMING,
        planner_state="reserved",
        summary="Reserve a disconfirming-evidence search action for later phases.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
        planner_state="live",
        summary="Generate and store the final research brief.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.ESCALATE_TO_HUMAN,
        planner_state="live",
        summary="Escalate a blocked or risky run to a human operator.",
    ),
    ResearchOrchestratorActionSpec(
        action_type=ResearchOrchestratorActionType.STOP,
        planner_state="live",
        summary="Record the terminal stop reason for the orchestrator run.",
    ),
)



def _build_shadow_planner_summary(  # noqa: PLR0912, PLR0915
    *,
    timeline: list[JSONObject],
    mode: str,
) -> JSONObject:
    latest_entry = timeline[-1] if timeline else {}
    latest_workspace_summary = (
        latest_entry.get("workspace_summary")
        if isinstance(latest_entry.get("workspace_summary"), dict)
        else {}
    )
    latest_recommendation = (
        latest_entry.get("recommendation")
        if isinstance(latest_entry.get("recommendation"), dict)
        else {}
    )
    latest_comparison = (
        latest_entry.get("comparison")
        if isinstance(latest_entry.get("comparison"), dict)
        else {}
    )
    action_matches = 0
    source_matches = 0
    planner_failures = 0
    invalid_recommendations = 0
    disabled_source_violations = 0
    budget_violations = 0
    fallback_recommendations = 0
    qualitative_rationale_present_count = 0
    telemetry_available_checkpoints = 0
    cost_available_checkpoints = 0
    token_available_checkpoints = 0
    latency_available_checkpoints = 0
    planner_total_prompt_tokens = 0
    planner_total_completion_tokens = 0
    planner_total_cost_usd = 0.0
    planner_total_latency_seconds = 0.0
    for entry in timeline:
        comparison = entry.get("comparison")
        if isinstance(comparison, dict):
            if comparison.get("action_match") is True:
                action_matches += 1
            if comparison.get("source_match") is True:
                source_matches += 1
            if comparison.get("budget_violation") is True:
                budget_violations += 1
            if comparison.get("qualitative_rationale_present") is True:
                qualitative_rationale_present_count += 1
        recommendation = entry.get("recommendation")
        if isinstance(recommendation, dict):
            planner_status = recommendation.get("planner_status")
            if planner_status in {"failed", "invalid"}:
                planner_failures += 1
            if recommendation.get("used_fallback") is True:
                fallback_recommendations += 1
            decision = recommendation.get("decision")
            if (
                isinstance(decision, dict)
                and decision.get("fallback_reason") is not None
            ):
                invalid_recommendations += 1
                if decision.get("fallback_reason") == "source_disabled":
                    disabled_source_violations += 1
            telemetry = _shadow_planner_telemetry_from_recommendation(recommendation)
            if telemetry.get("status") in {"available", "partial"}:
                telemetry_available_checkpoints += 1
            prompt_tokens = _optional_int(telemetry.get("prompt_tokens"))
            completion_tokens = _optional_int(telemetry.get("completion_tokens"))
            cost_usd = _optional_float(telemetry.get("cost_usd"))
            latency_seconds = _optional_float(telemetry.get("latency_seconds"))
            if prompt_tokens is not None and completion_tokens is not None:
                token_available_checkpoints += 1
                planner_total_prompt_tokens += prompt_tokens
                planner_total_completion_tokens += completion_tokens
            if cost_usd is not None:
                cost_available_checkpoints += 1
                planner_total_cost_usd += cost_usd
            if latency_seconds is not None:
                latency_available_checkpoints += 1
                planner_total_latency_seconds += latency_seconds
    planner_total_tokens = None
    if token_available_checkpoints > 0:
        planner_total_tokens = (
            planner_total_prompt_tokens + planner_total_completion_tokens
        )
    cost_tracking = _build_shadow_planner_cost_tracking(
        total_checkpoints=len(timeline),
        telemetry_available_checkpoints=telemetry_available_checkpoints,
        cost_available_checkpoints=cost_available_checkpoints,
        token_available_checkpoints=token_available_checkpoints,
        latency_available_checkpoints=latency_available_checkpoints,
        planner_total_prompt_tokens=(
            planner_total_prompt_tokens if token_available_checkpoints > 0 else None
        ),
        planner_total_completion_tokens=(
            planner_total_completion_tokens if token_available_checkpoints > 0 else None
        ),
        planner_total_tokens=planner_total_tokens,
        planner_total_cost_usd=(
            round(planner_total_cost_usd, 8) if cost_available_checkpoints > 0 else None
        ),
        planner_total_latency_seconds=(
            round(planner_total_latency_seconds, 6)
            if latency_available_checkpoints > 0
            else None
        ),
    )
    return {
        "mode": mode,
        "workspace_key": _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
        "recommendation_key": _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
        "comparison_key": _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
        "timeline_key": _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
        "timeline": timeline,
        "summary": {
            "checkpoint_count": len(timeline),
            "action_match_count": action_matches,
            "source_match_count": source_matches,
            "planner_failure_count": planner_failures,
            "invalid_recommendation_count": invalid_recommendations,
            "fallback_recommendation_count": fallback_recommendations,
            "qualitative_rationale_present_count": (
                qualitative_rationale_present_count
            ),
            "telemetry_available_checkpoints": telemetry_available_checkpoints,
            "cost_available_checkpoints": cost_available_checkpoints,
            "planner_total_cost_usd": cost_tracking.get("planner_total_cost_usd"),
            "latest_checkpoint_key": latest_entry.get("checkpoint_key"),
        },
        "evaluation": {
            "total_checkpoints": len(timeline),
            "action_matches": action_matches,
            "source_matches": source_matches,
            "planner_failures": planner_failures,
            "invalid_recommendations": invalid_recommendations,
            "disabled_source_violations": disabled_source_violations,
            "budget_violations": budget_violations,
            "fallback_recommendations": fallback_recommendations,
            "qualitative_rationale_present_count": (
                qualitative_rationale_present_count
            ),
            "telemetry_available_checkpoints": telemetry_available_checkpoints,
            "cost_available_checkpoints": cost_available_checkpoints,
            "token_available_checkpoints": token_available_checkpoints,
            "latency_available_checkpoints": latency_available_checkpoints,
            "planner_total_prompt_tokens": (
                cost_tracking.get("planner_total_prompt_tokens")
            ),
            "planner_total_completion_tokens": (
                cost_tracking.get("planner_total_completion_tokens")
            ),
            "planner_total_tokens": cost_tracking.get("planner_total_tokens"),
            "planner_total_cost_usd": cost_tracking.get("planner_total_cost_usd"),
            "planner_total_latency_seconds": (
                cost_tracking.get("planner_total_latency_seconds")
            ),
        },
        "cost_tracking": cost_tracking,
        "latest_workspace_summary": latest_workspace_summary,
        "latest_recommendation": latest_recommendation,
        "latest_comparison": latest_comparison,
    }

def _shadow_planner_recommendation_payload(
    *,
    planner_result: object,
    mode: str,
) -> JSONObject:
    typed_planner_result = cast("ShadowPlannerRecommendationResult", planner_result)
    decision = typed_planner_result.decision
    return {
        "mode": mode,
        "planner_status": typed_planner_result.planner_status,
        "used_fallback": typed_planner_result.used_fallback,
        "model_id": typed_planner_result.model_id,
        "agent_run_id": typed_planner_result.agent_run_id,
        "prompt_version": typed_planner_result.prompt_version,
        "validation_error": typed_planner_result.validation_error,
        "error": typed_planner_result.error,
        "telemetry": _shadow_planner_telemetry_payload(
            getattr(planner_result, "telemetry", None),
        ),
        "decision": decision.model_dump(mode="json"),
    }

def _guarded_recommendation_decision_payload(
    *,
    recommendation_payload: JSONObject,
) -> tuple[JSONObject | None, str | None]:
    decision = recommendation_payload.get("decision")
    if not isinstance(decision, dict):
        return None, None
    rationale = decision.get("qualitative_rationale")
    if recommendation_payload.get("planner_status") != "completed":
        return None, None
    if bool(recommendation_payload.get("used_fallback")):
        return None, None
    if recommendation_payload.get("validation_error") is not None:
        return None, None
    if not isinstance(rationale, str) or rationale.strip() == "":
        return None, None
    return decision, rationale

def _guarded_terminal_control_reason(action_type: object) -> str:
    if action_type == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value:
        return "guarded_escalate_to_human"
    return "guarded_stop_requested"

def _accepted_guarded_generate_brief_action(
    *,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
) -> JSONObject | None:
    decision, rationale = _guarded_recommendation_decision_payload(
        recommendation_payload=recommendation_payload,
    )
    if decision is None or rationale is None:
        return None
    if (
        decision.get("action_type")
        != ResearchOrchestratorActionType.GENERATE_BRIEF.value
    ):
        return None
    if decision.get("source_key") is not None:
        return None
    if (
        comparison.get("target_action_type")
        != ResearchOrchestratorActionType.RUN_CHASE_ROUND.value
    ):
        return None
    return {
        "status": "applied",
        "checkpoint_key": comparison.get("checkpoint_key"),
        "applied_action_type": decision.get("action_type"),
        "applied_source_key": decision.get("source_key"),
        "guarded_strategy": _GUARDED_STRATEGY_BRIEF_GENERATION,
        "stop_reason": "guarded_generate_brief",
        "comparison_status": comparison.get("comparison_status"),
        "target_action_type": comparison.get("target_action_type"),
        "target_source_key": comparison.get("target_source_key"),
        "planner_status": recommendation_payload.get("planner_status"),
        "model_id": recommendation_payload.get("model_id"),
        "agent_run_id": recommendation_payload.get("agent_run_id"),
        "prompt_version": recommendation_payload.get("prompt_version"),
        "decision_id": decision.get("decision_id"),
        "step_key": decision.get("step_key"),
        "evidence_basis": decision.get("evidence_basis"),
        "qualitative_rationale": rationale,
        "expected_value_band": decision.get("expected_value_band"),
        "risk_level": decision.get("risk_level"),
        "verification_status": "pending",
        "verification_reason": None,
        "verification_summary": None,
        "verified_at_phase": None,
    }

def _accepted_guarded_control_flow_action(
    *,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
) -> JSONObject | None:
    decision, rationale = _guarded_recommendation_decision_payload(
        recommendation_payload=recommendation_payload,
    )
    if decision is None or rationale is None:
        return None
    if decision.get("source_key") is not None:
        return None
    if decision.get("action_type") not in {
        ResearchOrchestratorActionType.STOP.value,
        ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value,
    }:
        return None
    target_action_type = comparison.get("target_action_type")
    if target_action_type not in {
        ResearchOrchestratorActionType.RUN_CHASE_ROUND.value,
        ResearchOrchestratorActionType.STOP.value,
    }:
        return None
    if (
        target_action_type == ResearchOrchestratorActionType.STOP.value
        and decision.get("action_type") != ResearchOrchestratorActionType.STOP.value
    ):
        return None
    stop_reason = _guarded_terminal_control_reason(decision.get("action_type"))
    return {
        "status": "applied",
        "checkpoint_key": comparison.get("checkpoint_key"),
        "applied_action_type": decision.get("action_type"),
        "applied_source_key": decision.get("source_key"),
        "guarded_strategy": _GUARDED_STRATEGY_TERMINAL_CONTROL,
        "comparison_status": comparison.get("comparison_status"),
        "target_action_type": comparison.get("target_action_type"),
        "target_source_key": comparison.get("target_source_key"),
        "planner_status": recommendation_payload.get("planner_status"),
        "model_id": recommendation_payload.get("model_id"),
        "agent_run_id": recommendation_payload.get("agent_run_id"),
        "prompt_version": recommendation_payload.get("prompt_version"),
        "decision_id": decision.get("decision_id"),
        "step_key": decision.get("step_key"),
        "evidence_basis": decision.get("evidence_basis"),
        "qualitative_rationale": rationale,
        "expected_value_band": decision.get("expected_value_band"),
        "risk_level": decision.get("risk_level"),
        "stop_reason": stop_reason,
        "verification_status": "pending",
        "verification_reason": None,
        "verification_summary": None,
        "verified_at_phase": None,
    }

def _accepted_guarded_chase_selection_action(
    *,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
    round_number: int,
    chase_candidates: tuple[ResearchOrchestratorChaseCandidate, ...],
    deterministic_selection: ResearchOrchestratorChaseSelection,
) -> JSONObject | None:
    decision, rationale = _guarded_recommendation_decision_payload(
        recommendation_payload=recommendation_payload,
    )
    if (
        decision is None
        or rationale is None
        or decision.get("source_key") is not None
        or (
            decision.get("action_type")
            != ResearchOrchestratorActionType.RUN_CHASE_ROUND.value
        )
        or (
            comparison.get("target_action_type")
            != ResearchOrchestratorActionType.RUN_CHASE_ROUND.value
        )
    ):
        return None
    action_input = decision.get("action_input")
    if not isinstance(action_input, dict):
        return None
    selected_entity_ids = _normalized_source_key_list(
        action_input.get("selected_entity_ids"),
    )
    selected_labels = _normalized_source_key_list(action_input.get("selected_labels"))
    selection_basis = action_input.get("selection_basis")
    if (
        not selected_entity_ids
        or not selected_labels
        or len(selected_entity_ids) != len(selected_labels)
        or not isinstance(selection_basis, str)
        or selection_basis == ""
    ):
        return None
    if len(set(selected_entity_ids)) != len(selected_entity_ids):
        return None
    candidate_map = {candidate.entity_id: candidate for candidate in chase_candidates}
    deterministic_entity_order = {
        entity_id: index
        for index, entity_id in enumerate(
            deterministic_selection.selected_entity_ids,
        )
    }
    deterministic_label_by_entity_id = dict(
        zip(
            deterministic_selection.selected_entity_ids,
            deterministic_selection.selected_labels,
            strict=True,
        )
    )
    invalid_selection = False
    previous_index = -1
    for entity_id, selected_label in zip(
        selected_entity_ids,
        selected_labels,
        strict=True,
    ):
        candidate = candidate_map.get(entity_id)
        deterministic_index = deterministic_entity_order.get(entity_id)
        deterministic_label = deterministic_label_by_entity_id.get(entity_id)
        if (
            candidate is None
            or candidate.display_label != selected_label
            or deterministic_index is None
            or deterministic_label != selected_label
            or deterministic_index <= previous_index
        ):
            invalid_selection = True
            break
        previous_index = deterministic_index
    if invalid_selection:
        return None
    deterministic_selected_entity_ids = list(
        deterministic_selection.selected_entity_ids
    )
    deterministic_selected_labels = list(deterministic_selection.selected_labels)
    return {
        "status": "applied",
        "checkpoint_key": comparison.get("checkpoint_key"),
        "applied_action_type": decision.get("action_type"),
        "applied_source_key": decision.get("source_key"),
        "guarded_strategy": _GUARDED_STRATEGY_CHASE_SELECTION,
        "round_number": round_number,
        "comparison_status": comparison.get("comparison_status"),
        "target_action_type": comparison.get("target_action_type"),
        "target_source_key": comparison.get("target_source_key"),
        "planner_status": recommendation_payload.get("planner_status"),
        "model_id": recommendation_payload.get("model_id"),
        "agent_run_id": recommendation_payload.get("agent_run_id"),
        "prompt_version": recommendation_payload.get("prompt_version"),
        "decision_id": decision.get("decision_id"),
        "step_key": decision.get("step_key"),
        "evidence_basis": decision.get("evidence_basis"),
        "qualitative_rationale": rationale,
        "expected_value_band": decision.get("expected_value_band"),
        "risk_level": decision.get("risk_level"),
        "selected_entity_ids": selected_entity_ids,
        "selected_labels": selected_labels,
        "selection_basis": selection_basis,
        "deterministic_selected_entity_ids": deterministic_selected_entity_ids,
        "deterministic_selected_labels": deterministic_selected_labels,
        "selection_scope": (
            "exact"
            if (
                selected_entity_ids == deterministic_selected_entity_ids
                and selected_labels == deterministic_selected_labels
            )
            else "subset"
        ),
        "verification_status": "pending",
        "verification_reason": None,
        "verification_summary": None,
        "verified_at_phase": None,
    }

def _accepted_guarded_structured_source_action(
    *,
    recommendation_payload: JSONObject,
    comparison: JSONObject,
    available_source_keys: tuple[str, ...],
) -> JSONObject | None:
    decision, rationale = _guarded_recommendation_decision_payload(
        recommendation_payload=recommendation_payload,
    )
    if decision is None or rationale is None:
        return None
    if (
        decision.get("action_type")
        != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT.value
    ):
        return None
    source_key = decision.get("source_key")
    if not isinstance(source_key, str):
        return None
    if source_key not in available_source_keys:
        return None
    if (
        comparison.get("target_action_type")
        != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT.value
    ):
        return None
    return {
        "status": "applied",
        "checkpoint_key": comparison.get("checkpoint_key"),
        "applied_action_type": decision.get("action_type"),
        "applied_source_key": source_key,
        "guarded_strategy": _GUARDED_STRATEGY_STRUCTURED_SOURCE,
        "comparison_status": comparison.get("comparison_status"),
        "target_action_type": comparison.get("target_action_type"),
        "target_source_key": comparison.get("target_source_key"),
        "planner_status": recommendation_payload.get("planner_status"),
        "model_id": recommendation_payload.get("model_id"),
        "agent_run_id": recommendation_payload.get("agent_run_id"),
        "prompt_version": recommendation_payload.get("prompt_version"),
        "decision_id": decision.get("decision_id"),
        "step_key": decision.get("step_key"),
        "evidence_basis": decision.get("evidence_basis"),
        "qualitative_rationale": rationale,
        "expected_value_band": decision.get("expected_value_band"),
        "risk_level": decision.get("risk_level"),
        "verification_status": "pending",
        "verification_reason": None,
        "verification_summary": None,
        "verified_at_phase": None,
    }

def _shadow_planner_telemetry_payload(telemetry: object) -> JSONObject:
    if telemetry is None:
        return {
            "status": "unavailable",
            "model_terminal_count": 0,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cost_usd": None,
            "latency_seconds": None,
            "tool_call_count": 0,
        }
    return {
        "status": getattr(telemetry, "status", "unavailable"),
        "model_terminal_count": getattr(telemetry, "model_terminal_count", 0),
        "prompt_tokens": getattr(telemetry, "prompt_tokens", None),
        "completion_tokens": getattr(telemetry, "completion_tokens", None),
        "total_tokens": getattr(telemetry, "total_tokens", None),
        "cost_usd": getattr(telemetry, "cost_usd", None),
        "latency_seconds": getattr(telemetry, "latency_seconds", None),
        "tool_call_count": getattr(telemetry, "tool_call_count", 0),
    }

def _shadow_planner_telemetry_from_recommendation(
    recommendation: JSONObject,
) -> JSONObject:
    telemetry = recommendation.get("telemetry")
    return dict(telemetry) if isinstance(telemetry, dict) else {}

def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None

def _optional_float(value: object) -> float | None:
    if isinstance(value, int):
        return float(value)
    return value if isinstance(value, float) else None

def _build_shadow_planner_cost_tracking(  # noqa: PLR0913
    *,
    total_checkpoints: int,
    telemetry_available_checkpoints: int,
    cost_available_checkpoints: int,
    token_available_checkpoints: int,
    latency_available_checkpoints: int,
    planner_total_prompt_tokens: int | None,
    planner_total_completion_tokens: int | None,
    planner_total_tokens: int | None,
    planner_total_cost_usd: float | None,
    planner_total_latency_seconds: float | None,
) -> JSONObject:
    status = "unavailable"
    if (
        total_checkpoints > 0
        and cost_available_checkpoints == total_checkpoints
        and token_available_checkpoints == total_checkpoints
        and latency_available_checkpoints == total_checkpoints
    ):
        status = "available"
    elif (
        telemetry_available_checkpoints > 0
        or cost_available_checkpoints > 0
        or token_available_checkpoints > 0
        or latency_available_checkpoints > 0
    ):
        status = "partial"
    return {
        "status": status,
        "total_checkpoints": total_checkpoints,
        "telemetry_available_checkpoints": telemetry_available_checkpoints,
        "cost_available_checkpoints": cost_available_checkpoints,
        "token_available_checkpoints": token_available_checkpoints,
        "latency_available_checkpoints": latency_available_checkpoints,
        "planner_total_prompt_tokens": planner_total_prompt_tokens,
        "planner_total_completion_tokens": planner_total_completion_tokens,
        "planner_total_tokens": planner_total_tokens,
        "planner_total_cost_usd": planner_total_cost_usd,
        "planner_total_latency_seconds": planner_total_latency_seconds,
    }

def _decision_prior_to(
    *,
    decisions: list[ResearchOrchestratorDecision],
) -> list[JSONObject]:
    return [decision.model_dump(mode="json") for decision in decisions]

def _first_comparable_decision(
    *,
    decisions: list[ResearchOrchestratorDecision],
) -> ResearchOrchestratorDecision | None:
    for decision in decisions:
        if decision.action_type in {
            ResearchOrchestratorActionType.INITIALIZE_WORKSPACE,
            ResearchOrchestratorActionType.STOP,
        }:
            continue
        if decision.status == "skipped":
            continue
        return decision
    return None

def _find_decision(
    *,
    decisions: list[ResearchOrchestratorDecision],
    action_type: ResearchOrchestratorActionType,
    round_number: int = 0,
    source_key: str | None = None,
) -> ResearchOrchestratorDecision | None:
    for decision in decisions:
        if (
            decision.action_type == action_type
            and decision.round_number == round_number
            and decision.source_key == source_key
        ):
            return decision
    return None

def _find_first_structured_enrichment_decision(
    *,
    decisions: list[ResearchOrchestratorDecision],
) -> ResearchOrchestratorDecision | None:
    for decision in decisions:
        if (
            decision.action_type
            != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT
        ):
            continue
        if decision.status == "skipped":
            continue
        return decision
    return None

def _checkpoint_target_decision(
    *,
    checkpoint_key: str,
    decisions: list[ResearchOrchestratorDecision],
    workspace_summary: JSONObject | None = None,
) -> ResearchOrchestratorDecision | None:
    target: ResearchOrchestratorDecision | None = None
    if checkpoint_key == "before_first_action":
        target = _first_comparable_decision(decisions=decisions)
    elif checkpoint_key == "after_pubmed_discovery":
        target = _find_decision(
            decisions=decisions,
            action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
            source_key="pubmed",
        )
    elif checkpoint_key in {"after_pubmed_ingest_extract", "after_driven_terms_ready"}:
        structured_target = _find_first_structured_enrichment_decision(
            decisions=decisions,
        )
        target = structured_target or _find_decision(
            decisions=decisions,
            action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
        )
    else:
        chase_round_number_by_checkpoint = {
            "after_bootstrap": 1,
            "after_chase_round_1": 2,
        }
        chase_round_number = chase_round_number_by_checkpoint.get(checkpoint_key)
        if chase_round_number is not None:
            synthetic_stop_target = _synthetic_chase_stop_target(
                checkpoint_key=checkpoint_key,
                chase_round_number=chase_round_number,
                workspace_summary=workspace_summary,
            )
            if synthetic_stop_target is not None:
                return synthetic_stop_target
            target = _find_decision(
                decisions=decisions,
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                round_number=chase_round_number,
            )
            if target is None:
                checkpoint_key = "before_brief_generation"
        if target is None and checkpoint_key in {
            "after_chase_round_2",
            "before_brief_generation",
        }:
            target = _find_decision(
                decisions=decisions,
                action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
            )
        elif target is None and checkpoint_key == "before_terminal_stop":
            target = _find_decision(
                decisions=decisions,
                action_type=ResearchOrchestratorActionType.STOP,
            )
    return target

def _synthetic_chase_stop_target(
    *,
    checkpoint_key: str,
    chase_round_number: int,
    workspace_summary: JSONObject | None,
) -> ResearchOrchestratorDecision | None:
    if not isinstance(workspace_summary, dict):
        return None
    deterministic_selection = workspace_summary.get("deterministic_selection")
    stop_reason: str | None = None
    if isinstance(deterministic_selection, dict):
        raw_stop_reason = deterministic_selection.get("stop_reason")
        if deterministic_selection.get("stop_instead") is True:
            stop_reason = (
                str(raw_stop_reason)
                if isinstance(raw_stop_reason, str) and raw_stop_reason.strip()
                else "threshold_not_met"
            )
    if stop_reason is None:
        threshold_met = workspace_summary.get("deterministic_threshold_met")
        chase_candidates = workspace_summary.get("chase_candidates")
        if (
            threshold_met is False
            and isinstance(chase_candidates, list)
            and not chase_candidates
        ):
            stop_reason = "threshold_not_met"
    if stop_reason is None:
        return None
    return ResearchOrchestratorDecision(
        decision_id=f"synthetic-{checkpoint_key}-stop",
        round_number=chase_round_number,
        action_type=ResearchOrchestratorActionType.STOP,
        action_input={
            "checkpoint_key": checkpoint_key,
            "synthetic_deterministic_target": True,
        },
        source_key=None,
        evidence_basis=(
            "The workspace summary indicates the deterministic chase baseline "
            "did not expose a continuing chase selection at this checkpoint."
        ),
        stop_reason=stop_reason,
        step_key=f"full-ai-orchestrator.v1.synthetic.{checkpoint_key}.control.stop",
        status="completed",
        expected_value_band="low",
        qualitative_rationale=(
            "The deterministic chase threshold was not met, so the comparable "
            "baseline action at this checkpoint is to stop rather than open a "
            "new chase round."
        ),
        risk_level="low",
        requires_approval=False,
        metadata={"synthetic_deterministic_target": True},
    )

def _phase_record(
    *,
    phase_records: dict[str, list[JSONObject]],
    phase: str,
) -> JSONObject | None:
    records = phase_records.get(phase)
    if not isinstance(records, list) or not records:
        return None
    return records[0]

def _phase_record_with_chase(
    *,
    phase_records: dict[str, list[JSONObject]],
    round_number: int,
) -> JSONObject | None:
    for phase in ("deferred_mondo", "completed"):
        records = phase_records.get(phase)
        if not isinstance(records, list):
            continue
        for record in records:
            workspace_snapshot = record.get("workspace_snapshot")
            if not isinstance(workspace_snapshot, dict):
                continue
            if isinstance(workspace_snapshot.get(f"chase_round_{round_number}"), dict):
                return record
    next_phase = f"chase_round_{round_number + 1}"
    return _phase_record(phase_records=phase_records, phase=next_phase)

def _checkpoint_phase_record_map(
    *,
    initial_workspace_summary: JSONObject,
    initial_decisions: list[ResearchOrchestratorDecision],
    phase_records: dict[str, list[JSONObject]],
    final_workspace_snapshot: JSONObject,
    final_decisions: list[ResearchOrchestratorDecision],
) -> dict[str, JSONObject]:
    checkpoint_map: dict[str, JSONObject] = {
        "before_first_action": {
            "workspace_summary": initial_workspace_summary,
            "prior_decisions": [
                decision.model_dump(mode="json") for decision in initial_decisions
            ],
        },
    }
    for checkpoint_key, phase in (
        ("after_pubmed_discovery", "document_ingestion"),
        ("after_pubmed_ingest_extract", "structured_enrichment"),
        ("after_driven_terms_ready", "structured_enrichment"),
        ("after_bootstrap", "chase_round_1"),
        ("before_brief_generation", "completed"),
        ("before_terminal_stop", "completed"),
    ):
        record = _phase_record(phase_records=phase_records, phase=phase)
        if record is not None:
            checkpoint_map[checkpoint_key] = record
    chase_one_record = _phase_record_with_chase(
        phase_records=phase_records, round_number=1
    )
    if chase_one_record is not None:
        checkpoint_map["after_chase_round_1"] = chase_one_record
    chase_two_record = _phase_record_with_chase(
        phase_records=phase_records, round_number=2
    )
    if chase_two_record is not None:
        checkpoint_map["after_chase_round_2"] = chase_two_record
    if "after_bootstrap" not in checkpoint_map:
        for phase in ("deferred_mondo", "completed"):
            record = _phase_record(phase_records=phase_records, phase=phase)
            if record is not None:
                checkpoint_map["after_bootstrap"] = record
                break
    final_record: JSONObject = {
        "workspace_snapshot": final_workspace_snapshot,
        "decisions": [decision.model_dump(mode="json") for decision in final_decisions],
    }
    checkpoint_map.setdefault("before_brief_generation", final_record)
    checkpoint_map.setdefault("before_terminal_stop", final_record)
    return checkpoint_map

async def _build_shadow_planner_timeline(  # noqa: PLR0913
    *,
    objective: str,
    seed_terms: list[str],
    sources: ResearchSpaceSourcePreferences,
    max_depth: int,
    max_hypotheses: int,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
    initial_workspace_summary: JSONObject,
    initial_decisions: list[ResearchOrchestratorDecision],
    phase_records: dict[str, list[JSONObject]],
    final_workspace_snapshot: JSONObject,
    final_decisions: list[ResearchOrchestratorDecision],
) -> list[JSONObject]:
    checkpoint_records = _checkpoint_phase_record_map(
        initial_workspace_summary=initial_workspace_summary,
        initial_decisions=initial_decisions,
        phase_records=phase_records,
        final_workspace_snapshot=final_workspace_snapshot,
        final_decisions=final_decisions,
    )
    timeline: list[JSONObject] = []
    for checkpoint_key in _SHADOW_PLANNER_CHECKPOINT_ORDER:
        record = checkpoint_records.get(checkpoint_key)
        if not isinstance(record, dict):
            continue
        record_workspace = record.get("workspace_summary")
        if isinstance(record_workspace, dict):
            workspace_summary = record_workspace
        else:
            workspace_snapshot = record.get("workspace_snapshot")
            workspace_summary = build_shadow_planner_workspace_summary(
                checkpoint_key=checkpoint_key,
                objective=objective,
                seed_terms=seed_terms,
                sources=sources,
                max_depth=max_depth,
                max_hypotheses=max_hypotheses,
                workspace_snapshot=(
                    workspace_snapshot if isinstance(workspace_snapshot, dict) else {}
                ),
                prior_decisions=[
                    decision_payload
                    for item in json_array_or_empty(record.get("decisions"))
                    if (decision_payload := json_object(item)) is not None
                ],
                action_registry=action_registry,
            )
        planner_result = await recommend_shadow_planner_action(
            checkpoint_key=checkpoint_key,
            objective=objective,
            workspace_summary=workspace_summary,
            sources=sources,
            action_registry=action_registry,
            harness_id=_HARNESS_ID,
            step_key_version=_STEP_KEY_VERSION,
        )
        comparison = build_shadow_planner_comparison(
            checkpoint_key=checkpoint_key,
            planner_result=planner_result,
            deterministic_target=_checkpoint_target_decision(
                checkpoint_key=checkpoint_key,
                decisions=final_decisions,
                workspace_summary=workspace_summary,
            ),
            workspace_summary=workspace_summary,
        )
        timeline.append(
            {
                "checkpoint_key": checkpoint_key,
                "workspace_summary": workspace_summary,
                "recommendation": _shadow_planner_recommendation_payload(
                    planner_result=planner_result,
                    mode="shadow",
                ),
                "comparison": comparison,
            }
        )
    return timeline

