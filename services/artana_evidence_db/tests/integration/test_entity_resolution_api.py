"""Focused integration coverage for deterministic graph-service entity resolution."""

from __future__ import annotations

from uuid import uuid4

from artana_evidence_db import database as graph_database
from artana_evidence_db.entity_resolution import normalize_entity_match_text
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.tests import support as graph_service_support
from artana_evidence_db.tests.support import admin_headers, build_seeded_space_fixture

graph_client = graph_service_support.graph_client

_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic integration evidence supports this claim.",
}


def test_entity_create_resolves_by_label_alias_and_alias_search(graph_client) -> None:
    fixture = build_seeded_space_fixture(slug_prefix="entity-resolution")
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13",
            "aliases": ["THRAP1"],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert create_response.status_code == 201, create_response.text
    created_payload = create_response.json()
    assert created_payload["created"] is True
    created_entity_id = created_payload["entity"]["id"]
    assert set(created_payload["entity"]["aliases"]) >= {"MED13", "THRAP1"}

    lower_label_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": " med13 ",
            "metadata": {},
            "identifiers": {},
        },
    )
    assert lower_label_response.status_code == 201, lower_label_response.text
    lower_label_payload = lower_label_response.json()
    assert lower_label_payload["created"] is False
    assert lower_label_payload["entity"]["id"] == created_entity_id

    alias_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "THRAP1",
            "metadata": {},
            "identifiers": {},
        },
    )
    assert alias_response.status_code == 201, alias_response.text
    alias_payload = alias_response.json()
    assert alias_payload["created"] is False
    assert alias_payload["entity"]["id"] == created_entity_id

    search_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        params={"q": "thrap1"},
    )
    assert search_response.status_code == 200, search_response.text
    search_payload = search_response.json()
    assert search_payload["total"] == 1
    assert search_payload["entities"][0]["id"] == created_entity_id
    assert "THRAP1" in search_payload["entities"][0]["aliases"]


def test_entity_create_rejects_missing_required_strict_match_anchors(
    graph_client,
) -> None:
    fixture = build_seeded_space_fixture(slug_prefix="strict-match")
    response = graph_client.post(
        f"/v1/spaces/{fixture['space_id']}/entities",
        headers=fixture["headers"],
        json={
            "entity_type": "PATIENT",
            "display_label": "Patient 1",
            "metadata": {},
            "identifiers": {"mrn": "patient-1"},
        },
    )

    assert response.status_code == 400, response.text
    assert "issuer" in response.json()["detail"]


def test_entity_create_rejects_conflicting_identifier_anchor_matches(
    graph_client,
) -> None:
    fixture = build_seeded_space_fixture(slug_prefix="identifier-conflict")
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    first_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13",
            "metadata": {},
            "identifiers": {"hgnc_id": "HGNC:1234"},
        },
    )
    assert first_response.status_code == 201, first_response.text

    second_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "THRAP1",
            "metadata": {},
            "identifiers": {"ensembl_id": "ENSG00000123066"},
        },
    )
    assert second_response.status_code == 201, second_response.text

    conflict_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "Conflict probe",
            "metadata": {},
            "identifiers": {
                "hgnc_id": " hgnc:1234 ",
                "ensembl_id": "ensg00000123066",
            },
        },
    )

    assert conflict_response.status_code == 409, conflict_response.text
    assert "Ambiguous exact match" in conflict_response.json()["detail"]


def test_entity_create_rejects_conflicting_alias_anchor_matches(graph_client) -> None:
    fixture = build_seeded_space_fixture(slug_prefix="alias-conflict")
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    alias_a = f"THRAP1-{uuid4().hex[:6]}"
    alias_b = f"TRAPPC9-{uuid4().hex[:6]}"

    first_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13",
            "aliases": [alias_a],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert first_response.status_code == 201, first_response.text

    second_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "BRCA1",
            "aliases": [alias_b],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert second_response.status_code == 201, second_response.text

    conflict_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "Novel candidate",
            "aliases": [alias_a.lower(), alias_b.lower()],
            "metadata": {},
            "identifiers": {},
        },
    )

    assert conflict_response.status_code == 409, conflict_response.text
    assert "Ambiguous exact match" in conflict_response.json()["detail"]


