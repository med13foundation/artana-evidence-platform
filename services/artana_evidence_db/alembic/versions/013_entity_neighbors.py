"""Add entity-neighbors read model."""

# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "013_entity_neighbors"
down_revision = "012_entity_claim_summary"
branch_labels = None
depends_on = None

_BYPASS_RLS = (
    "COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)"
)
_IS_ADMIN = (
    "COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)"
)
_CURRENT_USER_ID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"


def _table_name() -> str:
    schema = graph_schema_name()
    if schema is None:
        return '"entity_neighbors"'
    return f'"{schema}"."entity_neighbors"'


def _graph_space_memberships() -> str:
    schema = graph_schema_name()
    if schema is None:
        return "graph_space_memberships"
    return f'"{schema}".graph_space_memberships'


def _graph_spaces() -> str:
    schema = graph_schema_name()
    if schema is None:
        return "graph_spaces"
    return f'"{schema}".graph_spaces'


def _space_access_condition(space_column: str) -> str:
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR (
                {_CURRENT_USER_ID} IS NOT NULL
                AND {space_column} IN (
                    SELECT gsm.space_id
                    FROM {_graph_space_memberships()} AS gsm
                    WHERE gsm.user_id = {_CURRENT_USER_ID}
                      AND gsm.is_active = TRUE
                    UNION
                    SELECT gs.id
                    FROM {_graph_spaces()} AS gs
                    WHERE gs.owner_id = {_CURRENT_USER_ID}
                )
            )
        )
    """


def upgrade() -> None:
    schema = graph_schema_name()
    bind = op.get_bind()

    op.create_table(
        "entity_neighbors",
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("relation_id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("neighbor_entity_id", sa.UUID(), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("relation_updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["relation_id"],
            [f"{schema + '.' if schema else ''}relations.id"],
            name="fk_entity_neighbors_relation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id", "research_space_id"],
            [
                f"{schema + '.' if schema else ''}entities.id",
                f"{schema + '.' if schema else ''}entities.research_space_id",
            ],
            name="fk_entity_neighbors_entity_space",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["neighbor_entity_id", "research_space_id"],
            [
                f"{schema + '.' if schema else ''}entities.id",
                f"{schema + '.' if schema else ''}entities.research_space_id",
            ],
            name="fk_entity_neighbors_neighbor_space",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("entity_id", "relation_id"),
        schema=schema,
    )
    op.create_index(
        "idx_entity_neighbors_space_entity_updated",
        "entity_neighbors",
        ["research_space_id", "entity_id", "relation_updated_at"],
        schema=schema,
    )
    op.create_index(
        "idx_entity_neighbors_space_neighbor",
        "entity_neighbors",
        ["research_space_id", "neighbor_entity_id"],
        schema=schema,
    )

    if bind.dialect.name != "postgresql":
        return

    table_name = _table_name()
    condition = _space_access_condition("entity_neighbors.research_space_id")
    op.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f'DROP POLICY IF EXISTS "rls_entity_neighbors_access" ON {table_name}',
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "rls_entity_neighbors_access"
            ON {table_name}
            FOR ALL
            USING ({condition})
            WITH CHECK ({condition})
            """,
        ),
    )


def downgrade() -> None:
    schema = graph_schema_name()
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        table_name = _table_name()
        op.execute(
            sa.text(
                f'DROP POLICY IF EXISTS "rls_entity_neighbors_access" ON {table_name}',
            ),
        )
        op.execute(sa.text(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"))

    op.drop_index(
        "idx_entity_neighbors_space_neighbor",
        table_name="entity_neighbors",
        schema=schema,
    )
    op.drop_index(
        "idx_entity_neighbors_space_entity_updated",
        table_name="entity_neighbors",
        schema=schema,
    )
    op.drop_table("entity_neighbors", schema=schema)
