"""Contracts for the evidence API local identity boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceRecord,
    HarnessSpaceMemberRecord,
)
from artana_evidence_api.types.common import ResearchSpaceSettings

_ROLE_HIERARCHY: tuple[str, ...] = (
    "owner",
    "admin",
    "curator",
    "researcher",
    "viewer",
)


class IdentityUserConflictError(RuntimeError):
    """Raised when a requested user identity conflicts with an existing user."""


class IdentityUserNotFoundError(RuntimeError):
    """Raised when a membership or key operation targets a missing user."""


def role_rank(role: str) -> int:
    """Return the privilege rank for one space role."""
    try:
        return _ROLE_HIERARCHY.index(role.strip().lower())
    except ValueError:
        return len(_ROLE_HIERARCHY)


def role_at_least(actual_role: str, minimum_role: str) -> bool:
    """Return whether *actual_role* satisfies *minimum_role*."""
    return role_rank(actual_role) <= role_rank(minimum_role)


@dataclass(frozen=True, slots=True)
class IdentityUserRecord:
    """One local identity user record exposed through the boundary."""

    id: UUID
    email: str
    username: str
    full_name: str
    role: str
    status: str


@dataclass(frozen=True, slots=True)
class IdentityApiKeyRecord:
    """One API key summary exposed through the boundary."""

    id: UUID
    name: str
    key_prefix: str
    status: str
    created_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IdentityIssuedApiKey:
    """A newly issued API key plus its summary record."""

    raw_key: str
    record: IdentityApiKeyRecord


@dataclass(frozen=True, slots=True)
class IdentitySpaceAccessDecision:
    """Result of one space-access decision."""

    allowed: bool
    space: HarnessResearchSpaceRecord | None
    actual_role: str | None
    minimum_role: str
    reason: str | None = None


class IdentityGateway(Protocol):
    """Identity and tenancy operations owned by the local identity boundary."""

    def get_user(self, user_id: UUID | str) -> IdentityUserRecord | None:
        """Return one user by id."""

    def canonicalize_user_claims(
        self,
        user: IdentityUserRecord,
    ) -> IdentityUserRecord:
        """Reuse an existing local identity when token claims identify it."""

    def create_tester_user(
        self,
        *,
        email: str,
        username: str | None,
        full_name: str | None,
        role: str,
        user_id: UUID | str | None = None,
    ) -> IdentityUserRecord:
        """Create or reuse one tester/local user."""

    def bootstrap_already_completed(self) -> bool:
        """Return whether first-user bootstrap is locked."""

    def bootstrap_recovery_user(self) -> IdentityUserRecord | None:
        """Return the single recoverable bootstrap user, if any."""

    def resolve_api_key(self, raw_key: str) -> IdentityUserRecord | None:
        """Resolve one raw API key to its user."""

    def issue_api_key(
        self,
        *,
        user_id: UUID | str,
        name: str,
        description: str = "",
    ) -> IdentityIssuedApiKey:
        """Issue a new API key for a user."""

    def list_api_keys(self, *, user_id: UUID | str) -> list[IdentityApiKeyRecord]:
        """List API keys for a user."""

    def revoke_api_key(
        self,
        *,
        key_id: UUID | str,
        user_id: UUID | str,
    ) -> IdentityApiKeyRecord | None:
        """Revoke one API key."""

    def rotate_api_key(
        self,
        *,
        key_id: UUID | str,
        user_id: UUID | str,
    ) -> IdentityIssuedApiKey | None:
        """Rotate one API key."""

    def list_spaces(
        self,
        *,
        user_id: UUID | str,
        is_admin: bool,
    ) -> list[HarnessResearchSpaceRecord]:
        """List spaces visible to a user."""

    def get_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord | None:
        """Return one accessible space."""

    def create_space(
        self,
        *,
        owner: IdentityUserRecord,
        name: str,
        description: str | None,
        settings: ResearchSpaceSettings | None = None,
    ) -> HarnessResearchSpaceRecord:
        """Create one space for an existing local user."""

    def get_default_space(
        self,
        *,
        user_id: UUID | str,
    ) -> HarnessResearchSpaceRecord | None:
        """Return a user's default space, if present."""

    def ensure_default_space(
        self,
        *,
        owner: IdentityUserRecord,
    ) -> HarnessResearchSpaceRecord:
        """Return or create a user's default space."""

    def update_space_settings(
        self,
        *,
        space_id: UUID | str,
        settings: ResearchSpaceSettings,
    ) -> HarnessResearchSpaceRecord:
        """Update owner-managed space settings."""

    def prepare_space_archive(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Validate that a space can be archived by a user."""

    def archive_space(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_admin: bool,
    ) -> HarnessResearchSpaceRecord:
        """Archive one space."""

    def list_members(
        self,
        *,
        space_id: UUID | str,
    ) -> list[HarnessSpaceMemberRecord]:
        """List active members for one space."""

    def add_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        role: str,
        invited_by: UUID | str | None = None,
    ) -> HarnessSpaceMemberRecord:
        """Add an existing user to a space."""

    def remove_member(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
    ) -> HarnessSpaceMemberRecord | None:
        """Remove one user from a space."""

    def check_space_access(
        self,
        *,
        space_id: UUID | str,
        user_id: UUID | str,
        is_platform_admin: bool,
        is_service_user: bool,
        minimum_role: str = "viewer",
    ) -> IdentitySpaceAccessDecision:
        """Return the local decision for one space-access check."""


__all__ = [
    "IdentityApiKeyRecord",
    "IdentityGateway",
    "IdentityIssuedApiKey",
    "IdentitySpaceAccessDecision",
    "IdentityUserConflictError",
    "IdentityUserNotFoundError",
    "IdentityUserRecord",
    "role_at_least",
    "role_rank",
]
