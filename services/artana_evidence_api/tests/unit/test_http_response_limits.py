"""Unit tests for bounded upstream HTTP response readers."""

from __future__ import annotations

import httpx
import pytest
from artana_evidence_api.runtime.http_response_limits import (
    UpstreamResponseTooLargeError,
    async_get_limited_json,
    get_limited_json,
    limited_bytes_from_chunks,
    post_limited_json,
)


def test_get_limited_json_rejects_large_content_length_before_json_parse() -> None:
    parsed = False

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal parsed
        parsed = True
        return httpx.Response(
            200,
            headers={"content-length": "100"},
            json={"ok": True},
            request=request,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(_handler)) as client,
        pytest.raises(UpstreamResponseTooLargeError, match="test upstream"),
    ):
        get_limited_json(
            client,
            "https://example.test/data",
            context="test upstream",
            max_bytes=10,
        )

    assert parsed is True


def test_get_limited_json_forwards_supported_query_params() -> None:
    captured_url = ""

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_url
        captured_url = str(request.url)
        return httpx.Response(200, json={"ok": True}, request=request)

    with httpx.Client(transport=httpx.MockTransport(_handler)) as client:
        assert get_limited_json(
            client,
            "https://example.test/data",
            context="test upstream",
            params={"gene": "MED13", "taxon": 9606, "include": ["omim", "clinvar"]},
            max_bytes=100,
        ) == {"ok": True}

    assert "gene=MED13" in captured_url
    assert "taxon=9606" in captured_url
    assert "include=omim" in captured_url
    assert "include=clinvar" in captured_url


@pytest.mark.asyncio
async def test_async_get_limited_json_rejects_large_content_length() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": "100"},
            json={"ok": True},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        with pytest.raises(UpstreamResponseTooLargeError, match="test upstream"):
            await async_get_limited_json(
                client,
                "https://example.test/data",
                context="test upstream",
                max_bytes=10,
            )


def test_post_limited_json_rejects_large_content_length() -> None:
    captured_body = b""

    def _handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_body
        captured_body = request.content
        return httpx.Response(
            200,
            headers={"content-length": "100"},
            json={"ok": True},
            request=request,
        )

    with (
        httpx.Client(transport=httpx.MockTransport(_handler)) as client,
        pytest.raises(UpstreamResponseTooLargeError, match="test graphql"),
    ):
        post_limited_json(
            client,
            "https://example.test/graphql",
            context="test graphql",
            json_payload={"query": "{ ok }"},
            max_bytes=10,
        )

    assert b"ok" in captured_body


def test_limited_bytes_from_chunks_rejects_declared_large_body_before_consuming() -> None:
    consumed = False

    def chunks() -> object:
        nonlocal consumed
        consumed = True
        yield b"{}"

    with pytest.raises(UpstreamResponseTooLargeError, match="PMC OA"):
        limited_bytes_from_chunks(
            chunks(),
            headers={"content-length": "100"},
            context="PMC OA",
            max_bytes=10,
        )

    assert consumed is False


def test_limited_bytes_from_chunks_rejects_streaming_overflow() -> None:
    with pytest.raises(UpstreamResponseTooLargeError, match="PMC OA"):
        limited_bytes_from_chunks(
            [b"12345", b"67890", b"!"],
            headers={},
            context="PMC OA",
            max_bytes=10,
        )
