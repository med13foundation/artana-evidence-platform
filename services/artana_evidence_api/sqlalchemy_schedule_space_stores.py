"""SQLAlchemy schedule and research-space stores."""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from uuid import UUID

from artana_evidence_api.sqlalchemy_stores import (
    PERSONAL_DEFAULT_SETTING_KEY,
    PERSONAL_DEFAULT_SPACE_DESCRIPTION,
    PERSONAL_DEFAULT_SPACE_NAME,
    HarnessResearchSpaceRecord,
    HarnessResearchSpaceStore,
    HarnessScheduleModel,
    HarnessScheduleRecord,
    HarnessScheduleStore,
    HarnessSpaceMemberRecord,
    HarnessUserIdentityConflictError,
    HarnessUserModel,
    MembershipRoleEnum,
    ResearchSpaceMembershipModel,
    ResearchSpaceModel,
    SpaceLifecycleSyncPort,
    SpaceStatusEnum,
    _as_uuid,
    _is_personal_default_space,
    _normalize_assignable_member_role,
    _normalize_owner_text,
    _normalized_utc_datetime,
    _personal_default_slug,
    _research_space_record_from_model,
    _result_rowcount,
    _schedule_record_from_model,
    _SessionBackedStore,
    build_unique_space_slug,
    graph_sync_space_from_model,
    json_object_or_empty,
    normalize_schedule_cadence,
)
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject, ResearchSpaceSettings
    from sqlalchemy.orm import Session

_DateTimeNormalizer = Callable[[datetime | None], datetime]


def _current_normalized_utc_datetime(value: datetime | None = None) -> datetime:
    facade = sys.modules.get("artana_evidence_api.sqlalchemy_stores")
    candidate = getattr(facade, "_normalized_utc_datetime", None)
    if candidate is None or candidate is _current_normalized_utc_datetime:
        return _normalized_utc_datetime(value)
    return cast("_DateTimeNormalizer", candidate)(value)


