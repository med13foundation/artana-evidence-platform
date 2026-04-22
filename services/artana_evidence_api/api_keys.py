"""Helpers for persisted Artana API key issuance and verification."""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from artana_evidence_api.models.api_key import HarnessApiKeyModel
from artana_evidence_api.models.user import HarnessUserModel
from sqlalchemy import select
from sqlalchemy.orm import Session

API_KEY_PREFIX = "art_sk_"
API_KEY_ACTIVE_STATUS = "active"
API_KEY_REVOKED_STATUS = "revoked"
BOOTSTRAP_KEY_HEADER = "X-Artana-Bootstrap-Key"
BOOTSTRAP_KEY_ENV = "ARTANA_EVIDENCE_API_BOOTSTRAP_KEY"


@dataclass(frozen=True, slots=True)
class IssuedApiKey:
    """One newly issued API key plus its persisted model."""

    raw_key: str
    model: HarnessApiKeyModel


def generate_api_key() -> str:
    """Generate one opaque Artana API key."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    """Hash one API key for durable lookup."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def key_prefix(raw_key: str) -> str:
    """Return one short display prefix for a raw API key."""
    return raw_key[:16]


def resolve_bootstrap_key() -> str | None:
    """Return the configured bootstrap secret for self-hosted setup."""
    configured = os.getenv(BOOTSTRAP_KEY_ENV)
    if configured is None:
        return None
    normalized = configured.strip()
    return normalized or None


def _build_api_key_model(
    *,
    user_id: UUID | str,
    name: str,
    description: str,
    raw_key: str,
) -> HarnessApiKeyModel:
    return HarnessApiKeyModel(
        user_id=UUID(str(user_id)),
        name=name.strip() or "Default SDK Key",
        description=description.strip(),
        key_prefix=key_prefix(raw_key),
        key_hash=hash_api_key(raw_key),
        status=API_KEY_ACTIVE_STATUS,
        last_used_at=None,
        expires_at=None,
        revoked_at=None,
    )


def issue_api_key(
    session: Session,
    *,
    user_id: UUID | str,
    name: str,
    description: str = "",
) -> IssuedApiKey:
    """Create and persist one new API key for a user."""
    raw_key = generate_api_key()
    model = _build_api_key_model(
        user_id=user_id,
        name=name,
        description=description,
        raw_key=raw_key,
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return IssuedApiKey(raw_key=raw_key, model=model)


def resolve_user_from_api_key(
    session: Session,
    *,
    raw_key: str,
) -> HarnessUserModel | None:
    """Resolve the active user bound to one raw API key."""
    normalized_key = raw_key.strip()
    if normalized_key == "":
        return None
    now = datetime.now(UTC)
    api_key_model = (
        session.execute(
            select(HarnessApiKeyModel).where(
                HarnessApiKeyModel.key_hash == hash_api_key(normalized_key),
                HarnessApiKeyModel.status == API_KEY_ACTIVE_STATUS,
            ),
        )
        .scalars()
        .first()
    )
    if api_key_model is None:
        return None
    if api_key_model.revoked_at is not None:
        return None
    if (
        api_key_model.expires_at is not None
        and api_key_model.expires_at.replace(tzinfo=UTC) <= now
    ):
        return None
    return session.get(HarnessUserModel, api_key_model.user_id)


def list_api_keys_for_user(
    session: Session,
    *,
    user_id: UUID | str,
) -> list[HarnessApiKeyModel]:
    """Return all API keys belonging to one user, newest first."""
    return list(
        session.execute(
            select(HarnessApiKeyModel)
            .where(HarnessApiKeyModel.user_id == UUID(str(user_id)))
            .order_by(HarnessApiKeyModel.created_at.desc()),
        )
        .scalars()
        .all(),
    )


def revoke_api_key(
    session: Session,
    *,
    key_id: UUID | str,
    user_id: UUID | str,
) -> HarnessApiKeyModel | None:
    """Soft-revoke one API key. Returns the model or None if not found."""
    model = (
        session.execute(
            select(HarnessApiKeyModel).where(
                HarnessApiKeyModel.id == UUID(str(key_id)),
                HarnessApiKeyModel.user_id == UUID(str(user_id)),
            ),
        )
        .scalars()
        .first()
    )
    if model is None:
        return None
    if model.status == API_KEY_REVOKED_STATUS:
        return None
    model.status = API_KEY_REVOKED_STATUS
    model.revoked_at = datetime.now(UTC)
    session.commit()
    session.refresh(model)
    return model


def rotate_api_key(
    session: Session,
    *,
    key_id: UUID | str,
    user_id: UUID | str,
) -> IssuedApiKey | None:
    """Revoke one key and atomically issue a replacement. Returns the new key or None."""
    old_model = (
        session.execute(
            select(HarnessApiKeyModel).where(
                HarnessApiKeyModel.id == UUID(str(key_id)),
                HarnessApiKeyModel.user_id == UUID(str(user_id)),
                HarnessApiKeyModel.status == API_KEY_ACTIVE_STATUS,
            ),
        )
        .scalars()
        .first()
    )
    if old_model is None:
        return None
    old_model.status = API_KEY_REVOKED_STATUS
    old_model.revoked_at = datetime.now(UTC)
    raw_key = generate_api_key()
    new_model = _build_api_key_model(
        user_id=user_id,
        name=old_model.name,
        description=old_model.description or "",
        raw_key=raw_key,
    )
    session.add(new_model)
    try:
        session.commit()
        session.refresh(old_model)
        session.refresh(new_model)
    except Exception:
        session.rollback()
        raise
    return IssuedApiKey(raw_key=raw_key, model=new_model)


__all__ = [
    "API_KEY_ACTIVE_STATUS",
    "API_KEY_PREFIX",
    "API_KEY_REVOKED_STATUS",
    "BOOTSTRAP_KEY_ENV",
    "BOOTSTRAP_KEY_HEADER",
    "IssuedApiKey",
    "generate_api_key",
    "hash_api_key",
    "issue_api_key",
    "key_prefix",
    "list_api_keys_for_user",
    "resolve_bootstrap_key",
    "resolve_user_from_api_key",
    "revoke_api_key",
    "rotate_api_key",
]
