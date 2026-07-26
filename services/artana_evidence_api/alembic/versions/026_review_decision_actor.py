"""Record who made each review decision.

Every decision route authenticates a user and then discarded the identity, so
the promoted/rejected audit trail carried a written reason but no author.  These
columns are the storage half of closing that gap.

Nullable on purpose: rows decided before this migration have no attribution and
inventing one would be worse than admitting the gap.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "026_review_decision_actor"
down_revision = "025_proposal_source_provenance"
branch_labels = None
depends_on = None

_DECISION_TABLES = (
    "harness_proposals",
    "harness_review_items",
    "harness_run_approvals",
)


def upgrade() -> None:
    harness_schema = harness_schema_name()
    for table_name in _DECISION_TABLES:
        op.add_column(
            table_name,
            sa.Column("decided_by_user_id", PGUUID(as_uuid=False), nullable=True),
            schema=harness_schema,
        )
        op.add_column(
            table_name,
            sa.Column("decided_by_email", sa.String(length=320), nullable=True),
            schema=harness_schema,
        )


def downgrade() -> None:
    harness_schema = harness_schema_name()
    for table_name in _DECISION_TABLES:
        op.drop_column(table_name, "decided_by_email", schema=harness_schema)
        op.drop_column(table_name, "decided_by_user_id", schema=harness_schema)
