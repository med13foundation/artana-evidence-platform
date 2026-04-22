"""Add graph domain-pack seed status ledger."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name
from sqlalchemy.dialects import postgresql

revision = "031_pack_seed_status"
down_revision = "030_proposal_lifecycle"
branch_labels = None
depends_on = None


def _has_table(conn: sa.Connection, table: str, schema: str | None) -> bool:
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if _has_table(conn, "graph_pack_seed_status", schema):
        return
    op.create_table(
        "graph_pack_seed_status",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("pack_name", sa.String(length=64), nullable=False),
        sa.Column("pack_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_operation", sa.String(length=32), nullable=False),
        sa.Column("seed_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("repair_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metadata_payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("repaired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_graph_pack_seed_status"),
        sa.UniqueConstraint(
            "research_space_id",
            "pack_name",
            "pack_version",
            name="uq_graph_pack_seed_status_space_pack_version",
        ),
        schema=schema,
    )
    op.create_index(
        "idx_graph_pack_seed_status_space",
        "graph_pack_seed_status",
        ["research_space_id"],
        schema=schema,
    )
    op.create_index(
        "idx_graph_pack_seed_status_pack",
        "graph_pack_seed_status",
        ["pack_name", "pack_version"],
        schema=schema,
    )


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if not _has_table(conn, "graph_pack_seed_status", schema):
        return
    op.drop_index(
        "idx_graph_pack_seed_status_pack",
        table_name="graph_pack_seed_status",
        schema=schema,
    )
    op.drop_index(
        "idx_graph_pack_seed_status_space",
        table_name="graph_pack_seed_status",
        schema=schema,
    )
    op.drop_table("graph_pack_seed_status", schema=schema)
