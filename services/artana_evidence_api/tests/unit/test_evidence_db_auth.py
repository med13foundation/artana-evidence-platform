"""Unit tests for harness-local graph API service auth."""

from __future__ import annotations

from uuid import UUID

import jwt
import pytest
from artana_evidence_api.evidence_db_auth import (
    build_graph_service_bearer_token_for_service,
)


def test_build_graph_service_bearer_token_for_service_uses_expected_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    service_user_id = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", "graph-biomedical")
    monkeypatch.setenv("GRAPH_SERVICE_SERVICE_USER_ID", service_user_id)
    monkeypatch.delenv("GRAPH_SERVICE_AI_PRINCIPAL", raising=False)

    token = build_graph_service_bearer_token_for_service(
        role="researcher",
        graph_admin=True,
    )

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )

    assert payload["sub"] == service_user_id
    assert payload["role"] == "researcher"
    assert payload["type"] == "access"
    assert payload["graph_admin"] is True
    assert "graph_ai_principal" not in payload
    assert UUID(str(payload["sub"])) == UUID(service_user_id)
    assert payload["jti"]


def test_build_graph_service_bearer_token_includes_explicit_ai_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    service_user_id = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", "graph-biomedical")
    monkeypatch.setenv("GRAPH_SERVICE_SERVICE_USER_ID", service_user_id)

    token = build_graph_service_bearer_token_for_service(
        role="researcher",
        graph_admin=True,
        graph_ai_principal="agent:explicit",
    )

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )

    assert payload["graph_ai_principal"] == "agent:explicit"


def test_build_graph_service_bearer_token_defaults_ai_principal_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    service_user_id = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", "graph-biomedical")
    monkeypatch.setenv("GRAPH_SERVICE_SERVICE_USER_ID", service_user_id)
    monkeypatch.setenv("GRAPH_SERVICE_AI_PRINCIPAL", "agent:env-default")

    token = build_graph_service_bearer_token_for_service(
        role="researcher",
        graph_admin=True,
        default_graph_ai_principal_from_env=True,
    )

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )

    assert payload["graph_ai_principal"] == "agent:env-default"


def test_build_graph_service_bearer_token_includes_service_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    service_user_id = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", "graph-biomedical")
    monkeypatch.setenv("GRAPH_SERVICE_SERVICE_USER_ID", service_user_id)

    token = build_graph_service_bearer_token_for_service(
        role="researcher",
        graph_service_capabilities=["space_sync"],
    )

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )

    assert payload["graph_service_capabilities"] == ["space_sync"]


def test_build_graph_service_bearer_token_does_not_include_env_ai_principal_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    service_user_id = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", "graph-biomedical")
    monkeypatch.setenv("GRAPH_SERVICE_SERVICE_USER_ID", service_user_id)
    monkeypatch.setenv("GRAPH_SERVICE_AI_PRINCIPAL", "agent:env-default")

    token = build_graph_service_bearer_token_for_service(
        role="researcher",
        graph_admin=False,
    )

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )

    assert payload["graph_admin"] is False
    assert "graph_ai_principal" not in payload


def test_build_graph_service_bearer_token_respects_issuer_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    service_user_id = "11111111-2222-3333-4444-555555555555"
    issuer = "artana-platform"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", issuer)
    monkeypatch.setenv("GRAPH_SERVICE_SERVICE_USER_ID", service_user_id)

    token = build_graph_service_bearer_token_for_service(
        role="researcher",
        graph_admin=True,
    )

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer=issuer,
    )

    assert payload["iss"] == issuer
    assert payload["sub"] == service_user_id


def test_graph_service_token_contract_matches_expected_graph_service_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "artana-platform-backend-jwt-secret-for-development-2026-01"
    issuer = "artana-platform"
    service_user_id = "00000000-0000-0000-0000-000000000001"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", issuer)
    monkeypatch.setenv("GRAPH_SERVICE_SERVICE_USER_ID", service_user_id)
    monkeypatch.setenv(
        "GRAPH_DATABASE_URL",
        "postgresql://graph-test:graph-test@localhost:5432/graph_test",
    )

    token = build_graph_service_bearer_token_for_service(
        role="researcher",
        graph_admin=True,
    )

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer=issuer,
    )

    assert payload["iss"] == issuer
    assert payload["sub"] == service_user_id
    assert payload["role"] == "researcher"
    assert payload["type"] == "access"
    assert payload["graph_admin"] is True
    assert payload["jti"]
