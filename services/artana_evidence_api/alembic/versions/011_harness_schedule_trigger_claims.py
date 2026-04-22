"""Add durable schedule trigger claim columns."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "011_schedule_trigger_claims"
down_revision = "010_doc_storage_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    harness_schema = harness_schema_name()

    with op.batch_alter_table("harness_schedules", schema=harness_schema) as batch_op:
        batch_op.add_column(
            sa.Column("active_trigger_claim_id", sa.UUID(), nullable=True),
        )
        batch_op.add_column(
            sa.Column("active_trigger_claimed_at", sa.DateTime(), nullable=True),
        )
        batch_op.create_index(
            "ix_harness_schedules_active_trigger_claim_id",
            ["active_trigger_claim_id"],
            unique=False,
        )


def downgrade() -> None:
    harness_schema = harness_schema_name()

    with op.batch_alter_table("harness_schedules", schema=harness_schema) as batch_op:
        batch_op.drop_index("ix_harness_schedules_active_trigger_claim_id")
        batch_op.drop_column("active_trigger_claimed_at")
        batch_op.drop_column("active_trigger_claim_id")
