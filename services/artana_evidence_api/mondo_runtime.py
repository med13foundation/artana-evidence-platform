"""Service-local MONDO ontology fetch, parse, and ingestion runtime."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, cast
from uuid import UUID, uuid4

import httpx
from artana_evidence_api.types.common import JSONObject
from artana_evidence_api.types.graph_contracts import KernelRelationCreateRequest
from artana_evidence_api.types.graph_fact_assessment import (
    FactAssessment,
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    SupportBand,
)

logger = logging.getLogger(__name__)

_MONDO_STABLE_OBO_URL = "https://purl.obolibrary.org/obo/mondo.obo"
_MONDO_FALLBACK_URL = (
    "https://github.com/monarch-initiative/mondo/releases/latest/download/mondo.obo"
)
_MONDO_ID_PREFIX = "MONDO:"
_BATCH_CHUNK_SIZE = 200


@dataclass(frozen=True, slots=True)
class OntologyTerm:
    """One parsed ontology term from an OBO release."""

    id: str
    name: str
    definition: str = ""
    synonyms: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    xrefs: tuple[str, ...] = ()
    is_obsolete: bool = False
    namespace: str = ""
    comment: str = ""


@dataclass(frozen=True, slots=True)
class OntologyRelease:
    """Metadata about one ontology release."""

    version: str
    download_url: str
    format: str = "obo"
    release_date: str | None = None


@dataclass(frozen=True, slots=True)
class OntologyFetchResult:
    """Result of fetching and parsing one ontology release."""

    terms: list[OntologyTerm]
    release: OntologyRelease
    fetched_term_count: int
    checkpoint_after: JSONObject


@dataclass(frozen=True, slots=True)
class MondoIngestionSummary:
    """Research-init compatible summary of one MONDO loader run."""

    source_id: str
    ingestion_job_id: UUID
    release_version: str = ""
    terms_fetched: int = 0
    terms_imported: int = 0
    entities_created: int = 0
    entities_updated: int = 0
    alias_candidates_count: int = 0
    aliases_registered: int = 0
    aliases_persisted: int = 0
    aliases_skipped: int = 0
    alias_entities_touched: int = 0
    alias_errors: tuple[str, ...] = ()
    aliases_persisted_by_namespace_entity_type: dict[str, int] = field(
        default_factory=dict,
    )
    hierarchy_edges: int = 0
    hierarchy_edges_created: int = 0
    xref_edges_created: int = 0
    skipped_obsolete: int = 0
    checkpoint_after: JSONObject = field(default_factory=dict)


class OntologyGatewayProtocol(Protocol):
    """Ontology gateway surface consumed by the ingestion service."""

    async def fetch_release(
        self,
        *,
        version: str | None = None,
        format_preference: str = "obo",
        namespace_filter: str | None = None,
        max_terms: int | None = None,
    ) -> OntologyFetchResult: ...


class OntologyEntityWriterProtocol(Protocol):
    """Graph writer surface used by the service-local ontology loader."""

    def supports_batch_upsert(self) -> bool: ...

    def upsert_term(
        self,
        *,
        term: OntologyTerm,
        entity_type: str,
        research_space_id: str | None,
    ) -> bool: ...

    def upsert_terms_batch(
        self,
        *,
        terms: list[tuple[OntologyTerm, str]],
        research_space_id: str | None,
    ) -> int: ...

    def register_alias(self, *, term_id: str, alias: str) -> bool: ...

    def persist_hierarchy_edge(
        self,
        *,
        child_term_id: str,
        parent_term_id: str,
        research_space_id: str | None,
    ) -> bool: ...

    def persist_xref_edge(
        self,
        *,
        term_id: str,
        xref: str,
        research_space_id: str | None,
    ) -> bool: ...


class MondoGateway:
    """Fetch and parse the Monarch Disease Ontology OBO release."""

    def __init__(self, *, preloaded_content: str | None = None) -> None:
        self._preloaded_content = preloaded_content

    async def fetch_release(
        self,
        *,
        version: str | None = None,
        format_preference: str = "obo",
        namespace_filter: str | None = None,
        max_terms: int | None = None,
    ) -> OntologyFetchResult:
        """Fetch MONDO and keep only real ``MONDO:`` disease terms."""
        del namespace_filter
        if self._preloaded_content is not None:
            content = self._preloaded_content
            release_version = version or "preloaded"
            download_url = "preloaded://memory"
        else:
            content, release_version, download_url = await self._fetch_obo(
                version=version,
            )

        terms = [
            term
            for term in parse_obo_terms(content)
            if term.id.startswith(_MONDO_ID_PREFIX)
        ]
        if max_terms is not None:
            terms = terms[: max(max_terms, 0)]

        release = OntologyRelease(
            version=release_version,
            download_url=download_url,
            format=format_preference,
        )
        checkpoint: JSONObject = {
            "release_version": release_version,
            "terms_fetched": len(terms),
        }
        return OntologyFetchResult(
            terms=terms,
            release=release,
            fetched_term_count=len(terms),
            checkpoint_after=checkpoint,
        )

    async def _fetch_obo(self, *, version: str | None = None) -> tuple[str, str, str]:
        """Fetch OBO content from the stable URL, then GitHub fallback."""
        resolved_version = version or "latest"
        async with httpx.AsyncClient(timeout=120) as client:
            try:
                response = await client.get(
                    _MONDO_STABLE_OBO_URL,
                    follow_redirects=True,
                )
                response.raise_for_status()
            except httpx.HTTPError:
                logger.warning("MONDO stable URL failed; trying GitHub fallback")
            else:
                return response.text, resolved_version, _MONDO_STABLE_OBO_URL
            response = await client.get(_MONDO_FALLBACK_URL, follow_redirects=True)
            response.raise_for_status()
            return response.text, resolved_version, _MONDO_FALLBACK_URL


class MondoIngestionService:
    """Import MONDO terms as graph-backed disease ontology entities."""

    def __init__(
        self,
        *,
        gateway: OntologyGatewayProtocol,
        entity_writer: OntologyEntityWriterProtocol | None = None,
    ) -> None:
        self._gateway = gateway
        self._entity_writer = entity_writer

    async def ingest(
        self,
        *,
        source_id: str,
        research_space_id: str,
    ) -> MondoIngestionSummary:
        """Run one MONDO loader pass and return research-init metrics."""
        result = await self._gateway.fetch_release()
        active_terms: list[OntologyTerm] = []
        skipped_obsolete = 0
        for term in result.terms:
            if term.is_obsolete:
                skipped_obsolete += 1
                continue
            active_terms.append(term)

        term_pairs = [(term, "DISEASE") for term in active_terms]
        entities_created = self._upsert_entities(
            term_pairs=term_pairs,
            research_space_id=research_space_id,
        )
        entities_updated = max(len(term_pairs) - entities_created, 0)

        alias_candidates_count = 0
        aliases_persisted = 0
        alias_entities_touched = 0
        hierarchy_edges = 0
        hierarchy_edges_created = 0
        xref_edges_created = 0

        for term in active_terms:
            aliases = _alias_labels_for_term(term)
            alias_candidates_count += len(aliases)
            persisted_for_term = self._register_aliases(term=term, aliases=aliases)
            aliases_persisted += persisted_for_term
            if aliases:
                alias_entities_touched += 1

            hierarchy_edges += len(term.parents)
            hierarchy_edges_created += self._persist_hierarchy_edges(
                term=term,
                research_space_id=research_space_id,
            )
            xref_edges_created += self._persist_xrefs(
                term=term,
                research_space_id=research_space_id,
            )

        checkpoint_after: JSONObject = {
            "release_version": result.release.version,
            "release_date": result.release.release_date,
            "terms_imported": len(active_terms),
            "format": result.release.format,
        }
        namespace_metrics = (
            {"MONDO:DISEASE": aliases_persisted} if aliases_persisted else {}
        )
        return MondoIngestionSummary(
            source_id=source_id,
            ingestion_job_id=uuid4(),
            release_version=result.release.version,
            terms_fetched=len(result.terms),
            terms_imported=len(active_terms),
            entities_created=entities_created,
            entities_updated=entities_updated,
            alias_candidates_count=alias_candidates_count,
            aliases_registered=alias_candidates_count,
            aliases_persisted=aliases_persisted,
            aliases_skipped=max(alias_candidates_count - aliases_persisted, 0),
            alias_entities_touched=alias_entities_touched,
            aliases_persisted_by_namespace_entity_type=namespace_metrics,
            hierarchy_edges=hierarchy_edges,
            hierarchy_edges_created=hierarchy_edges_created,
            xref_edges_created=xref_edges_created,
            skipped_obsolete=skipped_obsolete,
            checkpoint_after=checkpoint_after,
        )

    def _upsert_entities(
        self,
        *,
        term_pairs: list[tuple[OntologyTerm, str]],
        research_space_id: str,
    ) -> int:
        if self._entity_writer is None or not term_pairs:
            return 0
        if not self._entity_writer.supports_batch_upsert():
            return sum(
                1
                for term, entity_type in term_pairs
                if self._entity_writer.upsert_term(
                    term=term,
                    entity_type=entity_type,
                    research_space_id=research_space_id,
                )
            )

        created_total = 0
        for start in range(0, len(term_pairs), _BATCH_CHUNK_SIZE):
            chunk = term_pairs[start : start + _BATCH_CHUNK_SIZE]
            try:
                created_total += self._entity_writer.upsert_terms_batch(
                    terms=chunk,
                    research_space_id=research_space_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MONDO batch upsert chunk %d failed; falling back to per-term: %s",
                    start // _BATCH_CHUNK_SIZE,
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

    def _register_aliases(self, *, term: OntologyTerm, aliases: list[str]) -> int:
        if self._entity_writer is None:
            return 0
        return sum(
            1
            for alias in aliases
            if self._entity_writer.register_alias(term_id=term.id, alias=alias)
        )

    def _persist_hierarchy_edges(
        self,
        *,
        term: OntologyTerm,
        research_space_id: str,
    ) -> int:
        if self._entity_writer is None:
            return 0
        return sum(
            1
            for parent_id in term.parents
            if self._entity_writer.persist_hierarchy_edge(
                child_term_id=term.id,
                parent_term_id=parent_id,
                research_space_id=research_space_id,
            )
        )

    def _persist_xrefs(self, *, term: OntologyTerm, research_space_id: str) -> int:
        if self._entity_writer is None:
            return 0
        return sum(
            1
            for xref in term.xrefs
            if self._entity_writer.persist_xref_edge(
                term_id=term.id,
                xref=xref,
                research_space_id=research_space_id,
            )
        )


class ServiceGraphOntologyEntityWriter:
    """Persist MONDO entities and hierarchy through the service graph transport."""

    def __init__(self, *, graph_api_gateway: object, research_space_id: UUID) -> None:
        self._gateway = graph_api_gateway
        self._space_id = research_space_id
        self._entity_id_cache: dict[str, UUID] = {}
        self._term_name_cache: dict[str, str] = {}
        self._aliases_persisted_during_upsert: dict[str, set[str]] = {}

    def supports_batch_upsert(self) -> bool:
        """Return whether the graph gateway exposes the batch entity path."""
        return callable(
            getattr(self._privileged_gateway(), "create_entities_batch_direct", None),
        )

    def upsert_terms_batch(
        self,
        *,
        terms: list[tuple[OntologyTerm, str]],
        research_space_id: str | None,
    ) -> int:
        """Bulk-upsert ontology entities when the graph transport supports it."""
        create_batch = getattr(
            self._privileged_gateway(),
            "create_entities_batch_direct",
            None,
        )
        if not callable(create_batch):
            return self._upsert_terms_one_by_one(
                terms=terms,
                research_space_id=research_space_id,
            )

        entities = [
            _entity_payload_for_term(term=term, entity_type=entity_type)
            for term, entity_type in terms
        ]
        response = cast(
            "JSONObject",
            create_batch(
                space_id=research_space_id or self._space_id,
                entities=entities,
            ),
        )
        rows = response.get("results")
        if not isinstance(rows, list):
            msg = "MONDO batch entity response missing results list"
            raise TypeError(msg)
        if len(rows) != len(terms):
            msg = (
                "MONDO batch entity response length mismatch: "
                f"{len(rows)} for {len(terms)} requested terms"
            )
            raise RuntimeError(msg)

        created_count = 0
        for (term, _entity_type), row in zip(terms, rows, strict=True):
            entity_id = _extract_entity_id(row)
            if entity_id is None and isinstance(row, Mapping):
                entity_id = _extract_entity_id(row.get("entity"))
            if entity_id is None:
                continue
            self._cache_term(term=term, entity_id=entity_id)
            if _response_indicates_created(row):
                created_count += 1
        return created_count

    def upsert_term(
        self,
        *,
        term: OntologyTerm,
        entity_type: str,
        research_space_id: str | None,
    ) -> bool:
        """Upsert one ontology term through the best available gateway method."""
        payload = _entity_payload_for_term(term=term, entity_type=entity_type)
        response = self._call_entity_upsert(
            space_id=research_space_id or self._space_id,
            payload=payload,
        )
        if response is None:
            return False
        entity_id = _extract_entity_id(response)
        if entity_id is None and isinstance(response, Mapping):
            entity_id = _extract_entity_id(response.get("entity"))
        if entity_id is None:
            return False
        self._cache_term(term=term, entity_id=entity_id)
        return _response_indicates_created(response) or "created" not in response

    def register_alias(self, *, term_id: str, alias: str) -> bool:
        """Count aliases already persisted by the entity upsert payload."""
        normalized_alias = alias.strip()
        if not normalized_alias:
            return False
        pending_aliases = self._aliases_persisted_during_upsert.get(term_id)
        if pending_aliases is None or normalized_alias not in pending_aliases:
            return False
        pending_aliases.remove(normalized_alias)
        return True

    def persist_hierarchy_edge(
        self,
        *,
        child_term_id: str,
        parent_term_id: str,
        research_space_id: str | None,
    ) -> bool:
        """Persist one deterministic MONDO ``is_a`` hierarchy edge."""
        child_entity_id = self._entity_id_cache.get(child_term_id)
        parent_entity_id = self._entity_id_cache.get(parent_term_id)
        if child_entity_id is None or parent_entity_id is None:
            return False

        materialize_relation = getattr(
            self._privileged_gateway(),
            "materialize_relation_direct",
            None,
        )
        if not callable(materialize_relation):
            return False

        child_name = self._term_name_cache.get(child_term_id, child_term_id)
        parent_name = self._term_name_cache.get(parent_term_id, parent_term_id)
        try:
            materialize_relation(
                space_id=research_space_id or self._space_id,
                request=KernelRelationCreateRequest(
                    source_id=child_entity_id,
                    relation_type="INSTANCE_OF",
                    target_id=parent_entity_id,
                    assessment=FactAssessment(
                        support_band=SupportBand.STRONG,
                        grounding_level=GroundingLevel.DOCUMENT,
                        mapping_status=MappingStatus.RESOLVED,
                        speculation_level=SpeculationLevel.DIRECT,
                        confidence_rationale=(
                            "MONDO OBO hierarchy import; curated is_a edge."
                        ),
                    ),
                    evidence_summary=(
                        f"Ontology hierarchy: {child_term_id} is_a {parent_term_id}"
                    ),
                    evidence_sentence=(
                        f"{child_name} ({child_term_id}) is classified as a "
                        f"subtype of {parent_name} ({parent_term_id}) in MONDO."
                    ),
                    evidence_sentence_source="ontology_import_template",
                    evidence_sentence_confidence="high",
                    evidence_tier="EXPERT_CURATED",
                    source_document_ref="ontology:MONDO",
                    metadata={
                        "source": "MONDO",
                        "child_term_id": child_term_id,
                        "parent_term_id": parent_term_id,
                    },
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "MONDO hierarchy edge %s -> %s failed: %s",
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
        """Persist a MONDO xref as an identifier on the graph entity."""
        entity_id = self._entity_id_cache.get(term_id)
        if entity_id is None:
            return False
        namespace, identifier_value = _parse_xref(xref)
        if not identifier_value:
            return False

        update_entity = getattr(
            self._privileged_gateway(),
            "update_entity_direct",
            None,
        )
        if not callable(update_entity):
            return False
        try:
            update_entity(
                space_id=research_space_id or self._space_id,
                entity_id=entity_id,
                identifiers={namespace: identifier_value},
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("MONDO xref %s on %s failed: %s", xref, term_id, exc)
            return False
        return True

    def get_ai_sentence_stats(self) -> dict[str, dict[str, int]]:
        """Return AI evidence sentence stats; MONDO local runtime is template-only."""
        return {}

    def _cache_term(self, *, term: OntologyTerm, entity_id: UUID) -> None:
        self._entity_id_cache[term.id] = entity_id
        self._term_name_cache[term.id] = term.name
        self._aliases_persisted_during_upsert[term.id] = set(
            _alias_labels_for_term(term),
        )

    def _upsert_terms_one_by_one(
        self,
        *,
        terms: list[tuple[OntologyTerm, str]],
        research_space_id: str | None,
    ) -> int:
        return sum(
            1
            for term, entity_type in terms
            if self.upsert_term(
                term=term,
                entity_type=entity_type,
                research_space_id=research_space_id,
            )
        )

    def _call_entity_upsert(
        self,
        *,
        space_id: UUID | str,
        payload: JSONObject,
    ) -> JSONObject | None:
        upsert_entity = getattr(
            self._privileged_gateway(),
            "upsert_entity_direct",
            None,
        )
        if callable(upsert_entity):
            return cast(
                "JSONObject",
                upsert_entity(
                    space_id=space_id,
                    entity_type=str(payload["entity_type"]),
                    display_label=str(payload["display_label"]),
                    aliases=_string_list(payload.get("aliases")),
                    metadata=_object_or_none(payload.get("metadata")),
                    identifiers=_string_mapping_or_none(payload.get("identifiers")),
                ),
            )

        create_entity = getattr(self._gateway, "create_entity", None)
        if not callable(create_entity):
            return None
        try:
            return cast(
                "JSONObject",
                create_entity(
                    space_id=space_id,
                    entity_type=str(payload["entity_type"]),
                    display_label=str(payload["display_label"]),
                    aliases=_string_list(payload.get("aliases")),
                ),
            )
        except TypeError:
            return cast(
                "JSONObject",
                create_entity(
                    space_id=space_id,
                    entity_type=str(payload["entity_type"]),
                    display_label=str(payload["display_label"]),
                ),
            )

    def _privileged_gateway(self) -> object:
        privileged_transport = getattr(
            self._gateway,
            "privileged_mutation_transport",
            None,
        )
        if callable(privileged_transport):
            return privileged_transport()
        return self._gateway


def parse_obo_terms(content: str) -> list[OntologyTerm]:
    """Parse OBO flat-file content into ontology terms."""
    terms: list[OntologyTerm] = []
    for block in content.split("[Term]"):
        block_content = block.strip()
        if not block_content:
            continue
        fields: dict[str, str | list[str]] = {}
        for raw_line in block_content.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            if line.startswith("["):
                break
            key, _, value = line.partition(":")
            normalized_key = key.strip()
            normalized_value = value.strip()
            if not normalized_key or not normalized_value:
                continue
            existing = fields.get(normalized_key)
            if existing is None:
                fields[normalized_key] = normalized_value
            elif isinstance(existing, list):
                existing.append(normalized_value)
            else:
                fields[normalized_key] = [existing, normalized_value]

        term_id = _scalar(fields.get("id"))
        if not term_id:
            continue
        terms.append(
            OntologyTerm(
                id=term_id,
                name=_scalar(fields.get("name")) or "",
                definition=_strip_obo_quotes(_scalar(fields.get("def")) or ""),
                synonyms=tuple(
                    _strip_obo_quotes(synonym)
                    for synonym in _as_list(fields.get("synonym"))
                    if synonym.strip()
                ),
                parents=tuple(
                    _extract_term_id(parent)
                    for parent in _as_list(fields.get("is_a"))
                    if parent.strip()
                ),
                xrefs=tuple(
                    xref.strip()
                    for xref in _as_list(fields.get("xref"))
                    if xref.strip()
                ),
                is_obsolete=(
                    (_scalar(fields.get("is_obsolete")) or "false")
                    .strip()
                    .lower()
                    == "true"
                ),
                namespace="MONDO" if term_id.startswith(_MONDO_ID_PREFIX) else "",
                comment=_scalar(fields.get("comment")) or "",
            ),
        )
    return terms


def _entity_payload_for_term(*, term: OntologyTerm, entity_type: str) -> JSONObject:
    metadata: JSONObject = {
        "ontology_namespace": term.namespace or "MONDO",
        "ontology_term_id": term.id,
        "definition": term.definition,
        "source": "MONDO",
    }
    identifiers = _term_identifier_mapping(term.id)
    payload: JSONObject = {
        "entity_type": entity_type,
        "display_label": term.name,
        "aliases": _alias_labels_for_term(term),
        "metadata": metadata,
        "identifiers": identifiers,
    }
    return payload


def _alias_labels_for_term(term: OntologyTerm) -> list[str]:
    aliases: list[str] = []
    seen: set[str] = set()
    for synonym in term.synonyms:
        alias = synonym.strip()
        if not alias or alias in seen:
            continue
        seen.add(alias)
        aliases.append(alias)
    return aliases


def _extract_entity_id(payload: object) -> UUID | None:
    if not isinstance(payload, Mapping):
        return None
    candidate = payload.get("id")
    if isinstance(candidate, UUID):
        return candidate
    if isinstance(candidate, str) and candidate.strip():
        try:
            return UUID(candidate)
        except ValueError:
            return None
    nested = payload.get("entity")
    if nested is payload:
        return None
    return _extract_entity_id(nested)


def _response_indicates_created(payload: object) -> bool:
    return isinstance(payload, Mapping) and payload.get("created") is True


def _term_identifier_mapping(term_id: str) -> dict[str, str]:
    namespace, identifier_value = _parse_xref(term_id)
    if not identifier_value:
        return {}
    return {namespace: identifier_value}


def _parse_xref(xref: str) -> tuple[str, str]:
    stripped = xref.strip()
    if ":" not in stripped:
        return "XREF", stripped
    namespace, _, value = stripped.partition(":")
    return namespace.strip(), value.strip()


def _scalar(value: str | list[str] | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _as_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _strip_obo_quotes(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith('"'):
        end_quote = stripped.find('"', 1)
        if end_quote > 0:
            return stripped[1:end_quote]
    return stripped


def _extract_term_id(is_a_value: str) -> str:
    value, _, _label = is_a_value.partition("!")
    return value.strip()


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return None
    strings = [item for item in value if isinstance(item, str)]
    return strings or None


def _object_or_none(value: object) -> JSONObject | None:
    return cast("JSONObject", value) if isinstance(value, dict) else None


def _string_mapping_or_none(value: object) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    result = {
        str(key): str(item)
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }
    return result or None


__all__ = [
    "MondoGateway",
    "MondoIngestionService",
    "MondoIngestionSummary",
    "OntologyFetchResult",
    "OntologyRelease",
    "OntologyTerm",
    "ServiceGraphOntologyEntityWriter",
    "parse_obo_terms",
]
