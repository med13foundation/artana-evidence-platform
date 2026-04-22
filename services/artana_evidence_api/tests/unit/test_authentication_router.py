"""Unit tests for standalone harness API key management routes."""

from __future__ import annotations

import os
from unittest.mock import Mock
from uuid import UUID

import jwt
from artana_evidence_api.api_keys import BOOTSTRAP_KEY_HEADER
from artana_evidence_api.app import create_app
from artana_evidence_api.database import get_session
from artana_evidence_api.dependencies import get_research_space_store
from artana_evidence_api.models.api_key import HarnessApiKeyModel
from artana_evidence_api.models.user import HarnessUserModel
from artana_evidence_api.routers import authentication as authentication_router
from artana_evidence_api.sqlalchemy_stores import SqlAlchemyHarnessResearchSpaceStore
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

_AUTH_TEST_SECRET = os.environ["AUTH_JWT_SECRET"]


def _jwt_auth_headers(
    *,
    user_id: str,
    email: str,
    role: str = "researcher",
) -> dict[str, str]:
    token = jwt.encode(
        {
            "iss": "artana-platform",
            "sub": user_id,
            "type": "access",
            "role": role,
            "status": "active",
            "email": email,
            "username": email.split("@", maxsplit=1)[0],
            "full_name": email,
        },
        _AUTH_TEST_SECRET,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def test_bootstrap_route_issues_api_key_and_default_space(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY",
        "bootstrap-secret",
    )
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )

    with TestClient(app) as client:
        bootstrap_response = client.post(
            "/v1/auth/bootstrap",
            headers={"X-Artana-Bootstrap-Key": "bootstrap-secret"},
            json={
                "email": "developer@example.com",
                "username": "developer",
                "full_name": "Developer Example",
                "role": "researcher",
                "api_key_name": "SDK Key",
                "create_default_space": True,
            },
        )

        assert bootstrap_response.status_code == 201
        bootstrap_payload = bootstrap_response.json()
        assert bootstrap_payload["user"]["email"] == "developer@example.com"
        assert bootstrap_payload["api_key"]["api_key"].startswith("art_sk_")
        assert bootstrap_payload["default_space"]["is_default"] is True

        issued_api_key = bootstrap_payload["api_key"]["api_key"]
        me_response = client.get(
            "/v1/auth/me",
            headers={"X-Artana-Key": issued_api_key},
        )
        assert me_response.status_code == 200
        assert me_response.json()["user"]["email"] == "developer@example.com"

        create_key_response = client.post(
            "/v1/auth/api-keys",
            headers={"X-Artana-Key": issued_api_key},
            json={"name": "CLI Key", "description": "Automation"},
        )
        assert create_key_response.status_code == 201
        create_key_payload = create_key_response.json()
        assert create_key_payload["api_key"]["name"] == "CLI Key"
        assert create_key_payload["api_key"]["api_key"].startswith("art_sk_")


