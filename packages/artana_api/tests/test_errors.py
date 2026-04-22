from __future__ import annotations

import httpx
import pytest
from artana_api.exceptions import ArtanaRequestError, ArtanaResponseValidationError
from artana_api_test_helpers import make_client


@pytest.fixture
def client_factory():
    return make_client


def test_failed_response_raises_artana_request_error_with_detail(
    client_factory,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid token"})

    client = client_factory(handler)
    try:
        with pytest.raises(ArtanaRequestError) as exc_info:
            client.health()
    finally:
        client.close()

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


def test_failed_response_uses_error_field_when_detail_missing(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "Rate limit reached"})

    client = client_factory(handler)
    try:
        with pytest.raises(ArtanaRequestError) as exc_info:
            client.health()
    finally:
        client.close()

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "Rate limit reached"


def test_failed_response_uses_plain_text_when_json_detail_missing(
    client_factory,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Upstream exploded")

    client = client_factory(handler)
    try:
        with pytest.raises(ArtanaRequestError) as exc_info:
            client.health()
    finally:
        client.close()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Upstream exploded"


def test_network_error_is_wrapped_as_request_error(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("unable to connect", request=request)

    client = client_factory(handler)
    try:
        with pytest.raises(ArtanaRequestError) as exc_info:
            client.health()
    finally:
        client.close()

    assert "unable to connect" in str(exc_info.value)


def test_non_json_success_response_raises_validation_error(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    client = client_factory(handler)
    try:
        with pytest.raises(ArtanaResponseValidationError) as exc_info:
            client.health()
    finally:
        client.close()

    assert "not valid JSON" in str(exc_info.value)


def test_invalid_success_payload_raises_validation_error(client_factory) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = client_factory(handler)
    try:
        with pytest.raises(ArtanaResponseValidationError) as exc_info:
            client.health()
    finally:
        client.close()

    assert "validation failed" in str(exc_info.value)
