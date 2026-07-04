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
_DEDUPLICATION_REASON = (
    "Rejected by migration 024 because a newer duplicate active proposal "
    "kept this claim fingerprint."
)


def _qualified_harness_proposals_table(harness_schema: str | None) -> str:
    if harness_schema is None:
        return "harness_proposals"
    return f"{harness_schema}.harness_proposals"


def upgrade() -> None:
    harness_schema = harness_schema_name()
    proposals_table = _qualified_harness_proposals_table(harness_schema)
    promoted_duplicate_count = _promoted_duplicate_fingerprint_group_count(
        proposals_table,
    )
    if promoted_duplicate_count > 0:
        msg = (
            "Migration 024 found multiple promoted proposals with the same "
            "active claim fingerprint in a space; resolve these product-data "
            "duplicates manually before enforcing the unique active index."
        )
        raise RuntimeError(msg)
    op.execute(
        sa.text(
            f"""
            WITH ranked_active AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY space_id, claim_fingerprint
                        ORDER BY
                            CASE
                                WHEN status = 'promoted' THEN 0
                                ELSE 1
                            END,
                            COALESCE(updated_at, created_at) DESC,
                            COALESCE(created_at, updated_at) DESC,
                            id DESC
                    ) AS active_rank
                FROM {proposals_table}
                WHERE claim_fingerprint IS NOT NULL
                  AND status IN ('pending_review', 'promoted')
            )
            UPDATE {proposals_table}
            SET
                status = 'rejected',
                decision_reason = CASE
                    WHEN decision_reason IS NULL OR decision_reason = ''
                        THEN :deduplication_reason
                    ELSE decision_reason || ' | ' || :deduplication_reason
                END,
                decided_at = COALESCE(decided_at, CURRENT_TIMESTAMP),
                updated_at = CURRENT_TIMESTAMP
            WHERE id IN (
                SELECT id
                FROM ranked_active
                WHERE active_rank > 1
            )
            """,
        ).bindparams(deduplication_reason=_DEDUPLICATION_REASON),
    )
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


def _promoted_duplicate_fingerprint_group_count(proposals_table: str) -> int:
    connection = op.get_bind()
    result = connection.execute(
        sa.text(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT space_id, claim_fingerprint
                FROM {proposals_table}
                WHERE claim_fingerprint IS NOT NULL
                  AND status = 'promoted'
                GROUP BY space_id, claim_fingerprint
                HAVING COUNT(*) > 1
            ) promoted_duplicates
            """,
        ),
    )
    return int(result.scalar_one())


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
