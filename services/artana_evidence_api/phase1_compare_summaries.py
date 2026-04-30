"""Workspace, telemetry, and advisory helpers for Phase 1 comparison."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Final, cast

from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorChaseCandidate,
    ResearchOrchestratorChaseSelection,
)
from artana_evidence_api.full_ai_orchestrator_runtime import (
    _STRUCTURED_ENRICHMENT_SOURCES,
    _accepted_guarded_chase_selection_action,
    _accepted_guarded_control_flow_action,
    _accepted_guarded_generate_brief_action,
    _accepted_guarded_structured_source_action,
)
from artana_evidence_api.types.common import (
    JSONObject,
    ResearchSpaceSettings,
    ResearchSpaceSourcePreferences,
    json_object,
    json_object_or_empty,
)
from pydantic import ValidationError

_UUID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
_PUBMED_BACKEND_ENV: Final[str] = "ARTANA_PUBMED_SEARCH_BACKEND"
_GUARDED_CHASE_ROLLOUT_ENV: Final[str] = "ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT"
_GUARDED_ROLLOUT_PROFILE_ENV: Final[str] = "ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE"
_DUAL_LIVE_GUARDED_MODE: Final[str] = "dual_live_guarded"
_ALL_SOURCE_KEYS: Final[tuple[str, ...]] = (
    "pubmed",
    "marrvel",
    "clinvar",
    "mondo",
    "pdf",
    "text",
    "drugbank",
    "alphafold",
    "uniprot",
    "hgnc",
    "clinical_trials",
    "mgi",
    "zfin",
)


def _source_settings(sources: ResearchSpaceSourcePreferences) -> ResearchSpaceSettings:
    return {"sources": sources}


def _source_payload(sources: ResearchSpaceSourcePreferences) -> JSONObject:
    return json_object_or_empty(sources)

def build_phase1_source_preferences(
    enabled_sources: list[str] | tuple[str, ...],
) -> ResearchSpaceSourcePreferences:
    """Return a normalized source preference map for the compare run."""
    selected = {source.strip() for source in enabled_sources if source.strip() != ""}
    unknown = sorted(source for source in selected if source not in _ALL_SOURCE_KEYS)
    if unknown:
        msg = f"Unknown source keys: {', '.join(unknown)}"
        raise ValueError(msg)
    return cast(
        "ResearchSpaceSourcePreferences",
        {source: source in selected for source in _ALL_SOURCE_KEYS},
    )


def _normalize_seed_terms(seed_terms: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for term in seed_terms:
        trimmed = term.strip()
        if trimmed == "":
            continue
        normalized.append(trimmed)
    if not normalized:
        msg = "At least one non-empty seed term is required"
        raise ValueError(msg)
    return tuple(normalized)


def _workspace_source_summary(snapshot: JSONObject) -> JSONObject:
    source_results = snapshot.get("source_results")
    if not isinstance(source_results, dict):
        return {}
    return {
        key: value
        for key, value in source_results.items()
        if isinstance(key, str) and isinstance(value, dict)
    }


def _workspace_chase_context_summary(value: object) -> JSONObject | None:
    if not isinstance(value, dict):
        return None
    filtered_chase_candidates = (
        [
            item
            for item in value.get("filtered_chase_candidates", [])
            if isinstance(item, dict)
        ]
        if isinstance(value.get("filtered_chase_candidates"), list)
        else []
    )
    filtered_labels = [
        item["display_label"]
        for item in filtered_chase_candidates
        if isinstance(item.get("display_label"), str)
    ]
    filtered_reason_counts = (
        {
            key: count
            for key, count in value.get(
                "filtered_chase_filter_reason_counts",
                {},
            ).items()
            if isinstance(key, str) and isinstance(count, int)
        }
        if isinstance(value.get("filtered_chase_filter_reason_counts"), dict)
        else {}
    )
    return {
        "round_number": value.get("round_number"),
        "candidate_count": value.get("candidate_count"),
        "deterministic_candidate_count": value.get("deterministic_candidate_count"),
        "deterministic_threshold_met": value.get("deterministic_threshold_met"),
        "selection_mode": value.get("selection_mode"),
        "selected_labels": (
            [item for item in value.get("selected_labels", []) if isinstance(item, str)]
            if isinstance(value.get("selected_labels"), list)
            else []
        ),
        "filtered_chase_candidate_count": value.get("filtered_chase_candidate_count"),
        "filtered_chase_filter_reason_counts": filtered_reason_counts,
        "filtered_chase_labels": filtered_labels,
    }


def _workspace_guarded_decision_proofs_summary(value: object) -> JSONObject | None:
    if not isinstance(value, dict):
        return None
    proofs = value.get("proofs")
    proof_summaries = (
        [
            {
                "proof_id": proof.get("proof_id"),
                "checkpoint_key": proof.get("checkpoint_key"),
                "guarded_strategy": proof.get("guarded_strategy"),
                "guarded_rollout_profile": proof.get("guarded_rollout_profile"),
                "guarded_rollout_profile_source": proof.get(
                    "guarded_rollout_profile_source",
                ),
                "decision_outcome": proof.get("decision_outcome"),
                "outcome_reason": proof.get("outcome_reason"),
                "recommended_action_type": proof.get("recommended_action_type"),
                "applied_action_type": proof.get("applied_action_type"),
                "policy_allowed": proof.get("policy_allowed"),
                "verification_status": proof.get("verification_status"),
                "used_fallback": proof.get("used_fallback"),
                "fallback_reason": proof.get("fallback_reason"),
                "validation_error": proof.get("validation_error"),
                "qualitative_rationale_present": proof.get(
                    "qualitative_rationale_present",
                ),
                "budget_violation": proof.get("budget_violation"),
                "disabled_source_violation": proof.get(
                    "disabled_source_violation",
                ),
                "planner_status": proof.get("planner_status"),
                "model_id": proof.get("model_id"),
                "prompt_version": proof.get("prompt_version"),
                "agent_run_id": proof.get("agent_run_id"),
            }
            for proof in proofs
            if isinstance(proof, dict)
        ]
        if isinstance(proofs, list)
        else []
    )
    artifact_keys = (
        [key for key in value.get("artifact_keys", []) if isinstance(key, str)]
        if isinstance(value.get("artifact_keys"), list)
        else []
    )
    return {
        "mode": value.get("mode"),
        "policy_version": value.get("policy_version"),
        "guarded_rollout_profile": value.get("guarded_rollout_profile"),
        "guarded_rollout_profile_source": value.get(
            "guarded_rollout_profile_source",
        ),
        "proof_count": value.get("proof_count"),
        "allowed_count": value.get("allowed_count"),
        "blocked_count": value.get("blocked_count"),
        "ignored_count": value.get("ignored_count"),
        "verified_count": value.get("verified_count"),
        "verification_failed_count": value.get("verification_failed_count"),
        "pending_verification_count": value.get("pending_verification_count"),
        "artifact_keys": artifact_keys,
        "proofs": proof_summaries,
    }


def summarize_workspace(snapshot: JSONObject | None) -> JSONObject:
    """Extract the high-signal fields we compare between both flows."""
    if snapshot is None:
        return {"present": False}
    source_results = _workspace_source_summary(snapshot)
    return {
        "present": True,
        "status": snapshot.get("status"),
        "documents_ingested": snapshot.get("documents_ingested"),
        "proposal_count": snapshot.get("proposal_count"),
        "pending_questions": snapshot.get("pending_questions"),
        "errors": snapshot.get("errors"),
        "pubmed_results": snapshot.get("pubmed_results"),
        "driven_terms": snapshot.get("driven_terms"),
        "bootstrap_run_id": snapshot.get("bootstrap_run_id"),
        "bootstrap_summary": snapshot.get("bootstrap_summary"),
        "brief_present": isinstance(snapshot.get("research_brief"), dict),
        "planner_execution_mode": snapshot.get("planner_execution_mode"),
        "guarded_rollout_profile": snapshot.get("guarded_rollout_profile"),
        "guarded_rollout_policy": json_object(
            snapshot.get("guarded_rollout_policy")
        ),
        "guarded_readiness": json_object(snapshot.get("guarded_readiness")),
        "guarded_execution": json_object(snapshot.get("guarded_execution")),
        "guarded_decision_proofs_key": snapshot.get("guarded_decision_proofs_key"),
        "guarded_decision_proofs": _workspace_guarded_decision_proofs_summary(
            snapshot.get("guarded_decision_proofs"),
        ),
        "pending_chase_round": _workspace_chase_context_summary(
            snapshot.get("pending_chase_round"),
        ),
        "chase_round_1": _workspace_chase_context_summary(
            snapshot.get("chase_round_1"),
        ),
        "chase_round_2": _workspace_chase_context_summary(
            snapshot.get("chase_round_2"),
        ),
        "source_results": source_results,
    }


def summarize_guarded_execution(guarded_execution: object) -> JSONObject:
    """Return a compact evaluation summary for guarded pilot actions."""
    if not isinstance(guarded_execution, dict):
        return {
            "present": False,
            "mode": None,
            "applied_count": 0,
            "verified_count": 0,
            "verification_failed_count": 0,
            "pending_verification_count": 0,
            "all_verified": False,
            "actions": [],
            "failed_actions": [],
        }

    actions = (
        [
            action
            for action in guarded_execution.get("actions", [])
            if isinstance(action, dict)
        ]
        if isinstance(guarded_execution.get("actions"), list)
        else []
    )
    failed_actions: list[JSONObject] = []
    chase_action_count = 0
    chase_verified_count = 0
    chase_exact_selection_match_count = 0
    chase_selected_entity_overlap_total = 0
    chase_selection_mismatch_count = 0
    terminal_control_action_count = 0
    terminal_control_verified_count = 0
    chase_checkpoint_stop_count = 0
    chase_checkpoint_escalate_count = 0
    action_summaries: list[JSONObject] = []
    for action in actions:
        action_summary = _guarded_execution_action_summary(action)
        action_summaries.append(action_summary)
        if action_summary.get("guarded_strategy") == "terminal_control_flow":
            terminal_control_action_count += 1
            if action_summary.get("verification_status") == "verified":
                terminal_control_verified_count += 1
            if action_summary.get("checkpoint_key") in {
                "after_bootstrap",
                "after_chase_round_1",
            }:
                if action_summary.get("action_type") == "STOP":
                    chase_checkpoint_stop_count += 1
                elif action_summary.get("action_type") == "ESCALATE_TO_HUMAN":
                    chase_checkpoint_escalate_count += 1
        if action_summary.get("guarded_strategy") == "chase_selection":
            chase_action_count += 1
            if action_summary.get("verification_status") == "verified":
                chase_verified_count += 1
            if bool(action_summary.get("exact_selection_match")):
                chase_exact_selection_match_count += 1
            chase_selected_entity_overlap_total += _guarded_chase_overlap_count(
                action_summary,
            )
            if not bool(action_summary.get("exact_selection_match")):
                chase_selection_mismatch_count += 1
        if action.get("verification_status") != "verification_failed":
            continue
        failed_actions.append(
            {
                "checkpoint_key": action.get("checkpoint_key"),
                "action_type": action.get("applied_action_type"),
                "source_key": action.get("applied_source_key"),
                "verification_reason": action.get("verification_reason"),
            },
        )
    applied_count = (
        guarded_execution.get("applied_count")
        if isinstance(guarded_execution.get("applied_count"), int)
        else len(actions)
    )
    verified_count = (
        guarded_execution.get("verified_count")
        if isinstance(guarded_execution.get("verified_count"), int)
        else 0
    )
    verification_failed_count = (
        guarded_execution.get("verification_failed_count")
        if isinstance(guarded_execution.get("verification_failed_count"), int)
        else len(failed_actions)
    )
    pending_verification_count = (
        guarded_execution.get("pending_verification_count")
        if isinstance(guarded_execution.get("pending_verification_count"), int)
        else 0
    )
    return {
        "present": True,
        "mode": guarded_execution.get("mode"),
        "applied_count": applied_count,
        "verified_count": verified_count,
        "verification_failed_count": verification_failed_count,
        "pending_verification_count": pending_verification_count,
        "all_verified": (
            verification_failed_count == 0 and pending_verification_count == 0
        ),
        "chase_action_count": chase_action_count,
        "chase_verified_count": chase_verified_count,
        "chase_exact_selection_match_count": chase_exact_selection_match_count,
        "chase_selected_entity_overlap_total": chase_selected_entity_overlap_total,
        "chase_selection_mismatch_count": chase_selection_mismatch_count,
        "terminal_control_action_count": terminal_control_action_count,
        "terminal_control_verified_count": terminal_control_verified_count,
        "chase_checkpoint_stop_count": chase_checkpoint_stop_count,
        "chase_checkpoint_escalate_count": chase_checkpoint_escalate_count,
        "actions": action_summaries,
        "failed_actions": failed_actions,
    }


def build_guarded_evaluation(
    *,
    planner_mode: FullAIOrchestratorPlannerMode,
    orchestrator_workspace: JSONObject,
    shadow_planner_summary: object | None = None,
) -> JSONObject:
    """Summarize whether guarded actions verified cleanly for one compare run."""
    if planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
        return {
            "mode": planner_mode.value,
            "status": "not_applicable",
            "applied_count": 0,
            "candidate_count": 0,
            "identified_count": 0,
            "verified_count": 0,
            "verification_failed_count": 0,
            "pending_verification_count": 0,
            "all_verified": None,
            "failed_actions": [],
            "applied_actions": [],
            "candidate_actions": [],
            "notes": "Guarded evaluation is only active when planner_mode=guarded.",
        }

    guarded_summary = summarize_guarded_execution(
        orchestrator_workspace.get("guarded_execution"),
    )
    verification_failed_count = _int_value(
        guarded_summary.get("verification_failed_count"),
    )
    pending_verification_count = _int_value(
        guarded_summary.get("pending_verification_count"),
    )
    applied_count = _int_value(guarded_summary.get("applied_count"))
    verified_count = _int_value(guarded_summary.get("verified_count"))
    candidate_summary = summarize_guarded_candidates(
        orchestrator_workspace=orchestrator_workspace,
        shadow_planner_summary=shadow_planner_summary,
    )
    candidate_count = _int_value(candidate_summary.get("candidate_count"))
    status = "clean"
    if verification_failed_count > 0:
        status = "verification_failed"
    elif pending_verification_count > 0:
        status = "verification_pending"
    elif applied_count == 0:
        status = (
            "candidate_detected_replay_only"
            if candidate_count > 0
            else "no_guarded_actions_applied"
        )
    identified_count = applied_count if applied_count > 0 else candidate_count
    return {
        "mode": planner_mode.value,
        "status": status,
        "applied_count": applied_count,
        "candidate_count": candidate_count,
        "identified_count": identified_count,
        "verified_count": verified_count,
        "verification_failed_count": verification_failed_count,
        "pending_verification_count": pending_verification_count,
        "chase_action_count": guarded_summary.get("chase_action_count"),
        "chase_verified_count": guarded_summary.get("chase_verified_count"),
        "chase_exact_selection_match_count": guarded_summary.get(
            "chase_exact_selection_match_count",
        ),
        "chase_selected_entity_overlap_total": guarded_summary.get(
            "chase_selected_entity_overlap_total",
        ),
        "chase_selection_mismatch_count": guarded_summary.get(
            "chase_selection_mismatch_count",
        ),
        "terminal_control_action_count": guarded_summary.get(
            "terminal_control_action_count",
        ),
        "terminal_control_verified_count": guarded_summary.get(
            "terminal_control_verified_count",
        ),
        "chase_checkpoint_stop_count": guarded_summary.get(
            "chase_checkpoint_stop_count",
        ),
        "chase_checkpoint_escalate_count": guarded_summary.get(
            "chase_checkpoint_escalate_count",
        ),
        "chase_candidate_count": candidate_summary.get("chase_candidate_count"),
        "chase_candidate_exact_selection_match_count": candidate_summary.get(
            "chase_candidate_exact_selection_match_count",
        ),
        "chase_candidate_overlap_total": candidate_summary.get(
            "chase_candidate_overlap_total",
        ),
        "all_verified": (
            guarded_summary.get("all_verified") if applied_count > 0 else None
        ),
        "failed_actions": guarded_summary.get("failed_actions"),
        "applied_actions": guarded_summary.get("actions"),
        "candidate_actions": candidate_summary.get("candidate_actions"),
        "notes": (
            "Guarded pilot is healthy."
            if status == "clean"
            else (
                "Shared baseline replay found a valid guarded intervention, but this compare mode cannot execute the branch change live."
                if status == "candidate_detected_replay_only"
                else (
                    "No guarded action was accepted during this compare run."
                    if status == "no_guarded_actions_applied"
                    else "At least one guarded action did not verify cleanly."
                )
            )
        ),
    }


def summarize_guarded_candidates(
    *,
    orchestrator_workspace: JSONObject,
    shadow_planner_summary: object | None,
) -> JSONObject:
    """Extract guarded opportunities from the shadow timeline in replay mode."""
    if not isinstance(shadow_planner_summary, dict):
        return {"candidate_count": 0, "candidate_actions": []}

    timeline = shadow_planner_summary.get("timeline")
    if not isinstance(timeline, list):
        return {"candidate_count": 0, "candidate_actions": []}

    source_results = _workspace_source_summary(orchestrator_workspace)
    available_structured_sources = tuple(
        source_key
        for source_key in _STRUCTURED_ENRICHMENT_SOURCES
        if source_key in source_results
    )
    candidate_actions: list[JSONObject] = []
    chase_candidate_count = 0
    chase_candidate_exact_selection_match_count = 0
    chase_candidate_overlap_total = 0
    for entry in timeline:
        candidate_action = _summarize_guarded_candidate_for_checkpoint(
            entry=entry,
            available_structured_sources=available_structured_sources,
        )
        if candidate_action is None:
            continue
        candidate_action_summary = _guarded_execution_action_summary(
            candidate_action,
        )
        candidate_action_summary["evaluation_mode"] = (
            "shared_baseline_replay_counterfactual"
        )
        if candidate_action_summary.get("guarded_strategy") == "chase_selection":
            chase_candidate_count += 1
            if bool(candidate_action_summary.get("exact_selection_match")):
                chase_candidate_exact_selection_match_count += 1
            chase_candidate_overlap_total += _guarded_chase_overlap_count(
                candidate_action_summary,
            )
        candidate_actions.append(candidate_action_summary)

    return {
        "candidate_count": len(candidate_actions),
        "chase_candidate_count": chase_candidate_count,
        "chase_candidate_exact_selection_match_count": (
            chase_candidate_exact_selection_match_count
        ),
        "chase_candidate_overlap_total": chase_candidate_overlap_total,
        "candidate_actions": candidate_actions,
    }


def _summarize_guarded_candidate_for_checkpoint(
    *,
    entry: object,
    available_structured_sources: tuple[str, ...],
) -> JSONObject | None:
    candidate_action: JSONObject | None = None
    if not isinstance(entry, dict):
        return None
    checkpoint_key = entry.get("checkpoint_key")
    recommendation = entry.get("recommendation")
    comparison = entry.get("comparison")
    if not isinstance(recommendation, dict) or not isinstance(comparison, dict):
        return None
    workspace_summary = json_object_or_empty(entry.get("workspace_summary"))
    if checkpoint_key == "after_driven_terms_ready":
        candidate_action = _accepted_guarded_structured_source_action(
            recommendation_payload=recommendation,
            comparison=comparison,
            available_source_keys=available_structured_sources,
        )
    elif checkpoint_key in {"after_bootstrap", "after_chase_round_1"}:
        candidate_action = _accepted_guarded_control_flow_action(
            recommendation_payload=recommendation,
            comparison=comparison,
        )
        if candidate_action is None:
            chase_candidates = _workspace_chase_candidates(workspace_summary)
            deterministic_selection = _workspace_deterministic_chase_selection(
                workspace_summary,
            )
            round_number = _checkpoint_chase_round_number(checkpoint_key)
            if (
                round_number is not None
                and chase_candidates
                and deterministic_selection is not None
            ):
                candidate_action = _accepted_guarded_chase_selection_action(
                    recommendation_payload=recommendation,
                    comparison=comparison,
                    round_number=round_number,
                    chase_candidates=chase_candidates,
                    deterministic_selection=deterministic_selection,
                )
        if candidate_action is None and checkpoint_key == "after_chase_round_1":
            candidate_action = _accepted_guarded_generate_brief_action(
                recommendation_payload=recommendation,
                comparison=comparison,
            )
    return candidate_action


def _guarded_execution_action_summary(action: JSONObject) -> JSONObject:
    summary: JSONObject = {
        "checkpoint_key": action.get("checkpoint_key"),
        "action_type": action.get("applied_action_type"),
        "source_key": action.get("applied_source_key"),
        "guarded_strategy": action.get("guarded_strategy"),
        "round_number": action.get("round_number"),
        "comparison_status": action.get("comparison_status"),
        "target_action_type": action.get("target_action_type"),
        "target_source_key": action.get("target_source_key"),
        "planner_status": action.get("planner_status"),
        "qualitative_rationale": action.get("qualitative_rationale"),
        "stop_reason": action.get("stop_reason"),
        "recommended_stop": action.get("recommended_stop"),
        "deterministic_stop_expected": action.get("deterministic_stop_expected"),
        "verification_status": action.get("verification_status"),
        "verification_reason": action.get("verification_reason"),
    }
    if action.get("guarded_strategy") != "chase_selection":
        return summary
    selected_entity_ids = _string_list(action.get("selected_entity_ids"))
    selected_labels = _string_list(action.get("selected_labels"))
    deterministic_selected_entity_ids = _string_list(
        action.get("deterministic_selected_entity_ids"),
    )
    deterministic_selected_labels = _string_list(
        action.get("deterministic_selected_labels"),
    )
    summary.update(
        {
            "selected_entity_ids": selected_entity_ids,
            "selected_labels": selected_labels,
            "deterministic_selected_entity_ids": deterministic_selected_entity_ids,
            "deterministic_selected_labels": deterministic_selected_labels,
            "selection_basis": action.get("selection_basis"),
            "selected_entity_overlap_count": len(
                set(selected_entity_ids) & set(deterministic_selected_entity_ids),
            ),
            "exact_selection_match": (
                selected_entity_ids == deterministic_selected_entity_ids
                and selected_labels == deterministic_selected_labels
            ),
        },
    )
    return summary


def _guarded_chase_overlap_count(action: JSONObject) -> int:
    value = action.get("selected_entity_overlap_count")
    return value if isinstance(value, int) else 0


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


@contextmanager
def _temporary_env_setting(name: str, value: str | None) -> Iterator[None]:
    previous = os.getenv(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


def _dict_value(value: object) -> JSONObject:
    return dict(value) if isinstance(value, dict) else {}


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _checkpoint_chase_round_number(checkpoint_key: object) -> int | None:
    if checkpoint_key == "after_bootstrap":
        return 1
    if checkpoint_key == "after_chase_round_1":
        return 2
    return None


def _workspace_chase_candidates(
    workspace_summary: JSONObject,
) -> tuple[ResearchOrchestratorChaseCandidate, ...]:
    raw_candidates = workspace_summary.get("chase_candidates")
    if not isinstance(raw_candidates, list):
        return ()
    parsed_candidates: list[ResearchOrchestratorChaseCandidate] = []
    for candidate in raw_candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            parsed_candidates.append(
                ResearchOrchestratorChaseCandidate.model_validate(candidate),
            )
        except ValidationError:
            continue
    return tuple(parsed_candidates)


def _workspace_deterministic_chase_selection(
    workspace_summary: JSONObject,
) -> ResearchOrchestratorChaseSelection | None:
    selection = workspace_summary.get("deterministic_selection")
    if not isinstance(selection, dict):
        return None
    try:
        return ResearchOrchestratorChaseSelection.model_validate(selection)
    except ValidationError:
        return None


def _normalized_unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        trimmed = value.strip()
        if trimmed == "" or trimmed in seen:
            continue
        seen.add(trimmed)
        normalized.append(trimmed)
    return normalized


def _normalize_pending_questions(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized_questions: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        normalized_question = _UUID_PATTERN.sub("<uuid>", item)
        normalized_questions.add(
            _pending_question_signature(normalized_question),
        )
    return sorted(normalized_questions)


_PENDING_QUESTION_RELATION_PATTERN = re.compile(
    r"^(What evidence best supports )(.+?) ([A-Z_]+) (.+\?)$",
)


def _pending_question_signature(question: str) -> str:
    match = _PENDING_QUESTION_RELATION_PATTERN.match(question)
    if match is None:
        return question
    prefix, subject, _relation, obj = match.groups()
    return f"{prefix}{subject} <relation> {obj}"


_ORDER_INSENSITIVE_SOURCE_RESULT_LIST_KEYS = {
    "alias_errors",
    "available_enrichment_sources",
    "deferred_enrichment_sources",
    "driven_genes_from_pubmed",
    "filtered_chase_labels",
    "selected_enrichment_sources",
}


def _normalize_source_results(value: object, *, key: str | None = None) -> object:
    if isinstance(value, dict):
        return {
            nested_key: _normalize_source_results(nested_value, key=nested_key)
            for nested_key, nested_value in sorted(value.items())
            if isinstance(nested_key, str)
        }
    if isinstance(value, list):
        normalized_items = [_normalize_source_results(item, key=key) for item in value]
        if key in _ORDER_INSENSITIVE_SOURCE_RESULT_LIST_KEYS and all(
            isinstance(item, str) for item in normalized_items
        ):
            normalized_string_items = [
                item for item in normalized_items if isinstance(item, str)
            ]
            return sorted(normalized_string_items)
        return normalized_items
    return value


def resolve_compare_environment() -> JSONObject:
    """Return the volatile environment settings relevant to compare runs."""
    backend = os.getenv(_PUBMED_BACKEND_ENV)
    normalized_backend = backend.strip().lower() if isinstance(backend, str) else ""
    if normalized_backend == "":
        normalized_backend = "default"
    return {
        "pubmed_search_backend": normalized_backend,
    }


def build_compare_advisories(
    *,
    mismatches: list[str],
    environment: JSONObject,
    guarded_evaluation: JSONObject | None = None,
) -> list[str]:
    """Explain known sources of volatility in compare output."""
    advisories: list[str] = []
    pubmed_backend = environment.get("pubmed_search_backend")
    if mismatches and pubmed_backend != "deterministic":
        advisories.append(
            "Live PubMed/backend variability can change candidate sets and proposal counts between runs; rerun compare with the deterministic backend to isolate orchestrator parity.",
        )
    compare_mode = environment.get("compare_mode")
    if (
        compare_mode == _DUAL_LIVE_GUARDED_MODE
        and isinstance(guarded_evaluation, dict)
        and guarded_evaluation.get("status") == "clean"
        and mismatches
    ):
        advisories.append(
            "Live guarded compare is expected to diverge from the deterministic baseline when the planner actually narrows structured sources or stops before chase round 2.",
        )
    if isinstance(guarded_evaluation, dict):
        status = guarded_evaluation.get("status")
        if status == "verification_failed":
            advisories.append(
                "Guarded pilot accepted an action that did not verify cleanly; inspect guarded_evaluation.failed_actions before widening the allowlist.",
            )
        elif status == "verification_pending":
            advisories.append(
                "Guarded pilot left accepted actions in a pending verification state; verify the execution hooks ran after the guarded action completed.",
            )
    return advisories


def compare_workspace_summaries(
    *,
    baseline: JSONObject,
    orchestrator: JSONObject,
) -> list[str]:
    """Return human-readable mismatches between baseline and orchestrator."""
    mismatches = [
        (
            f"{field_name}: baseline={baseline.get(field_name)!r} "
            f"orchestrator={orchestrator.get(field_name)!r}"
        )
        for field_name in (
            "documents_ingested",
            "proposal_count",
            "pubmed_results",
            "driven_terms",
            "brief_present",
        )
        if baseline.get(field_name) != orchestrator.get(field_name)
    ]
    baseline_pending_questions = _normalize_pending_questions(
        baseline.get("pending_questions"),
    )
    orchestrator_pending_questions = _normalize_pending_questions(
        orchestrator.get("pending_questions"),
    )
    if baseline_pending_questions != orchestrator_pending_questions:
        mismatches.append(
            "pending_questions: "
            f"baseline={baseline_pending_questions!r} "
            f"orchestrator={orchestrator_pending_questions!r}",
        )
    baseline_sources = _normalize_source_results(baseline.get("source_results"))
    orchestrator_sources = _normalize_source_results(orchestrator.get("source_results"))
    if baseline_sources != orchestrator_sources:
        mismatches.append(
            "source_results differ between baseline and orchestrator summaries",
        )
    return mismatches




__all__ = [
    name
    for name in globals()
    if name.startswith(("_", "build_", "compare_", "summarize_"))
    or name == "resolve_compare_environment"
]
