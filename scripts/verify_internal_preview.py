#!/usr/bin/env python3
"""Verify the externally reachable boundary used by internal preview testers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

_DEFAULT_TIMEOUT_SECONDS = 45.0
_INVALID_API_KEY = "art_sk_internal_preview_boundary_probe_invalid"
_PROTECTED_GRAPH_PATH = "/v1/spaces/00000000-0000-4000-8000-000000000000/entities"
_REQUIRED_EVIDENCE_OPERATIONS: Mapping[str, frozenset[str]] = {
    "/v2/auth/me": frozenset({"get"}),
    "/v2/auth/testers": frozenset({"post"}),
    "/v2/auth/api-keys": frozenset({"get", "post"}),
    "/v2/auth/api-keys/{key_id}": frozenset({"delete"}),
    "/v2/auth/api-keys/{key_id}/rotate": frozenset({"post"}),
    "/v2/auth/testers/{user_id}/api-keys": frozenset({"get"}),
    "/v2/auth/testers/{user_id}/api-keys/{key_id}": frozenset({"delete"}),
    "/v2/auth/testers/{user_id}/api-keys/{key_id}/rotate": frozenset({"post"}),
    "/v2/spaces": frozenset({"get", "post"}),
    "/v2/spaces/default": frozenset({"put"}),
}


class PreviewVerificationError(RuntimeError):
    """Raised when one internal-preview boundary assertion fails."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Small HTTP response contract used by the preview verifier."""

    status_code: int
    body: bytes


class HttpClient(Protocol):
    """HTTP transport boundary so verifier policy can be unit tested."""

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> HttpResponse:
        """Return one HTTP GET response, including non-2xx responses."""


