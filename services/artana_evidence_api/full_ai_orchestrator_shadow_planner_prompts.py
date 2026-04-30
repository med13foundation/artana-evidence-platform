"""Prompt construction for the full-AI shadow planner."""

from __future__ import annotations

import json
from pathlib import Path

from artana_evidence_api.full_ai_orchestrator_shadow_planner_models import (
    ShadowPlannerRecommendationOutput,
    _string_list,
)
from artana_evidence_api.full_ai_orchestrator_shadow_planner_workspace import (
    _workspace_chase_selection,
    _workspace_planner_constraints,
)
from artana_evidence_api.runtime_support import stable_sha256_digest
from artana_evidence_api.types.common import JSONObject

_PROMPT_PATH = (
    Path(__file__).resolve().parent
    / "prompts"
    / "full_ai_orchestrator_shadow_planner_v1.md"
)

def load_shadow_planner_prompt() -> str:
    """Return the versioned shadow planner system prompt."""

    return _PROMPT_PATH.read_text(encoding="utf-8").strip()


def shadow_planner_prompt_version() -> str:
    """Return a stable prompt version digest for metadata and evaluation."""

    return stable_sha256_digest(load_shadow_planner_prompt(), length=16)


def _build_shadow_planner_prompt(*, workspace_summary: JSONObject) -> str:
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        else "unknown"
    )
    live_action_types = ", ".join(planner_constraints["live_action_types"]) or "none"
    source_required = (
        ", ".join(planner_constraints["source_required_action_types"]) or "none"
    )
    control_actions = (
        ", ".join(planner_constraints["control_action_types_without_source_key"])
        or "none"
    )
    source_taxonomy = planner_constraints["source_taxonomy"]
    live_evidence_sources = (
        ", ".join(_string_list(source_taxonomy.get("live_evidence"))) or "none"
    )
    context_only_sources = (
        ", ".join(_string_list(source_taxonomy.get("context_only"))) or "none"
    )
    reserved_sources = (
        ", ".join(_string_list(source_taxonomy.get("reserved"))) or "none"
    )
    grounding_sources = (
        ", ".join(_string_list(source_taxonomy.get("grounding"))) or "none"
    )
    structured_sources = (
        ", ".join(planner_constraints["structured_enrichment_source_keys"]) or "none"
    )
    checkpoint_guidance = _checkpoint_guidance_text(
        checkpoint_key=checkpoint_key,
        structured_sources=planner_constraints["structured_enrichment_source_keys"],
    )
    return (
        "Shadow-planner workspace summary follows.\n"
        "Recommend exactly one next action.\n\n"
        f"Checkpoint guidance:\n{checkpoint_guidance}\n\n"
        "Output rules:\n"
        f"- action_type must be exactly one of: {live_action_types}\n"
        f"- source_key is required only for: {source_required}\n"
        f"- source_key must be omitted for: {control_actions}\n"
        f"- Source taxonomy: live_evidence={live_evidence_sources}; "
        f"context_only={context_only_sources}; grounding={grounding_sources}; "
        f"reserved={reserved_sources}\n"
        "- qualitative_rationale must lead with qualitative assessment grounded in the "
        "workspace summary.\n"
        "- Do not use percentages, scores, probabilities, ranked-number language, or "
        "numeric confidence claims in qualitative_rationale.\n"
        f"- QUERY_PUBMED must use source_key "
        f'"{planner_constraints["pubmed_source_key"]}".\n'
        f"- INGEST_AND_EXTRACT_PUBMED must use source_key "
        f'"{planner_constraints["pubmed_source_key"]}".\n'
        f"- RUN_STRUCTURED_ENRICHMENT may use only one of: {structured_sources}\n\n"
        f"{json.dumps(workspace_summary, sort_keys=True, indent=2, default=str)}\n"
    )


