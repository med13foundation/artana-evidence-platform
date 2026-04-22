"""End-to-end graph-service workflow coverage for deterministic resolution."""

from __future__ import annotations

from uuid import uuid4

from artana_evidence_db.app import create_app
from artana_evidence_db.tests import support as graph_service_support
from artana_evidence_db.tests.support import (
    admin_headers,
    build_graph_admin_headers,
    build_graph_auth_headers,
    build_seeded_space_fixture,
    reset_graph_service_database,
    seed_graph_service_dictionary_primitives,
)
from artana_evidence_db.user_models import UserRole
from fastapi.testclient import TestClient

graph_client = graph_service_support.graph_client

_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic e2e evidence directly supports the relation.",
}


def test_owner_entity_workflow_and_admin_relation_canonicalization(
    graph_client,
) -> None:
    fixture = build_seeded_space_fixture(slug_prefix="graph-e2e")
    owner_headers = fixture["headers"]
    space_id = fixture["space_id"]
    admin = admin_headers()
    suffix = uuid4().hex[:8]
    relation_type_id = f"GS_E2E_REL_{suffix}".upper()
    relation_synonym = f"modulates_{suffix.lower()}"

    source_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=owner_headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13",
            "aliases": ["THRAP1"],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert source_response.status_code == 201, source_response.text
    source_entity = source_response.json()["entity"]

    alias_lookup_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=owner_headers,
        json={
            "entity_type": "GENE",
            "display_label": "THRAP1",
            "metadata": {},
            "identifiers": {},
        },
    )
    assert alias_lookup_response.status_code == 201, alias_lookup_response.text
    assert alias_lookup_response.json()["created"] is False
    assert alias_lookup_response.json()["entity"]["id"] == source_entity["id"]

    target_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=owner_headers,
        json={
            "entity_type": "PHENOTYPE",
            "display_label": "Developmental delay",
            "metadata": {},
            "identifiers": {},
        },
    )
    assert target_response.status_code == 201, target_response.text
    target_entity = target_response.json()["entity"]

    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin,
        json={
            "id": relation_type_id,
            "display_name": f"Graph E2E Relation {suffix}",
            "description": "E2E relation type for standalone graph-service tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Inverse {suffix}",
            "source_ref": "graph-service-e2e",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text

    synonym_response = graph_client.post(
        "/v1/dictionary/relation-synonyms",
        headers=admin,
        json={
            "relation_type_id": relation_type_id,
            "synonym": relation_synonym,
            "source": "manual",
            "source_ref": "graph-service-e2e",
        },
    )
    assert synonym_response.status_code == 201, synonym_response.text

    constraint_response = graph_client.post(
        "/v1/dictionary/relation-constraints",
        headers=admin,
        json={
            "source_type": "GENE",
            "relation_type": relation_type_id,
            "target_type": "PHENOTYPE",
            "is_allowed": True,
            "requires_evidence": True,
            "source_ref": "graph-service-e2e",
        },
    )
    assert constraint_response.status_code == 201, constraint_response.text

    relation_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin,
        json={
            "source_id": source_entity["id"],
            "target_id": target_entity["id"],
            "relation_type": relation_synonym,
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_summary": "Synthetic end-to-end evidence summary.",
            "source_document_ref": "doi:10.0000/graph-e2e",
        },
    )
    assert relation_response.status_code == 201, relation_response.text
    relation_payload = relation_response.json()
    assert relation_payload["relation_type"] == relation_type_id

    relation_list_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=owner_headers,
        params={"relation_type": relation_type_id},
    )
    assert relation_list_response.status_code == 200, relation_list_response.text
    relation_list_payload = relation_list_response.json()
    assert relation_list_payload["total"] == 1
    assert relation_list_payload["relations"][0]["source_id"] == source_entity["id"]
    assert relation_list_payload["relations"][0]["target_id"] == target_entity["id"]
    assert relation_list_payload["relations"][0]["relation_type"] == relation_type_id


