"""Initial decision history helpers for the full AI orchestrator."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator_common_support import (
    _STRUCTURED_ENRICHMENT_SOURCES,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    ResearchOrchestratorActionType,
    ResearchOrchestratorDecision,
)
from artana_evidence_api.full_ai_orchestrator_response_support import _build_decision
from artana_evidence_api.types.common import (
    ResearchSpaceSourcePreferences,
    json_object_or_empty,
)


def _build_initial_decision_history(  # noqa: PLR0913
    *,
    objective: str,
    seed_terms: list[str],
    max_depth: int,
    max_hypotheses: int,
    sources: ResearchSpaceSourcePreferences,
) -> list[ResearchOrchestratorDecision]:
    decisions: list[ResearchOrchestratorDecision] = [
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
    ]
    pubmed_enabled = sources.get("pubmed", True)
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
            round_number=0,
            source_key="pubmed",
            action_input={"seed_terms": list(seed_terms)},
            evidence_basis="Deterministic Phase 1 baseline will run PubMed discovery before structured enrichment.",
            status="pending" if pubmed_enabled else "skipped",
            stop_reason=None if pubmed_enabled else "source_disabled",
            metadata={"planned": True},
        ),
    )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
            round_number=0,
            source_key="pubmed",
            action_input={"max_hypotheses": max_hypotheses},
            evidence_basis="Deterministic Phase 1 baseline will ingest selected PubMed records and extract proposals.",
            status="pending" if pubmed_enabled else "skipped",
            stop_reason=None if pubmed_enabled else "source_disabled",
            metadata={"planned": True},
        ),
    )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.DERIVE_DRIVEN_TERMS,
            round_number=0,
            action_input={"seed_terms": list(seed_terms)},
            evidence_basis="Driven terms are deterministically derived after the PubMed-backed phase.",
            status="pending",
            metadata={"planned": True},
        ),
    )
    for source_key in _STRUCTURED_ENRICHMENT_SOURCES:
        if not sources.get(source_key, False):
            continue
        decisions.append(
            _build_decision(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                round_number=0,
                source_key=source_key,
                action_input={"source_key": source_key},
                evidence_basis="Structured enrichment for enabled sources follows the deterministic source handlers.",
                status="pending",
                metadata={"planned": True},
            ),
        )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
            round_number=0,
            action_input={"max_depth": max_depth},
            evidence_basis="The deterministic baseline queues governed bootstrap after source enrichment.",
            status="pending",
            metadata={"planned": True},
        ),
    )
    decisions.extend(
        _build_decision(
            action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
            round_number=chase_round,
            action_input={"round_number": chase_round},
            evidence_basis="The deterministic baseline can execute up to two chase rounds using existing thresholds.",
            status="pending",
            metadata={"planned": True},
        )
        for chase_round in range(1, min(max_depth, 2) + 1)
    )
    decisions.append(
        _build_decision(
            action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
            round_number=0,
            action_input={"result_key": "research_brief"},
            evidence_basis="The deterministic baseline ends by generating and storing the research brief.",
            status="pending",
            metadata={"planned": True},
        ),
    )
    return decisions

__all__ = ["_build_initial_decision_history"]
