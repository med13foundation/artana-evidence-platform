"""Add MARRVEL source type and document format enum values."""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "014_add_marrvel_source_type"
down_revision = "013_proposal_claim_fingerprint"
branch_labels = None
depends_on = None


def _legacy_enum_exists(enum_name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False

    return (
        bind.execute(
            text("SELECT to_regtype(:enum_name)"),
            {"enum_name": enum_name},
        ).scalar_one_or_none()
        is not None
    )


def upgrade() -> None:
    if _legacy_enum_exists("sourcetypeenum"):
        op.execute("ALTER TYPE sourcetypeenum ADD VALUE IF NOT EXISTS 'marrvel'")
    if _legacy_enum_exists("documentformatenum"):
        op.execute(
            "ALTER TYPE documentformatenum ADD VALUE IF NOT EXISTS 'marrvel_json'",
        )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # A full enum rebuild would be needed; leaving as no-op.
    pass
