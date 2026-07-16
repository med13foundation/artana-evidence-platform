"""Regression tests for relation mutation router composition."""

from __future__ import annotations

from artana_evidence_db.routers.relation_routes.mutations import (
    create_relation as mutation_create_relation,
)
from artana_evidence_db.routers.relation_routes.mutations import (
    update_relation_curation_status as mutation_update_relation_curation_status,
)
from artana_evidence_db.routers.relations import (
    create_relation,
    router,
    update_relation_curation_status,
)
from fastapi.routing import APIRoute


def test_relation_mutation_routes_are_composed_once_with_stable_metadata() -> None:
    mutation_route_list = [
        route
        for route in router.routes
        if isinstance(route, APIRoute)
        and route.name in {"create_relation", "update_relation_curation_status"}
    ]
    mutation_routes = {route.name: route for route in mutation_route_list}

    assert len(mutation_route_list) == 2
    assert set(mutation_routes) == {
        "create_relation",
        "update_relation_curation_status",
    }
    assert mutation_routes["create_relation"].path == "/v1/spaces/{space_id}/relations"
    assert mutation_routes["create_relation"].methods == {"POST"}
    assert mutation_routes["create_relation"].tags == ["relations"]
    assert mutation_routes["update_relation_curation_status"].path == (
        "/v1/spaces/{space_id}/relations/{relation_id}"
    )
    assert mutation_routes["update_relation_curation_status"].methods == {"PUT"}
    assert mutation_routes["update_relation_curation_status"].tags == ["relations"]


def test_relations_router_preserves_mutation_endpoint_exports() -> None:
    assert create_relation is mutation_create_relation
    assert update_relation_curation_status is mutation_update_relation_curation_status
