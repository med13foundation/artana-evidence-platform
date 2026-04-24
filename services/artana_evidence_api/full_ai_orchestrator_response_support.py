"""Response and artifact helpers for the full AI orchestrator."""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, UUID, uuid5

from artana_evidence_api.full_ai_orchestrator_common_support import (
    _STRUCTURED_ENRICHMENT_SOURCES,
    _chase_round_action_input_from_workspace,
    _chase_round_metadata_from_workspace,
    _chase_round_stop_reason,
    _source_decision_status,
    build_step_key,
    require_action_enabled_for_sources,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.research_init_runtime import (
    ResearchInitExecutionResult,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
    json_array_or_empty,
    json_object,
    json_object_or_empty,
)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore

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



def _build_workspace_summary(*, workspace_snapshot: JSONObject) -> JSONObject:
    return {
        "status": workspace_snapshot.get("status"),
        "current_round": workspace_snapshot.get("current_round", 0),
        "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
        "proposal_count": workspace_snapshot.get("proposal_count", 0),
        "bootstrap_run_id": workspace_snapshot.get("bootstrap_run_id"),
        "bootstrap_source_type": workspace_snapshot.get("bootstrap_source_type"),
        "shadow_planner_mode": workspace_snapshot.get("shadow_planner_mode"),
        "planner_execution_mode": workspace_snapshot.get("planner_execution_mode"),
        "guarded_rollout_profile": workspace_snapshot.get("guarded_rollout_profile"),
        "guarded_rollout_profile_source": workspace_snapshot.get(
            "guarded_rollout_profile_source",
        ),
        "guarded_rollout_policy": json_object(
            workspace_snapshot.get("guarded_rollout_policy")
        ),
        "guarded_chase_rollout_enabled": workspace_snapshot.get(
            "guarded_chase_rollout_enabled",
        ),
        "shadow_planner_recommendation_key": workspace_snapshot.get(
            "shadow_planner_recommendation_key",
        ),
        "shadow_planner_comparison_key": workspace_snapshot.get(
            "shadow_planner_comparison_key",
        ),
        "shadow_planner_timeline_key": workspace_snapshot.get(
            "shadow_planner_timeline_key",
        ),
        "guarded_execution_log_key": workspace_snapshot.get(
            "guarded_execution_log_key",
        ),
        "guarded_readiness_key": workspace_snapshot.get("guarded_readiness_key"),
        "guarded_execution": json_object(workspace_snapshot.get("guarded_execution")),
        "guarded_readiness": json_object(workspace_snapshot.get("guarded_readiness")),
        "pending_question_count": len(
            json_array_or_empty(workspace_snapshot.get("pending_questions"))
        ),
        "artifact_keys": json_array_or_empty(workspace_snapshot.get("artifact_keys")),
        "result_keys": json_array_or_empty(workspace_snapshot.get("result_keys")),
    }

def _sanitize_replayed_workspace_snapshot(
    snapshot: JSONObject | None,
) -> JSONObject:
    if not isinstance(snapshot, dict):
        return {}
    sanitized = deepcopy(snapshot)
    for transient_key in ("artifact_keys", "result_keys", "primary_result_key"):
        sanitized.pop(transient_key, None)
    return sanitized

def _build_source_execution_summary(
    *,
    selected_sources: ResearchSpaceSourcePreferences,
    workspace_snapshot: JSONObject,
    research_init_result: ResearchInitExecutionResult,
) -> JSONObject:
    source_results = workspace_snapshot.get("source_results")
    return {
        "selected_sources": json_object_or_empty(selected_sources),
        "source_results": json_object_or_empty(source_results),
        "pubmed_result_count": len(research_init_result.pubmed_results),
        "documents_ingested": research_init_result.documents_ingested,
        "proposal_count": research_init_result.proposal_count,
    }

def _build_brief_metadata(
    *,
    workspace_snapshot: JSONObject,
    research_init_result: ResearchInitExecutionResult,
) -> JSONObject:
    research_brief = workspace_snapshot.get("research_brief")
    if not isinstance(research_brief, dict):
        return {
            "result_key": "research_brief",
            "present": False,
            "markdown_length": 0,
            "section_count": 0,
            "llm_markdown_present": research_init_result.research_brief_markdown
            is not None,
        }
    markdown = research_brief.get("markdown")
    sections = research_brief.get("sections")
    title = research_brief.get("title")
    return {
        "result_key": "research_brief",
        "present": True,
        "title": title if isinstance(title, str) else None,
        "markdown_length": len(markdown) if isinstance(markdown, str) else 0,
        "section_count": len(sections) if isinstance(sections, list) else 0,
        "llm_markdown_present": research_init_result.research_brief_markdown
        is not None,
    }

def _build_decision_history(  # noqa: PLR0913
    *,
    objective: str,
    seed_terms: list[str],
    max_depth: int,
    max_hypotheses: int,
    sources: ResearchSpaceSourcePreferences,
    workspace_snapshot: JSONObject,
    research_init_result: ResearchInitExecutionResult,
    source_execution_summary: JSONObject,
    bootstrap_summary: JSONObject | None,
    brief_metadata: JSONObject,
) -> list[ResearchOrchestratorDecision]:
    decisions: list[ResearchOrchestratorDecision] = []
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.INITIALIZE_WORKSPACE,
            round_number=0,
            action_input={
                "objective": objective,
                "seed_terms": list(seed_terms),
                "max_depth": max_depth,
                "max_hypotheses": max_hypotheses,
            },
            evidence_basis="Queued Phase 1 deterministic full AI orchestrator baseline.",
            status="completed",
            metadata={"enabled_sources": json_object_or_empty(sources)},
        ),
    )
    pubmed_enabled = sources.get("pubmed", True)
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
            round_number=0,
            source_key="pubmed",
            action_input={"seed_terms": list(seed_terms)},
            evidence_basis="Deterministic research-init PubMed discovery phase.",
            status="completed" if pubmed_enabled else "skipped",
            stop_reason=None if pubmed_enabled else "source_disabled",
            metadata={"pubmed_result_count": len(research_init_result.pubmed_results)},
        ),
    )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
            round_number=0,
            source_key="pubmed",
            action_input={"max_hypotheses": max_hypotheses},
            evidence_basis="Selected PubMed records were ingested through the existing deterministic pipeline.",
            status="completed" if pubmed_enabled else "skipped",
            stop_reason=None if pubmed_enabled else "source_disabled",
            metadata={
                "documents_ingested": research_init_result.documents_ingested,
                "proposal_count": research_init_result.proposal_count,
            },
        ),
    )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.DERIVE_DRIVEN_TERMS,
            round_number=0,
            action_input={
                "seed_terms": list(seed_terms),
                "driven_terms_count": len(
                    json_array_or_empty(workspace_snapshot.get("driven_terms"))
                ),
            },
            evidence_basis="Driven terms were derived from PubMed findings plus initial seed terms.",
            status="completed",
            metadata={
                "driven_terms": json_array_or_empty(
                    workspace_snapshot.get("driven_terms")
                ),
                "driven_genes_from_pubmed": (
                    json_array_or_empty(
                        workspace_snapshot.get("driven_genes_from_pubmed")
                    )
                ),
            },
        ),
    )
    for source_key in _STRUCTURED_ENRICHMENT_SOURCES:
        if not sources.get(source_key, False):
            continue
        require_action_enabled_for_sources(
            action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
            source_key=source_key,
            sources=sources,
        )
        source_results = source_execution_summary.get("source_results")
        source_summary = (
            source_results.get(source_key, {})
            if isinstance(source_results, dict)
            and isinstance(source_results.get(source_key), dict)
            else {}
        )
        structured_status, structured_stop_reason = _source_decision_status(
            source_summary=source_summary,
            pending_status="running",
        )
        decisions.append(
            _build_decision(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                round_number=0,
                source_key=source_key,
                action_input={"source_key": source_key},
                evidence_basis="Structured enrichment reused the current deterministic research-init source family handlers.",
                status=structured_status,
                stop_reason=structured_stop_reason,
                metadata={"source_summary": source_summary},
            ),
        )
    bootstrap_run_id = workspace_snapshot.get("bootstrap_run_id")
    bootstrap_status = "completed" if isinstance(bootstrap_run_id, str) else "skipped"
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
            round_number=0,
            action_input={
                "bootstrap_source_type": workspace_snapshot.get(
                    "bootstrap_source_type"
                ),
            },
            evidence_basis="Bootstrap execution delegated to the governed research-bootstrap runtime.",
            status=bootstrap_status,
            stop_reason=(
                None if bootstrap_status == "completed" else "bootstrap_not_triggered"
            ),
            metadata={
                "bootstrap_run_id": bootstrap_run_id,
                "bootstrap_summary": bootstrap_summary or {},
            },
        ),
    )
    guarded_stop_after_chase_round = (
        workspace_snapshot.get("guarded_stop_after_chase_round")
        if isinstance(workspace_snapshot.get("guarded_stop_after_chase_round"), int)
        else None
    )
    guarded_terminal_control_after_chase_round = (
        workspace_snapshot.get("guarded_terminal_control_after_chase_round")
        if isinstance(
            workspace_snapshot.get("guarded_terminal_control_after_chase_round"),
            int,
        )
        else None
    )
    guarded_terminal_control_action = json_object_or_empty(
        workspace_snapshot.get("guarded_terminal_control_action")
    )
    guarded_execution_summary = json_object_or_empty(
        workspace_snapshot.get("guarded_execution")
    )
    for chase_round in (1, 2):
        chase_summary = workspace_snapshot.get(f"chase_round_{chase_round}")
        chase_action_input = _chase_round_action_input_from_workspace(
            workspace_snapshot=workspace_snapshot,
            round_number=chase_round,
        )
        chase_metadata = _chase_round_metadata_from_workspace(
            workspace_snapshot=workspace_snapshot,
            round_number=chase_round,
        )
        raw_guarded_stop_reason = guarded_terminal_control_action.get("stop_reason")
        guarded_terminal_stop_reason = (
            raw_guarded_stop_reason
            if isinstance(raw_guarded_stop_reason, str)
            else None
        )
        guarded_stop_reason = (
            "guarded_generate_brief"
            if guarded_stop_after_chase_round == chase_round - 1
            else guarded_terminal_stop_reason
            if guarded_terminal_control_after_chase_round == chase_round - 1
            else None
        )
        decisions.append(
            _build_decision(
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                round_number=chase_round,
                action_input=chase_action_input,
                evidence_basis="Chase rounds reused the current deterministic entity-chase thresholds.",
                status=("completed" if isinstance(chase_summary, dict) else "skipped"),
                stop_reason=(
                    None
                    if isinstance(chase_summary, dict)
                    else (
                        guarded_stop_reason
                        if guarded_stop_reason is not None
                        else _chase_round_stop_reason(chase_metadata)
                    )
                ),
                metadata=(
                    chase_metadata
                    if chase_metadata
                    else (
                        {
                            "guarded_execution": guarded_execution_summary,
                            "guarded_terminal_control_action": (
                                guarded_terminal_control_action
                                if guarded_terminal_control_action
                                else {}
                            ),
                        }
                        if guarded_stop_reason is not None
                        else {}
                    )
                ),
            ),
        )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
            round_number=0,
            action_input={"result_key": "research_brief"},
            evidence_basis="Final brief generation reused the deterministic brief builder with optional LLM enhancement.",
            status="completed" if brief_metadata.get("present") else "skipped",
            stop_reason=(
                None if brief_metadata.get("present") else "brief_not_available"
            ),
            metadata=brief_metadata,
        ),
    )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.STOP,
            round_number=0,
            action_input={
                "error_count": len(research_init_result.errors),
                "pending_question_count": len(research_init_result.pending_questions),
            },
            evidence_basis=(
                "Deterministic baseline run reached a terminal state."
                if not guarded_terminal_control_action
                else "Guarded terminal control flow recorded the terminal decision."
            ),
            status="completed",
            stop_reason=(
                raw_stop_reason
                if isinstance(
                    (raw_stop_reason := guarded_terminal_control_action.get("stop_reason")),
                    str,
                )
                else _stop_reason(
                    research_init_result=research_init_result,
                    workspace_snapshot=workspace_snapshot,
                )
            ),
            metadata=(
                {
                    "final_status": workspace_snapshot.get("status", "completed"),
                    "guarded_terminal_control_action": guarded_terminal_control_action,
                }
                if guarded_terminal_control_action
                else {
                    "final_status": workspace_snapshot.get("status", "completed"),
                }
            ),
        ),
    )
    return decisions

