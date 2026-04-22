"""Ontology loader ingestion service.

Implements the loader/import contract for ontology hierarchies.  Terms are
imported as graph entities and dictionary entries — this is NOT an extraction
pipeline path.  Hierarchy edges (parent-child) are deterministic imports,
not governed relation claims.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from src.domain.services.ontology_ingestion import (
    OntologyIngestionSummary,
)

if TYPE_CHECKING:
    from src.domain.services.ontology_ingestion import (
        OntologyGateway,
        OntologyTerm,
    )
    from src.type_definitions.common import JSONObject


class _OntologyIngestionConfig(Protocol):
    """Structural type for ontology ingestion configuration."""

    version: str | None
    format_preference: str
    namespace_filter: str | None
    max_terms: int | None


logger = logging.getLogger(__name__)


def _default_entity_type_for_namespace(namespace: str) -> str:
    """Map ontology namespace to graph entity type."""
    mapping = {
        "HP": "PHENOTYPE",
        "UBERON": "TISSUE",
        "CL": "CELL_TYPE",
        "GO": "BIOLOGICAL_PROCESS",
        "MONDO": "DISEASE",
    }
    return mapping.get(namespace.upper(), "ONTOLOGY_TERM")


def _alias_metric_key(*, namespace: str, entity_type: str) -> str:
    """Return one compact namespace/entity-type key for alias metrics."""
    normalized_namespace = namespace.strip().upper() or "UNKNOWN"
    normalized_entity_type = entity_type.strip().upper() or "ONTOLOGY_TERM"
    return f"{normalized_namespace}:{normalized_entity_type}"


class OntologyIngestionService:
    """Import ontology terms as graph entities with hierarchy and aliases."""

    def __init__(
        self,
        *,
        gateway: OntologyGateway,
        entity_writer: _EntityWriter | None = None,
    ) -> None:
        self._gateway = gateway
        self._entity_writer = entity_writer

    async def ingest(
        self,
        *,
        source_id: object,
        research_space_id: str | None = None,
        config: _OntologyIngestionConfig | None = None,
        checkpoint_before: JSONObject | None = None,
    ) -> OntologyIngestionSummary:
        """Run one ontology loader pass.

        Returns a summary with import metrics.  Does NOT create source
        documents or extraction queue items — ontology terms are loader
        imports, not extraction pipeline inputs.
        """
        from uuid import UUID

        resolved_source_id = (
            source_id if isinstance(source_id, UUID) else UUID(str(source_id))
        )
        ingestion_job_id = uuid4()

        version = config.version if config else None
        format_preference = config.format_preference if config else "obo"
        namespace_filter = config.namespace_filter if config else None
        max_terms = config.max_terms if config else None

        # Check if we already have this version
        if checkpoint_before and version:
            last_version = checkpoint_before.get("release_version")
            if last_version == version:
                logger.info(
                    "Ontology version %s already imported, skipping",
                    version,
                )
                return OntologyIngestionSummary(
                    source_id=resolved_source_id,
                    ingestion_job_id=ingestion_job_id,
                    release_version=version,
                    checkpoint_before=checkpoint_before,
                    checkpoint_after=checkpoint_before,
                )

        result = await self._gateway.fetch_release(
            version=version,
            format_preference=format_preference,
            namespace_filter=namespace_filter,
            max_terms=max_terms,
        )

        terms = result.terms
        release_version = result.release.version
        entities_created = 0
        entities_updated = 0
        alias_candidates_count = 0
        aliases_registered = 0
        aliases_persisted = 0
        alias_entities_touched = 0
        aliases_persisted_by_namespace_entity_type: dict[str, int] = {}
        hierarchy_edges = 0
        hierarchy_edges_created = 0
        xref_edges_created = 0
        skipped_obsolete = 0

        # Pass 1: skip obsolete terms, then bulk-upsert entities so the
        # downstream edge-persisting pass can read entity_id_cache hits
        # without one HTTP round-trip per term.  Falls back to per-term
        # upsert when no writer is wired (dry-run mode).
        active_term_pairs: list[tuple[OntologyTerm, str]] = []
        for term in terms:
            if term.is_obsolete:
                skipped_obsolete += 1
                continue
            entity_type = _default_entity_type_for_namespace(
                term.namespace or namespace_filter or "",
            )
            active_term_pairs.append((term, entity_type))

        if self._entity_writer is not None and active_term_pairs:
            entities_created = self._batch_upsert_entities(
                term_pairs=active_term_pairs,
                research_space_id=research_space_id,
            )
            entities_updated = len(active_term_pairs) - entities_created

        # Pass 2: per-term aliases, hierarchy edges, xref edges.  These
        # cannot be trivially batched without changes to several other
        # endpoints; the entity-batch fast path alone reclaims the bulk
        # of the load-time win because the per-term operations here are
        # cheap when the entity already exists in the cache.
        for term, entity_type in active_term_pairs:
            if self._entity_writer is not None:
                ar, ap, hc, xc = self._write_term_edges(
                    term,
                    research_space_id,
                )
                aliases_registered += ar
                alias_candidates_count += ar
                aliases_persisted += ap
                if ar:
                    alias_entities_touched += 1
                if ap:
                    metric_key = _alias_metric_key(
                        namespace=term.namespace or namespace_filter or "",
                        entity_type=entity_type,
                    )
                    aliases_persisted_by_namespace_entity_type[metric_key] = (
                        aliases_persisted_by_namespace_entity_type.get(metric_key, 0)
                        + ap
                    )
                hierarchy_edges_created += hc
                xref_edges_created += xc
            hierarchy_edges += len(term.parents)

        checkpoint_after: JSONObject = {
            "release_version": release_version,
            "release_date": result.release.release_date,
            "terms_imported": len(terms) - skipped_obsolete,
            "format": result.release.format,
        }

        logger.info(
            "Ontology import complete: %d terms, %d entities created, "
            "%d aliases (%d persisted), %d hierarchy edges (%d persisted), "
            "%d xref edges persisted, version=%s",
            len(terms) - skipped_obsolete,
            entities_created,
            aliases_registered,
            aliases_persisted,
            hierarchy_edges,
            hierarchy_edges_created,
            xref_edges_created,
            release_version,
        )

        return OntologyIngestionSummary(
            source_id=resolved_source_id,
            ingestion_job_id=ingestion_job_id,
            release_version=release_version,
            terms_fetched=len(terms),
            terms_imported=len(terms) - skipped_obsolete,
            entities_created=entities_created,
            entities_updated=entities_updated,
            alias_candidates_count=alias_candidates_count,
            aliases_registered=aliases_registered,
            aliases_persisted=aliases_persisted,
            aliases_skipped=max(alias_candidates_count - aliases_persisted, 0),
            alias_entities_touched=alias_entities_touched,
            aliases_persisted_by_namespace_entity_type=(
                aliases_persisted_by_namespace_entity_type
            ),
            hierarchy_edges=hierarchy_edges,
            hierarchy_edges_created=hierarchy_edges_created,
            xref_edges_created=xref_edges_created,
            skipped_obsolete=skipped_obsolete,
            checkpoint_before=checkpoint_before,
            checkpoint_after=checkpoint_after,
        )

    _BATCH_CHUNK_SIZE = 200

    def _batch_upsert_entities(
        self,
        *,
        term_pairs: list[tuple[OntologyTerm, str]],
        research_space_id: str | None,
    ) -> int:
        """Upsert all term entities in chunks via the writer's batch path.

        Returns the total number of newly created entities (across all
        chunks).  The chunk size is bounded so individual graph-service
        transactions stay within the batch endpoint's 500-row cap and
        don't hold long-lived locks; for MONDO at 26k terms this gives
        ~130 batch POSTs instead of 26k single POSTs.
        """
        assert self._entity_writer is not None  # noqa: S101
        created_total = 0
        if not self._entity_writer.supports_batch_upsert():
            for term, entity_type in term_pairs:
                if self._entity_writer.upsert_term(
                    term=term,
                    entity_type=entity_type,
                    research_space_id=research_space_id,
                ):
                    created_total += 1
            return created_total
        chunk_size = self._BATCH_CHUNK_SIZE
        for start in range(0, len(term_pairs), chunk_size):
            chunk = term_pairs[start : start + chunk_size]
            try:
                created_total += self._entity_writer.upsert_terms_batch(
                    terms=chunk,
                    research_space_id=research_space_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Ontology batch upsert chunk %d failed (%d terms), "
                    "falling back to per-term upsert: %s",
                    start // chunk_size,
                    len(chunk),
                    exc,
                )
                for term, entity_type in chunk:
                    if self._entity_writer.upsert_term(
                        term=term,
                        entity_type=entity_type,
                        research_space_id=research_space_id,
                    ):
                        created_total += 1
        return created_total

    def _write_term_edges(
        self,
        term: OntologyTerm,
        research_space_id: str | None,
    ) -> tuple[int, int, int, int]:
        """Write one term's aliases, hierarchy edges, and xref edges.

        The entity itself is assumed to have been upserted in the prior
        batch pass — this method only persists the per-term edges that
        depend on the entity_id cache being populated.

        Returns (aliases_registered, aliases_persisted, hierarchy_edges, xref_edges).
        """
        assert self._entity_writer is not None  # noqa: S101
        aliases = 0
        aliases_persisted = 0
        for synonym in term.synonyms:
            if self._entity_writer.register_alias(term_id=term.id, alias=synonym):
                aliases_persisted += 1
            aliases += 1

        hierarchy = 0
        for parent_id in term.parents:
            if self._entity_writer.persist_hierarchy_edge(
                child_term_id=term.id,
                parent_term_id=parent_id,
                research_space_id=research_space_id,
            ):
                hierarchy += 1

        xrefs = 0
        for xref in term.xrefs:
            if self._entity_writer.persist_xref_edge(
                term_id=term.id,
                xref=xref,
                research_space_id=research_space_id,
            ):
                xrefs += 1

        return aliases, aliases_persisted, hierarchy, xrefs


class _EntityWriter:
    """Protocol for writing ontology entities to the graph.

    Implementations can be backed by a real graph API gateway or an
    in-memory stub for testing.
    """

    def upsert_term(
        self,
        *,
        term: OntologyTerm,
        entity_type: str,
        research_space_id: str | None,
    ) -> bool:
        """Upsert one ontology term as a graph entity.  Returns True if created."""
        raise NotImplementedError

    def supports_batch_upsert(self) -> bool:
        """Return whether the writer exposes a real batch fast path."""
        return False

    def upsert_terms_batch(
        self,
        *,
        terms: list[tuple[OntologyTerm, str]],
        research_space_id: str | None,
    ) -> int:
        """Optional fast path: upsert many terms in a single transaction.

        ``terms`` is a list of ``(term, entity_type)`` pairs.  Implementations
        that wrap a real graph API gateway should POST these as one
        ``KernelEntityBatchCreateRequest`` to amortize HTTP and commit
        overhead — critical for ontology loaders like MONDO that ingest
        ~26k terms per release.  Returns the number of newly created
        entities (the rest were resolved against existing rows).

        Default implementation falls back to repeated ``upsert_term``
        calls so test stubs don't have to override this method.
        """
        created_count = 0
        for term, entity_type in terms:
            if self.upsert_term(
                term=term,
                entity_type=entity_type,
                research_space_id=research_space_id,
            ):
                created_count += 1
        return created_count

    def register_alias(self, *, term_id: str, alias: str) -> bool:
        """Register one synonym/alias for an ontology term.

        Returns True when the alias was ensured as persisted for the term.
        """
        raise NotImplementedError

    def persist_hierarchy_edge(
        self,
        *,
        child_term_id: str,
        parent_term_id: str,
        research_space_id: str | None,
    ) -> bool:
        """Persist one ontology hierarchy edge (IS_A). Returns True if created."""
        raise NotImplementedError

    def persist_xref_edge(
        self,
        *,
        term_id: str,
        xref: str,
        research_space_id: str | None,
    ) -> bool:
        """Persist one cross-reference edge. Returns True if created."""
        raise NotImplementedError


__all__ = ["OntologyIngestionService"]
