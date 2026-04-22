from __future__ import annotations

import httpx
import pytest
from artana_api import ArtanaClient, ArtanaConfig, HealthResponse
from artana_api_test_helpers import make_client


@pytest.fixture
def client_factory():
    return make_client


def test_health_sends_configured_headers(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health"
        assert request.headers["Authorization"] == "Bearer test_bearer_token"
        assert request.headers["X-Artana-Key"] == "artana_test_key"
        assert request.headers["X-OpenAI-API-Key"] == "openai_test_key"
        assert "Content-Type" not in request.headers
        return httpx.Response(200, json={"status": "ok", "version": "2026.03.20"})

    client = client_factory(handler)
    try:
        response = client.health()
    finally:
        client.close()

    assert response.status == "ok"


def test_per_request_headers_override_configured_headers(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer override"
        assert request.headers["X-Artana-Key"] == "override-key"
        assert request.headers["X-OpenAI-API-Key"] == "override-openai"
        assert request.headers["Content-Type"] == "application/custom+json"
        return httpx.Response(200, json={"status": "ok", "version": "2026.03.20"})

    client = client_factory(handler)
    try:
        response = client._request_model(
            "POST",
            "/health",
            response_model=HealthResponse,
            json_body={"test": True},
            headers={
                "Authorization": "Bearer override",
                "X-Artana-Key": "override-key",
                "X-OpenAI-API-Key": "override-openai",
                "Content-Type": "application/custom+json",
            },
        )
    finally:
        client.close()

    assert response.version == "2026.03.20"


def test_custom_header_names_are_respected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Custom-Artana-Key"] == "artana_key"
        assert request.headers["X-Custom-OpenAI-Key"] == "openai_key"
        assert "X-Artana-Key" not in request.headers
        assert "X-OpenAI-API-Key" not in request.headers
        return httpx.Response(200, json={"status": "ok", "version": "2026.03.20"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(base_url="https://artana.test", transport=transport)
    config = ArtanaConfig(
        base_url="https://artana.test",
        api_key="artana_key",
        openai_api_key="openai_key",
        artana_api_key_header="X-Custom-Artana-Key",
        openai_api_key_header="X-Custom-OpenAI-Key",
    )
    client = ArtanaClient(config=config, client=http_client)
    try:
        response = client.health()
    finally:
        client.close()

    assert response.status == "ok"


def test_default_headers_take_precedence_over_generated_auth_headers(
    client_factory,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer static"
        assert request.headers["X-Artana-Key"] == "static-key"
        return httpx.Response(200, json={"status": "ok", "version": "2026.03.20"})

    client = client_factory(
        handler,
        default_headers={
            "Authorization": "Bearer static",
            "X-Artana-Key": "static-key",
        },
    )
    try:
        response = client.health()
    finally:
        client.close()

    assert response.version == "2026.03.20"