def _build_shadow_planner_repair_prompt(
    *,
    workspace_summary: JSONObject,
    invalid_output: ShadowPlannerRecommendationOutput,
    validation_error: str,
) -> str:
    repair_guidance = _shadow_planner_repair_guidance(
        workspace_summary=workspace_summary,
        validation_error=validation_error,
    )
    return (
        f"{_build_shadow_planner_prompt(workspace_summary=workspace_summary)}\n"
        "The previous recommendation was rejected.\n"
        f"validation_error: {validation_error}\n"
        f"{repair_guidance}"
        "Return a corrected recommendation that keeps the same intent where possible "
        "but follows every output rule exactly.\n"
        "Rejected recommendation:\n"
        f"{json.dumps(invalid_output.model_dump(mode='json'), sort_keys=True, indent=2)}\n"
    )


def _shadow_planner_repair_guidance(
    *,
    workspace_summary: JSONObject,
    validation_error: str,
) -> str:
    checkpoint_key = (
        str(workspace_summary.get("checkpoint_key"))
        if isinstance(workspace_summary.get("checkpoint_key"), str)
        else ""
    )
    if checkpoint_key not in {"after_bootstrap", "after_chase_round_1"}:
        return ""
    if validation_error not in {
        "chase_checkpoint_action_not_allowed",
        "chase_selection_required",
        "chase_selection_label_mismatch",
        "chase_selection_too_large",
        "chase_selection_unknown_entity",
        "objective_relevant_chase_required",
    }:
        return ""
    deterministic_selection = _workspace_chase_selection(
        workspace_summary=workspace_summary,
    )
    if deterministic_selection is not None and not deterministic_selection.stop_instead:
        return (
            "Repair guidance:\n"
            "- At this chase checkpoint, return RUN_CHASE_ROUND or STOP, not GENERATE_BRIEF.\n"
            "- selected_entity_ids and selected_labels must stay inside the supplied chase_candidates.\n"
            "- Choose STOP only when the supplied candidates are weak, repetitive, or off-objective.\n"
            "- If chase_decision_posture.posture is continue_objective_relevant, return RUN_CHASE_ROUND with a bounded subset of deterministic_selection.\n"
        )
    return (
        "Repair guidance:\n"
        "- At this chase checkpoint, only RUN_CHASE_ROUND or STOP is valid.\n"
        "- If deterministic_selection.stop_instead is true, return STOP with a non-empty stop_reason.\n"
    )


