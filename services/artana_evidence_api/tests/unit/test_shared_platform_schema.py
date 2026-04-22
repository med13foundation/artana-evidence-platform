"""Regression coverage for shared-platform table schema routing."""

from __future__ import annotations

from artana_evidence_api.db_schema import (
    qualify_shared_platform_foreign_key_target,
    shared_platform_schema_name,
)


def test_shared_platform_schema_is_public_for_postgres() -> None:
    """PostgreSQL-backed deployments should pin shared tables to ``public``."""
    schema = shared_platform_schema_name(
        "postgresql+psycopg2://service:secret@example.com:5432/artana_dev",
    )

    assert schema == "public"
    assert (
        qualify_shared_platform_foreign_key_target(
            "users.id",
            database_url="postgresql+psycopg2://service:secret@example.com:5432/artana_dev",
        )
        == "public.users.id"
    )


def test_shared_platform_schema_is_omitted_for_sqlite() -> None:
    """SQLite test runs should keep shared tables schema-less."""
    schema = shared_platform_schema_name("sqlite:///tmp/test.db")

    assert schema is None
    assert (
        qualify_shared_platform_foreign_key_target(
            "users.id",
            database_url="sqlite:///tmp/test.db",
        )
        == "users.id"
    )
