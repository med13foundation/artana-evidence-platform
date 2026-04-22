"""Service-to-service auth helpers for graph API calls."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

_DEFAULT_GRAPH_JWT_SECRET = "artana-platform-dev-jwt-secret-for-development-2026-01"
_DEFAULT_GRAPH_SERVICE_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_JWT_ALGORITHM = "HS256"
_DEFAULT_GRAPH_JWT_ISSUER = "graph-biomedical"


def _resolve_graph_jwt_secret() -> str:
    raw_secret = os.getenv("GRAPH_JWT_SECRET")
    if isinstance(raw_secret, str) and raw_secret.strip():
        return raw_secret.strip()
    return _DEFAULT_GRAPH_JWT_SECRET


def _resolve_graph_service_user_id() -> UUID:
    raw_user_id = os.getenv("GRAPH_SERVICE_SERVICE_USER_ID")
    if isinstance(raw_user_id, str) and raw_user_id.strip():
        return UUID(raw_user_id.strip())
    return _DEFAULT_GRAPH_SERVICE_USER_ID


def _resolve_graph_jwt_issuer() -> str:
    raw_issuer = os.getenv("GRAPH_JWT_ISSUER")
    if isinstance(raw_issuer, str) and raw_issuer.strip():
        return raw_issuer.strip()
    return _DEFAULT_GRAPH_JWT_ISSUER


def _resolve_graph_ai_principal() -> str | None:
    raw_principal = os.getenv("GRAPH_SERVICE_AI_PRINCIPAL")
    if isinstance(raw_principal, str) and raw_principal.strip():
        return raw_principal.strip()
    return None


def build_graph_service_bearer_token_for_service(
    *,
    user_id: str | UUID | None = None,
    role: str = "researcher",
    graph_admin: bool = False,
    graph_ai_principal: str | None = None,
    graph_service_capabilities: list[str] | None = None,
    default_graph_ai_principal_from_env: bool = False,
    expires_delta: timedelta | None = None,
) -> str:
    """Mint one graph-service bearer token for harness service calls."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=15)
    issued_at = datetime.now(UTC)
    resolved_user_id = (
        str(user_id)
        if isinstance(user_id, UUID)
        else (
            user_id.strip()
            if isinstance(user_id, str) and user_id.strip()
            else str(_resolve_graph_service_user_id())
        )
    )
    payload = {
        "sub": resolved_user_id,
        "role": role,
        "type": "access",
        "jti": str(uuid4()),
        "exp": issued_at + expires_delta,
        "iat": issued_at,
        "iss": _resolve_graph_jwt_issuer(),
        "graph_admin": graph_admin,
    }
    if graph_service_capabilities:
        payload["graph_service_capabilities"] = [
            capability
            for capability in graph_service_capabilities
            if isinstance(capability, str) and capability.strip()
        ]
    resolved_ai_principal = (
        graph_ai_principal.strip()
        if isinstance(graph_ai_principal, str) and graph_ai_principal.strip()
        else (
            _resolve_graph_ai_principal()
            if default_graph_ai_principal_from_env
            else None
        )
    )
    if resolved_ai_principal is not None:
        payload["graph_ai_principal"] = resolved_ai_principal
    return str(
        jwt.encode(
            payload,
            _resolve_graph_jwt_secret(),
            algorithm=_JWT_ALGORITHM,
        ),
    )


__all__ = ["build_graph_service_bearer_token_for_service"]
