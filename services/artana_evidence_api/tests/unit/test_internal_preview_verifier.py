"""Tests for the non-mutating internal-preview boundary verifier."""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urlparse

import pytest

from scripts.verify_internal_preview import (
    HttpResponse,
    PreviewConfig,
    PreviewVerificationError,
    UrllibHttpClient,
    verify_preview,
)

EVIDENCE_URL = "https://evidence.example.test"
GRAPH_URL = "https://graph.example.test"
TESTER_KEY = "art_sk_tester_secret"


class FakeHttpClient:
    """Route-aware fake that distinguishes anonymous and authenticated calls."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        parsed = urlparse(url)
        path = parsed.path
        if path == "/health":
            return _json_response(200, {"status": "ok"})
        if path == "/docs":
            return HttpResponse(status_code=200, body=b"<html>docs</html>")
        if path == "/openapi.json" and parsed.netloc.startswith("evidence"):
            return _json_response(200, _evidence_openapi())
        if path == "/openapi.json":
            return _json_response(200, {"openapi": "3.1.0", "paths": {}})
        if path == "/v2/auth/me":
            key = (headers or {}).get("X-Artana-Key")
            if key == TESTER_KEY:
                return _json_response(
                    200,
                    {"user": {"email": "tester@example.com"}, "default_space": None},
                )
            return _json_response(401, {"detail": "Authentication required"})
        if path == "/v2/spaces":
            key = (headers or {}).get("X-Artana-Key")
            return _json_response(200 if key == TESTER_KEY else 401, [])
        if path.endswith("/entities"):
            return _json_response(401, {"detail": "Authentication required"})
        raise AssertionError(f"Unexpected verifier request: {url}")


def _json_response(status_code: int, payload: object) -> HttpResponse:
    return HttpResponse(status_code=status_code, body=json.dumps(payload).encode())


def _evidence_openapi() -> dict[str, object]:
    return {
        "openapi": "3.1.0",
        "paths": {
            "/v2/auth/me": {"get": {}},
            "/v2/auth/testers": {"post": {}},
            "/v2/auth/api-keys": {"get": {}, "post": {}},
            "/v2/auth/api-keys/{key_id}": {"delete": {}},
            "/v2/auth/api-keys/{key_id}/rotate": {"post": {}},
            "/v2/auth/testers/{user_id}/api-keys": {"get": {}},
            "/v2/auth/testers/{user_id}/api-keys/{key_id}": {"delete": {}},
            "/v2/auth/testers/{user_id}/api-keys/{key_id}/rotate": {"post": {}},
            "/v2/spaces": {"get": {}, "post": {}},
            "/v2/spaces/default": {"put": {}},
        },
    }


def _config(*, api_key: str | None, require_api_key: bool = False) -> PreviewConfig:
    return PreviewConfig(
        evidence_base_url=EVIDENCE_URL,
        graph_base_url=GRAPH_URL,
        api_key=api_key,
        require_api_key=require_api_key,
        timeout_seconds=5.0,
    )


def test_preview_verifier_passes_public_and_authenticated_boundaries() -> None:
    results = verify_preview(_config(api_key=TESTER_KEY), FakeHttpClient())

    assert len(results) == 9
    assert {result.outcome for result in results} == {"PASS"}


def test_preview_verifier_skips_tester_key_when_running_public_ci_probe() -> None:
    results = verify_preview(_config(api_key=None), FakeHttpClient())

    tester_result = next(
        result for result in results if result.name == "evidence.tester-key"
    )
    assert tester_result.outcome == "SKIP"
    assert all(result.outcome != "FAIL" for result in results)


def test_preview_verifier_fails_when_required_tester_key_is_missing() -> None:
    results = verify_preview(
        _config(api_key=None, require_api_key=True),
        FakeHttpClient(),
    )

    tester_result = next(
        result for result in results if result.name == "evidence.tester-key"
    )
    assert tester_result.outcome == "FAIL"


def test_preview_verifier_fails_when_required_openapi_route_is_missing() -> None:
    class MissingRouteClient(FakeHttpClient):
        def get(
            self,
            url: str,
            *,
            headers: Mapping[str, str] | None = None,
        ) -> HttpResponse:
            if url == f"{EVIDENCE_URL}/openapi.json":
                payload = _evidence_openapi()
                paths = payload["paths"]
                assert isinstance(paths, dict)
                del paths["/v2/auth/testers"]
                return _json_response(200, payload)
            return super().get(url, headers=headers)

    results = verify_preview(_config(api_key=TESTER_KEY), MissingRouteClient())

    openapi_result = next(
        result for result in results if result.name == "evidence.openapi"
    )
    assert openapi_result.outcome == "FAIL"
    assert "/v2/auth/testers" in openapi_result.detail


def test_preview_verifier_reports_transport_failure_without_aborting_other_checks() -> (
    None
):
    class HealthTimeoutClient(FakeHttpClient):
        def get(
            self,
            url: str,
            *,
            headers: Mapping[str, str] | None = None,
        ) -> HttpResponse:
            if url == f"{EVIDENCE_URL}/health":
                raise PreviewVerificationError("request timed out")
            return super().get(url, headers=headers)

    results = verify_preview(_config(api_key=TESTER_KEY), HealthTimeoutClient())

    health_result = next(
        result for result in results if result.name == "evidence.health"
    )
    assert health_result.outcome == "FAIL"
    assert health_result.detail == "request timed out"
    assert next(
        result for result in results if result.name == "evidence.docs"
    ).outcome == "PASS"


def test_urllib_client_rejects_non_http_urls() -> None:
    client = UrllibHttpClient(timeout_seconds=1.0)

    with pytest.raises(
        PreviewVerificationError,
        match="request URL must use http or https",
    ):
        client.get("file:///tmp/internal-preview-secret")
