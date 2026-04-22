"""Add graph-owned source document persistence table."""

from __future__ import annotations

import artana_evidence_db.source_document_model  # noqa: F401
import sqlalchemy as sa
from alembic import op
from artana_evidence_db.orm_base import Base

revision = "023_graph_source_documents"
down_revision = "022_entity_resolution_hardening"
branch_labels = None
depends_on = None


def _source_document_metadata() -> sa.MetaData:
    metadata = Base.metadata
    source_document_table = metadata.tables["source_documents"]
    migration_metadata = sa.MetaData(naming_convention=metadata.naming_convention)
    source_document_table.to_metadata(migration_metadata)
    return migration_metadata


def upgrade() -> None:
    bind = op.get_bind()
    metadata = _source_document_metadata()
    metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    metadata = _source_document_metadata()
    metadata.drop_all(bind=bind, checkfirst=True)
