from __future__ import annotations

import pytest
from artana_evidence_db.config import GraphServiceSettings, get_settings
from artana_evidence_db.runtime.env import (
    allow_graph_test_auth_headers,
    resolve_graph_jwt_secret,
)


def test_graph_service_config_wrapper_require_graph_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GRAPH_DATABASE_URL", raising=False)

    with pytest.raises(
        RuntimeError,
        match="GRAPH_DATABASE_URL is required for the standalone graph service runtime",
    ):
        get_settings()


def test_graph_service_config_wrapper_returns_graph_service_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")

    settings = get_settings()

    assert isinstance(settings, GraphServiceSettings)


def test_graph_service_config_defaults_to_selected_pack_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")
    monkeypatch.delenv("GRAPH_SERVICE_NAME", raising=False)
    monkeypatch.delenv("GRAPH_JWT_ISSUER", raising=False)

    settings = get_settings()

    assert settings.app_name == "Sports Graph Service"
    assert settings.jwt_issuer == "graph-sports"


def test_graph_service_requires_graph_jwt_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENV", "production")
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")
    monkeypatch.delenv("GRAPH_JWT_SECRET", raising=False)

    with pytest.raises(
        RuntimeError,
        match="GRAPH_JWT_SECRET must be set",
    ):
        get_settings()


def test_graph_service_ignores_test_auth_flags_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENV", "production")
    monkeypatch.setenv("GRAPH_DATABASE_URL", "sqlite:///graph-service-test.db")
    monkeypatch.setenv(
        "GRAPH_JWT_SECRET",
        "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz",
    )
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("GRAPH_ALLOW_TEST_AUTH_HEADERS", "true")

    settings = get_settings()

    assert settings.allow_test_auth_headers is False


def test_graph_runtime_env_requires_graph_jwt_secret_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENV", "production")
    monkeypatch.delenv("GRAPH_JWT_SECRET", raising=False)

    with pytest.raises(
        RuntimeError,
        match="GRAPH_JWT_SECRET must be set",
    ):
        resolve_graph_jwt_secret()


def test_graph_runtime_env_ignores_test_auth_flags_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARTANA_ENV", "production")
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("GRAPH_ALLOW_TEST_AUTH_HEADERS", "true")

    assert allow_graph_test_auth_headers() is False
