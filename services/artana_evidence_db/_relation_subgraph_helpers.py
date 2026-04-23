"""Helpers for relation subgraph selection/materialization."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Literal

from artana_evidence_db.kernel_domain_models import KernelRelation
from artana_evidence_db.kernel_services import (
    KernelEntityService,
    KernelRelationService,
)
from artana_evidence_db.service_contracts import (
    KernelEntityResponse,
    KernelGraphDocumentRequest,
    KernelGraphSubgraphRequest,
)

_CURATION_STATUS_PRIORITY: dict[str, int] = {
    "APPROVED": 5,
    "UNDER_REVIEW": 4,
    "DRAFT": 3,
    "REJECTED": 2,
    "RETRACTED": 1,
}
_STARTER_FETCH_MULTIPLIER = 6
type GraphRelationRequest = KernelGraphSubgraphRequest | KernelGraphDocumentRequest


def _status_priority(status: str) -> int:
    return _CURATION_STATUS_PRIORITY.get(status.strip().upper(), 0)


def sort_relations_for_subgraph(
    relations: Iterable[KernelRelation],
) -> list[KernelRelation]:
    return sorted(
        relations,
        key=lambda relation: (
            _status_priority(str(relation.curation_status)),
            relation.updated_at,
        ),
        reverse=True,
    )


def filter_relations(
    relations: Iterable[KernelRelation],
    *,
    relation_types: set[str] | None,
    curation_statuses: set[str] | None,
) -> list[KernelRelation]:
    filtered: list[KernelRelation] = []
    for relation in relations:
        relation_type_normalized = str(relation.relation_type).strip().upper()
        curation_status_normalized = str(relation.curation_status).strip().upper()
        if (
            relation_types is not None
            and relation_type_normalized not in relation_types
        ):
            continue
        if (
            curation_statuses is not None
            and curation_status_normalized not in curation_statuses
        ):
            continue
        filtered.append(relation)
    return filtered


def ordered_node_ids_for_relations(
    relations: Iterable[KernelRelation],
    *,
    seed_entity_ids: list[str],
) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for seed_id in seed_entity_ids:
        if seed_id not in seen:
            seen.add(seed_id)
            ordered.append(seed_id)
    for relation in relations:
        for entity_id in (str(relation.source_id), str(relation.target_id)):
            if entity_id in seen:
                continue
            seen.add(entity_id)
            ordered.append(entity_id)
    return ordered


def _resolve_anchor_node_id_for_component(
    *,
    relations: list[KernelRelation],
    preferred_seed_entity_ids: list[str],
) -> str:
    relation_node_ids: set[str] = set()
    for relation in relations:
        relation_node_ids.add(str(relation.source_id))
        relation_node_ids.add(str(relation.target_id))

    for seed_entity_id in preferred_seed_entity_ids:
        if seed_entity_id in relation_node_ids:
            return seed_entity_id

    return str(relations[0].source_id)


def _collect_connected_component_node_ids(
    *,
    relations: list[KernelRelation],
    anchor_node_id: str,
) -> set[str]:
    adjacency: dict[str, set[str]] = {}
    for relation in relations:
        source_id = str(relation.source_id)
        target_id = str(relation.target_id)
        adjacency.setdefault(source_id, set()).add(target_id)
        adjacency.setdefault(target_id, set()).add(source_id)

    if anchor_node_id not in adjacency:
        return set()

    connected_node_ids: set[str] = set()
    queue: deque[str] = deque([anchor_node_id])
    while queue:
        node_id = queue.popleft()
        if node_id in connected_node_ids:
            continue
        connected_node_ids.add(node_id)
        for neighbor_id in adjacency.get(node_id, set()):
            if neighbor_id not in connected_node_ids:
                queue.append(neighbor_id)
    return connected_node_ids


def limit_relations_to_anchor_component(
    *,
    relations: list[KernelRelation],
    preferred_seed_entity_ids: list[str],
) -> list[KernelRelation]:
    if len(relations) <= 1:
        return relations
    anchor_node_id = _resolve_anchor_node_id_for_component(
        relations=relations,
        preferred_seed_entity_ids=preferred_seed_entity_ids,
    )
    connected_node_ids = _collect_connected_component_node_ids(
        relations=relations,
        anchor_node_id=anchor_node_id,
    )
    if not connected_node_ids:
        return relations
    return [
        relation
        for relation in relations
        if str(relation.source_id) in connected_node_ids
        and str(relation.target_id) in connected_node_ids
    ]


def collect_candidate_relations(
    *,
    mode: Literal["starter", "seeded"],
    space_id: str,
    request: GraphRelationRequest,
    relation_service: KernelRelationService,
    relation_types: set[str] | None,
    curation_statuses: set[str] | None,
) -> list[KernelRelation]:
    if mode == "starter":
        fetch_limit = max(
            request.max_edges * _STARTER_FETCH_MULTIPLIER,
            request.top_k * _STARTER_FETCH_MULTIPLIER,
            200,
        )
        relations = relation_service.list_by_research_space(
            space_id,
            limit=fetch_limit,
            offset=0,
        )
        filtered = filter_relations(
            relations,
            relation_types=relation_types,
            curation_statuses=curation_statuses,
        )
        return sort_relations_for_subgraph(filtered)

    deduped: dict[str, KernelRelation] = {}
    for seed_entity_id in request.seed_entity_ids:
        seed_relations = relation_service.get_neighborhood_in_space(
            space_id,
            str(seed_entity_id),
            depth=request.depth,
            relation_types=list(relation_types) if relation_types is not None else None,
            limit=request.top_k,
        )
        filtered_seed_relations = filter_relations(
            seed_relations,
            relation_types=relation_types,
            curation_statuses=curation_statuses,
        )
        for relation in sort_relations_for_subgraph(filtered_seed_relations)[
            : request.top_k
        ]:
            deduped[str(relation.id)] = relation
    return sort_relations_for_subgraph(deduped.values())


def materialize_nodes(
    *,
    entity_ids: list[str],
    space_id: str,
    entity_service: KernelEntityService,
) -> list[KernelEntityResponse]:
    nodes: list[KernelEntityResponse] = []
    for entity_id in entity_ids:
        entity = entity_service.get_entity(entity_id)
        if entity is None:
            continue
        if str(entity.research_space_id) != space_id:
            continue
        nodes.append(KernelEntityResponse.from_model(entity))
    return nodes
