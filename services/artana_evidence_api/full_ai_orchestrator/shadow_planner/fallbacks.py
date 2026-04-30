"""Fallback recommendation construction for the full-AI shadow planner."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.shadow_planner.models import (
    ShadowPlannerRecommendationOutput,
    _PlannerConstraintsSummary,
)
from artana_evidence_api.full_ai_orchestrator.shadow_planner.workspace import (
    _preferred_structured_enrichment_source_from_workspace,
    _structured_enrichment_source_keys,
    _workspace_chase_selection,
    _workspace_planner_constraints,
    planner_live_action_types,
    shadow_planner_synthesis_readiness,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
)
from artana_evidence_api.types.common import JSONObject, ResearchSpaceSourcePreferences


def _checkpoint_fallback_output(
    *,
    checkpoint_key: str,
    live_types: frozenset[ResearchOrchestratorActionType],
    planner_constraints: _PlannerConstraintsSummary,
    sources: ResearchSpaceSourcePreferences,
    structured_enrichment_sources: list[str],
    workspace_summary: JSONObject,
) -> dict[str, object] | None:
    output_kwargs: dict[str, object] | None = None
    synthesis_readiness = shadow_planner_synthesis_readiness(
        workspace_summary=workspace_summary,
    )
    preferred_structured_source = (
        _preferred_structured_enrichment_source_from_workspace(
            workspace_summary=workspace_summary,
            structured_enrichment_sources=structured_enrichment_sources,
        )
    )
    deterministic_chase_selection = _workspace_chase_selection(
        workspace_summary=workspace_summary,
    )
    if checkpoint_key == "before_terminal_stop":
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.STOP,
            "source_key": None,
            "evidence_basis": "The run is at the terminal checkpoint in shadow mode.",
            "qualitative_rationale": (
                "Stop because the deterministic workflow has already reached its final "
                "terminal checkpoint."
            ),
            "expected_value_band": "low",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "none",
                "basis": "terminal_checkpoint",
            },
            "stop_reason": "terminal_checkpoint",
            "fallback_reason": "openai_api_key_not_configured",
        }
    elif checkpoint_key == "before_brief_generation":
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.GENERATE_BRIEF,
            "source_key": None,
            "evidence_basis": (
                "The run is at the final synthesis checkpoint in shadow mode."
            ),
            "qualitative_rationale": (
                "Generate the brief because the deterministic workflow has already "
                "gathered evidence and reached the final synthesis boundary."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "brief_checkpoint",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    elif (
        checkpoint_key == "after_pubmed_discovery"
        and ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED in live_types
        and sources.get("pubmed", False)
        and planner_constraints["pubmed_ingest_pending"]
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
            "source_key": "pubmed",
            "evidence_basis": (
                "PubMed discovery has already surfaced grounded literature, but the "
                "documents have not been ingested and extracted yet."
            ),
            "qualitative_rationale": (
                "Ingest and extract the PubMed papers now because the run already "
                "found grounded literature and should turn that discovery step into "
                "usable evidence before branching into structured follow-up."
            ),
            "expected_value_band": "high",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "pubmed_ingest_after_discovery",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    elif (
        checkpoint_key in {"after_pubmed_ingest_extract", "after_driven_terms_ready"}
        and ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT in live_types
        and preferred_structured_source is not None
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
            "source_key": preferred_structured_source,
            "evidence_basis": (
                "PubMed ingest and extraction have already completed, so the next "
                "step is to broaden coverage through the strongest still-pending "
                "structured source for this objective."
            ),
            "qualitative_rationale": (
                f"Use {preferred_structured_source} structured enrichment now because "
                "the literature pass is already grounded and the workspace summary "
                "indicates that this source is the best remaining qualitative fit "
                "for the current research objective."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "post_pubmed_structured_enrichment",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    if (
        output_kwargs is None
        and checkpoint_key in {"after_bootstrap", "after_chase_round_1"}
        and ResearchOrchestratorActionType.STOP in live_types
        and (
            (
                deterministic_chase_selection is not None
                and deterministic_chase_selection.stop_instead
            )
            or (
                deterministic_chase_selection is None
                and synthesis_readiness["ready_for_brief"]
            )
        )
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.STOP,
            "source_key": None,
            "evidence_basis": (
                synthesis_readiness["summary"]
                if deterministic_chase_selection is None
                else (
                    "The deterministic chase candidate set does not clear the "
                    "bounded threshold for another chase round."
                )
            ),
            "qualitative_rationale": (
                "Stop here because the run is already synthesis-ready and the chase "
                "checkpoint does not justify another bounded retrieval step."
                if deterministic_chase_selection is None
                else (
                    "Stop here because the available chase candidates are too weak "
                    "or too few to justify another bounded chase round."
                )
            ),
            "expected_value_band": "low",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "none",
                "basis": (
                    "synthesis_ready_no_chase_selection"
                    if deterministic_chase_selection is None
                    else "threshold_not_met"
                ),
            },
            "stop_reason": (
                "synthesis_ready"
                if deterministic_chase_selection is None
                else "threshold_not_met"
            ),
            "fallback_reason": "openai_api_key_not_configured",
        }
    if (
        output_kwargs is None
        and checkpoint_key in {"after_bootstrap", "after_chase_round_1"}
        and ResearchOrchestratorActionType.RUN_CHASE_ROUND in live_types
        and deterministic_chase_selection is not None
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.RUN_CHASE_ROUND,
            "source_key": None,
            "evidence_basis": (
                "The bounded chase candidate set already clears the deterministic "
                "threshold for another chase round."
            ),
            "qualitative_rationale": (
                "Continue with a bounded chase round because the workspace already "
                "contains specific newly surfaced entities that are worth testing as "
                "the next discovery step."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "single_chase_round",
            },
            "selected_entity_ids": list(
                deterministic_chase_selection.selected_entity_ids,
            ),
            "selected_labels": list(deterministic_chase_selection.selected_labels),
            "selection_basis": deterministic_chase_selection.selection_basis,
            "fallback_reason": "openai_api_key_not_configured",
        }
    if (
        output_kwargs is None
        and checkpoint_key == "after_chase_round_2"
        and ResearchOrchestratorActionType.GENERATE_BRIEF in live_types
    ):
        output_kwargs = {
            "action_type": ResearchOrchestratorActionType.GENERATE_BRIEF,
            "source_key": None,
            "evidence_basis": (
                "Two chase rounds have already been attempted, so the next bounded "
                "step is synthesis."
            ),
            "qualitative_rationale": (
                "Move to brief generation because the bounded chase budget has been "
                "used and the workflow should now synthesize what it has learned."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "post_chase_brief",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    return output_kwargs


def _default_fallback_output(
    *,
    live_types: frozenset[ResearchOrchestratorActionType],
    sources: ResearchSpaceSourcePreferences,
    structured_enrichment_sources: list[str],
) -> dict[str, object]:
    preferred_structured_source = (
        structured_enrichment_sources[0] if structured_enrichment_sources else None
    )
    if ResearchOrchestratorActionType.QUERY_PUBMED in live_types and sources.get(
        "pubmed", False
    ):
        return {
            "action_type": ResearchOrchestratorActionType.QUERY_PUBMED,
            "source_key": "pubmed",
            "evidence_basis": (
                "PubMed discovery is the deterministic first evidence-gathering step."
            ),
            "qualitative_rationale": (
                "Start with literature discovery to ground the run in retrieved "
                "evidence before deciding which structured sources deserve follow-up."
            ),
            "expected_value_band": "high",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "single_source_query",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    if (
        ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT in live_types
        and preferred_structured_source is not None
    ):
        return {
            "action_type": ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
            "source_key": preferred_structured_source,
            "evidence_basis": (
                "A structured source is enabled, so the planner can still gather "
                "grounded records without free-form action selection."
            ),
            "qualitative_rationale": (
                f"Move to {preferred_structured_source} to broaden evidence coverage "
                "while the deterministic baseline remains in control."
            ),
            "expected_value_band": "medium",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "single_source_enrichment",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    if ResearchOrchestratorActionType.GENERATE_BRIEF in live_types:
        return {
            "action_type": ResearchOrchestratorActionType.GENERATE_BRIEF,
            "source_key": None,
            "evidence_basis": (
                "The available shadow-mode action set contains no usable source step."
            ),
            "qualitative_rationale": (
                "Move toward brief generation because the planner cannot open a "
                "grounded source step from the current live action set."
            ),
            "expected_value_band": "low",
            "risk_level": "low",
            "requires_approval": False,
            "budget_estimate": {
                "relative_size": "small",
                "basis": "brief_only",
            },
            "fallback_reason": "openai_api_key_not_configured",
        }
    return {
        "action_type": ResearchOrchestratorActionType.STOP,
        "source_key": None,
        "evidence_basis": (
            "No enabled or planner-selectable sources are available for the run."
        ),
        "qualitative_rationale": (
            "Stop because there is no live action capable of adding grounded evidence."
        ),
        "expected_value_band": "low",
        "risk_level": "low",
        "requires_approval": False,
        "budget_estimate": {
            "relative_size": "none",
            "basis": "no_live_actions",
        },
        "stop_reason": "no_live_actions",
        "fallback_reason": "openai_api_key_not_configured",
    }


def _build_fallback_output(
    *,
    checkpoint_key: str,
    workspace_summary: JSONObject,
    sources: ResearchSpaceSourcePreferences,
    action_registry: tuple[ResearchOrchestratorActionSpec, ...],
) -> ShadowPlannerRecommendationOutput:
    live_types = planner_live_action_types(action_registry=action_registry)
    planner_constraints = _workspace_planner_constraints(
        workspace_summary=workspace_summary,
    )
    structured_enrichment_sources = _structured_enrichment_source_keys(
        enabled_sources={
            key: value for key, value in sources.items() if isinstance(value, bool)
        },
    )
    output_kwargs = _checkpoint_fallback_output(
        checkpoint_key=checkpoint_key,
        live_types=live_types,
        planner_constraints=planner_constraints,
        sources=sources,
        structured_enrichment_sources=structured_enrichment_sources,
        workspace_summary=workspace_summary,
    )
    if output_kwargs is None:
        output_kwargs = _default_fallback_output(
            live_types=live_types,
            sources=sources,
            structured_enrichment_sources=structured_enrichment_sources,
        )
    return ShadowPlannerRecommendationOutput.model_validate(output_kwargs)
