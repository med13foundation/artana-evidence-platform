"""Add unique active proposal fingerprint constraint."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "024_unique_active_proposal_fingerprints"
down_revision = "023_harness_study_outcomes"
branch_labels = None
depends_on = None

_OLD_INDEX = "idx_harness_proposals_space_fingerprint"
_UNIQUE_INDEX = "uq_harness_proposals_active_space_claim_fingerprint"
_ACTIVE_FINGERPRINT_PREDICATE = (
    "claim_fingerprint IS NOT NULL "
    "AND status IN ('pending_review', 'promoted')"
)


def upgrade() -> None:
    harness_schema = harness_schema_name()
    op.drop_index(
        _OLD_INDEX,
        table_name="harness_proposals",
        schema=harness_schema,
    )
    op.create_index(
        _UNIQUE_INDEX,
        "harness_proposals",
        ["space_id", "claim_fingerprint"],
        unique=True,
        schema=harness_schema,
        postgresql_where=sa.text(_ACTIVE_FINGERPRINT_PREDICATE),
        sqlite_where=sa.text(_ACTIVE_FINGERPRINT_PREDICATE),
    )


def downgrade() -> None:
    harness_schema = harness_schema_name()
    op.drop_index(
        _UNIQUE_INDEX,
        table_name="harness_proposals",
        schema=harness_schema,
    )
    op.create_index(
        _OLD_INDEX,
        "harness_proposals",
        ["space_id", "claim_fingerprint"],
        unique=False,
        schema=harness_schema,
    )
