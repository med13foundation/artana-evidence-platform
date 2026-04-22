from __future__ import annotations

from uuid import UUID

import pytest
from artana_api import ArtanaClient, ArtanaConfig
from artana_api.exceptions import ArtanaConfigurationError


def test_config_from_env_reads_expected_values() -> None:
    config = ArtanaConfig.from_env(
        {
            "ARTANA_API_BASE_URL": "https://example.test/",
            "ARTANA_API_KEY": " artana_key ",
            "ARTANA_ACCESS_TOKEN": " bearer_token ",
            "ARTANA_OPENAI_API_KEY": " openai_key ",
            "ARTANA_DEFAULT_SPACE_ID": "11111111-1111-1111-1111-111111111111",
            "ARTANA_TIMEOUT_SECONDS": "45",
        },
    )

    assert config.base_url == "https://example.test"
    assert config.api_key == "artana_key"
    assert config.access_token == "bearer_token"
    assert config.openai_api_key == "openai_key"
    assert config.default_space_id == "11111111-1111-1111-1111-111111111111"
    assert config.timeout_seconds == 45.0


def test_config_from_env_supports_fallback_variable_names() -> None:
    config = ArtanaConfig.from_env(
        {
            "ARTANA_BASE_URL": "https://fallback.test/",
            "ARTANA_BEARER_TOKEN": "fallback_token",
            "OPENAI_API_KEY": "fallback_openai",
        },
    )

    assert config.base_url == "https://fallback.test"
    assert config.access_token == "fallback_token"
    assert config.openai_api_key == "fallback_openai"


def test_config_from_env_requires_base_url() -> None:
    with pytest.raises(ArtanaConfigurationError) as exc_info:
        ArtanaConfig.from_env({})

    assert "ARTANA_API_BASE_URL" in str(exc_info.value)


def test_config_from_env_rejects_invalid_timeout() -> None:
    with pytest.raises(ArtanaConfigurationError) as exc_info:
        ArtanaConfig.from_env(
            {
                "ARTANA_API_BASE_URL": "https://example.test",
                "ARTANA_TIMEOUT_SECONDS": "not-a-number",
            },
        )

    assert "ARTANA_TIMEOUT_SECONDS" in str(exc_info.value)


def test_config_normalizes_default_headers_and_uuid() -> None:
    config = ArtanaConfig(
        base_url=" https://example.test/ ",
        default_space_id="11111111-1111-1111-1111-111111111111",
        default_headers={
            " Authorization ": " Bearer custom ",
            "": "ignored",
            "X-Empty": "   ",
        },
    )

    assert config.base_url == "https://example.test"
    assert config.default_space_id == "11111111-1111-1111-1111-111111111111"
    assert config.default_headers == {"Authorization": "Bearer custom"}


def test_client_init_rejects_config_plus_inline_args() -> None:
    config = ArtanaConfig(base_url="https://example.test")

    with pytest.raises(ArtanaConfigurationError):
        ArtanaClient(config=config, base_url="https://duplicate.test")


def test_client_accepts_uuid_default_space_id() -> None:
    client = ArtanaClient(
        base_url="https://example.test",
        default_space_id=UUID("11111111-1111-1111-1111-111111111111"),
    )
    try:
        assert client.config.default_space_id == "11111111-1111-1111-1111-111111111111"
    finally:
        client.close()
