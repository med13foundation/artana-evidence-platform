"""Authentication helpers for the standalone harness service.

Platform roles carried by tokens and API keys are intentionally separate from
research-space membership checks. ``owner`` satisfies the general write gate,
but access to a specific space is still checked by the space ACL layer.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from enum import Enum
from uuid import UUID

import jwt
from artana_evidence_api.database import get_session
from artana_evidence_api.identity.contracts import (
    IdentityUserConflictError,
    IdentityUserRecord,
)
from artana_evidence_api.identity.local_gateway import LocalIdentityGateway
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_AUTH_JWT_SECRET_ENV = "AUTH_JWT_SECRET"
_AUTH_ALLOW_TEST_HEADERS_ENV = "AUTH_ALLOW_TEST_AUTH_HEADERS"
_PRODUCTION_LIKE_ENVS = frozenset({"production", "staging"})
_FALLBACK_DEV_JWT_SECRET = "artana-platform-dev-jwt-secret-change-in-production-2026-01"
_TOKEN_ISSUER = "artana-platform"
_TOKEN_ALGORITHM = "HS256"
_UNKNOWN_ROLE_LOG_VALUE_MAX_LENGTH = 64
# Owner is write-equivalent for harness actions, not admin-equivalent.
_WRITE_ROLES = frozenset(
    {
        "admin",
        "owner",
        "curator",
        "researcher",
    },
)
security = HTTPBearer(auto_error=False)
api_key_security = APIKeyHeader(name="X-Artana-Key", auto_error=False)


class HarnessUserStatus(str, Enum):
    """Account status values accepted by the harness service."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class HarnessUserRole(str, Enum):
    """Role values used by harness authorization checks."""

    ADMIN = "admin"
    OWNER = "owner"
    CURATOR = "curator"
    RESEARCHER = "researcher"
    VIEWER = "viewer"
    SERVICE = "service"


