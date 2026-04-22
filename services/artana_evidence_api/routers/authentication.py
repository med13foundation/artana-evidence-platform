"""Authentication and API key management endpoints for the harness service."""

from __future__ import annotations

import hmac
from typing import Literal
from uuid import UUID, uuid4

from artana_evidence_api.api_keys import (
    BOOTSTRAP_KEY_HEADER,
    issue_api_key,
    list_api_keys_for_user,
    resolve_bootstrap_key,
    revoke_api_key,
    rotate_api_key,
)
from artana_evidence_api.auth import HarnessUser, require_harness_read_access
from artana_evidence_api.database import get_session
from artana_evidence_api.dependencies import get_research_space_store
from artana_evidence_api.models.api_key import HarnessApiKeyModel
from artana_evidence_api.models.user import HarnessUserModel
from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceRecord,
    HarnessResearchSpaceStore,
)
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/v1/auth",
    tags=["auth"],
)
_BOOTSTRAP_KEY_SECURITY = APIKeyHeader(
    name=BOOTSTRAP_KEY_HEADER,
    auto_error=False,
    scheme_name="BootstrapAPIKeyHeader",
    description="Bootstrap API key required to create the initial self-hosted user.",
)


class AuthenticatedUserResponse(BaseModel):
    """Serialized authenticated user identity."""

    model_config = ConfigDict(strict=True)

    id: str
    email: str
    username: str
    full_name: str
    role: str
    status: str

    @classmethod
    def from_model(cls, model: HarnessUserModel) -> AuthenticatedUserResponse:
        return cls(
            id=str(model.id),
            email=model.email,
            username=model.username,
            full_name=model.full_name,
            role=model.role,
            status=model.status,
        )

    @classmethod
    def from_user(cls, user: HarnessUser) -> AuthenticatedUserResponse:
        return cls(
            id=str(user.id),
            email=str(user.email),
            username=user.username,
            full_name=user.full_name,
            role=user.role.value,
            status=user.status.value,
        )


class AuthResearchSpaceResponse(BaseModel):
    """Serialized default-space response embedded in auth routes."""

    model_config = ConfigDict(strict=True)

    id: str
    slug: str
    name: str
    description: str
    status: str
    role: str
    is_default: bool = False

    @classmethod
    def from_record(
        cls,
        record: HarnessResearchSpaceRecord,
    ) -> AuthResearchSpaceResponse:
        return cls(
            id=record.id,
            slug=record.slug,
            name=record.name,
            description=record.description,
            status=record.status,
            role=record.role,
            is_default=record.is_default,
        )


class IssuedApiKeyResponse(BaseModel):
    """One newly issued API key returned exactly once."""

    model_config = ConfigDict(strict=True)

    id: str
    name: str
    key_prefix: str
    status: str
    api_key: str
    created_at: str


class AuthContextResponse(BaseModel):
    """Current authenticated user plus their default space if present."""

    model_config = ConfigDict(strict=True)

    user: AuthenticatedUserResponse
    default_space: AuthResearchSpaceResponse | None = None


class AuthCredentialResponse(BaseModel):
    """Current user plus one newly issued API key."""

    model_config = ConfigDict(strict=True)

    user: AuthenticatedUserResponse
    api_key: IssuedApiKeyResponse
    default_space: AuthResearchSpaceResponse | None = None


class BootstrapApiKeyRequest(BaseModel):
    """Bootstrap one self-hosted user plus an initial SDK API key."""

    model_config = ConfigDict(strict=True)

    email: EmailStr
    username: str | None = Field(default=None, min_length=1, max_length=50)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["viewer", "researcher", "curator", "admin"] = "researcher"
    api_key_name: str = Field(default="Default SDK Key", min_length=1, max_length=100)
    api_key_description: str = Field(default="", max_length=500)
    create_default_space: bool = True


class CreateApiKeyRequest(BaseModel):
    """Create one additional API key for the authenticated user."""

    model_config = ConfigDict(strict=True)

    name: str = Field(default="Default SDK Key", min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)


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


