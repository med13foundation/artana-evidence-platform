"""Unit tests for standalone graph-service app startup."""

from __future__ import annotations

from types import SimpleNamespace

from artana_evidence_db import app as graph_app_module
from artana_evidence_db.database import SessionLocal
from artana_evidence_db.governance import (
    build_dictionary_repository,
    seed_builtin_dictionary_entries,
)
from artana_evidence_db.graph_domain_config import (
    GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
)
from artana_evidence_db.product_contract import (
    GRAPH_OPENAPI_URL,
    GRAPH_SERVICE_VERSION,
)
from artana_evidence_db.tests.support import reset_graph_service_database


def test_create_app_does_not_seed_service_local_dictionary_on_startup(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "biomedical")

    monkeypatch.setattr(
        graph_app_module,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("startup opened a DB session")),
        raising=False,
    )
    monkeypatch.setattr(
        graph_app_module,
        "get_settings",
        lambda: SimpleNamespace(app_name="Graph Service Test"),
    )

    app = graph_app_module.create_app()

    assert app.title == "Graph Service Test"
    assert app.version == GRAPH_SERVICE_VERSION
    assert app.openapi_url == GRAPH_OPENAPI_URL
    assert app.state.graph_domain_pack.name == "biomedical"
    assert app.state.graph_domain_pack.version == "1.0.0"
    assert (
        app.state.graph_domain_pack.dictionary_loading_extension.builtin_entity_types[
            0
        ].entity_type
        == "GENE"
    )


def test_create_app_uses_selected_domain_pack_without_startup_mutation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")

    monkeypatch.setattr(
        graph_app_module,
        "SessionLocal",
        lambda: (_ for _ in ()).throw(AssertionError("startup opened a DB session")),
        raising=False,
    )
    monkeypatch.setattr(
        graph_app_module,
        "get_settings",
        lambda: SimpleNamespace(app_name="Sports Graph Service Test"),
    )

    app = graph_app_module.create_app()

    assert app.title == "Sports Graph Service Test"
    assert app.state.graph_domain_pack.name == "sports"
    assert app.state.graph_domain_pack.version == "1.0.0"
    assert (
        app.state.graph_domain_pack.dictionary_loading_extension.builtin_domain_contexts[
            1
        ].id
        == "competition"
    )
    assert (
        app.state.graph_domain_pack.dictionary_loading_extension.builtin_entity_types[
            0
        ].entity_type
        == "TEAM"
    )
    assert (
        app.state.graph_domain_pack.dictionary_loading_extension.builtin_relation_constraints[
            0
        ].source_type
        == "PLAYER"
    )


def test_create_app_openapi_describes_graph_admin_dictionary_contract(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        graph_app_module,
        "get_settings",
        lambda: SimpleNamespace(app_name="Graph Service Test"),
    )

    app = graph_app_module.create_app()
    schema = app.openapi()

    assert (
        "graph_admin"
        in schema["components"]["securitySchemes"]["HTTPBearer"]["description"]
    )
    assert "/v1/dictionary/domain-contexts" in schema["paths"]
    assert "/v1/domain-packs/active" in schema["paths"]
    assert "/v1/domain-packs/{pack_name}" in schema["paths"]
    assert "/v1/domain-packs/{pack_name}/spaces/{space_id}/seed" in schema["paths"]
    assert "/v1/domain-packs/{pack_name}/spaces/{space_id}/repair" in schema["paths"]
    assert (
        "/v1/domain-packs/{pack_name}/spaces/{space_id}/seed-status" in schema["paths"]
    )


def test_seed_builtin_dictionary_entries_persists_core_relation_constraints() -> None:
    reset_graph_service_database()
    try:
        with SessionLocal() as session:
            seed_builtin_dictionary_entries(
                session,
                dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
            )
            session.commit()
            dictionary_repo = build_dictionary_repository(
                session,
                dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
            )
            constraints = dictionary_repo.get_constraints(source_type="GENE")
    finally:
        reset_graph_service_database()

    constraint_triples = {
        (constraint.source_type, constraint.relation_type, constraint.target_type)
        for constraint in constraints
        if constraint.is_active and constraint.review_status == "ACTIVE"
    }
    assert ("GENE", "ASSOCIATED_WITH", "PHENOTYPE") in constraint_triples
    assert ("GENE", "PHYSICALLY_INTERACTS_WITH", "GENE") in constraint_triples
