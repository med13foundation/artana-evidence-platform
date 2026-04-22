"""Static contract checks between the harness gateway and frozen graph OpenAPI."""

from __future__ import annotations

import json
from pathlib import Path


def test_graph_harness_gateway_endpoints_exist_in_frozen_openapi() -> None:
    spec = json.loads(
        Path("services/artana_evidence_db/openapi.json").read_text(encoding="utf-8"),
    )
    paths: dict[str, dict[str, object]] = spec["paths"]

    expected_operations = {
        ("/health", "get"),
        ("/v1/domain-packs", "get"),
        ("/v1/domain-packs/active", "get"),
        ("/v1/domain-packs/{pack_name}", "get"),
        ("/v1/domain-packs/{pack_name}/spaces/{space_id}/seed-status", "get"),
        ("/v1/domain-packs/{pack_name}/spaces/{space_id}/seed", "post"),
        ("/v1/domain-packs/{pack_name}/spaces/{space_id}/repair", "post"),
        ("/v1/dictionary/entity-types", "get"),
        ("/v1/dictionary/relation-types", "get"),
        ("/v1/dictionary/proposals/entity-types", "post"),
        ("/v1/dictionary/proposals/relation-types", "post"),
        ("/v1/dictionary/proposals/relation-constraints", "post"),
        ("/v1/admin/spaces/{space_id}/sync", "post"),
        ("/v1/spaces/{space_id}/entities", "post"),
        ("/v1/spaces/{space_id}/claims", "get"),
        ("/v1/spaces/{space_id}/claims", "post"),
        ("/v1/spaces/{space_id}/entities/embeddings/refresh", "post"),
        ("/v1/spaces/{space_id}/entities/embeddings/status", "get"),
        ("/v1/spaces/{space_id}/validate/entity", "post"),
        ("/v1/spaces/{space_id}/validate/claim", "post"),
        ("/v1/spaces/{space_id}/validate/triple", "post"),
        ("/v1/spaces/{space_id}/relations/suggestions", "post"),
        ("/v1/spaces/{space_id}/relations", "post"),
        ("/v1/spaces/{space_id}/reasoning-paths", "get"),
        ("/v1/spaces/{space_id}/reasoning-paths/{path_id}", "get"),
        ("/v1/spaces/{space_id}/hypotheses/manual", "post"),
        ("/v1/spaces/{space_id}/hypotheses", "get"),
        ("/v1/spaces/{space_id}/graph/document", "post"),
        ("/v1/spaces/{space_id}/claims/by-entity/{entity_id}", "get"),
        ("/v1/spaces/{space_id}/claims/{claim_id}/participants", "get"),
        ("/v1/spaces/{space_id}/claims/{claim_id}/evidence", "get"),
        ("/v1/spaces/{space_id}/relations/conflicts", "get"),
    }

    missing_operations = sorted(
        (path, method)
        for path, method in expected_operations
        if method not in paths.get(path, {})
    )

    assert missing_operations == []
