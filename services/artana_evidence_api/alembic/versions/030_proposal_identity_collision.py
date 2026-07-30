"""Record what a parked proposal collided with, so a reviewer can decide.

Migration 029 gave a parked proposal a way out: a reviewer says "same fact" or
"different facts".  It did not give them anything to decide on.  The
already-persisted path named the counterpart only inside a prose
``decision_reason``, as a bare UUID; the intra-batch path named nothing at all.
An action offered without the evidence to take it does not produce a decision,
it produces a decision record.

So the collision itself gets a column: counterpart id, title, source document,
status, the shared fingerprint, and whether the counterpart came from the same
batch or was already stored.  That last distinction is the difference between
"one extraction pass said this twice" and "the space already held it", which
changes what the reviewer is being asked.

Separate from ``identity_adjudication_payload`` because the two record different
things at different times.  This one is what the system observed, written before
any reviewer sees the row; that one is what a reviewer concluded.  Collapsing
them would mean a row carrying an "adjudication" nobody has made.

Snapshotted at park time rather than resolved on read, for reasons that are not
about performance.  The intra-batch counterpart has no committed row when the
decision is taken.  ``release_as_distinct`` clears the claim fingerprint, so
afterwards no query can find the counterpart at all.  And a reviewer needs what
collided when it collided, not whatever holds that fingerprint today.

Nullable, with no backfill.  A row written before this column has no recoverable
collision -- the intra-batch counterpart was never recorded anywhere, and the
already-persisted one survives only as prose in ``decision_reason``.  Parsing a
sentence into a foreign key would be inventing structure that was never
captured, so NULL is the truthful reading.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.db_schema import harness_schema_name

revision = "030_proposal_identity_collision"
down_revision = "029_proposal_identity_adjudication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "harness_proposals",
        sa.Column("identity_collision_payload", sa.JSON(), nullable=True),
        schema=harness_schema_name(),
    )


def downgrade() -> None:
    op.drop_column(
        "harness_proposals",
        "identity_collision_payload",
        schema=harness_schema_name(),
    )
