"""Unit tests for space-level access control enforcement."""

from __future__ import annotations

from typing import Final
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.app import create_app
from artana_evidence_api.auth import HarnessUser, HarnessUserRole, HarnessUserStatus
from artana_evidence_api.dependencies import (
    get_research_space_store,
)
from artana_evidence_api.models.user import HarnessUserModel
from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceStore,
)
from artana_evidence_api.space_acl import check_space_access, role_at_least
from artana_evidence_api.sqlalchemy_stores import (
    SqlAlchemyHarnessResearchSpaceStore,
)
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

_OWNER_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_OWNER_USER_EMAIL: Final[str] = "owner@example.com"
_OTHER_USER_ID: Final[str] = "22222222-2222-2222-2222-222222222222"
_OTHER_USER_EMAIL: Final[str] = "other@example.com"
_SERVICE_USER_ID: Final[str] = "33333333-3333-3333-3333-333333333333"
_SERVICE_USER_EMAIL: Final[str] = "research_inbox_runtime@artana.dev"


def _make_user(
    *,
    user_id: str = _OWNER_USER_ID,
    email: str = _OWNER_USER_EMAIL,
    role: HarnessUserRole = HarnessUserRole.RESEARCHER,
) -> HarnessUser:
    return HarnessUser(
        id=UUID(user_id),
        email=email,
        username=email.split("@")[0],
        full_name=email,
        role=role,
        status=HarnessUserStatus.ACTIVE,
    )


def _auth_headers(
    *,
    user_id: str = _OWNER_USER_ID,
    email: str = _OWNER_USER_EMAIL,
    role: str = "researcher",
) -> dict[str, str]:
    return {
        "X-TEST-USER-ID": user_id,
        "X-TEST-USER-EMAIL": email,
        "X-TEST-USER-ROLE": role,
    }


def _persist_sqlalchemy_user(
    db_session: Session,
    *,
    user_id: str,
    email: str,
    role: str = "researcher",
) -> None:
    user = HarnessUserModel(
        id=UUID(user_id),
        email=email,
        username=email.split("@")[0],
        full_name=email,
        hashed_password="not-used-in-this-test",
        role=role,
        status=HarnessUserStatus.ACTIVE.value,
    )
    db_session.add(user)
    db_session.commit()


# ---------------------------------------------------------------------------
# role_at_least tests
# ---------------------------------------------------------------------------


class TestRoleAtLeast:
    def test_owner_is_at_least_viewer(self) -> None:
        assert role_at_least("owner", "viewer") is True

    def test_viewer_is_not_researcher(self) -> None:
        assert role_at_least("viewer", "researcher") is False

    def test_researcher_is_at_least_viewer(self) -> None:
        assert role_at_least("researcher", "viewer") is True

    def test_admin_is_at_least_owner(self) -> None:
        # admin is second in hierarchy, owner is first
        assert role_at_least("admin", "owner") is False

    def test_owner_is_at_least_owner(self) -> None:
        assert role_at_least("owner", "owner") is True

    def test_unknown_role_is_not_sufficient(self) -> None:
        assert role_at_least("unknown", "viewer") is False

    def test_curator_is_at_least_researcher(self) -> None:
        assert role_at_least("curator", "researcher") is True


# ---------------------------------------------------------------------------
# check_space_access tests
# ---------------------------------------------------------------------------


