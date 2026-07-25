"""Record automated promotion explicitly instead of inferring it.

`reviewed_by IS NULL` was doing two jobs: "no human has reviewed this" and "a
machine approved this".  Auto-promotion set `curation_status='APPROVED'` and
`reviewed_at` while deliberately leaving `reviewed_by` NULL, and the recheck
predicate keyed on that NULL to demote auto-promotions when evidence changed.

The overload made the reviewer unrecordable.  `materialize_support_claim`
accepted a `reviewed_by` argument and discarded it, because persisting it would
have made the NULL check false and silently disabled the recheck -- auto
promotions would have become permanent for any relation a human had ever
touched (D7, ART-GOV-002).

This adds the explicit flag so the two facts can be stored separately.

Backfill is deliberately conservative.  An APPROVED row with no reviewer is
marked auto_promoted because that is exactly the state auto-promotion produced.
Every other row is left False: a row that already carries a reviewer was
approved by a human, and a non-APPROVED row has no promotion to attribute.
Historical rows cannot be re-adjudicated from the schema, so nothing here
invents provenance it does not have.
"""

# The only interpolated value is the schema-qualified table name from
# `graph_schema_name()`, which is deployment configuration rather than caller
# input.  Same pattern and same suppression as the existing migrations.
# ruff: noqa: S608

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "037_relation_auto_promoted_flag"
down_revision = "036_source_evidence_snapshots"
branch_labels = None
depends_on = None


def _relations_table() -> str:
    schema = graph_schema_name()
    return "relations" if schema is None else f"{schema}.relations"


def upgrade() -> None:
    schema = graph_schema_name()
    op.add_column(
        "relations",
        sa.Column(
            "auto_promoted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=schema,
    )
    # An APPROVED row with no reviewer is precisely what auto-promotion left
    # behind; nothing else can be attributed to it from the schema alone.
    op.execute(
        sa.text(
            f"""
            UPDATE {_relations_table()}
            SET auto_promoted = true
            WHERE UPPER(TRIM(curation_status)) = 'APPROVED'
              AND reviewed_by IS NULL
            """,
        ),
    )
    op.create_index(
        "idx_relations_auto_promoted",
        "relations",
        ["auto_promoted"],
        schema=schema,
    )


def downgrade() -> None:
    schema = graph_schema_name()
    op.drop_index("idx_relations_auto_promoted", table_name="relations", schema=schema)
    op.drop_column("relations", "auto_promoted", schema=schema)
