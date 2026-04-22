"""Research-space storage contracts for graph-harness space discovery."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from artana_evidence_api.models.research_space import MembershipRoleEnum
from artana_evidence_api.types.common import ResearchSpaceSettings

_SPACE_SLUG_MAX_LENGTH = 50
_NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9]+")
PERSONAL_DEFAULT_SETTING_KEY = "personal_default"
PERSONAL_DEFAULT_SPACE_NAME = "Personal Sandbox"
PERSONAL_DEFAULT_SPACE_DESCRIPTION = "Private default research space."
_ASSIGNABLE_MEMBER_ROLE_VALUES = frozenset(
    role.value for role in MembershipRoleEnum if role is not MembershipRoleEnum.OWNER
)


def _normalize_space_name(name: str) -> str:
    normalized = name.strip()
    if normalized == "":
        msg = "Space name is required"
        raise ValueError(msg)
    return normalized


def _normalize_space_description(description: str | None) -> str:
    if not isinstance(description, str):
        return ""
    return description.strip()


def _slug_base(name: str) -> str:
    ascii_name = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    )
    collapsed = _NON_ALPHANUMERIC_PATTERN.sub("-", ascii_name.lower()).strip("-")
    base = collapsed[:_SPACE_SLUG_MAX_LENGTH].strip("-")
    return base or "space"


def _build_slug_candidate(base: str, index: int) -> str:
    if index <= 1:
        return base
    suffix = f"-{index}"
    trimmed_base = base[: _SPACE_SLUG_MAX_LENGTH - len(suffix)].rstrip("-")
    if trimmed_base == "":
        trimmed_base = "space"
    return f"{trimmed_base}{suffix}"


def build_unique_space_slug(name: str, existing_slugs: set[str]) -> str:
    """Generate a unique slug for one space name."""
    base = _slug_base(name)
    index = 1
    while True:
        candidate = _build_slug_candidate(base, index)
        if candidate not in existing_slugs:
            return candidate
        index += 1


def _normalize_assignable_member_role(role: str) -> str:
    if not isinstance(role, str):
        msg = f"Invalid space member role: {role!r}"
        raise TypeError(msg)
    normalized_role = role.strip().lower()
    if normalized_role == "":
        msg = f"Invalid space member role: {role!r}"
        raise ValueError(msg)
    try:
        resolved_role = MembershipRoleEnum(normalized_role)
    except ValueError as exc:
        msg = f"Invalid space member role: {role!r}"
        raise ValueError(msg) from exc
    if resolved_role.value not in _ASSIGNABLE_MEMBER_ROLE_VALUES:
        msg = f"Invalid space member role: {role!r}"
        raise ValueError(msg)
    return resolved_role.value


@dataclass(frozen=True, slots=True)
class HarnessResearchSpaceRecord:
    """One research space accessible through the harness service."""

    id: str
    slug: str
    name: str
    description: str
    status: str
    role: str
    is_default: bool = False
    settings: ResearchSpaceSettings | None = None


@dataclass(frozen=True, slots=True)
class HarnessSpaceMemberRecord:
    """One membership entry for a space member."""

    id: str
    space_id: str
    user_id: str
    role: str
    invited_by: str | None = None
    invited_at: str | None = None
    joined_at: str | None = None
    is_active: bool = True


class HarnessUserIdentityConflictError(RuntimeError):
    """Raised when one auth identity conflicts with an existing shared user."""


class HarnessResearchSpaceStore:
    """In-memory research-space registry used by unit tests and local wiring."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[str, HarnessResearchSpaceRecord] = {}
        self._owner_ids: dict[str, str] = {}
        self._members: dict[str, list[HarnessSpaceMemberRecord]] = {}

    def list_spaces(
        self,
        *,
        user_id: UUID | str,
        is_admin: bool,
    ) -> list[HarnessResearchSpaceRecord]:
        """List spaces visible to one caller."""
        normalized_user_id = str(user_id)
        with self._lock:
            records = list(self._records.values())

        if is_admin:
            return [
                HarnessResearchSpaceRecord(
                    id=record.id,
                    slug=record.slug,
                    name=record.name,
                    description=record.description,
                    status=record.status,
                    role=(
                        "owner"
                        if self._owner_ids.get(record.id) == normalized_user_id
                        else "admin"
                    ),
                    is_default=record.is_default,
                    settings=record.settings,
                )
                for record in records
                if record.status != "archived"
            ]

        return [
            record
            for record in records
            if record.status != "archived"
            and self._owner_ids.get(record.id) == normalized_user_id
        ]

    def get_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord | None:
        """Return one accessible research space for the caller."""
        normalized_space_id = str(space_id)
        normalized_user_id = str(user_id)
        with self._lock:
            record = self._records.get(normalized_space_id)

        if record is None or record.status == "archived":
            return None

        owner_id = self._owner_ids.get(normalized_space_id)
        if owner_id == normalized_user_id:
            return record
        if is_admin:
            return HarnessResearchSpaceRecord(
                id=record.id,
                slug=record.slug,
                name=record.name,
                description=record.description,
                status=record.status,
                role="admin",
                is_default=record.is_default,
                settings=record.settings,
            )
        return None

    def get_default_space(
        self,
        *,
        user_id: UUID | str,
    ) -> HarnessResearchSpaceRecord | None:
        """Return the caller's personal default space when it exists."""
        normalized_user_id = str(user_id)
        with self._lock:
            records = list(self._records.values())
        for record in records:
            if (
                record.status != "archived"
                and record.is_default
                and self._owner_ids.get(record.id) == normalized_user_id
            ):
                return record
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
        """Create one new research space."""
        del (
            owner_email,
            owner_username,
            owner_full_name,
            owner_role,
            owner_status,
        )
        normalized_name = _normalize_space_name(name)
        normalized_description = _normalize_space_description(description)

        with self._lock:
            existing_slugs = {record.slug for record in self._records.values()}
            record = HarnessResearchSpaceRecord(
                id=str(uuid4()),
                slug=build_unique_space_slug(normalized_name, existing_slugs),
                name=normalized_name,
                description=normalized_description,
                status="active",
                role="owner",
                settings=settings,
            )
            self._records[record.id] = record
            self._owner_ids[record.id] = str(owner_id)
            return record

    def ensure_default_space(
        self,
        *,
        owner_id: UUID | str,
        owner_email: str | None = None,
        owner_username: str | None = None,
        owner_full_name: str | None = None,
        owner_role: str | None = None,
        owner_status: str | None = None,
    ) -> HarnessResearchSpaceRecord:
        """Return the caller's personal default space, creating it if missing."""
        del (
            owner_email,
            owner_username,
            owner_full_name,
            owner_role,
            owner_status,
        )
        existing_record = self.get_default_space(user_id=owner_id)
        if existing_record is not None:
            return existing_record

        with self._lock:
            existing_slugs = {record.slug for record in self._records.values()}
            record = HarnessResearchSpaceRecord(
                id=str(uuid4()),
                slug=build_unique_space_slug(
                    PERSONAL_DEFAULT_SPACE_NAME,
                    existing_slugs,
                ),
                name=PERSONAL_DEFAULT_SPACE_NAME,
                description=PERSONAL_DEFAULT_SPACE_DESCRIPTION,
                status="active",
                role="owner",
                is_default=True,
            )
            self._records[record.id] = record
            self._owner_ids[record.id] = str(owner_id)
            return record

    def prepare_space_archive(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Return one archivable space when the caller may manage it."""
        normalized_space_id = str(space_id)
        normalized_user_id = str(user_id)

        with self._lock:
            record = self._records.get(normalized_space_id)
            if record is None or record.status == "archived":
                msg = "Space not found"
                raise KeyError(msg)

            owner_id = self._owner_ids.get(normalized_space_id)
            if not is_admin and owner_id != normalized_user_id:
                msg = "Only the space owner or an admin can delete this space"
                raise PermissionError(msg)

            if is_admin and owner_id != normalized_user_id:
                return HarnessResearchSpaceRecord(
                    id=record.id,
                    slug=record.slug,
                    name=record.name,
                    description=record.description,
                    status=record.status,
                    role="admin",
                    is_default=record.is_default,
                    settings=record.settings,
                )
            return record

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
        normalized_space_id = str(space_id)

        with self._lock:
            current = self._records.get(normalized_space_id)
            if current is None or current.status == "archived":
                msg = "Space not found"
                raise KeyError(msg)
            archived_record = HarnessResearchSpaceRecord(
                id=current.id,
                slug=current.slug,
                name=current.name,
                description=current.description,
                status="archived",
                role=archivable_record.role,
                is_default=current.is_default,
                settings=current.settings,
            )
            self._records[normalized_space_id] = archived_record
            return archived_record

    def delete_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Archive one research space when the caller is allowed to manage it."""
        return self.archive_space(
            space_id=space_id,
            user_id=user_id,
            is_admin=is_admin,
        )

    def update_space_settings(
        self,
        *,
        space_id: UUID | str,
        settings: ResearchSpaceSettings,
    ) -> HarnessResearchSpaceRecord:
        """Replace one research space settings payload."""
        normalized_space_id = str(space_id)
        with self._lock:
            current = self._records.get(normalized_space_id)
            if current is None or current.status == "archived":
                msg = "Space not found"
                raise KeyError(msg)
            updated = HarnessResearchSpaceRecord(
                id=current.id,
                slug=current.slug,
                name=current.name,
                description=current.description,
                status=current.status,
                role=current.role,
                is_default=current.is_default,
                settings=dict(settings),
            )
            self._records[normalized_space_id] = updated
            return updated

    # ------------------------------------------------------------------
    # Membership management
    # ------------------------------------------------------------------

    def list_members(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessSpaceMemberRecord]:
        """Return all active members for the given space."""
        normalized_space_id = str(space_id)
        with self._lock:
            members = self._members.get(normalized_space_id, [])
            return [m for m in members if m.is_active]

    def add_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        role: str,
        invited_by: UUID | str | None = None,
    ) -> HarnessSpaceMemberRecord:
        """Add or re-activate a member in one space."""
        normalized_space_id = str(space_id)
        normalized_user_id = str(user_id)
        normalized_role = _normalize_assignable_member_role(role)
        now = datetime.now(UTC).isoformat()

        with self._lock:
            if normalized_space_id not in self._records:
                msg = "Space not found"
                raise KeyError(msg)

            existing_members = self._members.setdefault(normalized_space_id, [])
            for i, member in enumerate(existing_members):
                if member.user_id == normalized_user_id:
                    updated = HarnessSpaceMemberRecord(
                        id=member.id,
                        space_id=normalized_space_id,
                        user_id=normalized_user_id,
                        role=normalized_role,
                        invited_by=str(invited_by) if invited_by else member.invited_by,
                        invited_at=member.invited_at,
                        joined_at=now,
                        is_active=True,
                    )
                    existing_members[i] = updated
                    return updated

            record = HarnessSpaceMemberRecord(
                id=str(uuid4()),
                space_id=normalized_space_id,
                user_id=normalized_user_id,
                role=normalized_role,
                invited_by=str(invited_by) if invited_by else None,
                invited_at=now,
                joined_at=now,
                is_active=True,
            )
            existing_members.append(record)
            return record

    def remove_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
    ) -> HarnessSpaceMemberRecord | None:
        """Deactivate a member from one space. Returns the updated record or None."""
        normalized_space_id = str(space_id)
        normalized_user_id = str(user_id)

        with self._lock:
            existing_members = self._members.get(normalized_space_id, [])
            for i, member in enumerate(existing_members):
                if member.user_id == normalized_user_id and member.is_active:
                    updated = HarnessSpaceMemberRecord(
                        id=member.id,
                        space_id=member.space_id,
                        user_id=member.user_id,
                        role=member.role,
                        invited_by=member.invited_by,
                        invited_at=member.invited_at,
                        joined_at=member.joined_at,
                        is_active=False,
                    )
                    existing_members[i] = updated
                    return updated
            return None


__all__ = [
    "HarnessResearchSpaceRecord",
    "HarnessResearchSpaceStore",
    "HarnessSpaceMemberRecord",
    "HarnessUserIdentityConflictError",
    "PERSONAL_DEFAULT_SETTING_KEY",
    "PERSONAL_DEFAULT_SPACE_DESCRIPTION",
    "PERSONAL_DEFAULT_SPACE_NAME",
    "build_unique_space_slug",
]
