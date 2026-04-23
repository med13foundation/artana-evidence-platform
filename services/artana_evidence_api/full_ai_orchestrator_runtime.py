"""Deterministic Phase 1 full AI orchestrator runtime.

This runtime owns the durable action registry, decision ledger, workspace
summary, and orchestrator result artifact while delegating the scientific
workflow itself to the existing research-init runtime.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_api.full_ai_orchestrator_common_support import (
    _chase_round_action_input_from_workspace,
    _chase_round_metadata_from_workspace,
    _chase_round_stop_reason,
    _guarded_structured_verification_payload,
    _normalized_source_key_list,
    _planner_mode_value,
    _source_decision_status,
    _workspace_list,
    _workspace_object,
    build_step_key,
    is_control_action,
    is_source_action,
    orchestrator_action_registry,
    require_action_enabled_for_sources,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorGuardedRolloutProfile,
    FullAIOrchestratorPlannerMode,
    FullAIOrchestratorRunResponse,
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
    ResearchOrchestratorDecision,
    ResearchOrchestratorGuardedDecisionProof,
)
from artana_evidence_api.full_ai_orchestrator_guarded_rollout import (
    _guarded_profile_allows,
    _guarded_profile_allows_chase,
    _guarded_rollout_policy_summary,
    resolve_guarded_rollout_profile,
)
from artana_evidence_api.full_ai_orchestrator_guarded_support import (
    _build_guarded_decision_proof,
    _decision_payload_from_recommendation,
    _guarded_action_allowed_by_profile,
    _guarded_action_with_policy,
    _guarded_decision_proof_summary,
    _guarded_execution_summary,
    _guarded_readiness_summary,
    _guarded_rejection_reason,
    _guarded_strategy_for_recommendation,
    _put_decision_history_artifact,
    _put_guarded_decision_proof_artifacts,
    _put_guarded_execution_artifact,
    _put_guarded_readiness_artifact,
    _put_shadow_planner_artifacts,
)
from artana_evidence_api.full_ai_orchestrator_response_support import (
    _build_brief_metadata,
    _build_decision_history,
    _build_source_execution_summary,
    _build_workspace_summary,
    _collect_chase_round_summaries,
    _sanitize_replayed_workspace_snapshot,
    _store_action_output_artifacts,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner import (
    ShadowPlannerRecommendationResult,
    build_shadow_planner_comparison,
    build_shadow_planner_workspace_summary,
    recommend_shadow_planner_action,
)
from artana_evidence_api.full_ai_orchestrator_shadow_support import (
    _accepted_guarded_chase_selection_action,
    _accepted_guarded_control_flow_action,
    _accepted_guarded_generate_brief_action,
    _accepted_guarded_structured_source_action,
    _build_initial_decision_history,
    _build_shadow_planner_summary,
    _checkpoint_phase_record_map,
    _checkpoint_target_decision,
    _shadow_planner_recommendation_payload,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.research_init_runtime import (
    ResearchInitExecutionResult,
    ResearchInitProgressObserver,
    ResearchInitPubMedReplayBundle,
    ResearchInitStructuredEnrichmentReplayBundle,
    deserialize_pubmed_replay_bundle,
    execute_research_init_run,
    serialize_pubmed_replay_bundle,
)
from artana_evidence_api.research_init_source_results import build_source_results
from artana_evidence_api.response_serialization import serialize_run_record
from artana_evidence_api.transparency import ensure_run_transparency_seed
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSourcePreferences,
)

from .run_registry import HarnessRunRecord

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


















_ACTION_SPEC_BY_TYPE = {spec.action_type: spec for spec in _ACTION_REGISTRY}
_STRUCTURED_ENRICHMENT_SOURCES = (
    "clinvar",
    "drugbank",
    "alphafold",
    "clinical_trials",
    "mgi",
    "zfin",
    "marrvel",
)
_SHADOW_PLANNER_CHECKPOINT_ORDER = (
    "before_first_action",
    "after_pubmed_discovery",
    "after_pubmed_ingest_extract",
    "after_driven_terms_ready",
    "after_bootstrap",
    "after_chase_round_1",
    "after_chase_round_2",
    "before_brief_generation",
    "before_terminal_stop",
)


@dataclass(frozen=True, slots=True)
class FullAIOrchestratorExecutionResult:
    """Terminal result for one deterministic full AI orchestrator run."""

    run: HarnessRunRecord
    planner_mode: FullAIOrchestratorPlannerMode
    guarded_rollout_profile: str | None
    guarded_rollout_profile_source: str | None
    research_init_result: ResearchInitExecutionResult
    action_history: tuple[ResearchOrchestratorDecision, ...]
    workspace_summary: JSONObject
    source_execution_summary: JSONObject
    bootstrap_summary: JSONObject | None
    brief_metadata: JSONObject
    shadow_planner: JSONObject | None
    guarded_execution: JSONObject | None
    guarded_decision_proofs: JSONObject | None
    errors: list[str]


























def _build_live_brief_metadata(*, workspace_snapshot: JSONObject) -> JSONObject:
    research_brief = workspace_snapshot.get("research_brief")
    if not isinstance(research_brief, dict):
        return {
            "result_key": "research_brief",
            "present": False,
            "markdown_length": 0,
            "section_count": 0,
            "llm_markdown_present": False,
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
        "llm_markdown_present": isinstance(markdown, str) and markdown.strip() != "",
    }


def _build_live_pubmed_summary(
    *, workspace_snapshot: JSONObject, status: str
) -> JSONObject:
    source_results = _workspace_object(workspace_snapshot, "source_results")
    pubmed_summary = (
        dict(source_results.get("pubmed", {}))
        if isinstance(source_results.get("pubmed"), dict)
        else {}
    )
    return {
        "status": status,
        "pubmed_results": _workspace_list(workspace_snapshot, "pubmed_results"),
        "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
        "pubmed_source_summary": pubmed_summary,
    }


def _build_live_driven_terms_artifact(
    *,
    objective: str,
    seed_terms: list[str],
    workspace_snapshot: JSONObject,
    status: str,
) -> JSONObject:
    return {
        "status": status,
        "objective": objective,
        "seed_terms": list(seed_terms),
        "driven_terms": _workspace_list(workspace_snapshot, "driven_terms"),
        "driven_genes_from_pubmed": _workspace_list(
            workspace_snapshot,
            "driven_genes_from_pubmed",
        ),
    }


def _build_live_source_execution_summary(
    *,
    selected_sources: ResearchSpaceSourcePreferences,
    workspace_snapshot: JSONObject,
    status: str,
) -> JSONObject:
    return {
        "status": status,
        "selected_sources": dict(selected_sources),
        "source_results": _workspace_object(workspace_snapshot, "source_results"),
        "documents_ingested": workspace_snapshot.get("documents_ingested", 0),
        "proposal_count": workspace_snapshot.get("proposal_count", 0),
    }


def _build_live_bootstrap_summary(
    *, workspace_snapshot: JSONObject, status: str
) -> JSONObject:
    return {
        "status": status,
        "bootstrap_run_id": workspace_snapshot.get("bootstrap_run_id"),
        "bootstrap_source_type": workspace_snapshot.get("bootstrap_source_type"),
        "summary": _workspace_object(workspace_snapshot, "bootstrap_summary"),
    }


def _build_live_chase_rounds_artifact(
    *,
    workspace_snapshot: JSONObject,
    status: str,
) -> JSONObject:
    return {
        "status": status,
        "rounds": _collect_chase_round_summaries(workspace_snapshot=workspace_snapshot),
    }




@dataclass(slots=True)
class _FullAIOrchestratorProgressObserver(ResearchInitProgressObserver):
    """Mirror research-init phase changes into orchestrator artifacts."""

    artifact_store: HarnessArtifactStore
    space_id: UUID
    run_id: str
    objective: str
    seed_terms: list[str]
    max_depth: int
    max_hypotheses: int
    sources: ResearchSpaceSourcePreferences
    planner_mode: FullAIOrchestratorPlannerMode
    action_registry: tuple[ResearchOrchestratorActionSpec, ...]
    decisions: list[ResearchOrchestratorDecision]
    initial_workspace_summary: JSONObject
    phase_records: dict[str, list[JSONObject]]
    shadow_timeline: list[JSONObject] = field(default_factory=list)
    guarded_execution_log: list[JSONObject] = field(default_factory=list)
    guarded_decision_proofs: list[ResearchOrchestratorGuardedDecisionProof] = field(
        default_factory=list,
    )
    emitted_shadow_checkpoints: set[str] = field(default_factory=set)
    guarded_rollout_profile: str = _GUARDED_PROFILE_SHADOW_ONLY
    guarded_rollout_profile_source: str = "resolved"
    guarded_chase_rollout_enabled: bool = False
    _shadow_planner_task: asyncio.Task[None] | None = None
    _progress_artifact_backoff_until: float | None = None
    _progress_decision_backoff_until: float | None = None

    @staticmethod
    def _backoff_active(resume_at: float | None) -> bool:
        return resume_at is not None and time.monotonic() < resume_at

    @staticmethod
    def _activate_backoff() -> float:
        return time.monotonic() + _PROGRESS_PERSISTENCE_BACKOFF_SECONDS

    def on_progress(
        self,
        *,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int,
        metadata: JSONObject,
        workspace_snapshot: JSONObject,
    ) -> None:
        del message, progress_percent, completed_steps
        if phase == "pubmed_discovery":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="running",
                metadata={"sources": metadata.get("sources", {})},
            )
            self._put_progress_artifact(
                artifact_key=_PUBMED_ARTIFACT_KEY,
                content=_build_live_pubmed_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "document_ingestion":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="completed",
                metadata={
                    "pubmed_source_summary": self._source_summary(
                        workspace_snapshot,
                        "pubmed",
                    ),
                },
            )
            self._update_decision(
                action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="running",
                metadata={"candidate_count": metadata.get("candidate_count", 0)},
            )
            self._put_progress_artifact(
                artifact_key=_PUBMED_ARTIFACT_KEY,
                content=_build_live_pubmed_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "structured_enrichment":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.DERIVE_DRIVEN_TERMS,
                round_number=0,
                status="completed",
                metadata={
                    "driven_terms": _workspace_list(workspace_snapshot, "driven_terms"),
                    "driven_genes_from_pubmed": _workspace_list(
                        workspace_snapshot,
                        "driven_genes_from_pubmed",
                    ),
                },
            )
            for source_key in _STRUCTURED_ENRICHMENT_SOURCES:
                if not self.sources.get(source_key, False):
                    continue
                self._update_decision(
                    action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                    round_number=0,
                    source_key=source_key,
                    status="running",
                    metadata={
                        "source_summary": self._source_summary(
                            workspace_snapshot, source_key
                        )
                    },
                )
            self._put_progress_artifact(
                artifact_key=_DRIVEN_TERMS_ARTIFACT_KEY,
                content=_build_live_driven_terms_artifact(
                    objective=self.objective,
                    seed_terms=self.seed_terms,
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
                content=_build_live_source_execution_summary(
                    selected_sources=self.sources,
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "document_extraction":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="running",
                metadata={
                    "documents_ingested": workspace_snapshot.get(
                        "documents_ingested", 0
                    ),
                    "selected_document_count": metadata.get(
                        "selected_document_count", 0
                    ),
                },
            )
            self._update_structured_source_decisions(
                workspace_snapshot=workspace_snapshot,
                pending_status="running",
            )
            self._put_progress_artifact(
                artifact_key=_PUBMED_ARTIFACT_KEY,
                content=_build_live_pubmed_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_DRIVEN_TERMS_ARTIFACT_KEY,
                content=_build_live_driven_terms_artifact(
                    objective=self.objective,
                    seed_terms=self.seed_terms,
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
                content=_build_live_source_execution_summary(
                    selected_sources=self.sources,
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "bootstrap":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="completed",
                metadata={
                    "documents_ingested": workspace_snapshot.get(
                        "documents_ingested", 0
                    ),
                    "proposal_count": workspace_snapshot.get("proposal_count", 0),
                },
            )
            self._update_structured_source_decisions(
                workspace_snapshot=workspace_snapshot,
                pending_status="running",
            )
            self._update_decision(
                action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                round_number=0,
                status="running",
                metadata={
                    "created_entity_count": metadata.get("created_entity_count", 0),
                    "bootstrap_source_type": workspace_snapshot.get(
                        "bootstrap_source_type"
                    ),
                },
            )
            self._put_progress_artifact(
                artifact_key=_PUBMED_ARTIFACT_KEY,
                content=_build_live_pubmed_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
                content=_build_live_source_execution_summary(
                    selected_sources=self.sources,
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
        elif phase.startswith("chase_round_"):
            round_number = int(phase.removeprefix("chase_round_"))
            self._update_decision(
                action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                round_number=0,
                status="completed",
                metadata={
                    "bootstrap_run_id": workspace_snapshot.get("bootstrap_run_id"),
                    "bootstrap_summary": _workspace_object(
                        workspace_snapshot,
                        "bootstrap_summary",
                    ),
                },
                stop_reason=(
                    None
                    if workspace_snapshot.get("bootstrap_run_id") is not None
                    else "bootstrap_not_triggered"
                ),
            )
            self._update_chase_round_decisions(
                workspace_snapshot=workspace_snapshot,
                active_round=round_number,
            )
            self._put_progress_artifact(
                artifact_key=_BOOTSTRAP_ARTIFACT_KEY,
                content=_build_live_bootstrap_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
                content=_build_live_chase_rounds_artifact(
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "deferred_mondo":
            self._update_chase_round_decisions(
                workspace_snapshot=workspace_snapshot,
                active_round=None,
            )
            self._put_progress_artifact(
                artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
                content=_build_live_chase_rounds_artifact(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
                content=_build_live_source_execution_summary(
                    selected_sources=self.sources,
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
        elif phase == "completed":
            self._update_chase_round_decisions(
                workspace_snapshot=workspace_snapshot,
                active_round=None,
            )
            self._update_decision(
                action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
                round_number=0,
                status=(
                    "completed"
                    if _build_live_brief_metadata(
                        workspace_snapshot=workspace_snapshot,
                    ).get("present")
                    else "skipped"
                ),
                metadata=_build_live_brief_metadata(
                    workspace_snapshot=workspace_snapshot
                ),
                stop_reason=(
                    None
                    if _build_live_brief_metadata(
                        workspace_snapshot=workspace_snapshot,
                    ).get("present")
                    else "brief_not_available"
                ),
            )
            self._put_progress_artifact(
                artifact_key=_BOOTSTRAP_ARTIFACT_KEY,
                content=_build_live_bootstrap_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
                content=_build_live_chase_rounds_artifact(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_BRIEF_METADATA_ARTIFACT_KEY,
                content=_build_live_brief_metadata(
                    workspace_snapshot=workspace_snapshot
                ),
            )
        self._record_phase(phase=phase, workspace_snapshot=workspace_snapshot)
        self._persist_progress()
        self._enqueue_shadow_checkpoint_updates(
            phase=phase,
            workspace_snapshot=workspace_snapshot,
        )

    def _source_summary(
        self,
        workspace_snapshot: JSONObject,
        source_key: str,
    ) -> JSONObject:
        source_results = _workspace_object(workspace_snapshot, "source_results")
        value = source_results.get(source_key)
        return dict(value) if isinstance(value, dict) else {}

    def _update_decision(
        self,
        *,
        action_type: ResearchOrchestratorActionType,
        round_number: int,
        status: str,
        source_key: str | None = None,
        metadata: JSONObject | None = None,
        stop_reason: str | None = None,
    ) -> None:
        for index, decision in enumerate(self.decisions):
            if (
                decision.action_type == action_type
                and decision.round_number == round_number
                and decision.source_key == source_key
            ):
                merged_metadata = dict(decision.metadata)
                if metadata is not None:
                    merged_metadata.update(metadata)
                updated_fields = {
                    "status": status,
                    "metadata": merged_metadata,
                }
                if stop_reason is not None or decision.stop_reason is not None:
                    updated_fields["stop_reason"] = stop_reason
                self.decisions[index] = decision.model_copy(update=updated_fields)
                return

    def _update_structured_source_decisions(
        self,
        *,
        workspace_snapshot: JSONObject,
        pending_status: str,
    ) -> None:
        for source_key in _STRUCTURED_ENRICHMENT_SOURCES:
            if not self.sources.get(source_key, False):
                continue
            source_summary = self._source_summary(workspace_snapshot, source_key)
            decision_status, stop_reason = _source_decision_status(
                source_summary=source_summary,
                pending_status=pending_status,
            )
            self._update_decision(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                round_number=0,
                source_key=source_key,
                status=decision_status,
                metadata={"source_summary": source_summary},
                stop_reason=stop_reason,
            )

    def _update_chase_round_decisions(
        self,
        *,
        workspace_snapshot: JSONObject,
        active_round: int | None,
    ) -> None:
        for chase_round in range(1, min(self.max_depth, 2) + 1):
            chase_summary = workspace_snapshot.get(f"chase_round_{chase_round}")
            if isinstance(chase_summary, dict):
                self._update_decision(
                    action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                    round_number=chase_round,
                    status="completed",
                    metadata=_chase_round_metadata_from_workspace(
                        workspace_snapshot=workspace_snapshot,
                        round_number=chase_round,
                    ),
                )
                for index, decision in enumerate(self.decisions):
                    if (
                        decision.action_type
                        == ResearchOrchestratorActionType.RUN_CHASE_ROUND
                        and decision.round_number == chase_round
                    ):
                        self.decisions[index] = decision.model_copy(
                            update={
                                "action_input": _chase_round_action_input_from_workspace(
                                    workspace_snapshot=workspace_snapshot,
                                    round_number=chase_round,
                                )
                            }
                        )
                        break
                continue
            chase_action_input = _chase_round_action_input_from_workspace(
                workspace_snapshot=workspace_snapshot,
                round_number=chase_round,
            )
            chase_metadata = _chase_round_metadata_from_workspace(
                workspace_snapshot=workspace_snapshot,
                round_number=chase_round,
            )
            if active_round == chase_round:
                self._update_decision(
                    action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                    round_number=chase_round,
                    status="running",
                    metadata=(
                        chase_metadata
                        if chase_metadata
                        else {"round_number": chase_round}
                    ),
                )
            else:
                self._update_decision(
                    action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                    round_number=chase_round,
                    status="skipped",
                    metadata=chase_metadata,
                    stop_reason=_chase_round_stop_reason(chase_metadata),
                )
            for index, decision in enumerate(self.decisions):
                if (
                    decision.action_type
                    == ResearchOrchestratorActionType.RUN_CHASE_ROUND
                    and decision.round_number == chase_round
                ):
                    self.decisions[index] = decision.model_copy(
                        update={"action_input": chase_action_input}
                    )
                    break

    def _put_artifact(self, *, artifact_key: str, content: JSONObject) -> None:
        self.artifact_store.put_artifact(
            space_id=self.space_id,
            run_id=self.run_id,
            artifact_key=artifact_key,
            media_type="application/json",
            content=content,
        )

    def _put_progress_artifact(self, *, artifact_key: str, content: JSONObject) -> None:
        if self._backoff_active(self._progress_artifact_backoff_until):
            return
        try:
            self._put_artifact(artifact_key=artifact_key, content=content)
            self._progress_artifact_backoff_until = None
        except TimeoutError:
            self._progress_artifact_backoff_until = self._activate_backoff()
            _LOGGER.info(
                "Entering full AI orchestrator progress artifact backoff after timeout",
                extra={
                    "run_id": self.run_id,
                    "artifact_key": artifact_key,
                },
            )

    def _record_guarded_decision_proof(
        self,
        *,
        checkpoint_key: str,
        guarded_strategy: str,
        decision_outcome: Literal["allowed", "blocked", "ignored"],
        outcome_reason: str,
        recommendation_payload: JSONObject,
        comparison: JSONObject,
        guarded_action: JSONObject | None = None,
        policy_allowed: bool = False,
        disabled_source_violation: bool = False,
    ) -> ResearchOrchestratorGuardedDecisionProof:
        proof = _build_guarded_decision_proof(
            proof_id=(
                f"guarded-proof-{len(self.guarded_decision_proofs) + 1:03d}-"
                f"{checkpoint_key}"
            ),
            checkpoint_key=checkpoint_key,
            guarded_strategy=guarded_strategy,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            decision_outcome=decision_outcome,
            outcome_reason=outcome_reason,
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            guarded_action=guarded_action,
            policy_allowed=policy_allowed,
            disabled_source_violation=disabled_source_violation,
        )
        self.guarded_decision_proofs.append(proof)
        self._persist_guarded_decision_proof_state()
        return proof

    def _persist_guarded_decision_proof_state(self) -> None:
        if self.planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
            return
        guarded_readiness = _guarded_readiness_summary(
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        _put_guarded_readiness_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        _put_guarded_decision_proof_artifacts(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            proofs=self.guarded_decision_proofs,
        )
        self.artifact_store.patch_workspace(
            space_id=self.space_id,
            run_id=self.run_id,
            patch={
                "guarded_decision_proofs_key": (
                    _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
                ),
                "guarded_decision_proofs": _guarded_decision_proof_summary(
                    planner_mode=self.planner_mode,
                    guarded_rollout_profile=self.guarded_rollout_profile,
                    guarded_rollout_profile_source=self.guarded_rollout_profile_source,
                    proofs=self.guarded_decision_proofs,
                ),
                "guarded_readiness": guarded_readiness,
            },
        )

    def _persist_guarded_execution_state(
        self,
        *,
        extra_patch: JSONObject | None = None,
    ) -> None:
        _put_guarded_execution_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            actions=self.guarded_execution_log,
        )
        _put_guarded_readiness_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        guarded_readiness = _guarded_readiness_summary(
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        workspace_patch: JSONObject = {
            "shadow_planner_mode": _planner_mode_value(self.planner_mode),
            "planner_execution_mode": _planner_mode_value(self.planner_mode),
            "guarded_rollout_profile": self.guarded_rollout_profile,
            "guarded_rollout_profile_source": self.guarded_rollout_profile_source,
            "guarded_rollout_policy": _guarded_rollout_policy_summary(
                planner_mode=self.planner_mode,
                guarded_rollout_profile=self.guarded_rollout_profile,
                guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            ),
            "guarded_chase_rollout_enabled": self.guarded_chase_rollout_enabled,
            "guarded_execution_log_key": _GUARDED_EXECUTION_ARTIFACT_KEY,
            "guarded_readiness_key": _GUARDED_READINESS_ARTIFACT_KEY,
            "guarded_execution": _guarded_execution_summary(
                planner_mode=self.planner_mode,
                actions=self.guarded_execution_log,
            ),
            "guarded_readiness": guarded_readiness,
        }
        if self.planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
            workspace_patch["guarded_decision_proofs_key"] = (
                _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
            )
            workspace_patch["guarded_decision_proofs"] = (
                _guarded_decision_proof_summary(
                    planner_mode=self.planner_mode,
                    guarded_rollout_profile=self.guarded_rollout_profile,
                    guarded_rollout_profile_source=self.guarded_rollout_profile_source,
                    proofs=self.guarded_decision_proofs,
                )
            )
        if extra_patch is not None:
            workspace_patch.update(extra_patch)
        self.artifact_store.patch_workspace(
            space_id=self.space_id,
            run_id=self.run_id,
            patch=workspace_patch,
        )
        self._persist_guarded_decision_proof_state()

    def _update_guarded_action_verification(
        self,
        *,
        action_type: ResearchOrchestratorActionType,
        verification_status: str,
        verification_reason: str,
        verification_summary: JSONObject,
        verified_at_phase: str,
        guarded_strategy: str | None = None,
        stop_reason: str | None = None,
    ) -> bool:
        for index in range(len(self.guarded_execution_log) - 1, -1, -1):
            action = self.guarded_execution_log[index]
            if action.get("applied_action_type") != action_type.value:
                continue
            if action.get("verification_status") != "pending":
                continue
            if (
                guarded_strategy is not None
                and action.get("guarded_strategy") != guarded_strategy
            ):
                continue
            if stop_reason is not None and action.get("stop_reason") != stop_reason:
                continue
            updated_action = dict(action)
            updated_action["verification_status"] = verification_status
            updated_action["verification_reason"] = verification_reason
            updated_action["verification_summary"] = verification_summary
            updated_action["verified_at_phase"] = verified_at_phase
            self.guarded_execution_log[index] = updated_action
            self._update_guarded_decision_proof_verification(
                updated_action=updated_action,
                verification_status=verification_status,
                verification_reason=verification_reason,
            )
            self._persist_guarded_execution_state()
            return True
        return False

    def _update_guarded_decision_proof_verification(
        self,
        *,
        updated_action: JSONObject,
        verification_status: str,
        verification_reason: str,
    ) -> None:
        action_decision_id = updated_action.get("decision_id")
        action_checkpoint_key = updated_action.get("checkpoint_key")
        action_type = updated_action.get("applied_action_type")
        for index, proof in enumerate(self.guarded_decision_proofs):
            if proof.decision_outcome != "allowed":
                continue
            if (
                proof.decision_id == action_decision_id
                and proof.checkpoint_key == action_checkpoint_key
                and proof.applied_action_type == action_type
            ):
                self.guarded_decision_proofs[index] = proof.model_copy(
                    update={
                        "verification_status": verification_status,
                        "verification_reason": verification_reason,
                        "guarded_action": dict(updated_action),
                    },
                )
                return

    def _persist(self) -> None:
        _put_decision_history_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            decisions=self.decisions,
        )
        self.artifact_store.patch_workspace(
            space_id=self.space_id,
            run_id=self.run_id,
            patch={
                "decision_count": len(self.decisions),
                "last_decision_id": self.decisions[-1].decision_id,
            },
        )

    def _persist_progress(self) -> None:
        if self._backoff_active(self._progress_decision_backoff_until):
            return
        try:
            self._persist()
            self._progress_decision_backoff_until = None
        except TimeoutError:
            self._progress_decision_backoff_until = self._activate_backoff()
            _LOGGER.info(
                "Entering full AI orchestrator progress decision backoff after timeout",
                extra={"run_id": self.run_id},
            )

    def _record_phase(self, *, phase: str, workspace_snapshot: JSONObject) -> None:
        self.phase_records.setdefault(phase, []).append(
            {
                "phase": phase,
                "workspace_snapshot": deepcopy(workspace_snapshot),
                "decisions": [
                    decision.model_dump(mode="json") for decision in self.decisions
                ],
            }
        )

    def enqueue_initial_shadow_checkpoint(self) -> None:
        self._enqueue_shadow_checkpoint(
            checkpoint_key="before_first_action",
            workspace_summary=self.initial_workspace_summary,
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in self.decisions
            ],
        )

    async def finalize_shadow_planner(
        self,
        *,
        final_workspace_snapshot: JSONObject,
        final_decisions: list[ResearchOrchestratorDecision],
    ) -> list[JSONObject]:
        await self.wait_for_shadow_planner_updates()
        checkpoint_records = _checkpoint_phase_record_map(
            initial_workspace_summary=self.initial_workspace_summary,
            initial_decisions=self.decisions,
            phase_records=self.phase_records,
            final_workspace_snapshot=final_workspace_snapshot,
            final_decisions=final_decisions,
        )
        for checkpoint_key in _SHADOW_PLANNER_CHECKPOINT_ORDER:
            if checkpoint_key in self.emitted_shadow_checkpoints:
                continue
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
                    mode=_planner_mode_value(self.planner_mode),
                    objective=self.objective,
                    seed_terms=self.seed_terms,
                    sources=self.sources,
                    max_depth=self.max_depth,
                    max_hypotheses=self.max_hypotheses,
                    workspace_snapshot=(
                        workspace_snapshot
                        if isinstance(workspace_snapshot, dict)
                        else {}
                    ),
                    prior_decisions=(
                        list(record.get("decisions", []))
                        if isinstance(record.get("decisions"), list)
                        else []
                    ),
                    action_registry=self.action_registry,
                )
            await self._emit_shadow_checkpoint(
                checkpoint_key=checkpoint_key,
                workspace_summary=workspace_summary,
                deterministic_decisions=final_decisions,
            )
        return list(self.shadow_timeline)

    async def wait_for_shadow_planner_updates(self) -> None:
        if self._shadow_planner_task is None:
            return
        await self._shadow_planner_task

    async def maybe_skip_chase_round(  # noqa: PLR0911
        self,
        *,
        next_round_number: int,
        workspace_snapshot: JSONObject,
    ) -> bool:
        if self.planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
            return False
        if not self.guarded_chase_rollout_enabled:
            return False
        if next_round_number != _GUARDED_SKIP_CHASE_ROUND_NUMBER:
            return False
        if not isinstance(workspace_snapshot.get("chase_round_1"), dict):
            return False

        checkpoint_key = "after_chase_round_1"
        workspace_summary = build_shadow_planner_workspace_summary(
            checkpoint_key=checkpoint_key,
            mode=_planner_mode_value(self.planner_mode),
            objective=self.objective,
            seed_terms=self.seed_terms,
            sources=self.sources,
            max_depth=self.max_depth,
            max_hypotheses=self.max_hypotheses,
            workspace_snapshot=workspace_snapshot,
            prior_decisions=[
                decision.model_dump(mode="json") for decision in self.decisions
            ],
            action_registry=self.action_registry,
        )
        recommendation_payload, comparison = await self._get_or_emit_shadow_checkpoint(
            checkpoint_key=checkpoint_key,
            workspace_summary=workspace_summary,
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in self.decisions
            ],
        )
        guarded_action = _accepted_guarded_generate_brief_action(
            recommendation_payload=recommendation_payload,
            comparison=comparison,
        )
        if guarded_action is None:
            guarded_action = _accepted_guarded_control_flow_action(
                recommendation_payload=recommendation_payload,
                comparison=comparison,
            )
        if guarded_action is None:
            decision_payload = _decision_payload_from_recommendation(
                recommendation_payload,
            )
            if (
                decision_payload.get("action_type")
                == ResearchOrchestratorActionType.RUN_CHASE_ROUND.value
            ):
                return False
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_guarded_strategy_for_recommendation(
                    recommendation_payload=recommendation_payload,
                    default_strategy=_GUARDED_STRATEGY_BRIEF_GENERATION,
                ),
                decision_outcome="blocked",
                outcome_reason=_guarded_rejection_reason(
                    recommendation_payload=recommendation_payload,
                    comparison=comparison,
                    default_reason="not_an_eligible_guarded_terminal_action",
                ),
                recommendation_payload=recommendation_payload,
                comparison=comparison,
            )
            return False
        if not _guarded_action_allowed_by_profile(
            action=guarded_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
        ):
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=str(guarded_action["guarded_strategy"]),
                decision_outcome="blocked",
                outcome_reason="guarded_rollout_profile_disallows_strategy",
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                guarded_action=guarded_action,
                policy_allowed=False,
            )
            return False
        guarded_action = _guarded_action_with_policy(
            action=guarded_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
        )
        self._record_guarded_decision_proof(
            checkpoint_key=checkpoint_key,
            guarded_strategy=str(guarded_action["guarded_strategy"]),
            decision_outcome="allowed",
            outcome_reason="guarded_policy_allowed",
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            guarded_action=guarded_action,
            policy_allowed=True,
        )

        self.guarded_execution_log.append(guarded_action)
        guarded_action_type = guarded_action.get("applied_action_type")
        guarded_stop_reason = guarded_action.get("stop_reason")
        self._update_decision(
            action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
            round_number=next_round_number,
            status="skipped",
            metadata={"guarded_execution": guarded_action},
            stop_reason=(
                guarded_stop_reason
                if isinstance(guarded_stop_reason, str)
                else "guarded_generate_brief"
            ),
        )
        self._persist()
        if guarded_action_type == ResearchOrchestratorActionType.GENERATE_BRIEF.value:
            self._persist_guarded_execution_state(
                extra_patch={
                    "guarded_stop_after_chase_round": next_round_number - 1,
                },
            )
        else:
            self._persist_guarded_execution_state(
                extra_patch={
                    "guarded_terminal_control_after_chase_round": (
                        next_round_number - 1
                    ),
                    "guarded_terminal_control_action": {
                        "action_type": guarded_action_type,
                        "stop_reason": guarded_stop_reason,
                        "checkpoint_key": guarded_action.get("checkpoint_key"),
                        "human_review_required": (
                            guarded_action_type
                            == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                        ),
                    },
                    "guarded_human_review_required": (
                        guarded_action_type
                        == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                    ),
                },
            )
        return True

    async def maybe_select_structured_enrichment_sources(  # noqa: PLR0911
        self,
        *,
        available_source_keys: tuple[str, ...],
        workspace_snapshot: JSONObject,
    ) -> tuple[str, ...] | None:
        if self.planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
            return None
        if not _guarded_profile_allows(
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_strategy=_GUARDED_STRATEGY_STRUCTURED_SOURCE,
        ):
            return None
        if len(available_source_keys) <= 1:
            return None

        checkpoint_key = "after_driven_terms_ready"
        workspace_summary = build_shadow_planner_workspace_summary(
            checkpoint_key=checkpoint_key,
            mode=_planner_mode_value(self.planner_mode),
            objective=self.objective,
            seed_terms=self.seed_terms,
            sources=self.sources,
            max_depth=self.max_depth,
            max_hypotheses=self.max_hypotheses,
            workspace_snapshot=workspace_snapshot,
            prior_decisions=[
                decision.model_dump(mode="json") for decision in self.decisions
            ],
            action_registry=self.action_registry,
        )
        recommendation_payload, comparison = await self._get_or_emit_shadow_checkpoint(
            checkpoint_key=checkpoint_key,
            workspace_summary=workspace_summary,
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in self.decisions
            ],
        )
        guarded_action = _accepted_guarded_structured_source_action(
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            available_source_keys=available_source_keys,
        )
        if guarded_action is None:
            decision = _decision_payload_from_recommendation(recommendation_payload)
            recommended_source_key = decision.get("source_key")
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_GUARDED_STRATEGY_STRUCTURED_SOURCE,
                decision_outcome="blocked",
                outcome_reason=_guarded_rejection_reason(
                    recommendation_payload=recommendation_payload,
                    comparison=comparison,
                    default_reason="not_an_eligible_guarded_structured_source_action",
                ),
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                disabled_source_violation=(
                    isinstance(recommended_source_key, str)
                    and recommended_source_key not in set(available_source_keys)
                ),
            )
            return None
        if not _guarded_action_allowed_by_profile(
            action=guarded_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
        ):
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_GUARDED_STRATEGY_STRUCTURED_SOURCE,
                decision_outcome="blocked",
                outcome_reason="guarded_rollout_profile_disallows_strategy",
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                guarded_action=guarded_action,
                policy_allowed=False,
            )
            return None
        guarded_action = _guarded_action_with_policy(
            action=guarded_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
        )
        self._record_guarded_decision_proof(
            checkpoint_key=checkpoint_key,
            guarded_strategy=_GUARDED_STRATEGY_STRUCTURED_SOURCE,
            decision_outcome="allowed",
            outcome_reason="guarded_policy_allowed",
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            guarded_action=guarded_action,
            policy_allowed=True,
        )

        selected_source_key = guarded_action.get("applied_source_key")
        if not isinstance(selected_source_key, str):
            return None
        ordered_source_keys = [selected_source_key]
        ordered_source_keys.extend(
            source_key
            for source_key in available_source_keys
            if source_key != selected_source_key
        )
        guarded_action["ordered_source_keys"] = ordered_source_keys
        guarded_action["deferred_source_keys"] = []
        self.guarded_execution_log.append(guarded_action)
        _put_guarded_execution_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            actions=self.guarded_execution_log,
        )
        _put_guarded_readiness_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        for source_index, source_key in enumerate(ordered_source_keys):
            self._update_decision(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                round_number=0,
                source_key=source_key,
                status="running" if source_index == 0 else "pending",
                metadata={
                    "guarded_execution": guarded_action,
                    "guarded_priority": source_index,
                },
            )
        self._persist()
        self._persist_guarded_execution_state(
            extra_patch={
                "guarded_structured_enrichment_selection": {
                    "selected_source_key": selected_source_key,
                    "ordered_source_keys": ordered_source_keys,
                    "deferred_source_keys": [],
                },
            },
        )
        return tuple(ordered_source_keys)

    async def maybe_select_chase_round_selection(  # noqa: PLR0911
        self,
        *,
        round_number: int,
        chase_candidates: tuple[ResearchOrchestratorChaseCandidate, ...],
        deterministic_selection: ResearchOrchestratorChaseSelection,
        workspace_snapshot: JSONObject,
    ) -> ResearchOrchestratorChaseSelection | None:
        if self.planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
            return None
        if not self.guarded_chase_rollout_enabled:
            return None
        checkpoint_key_by_round = {
            1: "after_bootstrap",
            2: "after_chase_round_1",
        }
        checkpoint_key = checkpoint_key_by_round.get(round_number)
        if checkpoint_key is None:
            return None

        workspace_summary = build_shadow_planner_workspace_summary(
            checkpoint_key=checkpoint_key,
            mode=_planner_mode_value(self.planner_mode),
            objective=self.objective,
            seed_terms=self.seed_terms,
            sources=self.sources,
            max_depth=self.max_depth,
            max_hypotheses=self.max_hypotheses,
            workspace_snapshot=workspace_snapshot,
            prior_decisions=[
                decision.model_dump(mode="json") for decision in self.decisions
            ],
            action_registry=self.action_registry,
        )
        recommendation_payload, comparison = await self._get_or_emit_shadow_checkpoint(
            checkpoint_key=checkpoint_key,
            workspace_summary=workspace_summary,
            deterministic_decisions=[
                decision.model_copy(deep=True) for decision in self.decisions
            ],
        )

        guarded_action = _accepted_guarded_chase_selection_action(
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            round_number=round_number,
            chase_candidates=chase_candidates,
            deterministic_selection=deterministic_selection,
        )
        if guarded_action is not None:
            if not _guarded_action_allowed_by_profile(
                action=guarded_action,
                guarded_rollout_profile=self.guarded_rollout_profile,
            ):
                self._record_guarded_decision_proof(
                    checkpoint_key=checkpoint_key,
                    guarded_strategy=_GUARDED_STRATEGY_CHASE_SELECTION,
                    decision_outcome="blocked",
                    outcome_reason="guarded_rollout_profile_disallows_strategy",
                    recommendation_payload=recommendation_payload,
                    comparison=comparison,
                    guarded_action=guarded_action,
                    policy_allowed=False,
                )
                return None
            guarded_action = _guarded_action_with_policy(
                action=guarded_action,
                guarded_rollout_profile=self.guarded_rollout_profile,
                guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            )
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_GUARDED_STRATEGY_CHASE_SELECTION,
                decision_outcome="allowed",
                outcome_reason="guarded_policy_allowed",
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                guarded_action=guarded_action,
                policy_allowed=True,
            )
            self.guarded_execution_log.append(guarded_action)
            self._persist_guarded_execution_state(
                extra_patch={
                    f"guarded_chase_round_{round_number}": {
                        "selected_entity_ids": guarded_action["selected_entity_ids"],
                        "selected_labels": guarded_action["selected_labels"],
                        "selection_basis": guarded_action["selection_basis"],
                    },
                },
            )
            return ResearchOrchestratorChaseSelection(
                selected_entity_ids=list(guarded_action["selected_entity_ids"]),
                selected_labels=list(guarded_action["selected_labels"]),
                stop_instead=False,
                stop_reason=None,
                selection_basis=str(guarded_action["selection_basis"]),
            )

        control_flow_action = _accepted_guarded_control_flow_action(
            recommendation_payload=recommendation_payload,
            comparison=comparison,
        )
        if control_flow_action is None:
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_guarded_strategy_for_recommendation(
                    recommendation_payload=recommendation_payload,
                    default_strategy=_GUARDED_STRATEGY_CHASE_SELECTION,
                ),
                decision_outcome="blocked",
                outcome_reason=_guarded_rejection_reason(
                    recommendation_payload=recommendation_payload,
                    comparison=comparison,
                    default_reason="not_an_eligible_guarded_chase_action",
                ),
                recommendation_payload=recommendation_payload,
                comparison=comparison,
            )
            return None
        if not _guarded_action_allowed_by_profile(
            action=control_flow_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
        ):
            self._record_guarded_decision_proof(
                checkpoint_key=checkpoint_key,
                guarded_strategy=_GUARDED_STRATEGY_TERMINAL_CONTROL,
                decision_outcome="blocked",
                outcome_reason="guarded_rollout_profile_disallows_strategy",
                recommendation_payload=recommendation_payload,
                comparison=comparison,
                guarded_action=control_flow_action,
                policy_allowed=False,
            )
            return None
        control_flow_action = _guarded_action_with_policy(
            action=control_flow_action,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
        )
        self._record_guarded_decision_proof(
            checkpoint_key=checkpoint_key,
            guarded_strategy=_GUARDED_STRATEGY_TERMINAL_CONTROL,
            decision_outcome="allowed",
            outcome_reason="guarded_policy_allowed",
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            guarded_action=control_flow_action,
            policy_allowed=True,
        )
        self.guarded_execution_log.append(control_flow_action)
        self._persist_guarded_execution_state(
            extra_patch={
                "guarded_terminal_control_after_chase_round": round_number - 1,
                "guarded_terminal_control_action": {
                    "action_type": control_flow_action.get("applied_action_type"),
                    "stop_reason": control_flow_action.get("stop_reason"),
                    "checkpoint_key": control_flow_action.get("checkpoint_key"),
                    "human_review_required": (
                        control_flow_action.get("applied_action_type")
                        == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                    ),
                },
                "guarded_human_review_required": (
                    control_flow_action.get("applied_action_type")
                    == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                ),
            },
        )
        stop_reason = control_flow_action.get("stop_reason")
        return ResearchOrchestratorChaseSelection(
            selected_entity_ids=[],
            selected_labels=[],
            stop_instead=True,
            stop_reason=(
                stop_reason
                if isinstance(stop_reason, str) and stop_reason
                else "guarded_stop_requested"
            ),
            selection_basis=str(control_flow_action["qualitative_rationale"]),
        )

    def verify_guarded_structured_enrichment(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        source_results = _workspace_object(workspace_snapshot, "source_results")
        for action in reversed(self.guarded_execution_log):
            if (
                action.get("applied_action_type")
                != ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT.value
            ):
                continue
            guarded_strategy = action.get("guarded_strategy")
            if guarded_strategy not in {
                "single_structured_source",
                _GUARDED_STRATEGY_STRUCTURED_SOURCE,
            }:
                continue
            if action.get("verification_status") != "pending":
                continue
            (
                verification_status,
                verification_reason,
                verification_summary,
            ) = _guarded_structured_verification_payload(
                source_results=source_results,
                action=action,
            )
            return self._update_guarded_action_verification(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                guarded_strategy=guarded_strategy,
                verification_status=verification_status,
                verification_reason=verification_reason,
                verification_summary=verification_summary,
                verified_at_phase="structured_enrichment",
            )
        return False

    def verify_guarded_chase_selection(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        for action in reversed(self.guarded_execution_log):
            if action.get("guarded_strategy") != _GUARDED_STRATEGY_CHASE_SELECTION:
                continue
            if action.get("verification_status") != "pending":
                continue
            round_number = action.get("round_number")
            if not isinstance(round_number, int):
                return False
            chase_summary = workspace_snapshot.get(f"chase_round_{round_number}")
            if not isinstance(chase_summary, dict):
                return False
            selected_entity_ids = _normalized_source_key_list(
                chase_summary.get("selected_entity_ids"),
            )
            selected_labels = _normalized_source_key_list(
                chase_summary.get("selected_labels"),
            )
            verification_status = "verified"
            verification_reason = "guarded_chase_selection_applied"
            if chase_summary.get("selection_mode") != "guarded":
                verification_status = "verification_failed"
                verification_reason = "guarded_chase_selection_marker_missing"
            elif selected_entity_ids != action.get(
                "selected_entity_ids"
            ) or selected_labels != action.get("selected_labels"):
                verification_status = "verification_failed"
                verification_reason = "guarded_chase_selection_mismatch"
            return self._update_guarded_action_verification(
                action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                guarded_strategy=_GUARDED_STRATEGY_CHASE_SELECTION,
                verification_status=verification_status,
                verification_reason=verification_reason,
                verification_summary={
                    "chase_round": round_number,
                    "selected_entity_ids": selected_entity_ids,
                    "selected_labels": selected_labels,
                    "selection_mode": chase_summary.get("selection_mode"),
                },
                verified_at_phase="chase_round",
            )
        return False

    def verify_guarded_brief_generation(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        research_brief = workspace_snapshot.get("research_brief")
        chase_round_2 = workspace_snapshot.get("chase_round_2")
        guarded_stop_after_chase_round = workspace_snapshot.get(
            "guarded_stop_after_chase_round",
        )
        brief_present = isinstance(research_brief, dict)
        chase_round_2_present = isinstance(chase_round_2, dict)
        verification_status = "verified"
        verification_reason = "brief_generated_without_second_chase_round"
        if not brief_present:
            verification_status = "verification_failed"
            verification_reason = "brief_missing"
        elif chase_round_2_present:
            verification_status = "verification_failed"
            verification_reason = "unexpected_second_chase_round"
        elif guarded_stop_after_chase_round != 1:
            verification_status = "verification_failed"
            verification_reason = "guarded_stop_marker_missing"
        return self._update_guarded_action_verification(
            action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
            stop_reason="guarded_generate_brief",
            verification_status=verification_status,
            verification_reason=verification_reason,
            verification_summary={
                "brief_present": brief_present,
                "guarded_stop_after_chase_round": guarded_stop_after_chase_round,
                "chase_round_2_present": chase_round_2_present,
            },
            verified_at_phase="brief_generation",
        )

    def verify_guarded_terminal_control_flow(
        self,
        *,
        workspace_snapshot: JSONObject,
    ) -> bool:
        terminal_control_action = workspace_snapshot.get(
            "guarded_terminal_control_action",
        )
        terminal_control_after_round = workspace_snapshot.get(
            "guarded_terminal_control_after_chase_round",
        )
        human_review_required = workspace_snapshot.get(
            "guarded_human_review_required",
        )
        if not isinstance(terminal_control_action, dict):
            return False
        action_type = terminal_control_action.get("action_type")
        stop_reason = terminal_control_action.get("stop_reason")
        if action_type not in {
            ResearchOrchestratorActionType.STOP.value,
            ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value,
        }:
            return False
        if not isinstance(stop_reason, str) or stop_reason == "":
            return False

        checkpoint_key = terminal_control_action.get("checkpoint_key")
        expected_after_round_by_checkpoint = {
            "after_bootstrap": 0,
            "after_chase_round_1": 1,
        }
        expected_after_round = expected_after_round_by_checkpoint.get(checkpoint_key)

        verification_status = "verified"
        verification_reason = "terminal_control_action_verified"
        if expected_after_round is None:
            verification_status = "verification_failed"
            verification_reason = "terminal_control_checkpoint_invalid"
        elif terminal_control_after_round != expected_after_round:
            verification_status = "verification_failed"
            verification_reason = "terminal_control_round_marker_mismatch"

        if (
            verification_status == "verified"
            and action_type == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
        ):
            verification_reason = "human_review_requested"
            if human_review_required is not True:
                verification_status = "verification_failed"
                verification_reason = "human_review_marker_missing"
        elif verification_status == "verified" and human_review_required is True:
            verification_status = "verification_failed"
            verification_reason = "unexpected_human_review_marker"

        return self._update_guarded_action_verification(
            action_type=(
                ResearchOrchestratorActionType.ESCALATE_TO_HUMAN
                if action_type == ResearchOrchestratorActionType.ESCALATE_TO_HUMAN.value
                else ResearchOrchestratorActionType.STOP
            ),
            stop_reason=stop_reason,
            verification_status=verification_status,
            verification_reason=verification_reason,
            verification_summary={
                "guarded_terminal_control_action": terminal_control_action,
                "guarded_terminal_control_after_chase_round": terminal_control_after_round,
                "expected_after_chase_round": expected_after_round,
                "guarded_human_review_required": human_review_required,
            },
            verified_at_phase="control_flow",
            guarded_strategy=_GUARDED_STRATEGY_TERMINAL_CONTROL,
        )

    def _enqueue_shadow_checkpoint_updates(
        self,
        *,
        phase: str,
        workspace_snapshot: JSONObject,
    ) -> None:
        for checkpoint_key in self._checkpoint_keys_for_phase(
            phase=phase,
            workspace_snapshot=workspace_snapshot,
        ):
            workspace_summary = build_shadow_planner_workspace_summary(
                checkpoint_key=checkpoint_key,
                mode=_planner_mode_value(self.planner_mode),
                objective=self.objective,
                seed_terms=self.seed_terms,
                sources=self.sources,
                max_depth=self.max_depth,
                max_hypotheses=self.max_hypotheses,
                workspace_snapshot=workspace_snapshot,
                prior_decisions=[
                    decision.model_dump(mode="json") for decision in self.decisions
                ],
                action_registry=self.action_registry,
            )
            self._enqueue_shadow_checkpoint(
                checkpoint_key=checkpoint_key,
                workspace_summary=workspace_summary,
                deterministic_decisions=[
                    decision.model_copy(deep=True) for decision in self.decisions
                ],
            )

    def _enqueue_shadow_checkpoint(
        self,
        *,
        checkpoint_key: str,
        workspace_summary: JSONObject,
        deterministic_decisions: list[ResearchOrchestratorDecision],
    ) -> None:
        if checkpoint_key in self.emitted_shadow_checkpoints:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        previous_task = self._shadow_planner_task
        workspace_summary_copy = deepcopy(workspace_summary)
        decisions_copy = [
            decision.model_copy(deep=True) for decision in deterministic_decisions
        ]

        async def _run_after_previous() -> None:
            if previous_task is not None:
                await previous_task
            if checkpoint_key in self.emitted_shadow_checkpoints:
                return
            await self._emit_shadow_checkpoint(
                checkpoint_key=checkpoint_key,
                workspace_summary=workspace_summary_copy,
                deterministic_decisions=decisions_copy,
            )

        self._shadow_planner_task = loop.create_task(_run_after_previous())

    async def _emit_shadow_checkpoint(
        self,
        *,
        checkpoint_key: str,
        workspace_summary: JSONObject,
        deterministic_decisions: list[ResearchOrchestratorDecision],
    ) -> tuple[ShadowPlannerRecommendationResult, JSONObject]:
        if checkpoint_key in self.emitted_shadow_checkpoints:
            raise RuntimeError(
                f"Checkpoint '{checkpoint_key}' was already emitted and cannot be replayed synchronously.",
            )
        planner_result = await recommend_shadow_planner_action(
            checkpoint_key=checkpoint_key,
            objective=self.objective,
            workspace_summary=workspace_summary,
            sources=self.sources,
            action_registry=self.action_registry,
            harness_id=_HARNESS_ID,
            step_key_version=_STEP_KEY_VERSION,
        )
        comparison = build_shadow_planner_comparison(
            checkpoint_key=checkpoint_key,
            planner_result=planner_result,
            deterministic_target=_checkpoint_target_decision(
                checkpoint_key=checkpoint_key,
                decisions=deterministic_decisions,
                workspace_summary=workspace_summary,
            ),
            workspace_summary=workspace_summary,
            mode=_planner_mode_value(self.planner_mode),
        )
        self.shadow_timeline.append(
            {
                "checkpoint_key": checkpoint_key,
                "workspace_summary": workspace_summary,
                "recommendation": _shadow_planner_recommendation_payload(
                    planner_result=planner_result,
                    mode=_planner_mode_value(self.planner_mode),
                ),
                "comparison": comparison,
            }
        )
        self.emitted_shadow_checkpoints.add(checkpoint_key)
        shadow_planner_summary = _build_shadow_planner_summary(
            timeline=self.shadow_timeline,
            mode=_planner_mode_value(self.planner_mode),
        )
        _put_shadow_planner_artifacts(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            timeline=self.shadow_timeline,
            latest_summary=shadow_planner_summary,
            mode=_planner_mode_value(self.planner_mode),
        )
        self.artifact_store.patch_workspace(
            space_id=self.space_id,
            run_id=self.run_id,
            patch={
                "shadow_planner": shadow_planner_summary,
                "shadow_planner_mode": _planner_mode_value(self.planner_mode),
                "planner_execution_mode": _planner_mode_value(self.planner_mode),
                "shadow_planner_timeline_key": _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
                "shadow_planner_recommendation_key": (
                    _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY
                ),
                "shadow_planner_comparison_key": (
                    _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY
                ),
            },
        )
        return planner_result, comparison

    def _shadow_timeline_entry(self, checkpoint_key: str) -> JSONObject | None:
        for entry in reversed(self.shadow_timeline):
            if entry.get("checkpoint_key") != checkpoint_key:
                continue
            if not isinstance(entry.get("recommendation"), dict):
                continue
            if not isinstance(entry.get("comparison"), dict):
                continue
            return entry
        return None

    async def _get_or_emit_shadow_checkpoint(
        self,
        *,
        checkpoint_key: str,
        workspace_summary: JSONObject,
        deterministic_decisions: list[ResearchOrchestratorDecision],
    ) -> tuple[JSONObject, JSONObject]:
        await self.wait_for_shadow_planner_updates()
        existing_entry = self._shadow_timeline_entry(checkpoint_key)
        if existing_entry is not None:
            recommendation = existing_entry.get("recommendation")
            comparison = existing_entry.get("comparison")
            if isinstance(recommendation, dict) and isinstance(comparison, dict):
                return dict(recommendation), dict(comparison)

        planner_result, comparison = await self._emit_shadow_checkpoint(
            checkpoint_key=checkpoint_key,
            workspace_summary=workspace_summary,
            deterministic_decisions=deterministic_decisions,
        )
        return (
            _shadow_planner_recommendation_payload(
                planner_result=planner_result,
                mode=_planner_mode_value(self.planner_mode),
            ),
            comparison,
        )

    def _checkpoint_keys_for_phase(
        self,
        *,
        phase: str,
        workspace_snapshot: JSONObject,
    ) -> list[str]:
        checkpoint_keys: list[str] = []
        if phase == "document_ingestion":
            checkpoint_keys = ["after_pubmed_discovery"]
        elif phase == "structured_enrichment":
            checkpoint_keys = [
                "after_pubmed_ingest_extract",
                "after_driven_terms_ready",
            ]
        elif phase == "chase_round_1":
            checkpoint_keys = ["after_bootstrap"]
        elif phase == "chase_round_2":
            checkpoint_keys = ["after_chase_round_1"]
        elif phase == "deferred_mondo":
            checkpoint_keys = self._checkpoint_keys_for_terminal_phase(
                workspace_snapshot=workspace_snapshot,
                include_terminal=False,
            )
        elif phase == "completed":
            checkpoint_keys = self._checkpoint_keys_for_terminal_phase(
                workspace_snapshot=workspace_snapshot,
                include_terminal=True,
            )
        return checkpoint_keys

    def _checkpoint_keys_for_terminal_phase(
        self,
        *,
        workspace_snapshot: JSONObject,
        include_terminal: bool,
    ) -> list[str]:
        checkpoint_keys: list[str] = []
        if "after_bootstrap" not in self.emitted_shadow_checkpoints:
            checkpoint_keys.append("after_bootstrap")
        if (
            isinstance(workspace_snapshot.get("chase_round_1"), dict)
            and "after_chase_round_1" not in self.emitted_shadow_checkpoints
        ):
            checkpoint_keys.append("after_chase_round_1")
        if (
            isinstance(workspace_snapshot.get("chase_round_2"), dict)
            and "after_chase_round_2" not in self.emitted_shadow_checkpoints
        ):
            checkpoint_keys.append("after_chase_round_2")
        if include_terminal:
            checkpoint_keys.extend(
                checkpoint_key
                for checkpoint_key in (
                    "before_brief_generation",
                    "before_terminal_stop",
                )
                if checkpoint_key not in self.emitted_shadow_checkpoints
            )
        return checkpoint_keys


































































































def _store_pending_action_output_artifacts(
    *,
    artifact_store,
    space_id: UUID,
    run_id: str,
    objective: str,
    seed_terms: list[str],
    sources: ResearchSpaceSourcePreferences,
    planner_mode: FullAIOrchestratorPlannerMode,
    max_depth: int,
    max_hypotheses: int,
) -> None:
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "planned_source": "pubmed",
            "seed_terms": list(seed_terms),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_DRIVEN_TERMS_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "objective": objective,
            "seed_terms": list(seed_terms),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "selected_sources": dict(sources),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_BOOTSTRAP_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "max_depth": max_depth,
            "max_hypotheses": max_hypotheses,
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "planned_rounds": list(range(1, min(max_depth, 2) + 1)),
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_BRIEF_METADATA_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "status": "pending",
            "result_key": "research_brief",
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "mode": _planner_mode_value(planner_mode),
            "checkpoint_count": 0,
            "checkpoints": [],
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "mode": _planner_mode_value(planner_mode),
            "planner_status": "pending",
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "mode": _planner_mode_value(planner_mode),
            "comparison_status": "pending",
        },
    )
    _put_guarded_execution_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run_id,
        planner_mode=planner_mode,
        actions=[],
    )


def store_pubmed_replay_bundle_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
    replay_bundle: ResearchInitPubMedReplayBundle,
) -> None:
    """Persist one prepared PubMed replay bundle for queued orchestrator reuse."""
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_REPLAY_ARTIFACT_KEY,
        media_type="application/json",
        content=serialize_pubmed_replay_bundle(replay_bundle),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={"pubmed_replay_bundle_key": _PUBMED_REPLAY_ARTIFACT_KEY},
    )


def load_pubmed_replay_bundle_artifact(
    *,
    artifact_store: HarnessArtifactStore,
    space_id: UUID,
    run_id: str,
) -> ResearchInitPubMedReplayBundle | None:
    """Load a previously stored PubMed replay bundle for one orchestrator run."""
    artifact = artifact_store.get_artifact(
        space_id=space_id,
        run_id=run_id,
        artifact_key=_PUBMED_REPLAY_ARTIFACT_KEY,
    )
    if artifact is None:
        return None
    return deserialize_pubmed_replay_bundle(artifact.content)


def queue_full_ai_orchestrator_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    objective: str,
    seed_terms: list[str],
    sources: ResearchSpaceSourcePreferences,
    max_depth: int,
    max_hypotheses: int,
    graph_service_status: str,
    graph_service_version: str,
    run_registry,
    artifact_store,
    execution_services,
    planner_mode: FullAIOrchestratorPlannerMode = (
        FullAIOrchestratorPlannerMode.SHADOW
    ),
    guarded_rollout_profile: (
        FullAIOrchestratorGuardedRolloutProfile | str | None
    ) = None,
    guarded_rollout_profile_source: str | None = None,
) -> HarnessRunRecord:
    """Create a queued full AI orchestrator run without executing it inline."""
    resolved_guarded_rollout_profile, resolved_guarded_rollout_profile_source = (
        resolve_guarded_rollout_profile(
            planner_mode=planner_mode,
            request_profile=guarded_rollout_profile,
        )
    )
    if guarded_rollout_profile_source is not None:
        resolved_guarded_rollout_profile_source = guarded_rollout_profile_source
    guarded_chase_rollout_enabled = _guarded_profile_allows_chase(
        guarded_rollout_profile=resolved_guarded_rollout_profile,
    )
    source_results = build_source_results(sources=sources)
    shadow_workspace_summary = build_shadow_planner_workspace_summary(
        checkpoint_key="before_first_action",
        mode=_planner_mode_value(planner_mode),
        objective=objective,
        seed_terms=seed_terms,
        sources=sources,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        workspace_snapshot={
            "source_results": source_results,
            "current_round": 0,
            "documents_ingested": 0,
            "proposal_count": 0,
            "pending_questions": [],
            "errors": [],
        },
        prior_decisions=[],
        action_registry=orchestrator_action_registry(),
    )
    run = run_registry.create_run(
        space_id=space_id,
        harness_id=_HARNESS_ID,
        title=title,
        input_payload={
            "objective": objective,
            "seed_terms": list(seed_terms),
            "sources": dict(sources),
            "planner_mode": _planner_mode_value(planner_mode),
            "guarded_rollout_profile": resolved_guarded_rollout_profile,
            "guarded_rollout_profile_source": resolved_guarded_rollout_profile_source,
            "guarded_chase_rollout_enabled": guarded_chase_rollout_enabled,
            "max_depth": max_depth,
            "max_hypotheses": max_hypotheses,
        },
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    ensure_run_transparency_seed(
        run=run,
        artifact_store=artifact_store,
        runtime=execution_services.runtime,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=_ACTION_REGISTRY_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "harness_id": _HARNESS_ID,
            "version": _STEP_KEY_VERSION,
            "actions": [
                spec.model_dump(mode="json") for spec in orchestrator_action_registry()
            ],
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=_INITIALIZE_ARTIFACT_KEY,
        media_type="application/json",
        content={
            "objective": objective,
            "seed_terms": list(seed_terms),
            "sources": dict(sources),
            "planner_mode": _planner_mode_value(planner_mode),
            "guarded_rollout_profile": resolved_guarded_rollout_profile,
            "guarded_rollout_profile_source": resolved_guarded_rollout_profile_source,
            "guarded_rollout_policy": _guarded_rollout_policy_summary(
                planner_mode=planner_mode,
                guarded_rollout_profile=resolved_guarded_rollout_profile,
                guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            ),
            "guarded_chase_rollout_enabled": guarded_chase_rollout_enabled,
            "max_depth": max_depth,
            "max_hypotheses": max_hypotheses,
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=_SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
        media_type="application/json",
        content=shadow_workspace_summary,
    )
    initial_decisions = _build_initial_decision_history(
        objective=objective,
        seed_terms=seed_terms,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        sources=sources,
    )
    _put_decision_history_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        decisions=initial_decisions,
    )
    _put_guarded_execution_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        planner_mode=planner_mode,
        actions=[],
    )
    _put_guarded_readiness_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        planner_mode=planner_mode,
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
        actions=[],
    )
    if planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
        _put_guarded_decision_proof_artifacts(
            artifact_store=artifact_store,
            space_id=space_id,
            run_id=run.id,
            planner_mode=planner_mode,
            guarded_rollout_profile=resolved_guarded_rollout_profile,
            guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            proofs=[],
        )
    _store_pending_action_output_artifacts(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        objective=objective,
        seed_terms=seed_terms,
        sources=sources,
        planner_mode=planner_mode,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "objective": objective,
            "seed_terms": list(seed_terms),
            "enabled_sources": dict(sources),
            "sources": dict(sources),
            "current_round": 0,
            "source_results": source_results,
            "documents_ingested": 0,
            "proposal_count": 0,
            "pending_questions": [],
            "errors": [],
            "bootstrap_run_id": None,
            "bootstrap_summary": None,
            "chase_round_summaries": [],
            "brief_result_key": "research_brief",
            "decision_history_key": _DECISION_HISTORY_ARTIFACT_KEY,
            "action_registry_key": _ACTION_REGISTRY_ARTIFACT_KEY,
            "shadow_planner_mode": _planner_mode_value(planner_mode),
            "planner_execution_mode": _planner_mode_value(planner_mode),
            "guarded_rollout_profile": resolved_guarded_rollout_profile,
            "guarded_rollout_profile_source": resolved_guarded_rollout_profile_source,
            "guarded_rollout_policy": _guarded_rollout_policy_summary(
                planner_mode=planner_mode,
                guarded_rollout_profile=resolved_guarded_rollout_profile,
                guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            ),
            "guarded_chase_rollout_enabled": guarded_chase_rollout_enabled,
            "shadow_planner_workspace_key": _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
            "shadow_planner_recommendation_key": (
                _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY
            ),
            "shadow_planner_comparison_key": _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
            "shadow_planner_timeline_key": _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
            "guarded_execution_log_key": _GUARDED_EXECUTION_ARTIFACT_KEY,
            "guarded_readiness_key": _GUARDED_READINESS_ARTIFACT_KEY,
            "guarded_execution": _guarded_execution_summary(
                planner_mode=planner_mode,
                actions=[],
            ),
            "guarded_readiness": _guarded_readiness_summary(
                planner_mode=planner_mode,
                guarded_rollout_profile=resolved_guarded_rollout_profile,
                guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
                actions=[],
            ),
            "decision_count": len(initial_decisions),
            "last_decision_id": initial_decisions[-1].decision_id,
        },
    )
    if planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "guarded_decision_proofs_key": (
                    _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
                ),
                "guarded_decision_proofs": _guarded_decision_proof_summary(
                    planner_mode=planner_mode,
                    guarded_rollout_profile=resolved_guarded_rollout_profile,
                    guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
                    proofs=[],
                ),
            },
        )
    return run


async def execute_full_ai_orchestrator_run(  # noqa: PLR0913, PLR0915
    *,
    space_id: UUID,
    title: str,
    objective: str,
    seed_terms: list[str],
    max_depth: int,
    max_hypotheses: int,
    sources: ResearchSpaceSourcePreferences,
    execution_services,
    existing_run: HarnessRunRecord,
    planner_mode: FullAIOrchestratorPlannerMode = (
        FullAIOrchestratorPlannerMode.SHADOW
    ),
    guarded_rollout_profile: (
        FullAIOrchestratorGuardedRolloutProfile | str | None
    ) = None,
    guarded_rollout_profile_source: str | None = None,
    pubmed_replay_bundle: ResearchInitPubMedReplayBundle | None = None,
    structured_enrichment_replay_bundle: (
        ResearchInitStructuredEnrichmentReplayBundle | None
    ) = None,
    replayed_research_init_result: ResearchInitExecutionResult | None = None,
    replayed_workspace_snapshot: JSONObject | None = None,
    replayed_phase_records: dict[str, list[JSONObject]] | None = None,
) -> FullAIOrchestratorExecutionResult:
    """Execute the deterministic Phase 1 orchestrator baseline."""
    resolved_guarded_rollout_profile, resolved_guarded_rollout_profile_source = (
        resolve_guarded_rollout_profile(
            planner_mode=planner_mode,
            request_profile=guarded_rollout_profile,
        )
    )
    if guarded_rollout_profile_source is not None:
        resolved_guarded_rollout_profile_source = guarded_rollout_profile_source
    guarded_chase_rollout_enabled = _guarded_profile_allows_chase(
        guarded_rollout_profile=resolved_guarded_rollout_profile,
    )
    effective_pubmed_replay_bundle = pubmed_replay_bundle
    if effective_pubmed_replay_bundle is None:
        effective_pubmed_replay_bundle = load_pubmed_replay_bundle_artifact(
            artifact_store=execution_services.artifact_store,
            space_id=space_id,
            run_id=existing_run.id,
        )
    action_registry = orchestrator_action_registry()
    initial_decisions = _build_initial_decision_history(
        objective=objective,
        seed_terms=seed_terms,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        sources=sources,
    )
    initial_workspace_summary = build_shadow_planner_workspace_summary(
        checkpoint_key="before_first_action",
        mode=_planner_mode_value(planner_mode),
        objective=objective,
        seed_terms=seed_terms,
        sources=sources,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        workspace_snapshot={
            "source_results": build_source_results(sources=sources),
            "current_round": 0,
            "documents_ingested": 0,
            "proposal_count": 0,
            "pending_questions": [],
            "errors": [],
        },
        prior_decisions=[
            decision.model_dump(mode="json") for decision in initial_decisions
        ],
        action_registry=action_registry,
    )
    progress_observer = _FullAIOrchestratorProgressObserver(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        objective=objective,
        seed_terms=list(seed_terms),
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        sources=sources,
        planner_mode=planner_mode,
        action_registry=action_registry,
        decisions=initial_decisions,
        initial_workspace_summary=initial_workspace_summary,
        phase_records={},
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
        guarded_chase_rollout_enabled=guarded_chase_rollout_enabled,
    )
    progress_observer.enqueue_initial_shadow_checkpoint()
    if replayed_research_init_result is not None:
        execution_services.run_registry.set_run_status(
            space_id=space_id,
            run_id=existing_run.id,
            status="running",
        )
        sanitized_snapshot = _sanitize_replayed_workspace_snapshot(
            replayed_workspace_snapshot,
        )
        if sanitized_snapshot:
            execution_services.artifact_store.patch_workspace(
                space_id=space_id,
                run_id=existing_run.id,
                patch=sanitized_snapshot,
            )
        updated_run = execution_services.run_registry.set_run_status(
            space_id=space_id,
            run_id=existing_run.id,
            status="completed",
        )
        research_init_result = replace(
            replayed_research_init_result,
            run=existing_run if updated_run is None else updated_run,
        )
        if replayed_phase_records is not None:
            progress_observer.phase_records.clear()
            progress_observer.phase_records.update(deepcopy(replayed_phase_records))
    else:
        research_init_result = await execute_research_init_run(
            space_id=space_id,
            title=title,
            objective=objective,
            seed_terms=seed_terms,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            sources=sources,
            execution_services=execution_services,
            existing_run=existing_run,
            progress_observer=progress_observer,
            pubmed_replay_bundle=effective_pubmed_replay_bundle,
            structured_enrichment_replay_bundle=structured_enrichment_replay_bundle,
        )
    workspace_record = execution_services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=existing_run.id,
    )
    workspace_snapshot = (
        workspace_record.snapshot if workspace_record is not None else {}
    )
    if planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
        progress_observer.verify_guarded_structured_enrichment(
            workspace_snapshot=workspace_snapshot,
        )
        while progress_observer.verify_guarded_chase_selection(
            workspace_snapshot=workspace_snapshot,
        ):
            pass
        if workspace_snapshot.get("guarded_terminal_control_action") is not None:
            progress_observer.verify_guarded_terminal_control_flow(
                workspace_snapshot=workspace_snapshot,
            )
        elif workspace_snapshot.get("guarded_stop_after_chase_round") == 1:
            progress_observer.verify_guarded_brief_generation(
                workspace_snapshot=workspace_snapshot,
            )
    source_execution_summary = _build_source_execution_summary(
        selected_sources=sources,
        workspace_snapshot=workspace_snapshot,
        research_init_result=research_init_result,
    )
    bootstrap_summary = (
        workspace_snapshot.get("bootstrap_summary")
        if isinstance(workspace_snapshot.get("bootstrap_summary"), dict)
        else None
    )
    brief_metadata = _build_brief_metadata(
        workspace_snapshot=workspace_snapshot,
        research_init_result=research_init_result,
    )
    decisions = _build_decision_history(
        objective=objective,
        seed_terms=seed_terms,
        max_depth=max_depth,
        max_hypotheses=max_hypotheses,
        sources=sources,
        workspace_snapshot=workspace_snapshot,
        research_init_result=research_init_result,
        source_execution_summary=source_execution_summary,
        bootstrap_summary=bootstrap_summary,
        brief_metadata=brief_metadata,
    )
    shadow_planner_timeline = await progress_observer.finalize_shadow_planner(
        final_workspace_snapshot=workspace_snapshot,
        final_decisions=decisions,
    )
    shadow_planner_summary = _build_shadow_planner_summary(
        timeline=shadow_planner_timeline,
        mode=_planner_mode_value(planner_mode),
    )
    _put_shadow_planner_artifacts(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        timeline=shadow_planner_timeline,
        latest_summary=shadow_planner_summary,
        mode=_planner_mode_value(planner_mode),
    )
    _put_decision_history_artifact(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        decisions=decisions,
    )
    _store_action_output_artifacts(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        objective=objective,
        seed_terms=seed_terms,
        workspace_snapshot=workspace_snapshot,
        source_execution_summary=source_execution_summary,
        bootstrap_summary=bootstrap_summary,
        brief_metadata=brief_metadata,
    )
    _put_guarded_execution_artifact(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        planner_mode=planner_mode,
        actions=progress_observer.guarded_execution_log,
    )
    guarded_decision_proof_summary = None
    if planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
        _put_guarded_decision_proof_artifacts(
            artifact_store=execution_services.artifact_store,
            space_id=space_id,
            run_id=existing_run.id,
            planner_mode=planner_mode,
            guarded_rollout_profile=resolved_guarded_rollout_profile,
            guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            proofs=progress_observer.guarded_decision_proofs,
        )
        guarded_decision_proof_summary = _guarded_decision_proof_summary(
            planner_mode=planner_mode,
            guarded_rollout_profile=resolved_guarded_rollout_profile,
            guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            proofs=progress_observer.guarded_decision_proofs,
        )
    _put_guarded_readiness_artifact(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=existing_run.id,
        planner_mode=planner_mode,
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
        actions=progress_observer.guarded_execution_log,
        proofs=progress_observer.guarded_decision_proofs,
    )
    workspace_summary = _build_workspace_summary(workspace_snapshot=workspace_snapshot)
    workspace_summary["shadow_planner_mode"] = _planner_mode_value(planner_mode)
    workspace_summary["planner_execution_mode"] = _planner_mode_value(planner_mode)
    workspace_summary["guarded_rollout_profile"] = resolved_guarded_rollout_profile
    workspace_summary["guarded_rollout_profile_source"] = (
        resolved_guarded_rollout_profile_source
    )
    workspace_summary["guarded_rollout_policy"] = _guarded_rollout_policy_summary(
        planner_mode=planner_mode,
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
    )
    workspace_summary["guarded_chase_rollout_enabled"] = guarded_chase_rollout_enabled
    workspace_summary["shadow_planner_timeline_key"] = (
        _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY
    )
    workspace_summary["shadow_planner_recommendation_key"] = (
        _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY
    )
    workspace_summary["shadow_planner_comparison_key"] = (
        _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY
    )
    workspace_summary["guarded_execution_log_key"] = _GUARDED_EXECUTION_ARTIFACT_KEY
    workspace_summary["guarded_readiness_key"] = _GUARDED_READINESS_ARTIFACT_KEY
    workspace_summary["guarded_execution"] = _guarded_execution_summary(
        planner_mode=planner_mode,
        actions=progress_observer.guarded_execution_log,
    )
    workspace_summary["guarded_readiness"] = _guarded_readiness_summary(
        planner_mode=planner_mode,
        guarded_rollout_profile=resolved_guarded_rollout_profile,
        guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
        actions=progress_observer.guarded_execution_log,
        proofs=progress_observer.guarded_decision_proofs,
    )
    if guarded_decision_proof_summary is not None:
        workspace_summary["guarded_decision_proofs_key"] = (
            _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
        )
        workspace_summary["guarded_decision_proofs"] = guarded_decision_proof_summary
    run_record = research_init_result.run
    result = FullAIOrchestratorExecutionResult(
        run=run_record,
        planner_mode=planner_mode,
        guarded_rollout_profile=(
            resolved_guarded_rollout_profile
            if planner_mode is FullAIOrchestratorPlannerMode.GUARDED
            else None
        ),
        guarded_rollout_profile_source=(
            resolved_guarded_rollout_profile_source
            if planner_mode is FullAIOrchestratorPlannerMode.GUARDED
            else None
        ),
        research_init_result=research_init_result,
        action_history=tuple(decisions),
        workspace_summary=workspace_summary,
        source_execution_summary=source_execution_summary,
        bootstrap_summary=bootstrap_summary,
        brief_metadata=brief_metadata,
        shadow_planner=shadow_planner_summary,
        guarded_execution=_guarded_execution_summary(
            planner_mode=planner_mode,
            actions=progress_observer.guarded_execution_log,
        ),
        guarded_decision_proofs=guarded_decision_proof_summary,
        errors=list(research_init_result.errors),
    )
    response_payload = build_full_ai_orchestrator_run_response(result).model_dump(
        mode="json",
    )
    store_primary_result_artifact(
        artifact_store=execution_services.artifact_store,
        space_id=space_id,
        run_id=run_record.id,
        artifact_key=_RESULT_ARTIFACT_KEY,
        content=response_payload,
        status_value="completed",
        result_keys=(
            _RESULT_ARTIFACT_KEY,
            "research_init_result",
            _DECISION_HISTORY_ARTIFACT_KEY,
            _ACTION_REGISTRY_ARTIFACT_KEY,
            _INITIALIZE_ARTIFACT_KEY,
            _PUBMED_ARTIFACT_KEY,
            _DRIVEN_TERMS_ARTIFACT_KEY,
            _SOURCE_EXECUTION_ARTIFACT_KEY,
            _BOOTSTRAP_ARTIFACT_KEY,
            _CHASE_ROUNDS_ARTIFACT_KEY,
            _BRIEF_METADATA_ARTIFACT_KEY,
            _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
            _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY,
            _SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY,
            _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
            _GUARDED_EXECUTION_ARTIFACT_KEY,
            _GUARDED_READINESS_ARTIFACT_KEY,
            *(
                (_GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY,)
                if guarded_decision_proof_summary is not None
                else ()
            ),
        ),
        workspace_patch={
            "decision_history_key": _DECISION_HISTORY_ARTIFACT_KEY,
            "action_registry_key": _ACTION_REGISTRY_ARTIFACT_KEY,
            "decision_count": len(decisions),
            "last_decision_id": decisions[-1].decision_id,
            "workspace_summary": workspace_summary,
            "source_execution_summary": source_execution_summary,
            "brief_metadata": brief_metadata,
            "shadow_planner_mode": _planner_mode_value(planner_mode),
            "planner_execution_mode": _planner_mode_value(planner_mode),
            "guarded_rollout_profile": resolved_guarded_rollout_profile,
            "guarded_rollout_profile_source": resolved_guarded_rollout_profile_source,
            "guarded_rollout_policy": _guarded_rollout_policy_summary(
                planner_mode=planner_mode,
                guarded_rollout_profile=resolved_guarded_rollout_profile,
                guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
            ),
            "guarded_chase_rollout_enabled": guarded_chase_rollout_enabled,
            "shadow_planner_workspace_key": _SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY,
            "shadow_planner_recommendation_key": (
                _SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY
            ),
            "shadow_planner_comparison_key": (_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY),
            "shadow_planner_timeline_key": _SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY,
            "shadow_planner": shadow_planner_summary,
            "guarded_execution_log_key": _GUARDED_EXECUTION_ARTIFACT_KEY,
            "guarded_readiness_key": _GUARDED_READINESS_ARTIFACT_KEY,
            "guarded_execution": _guarded_execution_summary(
                planner_mode=planner_mode,
                actions=progress_observer.guarded_execution_log,
            ),
            "guarded_readiness": _guarded_readiness_summary(
                planner_mode=planner_mode,
                guarded_rollout_profile=resolved_guarded_rollout_profile,
                guarded_rollout_profile_source=resolved_guarded_rollout_profile_source,
                actions=progress_observer.guarded_execution_log,
                proofs=progress_observer.guarded_decision_proofs,
            ),
            **(
                {
                    "guarded_decision_proofs_key": (
                        _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
                    ),
                    "guarded_decision_proofs": guarded_decision_proof_summary,
                }
                if guarded_decision_proof_summary is not None
                else {}
            ),
            "chase_round_summaries": _collect_chase_round_summaries(
                workspace_snapshot=workspace_snapshot,
            ),
            "full_ai_orchestrator_result": response_payload,
            "brief_result_key": "research_brief",
        },
    )
    return result


def build_full_ai_orchestrator_run_response(
    result: FullAIOrchestratorExecutionResult,
) -> FullAIOrchestratorRunResponse:
    """Serialize one completed orchestrator run for HTTP responses."""
    return FullAIOrchestratorRunResponse(
        planner_mode=result.planner_mode,
        guarded_rollout_profile=result.guarded_rollout_profile,
        run=serialize_run_record(run=result.run),
        action_history=list(result.action_history),
        workspace_summary=result.workspace_summary,
        source_execution_summary=result.source_execution_summary,
        bootstrap_summary=result.bootstrap_summary,
        brief_metadata=result.brief_metadata,
        shadow_planner=result.shadow_planner,
        guarded_execution=result.guarded_execution,
        guarded_decision_proofs=result.guarded_decision_proofs,
        errors=list(result.errors),
    )




















__all__ = [
    "FullAIOrchestratorExecutionResult",
    "build_full_ai_orchestrator_run_response",
    "build_step_key",
    "execute_full_ai_orchestrator_run",
    "is_control_action",
    "is_source_action",
    "orchestrator_action_registry",
    "queue_full_ai_orchestrator_run",
    "require_action_enabled_for_sources",
    "resolve_guarded_rollout_profile",
]
