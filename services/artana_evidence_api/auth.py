"""Authentication helpers for the standalone harness service."""

from __future__ import annotations

import os
from collections.abc import Mapping
from enum import Enum
from uuid import UUID

import jwt
from artana_evidence_api.api_keys import resolve_user_from_api_key
from artana_evidence_api.database import get_session
from artana_evidence_api.models.user import HarnessUserModel
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

_AUTH_JWT_SECRET_ENV = "AUTH_JWT_SECRET"
_AUTH_ALLOW_TEST_HEADERS_ENV = "AUTH_ALLOW_TEST_AUTH_HEADERS"
_PRODUCTION_LIKE_ENVS = frozenset({"production", "staging"})
_FALLBACK_DEV_JWT_SECRET = "artana-platform-dev-jwt-secret-change-in-production-2026-01"
_TOKEN_ISSUER = "artana-platform"
_TOKEN_ALGORITHM = "HS256"
_WRITE_ROLES = frozenset(
    {
        "admin",
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
    """Platform role values used by harness authorization checks."""

    ADMIN = "admin"
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


def _parse_role(role_value: object) -> HarnessUserRole:
    if isinstance(role_value, str):
        normalized = role_value.strip().lower()
        try:
            return HarnessUserRole(normalized)
        except ValueError:
            return HarnessUserRole.VIEWER
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


def _build_user_from_test_headers(request: Request) -> HarnessUser | None:
    if not _allow_test_auth_headers():
        return None
    test_user_id = request.headers.get("X-TEST-USER-ID")
    test_user_email = request.headers.get("X-TEST-USER-EMAIL")
    if not test_user_id or not test_user_email:
        return None
    return _build_harness_user(
        user_id=_parse_user_id(test_user_id),
        email=test_user_email,
        username=test_user_email.split("@", maxsplit=1)[0],
        full_name=test_user_email,
        role=_parse_role(request.headers.get("X-TEST-USER-ROLE")),
    )


def _canonicalize_shared_harness_user(
    session: Session,
    *,
    user: HarnessUser,
) -> HarnessUser:
    """Reuse the shared user row when claims describe an existing identity."""
    if not isinstance(session, Session):
        return user
    existing_user = session.get(HarnessUserModel, user.id)
    if existing_user is not None:
        return user

    normalized_email = str(user.email).strip().lower()
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username is already in use",
        )
    return user.model_copy(
        update={
            "id": _parse_user_id(str(identity_match.id)),
            "email": identity_match.email,
            "username": identity_match.username,
            "full_name": identity_match.full_name,
        },
    )


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
                role=_parse_role(payload.get("role")),
                email=email if isinstance(email, str) else None,
                username=username if isinstance(username, str) else None,
                full_name=full_name if isinstance(full_name, str) else None,
                status_value=payload.get("status"),
            ),
        )

    if isinstance(api_key, str) and api_key.strip() != "":
        api_key_user = resolve_user_from_api_key(
            session,
            raw_key=api_key,
        )
        if api_key_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
                headers={"WWW-Authenticate": "APIKey"},
            )
        return _build_harness_user(
            user_id=_parse_user_id(str(api_key_user.id)),
            role=_parse_role(api_key_user.role),
            email=api_key_user.email,
            username=api_key_user.username,
            full_name=api_key_user.full_name,
            status_value=api_key_user.status,
        )

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
            detail="Researcher, curator, or admin role required",
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
