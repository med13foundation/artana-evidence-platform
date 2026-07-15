"""Regression tests for claim-relation router composition."""

from __future__ import annotations

from artana_evidence_db.routers.claim_routes.claim_relations import (
    create_claim_relation as child_create_claim_relation,
)
from artana_evidence_db.routers.claim_routes.claim_relations import (
    list_claim_relations as child_list_claim_relations,
)
from artana_evidence_db.routers.claim_routes.claim_relations import (
    update_claim_relation_review_status as child_update_claim_relation_review_status,
)
from artana_evidence_db.routers.claims import (
    create_claim_relation,
    list_claim_relations,
    router,
    update_claim_relation_review_status,
)
from fastapi.routing import APIRoute


def test_claim_relation_routes_are_composed_once_with_stable_metadata() -> None:
    claim_relation_route_list = [
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.name
        in {
            "create_claim_relation",
            "list_claim_relations",
            "update_claim_relation_review_status",
        }
    ]
    claim_relation_routes = {
        route.name: route for route in claim_relation_route_list
    }

    assert len(claim_relation_route_list) == 3
    assert set(claim_relation_routes) == {
        "create_claim_relation",
        "list_claim_relations",
        "update_claim_relation_review_status",
    }
    assert claim_relation_routes["list_claim_relations"].path == (
        "/v1/spaces/{space_id}/claim-relations"
    )
    assert claim_relation_routes["list_claim_relations"].methods == {"GET"}
    assert claim_relation_routes["list_claim_relations"].tags == ["claims"]
    assert claim_relation_routes["create_claim_relation"].path == (
        "/v1/spaces/{space_id}/claim-relations"
    )
    assert claim_relation_routes["create_claim_relation"].methods == {"POST"}
    assert claim_relation_routes["create_claim_relation"].tags == ["claims"]
    assert claim_relation_routes["update_claim_relation_review_status"].path == (
        "/v1/spaces/{space_id}/claim-relations/{relation_id}"
    )
    assert claim_relation_routes["update_claim_relation_review_status"].methods == {
        "PATCH",
    }
    assert claim_relation_routes["update_claim_relation_review_status"].tags == [
        "claims",
    ]


def test_claims_router_preserves_claim_relation_endpoint_exports() -> None:
    assert create_claim_relation is child_create_claim_relation
    assert list_claim_relations is child_list_claim_relations
    assert (
        update_claim_relation_review_status
        is child_update_claim_relation_review_status
    )
