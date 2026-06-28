"""Database URL security checks shared by API runtime database resolvers."""

from __future__ import annotations

import os

_DEFAULT_POSTGRES_PASSWORD_MARKER = "artana_dev_password"
_PRODUCTION_ENVIRONMENTS = frozenset({"production", "staging"})


def validate_database_url_security(
    url: str,
    *,
    environment: str | None = None,
    allow_insecure_defaults: bool | None = None,
) -> None:
    """Reject insecure default credentials in production-like environments."""
    raw_environment = environment if environment is not None else os.getenv("ARTANA_ENV")
    normalized_environment = (
        raw_environment.strip() if raw_environment is not None else "development"
    )
    resolved_environment = (normalized_environment or "development").lower()
    if allow_insecure_defaults is None:
        allow_insecure_defaults = os.getenv("ARTANA_ALLOW_INSECURE_DEFAULTS") == "1"
    if allow_insecure_defaults:
        return
    if resolved_environment not in _PRODUCTION_ENVIRONMENTS:
        return
    if _DEFAULT_POSTGRES_PASSWORD_MARKER not in url:
        return
    msg = (
        "Insecure default database credentials detected in a production/staging "
        "environment. Provide secure ARTANA_EVIDENCE_API_DATABASE_URL or "
        "DATABASE_URL values."
    )
    raise RuntimeError(msg)