def _build_decision(
    *,
    action_type: ResearchOrchestratorActionType,
    round_number: int,
    action_input: JSONObject,
    evidence_basis: str,
    status: str,
    source_key: str | None = None,
    stop_reason: str | None = None,
    metadata: JSONObject | None = None,
) -> ResearchOrchestratorDecision:
    step_key = build_step_key(
        action_type=action_type,
        round_number=round_number,
        source_key=source_key,
    )
    decision_id = str(
        uuid5(
            NAMESPACE_URL,
            (
                f"{_HARNESS_ID}:{step_key}:"
                f"{json.dumps(action_input, sort_keys=True, default=str)}"
            ),
        ),
    )
    return ResearchOrchestratorDecision(
        decision_id=decision_id,
        round_number=round_number,
        action_type=action_type,
        action_input=action_input,
        source_key=source_key,
        evidence_basis=evidence_basis,
        stop_reason=stop_reason,
        step_key=step_key,
        status=status,
        metadata={} if metadata is None else metadata,
    )

def _stop_reason(
    *,
    research_init_result: ResearchInitExecutionResult,
    workspace_snapshot: JSONObject,
) -> str:
    if research_init_result.errors:
        return "completed_with_errors"
    pending_questions = workspace_snapshot.get("pending_questions")
    if isinstance(pending_questions, list) and pending_questions:
        return "awaiting_scope_refinement"
    return "completed"

