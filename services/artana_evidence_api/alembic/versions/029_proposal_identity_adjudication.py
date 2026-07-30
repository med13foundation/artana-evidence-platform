"""Give a parked proposal somewhere to record how its identity was settled.

A cross-document fingerprint collision parks the second observation in
``identity_pending`` (ART-DATA-001).  That status was terminal: no route reached
it, the queue offered no action on it, and every retained second observation was
moved somewhere nobody could see or act on.  A reviewer can now say which it is
-- the same fact, or a different one -- and this column is where that answer is
kept.

Its own column, not a ``metadata_payload`` key.  Metadata is arbitrary
caller-supplied JSON, so a caller could otherwise have its own data read back as
adjudication history -- the same reason migration 027 gave an approval its own
superseded-decision column.  It also has to outlive the later promote or reject
of a released proposal, which overwrites decision_reason, decided_at and
decided_by.

Nullable, with no backfill: rows written before this column were never
adjudicated, and NULL is the truthful reading of that.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "029_proposal_identity_adjudication"
down_revision = "028_widen_fingerprint_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "harness_proposals",
        sa.Column("identity_adjudication_payload", sa.JSON(), nullable=True),
        schema=harness_schema_name(),
    )


def downgrade() -> None:
    op.drop_column(
        "harness_proposals",
        "identity_adjudication_payload",
        schema=harness_schema_name(),
    )
