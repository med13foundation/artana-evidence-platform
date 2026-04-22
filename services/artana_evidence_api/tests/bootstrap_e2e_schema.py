"""Bootstrap harness-service tables for cross-service E2E runs."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for candidate in (REPO_ROOT, REPO_ROOT / "services"):
    resolved = str(candidate)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)

import artana_evidence_api.models  # noqa: F401,E402
from artana_evidence_api.database import engine  # noqa: E402
from artana_evidence_api.db_schema import harness_schema_name  # noqa: E402
from artana_evidence_api.models.base import Base  # noqa: E402


def main() -> int:
    """Create the harness schema and ORM-owned tables if they are missing."""
    schema = harness_schema_name()
    with engine.begin() as connection:
        if schema is not None:
            connection.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        Base.metadata.create_all(bind=connection, checkfirst=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
