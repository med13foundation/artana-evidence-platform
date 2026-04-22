"""Shared runtime env resolution for platform authentication settings."""

from __future__ import annotations

import os

AUTH_JWT_SECRET_ENV = "AUTH_JWT_SECRET"  # noqa: S105 - env var name, not a secret value
GRAPH_JWT_SECRET_ENV = (
    "GRAPH_JWT_SECRET"  # noqa: S105 - env var name, not a secret value
)
AUTH_ALLOW_TEST_HEADERS_ENV = "AUTH_ALLOW_TEST_AUTH_HEADERS"
AUTH_BYPASS_JWT_FOR_TESTS_ENV = "AUTH_BYPASS_JWT_FOR_TESTS"
_PRODUCTION_LIKE_ENVS = frozenset({"production", "staging"})
_FALLBACK_DEV_JWT_SIGNING_MATERIAL = (
    "artana-resource-library-dev-jwt-secret-change-in-production-2026-01"
)
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def _environment() -> str:
    return os.getenv("ARTANA_ENV", "development").lower()


def _is_enabled(value: str | None) -> bool:
    return isinstance(value, str) and value.strip().lower() in _TRUE_VALUES


def resolve_auth_jwt_secret() -> str:
    configured_secret = os.getenv(AUTH_JWT_SECRET_ENV)
    if configured_secret:
        return configured_secret
    configured_graph_secret = os.getenv(GRAPH_JWT_SECRET_ENV)
    if configured_graph_secret and _environment() not in _PRODUCTION_LIKE_ENVS:
        return configured_graph_secret
    if _environment() in _PRODUCTION_LIKE_ENVS:
        message = f"{AUTH_JWT_SECRET_ENV} must be set when ARTANA_ENV is production or staging."
        raise RuntimeError(message)
    return _FALLBACK_DEV_JWT_SIGNING_MATERIAL


def using_fallback_auth_jwt_secret() -> bool:
    return (
        os.getenv(AUTH_JWT_SECRET_ENV) is None
        and os.getenv(GRAPH_JWT_SECRET_ENV) is None
        and _environment() not in _PRODUCTION_LIKE_ENVS
    )


def allow_auth_test_headers() -> bool:
    return os.getenv("TESTING") == "true" or _is_enabled(
        os.getenv(AUTH_ALLOW_TEST_HEADERS_ENV),
    )


def bypass_jwt_for_tests() -> bool:
    return _is_enabled(os.getenv(AUTH_BYPASS_JWT_FOR_TESTS_ENV))
