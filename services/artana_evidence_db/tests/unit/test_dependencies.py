"""Unit tests for standalone graph-service access dependencies."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from artana_evidence_db.auth import GraphServiceUser
from artana_evidence_db.dependencies import require_space_role, verify_space_membership
from artana_evidence_db.graph_access import GraphRlsSessionContext
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import UserRole, UserStatus
from fastapi import HTTPException


class _StubSpaceAccess:
    def __init__(self, role: MembershipRole | None) -> None:
        self._role = role

    def get_effective_role(self, space_id, user_id):  # noqa: ANN001
        del space_id, user_id
        return self._role


def _build_user(*, is_graph_admin: bool = False) -> GraphServiceUser:
    return GraphServiceUser(
        id=uuid4(),
        email="graph-user@example.com",
        username="graph-user",
        full_name="Graph User",
        role=UserRole.RESEARCHER,
        status=UserStatus.ACTIVE,
        hashed_password="hashed",
        is_graph_admin=is_graph_admin,
    )


def test_verify_space_membership_allows_member(monkeypatch: pytest.MonkeyPatch) -> None:
    rls_calls: list[GraphRlsSessionContext] = []

    monkeypatch.setattr(
        "artana_evidence_db.dependencies.set_graph_rls_session_context",
        lambda session, *, context: rls_calls.append(context),
    )

    verify_space_membership(
        space_id=uuid4(),
        current_user=_build_user(),
        space_access=_StubSpaceAccess(MembershipRole.RESEARCHER),
        session=SimpleNamespace(),
    )

    assert rls_calls[0].bypass_rls is False


def test_verify_space_membership_rejects_non_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_db.dependencies.set_graph_rls_session_context",
        lambda session, *, context: None,
    )

    with pytest.raises(
        HTTPException,
        match="User is not a member of this graph space",
    ):
        verify_space_membership(
            space_id=uuid4(),
            current_user=_build_user(),
            space_access=_StubSpaceAccess(None),
            session=SimpleNamespace(),
        )


def test_require_space_role_rejects_insufficient_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "artana_evidence_db.dependencies.set_graph_rls_session_context",
        lambda session, *, context: None,
    )

    with pytest.raises(HTTPException, match="User lacks permission for this operation"):
        require_space_role(
            space_id=uuid4(),
            current_user=_build_user(),
            space_access=_StubSpaceAccess(MembershipRole.RESEARCHER),
            session=SimpleNamespace(),
            required_role=MembershipRole.CURATOR,
        )


def test_require_space_role_allows_graph_admin_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rls_calls: list[GraphRlsSessionContext] = []

    monkeypatch.setattr(
        "artana_evidence_db.dependencies.set_graph_rls_session_context",
        lambda session, *, context: rls_calls.append(context),
    )

    require_space_role(
        space_id=uuid4(),
        current_user=_build_user(is_graph_admin=True),
        space_access=_StubSpaceAccess(None),
        session=SimpleNamespace(),
        required_role=MembershipRole.OWNER,
    )

    assert rls_calls[0].is_admin is True
