"""Unit tests for API database URL safety checks."""

from __future__ import annotations

import pytest
from artana_evidence_api.runtime.database_url_security import (
    validate_database_url_security,
)


def test_validate_database_url_security_rejects_default_password_in_production() -> None:
    with pytest.raises(RuntimeError, match="Insecure default database credentials"):
        validate_database_url_security(
            "postgresql+psycopg2://artana_dev:artana_dev_password@localhost/artana_dev",
            environment="production",
            allow_insecure_defaults=False,
        )


def test_validate_database_url_security_allows_development_defaults() -> None:
    validate_database_url_security(
        "postgresql+psycopg2://artana_dev:artana_dev_password@localhost/artana_dev",
        environment="development",
        allow_insecure_defaults=False,
    )


def test_validate_database_url_security_treats_blank_environment_as_development() -> None:
    validate_database_url_security(
        "postgresql+psycopg2://artana_dev:artana_dev_password@localhost/artana_dev",
        environment=" ",
        allow_insecure_defaults=False,
    )


def test_validate_database_url_security_allows_explicit_insecure_override() -> None:
    validate_database_url_security(
        "postgresql+psycopg2://artana_dev:artana_dev_password@localhost/artana_dev",
        environment="production",
        allow_insecure_defaults=True,
    )
