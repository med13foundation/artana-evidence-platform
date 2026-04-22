from __future__ import annotations

import pytest

from src.infrastructure.platform_graph.artana_evidence_api import runtime


def test_resolve_artana_evidence_api_service_url_prefers_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_API_SERVICE_URL",
        "https://graph-harness.example.com/",
    )
    monkeypatch.setenv("ARTANA_ENV", "production")
    monkeypatch.delenv("TESTING", raising=False)

    assert (
        runtime.resolve_artana_evidence_api_service_url()
        == "https://graph-harness.example.com"
    )


def test_resolve_artana_evidence_api_service_url_allows_local_fallback_in_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ARTANA_EVIDENCE_API_SERVICE_URL", raising=False)
    monkeypatch.setenv("TESTING", "true")

    assert runtime.resolve_artana_evidence_api_service_url() == "http://127.0.0.1:8091"


def test_resolve_artana_evidence_api_service_url_requires_env_outside_local_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ARTANA_EVIDENCE_API_SERVICE_URL", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("ARTANA_ENV", "production")

    with pytest.raises(
        RuntimeError,
        match="ARTANA_EVIDENCE_API_SERVICE_URL is required outside local development",
    ):
        runtime.resolve_artana_evidence_api_service_url()
