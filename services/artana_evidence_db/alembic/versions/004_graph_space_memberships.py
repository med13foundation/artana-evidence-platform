"""Add graph-owned space membership table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import (
    graph_schema_name,
    qualify_graph_foreign_key_target,
)

revision = "004_graph_space_memberships"
down_revision = "003_graph_spaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    graph_schema = graph_schema_name()
    inspector = sa.inspect(op.get_bind())
    if inspector.has_table("graph_space_memberships", schema=graph_schema):
        return
    if graph_schema is not None:
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{graph_schema}"'))
    uuid_type = sa.Uuid()
    role_enum = sa.Enum(
        "owner",
        "admin",
        "curator",
        "researcher",
        "viewer",
        name="graphspacemembershiproleenum",
    )
    role_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "graph_space_memberships",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("space_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column(
            "role",
            role_enum,
            nullable=False,
            server_default="researcher",
        ),
        sa.Column("invited_by", uuid_type, nullable=True),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["space_id"],
            [qualify_graph_foreign_key_target("graph_spaces.id", schema=graph_schema)],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "space_id",
            "user_id",
            name="uq_graph_space_memberships_space_user",
        ),
        schema=graph_schema,
        comment="Graph-owned tenant memberships for graph-service authz",
    )
    op.create_index(
        "idx_graph_space_memberships_space",
        "graph_space_memberships",
        ["space_id"],
        unique=False,
        schema=graph_schema,
    )
    op.create_index(
        "idx_graph_space_memberships_user",
        "graph_space_memberships",
        ["user_id"],
        unique=False,
        schema=graph_schema,
    )
    op.create_index(
        "idx_graph_space_memberships_role",
        "graph_space_memberships",
        ["role"],
        unique=False,
        schema=graph_schema,
    )


def downgrade() -> None:
    return None