def _create_user(
    session: Session,
    *,
    email: str,
    username: str,
    full_name: str,
    role: str,
) -> HarnessUserModel:
    existing_user = (
        session.execute(
            select(HarnessUserModel).where(
                or_(
                    HarnessUserModel.email == email,
                    HarnessUserModel.username == username,
                ),
            ),
        )
        .scalars()
        .first()
    )
    if existing_user is not None:
        if existing_user.email != email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username is already in use",
            )
        return existing_user

    user = HarnessUserModel(
        id=uuid4(),
        email=email,
        username=username,
        full_name=full_name,
        hashed_password="external-auth-not-applicable",
        role=role,
        status="active",
        email_verified=True,
        login_attempts=0,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _bootstrap_already_completed(session: Session) -> bool:
    """Return whether bootstrap should remain locked for this deployment."""
    if _bootstrap_recovery_user(session) is not None:
        return False
    existing_user_id = session.execute(
        select(HarnessUserModel.id).limit(1),
    ).scalar_one_or_none()
    return existing_user_id is not None


def _bootstrap_recovery_user(session: Session) -> HarnessUserModel | None:
    """Return the lone user eligible for bootstrap key recovery, if any."""
    existing_users = (
        session.execute(
            select(HarnessUserModel).limit(2),
        )
        .scalars()
        .all()
    )
    if len(existing_users) != 1:
        return None
    existing_key_id = session.execute(
        select(HarnessApiKeyModel.id).limit(1),
    ).scalar_one_or_none()
    if existing_key_id is not None:
        return None
    return existing_users[0]


def _default_space_response(
    *,
    research_space_store: HarnessResearchSpaceStore,
    user_id: UUID | str,
) -> AuthResearchSpaceResponse | None:
    default_space = research_space_store.get_default_space(user_id=user_id)
    if default_space is None:
        return None
    return AuthResearchSpaceResponse.from_record(default_space)


def _issued_api_key_response(raw_response) -> IssuedApiKeyResponse:
    return IssuedApiKeyResponse(
        id=str(raw_response.model.id),
        name=raw_response.model.name,
        key_prefix=raw_response.model.key_prefix,
        status=raw_response.model.status,
        api_key=raw_response.raw_key,
        created_at=raw_response.model.created_at.isoformat(),
    )


@router.post(
    "/bootstrap",
    response_model=AuthCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Bootstrap one self-hosted user and initial API key",
)
def bootstrap_api_key(
    request: BootstrapApiKeyRequest,
    bootstrap_key: str | None = Security(_BOOTSTRAP_KEY_SECURITY),
    session: Session = Depends(get_session),
    research_space_store: HarnessResearchSpaceStore = Depends(get_research_space_store),
) -> AuthCredentialResponse:
    """Create or reuse one user and issue an initial Artana API key."""
    configured_bootstrap_key = resolve_bootstrap_key()
    if configured_bootstrap_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Bootstrap API key provisioning is not enabled",
        )
    if bootstrap_key is None or not hmac.compare_digest(
        bootstrap_key.strip(),
        configured_bootstrap_key,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bootstrap key",
            headers={"WWW-Authenticate": "APIKey"},
        )
    recovery_user = _bootstrap_recovery_user(session)
    if _bootstrap_already_completed(session) and recovery_user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bootstrap has already been completed for this deployment",
        )

    if recovery_user is not None:
        user = recovery_user
    else:
        normalized_email = str(request.email).strip().lower()
        user = _create_user(
            session,
            email=normalized_email,
            username=_normalize_username(normalized_email, request.username),
            full_name=_normalize_full_name(normalized_email, request.full_name),
            role=request.role,
        )
    if request.create_default_space:
        research_space_store.ensure_default_space(
            owner_id=user.id,
            owner_email=user.email,
            owner_username=user.username,
            owner_full_name=user.full_name,
            owner_role=user.role,
            owner_status=user.status,
        )
    issued_key = issue_api_key(
        session,
        user_id=user.id,
        name=request.api_key_name,
        description=request.api_key_description,
    )
    return AuthCredentialResponse(
        user=AuthenticatedUserResponse.from_model(user),
        api_key=_issued_api_key_response(issued_key),
        default_space=_default_space_response(
            research_space_store=research_space_store,
            user_id=user.id,
        ),
    )


@router.get(
    "/me",
    response_model=AuthContextResponse,
    summary="Resolve the current authenticated identity",
)
def get_auth_context(
    current_user: HarnessUser = Depends(require_harness_read_access),
    research_space_store: HarnessResearchSpaceStore = Depends(get_research_space_store),
) -> AuthContextResponse:
    """Return the authenticated caller and their default space if it exists."""
    return AuthContextResponse(
        user=AuthenticatedUserResponse.from_user(current_user),
        default_space=_default_space_response(
            research_space_store=research_space_store,
            user_id=current_user.id,
        ),
    )


