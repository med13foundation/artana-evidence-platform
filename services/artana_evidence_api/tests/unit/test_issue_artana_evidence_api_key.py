"""Tests for operator-facing Artana API key issuance modes."""

from __future__ import annotations

from typing import Literal

import httpx
import pytest

from scripts.issue_artana_evidence_api_key import (
    IssueApiKeyConfig,
    KeyIssuerError,
    issue_api_key_with_client,
)


def _config(
    *,
    role: Literal["viewer", "researcher", "curator", "admin"] = "researcher",
) -> IssueApiKeyConfig:
    return IssueApiKeyConfig(
        base_url="https://evidence.example.test",
        mode="tester",
        timeout_seconds=5.0,
        bootstrap_key=None,
        api_key="art_sk_admin_secret",
        access_token=None,
        email="tester@example.com",
        username="tester",
        full_name="Tester Example",
        role=role,
        api_key_name="Tester preview key",
        api_key_description="Internal preview",
        create_default_space=True,
    )


def _issued_payload() -> dict[str, object]:
    return {
        "user": {
            "id": "11111111-1111-4111-8111-111111111111",
            "email": "tester@example.com",
            "role": "researcher",
        },
        "api_key": {
            "id": "22222222-2222-4222-8222-222222222222",
            "name": "Tester preview key",
            "key_prefix": "art_sk_test",
            "api_key": "art_sk_new_tester_secret",
        },
        "default_space": {
            "id": "33333333-3333-4333-8333-333333333333",
            "slug": "tester-default",
        },
    }


def test_tester_mode_creates_a_separate_tester_with_admin_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v2/auth/testers"
        assert request.headers["X-Artana-Key"] == "art_sk_admin_secret"
        assert request.read()
        return httpx.Response(201, json=_issued_payload())

    with httpx.Client(
        base_url="https://evidence.example.test",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = issue_api_key_with_client(client, _config())

    assert result.method == "tester"
    assert result.user_email == "tester@example.com"
    assert result.api_key == "art_sk_new_tester_secret"
    assert result.default_space_slug == "tester-default"


def test_tester_mode_rejects_admin_role_before_calling_api() -> None:
    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Unexpected request: {request.url}")

    with httpx.Client(
        base_url="https://evidence.example.test",
        transport=httpx.MockTransport(unexpected_request),
    ) as client, pytest.raises(KeyIssuerError, match="cannot have the admin role"):
        issue_api_key_with_client(client, _config(role="admin"))
