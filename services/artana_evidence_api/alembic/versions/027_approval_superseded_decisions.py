"""Give a run approval its own column for the decisions it supersedes.

When a re-proposed action reuses a decided approval key but describes a
different write, the approval is reopened so the run cannot proceed on a
decision made about something else -- and the decision it replaces is kept.

That trail was first written into ``metadata_payload``, which is arbitrary
caller-supplied JSON.  A caller could therefore supply the same key and have its
own data read back as system-authored decision history, and an unchanged
re-proposal of such an action compared unequal and reopened a decision nobody
had revisited.  Audit output does not belong in a namespace the caller writes.

Nullable, with no backfill: rows written before this column have no superseded
trail, and an empty array is the truthful reading of that.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "027_approval_superseded_decisions"
down_revision = "026_review_decision_actor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "harness_run_approvals",
        sa.Column("superseded_decisions_payload", sa.JSON(), nullable=True),
        schema=harness_schema_name(),
    )


def downgrade() -> None:
    op.drop_column(
        "harness_run_approvals",
        "superseded_decisions_payload",
        schema=harness_schema_name(),
    )
