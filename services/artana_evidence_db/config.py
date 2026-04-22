"""Service-local startup configuration for the standalone graph service."""

from __future__ import annotations

import os
from dataclasses import dataclass

from artana_evidence_db.runtime.pack_registry import resolve_graph_domain_pack
from artana_evidence_db.schema_support import resolve_graph_db_schema

_DEFAULT_GRAPH_JWT_SECRET = (
    "artana-platform-dev-jwt-secret-for-development-2026-01"  # noqa: S105
)
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class GraphServiceSettings:
    """Configuration values used by the graph service runtime."""

    app_name: str
    database_url: str
    database_schema: str
    host: str
    port: int
    reload: bool
    jwt_secret: str
    jwt_algorithm: str
    jwt_issuer: str
    allow_test_auth_headers: bool


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        message = f"{name} is required for the standalone graph service runtime"
        raise RuntimeError(message)
    return value.strip()


def _bool_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _resolve_graph_jwt_secret() -> str:
    graph_secret = os.getenv("GRAPH_JWT_SECRET")
    if isinstance(graph_secret, str) and graph_secret.strip():
        return graph_secret.strip()
    return _DEFAULT_GRAPH_JWT_SECRET


def get_settings() -> GraphServiceSettings:
    """Resolve graph service settings from environment variables."""
    database_url = _require_env("GRAPH_DATABASE_URL")
    graph_domain_pack = resolve_graph_domain_pack()
    return GraphServiceSettings(
        app_name=os.getenv(
            "GRAPH_SERVICE_NAME",
            graph_domain_pack.runtime_identity.service_name,
        ).strip()
        or graph_domain_pack.runtime_identity.service_name,
        database_url=database_url,
        database_schema=resolve_graph_db_schema(),
        host=os.getenv("GRAPH_SERVICE_HOST", "0.0.0.0"),  # noqa: S104
        port=int(os.getenv("GRAPH_SERVICE_PORT", "8090")),
        reload=_bool_env("GRAPH_SERVICE_RELOAD", default=False),
        jwt_secret=_resolve_graph_jwt_secret(),
        jwt_algorithm=os.getenv("GRAPH_JWT_ALGORITHM", "HS256"),
        jwt_issuer=os.getenv(
            "GRAPH_JWT_ISSUER",
            graph_domain_pack.runtime_identity.jwt_issuer,
        ).strip()
        or graph_domain_pack.runtime_identity.jwt_issuer,
        allow_test_auth_headers=(
            os.getenv("TESTING") == "true"
            or _bool_env("GRAPH_ALLOW_TEST_AUTH_HEADERS", default=False)
        ),
    )


__all__ = ["GraphServiceSettings", "_require_env", "get_settings"]
