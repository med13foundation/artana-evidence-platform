"""Integration tests for graph-owned unified search routes."""

from __future__ import annotations

from artana_evidence_db.tests import support as graph_service_support
from artana_evidence_db.tests.support import build_seeded_space_fixture

graph_client = graph_service_support.graph_client


def test_unified_search_returns_graph_entity_matches(graph_client) -> None:
    fixture = build_seeded_space_fixture(slug_prefix="search-space")
    space_id = fixture["space_id"]
    headers = fixture["headers"]

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "Artana Search Gene",
            "aliases": ["ARTANA1"],
            "metadata": {"source": "search-test"},
        },
    )
    assert create_response.status_code == 201

    response = graph_client.post(
        "/v1/search",
        headers=headers,
        params={
            "space_id": str(space_id),
            "query": "Artana",
            "limit": 10,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "Artana"
    assert payload["total_results"] >= 1
    assert payload["results"][0]["entity_type"] == "entity"
    assert payload["results"][0]["title"] == "Artana Search Gene"
