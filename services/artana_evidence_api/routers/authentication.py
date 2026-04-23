"""Authentication and API key management endpoints for the harness service."""

from __future__ import annotations

import hmac
from datetime import datetime
from typing import Literal
from uuid import UUID

from artana_evidence_api.api_keys import (
    BOOTSTRAP_KEY_HEADER,
    resolve_bootstrap_key,
)
from artana_evidence_api.auth import (
    HarnessUser,
    HarnessUserRole,
    require_harness_read_access,
    require_harness_write_access,
)
from artana_evidence_api.dependencies import get_identity_gateway
from artana_evidence_api.identity.contracts import (
    IdentityGateway,
    IdentityIssuedApiKey,
    IdentityUserConflictError,
    IdentityUserRecord,
)
from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceRecord,
)
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, EmailStr, Field

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
    def from_identity(cls, record: IdentityUserRecord) -> AuthenticatedUserResponse:
        return cls(
            id=str(record.id),
            email=record.email,
            username=record.username,
            full_name=record.full_name,
            role=record.role,
            status=record.status,
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


class CreateTesterRequest(BaseModel):
    """Create a tester user plus an initial API key."""

    model_config = ConfigDict(strict=True)

    email: EmailStr
    username: str | None = Field(default=None, min_length=1, max_length=50)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Literal["viewer", "researcher", "curator"] = "researcher"
    api_key_name: str = Field(default="Tester SDK Key", min_length=1, max_length=100)
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


def _default_space_response(
    *,
    identity_gateway: IdentityGateway,
    user_id: UUID | str,
) -> AuthResearchSpaceResponse | None:
    default_space = identity_gateway.get_default_space(user_id=user_id)
    if default_space is None:
        return None
    return AuthResearchSpaceResponse.from_record(default_space)


def _issued_api_key_response(raw_response: IdentityIssuedApiKey) -> IssuedApiKeyResponse:
    return IssuedApiKeyResponse(
        id=str(raw_response.record.id),
        name=raw_response.record.name,
        key_prefix=raw_response.record.key_prefix,
        status=raw_response.record.status,
        api_key=raw_response.raw_key,
        created_at=raw_response.record.created_at.isoformat(),
    )


def _credential_response(
    *,
    identity_gateway: IdentityGateway,
    user: IdentityUserRecord,
    issued_key: IdentityIssuedApiKey,
) -> AuthCredentialResponse:
    return AuthCredentialResponse(
        user=AuthenticatedUserResponse.from_identity(user),
        api_key=_issued_api_key_response(issued_key),
        default_space=_default_space_response(
            identity_gateway=identity_gateway,
            user_id=user.id,
        ),
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
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
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
    recovery_user = identity_gateway.bootstrap_recovery_user()
    if identity_gateway.bootstrap_already_completed() and recovery_user is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bootstrap has already been completed for this deployment",
        )

    if recovery_user is not None:
        user = recovery_user
    else:
        normalized_email = str(request.email).strip().lower()
        try:
            user = identity_gateway.create_tester_user(
                email=normalized_email,
                username=_normalize_username(normalized_email, request.username),
                full_name=_normalize_full_name(normalized_email, request.full_name),
                role=request.role,
            )
        except IdentityUserConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(exc),
            ) from exc
    if request.create_default_space:
        identity_gateway.ensure_default_space(owner=user)
    issued_key = identity_gateway.issue_api_key(
        user_id=user.id,
        name=request.api_key_name,
        description=request.api_key_description,
    )
    return _credential_response(
        identity_gateway=identity_gateway,
        user=user,
        issued_key=issued_key,
    )


@router.post(
    "/testers",
    response_model=AuthCredentialResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tester user and API key",
)
def create_tester(
    request: CreateTesterRequest,
    current_user: HarnessUser = Depends(require_harness_write_access),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> AuthCredentialResponse:
    """Create a low-friction tester identity through the local identity boundary."""
    if current_user.role != HarnessUserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to create tester users",
        )
    normalized_email = str(request.email).strip().lower()
    try:
        user = identity_gateway.create_tester_user(
            email=normalized_email,
            username=_normalize_username(normalized_email, request.username),
            full_name=_normalize_full_name(normalized_email, request.full_name),
            role=request.role,
        )
    except IdentityUserConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if request.create_default_space:
        identity_gateway.ensure_default_space(owner=user)
    issued_key = identity_gateway.issue_api_key(
        user_id=user.id,
        name=request.api_key_name,
        description=request.api_key_description,
    )
    return _credential_response(
        identity_gateway=identity_gateway,
        user=user,
        issued_key=issued_key,
    )


@router.get(
    "/me",
    response_model=AuthContextResponse,
    summary="Resolve the current authenticated identity",
)
def get_auth_context(
    current_user: HarnessUser = Depends(require_harness_read_access),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> AuthContextResponse:
    """Return the authenticated caller and their default space if it exists."""
    return AuthContextResponse(
        user=AuthenticatedUserResponse.from_user(current_user),
        default_space=_default_space_response(
            identity_gateway=identity_gateway,
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
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> AuthCredentialResponse:
    """Issue one additional API key bound to the current user."""
    issued_key = identity_gateway.issue_api_key(
        user_id=current_user.id,
        name=request.name,
        description=request.description,
    )
    return AuthCredentialResponse(
        user=AuthenticatedUserResponse.from_user(current_user),
        api_key=_issued_api_key_response(issued_key),
        default_space=_default_space_response(
            identity_gateway=identity_gateway,
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


def _ts(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


@router.get(
    "/api-keys",
    response_model=ApiKeyListResponse,
    summary="List API keys for the authenticated user",
)
def list_api_keys(
    current_user: HarnessUser = Depends(require_harness_read_access),
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> ApiKeyListResponse:
    """Return all API keys for the caller, showing prefix only."""
    models = identity_gateway.list_api_keys(user_id=current_user.id)
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
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> ApiKeySummaryResponse:
    """Soft-revoke one API key belonging to the caller."""
    model = identity_gateway.revoke_api_key(key_id=key_id, user_id=current_user.id)
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
    identity_gateway: IdentityGateway = Depends(get_identity_gateway),
) -> RotatedApiKeyResponse:
    """Revoke one key and issue a replacement. The new full key is returned once."""
    new_key = identity_gateway.rotate_api_key(key_id=key_id, user_id=current_user.id)
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
    "CreateTesterRequest",
    "IssuedApiKeyResponse",
    "RotatedApiKeyResponse",
    "bootstrap_api_key",
    "create_api_key",
    "create_tester",
    "delete_api_key",
    "get_auth_context",
    "list_api_keys",
    "rotate_api_key_endpoint",
    "router",
]