def test_bootstrap_route_rejects_missing_bootstrap_key_when_configured(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY",
        "bootstrap-secret",
    )
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/auth/bootstrap",
            json={"email": "developer@example.com"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid bootstrap key"


def test_bootstrap_route_uses_constant_time_bootstrap_key_compare(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY",
        "bootstrap-secret",
    )
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )
    compare_digest = Mock(return_value=False)
    monkeypatch.setattr(authentication_router.hmac, "compare_digest", compare_digest)

    with TestClient(app) as client:
        response = client.post(
            "/v1/auth/bootstrap",
            headers={"X-Artana-Bootstrap-Key": "  wrong-secret  "},
            json={"email": "developer@example.com"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid bootstrap key"
    compare_digest.assert_called_once_with("wrong-secret", "bootstrap-secret")


def test_bootstrap_route_rejects_second_bootstrap_attempt(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY",
        "bootstrap-secret",
    )
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )

    with TestClient(app) as client:
        first_response = client.post(
            "/v1/auth/bootstrap",
            headers={"X-Artana-Bootstrap-Key": "bootstrap-secret"},
            json={"email": "developer@example.com"},
        )
        second_response = client.post(
            "/v1/auth/bootstrap",
            headers={"X-Artana-Bootstrap-Key": "bootstrap-secret"},
            json={"email": "second@example.com"},
        )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert (
        second_response.json()["detail"]
        == "Bootstrap has already been completed for this deployment"
    )

    users = db_session.execute(select(HarnessUserModel)).scalars().all()
    assert [user.email for user in users] == ["developer@example.com"]


def test_bootstrap_route_recovers_existing_user_without_api_key(
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY",
        "bootstrap-secret",
    )
    existing_user = HarnessUserModel(
        id=UUID("00000000-0000-4000-a000-000000000218"),
        email="developer@example.com",
        username="developer",
        full_name="Developer Example",
        hashed_password="external-auth-not-applicable",
        role="researcher",
        status="active",
        email_verified=True,
        login_attempts=0,
    )
    db_session.add(existing_user)
    db_session.commit()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/auth/bootstrap",
            headers={"X-Artana-Bootstrap-Key": "bootstrap-secret"},
            json={
                "email": "ignored@example.com",
                "username": "ignored",
                "full_name": "Ignored",
                "role": "admin",
                "api_key_name": "Recovered Key",
                "create_default_space": True,
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["id"] == str(existing_user.id)
    assert payload["user"]["email"] == existing_user.email
    assert payload["api_key"]["name"] == "Recovered Key"
    assert payload["api_key"]["api_key"].startswith("art_sk_")
    assert payload["default_space"]["is_default"] is True

    users = db_session.execute(select(HarnessUserModel)).scalars().all()
    assert [user.email for user in users] == ["developer@example.com"]
    api_keys = db_session.execute(select(HarnessApiKeyModel)).scalars().all()
    assert len(api_keys) == 1
    assert api_keys[0].user_id == existing_user.id


def test_auth_me_reuses_existing_shared_user_for_jwt_identity_mismatch(
    db_session: Session,
) -> None:
    app = create_app()
    store = SqlAlchemyHarnessResearchSpaceStore(db_session)
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_research_space_store] = lambda: store
    existing_user_id = UUID("00000000-0000-4000-a000-000000e20704")
    db_session.add(
        HarnessUserModel(
            id=existing_user_id,
            email="issue207-auth@example.com",
            username="issue207-auth",
            full_name="Issue 207 Auth",
            hashed_password="external-auth-not-applicable",
            role="researcher",
            status="active",
            email_verified=True,
            login_attempts=0,
        ),
    )
    db_session.commit()
    existing_default = store.ensure_default_space(
        owner_id=existing_user_id,
        owner_email="issue207-auth@example.com",
        owner_username="issue207-auth",
        owner_role="researcher",
    )

    with TestClient(app) as client:
        response = client.get(
            "/v1/auth/me",
            headers=_jwt_auth_headers(
                user_id="00000000-0000-4000-a000-000000e20796",
                email="issue207-auth@example.com",
            ),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["id"] == str(existing_user_id)
    assert payload["user"]["email"] == "issue207-auth@example.com"
    assert payload["default_space"]["id"] == existing_default.id


def _bootstrap_and_get_client(db_session, monkeypatch):
    """Helper: bootstrap one user and return (TestClient, api_key, user_id)."""
    monkeypatch.setenv("ARTANA_EVIDENCE_API_BOOTSTRAP_KEY", "bootstrap-secret")
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )
    client = TestClient(app)
    resp = client.post(
        "/v1/auth/bootstrap",
        headers={"X-Artana-Bootstrap-Key": "bootstrap-secret"},
        json={"email": "dev@example.com", "create_default_space": True},
    )
    assert resp.status_code == 201
    payload = resp.json()
    return client, payload["api_key"]["api_key"], payload["user"]["id"]


def test_list_api_keys_returns_keys_without_full_secret(
    db_session: Session,
    monkeypatch,
) -> None:
    client, api_key, user_id = _bootstrap_and_get_client(db_session, monkeypatch)
    # Create a second key
    client.post(
        "/v1/auth/api-keys",
        headers={"X-Artana-Key": api_key},
        json={"name": "Second"},
    )
    resp = client.get("/v1/auth/api-keys", headers={"X-Artana-Key": api_key})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    for key in body["keys"]:
        assert "api_key" not in key
        assert len(key["key_prefix"]) > 0
        assert key["status"] in ("active", "revoked")


def test_revoke_api_key(db_session: Session, monkeypatch) -> None:
    client, api_key, _ = _bootstrap_and_get_client(db_session, monkeypatch)
    # Create a key to revoke
    resp = client.post(
        "/v1/auth/api-keys",
        headers={"X-Artana-Key": api_key},
        json={"name": "ToRevoke"},
    )
    key_id = resp.json()["api_key"]["id"]
    resp = client.delete(
        f"/v1/auth/api-keys/{key_id}",
        headers={"X-Artana-Key": api_key},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"
    assert resp.json()["revoked_at"] is not None


def test_revoke_nonexistent_key_returns_404(db_session: Session, monkeypatch) -> None:
    client, api_key, _ = _bootstrap_and_get_client(db_session, monkeypatch)
    resp = client.delete(
        "/v1/auth/api-keys/00000000-0000-0000-0000-000000000000",
        headers={"X-Artana-Key": api_key},
    )
    assert resp.status_code == 404


def test_rotate_api_key(db_session: Session, monkeypatch) -> None:
    client, api_key, _ = _bootstrap_and_get_client(db_session, monkeypatch)
    # Create a key to rotate
    resp = client.post(
        "/v1/auth/api-keys",
        headers={"X-Artana-Key": api_key},
        json={"name": "ToRotate"},
    )
    key_id = resp.json()["api_key"]["id"]
    resp = client.post(
        f"/v1/auth/api-keys/{key_id}/rotate",
        headers={"X-Artana-Key": api_key},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["revoked_key_id"] == key_id
    assert body["new_key"]["api_key"].startswith("art_sk_")


def test_rotate_api_key_rolls_back_when_key_issue_fails(
    db_session: Session,
    monkeypatch,
) -> None:
    client, api_key, _ = _bootstrap_and_get_client(db_session, monkeypatch)
    resp = client.post(
        "/v1/auth/api-keys",
        headers={"X-Artana-Key": api_key},
        json={"name": "ToRotate"},
    )
    key_id = resp.json()["api_key"]["id"]
    rotated_raw_key = resp.json()["api_key"]["api_key"]
    monkeypatch.setattr(
        "artana_evidence_api.api_keys.generate_api_key",
        lambda: rotated_raw_key,
    )

    with TestClient(client.app, raise_server_exceptions=False) as failure_client:
        failure_response = failure_client.post(
            f"/v1/auth/api-keys/{key_id}/rotate",
            headers={"X-Artana-Key": api_key},
        )

    assert failure_response.status_code == 500
    key_records = (
        db_session.execute(
            select(HarnessApiKeyModel).order_by(HarnessApiKeyModel.created_at.asc()),
        )
        .scalars()
        .all()
    )
    assert len(key_records) == 2
    assert all(record.status == "active" for record in key_records)
    assert all(record.revoked_at is None for record in key_records)
    assert (
        client.get("/v1/auth/me", headers={"X-Artana-Key": rotated_raw_key}).status_code
        == 200
    )


def test_rotate_already_revoked_key_returns_404(
    db_session: Session,
    monkeypatch,
) -> None:
    client, api_key, _ = _bootstrap_and_get_client(db_session, monkeypatch)
    resp = client.post(
        "/v1/auth/api-keys",
        headers={"X-Artana-Key": api_key},
        json={"name": "WillRevoke"},
    )
    key_id = resp.json()["api_key"]["id"]
    client.delete(f"/v1/auth/api-keys/{key_id}", headers={"X-Artana-Key": api_key})
    resp = client.post(
        f"/v1/auth/api-keys/{key_id}/rotate",
        headers={"X-Artana-Key": api_key},
    )
    assert resp.status_code == 404


def test_revoked_api_key_cannot_authenticate(
    db_session: Session,
    monkeypatch,
) -> None:
    client, api_key, _ = _bootstrap_and_get_client(db_session, monkeypatch)
    # Create a second key, revoke it, then try to auth with it
    resp = client.post(
        "/v1/auth/api-keys",
        headers={"X-Artana-Key": api_key},
        json={"name": "Expendable"},
    )
    expendable_key = resp.json()["api_key"]["api_key"]
    key_id = resp.json()["api_key"]["id"]
    # Verify it works
    assert (
        client.get("/v1/auth/me", headers={"X-Artana-Key": expendable_key}).status_code
        == 200
    )
    # Revoke
    client.delete(f"/v1/auth/api-keys/{key_id}", headers={"X-Artana-Key": api_key})
    # Should fail now
    assert (
        client.get("/v1/auth/me", headers={"X-Artana-Key": expendable_key}).status_code
        == 401
    )


def test_bootstrap_route_openapi_marks_bootstrap_key_as_security_requirement() -> None:
    app = create_app()

    operation = app.openapi()["paths"]["/v1/auth/bootstrap"]["post"]

    assert operation["security"] == [{"BootstrapAPIKeyHeader": []}]
    assert all(
        parameter["name"] != BOOTSTRAP_KEY_HEADER
        for parameter in operation.get("parameters", [])
    )
    assert app.openapi()["components"]["securitySchemes"]["BootstrapAPIKeyHeader"] == {
        "type": "apiKey",
        "in": "header",
        "name": BOOTSTRAP_KEY_HEADER,
        "description": "Bootstrap API key required to create the initial self-hosted user.",
    }
