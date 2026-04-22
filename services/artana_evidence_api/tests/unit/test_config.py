"""Unit tests for standalone harness service configuration."""

from __future__ import annotations

from artana_evidence_api.config import get_settings


def test_get_settings_uses_extended_default_graph_timeout(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ARTANA_EVIDENCE_API_GRAPH_API_TIMEOUT_SECONDS", raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.graph_api_timeout_seconds == 30.0

    get_settings.cache_clear()


def test_get_settings_allows_graph_timeout_override(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ARTANA_EVIDENCE_API_GRAPH_API_TIMEOUT_SECONDS", "12.5")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.graph_api_timeout_seconds == 12.5

    get_settings.cache_clear()
