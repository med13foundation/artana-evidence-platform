"""Add HGNC and current scheduled source type enum values."""

from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "015_add_hgnc_and_current_source_types"
down_revision = "014_add_marrvel_source_type"
branch_labels = None
depends_on = None

_SOURCE_TYPE_VALUES = (
    "file_upload",
    "api",
    "database",
    "web_scraping",
    "pubmed",
    "clinvar",
    "marrvel",
    "hpo",
    "uberon",
    "cell_ontology",
    "gene_ontology",
    "mondo",
    "uniprot",
    "drugbank",
    "hgnc",
    "alphafold",
    "clinical_trials",
    "mgi",
    "zfin",
)


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


def _add_enum_values(enum_name: str) -> None:
    if not _legacy_enum_exists(enum_name):
        return

    for value in _SOURCE_TYPE_VALUES:
        op.execute(f"ALTER TYPE {enum_name} ADD VALUE IF NOT EXISTS '{value}'")


def upgrade() -> None:
    _add_enum_values("sourcetypeenum")
    _add_enum_values("usersourcetypeenum")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values safely.
    # A full enum rebuild would be needed; leaving as no-op.
    pass
