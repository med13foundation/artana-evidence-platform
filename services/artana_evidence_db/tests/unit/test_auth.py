"""Unit coverage for standalone graph-service auth helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from artana_evidence_db.auth import (
    GraphServiceUser,
    get_current_user,
    graph_ai_principal_for_user,
    graph_service_capability_for_user,
    to_graph_rls_session_context,
    to_graph_tenant_membership,
)
from artana_evidence_db.graph_access import GraphAccessRole
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import UserRole, UserStatus
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request


async def test_get_current_user_accepts_jwt_subject_as_valid_email(monkeypatch) -> None:
    secret = "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", "graph-biomedical")
    token = str(
        jwt.encode(
            {
                "sub": "11111111-1111-1111-1111-111111111111",
                "role": UserRole.RESEARCHER.value,
                "type": "access",
                "graph_admin": True,
                "graph_ai_principal": "agent:graph-governor",
                "exp": datetime.now(UTC) + timedelta(minutes=15),
                "iat": datetime.now(UTC),
                "iss": "graph-biomedical",
            },
            secret,
            algorithm="HS256",
        ),
    )
    request = Request({"type": "http", "headers": []})

    user = await get_current_user(
        request,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
    )

    assert (
        user.email == "11111111-1111-1111-1111-111111111111@graph-service.example.com"
    )
    assert user.role == UserRole.RESEARCHER
    assert user.is_graph_admin is True
    assert user.graph_ai_principal == "agent:graph-governor"
    assert graph_ai_principal_for_user(user) == "agent:graph-governor"
    assert graph_service_capability_for_user(user, "space_sync") is False


async def test_get_current_user_accepts_test_graph_ai_principal_header(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TESTING", "true")
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"x-test-user-id", b"11111111-1111-1111-1111-111111111111"),
                (b"x-test-user-email", b"ai-governor@example.com"),
                (b"x-test-user-role", b"researcher"),
                (b"x-test-graph-ai-principal", b"agent:test-governor"),
            ],
        },
    )

    user = await get_current_user(request, None)

    assert user.graph_ai_principal == "agent:test-governor"


async def test_get_current_user_reads_graph_service_capabilities_from_jwt(
    monkeypatch,
) -> None:
    secret = "test-jwt-secret-0123456789abcdefghijklmnopqrstuvwxyz"
    monkeypatch.setenv("GRAPH_JWT_SECRET", secret)
    monkeypatch.setenv("GRAPH_JWT_ISSUER", "graph-biomedical")
    token = str(
        jwt.encode(
            {
                "sub": "11111111-1111-1111-1111-111111111111",
                "role": UserRole.RESEARCHER.value,
                "type": "access",
                "graph_service_capabilities": ["space_sync"],
                "exp": datetime.now(UTC) + timedelta(minutes=15),
                "iat": datetime.now(UTC),
                "iss": "graph-biomedical",
            },
            secret,
            algorithm="HS256",
        ),
    )
    request = Request({"type": "http", "headers": []})

    user = await get_current_user(
        request,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
    )

    assert user.graph_service_capabilities == ("space_sync",)
    assert graph_service_capability_for_user(user, "space_sync") is True


async def test_get_current_user_accepts_test_graph_service_capabilities_header(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TESTING", "true")
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"x-test-user-id", b"11111111-1111-1111-1111-111111111111"),
                (b"x-test-user-email", b"space-sync@example.com"),
                (b"x-test-user-role", b"researcher"),
                (b"x-test-graph-service-capabilities", b"space_sync"),
            ],
        },
    )

    user = await get_current_user(request, None)

    assert user.graph_service_capabilities == ("space_sync",)
    assert graph_service_capability_for_user(user, "space_sync") is True


def test_to_graph_tenant_membership_maps_space_role() -> None:
    membership = to_graph_tenant_membership(
        space_id=UUID("11111111-1111-1111-1111-111111111111"),
        membership_role=MembershipRole.CURATOR,
    )

    assert membership.tenant.tenant_id == "11111111-1111-1111-1111-111111111111"
    assert membership.membership_role == GraphAccessRole.CURATOR


def test_to_graph_rls_session_context_maps_graph_admin() -> None:
    current_user = GraphServiceUser(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        email="graph-admin@example.com",
        username="graph-admin",
        full_name="Graph Admin",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        hashed_password="hashed",
        is_graph_admin=True,
    )

    context = to_graph_rls_session_context(current_user, bypass_rls=True)

    assert context.current_user_id == "11111111-1111-1111-1111-111111111111"
    assert context.has_phi_access is True
    assert context.is_admin is True
    assert context.bypass_rls is True
