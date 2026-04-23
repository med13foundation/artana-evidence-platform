"""Local SQL-backed implementation of the evidence API identity boundary."""

from __future__ import annotations

from uuid import UUID, uuid4

from artana_evidence_api.api_keys import (
    IssuedApiKey,
    issue_api_key,
    list_api_keys_for_user,
    resolve_user_from_api_key,
    revoke_api_key,
    rotate_api_key,
)
from artana_evidence_api.identity.contracts import (
    IdentityApiKeyRecord,
    IdentityIssuedApiKey,
    IdentitySpaceAccessDecision,
    IdentityUserConflictError,
    IdentityUserNotFoundError,
    IdentityUserRecord,
    role_at_least,
)
from artana_evidence_api.models.api_key import HarnessApiKeyModel
from artana_evidence_api.models.user import HarnessUserModel
from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceRecord,
    HarnessResearchSpaceStore,
    HarnessSpaceMemberRecord,
    HarnessUserIdentityConflictError,
)
from artana_evidence_api.sqlalchemy_stores import SqlAlchemyHarnessResearchSpaceStore
from artana_evidence_api.types.common import ResearchSpaceSettings
from sqlalchemy import or_, select
from sqlalchemy.orm import Session


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if normalized == "":
        msg = "Email is required"
        raise ValueError(msg)
    return normalized


def _normalize_username(email: str, username: str | None) -> str:
    candidate = username.strip() if isinstance(username, str) else ""
    if candidate != "":
        return candidate[:50]
    return email.split("@", maxsplit=1)[0][:50] or "artana-user"


def _normalize_full_name(email: str, full_name: str | None) -> str:
    candidate = full_name.strip() if isinstance(full_name, str) else ""
    if candidate != "":
        return candidate[:100]
    return email[:100]


def _user_record_from_model(model: HarnessUserModel) -> IdentityUserRecord:
    return IdentityUserRecord(
        id=_as_uuid(model.id),
        email=model.email,
        username=model.username,
        full_name=model.full_name,
        role=model.role,
        status=model.status,
    )


def _api_key_record_from_model(model: HarnessApiKeyModel) -> IdentityApiKeyRecord:
    return IdentityApiKeyRecord(
        id=_as_uuid(model.id),
        name=model.name,
        key_prefix=model.key_prefix,
        status=model.status,
        created_at=model.created_at,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
        last_used_at=model.last_used_at,
    )


def _issued_api_key_from_result(result: IssuedApiKey) -> IdentityIssuedApiKey:
    return IdentityIssuedApiKey(
        raw_key=result.raw_key,
        record=_api_key_record_from_model(result.model),
    )


