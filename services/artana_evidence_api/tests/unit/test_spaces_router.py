"""Unit tests for harness research-space endpoints."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final
from uuid import UUID

import jwt
from artana_evidence_api.app import create_app
from artana_evidence_api.chat_sessions import HarnessChatSessionStore
from artana_evidence_api.dependencies import (
    get_chat_session_store,
    get_document_store,
    get_graph_snapshot_store,
    get_proposal_store,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
from artana_evidence_api.models.research_space import ResearchSpaceModel
from artana_evidence_api.models.user import HarnessUserModel
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceRecord,
    HarnessResearchSpaceStore,
)
from artana_evidence_api.research_state import HarnessResearchStateStore
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.sqlalchemy_stores import SqlAlchemyHarnessResearchSpaceStore
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

_TEST_USER_ID: Final[str] = "11111111-1111-1111-1111-111111111111"
_TEST_USER_EMAIL: Final[str] = "graph-harness-test@example.com"
_AUTH_TEST_SECRET: Final[str] = os.environ["AUTH_JWT_SECRET"]


@dataclass
class _HarnessSpaceTestStores:
    research_space_store: HarnessResearchSpaceStore
    run_registry: HarnessRunRegistry
    chat_session_store: HarnessChatSessionStore
    document_store: HarnessDocumentStore
    graph_snapshot_store: HarnessGraphSnapshotStore
    proposal_store: HarnessProposalStore
    research_state_store: HarnessResearchStateStore
    schedule_store: HarnessScheduleStore


class _RecordingSpaceLifecycleSync:
    def __init__(self) -> None:
        self.spaces: list[HarnessResearchSpaceRecord] = []

    def sync_space(self, space: HarnessResearchSpaceRecord) -> None:
        self.spaces.append(space)


def _auth_headers(*, role: str = "researcher") -> dict[str, str]:
    return {
        "X-TEST-USER-ID": _TEST_USER_ID,
        "X-TEST-USER-EMAIL": _TEST_USER_EMAIL,
        "X-TEST-USER-ROLE": role,
    }


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


def _build_client() -> tuple[TestClient, _HarnessSpaceTestStores]:
    app = create_app()
    stores = _HarnessSpaceTestStores(
        research_space_store=HarnessResearchSpaceStore(),
        run_registry=HarnessRunRegistry(),
        chat_session_store=HarnessChatSessionStore(),
        document_store=HarnessDocumentStore(),
        graph_snapshot_store=HarnessGraphSnapshotStore(),
        proposal_store=HarnessProposalStore(),
        research_state_store=HarnessResearchStateStore(),
        schedule_store=HarnessScheduleStore(),
    )
    app.dependency_overrides[get_research_space_store] = (
        lambda: stores.research_space_store
    )
    app.dependency_overrides[get_run_registry] = lambda: stores.run_registry
    app.dependency_overrides[get_chat_session_store] = lambda: stores.chat_session_store
    app.dependency_overrides[get_document_store] = lambda: stores.document_store
    app.dependency_overrides[get_graph_snapshot_store] = (
        lambda: stores.graph_snapshot_store
    )
    app.dependency_overrides[get_proposal_store] = lambda: stores.proposal_store
    app.dependency_overrides[get_research_state_store] = (
        lambda: stores.research_state_store
    )
    app.dependency_overrides[get_schedule_store] = lambda: stores.schedule_store
    return TestClient(app), stores


def test_create_space_returns_created_space() -> None:
    """Researchers can create one new research space."""
    client, _ = _build_client()

    response = client.post(
        "/v1/spaces",
        headers=_auth_headers(role="researcher"),
        json={
            "name": "Rare Disease Triage",
            "description": "Track graph-harness work for MED13 rare disease review.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Rare Disease Triage"
    assert payload["slug"] == "rare-disease-triage"
    assert payload["role"] == "owner"
    assert payload["status"] == "active"
    assert payload["is_default"] is False


def test_create_space_persists_source_preferences() -> None:
    """Source toggle preferences should be stored on the harness space record."""
    client, stores = _build_client()
    sources = {
        "pubmed": False,
        "marrvel": True,
        "clinvar": False,
        "mondo": False,
        "pdf": False,
        "text": False,
        "drugbank": False,
        "alphafold": False,
        "uniprot": False,
        "hgnc": True,
        "clinical_trials": False,
        "mgi": False,
        "zfin": False,
    }

    response = client.post(
        "/v1/spaces",
        headers=_auth_headers(role="researcher"),
        json={
            "name": "MARRVEL Only",
            "description": "Persist source preferences for bootstrap reuse.",
            "sources": sources,
        },
    )

    assert response.status_code == 201
    records = stores.research_space_store.list_spaces(
        user_id=_TEST_USER_ID,
        is_admin=False,
    )
    assert len(records) == 1
    assert records[0].settings == {"sources": sources}
    assert response.json()["settings"] == {"sources": sources}


def test_update_space_settings_clears_rollback_for_default_guarded_mode() -> None:
    """Owners can return a space to the default guarded runtime."""
    client, stores = _build_client()
    record = stores.research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Owned Space",
        description="Visible to the authenticated user.",
        settings={
            "sources": {"pubmed": True},
            "research_orchestration_mode": "deterministic",
        },
    )

    response = client.patch(
        f"/v1/spaces/{record.id}/settings",
        headers=_auth_headers(role="researcher"),
        json={"research_orchestration_mode": "full_ai_guarded"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["settings"]["sources"] == {"pubmed": True}
    assert "research_orchestration_mode" not in payload["settings"]
    records = stores.research_space_store.list_spaces(
        user_id=_TEST_USER_ID,
        is_admin=False,
    )
    assert records[0].settings == {"sources": {"pubmed": True}}


def test_update_space_settings_sets_guarded_rollout_profile() -> None:
    """Owners can select the guarded authority profile for a space."""
    client, stores = _build_client()
    record = stores.research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Owned Space",
        description="Visible to the authenticated user.",
        settings={"sources": {"pubmed": True}},
    )

    response = client.patch(
        f"/v1/spaces/{record.id}/settings",
        headers=_auth_headers(role="researcher"),
        json={
            "research_orchestration_mode": "full_ai_guarded",
            "full_ai_guarded_rollout_profile": "guarded_source_chase",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "research_orchestration_mode" not in payload["settings"]
    assert payload["settings"]["full_ai_guarded_rollout_profile"] == (
        "guarded_source_chase"
    )


def test_update_space_settings_deterministic_sets_explicit_rollback_mode() -> None:
    """The deterministic runtime is now the explicit rollback mode."""
    client, stores = _build_client()
    record = stores.research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Owned Space",
        description="Visible to the authenticated user.",
        settings={
            "sources": {"pubmed": True},
            "research_orchestration_mode": "full_ai_shadow",
            "full_ai_guarded_rollout_profile": "guarded_source_chase",
        },
    )

    response = client.patch(
        f"/v1/spaces/{record.id}/settings",
        headers=_auth_headers(role="researcher"),
        json={"research_orchestration_mode": "deterministic"},
    )

    assert response.status_code == 200
    assert response.json()["settings"] == {
        "sources": {"pubmed": True},
        "research_orchestration_mode": "deterministic",
    }


def test_update_space_settings_rejects_invalid_guarded_rollout_profile() -> None:
    """Unknown guarded profiles should fail validation before settings mutate."""
    client, stores = _build_client()
    record = stores.research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Owned Space",
        description="Visible to the authenticated user.",
    )

    response = client.patch(
        f"/v1/spaces/{record.id}/settings",
        headers=_auth_headers(role="researcher"),
        json={
            "research_orchestration_mode": "full_ai_guarded",
            "full_ai_guarded_rollout_profile": "guarded_everything",
        },
    )

    assert response.status_code == 422


def test_update_space_settings_rejects_non_owners() -> None:
    """Non-owner researchers cannot change orchestration mode."""
    client, stores = _build_client()
    record = stores.research_space_store.create_space(
        owner_id="22222222-2222-2222-2222-222222222222",
        name="Other Space",
        description="Owned by another researcher.",
    )

    response = client.patch(
        f"/v1/spaces/{record.id}/settings",
        headers=_auth_headers(role="researcher"),
        json={"research_orchestration_mode": "full_ai_shadow"},
    )

    assert response.status_code == 404


def test_ensure_default_space_returns_same_personal_space_across_calls() -> None:
    """The personal default space should be created once and then reused."""
    client, stores = _build_client()

    first_response = client.put(
        "/v1/spaces/default",
        headers=_auth_headers(role="researcher"),
    )
    second_response = client.put(
        "/v1/spaces/default",
        headers=_auth_headers(role="researcher"),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_payload = first_response.json()
    second_payload = second_response.json()
    assert first_payload["id"] == second_payload["id"]
    assert first_payload["is_default"] is True
    assert first_payload["role"] == "owner"
    records = stores.research_space_store.list_spaces(
        user_id=_TEST_USER_ID,
        is_admin=False,
    )
    assert len(records) == 1
    assert records[0].is_default is True


def test_list_spaces_returns_only_accessible_spaces_for_non_admins() -> None:
    """Non-admin callers only see spaces they own."""
    client, stores = _build_client()
    stores.research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Owned Space",
        description="Visible to the authenticated user.",
    )
    stores.research_space_store.create_space(
        owner_id="22222222-2222-2222-2222-222222222222",
        name="Other Space",
        description="Owned by another researcher.",
    )

    response = client.get("/v1/spaces", headers=_auth_headers(role="researcher"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert [space["name"] for space in payload["spaces"]] == ["Owned Space"]


def test_delete_space_archives_owned_space_and_returns_confirmation() -> None:
    """Owners can archive an empty space and receive a confirmation payload."""
    client, stores = _build_client()
    record = stores.research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Owned Space",
        description="Visible to the authenticated user.",
    )

    response = client.delete(
        f"/v1/spaces/{record.id}",
        headers=_auth_headers(role="researcher"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == record.id
    assert payload["status"] == "archived"
    assert payload["archived"] is True
    assert payload["confirmed"] is False
    assert payload["dependency_counts"]["total_records"] == 0
    remaining_records = stores.research_space_store.list_spaces(
        user_id=_TEST_USER_ID,
        is_admin=False,
    )
    assert remaining_records == []


def test_delete_space_rejects_non_owners() -> None:
    """Non-admin callers cannot delete spaces they do not own."""
    client, stores = _build_client()
    record = stores.research_space_store.create_space(
        owner_id="22222222-2222-2222-2222-222222222222",
        name="Other Space",
        description="Owned by another researcher.",
    )

    response = client.delete(
        f"/v1/spaces/{record.id}",
        headers=_auth_headers(role="researcher"),
    )

    assert response.status_code == 403
    assert (
        response.json()["detail"]
        == "Only the space owner or an admin can delete this space"
    )


def test_delete_space_requires_confirmation_for_non_empty_spaces() -> None:
    """Non-empty spaces should return a conflict until deletion is confirmed."""
    client, stores = _build_client()
    record = stores.research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Space With Data",
        description="Contains tracked state.",
    )
    stores.research_state_store.upsert_state(
        space_id=record.id,
        objective="Preserve this state",
    )

    response = client.delete(
        f"/v1/spaces/{record.id}",
        headers=_auth_headers(role="researcher"),
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    # Error detail is now normalised to a string (issue #164).
    assert isinstance(detail, str)
    assert "confirm=true" in detail
    visible_records = stores.research_space_store.list_spaces(
        user_id=_TEST_USER_ID,
        is_admin=False,
    )
    assert [space.id for space in visible_records] == [record.id]


def test_delete_space_archives_non_empty_space_when_confirmed() -> None:
    """Confirmed deletion should archive the space and preserve tracked records."""
    client, stores = _build_client()
    record = stores.research_space_store.create_space(
        owner_id=_TEST_USER_ID,
        name="Space With Data",
        description="Contains tracked state.",
    )
    stores.research_state_store.upsert_state(
        space_id=record.id,
        objective="Preserve this state",
    )
    stores.chat_session_store.create_session(
        space_id=record.id,
        title="Validation Chat",
        created_by=_TEST_USER_ID,
    )

    response = client.delete(
        f"/v1/spaces/{record.id}?confirm=true",
        headers=_auth_headers(role="researcher"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "archived"
    assert payload["confirmed"] is True
    assert payload["dependency_counts"]["research_state_records"] == 1
    assert payload["dependency_counts"]["chat_sessions"] == 1
    assert payload["dependency_counts"]["total_records"] == 2
    assert stores.research_state_store.get_state(space_id=record.id) is not None
    visible_records = stores.research_space_store.list_spaces(
        user_id=_TEST_USER_ID,
        is_admin=False,
    )
    assert visible_records == []


def test_create_space_bootstraps_missing_authenticated_user_in_database(
    db_session: Session,
) -> None:
    """DB-backed space creation should create the authenticated owner record first."""
    app = create_app()
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/spaces",
            headers=_auth_headers(role="researcher"),
            json={
                "name": "MED13",
                "description": "Bootstraps a missing authenticated owner.",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    assert payload["slug"] == "med13"
    created_user = db_session.get(HarnessUserModel, UUID(_TEST_USER_ID))
    assert created_user is not None
    assert created_user.email == _TEST_USER_EMAIL
    assert created_user.role == "researcher"
    assert created_user.status == "active"


def test_create_space_syncs_graph_tenant_snapshot_on_supported_path(
    db_session: Session,
) -> None:
    """The supported create-space route should trigger graph tenant sync."""
    app = create_app()
    sync = _RecordingSpaceLifecycleSync()
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(
            db_session,
            space_lifecycle_sync=sync,
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/spaces",
            headers=_auth_headers(role="researcher"),
            json={
                "name": "COVID Lifecycle",
                "description": "Verify graph tenant sync on space creation.",
            },
        )

    assert response.status_code == 201
    payload = response.json()
    created_space = db_session.get(ResearchSpaceModel, UUID(payload["id"]))
    assert created_space is not None
    assert len(sync.spaces) == 1
    assert sync.spaces[0].id == created_space.id
    assert sync.spaces[0].slug == created_space.slug


def test_ensure_default_space_supports_distinct_jwt_users_with_shared_prefix(
    db_session: Session,
) -> None:
    """Default spaces should not collide for different JWT users sharing a prefix."""
    app = create_app()
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )
    first_user_id = "00000000-0000-4000-a000-000000e2e201"
    second_user_id = "00000000-0000-4000-a000-000000e2e202"

    with TestClient(app) as client:
        first_response = client.put(
            "/v1/spaces/default",
            headers=_jwt_auth_headers(
                user_id=first_user_id,
                email="issue201-first@example.com",
                role="admin",
            ),
        )
        second_response = client.put(
            "/v1/spaces/default",
            headers=_jwt_auth_headers(
                user_id=second_user_id,
                email="issue201-second@example.com",
                role="admin",
            ),
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_payload = first_response.json()
    second_payload = second_response.json()
    assert first_payload["id"] != second_payload["id"]
    assert first_payload["slug"] == f"personal-{UUID(first_user_id).hex}"
    assert second_payload["slug"] == f"personal-{UUID(second_user_id).hex}"
    assert db_session.get(HarnessUserModel, UUID(first_user_id)) is not None
    assert db_session.get(HarnessUserModel, UUID(second_user_id)) is not None


def test_create_space_reuses_existing_shared_user_when_jwt_sub_differs(
    db_session: Session,
) -> None:
    """Space creation should reuse one existing shared user matched by email."""
    app = create_app()
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )
    existing_user_id = UUID("00000000-0000-4000-a000-000000e20701")
    jwt_user_id = "00000000-0000-4000-a000-000000e20799"
    db_session.add(
        HarnessUserModel(
            id=existing_user_id,
            email="issue207@example.com",
            username="issue207",
            full_name="Issue 207 Existing",
            hashed_password="external-auth-not-applicable",
            role="researcher",
            status="active",
            email_verified=True,
            login_attempts=0,
        ),
    )
    db_session.commit()

    with TestClient(app) as client:
        response = client.post(
            "/v1/spaces",
            headers=_jwt_auth_headers(
                user_id=jwt_user_id,
                email="issue207@example.com",
                role="researcher",
            ),
            json={
                "name": "Issue 207 Shared",
                "description": "Reuse the canonical shared user id.",
            },
        )

    assert response.status_code == 201
    created_space = (
        db_session.execute(
            select(ResearchSpaceModel).where(
                ResearchSpaceModel.slug == "issue-207-shared",
            ),
        )
        .scalars()
        .one()
    )
    assert created_space.owner_id == existing_user_id
    matched_users = (
        db_session.execute(
            select(HarnessUserModel).where(
                HarnessUserModel.email == "issue207@example.com",
            ),
        )
        .scalars()
        .all()
    )
    assert len(matched_users) == 1
    assert db_session.get(HarnessUserModel, UUID(jwt_user_id)) is None


def test_ensure_default_space_reuses_existing_default_when_jwt_sub_differs(
    db_session: Session,
) -> None:
    """Default-space resolution should reuse the canonical shared user and space."""
    app = create_app()
    store = SqlAlchemyHarnessResearchSpaceStore(db_session)
    app.dependency_overrides[get_research_space_store] = lambda: store
    existing_user_id = UUID("00000000-0000-4000-a000-000000e20702")
    jwt_user_id = "00000000-0000-4000-a000-000000e20798"
    db_session.add(
        HarnessUserModel(
            id=existing_user_id,
            email="issue207-default@example.com",
            username="issue207-default",
            full_name="Issue 207 Default",
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
        owner_email="issue207-default@example.com",
        owner_username="issue207-default",
        owner_role="researcher",
    )

    with TestClient(app) as client:
        response = client.put(
            "/v1/spaces/default",
            headers=_jwt_auth_headers(
                user_id=jwt_user_id,
                email="issue207-default@example.com",
                role="researcher",
            ),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == existing_default.id
    assert payload["slug"] == existing_default.slug
    matched_users = (
        db_session.execute(
            select(HarnessUserModel).where(
                HarnessUserModel.email == "issue207-default@example.com",
            ),
        )
        .scalars()
        .all()
    )
    assert len(matched_users) == 1
    owner_spaces = (
        db_session.execute(
            select(ResearchSpaceModel).where(
                ResearchSpaceModel.owner_id == existing_user_id,
            ),
        )
        .scalars()
        .all()
    )
    assert len(owner_spaces) == 1
    assert db_session.get(HarnessUserModel, UUID(jwt_user_id)) is None


def test_create_space_returns_409_for_username_conflict_in_shared_users(
    db_session: Session,
) -> None:
    """Username collisions with a different email should return 409, not 500."""
    app = create_app()
    app.dependency_overrides[get_research_space_store] = (
        lambda: SqlAlchemyHarnessResearchSpaceStore(db_session)
    )
    db_session.add(
        HarnessUserModel(
            id=UUID("00000000-0000-4000-a000-000000e20703"),
            email="issue207-conflict@example.com",
            username="issue207-conflict",
            full_name="Issue 207 Conflict",
            hashed_password="external-auth-not-applicable",
            role="researcher",
            status="active",
            email_verified=True,
            login_attempts=0,
        ),
    )
    db_session.commit()

    with TestClient(app) as client:
        response = client.post(
            "/v1/spaces",
            headers=_jwt_auth_headers(
                user_id="00000000-0000-4000-a000-000000e20797",
                email="issue207-conflict@different.example.com",
                role="researcher",
            ),
            json={"name": "Issue 207 Conflict"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Username is already in use"
