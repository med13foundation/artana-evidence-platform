"""Add entity-mechanism-paths reasoning index."""

# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "014_entity_mechanism_paths"
down_revision = "013_entity_neighbors"
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
        return '"entity_mechanism_paths"'
    return f'"{schema}"."entity_mechanism_paths"'


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
        "entity_mechanism_paths",
        sa.Column("path_id", sa.UUID(), nullable=False),
        sa.Column("research_space_id", sa.UUID(), nullable=False),
        sa.Column("seed_entity_id", sa.UUID(), nullable=False),
        sa.Column("end_entity_id", sa.UUID(), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("path_length", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "supporting_claim_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("path_updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
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
            ["path_id"],
            [f"{schema + '.' if schema else ''}reasoning_paths.id"],
            name="fk_entity_mechanism_paths_path",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["seed_entity_id", "research_space_id"],
            [
                f"{schema + '.' if schema else ''}entities.id",
                f"{schema + '.' if schema else ''}entities.research_space_id",
            ],
            name="fk_entity_mechanism_paths_seed_entity_space",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["end_entity_id", "research_space_id"],
            [
                f"{schema + '.' if schema else ''}entities.id",
                f"{schema + '.' if schema else ''}entities.research_space_id",
            ],
            name="fk_entity_mechanism_paths_end_entity_space",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("path_id"),
        schema=schema,
    )
    op.create_index(
        "idx_entity_mechanism_paths_space_seed_confidence",
        "entity_mechanism_paths",
        ["research_space_id", "seed_entity_id", "confidence"],
        schema=schema,
    )
    op.create_index(
        "idx_entity_mechanism_paths_space_end",
        "entity_mechanism_paths",
        ["research_space_id", "end_entity_id"],
        schema=schema,
    )

    if bind.dialect.name != "postgresql":
        return

    table_name = _table_name()
    condition = _space_access_condition("entity_mechanism_paths.research_space_id")
    op.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f'DROP POLICY IF EXISTS "rls_entity_mechanism_paths_access" ON {table_name}',
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "rls_entity_mechanism_paths_access"
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
                f'DROP POLICY IF EXISTS "rls_entity_mechanism_paths_access" ON {table_name}',
            ),
        )
        op.execute(sa.text(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY"))

    op.drop_index(
        "idx_entity_mechanism_paths_space_end",
        table_name="entity_mechanism_paths",
        schema=schema,
    )
    op.drop_index(
        "idx_entity_mechanism_paths_space_seed_confidence",
        table_name="entity_mechanism_paths",
        schema=schema,
    )
    op.drop_table("entity_mechanism_paths", schema=schema)
