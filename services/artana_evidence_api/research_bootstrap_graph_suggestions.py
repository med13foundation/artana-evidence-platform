"""Research-bootstrap graph relation suggestion helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphConnectionContract,
    ProposedRelation,
)
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionResult,
)
from artana_evidence_api.research_bootstrap_candidates import _normalized_unique_strings
from artana_evidence_api.types.graph_contracts import (
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionRequest,
)
from artana_evidence_api.types.graph_fact_assessment import (
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    build_fact_assessment_from_confidence,
)

if TYPE_CHECKING:
    from artana_evidence_api.graph_client import GraphTransportBundle

_GRAPH_CONNECTION_TIMEOUT_SECONDS = 45.0

def _graph_connection_timeout_contract(
    *,
    request: HarnessGraphConnectionRequest,
    source_type: str,
) -> GraphConnectionContract:
    return GraphConnectionContract(
        decision="fallback",
        confidence_score=0.0,
        rationale=("Graph connection timed out before relation discovery completed."),
        evidence=[
            EvidenceItem(
                source_type="note",
                locator=f"graph-connection-timeout:{request.seed_entity_id}",
                excerpt=(
                    "Graph connection timed out after "
                    f"{int(_GRAPH_CONNECTION_TIMEOUT_SECONDS)} seconds."
                ),
                relevance=0.2,
            ),
        ],
        source_type=source_type,
        research_space_id=request.research_space_id,
        seed_entity_id=request.seed_entity_id,
        proposed_relations=[],
        rejected_candidates=[],
        shadow_mode=request.shadow_mode,
        agent_run_id=None,
    )


def _graph_suggestion_label_map(
    *,
    graph_api_gateway: GraphTransportBundle,
    space_id: UUID,
    entity_ids: list[str],
) -> dict[str, str]:
    if not entity_ids:
        return {}
    try:
        entities = graph_api_gateway.list_entities(
            space_id=space_id,
            ids=entity_ids,
            limit=max(len(entity_ids), 50),
        )
    except GraphServiceClientError:
        return {}
    return {
        str(entity.id): (
            entity.display_label.strip()
            if isinstance(entity.display_label, str) and entity.display_label.strip()
            else str(entity.id)
        )
        for entity in entities.entities
    }


def _build_graph_connection_result_from_suggestions(
    *,
    request: HarnessGraphConnectionRequest,
    suggestion_response: KernelRelationSuggestionListResponse,
    label_map: dict[str, str],
) -> HarnessGraphConnectionResult:
    seed_entity_id = request.seed_entity_id
    seed_label = label_map.get(seed_entity_id, seed_entity_id)
    if suggestion_response.suggestions:
        proposed_relations = [
            ProposedRelation(
                source_id=str(suggestion.source_entity_id),
                relation_type=suggestion.relation_type,
                target_id=str(suggestion.target_entity_id),
                assessment=build_fact_assessment_from_confidence(
                    confidence=float(suggestion.final_score),
                    confidence_rationale=(
                        "Deterministic bootstrap suggestion from current graph structure."
                    ),
                    grounding_level=GroundingLevel.GRAPH_INFERENCE,
                    mapping_status=MappingStatus.NOT_APPLICABLE,
                    speculation_level=SpeculationLevel.NOT_APPLICABLE,
                ),
                evidence_summary=(
                    f"Graph bootstrap suggests {seed_label} "
                    f"{suggestion.relation_type} "
                    f"{label_map.get(str(suggestion.target_entity_id), str(suggestion.target_entity_id))}."
                ),
                supporting_provenance_ids=[],
                supporting_document_count=0,
                reasoning=(
                    "Deterministic bootstrap relation candidate derived from graph "
                    "structure, neighborhood overlap, and dictionary relation fit."
                ),
            )
            for suggestion in suggestion_response.suggestions
        ]
        contract = GraphConnectionContract(
            decision="generated",
            confidence_score=max(
                relation.confidence for relation in proposed_relations
            ),
            rationale=(
                "Generated graph-connection candidates from deterministic relation "
                "suggestions."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-suggestions:{seed_entity_id}",
                    excerpt=(
                        "Graph service returned "
                        f"{len(proposed_relations)} deterministic relation suggestion(s)."
                    ),
                    relevance=0.6,
                ),
            ],
            source_type=request.source_type or "pubmed",
            research_space_id=request.research_space_id,
            seed_entity_id=seed_entity_id,
            proposed_relations=proposed_relations,
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id=None,
        )
        return HarnessGraphConnectionResult(
            contract=contract,
            agent_run_id=None,
            active_skill_names=(),
        )

    matching_skip = next(
        (
            skipped
            for skipped in suggestion_response.skipped_sources
            if str(skipped.entity_id) == seed_entity_id
        ),
        None,
    )
    if matching_skip is not None:
        if matching_skip.reason == "constraint_config_missing":
            rationale = (
                "Graph relation suggestions were skipped because no active "
                "dictionary constraints are configured for this seed entity type."
            )
            excerpt = (
                f"Skipped relation suggestions for {seed_label}: "
                "constraint_config_missing."
            )
        else:
            rationale = (
                "Graph relation suggestions were skipped because the source entity "
                f"embedding is {matching_skip.state}."
            )
            excerpt = (
                f"Skipped relation suggestions for {seed_label}: "
                f"{matching_skip.reason} ({matching_skip.state})."
            )
    else:
        rationale = "Graph relation suggestions returned no safe candidates."
        excerpt = (
            f"No deterministic relation suggestions were returned for {seed_label}."
        )
    contract = GraphConnectionContract(
        decision="fallback",
        confidence_score=0.0,
        rationale=rationale,
        evidence=[
            EvidenceItem(
                source_type="note",
                locator=f"graph-suggestions:{seed_entity_id}",
                excerpt=excerpt,
                relevance=0.2,
            ),
        ],
        source_type=request.source_type or "pubmed",
        research_space_id=request.research_space_id,
        seed_entity_id=seed_entity_id,
        proposed_relations=[],
        rejected_candidates=[],
        shadow_mode=request.shadow_mode,
        agent_run_id=None,
    )
    return HarnessGraphConnectionResult(
        contract=contract,
        agent_run_id=None,
        active_skill_names=(),
    )


def _run_bootstrap_graph_suggestions(
    *,
    graph_api_gateway: GraphTransportBundle,
    space_id: UUID,
    request: HarnessGraphConnectionRequest,
    relation_types: list[str] | None,
    max_candidates: int,
) -> HarnessGraphConnectionResult | None:
    if not hasattr(graph_api_gateway, "suggest_relations"):
        return None
    normalized_relation_types = relation_types if relation_types else None
    try:
        suggestion_response = graph_api_gateway.suggest_relations(
            space_id=space_id,
            request=KernelRelationSuggestionRequest(
                source_entity_ids=[UUID(request.seed_entity_id)],
                limit_per_source=max(1, min(max_candidates, 10)),
                min_score=0.7,
                allowed_relation_types=normalized_relation_types,
                target_entity_types=None,
                exclude_existing_relations=True,
                require_all_ready=False,
            ),
        )
    except GraphServiceClientError:
        return None
    related_entity_ids = _normalized_unique_strings(
        [
            request.seed_entity_id,
            *[
                str(suggestion.target_entity_id)
                for suggestion in suggestion_response.suggestions
            ],
        ],
    )
    label_map = (
        _graph_suggestion_label_map(
            graph_api_gateway=graph_api_gateway,
            space_id=space_id,
            entity_ids=related_entity_ids,
        )
        if hasattr(graph_api_gateway, "list_entities")
        else {}
    )
    return _build_graph_connection_result_from_suggestions(
        request=request,
        suggestion_response=suggestion_response,
        label_map=label_map,
    )




__all__ = ["_graph_connection_timeout_contract", "_run_bootstrap_graph_suggestions"]