class TestCheckSpaceAccess:
    def _create_store_with_space(
        self,
    ) -> tuple[HarnessResearchSpaceStore, str]:
        store = HarnessResearchSpaceStore()
        record = store.create_space(
            owner_id=_OWNER_USER_ID,
            name="Test Space",
            description="desc",
        )
        return store, record.id

    def test_owner_can_access_own_space(self) -> None:
        store, space_id = self._create_store_with_space()
        user = _make_user()
        result = check_space_access(
            space_id=UUID(space_id),
            current_user=user,
            research_space_store=store,
            minimum_role="viewer",
        )
        assert result == user

    def test_service_user_bypasses_all_checks(self) -> None:
        store, space_id = self._create_store_with_space()
        service_user = _make_user(
            user_id=_SERVICE_USER_ID,
            email=_SERVICE_USER_EMAIL,
            role=HarnessUserRole.SERVICE,
        )
        result = check_space_access(
            space_id=UUID(space_id),
            current_user=service_user,
            research_space_store=store,
            minimum_role="owner",
        )
        assert result == service_user

    def test_admin_user_bypasses_membership_check(self) -> None:
        store, space_id = self._create_store_with_space()
        admin_user = _make_user(
            user_id=_OTHER_USER_ID,
            email=_OTHER_USER_EMAIL,
            role=HarnessUserRole.ADMIN,
        )
        result = check_space_access(
            space_id=UUID(space_id),
            current_user=admin_user,
            research_space_store=store,
            minimum_role="owner",
        )
        assert result == admin_user

    def test_audit_mode_logs_but_allows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SPACE_ACL_MODE", "audit")
        from artana_evidence_api.config import get_settings

        get_settings.cache_clear()
        try:
            store = HarnessResearchSpaceStore()
            record = store.create_space(
                owner_id=_OWNER_USER_ID,
                name="Audit Test",
                description="desc",
            )
            other_user = _make_user(
                user_id=_OTHER_USER_ID,
                email=_OTHER_USER_EMAIL,
            )
            # Non-member should still pass in audit mode
            result = check_space_access(
                space_id=UUID(record.id),
                current_user=other_user,
                research_space_store=store,
                minimum_role="viewer",
            )
            assert result == other_user
        finally:
            get_settings.cache_clear()

    def test_enforce_mode_blocks_non_member(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SPACE_ACL_MODE", "enforce")
        from artana_evidence_api.config import get_settings

        get_settings.cache_clear()
        try:
            store = HarnessResearchSpaceStore()
            record = store.create_space(
                owner_id=_OWNER_USER_ID,
                name="Enforce Test",
                description="desc",
            )
            other_user = _make_user(
                user_id=_OTHER_USER_ID,
                email=_OTHER_USER_EMAIL,
            )
            with pytest.raises(HTTPException) as exc_info:
                check_space_access(
                    space_id=UUID(record.id),
                    current_user=other_user,
                    research_space_store=store,
                    minimum_role="viewer",
                )
            assert exc_info.value.status_code == 403
        finally:
            get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Membership store tests
# ---------------------------------------------------------------------------


class TestMembershipStore:
    def _create_store_with_space(
        self,
    ) -> tuple[HarnessResearchSpaceStore, str]:
        store = HarnessResearchSpaceStore()
        record = store.create_space(
            owner_id=_OWNER_USER_ID,
            name="Members Test Space",
            description="desc",
        )
        return store, record.id

    def test_add_member(self) -> None:
        store, space_id = self._create_store_with_space()
        member = store.add_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
            role="viewer",
            invited_by=_OWNER_USER_ID,
        )
        assert member.user_id == _OTHER_USER_ID
        assert member.role == "viewer"
        assert member.is_active is True

    @pytest.mark.parametrize("role", ["admin", "curator", "researcher", "viewer"])
    def test_add_member_accepts_assignable_roles(self, role: str) -> None:
        store, space_id = self._create_store_with_space()
        member = store.add_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
            role=role,
        )
        assert member.role == role

    @pytest.mark.parametrize("role", ["owner", "editor", "bogus"])
    def test_add_member_rejects_invalid_roles(self, role: str) -> None:
        store, space_id = self._create_store_with_space()
        with pytest.raises(ValueError):
            store.add_member(
                space_id=space_id,
                user_id=_OTHER_USER_ID,
                role=role,
            )

    def test_list_members(self) -> None:
        store, space_id = self._create_store_with_space()
        store.add_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
            role="researcher",
        )
        members = store.list_members(space_id=space_id)
        assert len(members) == 1
        assert members[0].user_id == _OTHER_USER_ID

    def test_remove_member(self) -> None:
        store, space_id = self._create_store_with_space()
        store.add_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
            role="viewer",
        )
        removed = store.remove_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
        )
        assert removed is not None
        assert removed.is_active is False
        # After removal, listing should return empty
        members = store.list_members(space_id=space_id)
        assert len(members) == 0

    def test_remove_nonexistent_member_returns_none(self) -> None:
        store, space_id = self._create_store_with_space()
        result = store.remove_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
        )
        assert result is None

    def test_add_member_to_nonexistent_space_raises(self) -> None:
        store = HarnessResearchSpaceStore()
        with pytest.raises(KeyError):
            store.add_member(
                space_id=str(uuid4()),
                user_id=_OTHER_USER_ID,
                role="viewer",
            )

    def test_add_existing_member_updates_role(self) -> None:
        store, space_id = self._create_store_with_space()
        store.add_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
            role="viewer",
        )
        updated = store.add_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
            role="researcher",
        )
        assert updated.role == "researcher"
        members = store.list_members(space_id=space_id)
        assert len(members) == 1
        assert members[0].role == "researcher"


