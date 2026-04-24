#!/usr/bin/env python3
"""Bootstrap or issue one Artana Evidence API key on demand."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx

_DEFAULT_BASE_URL = "http://localhost:8091"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_DEFAULT_ROLE = "researcher"
_DEFAULT_EMAIL = "developer@example.com"
_DEFAULT_USERNAME = "developer"
_DEFAULT_FULL_NAME = "Developer Example"
_DEFAULT_API_KEY_NAME = "Default SDK Key"
_OUTPUT_CHOICES = ("shell", "json", "key")
_MODE_CHOICES = ("auto", "bootstrap", "create")
_ROLE_CHOICES = ("viewer", "researcher", "curator", "admin")


class KeyIssuerError(RuntimeError):
    """Raised when the key issuance flow cannot complete."""


class APIRequestFailure(KeyIssuerError):
    """Raised when the API returns a non-success response."""

    def __init__(self, *, action: str, status_code: int, detail: str) -> None:
        self.action = action
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{action} failed with HTTP {status_code}: {detail}")


@dataclass(frozen=True, slots=True)
class IssueApiKeyConfig:
    """Configuration for one key issuance attempt."""

    base_url: str
    mode: Literal["auto", "bootstrap", "create"]
    timeout_seconds: float
    bootstrap_key: str | None
    api_key: str | None
    access_token: str | None
    email: str
    username: str | None
    full_name: str | None
    role: Literal["viewer", "researcher", "curator", "admin"]
    api_key_name: str
    api_key_description: str
    create_default_space: bool


@dataclass(frozen=True, slots=True)
class IssuedKeyResult:
    """Normalized result returned by bootstrap or key-creation routes."""

    method: Literal["bootstrap", "create"]
    user_id: str
    user_email: str
    user_role: str
    key_id: str
    key_name: str
    key_prefix: str
    api_key: str
    default_space_id: str | None
    default_space_slug: str | None


def _maybe_string(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _env_first(*names: str) -> str | None:
    for name in names:
        value = _maybe_string(os.getenv(name))
        if value is not None:
            return value
    return None


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Issue one Artana Evidence API key. Use bootstrap mode for the first "
            "key on a fresh deployment, or create mode to mint another key with "
            "an existing credential."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=_env_first("ARTANA_API_BASE_URL", "HARNESS_URL") or _DEFAULT_BASE_URL,
        help="Artana Evidence API base URL. Defaults to http://localhost:8091.",
    )
    parser.add_argument(
        "--mode",
        choices=_MODE_CHOICES,
        default="auto",
        help="auto tries bootstrap first when possible, then falls back to create.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=_DEFAULT_TIMEOUT_SECONDS,
        help="HTTP timeout in seconds. Defaults to 30.",
    )
    parser.add_argument(
        "--bootstrap-key",
        default=_env_first("ARTANA_EVIDENCE_API_BOOTSTRAP_KEY", "ARTANA_BOOTSTRAP_KEY"),
        help="Bootstrap secret for /v2/auth/bootstrap.",
    )
    parser.add_argument(
        "--api-key",
        default=_env_first("ARTANA_API_KEY", "ARTANA_EVIDENCE_API_KEY"),
        help="Existing Artana API key for /v2/auth/api-keys.",
    )
    parser.add_argument(
        "--access-token",
        default=_env_first("ARTANA_ACCESS_TOKEN", "TOKEN"),
        help="Existing bearer token for /v2/auth/api-keys.",
    )
    parser.add_argument(
        "--email",
        default=_env_first("ARTANA_KEY_USER_EMAIL") or _DEFAULT_EMAIL,
        help="Bootstrap user email.",
    )
    parser.add_argument(
        "--username",
        default=_env_first("ARTANA_KEY_USERNAME") or _DEFAULT_USERNAME,
        help="Bootstrap username.",
    )
    parser.add_argument(
        "--full-name",
        default=_env_first("ARTANA_KEY_FULL_NAME") or _DEFAULT_FULL_NAME,
        help="Bootstrap full name.",
    )
    parser.add_argument(
        "--role",
        choices=_ROLE_CHOICES,
        default=_env_first("ARTANA_KEY_ROLE") or _DEFAULT_ROLE,
        help="Bootstrap user role. Defaults to researcher.",
    )
    parser.add_argument(
        "--api-key-name",
        default=_env_first("ARTANA_KEY_NAME") or _DEFAULT_API_KEY_NAME,
        help="Friendly label for the issued API key.",
    )
    parser.add_argument(
        "--api-key-description",
        default=_env_first("ARTANA_KEY_DESCRIPTION") or "",
        help="Optional description stored with the API key.",
    )
    parser.add_argument(
        "--create-default-space",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Create or ensure a default space during bootstrap. Defaults to true.",
    )
    parser.add_argument(
        "--output",
        choices=_OUTPUT_CHOICES,
        default="shell",
        help="Output format: shell exports, json, or the raw key only.",
    )
    return parser.parse_args(argv)


def _config_from_args(args: argparse.Namespace) -> IssueApiKeyConfig:
    bootstrap_key = _maybe_string(args.bootstrap_key)
    api_key = _maybe_string(args.api_key)
    access_token = _maybe_string(args.access_token)
    username = _maybe_string(args.username)
    full_name = _maybe_string(args.full_name)
    api_key_description = _maybe_string(args.api_key_description) or ""
    if args.timeout_seconds <= 0:
        raise KeyIssuerError("--timeout-seconds must be greater than zero.")
    return IssueApiKeyConfig(
        base_url=_maybe_string(args.base_url) or _DEFAULT_BASE_URL,
        mode=args.mode,
        timeout_seconds=float(args.timeout_seconds),
        bootstrap_key=bootstrap_key,
        api_key=api_key,
        access_token=access_token,
        email=str(args.email).strip().lower(),
        username=username,
        full_name=full_name,
        role=args.role,
        api_key_name=str(args.api_key_name).strip() or _DEFAULT_API_KEY_NAME,
        api_key_description=api_key_description,
        create_default_space=bool(args.create_default_space),
    )


def _json_object(response: httpx.Response) -> Mapping[str, object]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise KeyIssuerError(
            f"Expected JSON response from {response.request.url}, got invalid JSON.",
        ) from exc
    if not isinstance(payload, Mapping):
        raise KeyIssuerError(
            f"Expected JSON object response from {response.request.url}, got {type(payload).__name__}.",
        )
    return payload


def _response_detail(response: httpx.Response) -> str:
    payload = _json_object(response)
    detail = payload.get("detail")
    if isinstance(detail, str) and detail.strip() != "":
        return detail.strip()
    return response.text.strip() or "Request failed without a JSON detail message."


def _raise_if_error(response: httpx.Response, *, action: str) -> None:
    if 200 <= response.status_code < 300:
        return
    raise APIRequestFailure(
        action=action,
        status_code=response.status_code,
        detail=_response_detail(response),
    )


def _parse_issued_key_result(
    payload: Mapping[str, object],
    *,
    method: Literal["bootstrap", "create"],
) -> IssuedKeyResult:
    user_obj = payload.get("user")
    api_key_obj = payload.get("api_key")
    default_space_obj = payload.get("default_space")
    if not isinstance(user_obj, Mapping):
        raise KeyIssuerError("Response did not include a valid user object.")
    if not isinstance(api_key_obj, Mapping):
        raise KeyIssuerError("Response did not include a valid api_key object.")
    if default_space_obj is not None and not isinstance(default_space_obj, Mapping):
        raise KeyIssuerError("Response did not include a valid default_space object.")

    def _required_string(container: Mapping[str, object], key: str) -> str:
        value = container.get(key)
        if not isinstance(value, str) or value.strip() == "":
            raise KeyIssuerError(f"Response field {key!r} was missing or empty.")
        return value

    default_space_id = None
    default_space_slug = None
    if isinstance(default_space_obj, Mapping):
        default_space_id = _required_string(default_space_obj, "id")
        default_space_slug = _required_string(default_space_obj, "slug")

    return IssuedKeyResult(
        method=method,
        user_id=_required_string(user_obj, "id"),
        user_email=_required_string(user_obj, "email"),
        user_role=_required_string(user_obj, "role"),
        key_id=_required_string(api_key_obj, "id"),
        key_name=_required_string(api_key_obj, "name"),
        key_prefix=_required_string(api_key_obj, "key_prefix"),
        api_key=_required_string(api_key_obj, "api_key"),
        default_space_id=default_space_id,
        default_space_slug=default_space_slug,
    )


def _bootstrap_headers(config: IssueApiKeyConfig) -> dict[str, str]:
    bootstrap_key = _maybe_string(config.bootstrap_key)
    if bootstrap_key is None:
        raise KeyIssuerError(
            "Bootstrap mode requires --bootstrap-key or ARTANA_EVIDENCE_API_BOOTSTRAP_KEY.",
        )
    return {"X-Artana-Bootstrap-Key": bootstrap_key}


def _auth_headers(config: IssueApiKeyConfig) -> dict[str, str]:
    api_key = _maybe_string(config.api_key)
    access_token = _maybe_string(config.access_token)
    if api_key is not None:
        return {"X-Artana-Key": api_key}
    if access_token is not None:
        return {"Authorization": f"Bearer {access_token}"}
    raise KeyIssuerError(
        "Create mode requires --api-key, --access-token, ARTANA_API_KEY, or TOKEN.",
    )


def _bootstrap_payload(config: IssueApiKeyConfig) -> dict[str, object]:
    payload: dict[str, object] = {
        "email": config.email,
        "role": config.role,
        "api_key_name": config.api_key_name,
        "api_key_description": config.api_key_description,
        "create_default_space": config.create_default_space,
    }
    if config.username is not None:
        payload["username"] = config.username
    if config.full_name is not None:
        payload["full_name"] = config.full_name
    return payload


def _create_key_payload(config: IssueApiKeyConfig) -> dict[str, object]:
    return {
        "name": config.api_key_name,
        "description": config.api_key_description,
    }


def _bootstrap_one_key(
    client: httpx.Client,
    config: IssueApiKeyConfig,
) -> IssuedKeyResult:
    response = client.post(
        "/v2/auth/bootstrap",
        headers=_bootstrap_headers(config),
        json=_bootstrap_payload(config),
    )
    _raise_if_error(response, action="Bootstrap API key issuance")
    return _parse_issued_key_result(_json_object(response), method="bootstrap")


def _create_one_key(
    client: httpx.Client,
    config: IssueApiKeyConfig,
) -> IssuedKeyResult:
    response = client.post(
        "/v2/auth/api-keys",
        headers=_auth_headers(config),
        json=_create_key_payload(config),
    )
    _raise_if_error(response, action="Additional API key issuance")
    return _parse_issued_key_result(_json_object(response), method="create")


def issue_api_key_with_client(
    client: httpx.Client,
    config: IssueApiKeyConfig,
) -> IssuedKeyResult:
    """Run the requested issuance flow against one already-open HTTP client."""
    if config.mode == "bootstrap":
        return _bootstrap_one_key(client, config)
    if config.mode == "create":
        return _create_one_key(client, config)

    has_bootstrap = _maybe_string(config.bootstrap_key) is not None
    has_auth = _maybe_string(config.api_key) is not None or _maybe_string(
        config.access_token,
    ) is not None

    if has_bootstrap and not has_auth:
        try:
            return _bootstrap_one_key(client, config)
        except APIRequestFailure as exc:
            if exc.status_code == 409:
                raise KeyIssuerError(
                    "Bootstrap has already been completed for this deployment. "
                    "Re-run with --api-key or --access-token to create another key.",
                ) from exc
            raise

    if has_auth and not has_bootstrap:
        return _create_one_key(client, config)

    if has_bootstrap and has_auth:
        try:
            return _bootstrap_one_key(client, config)
        except APIRequestFailure as exc:
            if exc.status_code == 409:
                return _create_one_key(client, config)
            raise

    raise KeyIssuerError(
        "Auto mode needs either a bootstrap key for first-time setup or an existing "
        "API key / bearer token to create another key.",
    )


def issue_api_key(config: IssueApiKeyConfig) -> IssuedKeyResult:
    """Run the requested issuance flow with a fresh HTTP client."""
    with httpx.Client(
        base_url=config.base_url.rstrip("/"),
        timeout=config.timeout_seconds,
        follow_redirects=True,
    ) as client:
        return issue_api_key_with_client(client, config)


def _shell_quote(value: str) -> str:
    return shlex.quote(value)


def _shell_output(result: IssuedKeyResult, *, base_url: str) -> str:
    lines = [
        f"export ARTANA_API_BASE_URL={_shell_quote(base_url.rstrip('/'))}",
        f"export ARTANA_API_KEY={_shell_quote(result.api_key)}",
        f"export ARTANA_KEY_ID={_shell_quote(result.key_id)}",
        f"export ARTANA_KEY_METHOD={_shell_quote(result.method)}",
        f"export ARTANA_USER_EMAIL={_shell_quote(result.user_email)}",
    ]
    if result.default_space_id is not None:
        lines.append(
            f"export ARTANA_DEFAULT_SPACE_ID={_shell_quote(result.default_space_id)}",
        )
    if result.default_space_slug is not None:
        lines.append(
            f"export ARTANA_DEFAULT_SPACE_SLUG={_shell_quote(result.default_space_slug)}",
        )
    return "\n".join(lines)


def _json_output(result: IssuedKeyResult, *, base_url: str) -> str:
    payload = {
        "base_url": base_url.rstrip("/"),
        "method": result.method,
        "user_id": result.user_id,
        "user_email": result.user_email,
        "user_role": result.user_role,
        "key_id": result.key_id,
        "key_name": result.key_name,
        "key_prefix": result.key_prefix,
        "api_key": result.api_key,
        "default_space_id": result.default_space_id,
        "default_space_slug": result.default_space_slug,
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _format_output(
    result: IssuedKeyResult,
    *,
    base_url: str,
    output: Literal["shell", "json", "key"],
) -> str:
    if output == "key":
        return result.api_key
    if output == "json":
        return _json_output(result, base_url=base_url)
    return _shell_output(result, base_url=base_url)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        config = _config_from_args(args)
        result = issue_api_key(config)
    except (KeyIssuerError, httpx.HTTPError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        _format_output(
            result,
            base_url=config.base_url,
            output=args.output,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
