"""Let a fingerprint column hold every fingerprint the service writes.

``harness_proposals.claim_fingerprint`` was varchar(32) and
``harness_review_items.review_fingerprint`` was varchar(64), but neither width
covers what the code actually writes:

* ``ClaimFrame.dedupe_identity`` is a full 64-character SHA-256, so every
  frame-backed extraction proposal failed to insert;
* evidence-selection staging writes ``evidence-selection:<sha256>`` (83) and
  ``evidence-selection-review:<sha256>`` (90), so neither half of a staged
  source-record review could insert either.

Postgres rejected all three with StringDataRightTruncation.  Nothing caught it
because the test suite runs on SQLite, which does not enforce VARCHAR length.

Both columns move together on purpose.  Widening only the proposal side would
turn a symmetric failure -- ``stage_selected_records_for_review`` writes a
proposal *and* a review item, and today neither lands -- into a partial success
where the proposal lands and its review item does not.

Widening a varchar in Postgres is a catalog-only change: no table rewrite, and
no rebuild of ``uq_harness_proposals_active_space_claim_fingerprint`` or
``uq_harness_review_items_space_review_fingerprint``, both of which cover these
columns.  No data changes -- every stored value already fits.

The downgrade narrows back only if every stored value still fits, and refuses
otherwise rather than truncating an identity.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_api.claim_fingerprint import MAX_FINGERPRINT_LENGTH
from artana_evidence_api.db_schema import harness_schema_name

revision = "028_widen_fingerprint_columns"
down_revision = "027_approval_superseded_decisions"
branch_labels = None
depends_on = None

#: (table, column, width before this migration).
_FINGERPRINT_COLUMNS = (
    ("harness_proposals", "claim_fingerprint", 32),
    ("harness_review_items", "review_fingerprint", 64),
)


def _retype(
    *,
    table_name: str,
    column_name: str,
    from_length: int,
    to_length: int,
) -> None:
    """Change one fingerprint column's declared width on either dialect.

    SQLite has no ``ALTER COLUMN TYPE``, so the change has to go through a batch
    table rebuild there.  ``batch_alter_table`` emits a plain ``ALTER`` on
    Postgres and only rebuilds where the dialect forces it, so one call covers
    both.
    """

    with op.batch_alter_table(
        table_name,
        schema=harness_schema_name(),
    ) as batch_op:
        batch_op.alter_column(
            column_name,
            type_=sa.String(length=to_length),
            existing_type=sa.String(length=from_length),
            existing_nullable=True,
        )


def upgrade() -> None:
    for table_name, column_name, previous_length in _FINGERPRINT_COLUMNS:
        _retype(
            table_name=table_name,
            column_name=column_name,
            from_length=previous_length,
            to_length=MAX_FINGERPRINT_LENGTH,
        )


def downgrade() -> None:
    harness_schema = harness_schema_name()
    for table_name, column_name, previous_length in _FINGERPRINT_COLUMNS:
        _reject_values_wider_than(
            harness_schema=harness_schema,
            table_name=table_name,
            column_name=column_name,
            length=previous_length,
        )
        _retype(
            table_name=table_name,
            column_name=column_name,
            from_length=MAX_FINGERPRINT_LENGTH,
            to_length=previous_length,
        )


def _reject_values_wider_than(
    *,
    harness_schema: str | None,
    table_name: str,
    column_name: str,
    length: int,
) -> None:
    """Refuse to narrow a column that would silently truncate an identity."""

    qualified = (
        table_name if harness_schema is None else f"{harness_schema}.{table_name}"
    )
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            f"""
            SELECT COUNT(*)
            FROM {qualified}
            WHERE {column_name} IS NOT NULL
              AND LENGTH({column_name}) > :length
            """,
        ).bindparams(length=length),
    )
    oversized_count = int(result.scalar_one())
    if oversized_count > 0:
        msg = (
            f"Cannot narrow {qualified}.{column_name} back to varchar({length}): "
            f"{oversized_count} row(s) hold a longer fingerprint. Truncating "
            "them would change an identity, so resolve those rows first."
        )
        raise RuntimeError(msg)