class HarnessUser(BaseModel):
    """Minimal authenticated user shape owned by the harness service."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    email: EmailStr
    username: str = Field(min_length=1, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    role: HarnessUserRole
    status: HarnessUserStatus

    def can_authenticate(self) -> bool:
        """Return whether the current user is allowed to use the harness."""
        return self.status == HarnessUserStatus.ACTIVE


def _environment() -> str:
    return os.getenv("ARTANA_ENV", "development").strip().lower()


def _is_truthy(value: str | None) -> bool:
    return isinstance(value, str) and value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _allow_test_auth_headers() -> bool:
    return os.getenv("TESTING") == "true" or _is_truthy(
        os.getenv(_AUTH_ALLOW_TEST_HEADERS_ENV),
    )


def _resolve_jwt_secret() -> str:
    configured_secret = os.getenv(_AUTH_JWT_SECRET_ENV)
    if configured_secret:
        return configured_secret
    if _environment() in _PRODUCTION_LIKE_ENVS:
        message = f"{_AUTH_JWT_SECRET_ENV} must be set when ARTANA_ENV is production or staging."
        raise RuntimeError(message)
    return _FALLBACK_DEV_JWT_SECRET


def _unknown_role_log_value(role_value: object) -> str:
    if not isinstance(role_value, str):
        return type(role_value).__name__
    normalized = role_value.strip().lower()
    if len(normalized) <= _UNKNOWN_ROLE_LOG_VALUE_MAX_LENGTH:
        return normalized
    return f"{normalized[:_UNKNOWN_ROLE_LOG_VALUE_MAX_LENGTH]}..."


def _log_unknown_role(role_value: object, *, context: str | None) -> None:
    if role_value is None:
        return
    logger.warning(
        "Unknown harness platform role %r from %s; falling back to viewer",
        _unknown_role_log_value(role_value),
        context or "unknown auth context",
    )


def _parse_role(
    role_value: object,
    *,
    context: str | None = None,
) -> HarnessUserRole:
    if isinstance(role_value, str):
        normalized = role_value.strip().lower()
        try:
            return HarnessUserRole(normalized)
        except ValueError:
            _log_unknown_role(role_value, context=context)
            return HarnessUserRole.VIEWER
    _log_unknown_role(role_value, context=context)
    return HarnessUserRole.VIEWER


def _parse_status(status_value: object) -> HarnessUserStatus:
    if isinstance(status_value, str):
        normalized = status_value.strip().lower()
        try:
            return HarnessUserStatus(normalized)
        except ValueError:
            return HarnessUserStatus.ACTIVE
    return HarnessUserStatus.ACTIVE


def _parse_user_id(user_id_value: object) -> UUID:
    if not isinstance(user_id_value, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return UUID(user_id_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def _build_harness_user(
    *,
    user_id: UUID,
    role: HarnessUserRole,
    email: str | None = None,
    username: str | None = None,
    full_name: str | None = None,
    status_value: object = HarnessUserStatus.ACTIVE.value,
) -> HarnessUser:
    resolved_email = (
        email.strip()
        if isinstance(email, str) and email.strip()
        else f"{user_id}@graph-harness.example.com"
    )
    resolved_username = (
        username.strip()
        if isinstance(username, str) and username.strip()
        else resolved_email.split("@", maxsplit=1)[0]
    )
    resolved_full_name = (
        full_name.strip()
        if isinstance(full_name, str) and full_name.strip()
        else resolved_email
    )
    return HarnessUser(
        id=user_id,
        email=resolved_email,
        username=resolved_username,
        full_name=resolved_full_name,
        role=role,
        status=_parse_status(status_value),
    )


def _identity_record_from_harness_user(user: HarnessUser) -> IdentityUserRecord:
    return IdentityUserRecord(
        id=user.id,
        email=str(user.email),
        username=user.username,
        full_name=user.full_name,
        role=user.role.value,
        status=user.status.value,
    )


def _build_harness_user_from_identity(record: IdentityUserRecord) -> HarnessUser:
    return _build_harness_user(
        user_id=record.id,
        role=_parse_role(record.role, context=f"identity user {record.id}"),
        email=record.email,
        username=record.username,
        full_name=record.full_name,
        status_value=record.status,
    )


def _build_user_from_test_headers(request: Request) -> HarnessUser | None:
    if not _allow_test_auth_headers():
        return None
    test_user_id = request.headers.get("X-TEST-USER-ID")
    test_user_email = request.headers.get("X-TEST-USER-EMAIL")
    if not test_user_id or not test_user_email:
        return None
    parsed_user_id = _parse_user_id(test_user_id)
    return _build_harness_user(
        user_id=parsed_user_id,
        email=test_user_email,
        username=test_user_email.split("@", maxsplit=1)[0],
        full_name=test_user_email,
        role=_parse_role(
            request.headers.get("X-TEST-USER-ROLE"),
            context=f"test headers subject {parsed_user_id}",
        ),
    )


def _canonicalize_shared_harness_user(
    session: Session,
    *,
    user: HarnessUser,
) -> HarnessUser:
    """Reuse the local identity row when claims describe an existing identity."""
    try:
        identity_user = LocalIdentityGateway(session=session).canonicalize_user_claims(
            _identity_record_from_harness_user(user),
        )
    except IdentityUserConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return _build_harness_user_from_identity(identity_user)


def _decode_access_token(token: str) -> Mapping[str, object]:
    try:
        payload = jwt.decode(
            token,
            _resolve_jwt_secret(),
            algorithms=[_TOKEN_ALGORITHM],
            issuer=_TOKEN_ISSUER,
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidIssuerError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token issuer",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc!s}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not isinstance(payload, Mapping):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_current_harness_user(
    request: Request,
    api_key: str | None = Depends(api_key_security),
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: Session = Depends(get_session),
) -> HarnessUser:
    """Return the authenticated harness caller from test headers, API key, or JWT."""
    test_user = _build_user_from_test_headers(request)
    if test_user is not None:
        return test_user

    if credentials is not None:
        payload = _decode_access_token(credentials.credentials)
        user_id = _parse_user_id(payload.get("sub"))
        email = payload.get("email")
        username = payload.get("username")
        full_name = payload.get("full_name")
        return _canonicalize_shared_harness_user(
            session,
            user=_build_harness_user(
                user_id=user_id,
                role=_parse_role(
                    payload.get("role"),
                    context=f"access token subject {user_id}",
                ),
                email=email if isinstance(email, str) else None,
                username=username if isinstance(username, str) else None,
                full_name=full_name if isinstance(full_name, str) else None,
                status_value=payload.get("status"),
            ),
        )

    if isinstance(api_key, str) and api_key.strip() != "":
        api_key_user = LocalIdentityGateway(session=session).resolve_api_key(api_key)
        if api_key_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "APIKey"},
            )
        return _build_harness_user_from_identity(api_key_user)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


_CURRENT_HARNESS_USER_DEPENDENCY = Depends(get_current_harness_user)


def require_harness_read_access(
    current_user: HarnessUser = _CURRENT_HARNESS_USER_DEPENDENCY,
) -> HarnessUser:
    """Require authenticated active access for harness read endpoints."""
    if not current_user.can_authenticate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    return current_user


def require_harness_write_access(
    current_user: HarnessUser = _CURRENT_HARNESS_USER_DEPENDENCY,
) -> HarnessUser:
    """Require researcher-or-higher access for harness mutations."""
    if not current_user.can_authenticate():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    if current_user.role.value not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner, researcher, curator, or admin role required",
        )
    return current_user


__all__ = [
    "HarnessUser",
    "HarnessUserRole",
    "HarnessUserStatus",
    "get_current_harness_user",
    "require_harness_read_access",
    "require_harness_write_access",
    "security",
]