class LocalIdentityGateway:
    """Local identity/tenancy gateway backed by existing service tables."""

    def __init__(
        self,
        *,
        session: Session | None = None,
        research_space_store: HarnessResearchSpaceStore | None = None,
    ) -> None:
        self._session = session
        self._research_space_store = research_space_store

    def _require_session(self) -> Session:
        if self._session is None:
            msg = "User and API-key operations require a database session"
            raise RuntimeError(msg)
        return self._session

    def _require_space_store(self) -> HarnessResearchSpaceStore:
        if self._research_space_store is None:
            msg = "Research-space operations require a research-space store"
            raise RuntimeError(msg)
        return self._research_space_store

    def get_user(self, user_id: UUID | str) -> IdentityUserRecord | None:
        """Return one local user by id."""
        model = self._require_session().get(HarnessUserModel, _as_uuid(user_id))
        return _user_record_from_model(model) if model is not None else None

    def canonicalize_user_claims(
        self,
        user: IdentityUserRecord,
    ) -> IdentityUserRecord:
        """Reuse an existing local identity when claims describe one."""
        session = self._require_session()
        existing_user = session.get(HarnessUserModel, user.id)
        if existing_user is not None:
            return user

        normalized_email = _normalize_email(user.email)
        normalized_username = user.username.strip()
        identity_match = (
            session.execute(
                select(HarnessUserModel).where(
                    or_(
                        HarnessUserModel.email == normalized_email,
                        HarnessUserModel.username == normalized_username,
                    ),
                ),
            )
            .scalars()
            .first()
        )
        if identity_match is None:
            return user
        if identity_match.email != normalized_email:
            msg = "Username is already in use"
            raise IdentityUserConflictError(msg)
        return IdentityUserRecord(
            id=_as_uuid(identity_match.id),
            email=identity_match.email,
            username=identity_match.username,
            full_name=identity_match.full_name,
            role=user.role,
            status=user.status,
        )

    def create_tester_user(
        self,
        *,
        email: str,
        username: str | None,
        full_name: str | None,
        role: str,
        user_id: UUID | str | None = None,
    ) -> IdentityUserRecord:
        """Create or reuse one local tester user."""
        normalized_email = _normalize_email(email)
        normalized_username = _normalize_username(normalized_email, username)
        normalized_full_name = _normalize_full_name(normalized_email, full_name)

        if user_id is not None:
            existing_by_id = self._require_session().get(
                HarnessUserModel,
                _as_uuid(user_id),
            )
            if existing_by_id is not None:
                return _user_record_from_model(existing_by_id)

        identity_match = (
            self._require_session().execute(
                select(HarnessUserModel).where(
                    or_(
                        HarnessUserModel.email == normalized_email,
                        HarnessUserModel.username == normalized_username,
                    ),
                ),
            )
            .scalars()
            .first()
        )
        if identity_match is not None:
            if identity_match.email != normalized_email:
                msg = "Username is already in use"
                raise IdentityUserConflictError(msg)
            return _user_record_from_model(identity_match)

        model = HarnessUserModel(
            id=_as_uuid(user_id) if user_id is not None else uuid4(),
            email=normalized_email,
            username=normalized_username,
            full_name=normalized_full_name,
            hashed_password="external-auth-not-applicable",
            role=role.strip().lower() or "researcher",
            status="active",
            email_verified=True,
            login_attempts=0,
        )
        session = self._require_session()
        session.add(model)
        session.commit()
        session.refresh(model)
        return _user_record_from_model(model)

    def bootstrap_recovery_user(self) -> IdentityUserRecord | None:
        """Return the lone user eligible for bootstrap key recovery, if any."""
        existing_users = (
            self._require_session().execute(
                select(HarnessUserModel).limit(2),
            )
            .scalars()
            .all()
        )
        if len(existing_users) != 1:
            return None
        existing_key_id = self._require_session().execute(
            select(HarnessApiKeyModel.id).limit(1),
        ).scalar_one_or_none()
        if existing_key_id is not None:
            return None
        return _user_record_from_model(existing_users[0])

    def bootstrap_already_completed(self) -> bool:
        """Return whether first-user bootstrap should remain locked."""
        if self.bootstrap_recovery_user() is not None:
            return False
        existing_user_id = self._require_session().execute(
            select(HarnessUserModel.id).limit(1),
        ).scalar_one_or_none()
        return existing_user_id is not None

    def resolve_api_key(self, raw_key: str) -> IdentityUserRecord | None:
        """Resolve one raw API key to its user."""
        model = resolve_user_from_api_key(self._require_session(), raw_key=raw_key)
        return _user_record_from_model(model) if model is not None else None

    def issue_api_key(
        self,
        *,
        user_id: UUID | str,
        name: str,
        description: str = "",
    ) -> IdentityIssuedApiKey:
        """Issue one local API key."""
        return _issued_api_key_from_result(
            issue_api_key(
                self._require_session(),
                user_id=user_id,
                name=name,
                description=description,
            ),
        )

    def list_api_keys(self, *, user_id: UUID | str) -> list[IdentityApiKeyRecord]:
        """List all API keys for one user."""
        return [
            _api_key_record_from_model(model)
            for model in list_api_keys_for_user(
                self._require_session(),
                user_id=user_id,
            )
        ]

    def revoke_api_key(
        self,
        *,
        key_id: UUID | str,
        user_id: UUID | str,
    ) -> IdentityApiKeyRecord | None:
        """Revoke one API key."""
        model = revoke_api_key(
            self._require_session(),
            key_id=key_id,
            user_id=user_id,
        )
        return _api_key_record_from_model(model) if model is not None else None

    def rotate_api_key(
        self,
        *,
        key_id: UUID | str,
        user_id: UUID | str,
    ) -> IdentityIssuedApiKey | None:
        """Rotate one API key."""
        result = rotate_api_key(
            self._require_session(),
            key_id=key_id,
            user_id=user_id,
        )
        return _issued_api_key_from_result(result) if result is not None else None

    def list_spaces(
        self,
        *,
        user_id: UUID | str,
        is_admin: bool,
    ) -> list[HarnessResearchSpaceRecord]:
        """List spaces visible to one user."""
        return self._require_space_store().list_spaces(
            user_id=user_id,
            is_admin=is_admin,
        )

    def get_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord | None:
        """Return one accessible space."""
        return self._require_space_store().get_space(
            space_id=space_id,
            user_id=user_id,
            is_admin=is_admin,
        )

    def create_space(
        self,
        *,
        owner: IdentityUserRecord,
        name: str,
        description: str | None,
        settings: ResearchSpaceSettings | None = None,
    ) -> HarnessResearchSpaceRecord:
        """Create one space after explicitly ensuring the local owner."""
        store = self._require_space_store()
        local_owner = (
            self.create_tester_user(
                user_id=owner.id,
                email=owner.email,
                username=owner.username,
                full_name=owner.full_name,
                role=owner.role,
            )
            if isinstance(store, SqlAlchemyHarnessResearchSpaceStore)
            else owner
        )
        try:
            return store.create_space(
                owner_id=local_owner.id,
                owner_email=local_owner.email,
                owner_username=local_owner.username,
                owner_full_name=local_owner.full_name,
                owner_role=local_owner.role,
                owner_status=local_owner.status,
                name=name,
                description=description,
                settings=settings,
            )
        except HarnessUserIdentityConflictError as exc:
            raise IdentityUserConflictError(str(exc)) from exc

    def get_default_space(
        self,
        *,
        user_id: UUID | str,
    ) -> HarnessResearchSpaceRecord | None:
        """Return a user's default space, if present."""
        return self._require_space_store().get_default_space(user_id=user_id)

    def ensure_default_space(
        self,
        *,
        owner: IdentityUserRecord,
    ) -> HarnessResearchSpaceRecord:
        """Return or create a default space after explicitly ensuring owner."""
        store = self._require_space_store()
        local_owner = (
            self.create_tester_user(
                user_id=owner.id,
                email=owner.email,
                username=owner.username,
                full_name=owner.full_name,
                role=owner.role,
            )
            if isinstance(store, SqlAlchemyHarnessResearchSpaceStore)
            else owner
        )
        try:
            return store.ensure_default_space(
                owner_id=local_owner.id,
                owner_email=local_owner.email,
                owner_username=local_owner.username,
                owner_full_name=local_owner.full_name,
                owner_role=local_owner.role,
                owner_status=local_owner.status,
            )
        except HarnessUserIdentityConflictError as exc:
            raise IdentityUserConflictError(str(exc)) from exc

    def update_space_settings(
        self,
        *,
        space_id: UUID | str,
        settings: ResearchSpaceSettings,
    ) -> HarnessResearchSpaceRecord:
        """Update owner-managed space settings."""
        return self._require_space_store().update_space_settings(
            space_id=space_id,
            settings=settings,
        )

    def prepare_space_archive(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Validate that a user can archive one space."""
        return self._require_space_store().prepare_space_archive(
            space_id=space_id,
            user_id=user_id,
            is_admin=is_admin,
        )

    def archive_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Archive one space."""
        return self._require_space_store().archive_space(
            space_id=space_id,
            user_id=user_id,
            is_admin=is_admin,
        )

    def list_members(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessSpaceMemberRecord]:
        """List active members for a space."""
        return self._require_space_store().list_members(space_id=space_id)

    def add_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        role: str,
        invited_by: UUID | str | None = None,
    ) -> HarnessSpaceMemberRecord:
        """Add an existing user to a space."""
        store = self._require_space_store()
        if (
            isinstance(store, SqlAlchemyHarnessResearchSpaceStore)
            and self.get_user(user_id) is None
        ):
            msg = "User must exist before they can be added to a space"
            raise IdentityUserNotFoundError(msg)
        return store.add_member(
            space_id=space_id,
            user_id=user_id,
            role=role,
            invited_by=invited_by,
        )

    def remove_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
    ) -> HarnessSpaceMemberRecord | None:
        """Remove one user from a space."""
        return self._require_space_store().remove_member(
            space_id=space_id,
            user_id=user_id,
        )

    def check_space_access(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_platform_admin: bool,
        is_service_user: bool,
        minimum_role: str = "viewer",
    ) -> IdentitySpaceAccessDecision:
        """Return one local space-access decision."""
        if is_service_user:
            return IdentitySpaceAccessDecision(
                allowed=True,
                space=None,
                actual_role="service",
                minimum_role=minimum_role,
            )
        record = self.get_space(
            space_id=space_id,
            user_id=user_id,
            is_admin=is_platform_admin,
        )
        if is_platform_admin:
            if record is None:
                return IdentitySpaceAccessDecision(
                    allowed=False,
                    space=None,
                    actual_role=None,
                    minimum_role=minimum_role,
                    reason=f"Space {space_id} was not found",
                )
            return IdentitySpaceAccessDecision(
                allowed=True,
                space=record,
                actual_role="admin",
                minimum_role=minimum_role,
            )
        if record is None:
            return IdentitySpaceAccessDecision(
                allowed=False,
                space=None,
                actual_role=None,
                minimum_role=minimum_role,
                reason=f"User {user_id} has no membership in space {space_id}",
            )
        if not role_at_least(record.role, minimum_role):
            return IdentitySpaceAccessDecision(
                allowed=False,
                space=record,
                actual_role=record.role,
                minimum_role=minimum_role,
                reason=(
                    f"User {user_id} has role '{record.role}' in space "
                    f"{space_id} but '{minimum_role}' or higher is required"
                ),
            )
        return IdentitySpaceAccessDecision(
            allowed=True,
            space=record,
            actual_role=record.role,
            minimum_role=minimum_role,
        )


__all__ = ["LocalIdentityGateway"]
