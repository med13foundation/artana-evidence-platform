# ruff: noqa: T201
"""Small HTTP-only client flow for the standalone Artana Evidence DB.

This example intentionally imports no Artana Python packages. It shows how an
external project can create/sync a graph space, seed a domain pack, validate
payloads, create graph entities, create a claim, and export the graph by using
only the public HTTP API.
"""

from __future__ import annotations

import argparse
import os
from typing import cast
from uuid import UUID, uuid4

import httpx


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--graph-url",
        default=os.getenv("GRAPH_URL", "http://localhost:8090"),
        help="Base URL for the graph service.",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("GRAPH_TOKEN"),
        required=os.getenv("GRAPH_TOKEN") is None,
        help="Bearer token with graph_admin privileges.",
    )
    parser.add_argument(
        "--space-id",
        default=os.getenv("SPACE_ID", str(uuid4())),
        help="Graph space UUID to create or reuse.",
    )
    parser.add_argument(
        "--owner-id",
        default=os.getenv("OWNER_ID", str(uuid4())),
        help="Owner UUID for the graph-space registry row.",
    )
    parser.add_argument(
        "--pack",
        default=os.getenv("GRAPH_PACK", "biomedical"),
        help="Domain pack to seed into the space.",
    )
    return parser.parse_args()


def _request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    response = client.request(method, path, json=json_payload)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        msg = f"Expected JSON object from {method} {path}"
        raise TypeError(msg)
    return cast("dict[str, object]", payload)


def _nested_object(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload[key]
    if not isinstance(value, dict):
        msg = f"Expected '{key}' to be a JSON object"
        raise TypeError(msg)
    return cast("dict[str, object]", value)


def _create_entity(
    client: httpx.Client,
    *,
    space_id: UUID,
    entity_type: str,
    display_label: str,
    aliases: list[str],
) -> UUID:
    entity_payload: dict[str, object] = {
        "entity_type": entity_type,
        "display_label": display_label,
        "aliases": aliases,
        "metadata": {"origin": "http_only_example"},
        "identifiers": {},
    }
    validation = _request_json(
        client,
        "POST",
        f"/v1/spaces/{space_id}/validate/entity",
        json_payload=entity_payload,
    )
    if validation.get("valid") is not True:
        msg = f"Entity validation failed: {validation}"
        raise RuntimeError(msg)

    created = _request_json(
        client,
        "POST",
        f"/v1/spaces/{space_id}/entities",
        json_payload=entity_payload,
    )
    entity = _nested_object(created, "entity")
    return UUID(str(entity["id"]))


def main() -> int:
    args = _parse_args()
    graph_url = str(args.graph_url).rstrip("/")
    token = str(args.token)
    space_id = UUID(str(args.space_id))
    owner_id = UUID(str(args.owner_id))
    pack_name = str(args.pack)

    with httpx.Client(
        base_url=graph_url,
        timeout=20,
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        health = _request_json(client, "GET", "/health")
        active_pack = _request_json(client, "GET", "/v1/domain-packs/active")
        print(f"graph service: {health['status']} version={health['version']}")
        print(f"active pack: {active_pack['name']} {active_pack['version']}")

        _request_json(
            client,
            "PUT",
            f"/v1/admin/spaces/{space_id}",
            json_payload={
                "slug": f"http-only-example-{space_id.hex[:8]}",
                "name": "HTTP Only Example Space",
                "description": "Created by the HTTP-only example client.",
                "owner_id": str(owner_id),
                "status": "active",
                "settings": {},
            },
        )
        seed_result = _request_json(
            client,
            "POST",
            f"/v1/domain-packs/{pack_name}/spaces/{space_id}/seed",
        )
        seed_status = _nested_object(seed_result, "status")
        print(
            "seed:"
            f" applied={seed_result['applied']}"
            f" pack={seed_status['pack_name']}@{seed_status['pack_version']}",
        )

        gene_id = _create_entity(
            client,
            space_id=space_id,
            entity_type="GENE",
            display_label="MED13",
            aliases=["Mediator complex subunit 13"],
        )
        phenotype_id = _create_entity(
            client,
            space_id=space_id,
            entity_type="PHENOTYPE",
            display_label="Developmental delay",
            aliases=[],
        )

        assessment: dict[str, object] = {
            "support_band": "SUPPORTED",
            "grounding_level": "SPAN",
            "mapping_status": "RESOLVED",
            "speculation_level": "DIRECT",
            "confidence_rationale": "Example evidence sentence supports the claim.",
        }
        claim_payload: dict[str, object] = {
            "source_entity_id": str(gene_id),
            "target_entity_id": str(phenotype_id),
            "relation_type": "ASSOCIATED_WITH",
            "assessment": assessment,
            "claim_text": "MED13 is associated with developmental delay.",
            "evidence_sentence": "MED13 is associated with developmental delay.",
            "evidence_sentence_source": "verbatim_span",
            "evidence_sentence_confidence": "HIGH",
            "source_document_ref": "example:local-note",
            "source_ref": f"http-only-example:{space_id}:med13-developmental-delay",
            "metadata": {"origin": "http_only_example"},
        }
        claim_validation = _request_json(
            client,
            "POST",
            f"/v1/spaces/{space_id}/validate/claim",
            json_payload=claim_payload,
        )
        if claim_validation.get("valid") is not True:
            msg = f"Claim validation failed: {claim_validation}"
            raise RuntimeError(msg)

        claim = _request_json(
            client,
            "POST",
            f"/v1/spaces/{space_id}/claims",
            json_payload=claim_payload,
        )
        graph_export = _request_json(
            client,
            "GET",
            f"/v1/spaces/{space_id}/graph/export",
        )
        print(f"claim: {claim['id']}")
        print(
            "export:"
            f" entities={len(cast('list[object]', graph_export['entities']))}"
            f" relations={len(cast('list[object]', graph_export['relations']))}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