@dataclass(frozen=True, slots=True)
class UrllibHttpClient:
    """Dependency-free HTTP client suitable for deployment workflows."""

    timeout_seconds: float

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> HttpResponse:
        parsed_url = urlsplit(url)
        if parsed_url.scheme not in {"http", "https"} or parsed_url.netloc == "":
            raise PreviewVerificationError("request URL must use http or https")
        request_headers = {"User-Agent": "artana-internal-preview-verifier/1"}
        if headers is not None:
            request_headers.update(headers)
        request = Request(url, headers=request_headers, method="GET")  # noqa: S310
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                return HttpResponse(status_code=response.status, body=response.read())
        except HTTPError as exc:
            return HttpResponse(status_code=exc.code, body=exc.read())
        except URLError as exc:
            raise PreviewVerificationError(f"request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise PreviewVerificationError("request timed out") from exc


@dataclass(frozen=True, slots=True)
class PreviewConfig:
    """Addresses and optional tester credential for one verification run."""

    evidence_base_url: str | None
    graph_base_url: str | None
    api_key: str | None
    require_api_key: bool
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One independently reportable preview-boundary assertion."""

    name: str
    outcome: Literal["PASS", "FAIL", "SKIP"]
    detail: str


def _normalized_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().rstrip("/")
    return normalized or None


def _env_first(*names: str) -> str | None:
    for name in names:
        value = _normalized_optional(os.getenv(name))
        if value is not None:
            return value
    return None


def _url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def _body_excerpt(response: HttpResponse) -> str:
    text = response.body.decode("utf-8", errors="replace").strip()
    return " ".join(text.split())[:200] or "empty response body"


def _expect_status(
    client: HttpClient,
    *,
    base_url: str,
    path: str,
    expected_status: int,
    headers: Mapping[str, str] | None = None,
) -> HttpResponse:
    response = client.get(_url(base_url, path), headers=headers)
    if response.status_code != expected_status:
        raise PreviewVerificationError(
            f"GET {path} returned HTTP {response.status_code}; expected "
            f"{expected_status}. Response: {_body_excerpt(response)}",
        )
    return response


def _json_object(response: HttpResponse, *, path: str) -> Mapping[str, object]:
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreviewVerificationError(f"GET {path} did not return valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise PreviewVerificationError(f"GET {path} did not return a JSON object")
    return payload


def _run_check(name: str, check: Callable[[], object]) -> CheckResult:
    try:
        check()
    except PreviewVerificationError as exc:
        return CheckResult(name=name, outcome="FAIL", detail=str(exc))
    return CheckResult(name=name, outcome="PASS", detail="ok")


def _verify_health(client: HttpClient, *, base_url: str) -> None:
    response = _expect_status(
        client,
        base_url=base_url,
        path="/health",
        expected_status=200,
    )
    payload = _json_object(response, path="/health")
    if payload.get("status") != "ok":
        raise PreviewVerificationError("GET /health did not report status=ok")


def _verify_evidence_openapi(client: HttpClient, *, base_url: str) -> None:
    response = _expect_status(
        client,
        base_url=base_url,
        path="/openapi.json",
        expected_status=200,
    )
    payload = _json_object(response, path="/openapi.json")
    paths = payload.get("paths")
    if not isinstance(paths, Mapping):
        raise PreviewVerificationError("OpenAPI response has no paths object")
    missing: list[str] = []
    for path, methods in _REQUIRED_EVIDENCE_OPERATIONS.items():
        operation = paths.get(path)
        if not isinstance(operation, Mapping):
            missing.append(path)
            continue
        for method in methods:
            if method not in operation:
                missing.append(f"{method.upper()} {path}")
    if missing:
        raise PreviewVerificationError(
            "OpenAPI is missing required preview operations: " + ", ".join(missing),
        )


def _verify_authenticated_evidence(
    client: HttpClient,
    *,
    base_url: str,
    api_key: str,
) -> None:
    headers = {"X-Artana-Key": api_key}
    response = _expect_status(
        client,
        base_url=base_url,
        path="/v2/auth/me",
        expected_status=200,
        headers=headers,
    )
    payload = _json_object(response, path="/v2/auth/me")
    if not isinstance(payload.get("user"), Mapping):
        raise PreviewVerificationError("Authenticated identity response has no user object")
    _expect_status(
        client,
        base_url=base_url,
        path="/v2/spaces",
        expected_status=200,
        headers=headers,
    )


def verify_preview(config: PreviewConfig, client: HttpClient) -> list[CheckResult]:
    """Run non-mutating preview checks and return every result."""
    results: list[CheckResult] = []
    if config.evidence_base_url is not None:
        base_url = config.evidence_base_url
        results.extend(
            [
                _run_check(
                    "evidence.health",
                    lambda: _verify_health(client, base_url=base_url),
                ),
                _run_check(
                    "evidence.docs",
                    lambda: _expect_status(
                        client,
                        base_url=base_url,
                        path="/docs",
                        expected_status=200,
                    ),
                ),
                _run_check(
                    "evidence.openapi",
                    lambda: _verify_evidence_openapi(client, base_url=base_url),
                ),
                _run_check(
                    "evidence.anonymous-denied",
                    lambda: _expect_status(
                        client,
                        base_url=base_url,
                        path="/v2/auth/me",
                        expected_status=401,
                    ),
                ),
                _run_check(
                    "evidence.invalid-key-denied",
                    lambda: _expect_status(
                        client,
                        base_url=base_url,
                        path="/v2/auth/me",
                        expected_status=401,
                        headers={"X-Artana-Key": _INVALID_API_KEY},
                    ),
                ),
            ],
        )
        if config.api_key is not None:
            results.append(
                _run_check(
                    "evidence.tester-key",
                    lambda: _verify_authenticated_evidence(
                        client,
                        base_url=base_url,
                        api_key=config.api_key or "",
                    ),
                ),
            )
        elif config.require_api_key:
            results.append(
                CheckResult(
                    name="evidence.tester-key",
                    outcome="FAIL",
                    detail="--require-api-key was set but no API key was supplied",
                ),
            )
        else:
            results.append(
                CheckResult(
                    name="evidence.tester-key",
                    outcome="SKIP",
                    detail="no API key supplied; public boundary only",
                ),
            )

    if config.graph_base_url is not None:
        graph_url = config.graph_base_url
        results.extend(
            [
                _run_check(
                    "graph.health",
                    lambda: _verify_health(client, base_url=graph_url),
                ),
                _run_check(
                    "graph.openapi",
                    lambda: _expect_status(
                        client,
                        base_url=graph_url,
                        path="/openapi.json",
                        expected_status=200,
                    ),
                ),
                _run_check(
                    "graph.anonymous-data-denied",
                    lambda: _expect_status(
                        client,
                        base_url=graph_url,
                        path=_PROTECTED_GRAPH_PATH,
                        expected_status=401,
                    ),
                ),
            ],
        )
    return results


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify internal-preview reachability, documented contracts, and "
            "fail-closed authentication without mutating service data."
        ),
    )
    parser.add_argument(
        "--evidence-base-url",
        default=_env_first("ARTANA_PREVIEW_BASE_URL", "ARTANA_API_BASE_URL"),
    )
    parser.add_argument(
        "--graph-base-url",
        default=_env_first("ARTANA_PREVIEW_GRAPH_BASE_URL", "GRAPH_API_URL"),
    )
    parser.add_argument(
        "--api-key",
        default=_env_first("ARTANA_PREVIEW_API_KEY", "ARTANA_API_KEY"),
        help="Optional tester key. The verifier never prints it.",
    )
    parser.add_argument(
        "--require-api-key",
        action="store_true",
        help="Fail unless an authenticated tester-key check runs successfully.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=_DEFAULT_TIMEOUT_SECONDS,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    evidence_base_url = _normalized_optional(args.evidence_base_url)
    graph_base_url = _normalized_optional(args.graph_base_url)
    api_key = _normalized_optional(args.api_key)
    if evidence_base_url is None and graph_base_url is None:
        print("error: supply --evidence-base-url and/or --graph-base-url", file=sys.stderr)
        return 2
    if args.timeout_seconds <= 0:
        print("error: --timeout-seconds must be greater than zero", file=sys.stderr)
        return 2
    config = PreviewConfig(
        evidence_base_url=evidence_base_url,
        graph_base_url=graph_base_url,
        api_key=api_key,
        require_api_key=bool(args.require_api_key),
        timeout_seconds=float(args.timeout_seconds),
    )
    client = UrllibHttpClient(timeout_seconds=config.timeout_seconds)
    results = verify_preview(config, client)
    for result in results:
        print(f"[{result.outcome}] {result.name}: {result.detail}")
    passed = sum(result.outcome == "PASS" for result in results)
    skipped = sum(result.outcome == "SKIP" for result in results)
    failed = sum(result.outcome == "FAIL" for result in results)
    print(f"Preview verification: {passed} passed, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
