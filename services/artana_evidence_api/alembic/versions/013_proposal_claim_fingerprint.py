"""Add claim_fingerprint column to harness_proposals for deduplication."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "013_proposal_claim_fingerprint"
down_revision = "011_schedule_trigger_claims"
branch_labels = None
depends_on = None


def upgrade() -> None:
    harness_schema = harness_schema_name()

    with op.batch_alter_table("harness_proposals", schema=harness_schema) as batch_op:
        batch_op.add_column(
            sa.Column("claim_fingerprint", sa.String(length=32), nullable=True),
        )
        batch_op.create_index(
            "idx_harness_proposals_space_fingerprint",
            ["space_id", "claim_fingerprint"],
            unique=False,
        )


def downgrade() -> None:
    harness_schema = harness_schema_name()

    with op.batch_alter_table("harness_proposals", schema=harness_schema) as batch_op:
        batch_op.drop_index("idx_harness_proposals_space_fingerprint")
        batch_op.drop_column("claim_fingerprint")