def _checkpoint_guidance_text(
    *,
    checkpoint_key: str,
    structured_sources: list[str],
) -> str:
    structured_sources_text = ", ".join(structured_sources) or "none"
    guidance_map = {
        "before_first_action": (
            "- This is the opening checkpoint. If PubMed is enabled, favor "
            "QUERY_PUBMED unless the summary explicitly says grounded evidence is "
            "already present."
        ),
        "after_pubmed_discovery": (
            "- PubMed discovery has already happened, so do not treat this like the "
            "opening checkpoint.\n"
            "- If PubMed documents were discovered or selected and they have not been "
            "ingested yet, prefer INGEST_AND_EXTRACT_PUBMED before structured "
            "enrichment.\n"
            "- Do not apply objective_routing_hints to structured-source selection "
            "until PubMed ingest/extract is complete.\n"
            "- Do not choose STOP unless the summary explicitly says there are no "
            "usable documents or no meaningful live action remains."
        ),
        "after_pubmed_ingest_extract": (
            "- Literature ingest and extraction are already complete.\n"
            f"- If structured enrichment sources are enabled ({structured_sources_text}), "
            "prefer RUN_STRUCTURED_ENRICHMENT rather than STOP unless the summary "
            "explicitly says evidence is sufficient or all structured options are exhausted.\n"
            "- If you choose RUN_STRUCTURED_ENRICHMENT, start from "
            "planner_constraints.pending_structured_enrichment_source_keys, then use "
            "objective_routing_hints.preferred_pending_structured_sources to choose "
            "a later source only when the workspace summary gives a stronger "
            "qualitative reason."
        ),
        "after_driven_terms_ready": (
            "- Driven terms are ready, so the workflow should usually broaden coverage "
            "through one enabled structured source before stopping.\n"
            "- When several structured sources are still pending, use the deterministic "
            "pending-source order as the default, but prefer the objective_routing_hints "
            "ordering when the objective clearly points to a better source family."
        ),
        "after_bootstrap": (
            "- Bootstrap has completed.\n"
            "- At this checkpoint, the only valid action types are RUN_CHASE_ROUND and STOP.\n"
            "- Treat chase_decision_posture as the backend-derived qualitative guardrail for this checkpoint.\n"
            "- If chase_decision_posture.posture is continue_objective_relevant, choose RUN_CHASE_ROUND with a bounded subset of deterministic_selection.\n"
            "- If chase_decision_posture.posture is stop_threshold_not_met, choose STOP with a clear stop_reason.\n"
            "- If deterministic_threshold_met is true, treat that only as permission to continue, "
            "not as a command to continue.\n"
            "- Prefer STOP when the supplied chase_candidates are weak, repetitive, off-objective, "
            "or mostly broaden away from the objective.\n"
            "- Prefer one bounded RUN_CHASE_ROUND when deterministic_threshold_met is true, "
            "deterministic_selection.stop_instead is false, and deterministic selected labels "
            "directly match the objective terms, disease area, mechanism, therapy, or model-organism focus.\n"
            "- Do not use synthesis_readiness.ready_for_brief by itself as a stop signal when "
            "the candidate set is still objective-relevant and bounded.\n"
            "- If you choose RUN_CHASE_ROUND, keep the selection inside the supplied chase_candidates.\n"
            "- If the workspace summary already shows the threshold was not met, prefer STOP with "
            'stop_reason="threshold_not_met".\n'
            "- If synthesis_readiness.ready_for_brief is true and the candidate set is weak, repetitive, "
            "or off-objective, fold that readiness into a STOP rationale instead of switching to GENERATE_BRIEF."
        ),
        "after_chase_round_1": (
            "- One chase round has completed.\n"
            "- At this checkpoint, the only valid action types are RUN_CHASE_ROUND and STOP.\n"
            "- Treat chase_decision_posture as the backend-derived qualitative guardrail for this checkpoint.\n"
            "- If chase_decision_posture.posture is continue_objective_relevant, choose RUN_CHASE_ROUND with a bounded subset of deterministic_selection.\n"
            "- If chase_decision_posture.posture is stop_threshold_not_met, choose STOP with a clear stop_reason.\n"
            "- If the workspace summary says the chase threshold was not met, prefer STOP with "
            'stop_reason="threshold_not_met".\n'
            "- If the remaining chase_candidates are weak, repetitive, off-objective, or mostly "
            "broaden away from the objective, prefer STOP even when the deterministic threshold is met.\n"
            "- If deterministic_threshold_met is true, deterministic_selection.stop_instead is false, "
            "and the remaining selected labels directly match the objective, prefer a bounded RUN_CHASE_ROUND.\n"
            "- Do not use synthesis_readiness.ready_for_brief by itself as a stop signal when "
            "the candidate set is still objective-relevant and bounded.\n"
            "- Otherwise, use a bounded RUN_CHASE_ROUND only for candidates that are clearly "
            "worth chasing next."
        ),
        "after_chase_round_2": (
            "- The bounded chase rounds are exhausted. Prefer GENERATE_BRIEF over "
            "opening more retrieval."
        ),
        "before_brief_generation": (
            "- The workflow is at the synthesis boundary. If evidence has already "
            "been gathered, prefer GENERATE_BRIEF rather than STOP."
        ),
        "before_terminal_stop": (
            "- The workflow is already at the terminal checkpoint. Prefer STOP "
            "unless the summary explicitly identifies an unresolved blocker that "
            "requires escalation."
        ),
    }
    return guidance_map.get(
        checkpoint_key,
        "- Use the checkpoint name and workspace summary to choose the single best next bounded action.",
    )