class TestSqlAlchemyMembershipStore:
    def _create_store_with_space(
        self,
        db_session: Session,
    ) -> tuple[SqlAlchemyHarnessResearchSpaceStore, str]:
        store = SqlAlchemyHarnessResearchSpaceStore(db_session)
        record = store.create_space(
            owner_id=_OWNER_USER_ID,
            name="Members SQLAlchemy Test Space",
            description="desc",
        )
        return store, record.id

    def test_add_member_rejects_invalid_roles(
        self,
        db_session: Session,
    ) -> None:
        store, space_id = self._create_store_with_space(db_session)
        with pytest.raises(ValueError):
            store.add_member(
                space_id=space_id,
                user_id=_OTHER_USER_ID,
                role="owner",
            )

    def test_add_member_accepts_assignable_roles(
        self,
        db_session: Session,
    ) -> None:
        store, space_id = self._create_store_with_space(db_session)
        _persist_sqlalchemy_user(
            db_session,
            user_id=_OTHER_USER_ID,
            email=_OTHER_USER_EMAIL,
        )
        member = store.add_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
            role="curator",
        )
        assert member.role == "curator"

    def test_add_member_bootstraps_missing_user_record(
        self,
        db_session: Session,
    ) -> None:
        store, space_id = self._create_store_with_space(db_session)

        member = store.add_member(
            space_id=space_id,
            user_id=_OTHER_USER_ID,
            role="viewer",
        )

        assert member.user_id == _OTHER_USER_ID
        persisted_user = db_session.get(HarnessUserModel, UUID(_OTHER_USER_ID))
        assert persisted_user is not None
        assert persisted_user.email == f"{_OTHER_USER_ID}@graph-harness.example.com"


# ---------------------------------------------------------------------------
# Router endpoint tests
# ---------------------------------------------------------------------------


def _build_client() -> tuple[TestClient, HarnessResearchSpaceStore]:
    app = create_app()
    store = HarnessResearchSpaceStore()
    app.dependency_overrides[get_research_space_store] = lambda: store
    return TestClient(app), store


