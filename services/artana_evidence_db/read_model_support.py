"""Service-local graph read-model dispatcher support."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class GraphReadModelOwner(StrEnum):
    """Ownership scope for one read-model definition."""

    GRAPH_CORE = "graph_core"
    DOMAIN_PACK = "domain_pack"


class GraphReadModelAuthoritativeSource(StrEnum):
    """Authoritative stores from which read models may be derived."""

    CLAIM_LEDGER = "claim_ledger"
    CANONICAL_GRAPH = "canonical_graph"
    PROJECTION_LINEAGE = "projection_lineage"


class GraphReadModelTrigger(StrEnum):
    """Events that can refresh one read model."""

    CLAIM_CHANGE = "claim_change"
    ENTITY_CHANGE = "entity_change"
    PROJECTION_CHANGE = "projection_change"
    FULL_REBUILD = "full_rebuild"


@dataclass(frozen=True)
class GraphReadModelDefinition:
    """One graph query read model owned by graph-core or a domain pack."""

    name: str
    description: str
    owner: GraphReadModelOwner
    authoritative_sources: tuple[GraphReadModelAuthoritativeSource, ...]
    triggers: tuple[GraphReadModelTrigger, ...]
    is_truth_source: bool = False


@dataclass(frozen=True)
class GraphReadModelUpdate:
    """One incremental or rebuild update request for a read model."""

    model_name: str
    trigger: GraphReadModelTrigger
    claim_ids: tuple[str, ...] = ()
    relation_ids: tuple[str, ...] = ()
    entity_ids: tuple[str, ...] = ()
    space_id: str | None = None


@runtime_checkable
class GraphReadModelProjector(Protocol):
    """Runtime contract for one rebuildable graph read-model projector."""

    @property
    def definition(self) -> GraphReadModelDefinition:
        """Return the read-model definition owned by this projector."""

    def rebuild(self, *, space_id: str | None = None) -> int:
        """Rebuild the whole read model and return the affected row count."""

    def apply_update(self, update: GraphReadModelUpdate) -> int:
        """Apply one incremental update and return the affected row count."""


@runtime_checkable
class GraphReadModelUpdateDispatcher(Protocol):
    """Runtime contract for dispatching read-model refresh intents."""

    def dispatch(self, update: GraphReadModelUpdate) -> int:
        """Dispatch one read-model update and return the affected row count."""

    def dispatch_many(self, updates: tuple[GraphReadModelUpdate, ...]) -> int:
        """Dispatch multiple updates and return the total affected row count."""


@dataclass
class NullGraphReadModelUpdateDispatcher:
    """No-op dispatcher used by tests and service seams without projectors."""

    def dispatch(self, update: GraphReadModelUpdate) -> int:
        del update
        return 0

    def dispatch_many(self, updates: tuple[GraphReadModelUpdate, ...]) -> int:
        del updates
        return 0


@dataclass
class ProjectorBackedGraphReadModelUpdateDispatcher:
    """Dispatcher that routes updates to registered read-model projectors."""

    projectors: dict[str, GraphReadModelProjector]

    def dispatch(self, update: GraphReadModelUpdate) -> int:
        projector = self.projectors.get(update.model_name)
        if projector is None:
            return 0
        trigger_value = str(getattr(update.trigger, "value", update.trigger))
        if trigger_value == GraphReadModelTrigger.FULL_REBUILD.value:
            return projector.rebuild(space_id=update.space_id)
        return projector.apply_update(update)

    def dispatch_many(self, updates: tuple[GraphReadModelUpdate, ...]) -> int:
        return sum(self.dispatch(update) for update in updates)


ENTITY_NEIGHBORS_READ_MODEL = GraphReadModelDefinition(
    name="entity_neighbors",
    description="Fast neighborhood reads derived from canonical relations and lineage.",
    owner=GraphReadModelOwner.GRAPH_CORE,
    authoritative_sources=(
        GraphReadModelAuthoritativeSource.CANONICAL_GRAPH,
        GraphReadModelAuthoritativeSource.PROJECTION_LINEAGE,
    ),
    triggers=(
        GraphReadModelTrigger.PROJECTION_CHANGE,
        GraphReadModelTrigger.FULL_REBUILD,
    ),
)

ENTITY_RELATION_SUMMARY_READ_MODEL = GraphReadModelDefinition(
    name="entity_relation_summary",
    description="Per-entity relation counts and summary metrics for graph browsing.",
    owner=GraphReadModelOwner.GRAPH_CORE,
    authoritative_sources=(
        GraphReadModelAuthoritativeSource.CANONICAL_GRAPH,
        GraphReadModelAuthoritativeSource.PROJECTION_LINEAGE,
    ),
    triggers=(
        GraphReadModelTrigger.PROJECTION_CHANGE,
        GraphReadModelTrigger.FULL_REBUILD,
    ),
)

ENTITY_CLAIM_SUMMARY_READ_MODEL = GraphReadModelDefinition(
    name="entity_claim_summary",
    description="Per-entity claim-backed summary metrics for evidence-oriented reads.",
    owner=GraphReadModelOwner.GRAPH_CORE,
    authoritative_sources=(
        GraphReadModelAuthoritativeSource.CLAIM_LEDGER,
        GraphReadModelAuthoritativeSource.PROJECTION_LINEAGE,
    ),
    triggers=(
        GraphReadModelTrigger.CLAIM_CHANGE,
        GraphReadModelTrigger.PROJECTION_CHANGE,
        GraphReadModelTrigger.FULL_REBUILD,
    ),
)

ENTITY_MECHANISM_PATHS_READ_MODEL = GraphReadModelDefinition(
    name="entity_mechanism_paths",
    description=(
        "Per-seed mechanism-path candidates derived from grounded reasoning paths "
        "for hypothesis and mechanism-oriented reads."
    ),
    owner=GraphReadModelOwner.GRAPH_CORE,
    authoritative_sources=(
        GraphReadModelAuthoritativeSource.CLAIM_LEDGER,
        GraphReadModelAuthoritativeSource.PROJECTION_LINEAGE,
    ),
    triggers=(
        GraphReadModelTrigger.CLAIM_CHANGE,
        GraphReadModelTrigger.PROJECTION_CHANGE,
        GraphReadModelTrigger.FULL_REBUILD,
    ),
)

ENTITY_EMBEDDING_STATUS_READ_MODEL = GraphReadModelDefinition(
    name="entity_embedding_status",
    description=(
        "Graph-owned readiness metadata for entity embedding projections and "
        "partial vector-dependent workflows."
    ),
    owner=GraphReadModelOwner.GRAPH_CORE,
    authoritative_sources=(GraphReadModelAuthoritativeSource.CANONICAL_GRAPH,),
    triggers=(
        GraphReadModelTrigger.ENTITY_CHANGE,
        GraphReadModelTrigger.FULL_REBUILD,
    ),
)


__all__ = [
    "ENTITY_CLAIM_SUMMARY_READ_MODEL",
    "ENTITY_EMBEDDING_STATUS_READ_MODEL",
    "ENTITY_MECHANISM_PATHS_READ_MODEL",
    "ENTITY_NEIGHBORS_READ_MODEL",
    "ENTITY_RELATION_SUMMARY_READ_MODEL",
    "GraphReadModelAuthoritativeSource",
    "GraphReadModelDefinition",
    "GraphReadModelOwner",
    "GraphReadModelProjector",
    "GraphReadModelTrigger",
    "GraphReadModelUpdate",
    "GraphReadModelUpdateDispatcher",
    "NullGraphReadModelUpdateDispatcher",
    "ProjectorBackedGraphReadModelUpdateDispatcher",
]