class SqlAlchemyHarnessScheduleStore(HarnessScheduleStore, _SessionBackedStore):
    """Persist harness schedule definitions in relational storage."""

    def __init__(self, session: Session | None = None) -> None:
        _SessionBackedStore.__init__(self, session)

    def create_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        harness_id: str,
        title: str,
        cadence: str,
        created_by: UUID | str,
        configuration: JSONObject,
        metadata: JSONObject,
        status: str = "active",
    ) -> HarnessScheduleRecord:
        normalized_cadence = normalize_schedule_cadence(cadence)
        model = HarnessScheduleModel(
            space_id=str(space_id),
            harness_id=harness_id,
            title=title,
            cadence=normalized_cadence,
            status=status,
            created_by=str(created_by),
            configuration_payload=configuration,
            metadata_payload=metadata,
            last_run_id=None,
            last_run_at=None,
            active_trigger_claim_id=None,
            active_trigger_claimed_at=None,
        )
        self.session.add(model)
        self.session.commit()
        self.session.refresh(model)
        return _schedule_record_from_model(model)

    def list_schedules(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessScheduleRecord]:
        stmt = (
            select(HarnessScheduleModel)
            .where(HarnessScheduleModel.space_id == str(space_id))
            .order_by(HarnessScheduleModel.updated_at.desc())
        )
        models = self.session.execute(stmt).scalars().all()
        return [_schedule_record_from_model(model) for model in models]

    def count_schedules(
        self,
        *,
        space_id: UUID | str,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(HarnessScheduleModel)
            .where(
                HarnessScheduleModel.space_id == str(space_id),
            )
        )
        return int(self.session.execute(stmt).scalar_one())

    def list_all_schedules(
        self,
        *,
        status: str | None = None,
    ) -> list[HarnessScheduleRecord]:
        stmt = select(HarnessScheduleModel).order_by(
            HarnessScheduleModel.updated_at.desc(),
        )
        if isinstance(status, str) and status.strip() != "":
            stmt = stmt.where(HarnessScheduleModel.status == status.strip())
        models = self.session.execute(stmt).scalars().all()
        return [_schedule_record_from_model(model) for model in models]

    def get_schedule(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
    ) -> HarnessScheduleRecord | None:
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        return _schedule_record_from_model(model)

    def update_schedule(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        title: str | None = None,
        cadence: str | None = None,
        status: str | None = None,
        configuration: JSONObject | None = None,
        metadata: JSONObject | None = None,
        last_run_id: UUID | str | None = None,
        last_run_at: datetime | None = None,
    ) -> HarnessScheduleRecord | None:
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        if isinstance(title, str) and title.strip() != "":
            model.title = title
        if isinstance(cadence, str) and cadence.strip() != "":
            model.cadence = normalize_schedule_cadence(cadence)
        if isinstance(status, str) and status.strip() != "":
            model.status = status
        if configuration is not None:
            model.configuration_payload = configuration
        if metadata is not None:
            model.metadata_payload = metadata
        if last_run_id is not None:
            model.last_run_id = str(last_run_id)
        if last_run_at is not None:
            model.last_run_at = last_run_at
        self.session.commit()
        self.session.refresh(model)
        return _schedule_record_from_model(model)

    def acquire_trigger_claim(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        claim_id: UUID | str,
        claimed_at: datetime | None = None,
        ttl_seconds: int = 30,
    ) -> HarnessScheduleRecord | None:
        normalized_now = _current_normalized_utc_datetime(claimed_at)
        stale_before = normalized_now - timedelta(seconds=ttl_seconds)
        stmt = (
            update(HarnessScheduleModel)
            .where(HarnessScheduleModel.id == str(schedule_id))
            .where(HarnessScheduleModel.space_id == str(space_id))
            .where(
                or_(
                    HarnessScheduleModel.active_trigger_claim_id.is_(None),
                    HarnessScheduleModel.active_trigger_claimed_at.is_(None),
                    HarnessScheduleModel.active_trigger_claimed_at <= stale_before,
                    HarnessScheduleModel.active_trigger_claim_id == str(claim_id),
                ),
            )
            .values(
                active_trigger_claim_id=str(claim_id),
                active_trigger_claimed_at=normalized_now,
            )
        )
        result = self.session.execute(stmt)
        self.session.commit()
        if _result_rowcount(result) != 1:
            return None
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        self.session.refresh(model)
        return _schedule_record_from_model(model)

    def release_trigger_claim(
        self,
        *,
        space_id: UUID | str,
        schedule_id: UUID | str,
        claim_id: UUID | str,
    ) -> HarnessScheduleRecord | None:
        stmt = (
            update(HarnessScheduleModel)
            .where(HarnessScheduleModel.id == str(schedule_id))
            .where(HarnessScheduleModel.space_id == str(space_id))
            .where(HarnessScheduleModel.active_trigger_claim_id == str(claim_id))
            .values(
                active_trigger_claim_id=None,
                active_trigger_claimed_at=None,
            )
        )
        result = self.session.execute(stmt)
        self.session.commit()
        if _result_rowcount(result) != 1:
            return None
        model = self.session.get(HarnessScheduleModel, str(schedule_id))
        if model is None or model.space_id != str(space_id):
            return None
        self.session.refresh(model)
        return _schedule_record_from_model(model)


