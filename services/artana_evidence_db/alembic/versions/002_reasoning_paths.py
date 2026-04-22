"""Add derived reasoning path tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002_reasoning_paths"
down_revision = "001_current_baseline"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return inspector.has_table(table_name)


def _has_index(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return any(
        index["name"] == index_name for index in inspector.get_indexes(table_name)
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    uuid_type = sa.Uuid()
    if not _has_table(inspector, "reasoning_paths"):
        op.create_table(
            "reasoning_paths",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("research_space_id", uuid_type, nullable=False),
            sa.Column(
                "path_kind",
                sa.String(length=32),
                nullable=False,
                server_default="MECHANISM",
            ),
            sa.Column(
                "status",
                sa.String(length=16),
                nullable=False,
                server_default="ACTIVE",
            ),
            sa.Column("start_entity_id", uuid_type, nullable=False),
            sa.Column("end_entity_id", uuid_type, nullable=False),
            sa.Column("root_claim_id", uuid_type, nullable=False),
            sa.Column("path_length", sa.Integer(), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column("path_signature_hash", sa.String(length=128), nullable=False),
            sa.Column("generated_by", sa.String(length=255), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "metadata_payload",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "path_kind IN ('MECHANISM')",
                name="ck_reasoning_paths_kind",
            ),
            sa.CheckConstraint(
                "status IN ('ACTIVE', 'STALE')",
                name="ck_reasoning_paths_status",
            ),
            sa.CheckConstraint(
                "path_length >= 1 AND path_length <= 32",
                name="ck_reasoning_paths_length",
            ),
            sa.CheckConstraint(
                "confidence >= 0.0 AND confidence <= 1.0",
                name="ck_reasoning_paths_confidence",
            ),
            sa.ForeignKeyConstraint(
                ["start_entity_id"],
                ["entities.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["end_entity_id"],
                ["entities.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["root_claim_id"],
                ["relation_claims.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "research_space_id",
                "path_kind",
                "path_signature_hash",
                name="uq_reasoning_paths_space_signature",
            ),
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "reasoning_paths",
        "idx_reasoning_paths_space_status",
    ):
        op.create_index(
            "idx_reasoning_paths_space_status",
            "reasoning_paths",
            ["research_space_id", "status"],
            unique=False,
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "reasoning_paths",
        "idx_reasoning_paths_space_start_end",
    ):
        op.create_index(
            "idx_reasoning_paths_space_start_end",
            "reasoning_paths",
            ["research_space_id", "start_entity_id", "end_entity_id"],
            unique=False,
        )
        inspector = sa.inspect(bind)

    if not _has_table(inspector, "reasoning_path_steps"):
        op.create_table(
            "reasoning_path_steps",
            sa.Column("id", uuid_type, nullable=False),
            sa.Column("path_id", uuid_type, nullable=False),
            sa.Column("step_index", sa.Integer(), nullable=False),
            sa.Column("source_claim_id", uuid_type, nullable=False),
            sa.Column("target_claim_id", uuid_type, nullable=False),
            sa.Column("claim_relation_id", uuid_type, nullable=False),
            sa.Column("canonical_relation_id", uuid_type, nullable=True),
            sa.Column(
                "metadata_payload",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.CheckConstraint(
                "step_index >= 0 AND step_index <= 255",
                name="ck_reasoning_path_steps_index",
            ),
            sa.ForeignKeyConstraint(
                ["path_id"],
                ["reasoning_paths.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["source_claim_id"],
                ["relation_claims.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["target_claim_id"],
                ["relation_claims.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["claim_relation_id"],
                ["claim_relations.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["canonical_relation_id"],
                ["relations.id"],
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "path_id",
                "step_index",
                name="uq_reasoning_path_steps_order",
            ),
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "reasoning_path_steps",
        "idx_reasoning_path_steps_path",
    ):
        op.create_index(
            "idx_reasoning_path_steps_path",
            "reasoning_path_steps",
            ["path_id"],
            unique=False,
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "reasoning_path_steps",
        "idx_reasoning_path_steps_source_claim",
    ):
        op.create_index(
            "idx_reasoning_path_steps_source_claim",
            "reasoning_path_steps",
            ["source_claim_id"],
            unique=False,
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "reasoning_path_steps",
        "idx_reasoning_path_steps_target_claim",
    ):
        op.create_index(
            "idx_reasoning_path_steps_target_claim",
            "reasoning_path_steps",
            ["target_claim_id"],
            unique=False,
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "reasoning_path_steps",
        "idx_reasoning_path_steps_claim_relation",
    ):
        op.create_index(
            "idx_reasoning_path_steps_claim_relation",
            "reasoning_path_steps",
            ["claim_relation_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_index(
        "idx_reasoning_path_steps_claim_relation",
        table_name="reasoning_path_steps",
    )
    op.drop_index(
        "idx_reasoning_path_steps_target_claim",
        table_name="reasoning_path_steps",
    )
    op.drop_index(
        "idx_reasoning_path_steps_source_claim",
        table_name="reasoning_path_steps",
    )
    op.drop_index("idx_reasoning_path_steps_path", table_name="reasoning_path_steps")
    op.drop_table("reasoning_path_steps")
    op.drop_index("idx_reasoning_paths_space_start_end", table_name="reasoning_paths")
    op.drop_index("idx_reasoning_paths_space_status", table_name="reasoning_paths")
    op.drop_table("reasoning_paths")
