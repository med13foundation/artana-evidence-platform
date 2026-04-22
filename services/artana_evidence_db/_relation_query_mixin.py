"""Read/query mixin for service-local relation repositories."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db._relation_repository_shared import _as_uuid
from artana_evidence_db.graph_core_models import (
    KernelMechanisticGap,
    KernelReachabilityGap,
    KernelRelation,
)
from artana_evidence_db.kernel_claim_models import (
    RelationClaimModel,
    RelationProjectionSourceModel,
)
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.kernel_relation_models import (
    RelationEvidenceModel,
    RelationModel,
)
from artana_evidence_db.read_models import EntityNeighborModel
from sqlalchemy import String, and_, func, or_, select
from sqlalchemy.orm import aliased

if TYPE_CHECKING:
    from artana_evidence_db.relation_repository import (
        SqlAlchemyKernelRelationRepository,
    )
    from sqlalchemy.sql import Select
    from sqlalchemy.sql.elements import ColumnElement


class _KernelRelationQueryMixin:
    """Read and graph-traversal query helpers."""

    _HIGH_CONFIDENCE_THRESHOLD = 0.8
    _MEDIUM_CONFIDENCE_THRESHOLD = 0.6

    def get_by_id(
        self: SqlAlchemyKernelRelationRepository,
        relation_id: str,
        *,
        claim_backed_only: bool = True,
    ) -> KernelRelation | None:
        stmt = select(RelationModel).where(RelationModel.id == _as_uuid(relation_id))
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        model = self._session.scalars(stmt.limit(1)).first()
        return KernelRelation.model_validate(model) if model is not None else None

    def find_by_triple(
        self: SqlAlchemyKernelRelationRepository,
        *,
        research_space_id: str,
        source_id: str,
        relation_type: str,
        target_id: str,
        canonicalization_fingerprint: str = "",
        claim_backed_only: bool = True,
    ) -> KernelRelation | None:
        stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
            RelationModel.source_id == _as_uuid(source_id),
            RelationModel.relation_type == relation_type,
            RelationModel.target_id == _as_uuid(target_id),
            RelationModel.canonicalization_fingerprint == canonicalization_fingerprint,
        )
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        model = self._session.scalars(stmt.limit(1)).first()
        return KernelRelation.model_validate(model) if model is not None else None

    def find_by_source(
        self: SqlAlchemyKernelRelationRepository,
        source_id: str,
        *,
        relation_type: str | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.source_id == _as_uuid(source_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_target(
        self: SqlAlchemyKernelRelationRepository,
        target_id: str,
        *,
        relation_type: str | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = select(RelationModel).where(
            RelationModel.target_id == _as_uuid(target_id),
        )
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_neighborhood(  # noqa: C901
        self: SqlAlchemyKernelRelationRepository,
        entity_id: str,
        *,
        depth: int = 1,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
    ) -> list[KernelRelation]:
        if depth == 1 and claim_backed_only:
            indexed_relations = self._find_neighborhood_from_read_model(
                entity_id=entity_id,
                relation_types=relation_types,
                limit=limit,
            )
            if indexed_relations:
                return indexed_relations

        visited_ids: set[UUID] = set()
        frontier: set[UUID] = {_as_uuid(entity_id)}
        all_relations: list[RelationModel] = []

        for _hop in range(depth):
            if not frontier:
                break

            stmt = select(RelationModel).where(
                or_(
                    RelationModel.source_id.in_(frontier),
                    RelationModel.target_id.in_(frontier),
                ),
            )
            if relation_types:
                stmt = stmt.where(RelationModel.relation_type.in_(relation_types))
            if claim_backed_only:
                stmt = stmt.where(self._active_support_projection_exists())

            hop_relations = list(self._session.scalars(stmt).all())
            all_relations.extend(hop_relations)

            visited_ids |= frontier
            next_frontier: set[UUID] = set()
            for relation in hop_relations:
                source_uuid = _as_uuid(relation.source_id)
                target_uuid = _as_uuid(relation.target_id)
                if source_uuid not in visited_ids:
                    next_frontier.add(source_uuid)
                if target_uuid not in visited_ids:
                    next_frontier.add(target_uuid)
            frontier = next_frontier

        seen: set[str] = set()
        unique: list[RelationModel] = []
        for relation in all_relations:
            relation_id = str(relation.id)
            if relation_id not in seen:
                seen.add(relation_id)
                unique.append(relation)
        unique.sort(key=lambda relation: relation.updated_at, reverse=True)
        if limit is not None:
            unique = unique[: max(limit, 1)]
        return [KernelRelation.model_validate(model) for model in unique]

    def find_reachability_gaps(
        self: SqlAlchemyKernelRelationRepository,
        seed_entity_id: str,
        *,
        max_path_length: int = 2,
        relation_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelReachabilityGap]:
        """Find entities reachable from ``seed`` via multi-hop paths but with no direct edge.

        Phase 4 Tier 4 query: structurally implied connections that have no
        direct evidence in the canonical relation graph.  Useful for surfacing
        "you should probably add this direct relation" candidates.

        Bounds: ``max_path_length`` must be 2-5 inclusive.  Length 1 is
        rejected because a 1-hop "gap" is a contradiction (any reachable
        entity at depth 1 has a direct edge by definition).
        """
        if max_path_length < 2 or max_path_length > 5:
            msg = "max_path_length must be between 2 and 5 inclusive"
            raise ValueError(msg)

        seed_uuid = _as_uuid(seed_entity_id)

        direct_relations = self.find_neighborhood(
            seed_entity_id,
            depth=1,
            relation_types=relation_types,
            claim_backed_only=claim_backed_only,
        )
        direct_neighbors: set[UUID] = {
            self._other_endpoint(relation, seed_uuid) for relation in direct_relations
        }
        direct_neighbors.discard(seed_uuid)

        multi_hop_relations = self.find_neighborhood(
            seed_entity_id,
            depth=max_path_length,
            relation_types=relation_types,
            claim_backed_only=claim_backed_only,
        )

        # Compute reachable entity set and remember a sample bridge entity
        # (any 1-hop neighbor of the seed that participates in a relation
        # involving the gap target) for each reachable target.
        reachable: set[UUID] = set()
        bridge_for_target: dict[UUID, UUID] = {}
        for relation in multi_hop_relations:
            source_uuid = _as_uuid(str(relation.source_id))
            target_uuid = _as_uuid(str(relation.target_id))
            for endpoint in (source_uuid, target_uuid):
                if endpoint == seed_uuid:
                    continue
                reachable.add(endpoint)
                if endpoint in bridge_for_target:
                    continue
                # Pick a 1-hop neighbor that bridges to this target.
                if source_uuid in direct_neighbors and target_uuid == endpoint:
                    bridge_for_target[endpoint] = source_uuid
                elif target_uuid in direct_neighbors and source_uuid == endpoint:
                    bridge_for_target[endpoint] = target_uuid

        gap_entity_ids = sorted(
            reachable - direct_neighbors,
            key=str,
        )

        start = max(offset or 0, 0)
        if limit is not None:
            gap_entity_ids = gap_entity_ids[start : start + max(limit, 0)]
        else:
            gap_entity_ids = gap_entity_ids[start:]

        return [
            KernelReachabilityGap(
                seed_entity_id=seed_uuid,
                target_entity_id=target_id,
                # Without enumerating all paths we conservatively report
                # the smallest possible multi-hop length (2).  Callers can
                # use the bridge_entity_id to walk a concrete path.
                min_path_length=2,
                bridge_entity_id=bridge_for_target.get(target_id),
            )
            for target_id in gap_entity_ids
        ]

    @staticmethod
    def _other_endpoint(relation: KernelRelation, anchor: UUID) -> UUID:
        """Return the endpoint of ``relation`` that is not ``anchor``."""
        source_uuid = _as_uuid(str(relation.source_id))
        target_uuid = _as_uuid(str(relation.target_id))
        return target_uuid if source_uuid == anchor else source_uuid

    _DEFAULT_MECHANISTIC_INTERMEDIATE_TYPES = (
        "BIOLOGICAL_PROCESS",
        "SIGNALING_PATHWAY",
        "MOLECULAR_FUNCTION",
        "PROTEIN_DOMAIN",
    )

    _MIN_MECHANISTIC_MAX_HOPS = 2
    _MAX_MECHANISTIC_MAX_HOPS = 4
    _DEFAULT_MECHANISTIC_MAX_VISITED = 5000

    def find_mechanistic_gaps(  # noqa: C901, PLR0912, PLR0913, PLR0915
        self: SqlAlchemyKernelRelationRepository,
        research_space_id: str,
        *,
        relation_types: list[str] | None = None,
        source_entity_type: str | None = None,
        target_entity_type: str | None = None,
        intermediate_entity_types: list[str] | None = None,
        claim_backed_only: bool = True,
        limit: int | None = None,
        offset: int | None = None,
        max_hops: int = 2,
        max_visited: int | None = None,
    ) -> list[KernelMechanisticGap]:
        """Find direct relations that lack an N-hop bridge through mechanism entities.

        For each direct canonical relation matching the configured pattern
        (default: ``ASSOCIATED_WITH``, optionally narrowed by source/target
        entity types), check whether any *path* of length 2..``max_hops``
        whose intermediate nodes are all of an "explanatory" entity type
        (default: BIOLOGICAL_PROCESS, SIGNALING_PATHWAY, MOLECULAR_FUNCTION,
        PROTEIN_DOMAIN) connects the endpoints.  Relations with no such
        bridge at any allowed depth are returned as mechanistic gaps.

        ``max_hops`` defaults to 2 (preserving the legacy 2-hop bridge test);
        must be within ``[2, 4]``.  Length 1 is "is there a direct relation",
        which is a different question; paths deeper than 4 in a dense
        biomedical graph are rarely meaningful and cheaply explode the BFS.

        Phase 4 Tier 4 query: "what gene-disease associations lack a
        mechanistic explanation?"
        """
        if (
            max_hops < self._MIN_MECHANISTIC_MAX_HOPS
            or max_hops > self._MAX_MECHANISTIC_MAX_HOPS
        ):
            msg = (
                f"max_hops must be between {self._MIN_MECHANISTIC_MAX_HOPS} and "
                f"{self._MAX_MECHANISTIC_MAX_HOPS} inclusive"
            )
            raise ValueError(msg)

        effective_max_visited = (
            max_visited
            if max_visited is not None
            else self._DEFAULT_MECHANISTIC_MAX_VISITED
        )

        normalized_relation_types = [
            rt.strip().upper() for rt in (relation_types or ["ASSOCIATED_WITH"]) if rt
        ]
        if not normalized_relation_types:
            normalized_relation_types = ["ASSOCIATED_WITH"]

        intermediate_set = tuple(
            t.strip().upper()
            for t in (
                intermediate_entity_types
                or self._DEFAULT_MECHANISTIC_INTERMEDIATE_TYPES
            )
            if t
        )
        if not intermediate_set:
            intermediate_set = self._DEFAULT_MECHANISTIC_INTERMEDIATE_TYPES

        # 1. Find candidate direct relations matching the pattern.
        source_entity = aliased(EntityModel)
        target_entity = aliased(EntityModel)
        stmt = (
            select(RelationModel)
            .join(source_entity, source_entity.id == RelationModel.source_id)
            .join(target_entity, target_entity.id == RelationModel.target_id)
            .where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
                RelationModel.relation_type.in_(normalized_relation_types),
            )
            .order_by(RelationModel.created_at.desc())
        )
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        if source_entity_type is not None:
            stmt = stmt.where(
                source_entity.entity_type == source_entity_type.strip().upper(),
            )
        if target_entity_type is not None:
            stmt = stmt.where(
                target_entity.entity_type == target_entity_type.strip().upper(),
            )

        candidate_relations = list(self._session.scalars(stmt).all())

        # 2. For each candidate, check whether any mechanism-typed path of
        #    length 2..max_hops bridges its endpoints.  Cache typed-neighbor
        #    sets per entity for the first hop (used both as a fast
        #    intermediate-count metric and as BFS seed neighbors).
        typed_neighbor_cache: dict[UUID, set[UUID]] = {}

        def neighbors_for(entity_id: UUID) -> set[UUID]:
            cached = typed_neighbor_cache.get(entity_id)
            if cached is not None:
                return cached
            value = self._typed_neighbors(
                entity_id=entity_id,
                research_space_id=research_space_id,
                intermediate_entity_types=intermediate_set,
                claim_backed_only=claim_backed_only,
            )
            typed_neighbor_cache[entity_id] = value
            return value

        gaps: list[KernelMechanisticGap] = []
        for relation in candidate_relations:
            source_uuid = _as_uuid(str(relation.source_id))
            target_uuid = _as_uuid(str(relation.target_id))
            source_intermediates = neighbors_for(source_uuid)
            target_intermediates = neighbors_for(target_uuid)

            bridge_path = self._find_mechanistic_bridge_path(
                research_space_id=research_space_id,
                source_entity_id=source_uuid,
                target_entity_id=target_uuid,
                intermediate_entity_types=intermediate_set,
                claim_backed_only=claim_backed_only,
                max_hops=max_hops,
                max_visited=effective_max_visited,
                typed_neighbor_cache=typed_neighbor_cache,
            )
            if bridge_path is not None:
                # A qualifying path was found — not a gap.
                continue

            gaps.append(
                KernelMechanisticGap(
                    relation_id=_as_uuid(str(relation.id)),
                    source_entity_id=source_uuid,
                    target_entity_id=target_uuid,
                    relation_type=str(relation.relation_type),
                    source_intermediate_count=len(source_intermediates),
                    target_intermediate_count=len(target_intermediates),
                    bridge_entity_id=None,
                    bridge_path=None,
                ),
            )

        start = max(offset or 0, 0)
        if limit is not None:
            return gaps[start : start + max(limit, 0)]
        return gaps[start:]

    def _find_mechanistic_bridge_path(  # noqa: C901, PLR0913
        self: SqlAlchemyKernelRelationRepository,
        *,
        research_space_id: str,
        source_entity_id: UUID,
        target_entity_id: UUID,
        intermediate_entity_types: tuple[str, ...],
        claim_backed_only: bool,
        max_hops: int,
        max_visited: int,
        typed_neighbor_cache: dict[UUID, set[UUID]],
    ) -> list[UUID] | None:
        """Constrained BFS for a mechanism-typed bridge path.

        Returns the ordered list of *intermediate* entity IDs on the first
        path of length ``2..max_hops`` from ``source`` to ``target`` where
        every intermediate node's ``entity_type`` is in
        ``intermediate_entity_types``.  Returns ``None`` if no such path
        exists within the depth and visited-node budget.

        Notes:
        - BFS guarantees we find the shortest qualifying bridge first.
        - The visited set includes every node we've expanded from so we
          never re-enqueue the same node twice in one call.
        - Expansion stops early on the first path reaching ``target``.
        - ``max_visited`` caps total nodes we process (BFS pops) to prevent
          pathological runs on dense subgraphs; on overflow we return
          ``None`` (i.e. "no bridge found within budget" — the relation
          will be reported as a gap).
        """
        if source_entity_id == target_entity_id:
            return None
        if not intermediate_entity_types:
            return None

        # Depth here = hop count from source.  Depth 1 means "1 edge from
        # source" — the node we're sitting on is the first intermediate.
        # A 2-hop bridge is depth=1 intermediate + 1 edge to target.
        # A 3-hop bridge is depth=2 intermediate + 1 edge to target.
        # So max intermediate depth = max_hops - 1.
        max_intermediate_depth = max_hops - 1

        # Seed frontier: typed neighbors of source at depth 1 that are not
        # the target itself (direct target hit = 1 hop, which is excluded).
        first_hop = typed_neighbor_cache.get(source_entity_id)
        if first_hop is None:
            first_hop = self._typed_neighbors(
                entity_id=source_entity_id,
                research_space_id=research_space_id,
                intermediate_entity_types=intermediate_entity_types,
                claim_backed_only=claim_backed_only,
            )
            typed_neighbor_cache[source_entity_id] = first_hop

        # parents maps child_node -> parent_node for path reconstruction.
        parents: dict[UUID, UUID | None] = {}
        visited: set[UUID] = {source_entity_id}
        frontier: list[tuple[UUID, int]] = []
        for neighbor in first_hop:
            if neighbor == target_entity_id or neighbor == source_entity_id:
                continue
            if neighbor in visited:
                continue
            visited.add(neighbor)
            parents[neighbor] = None
            frontier.append((neighbor, 1))

        visited_count = 0

        def reconstruct(tail: UUID) -> list[UUID]:
            path: list[UUID] = []
            cursor: UUID | None = tail
            while cursor is not None:
                path.append(cursor)
                cursor = parents.get(cursor)
            path.reverse()
            return path

        while frontier:
            next_frontier: list[tuple[UUID, int]] = []
            for node, depth in frontier:
                visited_count += 1
                if visited_count > max_visited:
                    return None

                # Does this intermediate have a direct edge to the target?
                # Any edge suffices here: the target's entity_type is *not*
                # constrained to the mechanism allowlist.
                if self._has_edge_between(
                    research_space_id=research_space_id,
                    left_entity_id=node,
                    right_entity_id=target_entity_id,
                    claim_backed_only=claim_backed_only,
                ):
                    return reconstruct(node)

                if depth >= max_intermediate_depth:
                    continue

                node_neighbors = typed_neighbor_cache.get(node)
                if node_neighbors is None:
                    node_neighbors = self._typed_neighbors(
                        entity_id=node,
                        research_space_id=research_space_id,
                        intermediate_entity_types=intermediate_entity_types,
                        claim_backed_only=claim_backed_only,
                    )
                    typed_neighbor_cache[node] = node_neighbors

                for neighbor in node_neighbors:
                    if neighbor in visited:
                        continue
                    if neighbor == source_entity_id:
                        continue
                    # We still enqueue neighbor even if it equals target;
                    # the _has_edge_between check will fire on the next
                    # iteration — but shortcut: we already test
                    # has-edge-to-target per popped node, so we can skip
                    # enqueuing target itself.  (Edge-to-target is checked
                    # via the just-expanded node.)
                    if neighbor == target_entity_id:
                        continue
                    visited.add(neighbor)
                    parents[neighbor] = node
                    next_frontier.append((neighbor, depth + 1))
                    if len(visited) > max_visited:
                        return None
            frontier = next_frontier

        return None

    def _has_edge_between(
        self: SqlAlchemyKernelRelationRepository,
        *,
        research_space_id: str,
        left_entity_id: UUID,
        right_entity_id: UUID,
        claim_backed_only: bool,
    ) -> bool:
        """Return True if any relation directly connects the two entities."""
        stmt = select(RelationModel.id).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
            or_(
                and_(
                    RelationModel.source_id == left_entity_id,
                    RelationModel.target_id == right_entity_id,
                ),
                and_(
                    RelationModel.source_id == right_entity_id,
                    RelationModel.target_id == left_entity_id,
                ),
            ),
        )
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        return self._session.scalars(stmt.limit(1)).first() is not None

    def _typed_neighbors(
        self: SqlAlchemyKernelRelationRepository,
        *,
        entity_id: UUID,
        research_space_id: str,
        intermediate_entity_types: tuple[str, ...],
        claim_backed_only: bool,
    ) -> set[UUID]:
        """Return 1-hop neighbor entity IDs whose ``entity_type`` is in the set.

        A neighbor is any entity sharing a relation with ``entity_id`` (in
        either direction).  ``entity_id`` itself is excluded.
        """
        if not intermediate_entity_types:
            return set()

        neighbor_entity = aliased(EntityModel)
        stmt = (
            select(neighbor_entity.id)
            .join(
                RelationModel,
                or_(
                    RelationModel.source_id == neighbor_entity.id,
                    RelationModel.target_id == neighbor_entity.id,
                ),
            )
            .where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
                neighbor_entity.entity_type.in_(intermediate_entity_types),
                neighbor_entity.id != entity_id,
                or_(
                    RelationModel.source_id == entity_id,
                    RelationModel.target_id == entity_id,
                ),
            )
            .distinct()
        )
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        return set(self._session.scalars(stmt).all())

    def _find_neighborhood_from_read_model(
        self: SqlAlchemyKernelRelationRepository,
        *,
        entity_id: str,
        relation_types: list[str] | None,
        limit: int | None,
    ) -> list[KernelRelation]:
        stmt = (
            select(RelationModel)
            .join(
                EntityNeighborModel,
                EntityNeighborModel.relation_id == RelationModel.id,
            )
            .where(EntityNeighborModel.entity_id == _as_uuid(entity_id))
            .order_by(
                EntityNeighborModel.relation_updated_at.desc(),
                RelationModel.id.desc(),
            )
        )
        if relation_types:
            stmt = stmt.where(EntityNeighborModel.relation_type.in_(relation_types))
        if limit is not None:
            stmt = stmt.limit(max(limit, 1))
        models = list(self._session.scalars(stmt).all())
        return [KernelRelation.model_validate(model) for model in models]

    def find_by_research_space(  # noqa: C901, PLR0913
        self: SqlAlchemyKernelRelationRepository,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        claim_backed_only: bool = True,
        max_source_family_count: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelRelation]:
        stmt = self._build_research_space_stmt(
            research_space_id=research_space_id,
            relation_type=relation_type,
            curation_status=curation_status,
            validation_state=validation_state,
            source_document_id=source_document_id,
            certainty_band=certainty_band,
            node_query=node_query,
            node_ids=node_ids,
            claim_backed_only=claim_backed_only,
            max_source_family_count=max_source_family_count,
        )
        if stmt is None:
            return []
        stmt = stmt.order_by(RelationModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelRelation.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def search_by_text(
        self: SqlAlchemyKernelRelationRepository,
        research_space_id: str,
        query: str,
        *,
        claim_backed_only: bool = True,
        limit: int = 20,
    ) -> list[KernelRelation]:
        stmt = (
            select(RelationModel)
            .outerjoin(
                RelationEvidenceModel,
                RelationEvidenceModel.relation_id == RelationModel.id,
            )
            .where(
                RelationModel.research_space_id == _as_uuid(research_space_id),
                or_(
                    RelationModel.relation_type.ilike(f"%{query}%"),
                    RelationModel.curation_status.ilike(f"%{query}%"),
                    RelationEvidenceModel.evidence_summary.ilike(f"%{query}%"),
                ),
            )
            .order_by(RelationModel.updated_at.desc())
            .limit(limit)
        )
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        models = list(self._session.scalars(stmt).all())
        seen: set[UUID] = set()
        unique_models: list[RelationModel] = []
        for model in models:
            if model.id in seen:
                continue
            seen.add(model.id)
            unique_models.append(model)
        return [KernelRelation.model_validate(model) for model in unique_models]

    def count_by_research_space(  # noqa: PLR0913
        self: SqlAlchemyKernelRelationRepository,
        research_space_id: str,
        *,
        relation_type: str | None = None,
        curation_status: str | None = None,
        validation_state: str | None = None,
        source_document_id: str | None = None,
        certainty_band: str | None = None,
        node_query: str | None = None,
        node_ids: list[str] | None = None,
        claim_backed_only: bool = True,
        max_source_family_count: int | None = None,
    ) -> int:
        stmt = self._build_research_space_stmt(
            research_space_id=research_space_id,
            relation_type=relation_type,
            curation_status=curation_status,
            validation_state=validation_state,
            source_document_id=source_document_id,
            certainty_band=certainty_band,
            node_query=node_query,
            node_ids=node_ids,
            claim_backed_only=claim_backed_only,
            max_source_family_count=max_source_family_count,
        )
        if stmt is None:
            return 0
        result = self._session.execute(
            stmt.with_only_columns(
                func.count(func.distinct(RelationModel.id)),
                maintain_column_froms=True,
            ),
        )
        return int(result.scalar_one())

    def _build_research_space_stmt(  # noqa: C901, PLR0912, PLR0913
        self: SqlAlchemyKernelRelationRepository,
        *,
        research_space_id: str,
        relation_type: str | None,
        curation_status: str | None,
        validation_state: str | None,
        source_document_id: str | None,
        certainty_band: str | None,
        node_query: str | None,
        node_ids: list[str] | None,
        claim_backed_only: bool,
        max_source_family_count: int | None = None,
    ) -> Select[tuple[RelationModel]] | None:
        stmt = select(RelationModel).where(
            RelationModel.research_space_id == _as_uuid(research_space_id),
        )
        if claim_backed_only:
            stmt = stmt.where(self._active_support_projection_exists())
        if relation_type is not None:
            stmt = stmt.where(RelationModel.relation_type == relation_type)
        if curation_status is not None:
            stmt = stmt.where(RelationModel.curation_status == curation_status)
        if max_source_family_count is not None:
            stmt = stmt.where(
                RelationModel.distinct_source_family_count <= max_source_family_count,
            )
        if validation_state is not None:
            claim_relation_ids = select(RelationClaimModel.linked_relation_id).where(
                RelationClaimModel.research_space_id == _as_uuid(research_space_id),
                RelationClaimModel.linked_relation_id.is_not(None),
                RelationClaimModel.validation_state == validation_state,
            )
            stmt = stmt.where(RelationModel.id.in_(claim_relation_ids))
        if source_document_id is not None:
            source_document_uuid = _try_as_uuid(source_document_id)
            if source_document_uuid is None:
                return None
            evidence_relation_ids = select(RelationEvidenceModel.relation_id).where(
                RelationEvidenceModel.source_document_id == source_document_uuid,
            )
            claim_relation_ids = select(RelationClaimModel.linked_relation_id).where(
                RelationClaimModel.research_space_id == _as_uuid(research_space_id),
                RelationClaimModel.linked_relation_id.is_not(None),
                RelationClaimModel.source_document_id == source_document_uuid,
            )
            stmt = stmt.where(
                or_(
                    RelationModel.id.in_(evidence_relation_ids),
                    RelationModel.id.in_(claim_relation_ids),
                ),
            )
        if certainty_band is not None:
            normalized_band = certainty_band.strip().upper()
            if normalized_band == "HIGH":
                stmt = stmt.where(
                    RelationModel.aggregate_confidence
                    >= self._HIGH_CONFIDENCE_THRESHOLD,
                )
            elif normalized_band == "MEDIUM":
                stmt = stmt.where(
                    RelationModel.aggregate_confidence
                    >= self._MEDIUM_CONFIDENCE_THRESHOLD,
                    RelationModel.aggregate_confidence
                    < self._HIGH_CONFIDENCE_THRESHOLD,
                )
            elif normalized_band == "LOW":
                stmt = stmt.where(
                    RelationModel.aggregate_confidence
                    < self._MEDIUM_CONFIDENCE_THRESHOLD,
                )
        if node_ids:
            node_uuid_ids: list[UUID] = []
            for node_id in node_ids:
                trimmed = node_id.strip()
                if not trimmed:
                    continue
                try:
                    node_uuid_ids.append(_as_uuid(trimmed))
                except ValueError:
                    continue
            if not node_uuid_ids:
                return None
            stmt = stmt.where(
                or_(
                    RelationModel.source_id.in_(node_uuid_ids),
                    RelationModel.target_id.in_(node_uuid_ids),
                ),
            )
        if node_query is not None and node_query.strip():
            source_entity = aliased(EntityModel)
            target_entity = aliased(EntityModel)
            search_term = f"%{node_query.strip()}%"
            stmt = stmt.join(
                source_entity,
                source_entity.id == RelationModel.source_id,
            ).join(
                target_entity,
                target_entity.id == RelationModel.target_id,
            )
            stmt = stmt.where(
                or_(
                    RelationModel.source_id.cast(String).ilike(search_term),
                    RelationModel.target_id.cast(String).ilike(search_term),
                    source_entity.display_label.ilike(search_term),
                    target_entity.display_label.ilike(search_term),
                    source_entity.entity_type.ilike(search_term),
                    target_entity.entity_type.ilike(search_term),
                ),
            )
        return stmt

    @staticmethod
    def _active_support_projection_exists() -> ColumnElement[bool]:
        projection_to_claim = and_(
            RelationClaimModel.id == RelationProjectionSourceModel.claim_id,
            RelationClaimModel.research_space_id
            == RelationProjectionSourceModel.research_space_id,
        )
        return (
            select(RelationProjectionSourceModel.id)
            .join(RelationClaimModel, projection_to_claim)
            .where(
                RelationProjectionSourceModel.relation_id == RelationModel.id,
                RelationProjectionSourceModel.research_space_id
                == RelationModel.research_space_id,
                RelationClaimModel.polarity == "SUPPORT",
                RelationClaimModel.claim_status == "RESOLVED",
                RelationClaimModel.persistability == "PERSISTABLE",
            )
            .exists()
        )


def _try_as_uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        return _as_uuid(normalized)
    except ValueError:
        return None
