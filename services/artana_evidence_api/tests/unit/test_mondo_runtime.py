"""Unit coverage for the service-local MONDO runtime."""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_api.mondo_runtime import (
    MondoGateway,
    MondoIngestionService,
    OntologyTerm,
    ServiceGraphOntologyEntityWriter,
)

_SAMPLE_MONDO_OBO = """
format-version: 1.2

[Term]
id: MONDO:0000001
name: disease
def: "A disease is a disposition to undergo pathological processes." [MONDO:patterns]
synonym: "disorder" EXACT []
xref: OMIM:000001

[Term]
id: MONDO:0000002
name: inherited disease
def: "A disease caused by genetic variation." [MONDO:patterns]
synonym: "heritable disorder" EXACT []
is_a: MONDO:0000001 ! disease
xref: DOID:630

[Term]
id: HP:0001250
name: Seizure

[Term]
id: MONDO:9999999
name: obsolete MONDO disease
is_obsolete: true
""".strip()


class _RecordingOntologyWriter:
    def __init__(self) -> None:
        self.term_ids: set[str] = set()
        self.aliases: list[tuple[str, str]] = []
        self.hierarchy_edges: list[tuple[str, str]] = []
        self.xrefs: list[tuple[str, str]] = []

    def supports_batch_upsert(self) -> bool:
        return True

    def upsert_term(
        self,
        *,
        term: OntologyTerm,
        entity_type: str,
        research_space_id: str | None,
    ) -> bool:
        del entity_type, research_space_id
        self.term_ids.add(term.id)
        return True

    def upsert_terms_batch(
        self,
        *,
        terms: list[tuple[OntologyTerm, str]],
        research_space_id: str | None,
    ) -> int:
        del research_space_id
        for term, _entity_type in terms:
            self.term_ids.add(term.id)
        return len(terms)

    def register_alias(self, *, term_id: str, alias: str) -> bool:
        self.aliases.append((term_id, alias))
        return True

    def persist_hierarchy_edge(
        self,
        *,
        child_term_id: str,
        parent_term_id: str,
        research_space_id: str | None,
    ) -> bool:
        del research_space_id
        if child_term_id not in self.term_ids or parent_term_id not in self.term_ids:
            return False
        self.hierarchy_edges.append((child_term_id, parent_term_id))
        return True

    def persist_xref_edge(
        self,
        *,
        term_id: str,
        xref: str,
        research_space_id: str | None,
    ) -> bool:
        del research_space_id
        self.xrefs.append((term_id, xref))
        return True


class _BatchGraphGateway:
    def __init__(self) -> None:
        self.entities: list[dict[str, object]] = []
        self.relations: list[object] = []
        self.identifier_updates: list[dict[str, object]] = []

    def create_entities_batch_direct(
        self,
        *,
        space_id: str,
        entities: list[dict[str, object]],
    ) -> dict[str, object]:
        del space_id
        self.entities.extend(entities)
        return {
            "results": [
                {
                    "entity": {"id": str(uuid4())},
                    "created": True,
                }
                for _entity in entities
            ],
        }

    def materialize_relation_direct(self, *, space_id: str, request: object) -> object:
        del space_id
        self.relations.append(request)
        return request

    def update_entity_direct(
        self,
        *,
        space_id: str,
        entity_id: object,
        identifiers: dict[str, str],
    ) -> dict[str, object]:
        del space_id
        self.identifier_updates.append(
            {"entity_id": entity_id, "identifiers": identifiers},
        )
        return {"id": str(entity_id)}


@pytest.mark.asyncio
async def test_mondo_gateway_filters_to_mondo_terms_and_preserves_obo_fields() -> None:
    gateway = MondoGateway(preloaded_content=_SAMPLE_MONDO_OBO)

    result = await gateway.fetch_release()

    assert [term.id for term in result.terms] == [
        "MONDO:0000001",
        "MONDO:0000002",
        "MONDO:9999999",
    ]
    inherited = result.terms[1]
    assert inherited.namespace == "MONDO"
    assert inherited.definition == "A disease caused by genetic variation."
    assert inherited.synonyms == ("heritable disorder",)
    assert inherited.parents == ("MONDO:0000001",)
    assert inherited.xrefs == ("DOID:630",)
    assert result.fetched_term_count == 3


@pytest.mark.asyncio
async def test_mondo_ingestion_counts_terms_aliases_hierarchy_and_xrefs() -> None:
    writer = _RecordingOntologyWriter()
    service = MondoIngestionService(
        gateway=MondoGateway(preloaded_content=_SAMPLE_MONDO_OBO),
        entity_writer=writer,
    )

    summary = await service.ingest(
        source_id=str(uuid4()),
        research_space_id=str(uuid4()),
    )

    assert summary.terms_fetched == 3
    assert summary.terms_imported == 2
    assert summary.skipped_obsolete == 1
    assert summary.entities_created == 2
    assert summary.alias_candidates_count == 2
    assert summary.aliases_persisted == 2
    assert summary.hierarchy_edges == 1
    assert summary.hierarchy_edges_created == 1
    assert summary.xref_edges_created == 2
    assert writer.hierarchy_edges == [("MONDO:0000002", "MONDO:0000001")]


@pytest.mark.asyncio
async def test_service_graph_writer_uses_batch_gateway_for_mondo_entities() -> None:
    gateway = _BatchGraphGateway()
    writer = ServiceGraphOntologyEntityWriter(
        graph_api_gateway=gateway,
        research_space_id=uuid4(),
    )
    service = MondoIngestionService(
        gateway=MondoGateway(preloaded_content=_SAMPLE_MONDO_OBO),
        entity_writer=writer,
    )

    summary = await service.ingest(
        source_id=str(uuid4()),
        research_space_id=str(uuid4()),
    )

    assert summary.entities_created == 2
    assert summary.hierarchy_edges_created == 1
    assert summary.xref_edges_created == 2
    assert len(gateway.entities) == 2
    assert gateway.entities[0]["entity_type"] == "DISEASE"
    assert gateway.entities[0]["identifiers"] == {"MONDO": "0000001"}
    assert len(gateway.relations) == 1
    assert len(gateway.identifier_updates) == 2
