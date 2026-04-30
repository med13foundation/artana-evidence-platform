"""Action registry and source gating for the full-AI orchestrator."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.runtime_constants import (
    _HARNESS_ID,
    _STEP_KEY_VERSION,
    _STRUCTURED_ENRICHMENT_SOURCES,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionSpec,
    ResearchOrchestratorActionType,
)
from artana_evidence_api.types.common import ResearchSpaceSourcePreferences

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


def orchestrator_action_registry() -> tuple[ResearchOrchestratorActionSpec, ...]:
    """Return the allowlisted Phase 1 action registry."""
    return _ACTION_REGISTRY


def is_source_action(action_type: ResearchOrchestratorActionType) -> bool:
    """Return whether an orchestrator action is source-bound."""
    return action_type in _SOURCE_ACTIONS


def is_control_action(action_type: ResearchOrchestratorActionType) -> bool:
    """Return whether an orchestrator action is pure control flow."""
    return action_type in _CONTROL_ACTIONS


def require_action_enabled_for_sources(
    *,
    action_type: ResearchOrchestratorActionType,
    source_key: str | None,
    sources: ResearchSpaceSourcePreferences,
) -> None:
    """Raise when a source-bound action targets a disabled source."""
    if not is_source_action(action_type):
        return
    resolved_source_key = (
        source_key
        if source_key is not None
        else _ACTION_SPEC_BY_TYPE[action_type].default_source_key
    )
    if resolved_source_key is None:
        return
    if sources.get(resolved_source_key, False):
        return
    msg = (
        f"Action '{action_type.value}' is unavailable because source "
        f"'{resolved_source_key}' is disabled."
    )
    raise ValueError(msg)


def build_step_key(
    *,
    action_type: ResearchOrchestratorActionType,
    round_number: int,
    source_key: str | None = None,
) -> str:
    """Return the stable step key for one deterministic action."""
    normalized_action = action_type.value.casefold()
    source_segment = source_key if source_key is not None else "control"
    return (
        f"{_HARNESS_ID}.{_STEP_KEY_VERSION}.round_{round_number}."
        f"{source_segment}.{normalized_action}"
    )


__all__ = [
    "_ACTION_REGISTRY",
    "_ACTION_SPEC_BY_TYPE",
    "_CONTROL_ACTIONS",
    "_SOURCE_ACTIONS",
    "_STRUCTURED_ENRICHMENT_SOURCES",
    "build_step_key",
    "is_control_action",
    "is_source_action",
    "orchestrator_action_registry",
    "require_action_enabled_for_sources",
]
