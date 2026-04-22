"""Add curation reviews table used by extraction and graph review queues."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "016_add_reviews_table"
down_revision = "015_add_hgnc_and_current_source_types"
branch_labels = None
depends_on = None


def _shared_schema() -> str | None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return "public"
    return None


def _research_space_fk_target(*, schema: str | None) -> str:
    if schema is None:
        return "research_spaces.id"
    return f"{schema}.research_spaces.id"


def _shared_platform_table_exists(*, table_name: str, schema: str | None) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return inspector.has_table(table_name, schema=schema)


def _uuid_type() -> sa.types.TypeEngine[object]:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=False)
    return sa.String(length=36)


def _research_space_id_column(*, schema: str | None) -> sa.Column[object]:
    foreign_key: sa.ForeignKey | None = None
    if _shared_platform_table_exists(table_name="research_spaces", schema=schema):
        foreign_key = sa.ForeignKey(_research_space_fk_target(schema=schema))
    return sa.Column(
        "research_space_id",
        _uuid_type(),
        foreign_key,
        nullable=True,
    )


def upgrade() -> None:
    schema = _shared_schema()
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "priority",
            sa.String(length=16),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("issues", sa.Integer(), nullable=False, server_default="0"),
        _research_space_id_column(schema=schema),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("last_updated", sa.DateTime(), nullable=True),
        schema=schema,
    )
    op.create_index(
        "ix_reviews_entity_type",
        "reviews",
        ["entity_type"],
        schema=schema,
    )
    op.create_index(
        "ix_reviews_entity_id",
        "reviews",
        ["entity_id"],
        schema=schema,
    )
    op.create_index(
        "ix_reviews_status",
        "reviews",
        ["status"],
        schema=schema,
    )
    op.create_index(
        "ix_reviews_research_space_id",
        "reviews",
        ["research_space_id"],
        schema=schema,
    )


def downgrade() -> None:
    schema = _shared_schema()
    op.drop_index(
        "ix_reviews_research_space_id",
        table_name="reviews",
        schema=schema,
    )
    op.drop_index(
        "ix_reviews_status",
        table_name="reviews",
        schema=schema,
    )
    op.drop_index(
        "ix_reviews_entity_id",
        table_name="reviews",
        schema=schema,
    )
    op.drop_index(
        "ix_reviews_entity_type",
        table_name="reviews",
        schema=schema,
    )
    op.drop_table("reviews", schema=schema)
