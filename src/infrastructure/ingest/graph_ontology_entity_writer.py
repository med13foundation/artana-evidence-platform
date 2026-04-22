"""Concrete entity writer that persists ontology data to the graph via the graph API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from src.infrastructure.ingest.ontology_entity_aliases import (
    alias_labels_for_term,
    alias_labels_from_entity_payload,
    entity_payload_from_upsert_response,
    response_indicates_created,
)
from src.infrastructure.ingest.ontology_evidence_sentence import (
    OntologyEvidenceSentenceResolver,
    _build_hierarchy_evidence_sentence,
)

if TYPE_CHECKING:
    from src.domain.services.ontology_ingestion import OntologyTerm

logger = logging.getLogger(__name__)


def _parse_xref(xref: str) -> tuple[str, str]:
    """Parse ``'NAMESPACE:VALUE'`` into ``(namespace, value)``."""
    stripped = xref.strip()
    if ":" in stripped:
        namespace, _, value = stripped.partition(":")
        return namespace.strip(), value.strip()
    return "XREF", stripped


class GraphOntologyEntityWriter:
    """Writes ontology entities, aliases, and edges to the graph service.

    Implements the _EntityWriter protocol from OntologyIngestionService.

    Uses the ``GraphApiGateway`` (harness-level client) which exposes flat
    parameter methods like ``create_entity(space_id, entity_type, display_label)``
    and returns raw JSON dicts.

    When an ``evidence_sentence_harness`` is provided and the AI evidence
    feature flag is enabled (either the global
    ``ARTANA_ONTOLOGY_LLM_EVIDENCE_SENTENCES`` or a per-namespace flag like
    ``ARTANA_ONTOLOGY_LLM_EVIDENCE_SENTENCES_HP``), IS_A hierarchy edges
    get AI-generated evidence sentences grounded in the parsed OBO
    definitions and synonyms.  Generated sentences are cached by
    ``(child_id, parent_id)`` so a single ontology load does not duplicate
    work when a term appears as a parent of many children.  Any failure
    (harness unavailable, timeout, rate limit, validation mismatch, etc.)
    silently falls back to the existing template sentence.

    Per-namespace observability counters are tracked and exposed via
    :meth:`get_ai_sentence_stats` so the loader / scheduler factory can log
    a summary at the end of an ontology load.
    """

    def __init__(
        self,
        *,
        graph_api_gateway: object,
        research_space_id: UUID,
        evidence_sentence_harness: object | None = None,
    ) -> None:
        self._gateway = graph_api_gateway
        self._space_id = research_space_id
        self._entity_id_cache: dict[str, UUID] = {}
        self._term_name_cache: dict[str, str] = {}
        self._term_definition_cache: dict[str, str] = {}
        self._term_synonyms_cache: dict[str, tuple[str, ...]] = {}
        self._aliases_persisted_during_upsert: dict[str, set[str]] = {}
        self._aliases_known_before_registration: dict[str, set[str]] = {}
        self._aliases_skipped_during_upsert: dict[str, set[str]] = {}
        self._aliases_counted_as_persisted: dict[str, set[str]] = {}
        self._evidence_sentence_resolver = OntologyEvidenceSentenceResolver(
            evidence_sentence_harness=evidence_sentence_harness,
            research_space_id=research_space_id,
            term_definition_cache=self._term_definition_cache,
            term_synonyms_cache=self._term_synonyms_cache,
        )

    def supports_batch_upsert(self) -> bool:
        """Graph-backed writers can use the batch entity endpoint."""
        return hasattr(self._gateway, "create_entities_batch")

    def upsert_term(
        self,
        *,
        term: OntologyTerm,
        entity_type: str,
        research_space_id: str | None,
    ) -> bool:
        """Create or resolve one ontology term as a graph entity."""
        space_id = UUID(research_space_id) if research_space_id else self._space_id

        try:
            # GraphApiGateway.create_entity returns raw JSONObject
            result = self._gateway.create_entity(  # type: ignore[attr-defined]
                space_id=space_id,
                entity_type=entity_type,
                display_label=term.name,
                aliases=alias_labels_for_term(term),
            )
            # Result is a dict like {"id": "...", "entity_type": "...", ...}
            # or {"entity": {"id": "..."}, "created": true} depending on the endpoint
            entity_id = _extract_entity_id(result)
            if entity_id is not None:
                self._cache_term_metadata(term=term, entity_id=entity_id)
                self._record_alias_state_from_upsert(
                    term=term,
                    result=result,
                    created=response_indicates_created(result),
                )
                return True
            logger.debug("Entity upsert for %s: no ID in response", term.id)
            return False  # noqa: TRY300
        except Exception as exc:  # noqa: BLE001
            logger.debug("Entity upsert for %s: %s", term.id, exc)
            return False

    def upsert_terms_batch(
        self,
        *,
        terms: list[tuple[OntologyTerm, str]],
        research_space_id: str | None,
    ) -> int:
        """Bulk-upsert many ontology terms via the graph batch endpoint.

        Posts the entire chunk to ``POST /v1/spaces/{space_id}/entities/batch``
        in one HTTP round-trip with one server-side transaction.  Returns
        the count of newly created entities; the rest were resolved against
        existing rows in the space.

        On any HTTP-level failure the caller (``OntologyIngestionService``)
        falls back to per-term ``upsert_term`` so a single bad chunk does
        not abort the whole load.
        """
        if not terms:
            return 0
        space_id = UUID(research_space_id) if research_space_id else self._space_id

        payload_entities: list[dict[str, object]] = [
            {
                "entity_type": entity_type,
                "display_label": term.name,
                "aliases": alias_labels_for_term(term),
                "metadata": {},
                "identifiers": {},
            }
            for term, entity_type in terms
        ]

        result = self._gateway.create_entities_batch(  # type: ignore[attr-defined]
            space_id=space_id,
            entities=payload_entities,
        )
        if not isinstance(result, dict):
            msg = (
                f"Unexpected batch response shape: {type(result).__name__}; "
                "expected dict with 'results' key."
            )
            raise TypeError(msg)

        results_field = result.get("results")
        if not isinstance(results_field, list):
            msg = "Batch response missing 'results' list."
            raise TypeError(msg)
        if len(results_field) != len(terms):
            msg = (
                f"Batch response length mismatch: got {len(results_field)} "
                f"results for {len(terms)} requested terms."
            )
            raise RuntimeError(msg)

        created_count = 0
        for (term, _entity_type), row in zip(terms, results_field, strict=True):
            if not isinstance(row, dict):
                continue
            entity_payload = row.get("entity")
            entity_id = _extract_entity_id(entity_payload)
            if entity_id is None:
                # Some response shapes embed id at the top level instead.
                entity_id = _extract_entity_id(row)
            if entity_id is None:
                logger.debug(
                    "Batch upsert: no entity id for term %s in response row",
                    term.id,
                )
                continue
            self._cache_term_metadata(term=term, entity_id=entity_id)
            self._record_alias_state_from_upsert(
                term=term,
                result=row,
                created=row.get("created") is True,
            )
            if row.get("created") is True:
                created_count += 1
        return created_count

    def _cache_term_metadata(self, *, term: OntologyTerm, entity_id: UUID) -> None:
        """Stash the term's identifiers and OBO fields in the writer caches."""
        self._entity_id_cache[term.id] = entity_id
        self._term_name_cache[term.id] = term.name
        # Cache the richer OBO fields so persist_hierarchy_edge can feed
        # them to the AI evidence-sentence harness later.
        if term.definition:
            self._term_definition_cache[term.id] = term.definition
        if term.synonyms:
            self._term_synonyms_cache[term.id] = term.synonyms

    def _record_alias_state_from_upsert(
        self,
        *,
        term: OntologyTerm,
        result: object,
        created: bool,
    ) -> None:
        aliases_requested = set(alias_labels_for_term(term))
        if not aliases_requested:
            return
        entity_payload = entity_payload_from_upsert_response(result)
        existing_aliases = alias_labels_from_entity_payload(entity_payload)
        entity_payload_has_aliases = isinstance(entity_payload, dict) and isinstance(
            entity_payload.get("aliases"), list
        )
        if entity_payload_has_aliases:
            persisted_aliases = aliases_requested & existing_aliases
            skipped_aliases = aliases_requested - persisted_aliases
            self._aliases_persisted_during_upsert[term.id] = persisted_aliases
            if skipped_aliases:
                self._aliases_skipped_during_upsert[term.id] = skipped_aliases
            else:
                self._aliases_skipped_during_upsert.pop(term.id, None)
            if created:
                self._aliases_known_before_registration.pop(term.id, None)
            else:
                self._aliases_known_before_registration[term.id] = existing_aliases
            return
        if created:
            self._aliases_persisted_during_upsert[term.id] = aliases_requested
            self._aliases_known_before_registration.pop(term.id, None)
            self._aliases_skipped_during_upsert.pop(term.id, None)
            return
        if not existing_aliases:
            return
        self._aliases_known_before_registration[term.id] = existing_aliases
        self._aliases_skipped_during_upsert.pop(term.id, None)
        self._aliases_persisted_during_upsert.setdefault(
            term.id, set()
        ).difference_update(
            existing_aliases,
        )

    def register_alias(self, *, term_id: str, alias: str) -> bool:
        """Ensure one ontology synonym is persisted as a graph entity alias."""
        entity_id = self._entity_id_cache.get(term_id)
        normalized_alias = alias.strip()
        if entity_id is None or not normalized_alias:
            return False

        counted_aliases = self._aliases_counted_as_persisted.setdefault(term_id, set())
        existing_aliases = self._aliases_known_before_registration.get(term_id, set())
        skipped_aliases = self._aliases_skipped_during_upsert.get(term_id, set())
        if (
            normalized_alias in counted_aliases
            or normalized_alias in existing_aliases
            or normalized_alias in skipped_aliases
        ):
            return False

        upsert_aliases = self._aliases_persisted_during_upsert.setdefault(
            term_id,
            set(),
        )
        if normalized_alias in upsert_aliases:
            upsert_aliases.remove(normalized_alias)
            counted_aliases.add(normalized_alias)
            return True

        update_entity = getattr(self._gateway, "update_entity", None)
        if not callable(update_entity):
            logger.debug(
                "Alias registration unavailable for %s: gateway has no update_entity",
                term_id,
            )
            return False

        persisted = False
        try:
            update_entity(
                space_id=self._space_id,
                entity_id=entity_id,
                aliases=[normalized_alias],
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Alias registration for %s failed: %s", term_id, exc)
        else:
            counted_aliases.add(normalized_alias)
            persisted = True
        return persisted

    def persist_hierarchy_edge(
        self,
        *,
        child_term_id: str,
        parent_term_id: str,
        research_space_id: str | None,
    ) -> bool:
        """Persist one IS_A hierarchy edge with an evidence sentence.

        Tries the AI evidence-sentence harness first (when enabled via the
        ``ARTANA_ONTOLOGY_LLM_EVIDENCE_SENTENCES`` env var and a harness is
        wired in); falls back gracefully to the static template sentence on
        any failure.
        """
        child_entity_id = self._entity_id_cache.get(child_term_id)
        parent_entity_id = self._entity_id_cache.get(parent_term_id)

        if child_entity_id is None or parent_entity_id is None:
            return False

        space_id = UUID(research_space_id) if research_space_id else self._space_id

        child_name = self._term_name_cache.get(child_term_id, child_term_id)
        parent_name = self._term_name_cache.get(parent_term_id, parent_term_id)
        template_sentence = _build_hierarchy_evidence_sentence(
            child_name=child_name,
            parent_name=parent_name,
            child_id=child_term_id,
            parent_id=parent_term_id,
        )

        evidence_sentence, sentence_source, sentence_confidence = (
            self._evidence_sentence_resolver.resolve(
                child_term_id=child_term_id,
                parent_term_id=parent_term_id,
                child_name=child_name,
                parent_name=parent_name,
                template_sentence=template_sentence,
                research_space_id=research_space_id,
            )
        )

        try:
            self._create_relation_raw(
                space_id=space_id,
                source_id=child_entity_id,
                target_id=parent_entity_id,
                relation_type="INSTANCE_OF",
                evidence_sentence=evidence_sentence,
                evidence_sentence_source=sentence_source,
                evidence_sentence_confidence=sentence_confidence,
                child_term_id=child_term_id,
                parent_term_id=parent_term_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Hierarchy edge %s -> %s: %s",
                child_term_id,
                parent_term_id,
                exc,
            )
            return False
        return True

    def persist_xref_edge(
        self,
        *,
        term_id: str,
        xref: str,
        research_space_id: str | None,
    ) -> bool:
        """Persist one cross-reference as an identifier on the source entity.

        Xrefs are stored as entity identifiers (namespace + value) rather
        than as graph edges, because the target entity typically does not
        exist in the graph yet.  This enables cross-source entity resolution
        (e.g. ClinVar referencing OMIM:125853 resolves to MONDO:0005148).
        """
        entity_id = self._entity_id_cache.get(term_id)
        if entity_id is None:
            return False

        namespace, identifier_value = _parse_xref(xref)
        if not identifier_value:
            return False

        space_id = UUID(research_space_id) if research_space_id else self._space_id

        try:
            self._add_identifier_raw(
                space_id=space_id,
                entity_id=entity_id,
                namespace=namespace,
                identifier_value=identifier_value,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Xref identifier %s on %s: %s",
                xref,
                term_id,
                exc,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def get_ai_sentence_stats(self) -> dict[str, dict[str, int]]:
        """Return a deep copy of the per-namespace AI evidence sentence counters.

        Used by the ontology loader factory to log a one-line summary at
        the end of an ontology load (e.g. ``"HPO: 12,500 requested,
        12,447 generated, 53 fallback, avg 187 chars"``) without exposing
        the internal mutable counter dict.
        """
        return self._evidence_sentence_resolver.get_stats()

    def _create_relation_raw(  # noqa: PLR0913
        self,
        *,
        space_id: UUID,
        source_id: UUID,
        target_id: UUID,
        relation_type: str,
        evidence_sentence: str,
        child_term_id: str,
        parent_term_id: str,
        evidence_sentence_source: str = "artana_generated",
        evidence_sentence_confidence: str = "high",
    ) -> None:
        """Create a relation via the graph service's raw HTTP API."""
        import json

        # Build the request payload matching KernelRelationCreateRequest
        payload = {
            "source_id": str(source_id),
            "relation_type": relation_type,
            "target_id": str(target_id),
            "confidence": 1.0,
            "evidence_summary": (
                f"Ontology hierarchy: {child_term_id} is_a {parent_term_id}"
            ),
            "evidence_sentence": evidence_sentence,
            "evidence_sentence_source": evidence_sentence_source,
            "evidence_sentence_confidence": evidence_sentence_confidence,
            "evidence_tier": "EXPERT_CURATED",
            "source_document_ref": f"ontology:{child_term_id.split(':')[0]}",
        }

        # Use the gateway's own _request method which handles auth correctly.
        # GraphApiGateway._request(method, path, content=...) returns httpx.Response.
        path = f"/v1/spaces/{space_id}/relations"
        self._gateway._request(  # type: ignore[attr-defined]  # noqa: SLF001
            "POST",
            path,
            content=json.dumps(payload),
        )

    def _add_identifier_raw(
        self,
        *,
        space_id: UUID,
        entity_id: UUID,
        namespace: str,
        identifier_value: str,
    ) -> None:
        """Add a cross-reference identifier to an entity via the graph API."""
        import json

        payload = {"identifiers": {namespace: identifier_value}}
        path = f"/v1/spaces/{space_id}/entities/{entity_id}"
        self._gateway._request(  # type: ignore[attr-defined]  # noqa: SLF001
            "PUT",
            path,
            content=json.dumps(payload),
        )


def _extract_entity_id(result: object) -> UUID | None:
    """Extract entity UUID from a GraphApiGateway.create_entity response."""
    if isinstance(result, dict):
        # Direct response: {"id": "...", ...}
        raw_id = result.get("id")
        if raw_id is not None:
            return UUID(str(raw_id))
        # Wrapped response: {"entity": {"id": "..."}, "created": true}
        entity = result.get("entity")
        if isinstance(entity, dict):
            raw_id = entity.get("id")
            if raw_id is not None:
                return UUID(str(raw_id))
    return None


__all__ = ["GraphOntologyEntityWriter"]
