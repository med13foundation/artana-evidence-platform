"""Unit coverage for standalone graph-harness auth helpers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from artana_evidence_api.api_keys import issue_api_key
from artana_evidence_api.auth import (
    HarnessUser,
    HarnessUserRole,
    HarnessUserStatus,
    _parse_role,
    get_current_harness_user,
    require_harness_write_access,
)
from artana_evidence_api.models.user import HarnessUserModel
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from starlette.requests import Request

_TEST_SECRET = "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"


def _request_with_headers(headers: dict[str, str] | None = None) -> Request:
    raw_headers = [
        (name.lower().encode("ascii"), value.encode("ascii"))
        for name, value in (headers or {}).items()
    ]
    return Request({"type": "http", "headers": raw_headers})


def test_parse_role_preserves_platform_roles() -> None:
    assert _parse_role("ADMIN") == HarnessUserRole.ADMIN
    assert _parse_role("admin") == HarnessUserRole.ADMIN
    assert _parse_role("curator") == HarnessUserRole.CURATOR
    assert _parse_role("researcher") == HarnessUserRole.RESEARCHER
    assert _parse_role("viewer") == HarnessUserRole.VIEWER
    assert _parse_role("service") == HarnessUserRole.SERVICE


def test_parse_role_treats_owner_as_invalid_platform_role(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="artana_evidence_api.auth"):
        role = _parse_role(
            "OWNER",
            context="test subject 11111111-1111-1111-1111-111111111111",
        )

    assert role == HarnessUserRole.VIEWER
    assert "Unknown harness platform role 'owner' from test subject" in caplog.text
    assert "falling back to viewer" in caplog.text


def test_parse_role_warns_on_non_string_role_claim(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="artana_evidence_api.auth"):
        role = _parse_role(
            ["admin"],
            context="access token subject 11111111-1111-1111-1111-111111111111",
        )

    assert role == HarnessUserRole.VIEWER
    assert "Unknown harness platform role 'list' from access token subject" in (
        caplog.text
    )


def test_parse_role_defaults_missing_role_to_viewer_without_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="artana_evidence_api.auth"):
        role = _parse_role(None)

    assert role == HarnessUserRole.VIEWER
    assert [
        record
        for record in caplog.records
        if record.name == "artana_evidence_api.auth"
    ] == []


def test_parse_role_truncates_long_invalid_role_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    role_value = "x" * 80

    with caplog.at_level(logging.WARNING, logger="artana_evidence_api.auth"):
        role = _parse_role(role_value, context="test subject")

    assert role == HarnessUserRole.VIEWER
    assert "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx..." in (
        caplog.text
    )
    assert role_value not in caplog.text


@pytest.mark.asyncio
async def test_get_current_harness_user_accepts_test_headers(monkeypatch) -> None:
    monkeypatch.setenv("TESTING", "true")
    request = _request_with_headers(
        {
            "X-TEST-USER-ID": "11111111-1111-1111-1111-111111111111",
            "X-TEST-USER-EMAIL": "harness-tester@example.com",
            "X-TEST-USER-ROLE": "curator",
        },
    )

    user = await get_current_harness_user(request, credentials=None)

    assert user.id == UUID("11111111-1111-1111-1111-111111111111")
    assert str(user.email) == "harness-tester@example.com"
    assert user.role == HarnessUserRole.CURATOR


@pytest.mark.asyncio
async def test_get_current_harness_user_accepts_platform_access_token(
    monkeypatch,
    db_session: Session,
) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET", _TEST_SECRET)
    token = jwt.encode(
        {
            "sub": "11111111-1111-1111-1111-111111111111",
            "role": "researcher",
            "type": "access",
            "iss": "artana-platform",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        },
        _TEST_SECRET,
        algorithm="HS256",
    )
    request = _request_with_headers()

    user = await get_current_harness_user(
        request,
        credentials=HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token,
        ),
        session=db_session,
    )

    assert user.role == HarnessUserRole.RESEARCHER
    assert (
        str(user.email)
        == "11111111-1111-1111-1111-111111111111@graph-harness.example.com"
    )


@pytest.mark.asyncio
async def test_owner_platform_role_claim_falls_back_to_viewer_and_fails_write_access(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET", _TEST_SECRET)
    token = jwt.encode(
        {
            "sub": "11111111-1111-1111-1111-111111111111",
            "role": "owner",
            "type": "access",
            "iss": "artana-platform",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=15),
        },
        _TEST_SECRET,
        algorithm="HS256",
    )

    with caplog.at_level(logging.WARNING, logger="artana_evidence_api.auth"):
        user = await get_current_harness_user(
            _request_with_headers(),
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=token,
            ),
            session=db_session,
        )

    assert user.role == HarnessUserRole.VIEWER
    assert "Unknown harness platform role 'owner'" in caplog.text
    assert "access token subject 11111111-1111-1111-1111-111111111111" in caplog.text
    with pytest.raises(HTTPException) as exc_info:
        require_harness_write_access(current_user=user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Researcher, curator, or admin role required"


@pytest.mark.asyncio
async def test_get_current_harness_user_reuses_existing_shared_user_for_matching_email(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET", _TEST_SECRET)
    existing_user_id = uuid4()
    db_session.add(
        HarnessUserModel(
            id=existing_user_id,
            email="shared-user@example.com",
            username="shared-user",
            full_name="Shared User",
            hashed_password="external-auth-not-applicable",
            role="researcher",
            status="active",
            email_verified=True,
            login_attempts=0,
        ),
    )
    db_session.commit()
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "role": "admin",
            "status": "active",
            "type": "access",
            "iss": "artana-platform",
            "email": "shared-user@example.com",
            "username": "shared-user",
            "full_name": "Shared User",
        },
        _TEST_SECRET,
        algorithm="HS256",
    )

    user = await get_current_harness_user(
        _request_with_headers(),
        credentials=HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token,
        ),
        session=db_session,
    )

    assert user.id == existing_user_id
    assert str(user.email) == "shared-user@example.com"
    assert user.username == "shared-user"
    assert user.role == HarnessUserRole.ADMIN


@pytest.mark.asyncio
async def test_get_current_harness_user_rejects_username_conflict_for_different_email(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET", _TEST_SECRET)
    db_session.add(
        HarnessUserModel(
            id=uuid4(),
            email="shared-user@example.com",
            username="shared-user",
            full_name="Shared User",
            hashed_password="external-auth-not-applicable",
            role="researcher",
            status="active",
            email_verified=True,
            login_attempts=0,
        ),
    )
    db_session.commit()
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "role": "researcher",
            "status": "active",
            "type": "access",
            "iss": "artana-platform",
            "email": "shared-user@different.example.com",
            "username": "shared-user",
            "full_name": "Shared User",
        },
        _TEST_SECRET,
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc_info:
        await get_current_harness_user(
            _request_with_headers(),
            credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials=token,
            ),
            session=db_session,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Username is already in use"


@pytest.mark.asyncio
async def test_get_current_harness_user_accepts_artana_api_key(
    db_session: Session,
) -> None:
    user_id = uuid4()
    db_session.add(
        HarnessUserModel(
            id=user_id,
            email="api-key-user@example.com",
            username="api-key-user",
            full_name="API Key User",
            hashed_password="external-auth-not-applicable",
            role="researcher",
            status="active",
            email_verified=True,
            login_attempts=0,
        ),
    )
    db_session.commit()
    issued_key = issue_api_key(
        db_session,
        user_id=user_id,
        name="SDK Key",
    )
    request = _request_with_headers({"X-Artana-Key": issued_key.raw_key})

    user = await get_current_harness_user(
        request,
        api_key=issued_key.raw_key,
        credentials=None,
        session=db_session,
    )

    assert user.id == user_id
    assert str(user.email) == "api-key-user@example.com"
    assert user.role == HarnessUserRole.RESEARCHER


def test_require_harness_write_access_rejects_viewer_role() -> None:
    with pytest.raises(HTTPException) as exc_info:
        require_harness_write_access(
            current_user=HarnessUser(
                id=UUID("11111111-1111-1111-1111-111111111111"),
                email="viewer@example.com",
                username="viewer",
                full_name="Viewer",
                role=HarnessUserRole.VIEWER,
                status=HarnessUserStatus.ACTIVE,
            ),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Researcher, curator, or admin role required"