def test_graph_service_write_and_read_workflow_end_to_end() -> None:
    reset_graph_service_database()
    try:
        with TestClient(create_app()) as client:
            graph_admin_headers = build_graph_admin_headers()
            owner_id = uuid4()
            member_id = uuid4()
            space_id = uuid4()

            create_space_response = client.put(
                f"/v1/admin/spaces/{space_id}",
                headers=graph_admin_headers,
                json={
                    "slug": f"graph-e2e-{space_id.hex[:8]}",
                    "name": "Graph E2E Space",
                    "description": "Standalone graph-service e2e workflow space.",
                    "owner_id": str(owner_id),
                    "status": "active",
                    "settings": {"review_threshold": 0.8},
                },
            )
            assert create_space_response.status_code == 200, create_space_response.text

            membership_response = client.put(
                f"/v1/admin/spaces/{space_id}/memberships/{member_id}",
                headers=graph_admin_headers,
                json={"role": "researcher", "is_active": True},
            )
            assert membership_response.status_code == 200, membership_response.text
            seed_graph_service_dictionary_primitives()

            member_headers = build_graph_auth_headers(
                user_id=member_id,
                email=f"graph-member-{member_id.hex[:10]}@example.com",
                role=UserRole.RESEARCHER,
            )

            source_entity_response = client.post(
                f"/v1/spaces/{space_id}/entities",
                headers=member_headers,
                json={
                    "entity_type": "GENE",
                    "display_label": "MED13",
                    "metadata": {"source": "graph-e2e"},
                    "identifiers": {"hgnc_id": f"HGNC:{uuid4().hex[:8]}"},
                },
            )
            assert (
                source_entity_response.status_code == 201
            ), source_entity_response.text
            source_entity_id = source_entity_response.json()["entity"]["id"]

            target_entity_response = client.post(
                f"/v1/spaces/{space_id}/entities",
                headers=member_headers,
                json={
                    "entity_type": "PHENOTYPE",
                    "display_label": "Developmental delay",
                    "metadata": {"source": "graph-e2e"},
                    "identifiers": {"mesh_id": f"MESH:{uuid4().hex[:8]}"},
                },
            )
            assert (
                target_entity_response.status_code == 201
            ), target_entity_response.text
            target_entity_id = target_entity_response.json()["entity"]["id"]

            create_relation_response = client.post(
                f"/v1/spaces/{space_id}/relations",
                headers=graph_admin_headers,
                json={
                    "source_id": source_entity_id,
                    "relation_type": "ASSOCIATED_WITH",
                    "target_id": target_entity_id,
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "evidence_summary": "Curated e2e relation.",
                    "evidence_sentence": "MED13 is associated with developmental delay.",
                    "evidence_sentence_source": "verbatim_span",
                    "evidence_sentence_confidence": "high",
                    "evidence_tier": "LITERATURE",
                },
            )
            assert (
                create_relation_response.status_code == 201
            ), create_relation_response.text
            relation_id = create_relation_response.json()["id"]

            export_response = client.get(
                f"/v1/spaces/{space_id}/graph/export",
                headers=member_headers,
            )
            assert export_response.status_code == 200, export_response.text
            export_payload = export_response.json()
            exported_node_ids = {node["id"] for node in export_payload["nodes"]}
            exported_edge_ids = {edge["id"] for edge in export_payload["edges"]}
            assert source_entity_id in exported_node_ids
            assert target_entity_id in exported_node_ids
            assert relation_id in exported_edge_ids

            graph_document_response = client.post(
                f"/v1/spaces/{space_id}/graph/document",
                headers=member_headers,
                json={
                    "mode": "seeded",
                    "seed_entity_ids": [source_entity_id],
                    "depth": 2,
                    "top_k": 25,
                    "max_nodes": 180,
                    "max_edges": 260,
                    "include_claims": True,
                    "include_evidence": True,
                    "max_claims": 250,
                    "evidence_limit_per_claim": 3,
                },
            )
            assert (
                graph_document_response.status_code == 200
            ), graph_document_response.text
            document_payload = graph_document_response.json()
            assert document_payload["meta"]["counts"]["entity_nodes"] >= 2
            assert document_payload["meta"]["counts"]["canonical_edges"] >= 1
    finally:
        reset_graph_service_database()