def test_entity_lookup_returns_conflict_for_ambiguous_exact_label(graph_client) -> None:
    fixture = build_seeded_space_fixture(slug_prefix="ambiguous-label")
    space_id = fixture["space_id"]

    with graph_database.SessionLocal() as session:
        session.add_all(
            [
                EntityModel(
                    id=uuid4(),
                    research_space_id=space_id,
                    entity_type="GENE",
                    display_label="MED13",
                    display_label_normalized=normalize_entity_match_text("MED13"),
                    metadata_payload={},
                ),
                EntityModel(
                    id=uuid4(),
                    research_space_id=space_id,
                    entity_type="GENE",
                    display_label="MED13",
                    display_label_normalized=normalize_entity_match_text("MED13"),
                    metadata_payload={},
                ),
            ],
        )
        session.commit()

    response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=fixture["headers"],
        json={
            "entity_type": "GENE",
            "display_label": "med13",
            "metadata": {},
            "identifiers": {},
        },
    )

    assert response.status_code == 409, response.text
    assert "Ambiguous exact match" in response.json()["detail"]


def test_relation_claim_creation_canonicalizes_relation_synonyms(graph_client) -> None:
    fixture = build_seeded_space_fixture(slug_prefix="claim-canonical")
    admin = admin_headers()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    suffix = uuid4().hex[:8]
    relation_type_id = f"GS_REL_{suffix}".upper()
    relation_synonym = f"links_{suffix.lower()}"

    source_entity_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13",
            "metadata": {},
            "identifiers": {},
        },
    )
    assert source_entity_response.status_code == 201, source_entity_response.text
    source_entity_id = source_entity_response.json()["entity"]["id"]

    target_entity_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "PHENOTYPE",
            "display_label": "Developmental delay",
            "metadata": {},
            "identifiers": {},
        },
    )
    assert target_entity_response.status_code == 201, target_entity_response.text
    target_entity_id = target_entity_response.json()["entity"]["id"]

    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin,
        json={
            "id": relation_type_id,
            "display_name": f"Relates To {suffix}",
            "description": "Deterministic relation synonym integration test.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Inverse {suffix}",
            "source_ref": "graph-service-entity-resolution-test",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text

    relation_synonym_response = graph_client.post(
        "/v1/dictionary/relation-synonyms",
        headers=admin,
        json={
            "relation_type_id": relation_type_id,
            "synonym": relation_synonym,
            "source": "manual",
            "source_ref": "graph-service-entity-resolution-test",
        },
    )
    assert relation_synonym_response.status_code == 201, relation_synonym_response.text

    relation_constraint_response = graph_client.post(
        "/v1/dictionary/relation-constraints",
        headers=admin,
        json={
            "source_type": "GENE",
            "relation_type": relation_type_id,
            "target_type": "PHENOTYPE",
            "is_allowed": True,
            "requires_evidence": True,
            "source_ref": "graph-service-entity-resolution-test",
        },
    )
    assert (
        relation_constraint_response.status_code == 201
    ), relation_constraint_response.text

    claim_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=headers,
        json={
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "relation_type": relation_synonym,
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "Synthetic synonym-backed relation claim.",
            "evidence_summary": "Curated support evidence.",
            "source_document_ref": "doi:10.0000/test-graph-service",
            "metadata": {},
        },
    )
    assert claim_response.status_code == 201, claim_response.text
    assert claim_response.json()["relation_type"] == relation_type_id


