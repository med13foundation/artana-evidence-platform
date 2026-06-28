"""Runtime environment helpers owned by the standalone graph service."""

from __future__ import annotations

import os

DEFAULT_GRAPH_JWT_SECRET = "artana-platform-dev-jwt-secret-for-development-2026-01"  # noqa: S105 - development-only fallback for local/runtime tooling
PRODUCTION_LIKE_ENVS = frozenset({"production", "staging"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _is_enabled(value: str | None) -> bool:
    return isinstance(value, str) and value.strip().lower() in _TRUE_VALUES


def _environment() -> str:
    return os.getenv("ARTANA_ENV", "development").strip().lower()


def resolve_graph_jwt_secret() -> str:
    """Resolve the graph JWT secret from the neutral graph env contract."""
    graph_secret = os.getenv("GRAPH_JWT_SECRET")
    if isinstance(graph_secret, str) and graph_secret.strip():
        return graph_secret.strip()

    if _environment() in PRODUCTION_LIKE_ENVS:
        msg = "GRAPH_JWT_SECRET must be set when ARTANA_ENV is production or staging."
        raise RuntimeError(msg)

    return DEFAULT_GRAPH_JWT_SECRET


def allow_graph_test_auth_headers() -> bool:
    """Resolve whether graph test-auth headers are enabled."""
    if _environment() in PRODUCTION_LIKE_ENVS:
        return False
    if os.getenv("TESTING") == "true":
        return True
    return _is_enabled(os.getenv("GRAPH_ALLOW_TEST_AUTH_HEADERS"))


__all__ = [
    "DEFAULT_GRAPH_JWT_SECRET",
    "allow_graph_test_auth_headers",
    "PRODUCTION_LIKE_ENVS",
    "resolve_graph_jwt_secret",
]