class TestMemberEndpoints:
    def test_list_members_empty(self) -> None:
        client, store = _build_client()
        record = store.create_space(
            owner_id=_OWNER_USER_ID,
            name="Test Space",
            description="desc",
        )
        resp = client.get(
            f"/v1/spaces/{record.id}/members",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["members"] == []

    def test_add_and_list_member(self) -> None:
        client, store = _build_client()
        record = store.create_space(
            owner_id=_OWNER_USER_ID,
            name="Test Space",
            description="desc",
        )
        resp = client.post(
            f"/v1/spaces/{record.id}/members",
            headers=_auth_headers(),
            json={"user_id": _OTHER_USER_ID, "role": "viewer"},
        )
        assert resp.status_code == 201
        member = resp.json()
        assert member["user_id"] == _OTHER_USER_ID
        assert member["role"] == "viewer"

        # List should now contain the new member
        resp = client.get(
            f"/v1/spaces/{record.id}/members",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_remove_member(self) -> None:
        client, store = _build_client()
        record = store.create_space(
            owner_id=_OWNER_USER_ID,
            name="Test Space",
            description="desc",
        )
        store.add_member(
            space_id=record.id,
            user_id=_OTHER_USER_ID,
            role="viewer",
        )
        resp = client.delete(
            f"/v1/spaces/{record.id}/members/{_OTHER_USER_ID}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_active"] is False

    def test_remove_nonexistent_member_returns_404(self) -> None:
        client, store = _build_client()
        record = store.create_space(
            owner_id=_OWNER_USER_ID,
            name="Test Space",
            description="desc",
        )
        resp = client.delete(
            f"/v1/spaces/{record.id}/members/{_OTHER_USER_ID}",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404

    @pytest.mark.parametrize("role", ["owner", "editor", "bogus"])
    def test_add_member_rejects_invalid_roles(self, role: str) -> None:
        client, store = _build_client()
        record = store.create_space(
            owner_id=_OWNER_USER_ID,
            name="Test Space",
            description="desc",
        )
        resp = client.post(
            f"/v1/spaces/{record.id}/members",
            headers=_auth_headers(),
            json={"user_id": _OTHER_USER_ID, "role": role},
        )
        assert resp.status_code == 422

    def test_viewer_cannot_add_member(self) -> None:
        client, store = _build_client()
        record = store.create_space(
            owner_id=_OWNER_USER_ID,
            name="Test Space",
            description="desc",
        )
        resp = client.post(
            f"/v1/spaces/{record.id}/members",
            headers=_auth_headers(role="viewer"),
            json={"user_id": _OTHER_USER_ID, "role": "viewer"},
        )
        # Viewer cannot write, so should get 403
        assert resp.status_code == 403

    def test_member_cannot_use_owner_route_in_audit_mode(
        self,
        db_session: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("SPACE_ACL_MODE", "audit")
        from artana_evidence_api.config import get_settings

        get_settings.cache_clear()
        try:
            app = create_app()
            app.dependency_overrides[get_research_space_store] = (
                lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
            )
            store = SqlAlchemyHarnessResearchSpaceStore(db_session)
            record = store.create_space(
                owner_id=_OWNER_USER_ID,
                name="DB Test Space",
                description="desc",
            )
            store.add_member(
                space_id=record.id,
                user_id=_OTHER_USER_ID,
                role="researcher",
            )

            with TestClient(app) as client:
                resp = client.patch(
                    f"/v1/spaces/{record.id}/settings",
                    headers=_auth_headers(
                        user_id=_OTHER_USER_ID,
                        email=_OTHER_USER_EMAIL,
                        role="researcher",
                    ),
                    json={"research_orchestration_mode": "full_ai_shadow"},
                )

            assert resp.status_code == 403
            assert resp.json()["detail"] == "Owner access to this space is required"
        finally:
            get_settings.cache_clear()

    def test_db_backed_add_member_requires_existing_user(
        self,
        db_session: Session,
    ) -> None:
        app = create_app()
        app.dependency_overrides[get_research_space_store] = (
            lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
        )

        with TestClient(app) as client:
            store = SqlAlchemyHarnessResearchSpaceStore(db_session)
            record = store.create_space(
                owner_id=_OWNER_USER_ID,
                name="DB Test Space",
                description="desc",
            )
            response = client.post(
                f"/v1/spaces/{record.id}/members",
                headers=_auth_headers(),
                json={"user_id": _OTHER_USER_ID, "role": "viewer"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == (
            "User must exist before they can be added to a space"
        )
        persisted_user = db_session.get(HarnessUserModel, UUID(_OTHER_USER_ID))
        assert persisted_user is None

        _persist_sqlalchemy_user(
            db_session,
            user_id=_OTHER_USER_ID,
            email=_OTHER_USER_EMAIL,
        )
        with TestClient(app) as client:
            retry_response = client.post(
                f"/v1/spaces/{record.id}/members",
                headers=_auth_headers(),
                json={"user_id": _OTHER_USER_ID, "role": "viewer"},
            )

        assert retry_response.status_code == 201
        payload = retry_response.json()
        assert payload["user_id"] == _OTHER_USER_ID


class TestServiceRoleEnum:
    def test_service_role_exists(self) -> None:
        assert HarnessUserRole.SERVICE.value == "service"

    def test_service_user_can_be_built(self) -> None:
        user = _make_user(role=HarnessUserRole.SERVICE)
        assert user.role == HarnessUserRole.SERVICE