class SqlAlchemyHarnessResearchSpaceStore(
    HarnessResearchSpaceStore,
    _SessionBackedStore,
):
    """Read and create research spaces backed by shared platform tables."""

    def __init__(
        self,
        session: Session | None = None,
        *,
        space_lifecycle_sync: SpaceLifecycleSyncPort | None = None,
    ) -> None:
        HarnessResearchSpaceStore.__init__(self)
        _SessionBackedStore.__init__(self, session)
        self._space_lifecycle_sync = space_lifecycle_sync

    def _sync_space_model(self, model: ResearchSpaceModel) -> None:
        if self._space_lifecycle_sync is None:
            return
        self._space_lifecycle_sync.sync_space(graph_sync_space_from_model(model))

    def _ensure_owner_user(  # noqa: PLR0913
        self,
        *,
        owner_id: UUID,
        owner_email: str | None = None,
        owner_username: str | None = None,
        owner_full_name: str | None = None,
        owner_role: str | None = None,
        owner_status: str | None = None,
    ) -> UUID:
        existing_owner = self.session.get(HarnessUserModel, owner_id)
        if existing_owner is not None:
            return owner_id

        fallback_email = f"{owner_id}@graph-harness.example.com"
        normalized_email = _normalize_owner_text(
            owner_email,
            fallback=fallback_email,
            max_length=255,
        )
        normalized_username = _normalize_owner_text(
            owner_username,
            fallback=normalized_email.split("@", maxsplit=1)[0],
            max_length=50,
        )
        normalized_full_name = _normalize_owner_text(
            owner_full_name,
            fallback=normalized_email,
            max_length=100,
        )
        identity_match = (
            self.session.execute(
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
                raise HarnessUserIdentityConflictError(msg)
            return _as_uuid(identity_match.id)
        self.session.add(
            HarnessUserModel(
                id=owner_id,
                email=normalized_email,
                username=normalized_username,
                full_name=normalized_full_name,
                hashed_password="external-auth-not-applicable",
                role=_normalize_owner_text(
                    owner_role,
                    fallback="viewer",
                    max_length=32,
                ).lower(),
                status=_normalize_owner_text(
                    owner_status,
                    fallback="active",
                    max_length=32,
                ).lower(),
                email_verified=True,
                login_attempts=0,
            ),
        )
        self.session.flush()
        return owner_id

    def _ensure_owner_membership(
        self,
        *,
        space_id: UUID,
        owner_id: UUID,
    ) -> None:
        membership = (
            self.session.execute(
                select(ResearchSpaceMembershipModel).where(
                    ResearchSpaceMembershipModel.space_id == space_id,
                    ResearchSpaceMembershipModel.user_id == owner_id,
                ),
            )
            .scalars()
            .first()
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        if membership is None:
            self.session.add(
                ResearchSpaceMembershipModel(
                    space_id=space_id,
                    user_id=owner_id,
                    role=MembershipRoleEnum.OWNER,
                    invited_by=None,
                    invited_at=None,
                    joined_at=now,
                    is_active=True,
                ),
            )
            return

        membership.role = MembershipRoleEnum.OWNER
        membership.is_active = True
        if membership.joined_at is None:
            membership.joined_at = now

    def _role_for_space_row(
        self,
        *,
        space_model: ResearchSpaceModel,
        membership_role: MembershipRoleEnum | None,
        current_user_id: UUID,
        is_admin: bool,
    ) -> str:
        if isinstance(membership_role, MembershipRoleEnum):
            return membership_role.value
        if space_model.owner_id == current_user_id:
            return MembershipRoleEnum.OWNER.value
        if is_admin:
            return MembershipRoleEnum.ADMIN.value
        return MembershipRoleEnum.VIEWER.value

    def list_spaces(
        self,
        *,
        user_id: UUID | str,
        is_admin: bool,
    ) -> list[HarnessResearchSpaceRecord]:
        normalized_user_id = _as_uuid(user_id)
        membership_join = and_(
            ResearchSpaceMembershipModel.space_id == ResearchSpaceModel.id,
            ResearchSpaceMembershipModel.user_id == normalized_user_id,
            ResearchSpaceMembershipModel.is_active.is_(True),
        )
        stmt = (
            select(ResearchSpaceModel, ResearchSpaceMembershipModel.role)
            .outerjoin(ResearchSpaceMembershipModel, membership_join)
            .where(ResearchSpaceModel.status != SpaceStatusEnum.ARCHIVED)
            .order_by(ResearchSpaceModel.created_at.desc())
        )
        if not is_admin:
            stmt = stmt.where(
                or_(
                    ResearchSpaceModel.owner_id == normalized_user_id,
                    ResearchSpaceMembershipModel.id.is_not(None),
                ),
            )

        rows = self.session.execute(stmt).all()
        records: list[HarnessResearchSpaceRecord] = []
        for space_model, membership_role in rows:
            records.append(
                _research_space_record_from_model(
                    space_model,
                    role=self._role_for_space_row(
                        space_model=space_model,
                        membership_role=membership_role,
                        current_user_id=normalized_user_id,
                        is_admin=is_admin,
                    ),
                ),
            )
        return records

    def get_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord | None:
        normalized_space_id = _as_uuid(space_id)
        normalized_user_id = _as_uuid(user_id)
        membership_join = and_(
            ResearchSpaceMembershipModel.space_id == ResearchSpaceModel.id,
            ResearchSpaceMembershipModel.user_id == normalized_user_id,
            ResearchSpaceMembershipModel.is_active.is_(True),
        )
        stmt = (
            select(ResearchSpaceModel, ResearchSpaceMembershipModel.role)
            .outerjoin(ResearchSpaceMembershipModel, membership_join)
            .where(
                ResearchSpaceModel.id == normalized_space_id,
                ResearchSpaceModel.status != SpaceStatusEnum.ARCHIVED,
            )
        )
        if not is_admin:
            stmt = stmt.where(
                or_(
                    ResearchSpaceModel.owner_id == normalized_user_id,
                    ResearchSpaceMembershipModel.id.is_not(None),
                ),
            )
        row = self.session.execute(stmt).first()
        if row is None:
            return None
        space_model, membership_role = row
        return _research_space_record_from_model(
            space_model,
            role=self._role_for_space_row(
                space_model=space_model,
                membership_role=membership_role,
                current_user_id=normalized_user_id,
                is_admin=is_admin,
            ),
        )

    def get_default_space(
        self,
        *,
        user_id: UUID | str,
    ) -> HarnessResearchSpaceRecord | None:
        normalized_user_id = _as_uuid(user_id)
        models = (
            self.session.execute(
                select(ResearchSpaceModel)
                .where(
                    ResearchSpaceModel.owner_id == normalized_user_id,
                    ResearchSpaceModel.status != SpaceStatusEnum.ARCHIVED,
                )
                .order_by(ResearchSpaceModel.created_at.asc()),
            )
            .scalars()
            .all()
        )
        for model in models:
            if _is_personal_default_space(model):
                return _research_space_record_from_model(
                    model,
                    role=MembershipRoleEnum.OWNER.value,
                )
        return None

    def create_space(
        self,
        *,
        owner_id: UUID | str,
        owner_email: str | None = None,
        owner_username: str | None = None,
        owner_full_name: str | None = None,
        owner_role: str | None = None,
        owner_status: str | None = None,
        name: str,
        description: str | None,
        settings: ResearchSpaceSettings | None = None,
    ) -> HarnessResearchSpaceRecord:
        normalized_name = name.strip()
        if normalized_name == "":
            msg = "Space name is required"
            raise ValueError(msg)
        normalized_description = (
            description.strip() if isinstance(description, str) else ""
        )
        owner_uuid = _as_uuid(owner_id)
        owner_uuid = self._ensure_owner_user(
            owner_id=owner_uuid,
            owner_email=owner_email,
            owner_username=owner_username,
            owner_full_name=owner_full_name,
            owner_role=owner_role,
            owner_status=owner_status,
        )

        existing_slugs = set(
            self.session.execute(select(ResearchSpaceModel.slug)).scalars().all(),
        )
        model = ResearchSpaceModel(
            slug=build_unique_space_slug(normalized_name, existing_slugs),
            name=normalized_name,
            description=normalized_description,
            owner_id=owner_uuid,
            status=SpaceStatusEnum.ACTIVE,
            settings=settings or {},
            tags=[],
        )
        self.session.add(model)
        try:
            self.session.flush()
            self._ensure_owner_membership(space_id=_as_uuid(model.id), owner_id=owner_uuid)
            self.session.flush()
            self._sync_space_model(model)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(model)
        return _research_space_record_from_model(
            model,
            role=MembershipRoleEnum.OWNER.value,
        )

    def ensure_default_space(  # noqa: PLR0913
        self,
        *,
        owner_id: UUID | str,
        owner_email: str | None = None,
        owner_username: str | None = None,
        owner_full_name: str | None = None,
        owner_role: str | None = None,
        owner_status: str | None = None,
    ) -> HarnessResearchSpaceRecord:
        owner_uuid = _as_uuid(owner_id)
        owner_uuid = self._ensure_owner_user(
            owner_id=owner_uuid,
            owner_email=owner_email,
            owner_username=owner_username,
            owner_full_name=owner_full_name,
            owner_role=owner_role,
            owner_status=owner_status,
        )
        existing_record = self.get_default_space(user_id=owner_uuid)
        if existing_record is not None:
            return existing_record

        model = ResearchSpaceModel(
            slug=_personal_default_slug(owner_uuid),
            name=PERSONAL_DEFAULT_SPACE_NAME,
            description=PERSONAL_DEFAULT_SPACE_DESCRIPTION,
            owner_id=owner_uuid,
            status=SpaceStatusEnum.ACTIVE,
            settings={PERSONAL_DEFAULT_SETTING_KEY: True},
            tags=["personal-default"],
        )
        self.session.add(model)
        try:
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            existing_after_conflict = self.get_default_space(user_id=owner_uuid)
            if existing_after_conflict is not None:
                return existing_after_conflict
            raise

        try:
            self._ensure_owner_membership(space_id=_as_uuid(model.id), owner_id=owner_uuid)
            self.session.flush()
            self._sync_space_model(model)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(model)
        return _research_space_record_from_model(
            model,
            role=MembershipRoleEnum.OWNER.value,
        )

    def update_space_settings(
        self,
        *,
        space_id: UUID | str,
        settings: ResearchSpaceSettings,
    ) -> HarnessResearchSpaceRecord:
        """Replace one research space settings payload."""
        model = self.session.get(ResearchSpaceModel, _as_uuid(space_id))
        if model is None or model.status == SpaceStatusEnum.ARCHIVED:
            msg = "Space not found"
            raise KeyError(msg)
        model.settings = json_object_or_empty(settings)
        try:
            self.session.flush()
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        self.session.refresh(model)
        return _research_space_record_from_model(
            model,
            role=MembershipRoleEnum.OWNER.value,
        )

    def prepare_space_archive(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Return one archivable space when the caller may manage it."""
        space_uuid = _as_uuid(space_id)
        user_uuid = _as_uuid(user_id)

        model = self.session.get(ResearchSpaceModel, space_uuid)
        if model is None or model.status == SpaceStatusEnum.ARCHIVED:
            msg = "Space not found"
            raise KeyError(msg)

        if not is_admin and model.owner_id != user_uuid:
            msg = "Only the space owner or an admin can delete this space"
            raise PermissionError(msg)

        return _research_space_record_from_model(
            model,
            role=(
                MembershipRoleEnum.ADMIN.value
                if is_admin and model.owner_id != user_uuid
                else MembershipRoleEnum.OWNER.value
            ),
        )

    def archive_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Archive one research space when the caller is allowed to manage it."""
        archivable_record = self.prepare_space_archive(
            space_id=space_id,
            user_id=user_id,
            is_admin=is_admin,
        )
        model = self.session.get(ResearchSpaceModel, _as_uuid(space_id))
        if model is None or model.status == SpaceStatusEnum.ARCHIVED:
            msg = "Space not found"
            raise KeyError(msg)
        model.status = SpaceStatusEnum.ARCHIVED
        self.session.commit()
        self.session.refresh(model)
        return _research_space_record_from_model(
            model,
            role=archivable_record.role,
        )

    def delete_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        return self.archive_space(
            space_id=space_id,
            user_id=user_id,
            is_admin=is_admin,
        )

    # ------------------------------------------------------------------
    # Membership management
    # ------------------------------------------------------------------

    def list_members(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessSpaceMemberRecord]:
        normalized_space_id = _as_uuid(space_id)
        stmt = select(ResearchSpaceMembershipModel).where(
            ResearchSpaceMembershipModel.space_id == normalized_space_id,
            ResearchSpaceMembershipModel.is_active.is_(True),
        )
        rows = self.session.execute(stmt).scalars().all()
        return [
            HarnessSpaceMemberRecord(
                id=str(row.id),
                space_id=str(row.space_id),
                user_id=str(row.user_id),
                role=(
                    row.role.value
                    if isinstance(row.role, MembershipRoleEnum)
                    else str(row.role)
                ),
                invited_by=str(row.invited_by) if row.invited_by else None,
                invited_at=row.invited_at.isoformat() if row.invited_at else None,
                joined_at=row.joined_at.isoformat() if row.joined_at else None,
                is_active=row.is_active,
            )
            for row in rows
        ]

    def add_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        role: str,
        invited_by: UUID | str | None = None,
    ) -> HarnessSpaceMemberRecord:
        normalized_space_id = _as_uuid(space_id)
        normalized_user_id = _as_uuid(user_id)
        normalized_role = _normalize_assignable_member_role(role)
        now = datetime.now(UTC).replace(tzinfo=None)

        self._ensure_owner_user(owner_id=normalized_user_id)

        space = self.session.get(ResearchSpaceModel, normalized_space_id)
        if space is None:
            msg = "Space not found"
            raise KeyError(msg)

        existing = (
            self.session.execute(
                select(ResearchSpaceMembershipModel).where(
                    ResearchSpaceMembershipModel.space_id == normalized_space_id,
                    ResearchSpaceMembershipModel.user_id == normalized_user_id,
                ),
            )
            .scalars()
            .first()
        )

        if existing is not None:
            existing.role = MembershipRoleEnum(normalized_role)
            existing.is_active = True
            if existing.joined_at is None:
                existing.joined_at = now
            self.session.commit()
            self.session.refresh(existing)
            model = existing
        else:
            model = ResearchSpaceMembershipModel(
                space_id=normalized_space_id,
                user_id=normalized_user_id,
                role=MembershipRoleEnum(normalized_role),
                invited_by=_as_uuid(invited_by) if invited_by else None,
                invited_at=now,
                joined_at=now,
                is_active=True,
            )
            self.session.add(model)
            self.session.commit()
            self.session.refresh(model)

        return HarnessSpaceMemberRecord(
            id=str(model.id),
            space_id=str(model.space_id),
            user_id=str(model.user_id),
            role=(
                model.role.value
                if isinstance(model.role, MembershipRoleEnum)
                else str(model.role)
            ),
            invited_by=str(model.invited_by) if model.invited_by else None,
            invited_at=model.invited_at.isoformat() if model.invited_at else None,
            joined_at=model.joined_at.isoformat() if model.joined_at else None,
            is_active=model.is_active,
        )

    def remove_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
    ) -> HarnessSpaceMemberRecord | None:
        normalized_space_id = _as_uuid(space_id)
        normalized_user_id = _as_uuid(user_id)

        existing = (
            self.session.execute(
                select(ResearchSpaceMembershipModel).where(
                    ResearchSpaceMembershipModel.space_id == normalized_space_id,
                    ResearchSpaceMembershipModel.user_id == normalized_user_id,
                    ResearchSpaceMembershipModel.is_active.is_(True),
                ),
            )
            .scalars()
            .first()
        )
        if existing is None:
            return None

        existing.is_active = False
        self.session.commit()
        self.session.refresh(existing)
        return HarnessSpaceMemberRecord(
            id=str(existing.id),
            space_id=str(existing.space_id),
            user_id=str(existing.user_id),
            role=(
                existing.role.value
                if isinstance(existing.role, MembershipRoleEnum)
                else str(existing.role)
            ),
            invited_by=str(existing.invited_by) if existing.invited_by else None,
            invited_at=existing.invited_at.isoformat() if existing.invited_at else None,
            joined_at=existing.joined_at.isoformat() if existing.joined_at else None,
            is_active=existing.is_active,
        )
