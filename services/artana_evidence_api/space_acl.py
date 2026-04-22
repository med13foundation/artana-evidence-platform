"""Space-level access control enforcement for the harness service.

Provides FastAPI dependency functions that enforce membership and role checks
on space-scoped endpoints.  The ``SPACE_ACL_MODE`` environment variable
(surfaced via
:pydata:`~artana_evidence_api.config.GraphHarnessServiceSettings.space_acl_mode`)
controls whether violations are **logged** (``audit``) or **blocked**
(``enforce``).

Role hierarchy (highest to lowest): ``owner`` > ``admin`` > ``curator`` >
``researcher`` > ``viewer``.
"""

from __future__ import annotations

import logging
from enum import Enum
from uuid import UUID

from artana_evidence_api.auth import HarnessUser, HarnessUserRole
from artana_evidence_api.config import get_settings
from artana_evidence_api.research_space_store import HarnessResearchSpaceStore
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Role hierarchy – lower index means higher privilege
# ---------------------------------------------------------------------------

_ROLE_HIERARCHY: list[str] = [
    "owner",
    "admin",
    "curator",
    "researcher",
    "viewer",
]


class SpaceRole(str, Enum):
    """Logical space-level roles used by ACL checks."""

    OWNER = "owner"
    ADMIN = "admin"
    CURATOR = "curator"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


def _role_rank(role: str) -> int:
    """Return the rank of a role (lower is more privileged)."""
    try:
        return _ROLE_HIERARCHY.index(role.lower())
    except ValueError:
        return len(_ROLE_HIERARCHY)


def role_at_least(actual_role: str, minimum_role: str) -> bool:
    """Return ``True`` when *actual_role* is at least as privileged as
    *minimum_role*."""
    return _role_rank(actual_role) <= _role_rank(minimum_role)


# ---------------------------------------------------------------------------
# ACL mode helpers
# ---------------------------------------------------------------------------


def _is_enforce_mode() -> bool:
    return get_settings().space_acl_mode == "enforce"


def _is_service_user(user: HarnessUser) -> bool:
    return user.role == HarnessUserRole.SERVICE


# ---------------------------------------------------------------------------
# Core check
# ---------------------------------------------------------------------------


def check_space_access(
    *,
    space_id: UUID,
    current_user: HarnessUser,
    research_space_store: HarnessResearchSpaceStore,
    minimum_role: str = "viewer",
) -> HarnessUser:
    """Verify the caller has at least *minimum_role* on the given space.

    In ``audit`` mode violations are logged but the request proceeds.
    In ``enforce`` mode violations raise 403.

    Service users (``role == "service"``) bypass all checks.
    Platform admins (``role == "admin"``) bypass all checks.
    """
    if _is_service_user(current_user):
        return current_user

    if current_user.role == HarnessUserRole.ADMIN:
        return current_user

    record = research_space_store.get_space(
        space_id=space_id,
        user_id=current_user.id,
        is_admin=False,
    )

    violation: str | None = None
    if record is None:
        violation = f"User {current_user.id} has no membership in space {space_id}"
    elif not role_at_least(record.role, minimum_role):
        violation = (
            f"User {current_user.id} has role '{record.role}' in space "
            f"{space_id} but '{minimum_role}' or higher is required"
        )

    if violation is not None:
        logger.warning("Space ACL violation: %s", violation)
        if _is_enforce_mode():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=violation,
            )

    return current_user


__all__ = [
    "SpaceRole",
    "check_space_access",
    "role_at_least",
]
