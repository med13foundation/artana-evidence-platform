"""
Utility helpers shared across data discovery repository implementations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

LEGACY_OWNER_ID_THRESHOLD = 1_000


def expand_identifier(
    identifier: UUID | str,
    *,
    allow_legacy_formats: bool = True,
) -> list[str]:
    """Return possible identifier string representations for legacy databases."""

    raw_value = str(identifier)
    if not allow_legacy_formats:
        return [raw_value]

    candidates = {raw_value}
    compact = raw_value.replace("-", "")
    if compact:
        candidates.add(compact)
    return list(candidates)


def owner_identifier_candidates(
    identifier: UUID | str,
    *,
    allow_legacy_formats: bool,
) -> list[str]:
    """Return legacy owner identifiers (UUID, compact UUID, integer fallback)."""

    raw_value = str(identifier)
    if not allow_legacy_formats:
        return [raw_value]

    candidates = {raw_value}
    compact = raw_value.replace("-", "")
    if compact:
        candidates.add(compact)
        stripped = compact.lstrip("0")
        if stripped and stripped.isdigit():
            int_value = int(stripped)
            if int_value < LEGACY_OWNER_ID_THRESHOLD:
                candidates.add(str(int_value))
    return list(candidates)


def dialect_name_for_session(session: Session) -> str:
    """Return the SQL dialect name for a SQLAlchemy session bind."""

    try:
        bind = session.get_bind()
    except RuntimeError:
        return ""
    dialect = getattr(bind, "dialect", None)
    return getattr(dialect, "name", "") or ""


__all__ = [
    "dialect_name_for_session",
    "expand_identifier",
    "owner_identifier_candidates",
]