def test_entities_batch_creates_multiple_entities_in_one_request(graph_client) -> None:
    """The batch endpoint creates many entities in a single transaction."""
    fixture = build_seeded_space_fixture(slug_prefix="entity-batch")
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    response = graph_client.post(
        f"/v1/spaces/{space_id}/entities/batch",
        headers=headers,
        json={
            "entities": [
                {
                    "entity_type": "GENE",
                    "display_label": "BatchGene1",
                    "aliases": ["BG1"],
                    "metadata": {},
                    "identifiers": {},
                },
                {
                    "entity_type": "GENE",
                    "display_label": "BatchGene2",
                    "aliases": ["BG2"],
                    "metadata": {},
                    "identifiers": {},
                },
                {
                    "entity_type": "GENE",
                    "display_label": "BatchGene3",
                    "aliases": [],
                    "metadata": {},
                    "identifiers": {},
                },
            ],
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["created_count"] == 3
    assert payload["resolved_count"] == 0
    assert len(payload["results"]) == 3
    labels = {row["entity"]["display_label"] for row in payload["results"]}
    assert labels == {"BatchGene1", "BatchGene2", "BatchGene3"}
    for row in payload["results"]:
        assert row["created"] is True


def test_entities_batch_resolves_existing_entities_via_aliases(graph_client) -> None:
    """Repeated batch entries against existing aliases resolve, not duplicate."""
    fixture = build_seeded_space_fixture(slug_prefix="entity-batch-resolve")
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    seed_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13",
            "aliases": ["THRAP1"],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert seed_response.status_code == 201
    seeded_entity_id = seed_response.json()["entity"]["id"]

    batch_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities/batch",
        headers=headers,
        json={
            "entities": [
                {
                    "entity_type": "GENE",
                    "display_label": "med13",  # case-insensitive label match
                    "metadata": {},
                    "identifiers": {},
                },
                {
                    "entity_type": "GENE",
                    "display_label": "THRAP1",  # alias of MED13
                    "metadata": {},
                    "identifiers": {},
                },
                {
                    "entity_type": "GENE",
                    "display_label": "BrandNewGene",
                    "metadata": {},
                    "identifiers": {},
                },
            ],
        },
    )

    assert batch_response.status_code == 201, batch_response.text
    payload = batch_response.json()
    assert payload["created_count"] == 1
    assert payload["resolved_count"] == 2
    # First two rows resolve to the seeded entity
    assert payload["results"][0]["created"] is False
    assert payload["results"][0]["entity"]["id"] == seeded_entity_id
    assert payload["results"][1]["created"] is False
    assert payload["results"][1]["entity"]["id"] == seeded_entity_id
    # Third row creates the new entity
    assert payload["results"][2]["created"] is True
    assert payload["results"][2]["entity"]["display_label"] == "BrandNewGene"


def test_create_entity_rejects_conflicting_aliases(graph_client) -> None:
    """Single-entity writes still fail fast on conflicting aliases."""
    fixture = build_seeded_space_fixture(slug_prefix="entity-alias-conflict-single")
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    seed_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "PATIENT",
            "display_label": "Seed Patient",
            "aliases": ["shared-cohort-alias"],
            "metadata": {},
            "identifiers": {"mrn": "seed-1", "issuer": "hospital-a"},
        },
    )
    assert seed_response.status_code == 201, seed_response.text

    response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "PATIENT",
            "display_label": "New Patient",
            "aliases": ["shared-cohort-alias", "unique-cohort-alias"],
            "metadata": {},
            "identifiers": {"mrn": "seed-2", "issuer": "hospital-b"},
        },
    )

    assert response.status_code == 409, response.text
    assert "already assigned to another entity" in response.json()["detail"]


def test_entities_batch_skips_conflicting_aliases_without_rolling_back(
    graph_client,
) -> None:
    """Batch writes keep the entity row and drop only the conflicting aliases."""
    fixture = build_seeded_space_fixture(slug_prefix="entity-batch-alias-conflict")
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    seed_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "PATIENT",
            "display_label": "Seed Patient",
            "aliases": ["shared-cohort-alias"],
            "metadata": {},
            "identifiers": {"mrn": "seed-1", "issuer": "hospital-a"},
        },
    )
    assert seed_response.status_code == 201, seed_response.text

    batch_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities/batch",
        headers=headers,
        json={
            "entities": [
                {
                    "entity_type": "PATIENT",
                    "display_label": "New Patient",
                    "aliases": ["shared-cohort-alias", "unique-cohort-alias"],
                    "metadata": {},
                    "identifiers": {"mrn": "seed-2", "issuer": "hospital-b"},
                },
            ],
        },
    )

    assert batch_response.status_code == 201, batch_response.text
    payload = batch_response.json()
    assert payload["created_count"] == 1
    assert payload["resolved_count"] == 0
    row = payload["results"][0]
    assert row["created"] is True
    assert row["entity"]["display_label"] == "New Patient"
    assert "unique-cohort-alias" in row["entity"]["aliases"]
    assert "shared-cohort-alias" not in row["entity"]["aliases"]


def test_entities_batch_rolls_back_on_validation_error(graph_client) -> None:
    """A bad entry aborts the whole transaction — no partial writes."""
    fixture = build_seeded_space_fixture(slug_prefix="entity-batch-rollback")
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    response = graph_client.post(
        f"/v1/spaces/{space_id}/entities/batch",
        headers=headers,
        json={
            "entities": [
                {
                    "entity_type": "GENE",
                    "display_label": "WouldBeCreated",
                    "metadata": {},
                    "identifiers": {},
                },
                {
                    # NOT_A_REAL_TYPE has no resolution policy → ValueError
                    "entity_type": "NOT_A_REAL_TYPE",
                    "display_label": "Bad",
                    "metadata": {},
                    "identifiers": {},
                },
            ],
        },
    )

    assert response.status_code == 400, response.text

    # Verify the first (valid) entry was rolled back — search by label.
    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        params={"q": "WouldBeCreated"},
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 0


def test_entities_batch_rejects_empty_payload(graph_client) -> None:
    """An empty entities list is a 422 from pydantic validation."""
    fixture = build_seeded_space_fixture(slug_prefix="entity-batch-empty")
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    response = graph_client.post(
        f"/v1/spaces/{space_id}/entities/batch",
        headers=headers,
        json={"entities": []},
    )
    assert response.status_code == 422, response.text
