"""Shared bounded readers for upstream HTTP responses."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, TypeAlias

import httpx

_DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_MAX_RESPONSE_BYTES_ENV = "ARTANA_EVIDENCE_API_MAX_UPSTREAM_RESPONSE_BYTES"
HTTPQueryParamPrimitive: TypeAlias = str | int | float | bool | None
HTTPQueryParams: TypeAlias = (
    httpx.QueryParams
    | Mapping[str, HTTPQueryParamPrimitive | Sequence[HTTPQueryParamPrimitive]]
    | list[tuple[str, HTTPQueryParamPrimitive]]
    | tuple[tuple[str, HTTPQueryParamPrimitive], ...]
    | str
    | bytes
)


class UpstreamResponseTooLargeError(httpx.HTTPError):
    """Raised when an upstream response exceeds the configured byte limit."""


def max_upstream_response_bytes() -> int:
    """Return the configured upstream response size cap."""
    raw_value = os.getenv(_MAX_RESPONSE_BYTES_ENV)
    if raw_value is None or raw_value.strip() == "":
        return _DEFAULT_MAX_RESPONSE_BYTES
    try:
        parsed = int(raw_value)
    except ValueError:
        return _DEFAULT_MAX_RESPONSE_BYTES
    return max(parsed, 1)


def get_limited_json(
    client: httpx.Client,
    url: str,
    *,
    context: str,
    params: HTTPQueryParams | None = None,
    headers: Mapping[str, str] | None = None,
    follow_redirects: bool = False,
    max_bytes: int | None = None,
) -> Any:
    """GET one JSON response while enforcing a bounded body size."""
    with client.stream(
        "GET",
        url,
        params=params,
        headers=headers,
        follow_redirects=follow_redirects,
    ) as response:
        response.raise_for_status()
        return _decode_json(
            _read_limited_response(response, context=context, max_bytes=max_bytes),
            context=context,
        )


def post_limited_json(
    client: httpx.Client,
    url: str,
    *,
    context: str,
    json_payload: Mapping[str, object],
    params: HTTPQueryParams | None = None,
    headers: Mapping[str, str] | None = None,
    follow_redirects: bool = False,
    max_bytes: int | None = None,
) -> Any:
    """POST one JSON request and enforce a bounded JSON response size."""
    with client.stream(
        "POST",
        url,
        params=params,
        headers=headers,
        json=dict(json_payload),
        follow_redirects=follow_redirects,
    ) as response:
        response.raise_for_status()
        return _decode_json(
            _read_limited_response(response, context=context, max_bytes=max_bytes),
            context=context,
        )


def limited_json_from_response(
    response: httpx.Response,
    *,
    context: str,
    max_bytes: int | None = None,
) -> Any:
    """Decode an already obtained response after enforcing the body size cap."""
    return _decode_json(
        _read_limited_response(response, context=context, max_bytes=max_bytes),
        context=context,
    )


def limited_text_from_response(
    response: httpx.Response,
    *,
    context: str,
    max_bytes: int | None = None,
) -> str:
    """Decode an already obtained text response after enforcing the body size cap."""
    return _decode_text(
        _read_limited_response(response, context=context, max_bytes=max_bytes),
        context=context,
    )


def limited_bytes_from_chunks(
    chunks: Iterable[bytes],
    *,
    headers: Mapping[str, str],
    context: str,
    max_bytes: int | None = None,
) -> bytes:
    """Read byte chunks while enforcing the same upstream response size cap."""
    limit = _effective_limit(max_bytes)
    _raise_if_declared_too_large(headers, context=context, limit=limit)
    collected: list[bytes] = []
    total = 0
    for chunk in chunks:
        total += len(chunk)
        if total > limit:
            _raise_too_large(context=context, limit=limit)
        collected.append(chunk)
    return b"".join(collected)


async def async_get_limited_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    context: str,
    params: HTTPQueryParams | None = None,
    headers: Mapping[str, str] | None = None,
    follow_redirects: bool = False,
    max_bytes: int | None = None,
) -> Any:
    """GET one JSON response asynchronously while bounding the body size."""
    async with client.stream(
        "GET",
        url,
        params=params,
        headers=headers,
        follow_redirects=follow_redirects,
    ) as response:
        response.raise_for_status()
        return _decode_json(
            await _aread_limited_response(
                response,
                context=context,
                max_bytes=max_bytes,
            ),
            context=context,
        )


async def async_limited_json_from_response(
    response: httpx.Response,
    *,
    context: str,
    max_bytes: int | None = None,
) -> Any:
    """Decode a streamed async response after enforcing the body size cap."""
    return _decode_json(
        await _aread_limited_response(
            response,
            context=context,
            max_bytes=max_bytes,
        ),
        context=context,
    )


async def async_get_limited_text(
    client: httpx.AsyncClient,
    url: str,
    *,
    context: str,
    params: HTTPQueryParams | None = None,
    headers: Mapping[str, str] | None = None,
    follow_redirects: bool = False,
    max_bytes: int | None = None,
) -> str:
    """GET one text response asynchronously while bounding the body size."""
    async with client.stream(
        "GET",
        url,
        params=params,
        headers=headers,
        follow_redirects=follow_redirects,
    ) as response:
        response.raise_for_status()
        return _decode_text(
            await _aread_limited_response(
                response,
                context=context,
                max_bytes=max_bytes,
            ),
            context=context,
        )


def _read_limited_response(
    response: httpx.Response,
    *,
    context: str,
    max_bytes: int | None,
) -> bytes:
    return limited_bytes_from_chunks(
        response.iter_bytes(),
        headers=response.headers,
        context=context,
        max_bytes=max_bytes,
    )


async def _aread_limited_response(
    response: httpx.Response,
    *,
    context: str,
    max_bytes: int | None,
) -> bytes:
    limit = _effective_limit(max_bytes)
    _raise_if_declared_too_large(response.headers, context=context, limit=limit)
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > limit:
            _raise_too_large(context=context, limit=limit)
        chunks.append(chunk)
    return b"".join(chunks)


def _effective_limit(max_bytes: int | None) -> int:
    if isinstance(max_bytes, int) and max_bytes > 0:
        return max_bytes
    return max_upstream_response_bytes()


def _raise_if_declared_too_large(
    headers: Mapping[str, str],
    *,
    context: str,
    limit: int,
) -> None:
    content_length = _content_length(headers)
    if content_length is not None and content_length > limit:
        _raise_too_large(context=context, limit=limit)


def _content_length(headers: Mapping[str, str]) -> int | None:
    raw_value = headers.get("content-length")
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def _raise_too_large(
    *,
    context: str,
    limit: int,
) -> None:
    msg = f"{context} response exceeded {limit} bytes"
    raise UpstreamResponseTooLargeError(msg)


def _decode_json(data: bytes, *, context: str) -> Any:
    try:
        return json.loads(_decode_text(data, context=context))
    except json.JSONDecodeError as exc:
        msg = f"{context} response was not valid JSON"
        raise ValueError(msg) from exc


def _decode_text(data: bytes, *, context: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"{context} response was not valid UTF-8"
        raise ValueError(msg) from exc
