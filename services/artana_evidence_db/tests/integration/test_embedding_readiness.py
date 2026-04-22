from __future__ import annotations

from uuid import UUID

import pytest
from artana_evidence_db import kernel_runtime_factories
from artana_evidence_db.tests.support import (
    build_seeded_space_fixture,
)
from artana_evidence_db.tests.support import (
    graph_client as graph_client_fixture,
)
from fastapi.testclient import TestClient

graph_client = graph_client_fixture


class _StubEmbeddingProvider:
    def embed_text(self, text: str, *, model_name: str) -> list[float] | None:
        del text, model_name
        return [0.01] * 1536


def _create_entity(
    graph_client: TestClient,
    *,
    space_id: UUID,
    headers: dict[str, str],
    label: str,
    entity_type: str = "GENE",
) -> str:
    response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": entity_type,
            "display_label": label,
            "aliases": [],
            "metadata": {},
            "identifiers": {},
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return str(payload["entity"]["id"])


def test_graph_embedding_readiness_is_explicit_and_partial_by_default(
    graph_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = build_seeded_space_fixture(slug_prefix="embedding-readiness")
    space_id = UUID(str(space["space_id"]))
    headers = space["headers"]

    source_entity_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=headers,
        label="MED13",
    )
    target_entity_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=headers,
        label="CDK8",
    )

    status_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities/embeddings/status",
        headers=headers,
        params={"entity_ids": source_entity_id},
    )
    assert status_response.status_code == 200, status_response.text
    status_payload = status_response.json()
    assert status_payload["total"] == 1
    assert status_payload["statuses"][0]["state"] == "pending"

    partial_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations/suggestions",
        headers=headers,
        json={
            "source_entity_ids": [source_entity_id],
            "limit_per_source": 5,
            "min_score": 0.0,
        },
    )
    assert partial_response.status_code == 200, partial_response.text
    partial_payload = partial_response.json()
    assert partial_payload["incomplete"] is True
    assert partial_payload["suggestions"] == []
    assert partial_payload["skipped_sources"] == [
        {
            "entity_id": source_entity_id,
            "state": "pending",
            "reason": "embedding_pending",
        },
    ]

    strict_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations/suggestions",
        headers=headers,
        json={
            "source_entity_ids": [source_entity_id],
            "limit_per_source": 5,
            "min_score": 0.0,
            "require_all_ready": True,
        },
    )
    assert strict_response.status_code == 409, strict_response.text
    strict_payload = strict_response.json()
    assert (
        strict_payload["detail"]["skipped_sources"][0]["entity_id"] == source_entity_id
    )

    monkeypatch.setattr(
        kernel_runtime_factories,
        "HybridTextEmbeddingProvider",
        _StubEmbeddingProvider,
    )
    refresh_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities/embeddings/refresh",
        headers=headers,
        json={
            "entity_ids": [source_entity_id, target_entity_id],
            "limit": 2,
        },
    )
    assert refresh_response.status_code == 200, refresh_response.text
    refresh_payload = refresh_response.json()
    assert refresh_payload["processed"] == 2
    assert refresh_payload["refreshed"] == 2
    assert refresh_payload["failed"] == 0

    ready_status_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities/embeddings/status",
        headers=headers,
        params={"entity_ids": f"{source_entity_id},{target_entity_id}"},
    )
    assert ready_status_response.status_code == 200, ready_status_response.text
    ready_states = {
        row["entity_id"]: row["state"]
        for row in ready_status_response.json()["statuses"]
    }
    assert ready_states[source_entity_id] == "ready"
    assert ready_states[target_entity_id] == "ready"

    suggestion_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations/suggestions",
        headers=headers,
        json={
            "source_entity_ids": [source_entity_id],
            "limit_per_source": 5,
            "min_score": 0.0,
        },
    )
    assert suggestion_response.status_code == 200, suggestion_response.text
    suggestion_payload = suggestion_response.json()
    assert suggestion_payload["incomplete"] is False
    assert suggestion_payload["total"] >= 1

    update_response = graph_client.put(
        f"/v1/spaces/{space_id}/entities/{source_entity_id}",
        headers=headers,
        json={"display_label": "MED13 updated"},
    )
    assert update_response.status_code == 200, update_response.text

    stale_status_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities/embeddings/status",
        headers=headers,
        params={"entity_ids": source_entity_id},
    )
    assert stale_status_response.status_code == 200, stale_status_response.text
    stale_payload = stale_status_response.json()
    assert stale_payload["statuses"][0]["state"] == "stale"


def test_graph_relation_suggestions_skip_constraint_gaps_by_default(
    graph_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    space = build_seeded_space_fixture(slug_prefix="constraint-gap")
    space_id = UUID(str(space["space_id"]))
    headers = space["headers"]

    source_entity_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=headers,
        label="Drug compound A",
        entity_type="DRUG",
    )
    target_entity_id = _create_entity(
        graph_client,
        space_id=space_id,
        headers=headers,
        label="Drug compound B",
        entity_type="DRUG",
    )

    monkeypatch.setattr(
        kernel_runtime_factories,
        "HybridTextEmbeddingProvider",
        _StubEmbeddingProvider,
    )
    refresh_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities/embeddings/refresh",
        headers=headers,
        json={
            "entity_ids": [source_entity_id, target_entity_id],
            "limit": 2,
        },
    )
    assert refresh_response.status_code == 200, refresh_response.text

    suggestion_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations/suggestions",
        headers=headers,
        json={
            "source_entity_ids": [source_entity_id],
            "limit_per_source": 5,
            "min_score": 0.0,
        },
    )
    assert suggestion_response.status_code == 200, suggestion_response.text
    suggestion_payload = suggestion_response.json()
    # DRUG→DRUG has no self-referencing constraint, so no suggestions for this pair.
    # But DRUG has outgoing constraints (TARGETS, TREATS, etc.), so the source
    # is not flagged as "constraint_config_missing".
    assert len(suggestion_payload["suggestions"]) == 0
