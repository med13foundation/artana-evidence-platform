"""HTTP helpers for the live full-AI canary script."""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING

import httpx

from scripts.full_ai_real_space_canary.constants import (
    _API_KEY_ENV,
    _BEARER_TOKEN_ENV,
    _DEFAULT_POLL_REQUEST_TIMEOUT_SECONDS,
    _HTTP_NOT_FOUND,
    _HTTP_OK,
    _HTTP_UNAUTHORIZED,
)
from scripts.full_ai_real_space_canary.json_values import _maybe_string

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject

    from scripts.full_ai_real_space_canary.runner import RealSpaceCanaryConfig


def _resolve_auth_headers(args: argparse.Namespace) -> dict[str, str]:
    api_key = _maybe_string(args.api_key) or _maybe_string(os.getenv(_API_KEY_ENV))
    if api_key is not None:
        return {"X-Artana-Key": api_key}
    bearer_token = _maybe_string(args.bearer_token) or _maybe_string(
        os.getenv(_BEARER_TOKEN_ENV),
    )
    if bearer_token is not None:
        return {"Authorization": f"Bearer {bearer_token}"}
    if bool(args.use_test_auth):
        return {
            "X-TEST-USER-ID": str(args.test_user_id).strip(),
            "X-TEST-USER-EMAIL": str(args.test_user_email).strip(),
            "X-TEST-USER-ROLE": str(args.test_user_role).strip(),
        }
    raise SystemExit(
        "Authentication is required. Provide --api-key / ARTANA_EVIDENCE_API_KEY, "
        "--bearer-token / ARTANA_EVIDENCE_API_BEARER_TOKEN, or --use-test-auth.",
    )


def _request_json(  # noqa: PLR0913
    *,
    client: httpx.Client,
    method: str,
    path: str,
    headers: dict[str, str],
    json_body: JSONObject | None = None,
    acceptable_statuses: tuple[int, ...] = (200,),
    timeout_seconds: float | None = None,
) -> JSONObject:
    response = client.request(
        method=method,
        url=path,
        headers=headers,
        json=json_body,
        timeout=timeout_seconds,
    )
    if response.status_code not in acceptable_statuses:
        raise RuntimeError(
            _format_http_error(
                method=method,
                path=path,
                status_code=response.status_code,
                detail=response.text.strip(),
            ),
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {path} returned non-JSON content") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{method} {path} returned a non-object JSON payload")
    return dict(payload)


def _optional_json_request(
    *,
    client: httpx.Client,
    method: str,
    path: str,
    headers: dict[str, str],
    timeout_seconds: float | None = None,
) -> JSONObject | None:
    response = client.request(
        method=method,
        url=path,
        headers=headers,
        timeout=timeout_seconds,
    )
    if response.status_code == _HTTP_NOT_FOUND:
        return None
    if response.status_code != _HTTP_OK:
        raise RuntimeError(
            _format_http_error(
                method=method,
                path=path,
                status_code=response.status_code,
                detail=response.text.strip(),
            ),
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{method} {path} returned non-JSON content") from exc
    if not isinstance(payload, dict):
        raise TypeError(f"{method} {path} returned a non-object JSON payload")
    return dict(payload)


def _format_http_error(
    *,
    method: str,
    path: str,
    status_code: int,
    detail: str,
) -> str:
    detail_text = f": {detail}" if detail else ""
    if status_code == _HTTP_UNAUTHORIZED and "Signature verification failed" in detail:
        return (
            f"{method} {path} returned HTTP {_HTTP_UNAUTHORIZED}{detail_text}. "
            "Bearer token signature verification failed. Ensure the token was "
            "signed with the same AUTH_JWT_SECRET the Artana Evidence API is "
            "using, or rerun with --api-key / ARTANA_EVIDENCE_API_KEY or "
            "--use-test-auth for local development."
        )
    return f"{method} {path} returned HTTP {status_code}{detail_text}"


def _request_timeout_seconds(config: RealSpaceCanaryConfig) -> float:
    return max(
        1.0,
        min(config.poll_timeout_seconds, _DEFAULT_POLL_REQUEST_TIMEOUT_SECONDS),
    )


def _is_transient_request_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, RuntimeError):
        message = str(exc)
        return "HTTP 500" in message or "HTTP 502" in message or "HTTP 503" in message
    return False


__all__ = [
    "_format_http_error",
    "_is_transient_request_error",
    "_optional_json_request",
    "_request_json",
    "_request_timeout_seconds",
    "_resolve_auth_headers",
]