def _collect_chase_round_summaries(
    *, workspace_snapshot: JSONObject
) -> list[JSONObject]:
    summaries: list[JSONObject] = []
    for chase_round in (1, 2):
        summary = workspace_snapshot.get(f"chase_round_{chase_round}")
        if isinstance(summary, dict):
            summaries.append({"round_number": chase_round, **summary})
    return summaries

def _store_action_output_artifacts(  # noqa: PLR0913
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    objective: str,
    seed_terms: list[str],
    workspace_snapshot: JSONObject,
    source_execution_summary: JSONObject,
    bootstrap_summary: JSONObject | None,
    brief_metadata: JSONObject,
) -> None:
    pubmed_results = workspace_snapshot.get("pubmed_results")
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "pubmed_results": json_array_or_empty(pubmed_results),
            "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_DRIVEN_TERMS_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "objective": objective,
            "seed_terms": list(seed_terms),
            "driven_terms": (
                json_array_or_empty(workspace_snapshot.get("driven_terms"))
            ),
            "driven_genes_from_pubmed": (
                json_array_or_empty(
                    workspace_snapshot.get("driven_genes_from_pubmed")
                )
            ),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
        media_type="application/json",
        content=source_execution_summary,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_BOOTSTRAP_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "bootstrap_run_id": workspace_snapshot.get("bootstrap_run_id"),
            "bootstrap_source_type": workspace_snapshot.get("bootstrap_source_type"),
            "summary": bootstrap_summary or {},
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "rounds": _collect_chase_round_summaries(
                workspace_snapshot=workspace_snapshot
            )
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_BRIEF_METADATA_ARTIFACT_KEY,
        media_type="application/json",
        content=brief_metadata,
    )
