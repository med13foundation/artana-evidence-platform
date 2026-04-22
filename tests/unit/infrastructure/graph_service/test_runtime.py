from __future__ import annotations

from uuid import UUID

import jwt
import pytest

from src.domain.entities.user import UserStatus
from src.infrastructure.platform_graph.graph_service import runtime


def test_resolve_graph_service_url_prefers_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_SERVICE_URL", "https://graph.example.com/")
    monkeypatch.setenv("ARTANA_ENV", "production")
    monkeypatch.delenv("TESTING", raising=False)

    assert runtime.resolve_graph_service_url() == "https://graph.example.com"


def test_resolve_graph_service_url_allows_local_fallback_in_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_SERVICE_URL", raising=False)
    monkeypatch.setenv("TESTING", "true")

    assert runtime.resolve_graph_service_url() == "http://127.0.0.1:8090"


def test_resolve_graph_service_url_requires_env_outside_local_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_SERVICE_URL", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ARTANA_ENV", "production")

    with pytest.raises(
        RuntimeError,
        match="GRAPH_SERVICE_URL is required outside local development",
    ):
        runtime.resolve_graph_service_url()


def test_build_graph_service_bearer_token_for_service_uses_graph_service_issuer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    service_user_id = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_SERVICE_SERVICE_USER_ID", service_user_id)
    monkeypatch.delenv("GRAPH_JWT_ISSUER", raising=False)

    token = runtime.build_graph_service_bearer_token_for_service()

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )

    assert payload["sub"] == service_user_id
    assert payload["role"] == "viewer"
    assert payload["graph_admin"] is True
    assert "graph_service_capabilities" not in payload
    assert UUID(str(payload["sub"])) == UUID(service_user_id)


def test_build_graph_service_bearer_token_for_service_includes_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    service_user_id = "11111111-2222-3333-4444-555555555555"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_SERVICE_SERVICE_USER_ID", service_user_id)
    monkeypatch.delenv("GRAPH_JWT_ISSUER", raising=False)

    token = runtime.build_graph_service_bearer_token_for_service(
        graph_service_capabilities=("space_sync",),
    )

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="graph-biomedical",
    )

    assert payload["graph_service_capabilities"] == ["space_sync"]


def test_build_graph_service_bearer_token_for_user_respects_graph_issuer_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "test-graph-secret-key-with-minimum-length-123456"
    custom_issuer = "graph-custom"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", custom_issuer)

    user = runtime.User(
        id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        email="graph-user@example.com",
        username="graph-user",
        full_name="Graph User",
        hashed_password="hashed-password",
        role=runtime.UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
    )

    token = runtime.build_graph_service_bearer_token_for_user(user)

    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer=custom_issuer,
    )

    assert payload["sub"] == str(user.id)
    assert payload["role"] == "researcher"