@router.post(
    "/api-keys",
    response_model=AuthCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an additional API key for the authenticated user",
)
def create_api_key(
    request: CreateApiKeyRequest,
    current_user: HarnessUser = Depends(require_harness_read_access),
    session: Session = Depends(get_session),
    research_space_store: HarnessResearchSpaceStore = Depends(get_research_space_store),
) -> AuthCredentialResponse:
    """Issue one additional API key bound to the current user."""
    issued_key = issue_api_key(
        session,
        user_id=current_user.id,
        name=request.name,
        description=request.description,
    )
    return AuthCredentialResponse(
        user=AuthenticatedUserResponse.from_user(current_user),
        api_key=_issued_api_key_response(issued_key),
        default_space=_default_space_response(
            research_space_store=research_space_store,
            user_id=current_user.id,
        ),
    )


# ---------------------------------------------------------------------------
# API key management (list, revoke, rotate)
# ---------------------------------------------------------------------------


class ApiKeySummaryResponse(BaseModel):
    """One API key summary — never exposes the full key."""

    model_config = ConfigDict(strict=True)

    id: str
    name: str
    key_prefix: str
    status: str
    created_at: str
    expires_at: str | None = None
    revoked_at: str | None = None
    last_used_at: str | None = None


class ApiKeyListResponse(BaseModel):
    """Paginated list of API key summaries."""

    model_config = ConfigDict(strict=True)

    keys: list[ApiKeySummaryResponse]
    total: int


class RotatedApiKeyResponse(BaseModel):
    """Response after rotating an API key — includes the new full key once."""

    model_config = ConfigDict(strict=True)

    revoked_key_id: str
    new_key: IssuedApiKeyResponse


def _ts(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


@router.get(
    "/api-keys",
    response_model=ApiKeyListResponse,
    summary="List API keys for the authenticated user",
)
def list_api_keys(
    current_user: HarnessUser = Depends(require_harness_read_access),
    session: Session = Depends(get_session),
) -> ApiKeyListResponse:
    """Return all API keys for the caller, showing prefix only."""
    models = list_api_keys_for_user(session, user_id=current_user.id)
    return ApiKeyListResponse(
        keys=[
            ApiKeySummaryResponse(
                id=str(m.id),
                name=m.name,
                key_prefix=m.key_prefix,
                status=m.status,
                created_at=m.created_at.isoformat(),
                expires_at=_ts(m.expires_at),
                revoked_at=_ts(m.revoked_at),
                last_used_at=_ts(m.last_used_at),
            )
            for m in models
        ],
        total=len(models),
    )


@router.delete(
    "/api-keys/{key_id}",
    response_model=ApiKeySummaryResponse,
    summary="Revoke an API key",
)
def delete_api_key(
    key_id: UUID,
    current_user: HarnessUser = Depends(require_harness_read_access),
    session: Session = Depends(get_session),
) -> ApiKeySummaryResponse:
    """Soft-revoke one API key belonging to the caller."""
    model = revoke_api_key(session, key_id=key_id, user_id=current_user.id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked",
        )
    return ApiKeySummaryResponse(
        id=str(model.id),
        name=model.name,
        key_prefix=model.key_prefix,
        status=model.status,
        created_at=model.created_at.isoformat(),
        expires_at=_ts(model.expires_at),
        revoked_at=_ts(model.revoked_at),
        last_used_at=_ts(model.last_used_at),
    )


@router.post(
    "/api-keys/{key_id}/rotate",
    response_model=RotatedApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Rotate an API key",
)
def rotate_api_key_endpoint(
    key_id: UUID,
    current_user: HarnessUser = Depends(require_harness_read_access),
    session: Session = Depends(get_session),
) -> RotatedApiKeyResponse:
    """Revoke one key and issue a replacement. The new full key is returned once."""
    new_key = rotate_api_key(session, key_id=key_id, user_id=current_user.id)
    if new_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found or already revoked",
        )
    return RotatedApiKeyResponse(
        revoked_key_id=str(key_id),
        new_key=_issued_api_key_response(new_key),
    )


__all__ = [
    "ApiKeyListResponse",
    "ApiKeySummaryResponse",
    "AuthContextResponse",
    "AuthCredentialResponse",
    "AuthenticatedUserResponse",
    "BootstrapApiKeyRequest",
    "CreateApiKeyRequest",
    "IssuedApiKeyResponse",
    "RotatedApiKeyResponse",
    "bootstrap_api_key",
    "create_api_key",
    "delete_api_key",
    "get_auth_context",
    "list_api_keys",
    "rotate_api_key_endpoint",
    "router",
]
