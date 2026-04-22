"""Add AI Full Mode governance ledgers."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import (
    graph_schema_name,
    qualify_graph_foreign_key_target,
)
from sqlalchemy.dialects import postgresql

revision = "032_ai_full_mode_governance"
down_revision = "031_pack_seed_status"
branch_labels = None
depends_on = None


def _has_table(conn: sa.Connection, table: str, schema: str | None) -> bool:
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    graph_spaces_fk = qualify_graph_foreign_key_target(
        "graph_spaces.id",
        schema=schema,
    )
    domain_contexts_fk = qualify_graph_foreign_key_target(
        "dictionary_domain_contexts.id",
        schema=schema,
    )
    concept_sets_fk = qualify_graph_foreign_key_target(
        "concept_sets.id",
        schema=schema,
    )
    concept_members_fk = qualify_graph_foreign_key_target(
        "concept_members.id",
        schema=schema,
    )

    if not _has_table(conn, "concept_proposals", schema):
        op.create_table(
            "concept_proposals",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("research_space_id", sa.UUID(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("candidate_decision", sa.String(length=32), nullable=False),
            sa.Column("domain_context", sa.String(length=64), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("canonical_label", sa.String(length=255), nullable=False),
            sa.Column("normalized_label", sa.String(length=255), nullable=False),
            sa.Column("concept_set_id", sa.UUID(), nullable=True),
            sa.Column("existing_concept_member_id", sa.UUID(), nullable=True),
            sa.Column("applied_concept_member_id", sa.UUID(), nullable=True),
            sa.Column(
                "synonyms_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "external_refs_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "evidence_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "duplicate_checks_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "warnings_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "decision_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("proposed_by", sa.String(length=128), nullable=False),
            sa.Column("reviewed_by", sa.String(length=128), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_reason", sa.Text(), nullable=True),
            sa.Column("source_ref", sa.String(length=1024), nullable=True),
            sa.Column("proposal_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_concept_proposals"),
            sa.ForeignKeyConstraint(
                ["research_space_id"],
                [graph_spaces_fk],
                name="fk_concept_proposals_space",
            ),
            sa.ForeignKeyConstraint(
                ["domain_context"],
                [domain_contexts_fk],
                name="fk_concept_proposals_domain_context",
            ),
            sa.ForeignKeyConstraint(
                ["concept_set_id"],
                [concept_sets_fk],
                name="fk_concept_proposals_concept_set",
            ),
            sa.ForeignKeyConstraint(
                ["existing_concept_member_id"],
                [concept_members_fk],
                name="fk_concept_proposals_existing_member",
            ),
            sa.ForeignKeyConstraint(
                ["applied_concept_member_id"],
                [concept_members_fk],
                name="fk_concept_proposals_applied_member",
            ),
            sa.UniqueConstraint(
                "research_space_id",
                "source_ref",
                name="uq_concept_proposals_space_source_ref",
            ),
            sa.CheckConstraint(
                "status IN ('SUBMITTED', 'DUPLICATE_CANDIDATE', "
                "'CHANGES_REQUESTED', 'APPROVED', 'REJECTED', 'MERGED', 'APPLIED')",
                name="ck_concept_proposals_status",
            ),
            sa.CheckConstraint(
                "candidate_decision IN ('CREATE_NEW', 'MATCH_EXISTING', "
                "'MERGE_AS_SYNONYM', 'SYNONYM_COLLISION', 'EXTERNAL_REF_MATCH', "
                "'NEEDS_REVIEW')",
                name="ck_concept_proposals_candidate_decision",
            ),
            schema=schema,
        )
        op.create_index(
            "idx_concept_proposals_space_status",
            "concept_proposals",
            ["research_space_id", "status"],
            schema=schema,
        )
        op.create_index(
            "idx_concept_proposals_space_label",
            "concept_proposals",
            ["research_space_id", "domain_context", "normalized_label"],
            schema=schema,
        )

    if not _has_table(conn, "graph_change_proposals", schema):
        op.create_table(
            "graph_change_proposals",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("research_space_id", sa.UUID(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column(
                "proposal_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "resolution_plan_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "warnings_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "error_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "applied_concept_member_ids_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "applied_claim_ids_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column("proposed_by", sa.String(length=128), nullable=False),
            sa.Column("reviewed_by", sa.String(length=128), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_reason", sa.Text(), nullable=True),
            sa.Column("source_ref", sa.String(length=1024), nullable=True),
            sa.Column("proposal_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_graph_change_proposals"),
            sa.ForeignKeyConstraint(
                ["research_space_id"],
                [graph_spaces_fk],
                name="fk_graph_change_proposals_space",
            ),
            sa.UniqueConstraint(
                "research_space_id",
                "source_ref",
                name="uq_graph_change_proposals_space_source_ref",
            ),
            sa.CheckConstraint(
                "status IN ('READY_FOR_REVIEW', 'CHANGES_REQUESTED', "
                "'REJECTED', 'APPLIED')",
                name="ck_graph_change_proposals_status",
            ),
            schema=schema,
        )
        op.create_index(
            "idx_graph_change_proposals_space_status",
            "graph_change_proposals",
            ["research_space_id", "status"],
            schema=schema,
        )

    if not _has_table(conn, "ai_full_mode_decisions", schema):
        op.create_table(
            "ai_full_mode_decisions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("research_space_id", sa.UUID(), nullable=False),
            sa.Column("target_type", sa.String(length=32), nullable=False),
            sa.Column("target_id", sa.UUID(), nullable=False),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("ai_principal", sa.String(length=128), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("risk_tier", sa.String(length=16), nullable=False),
            sa.Column("input_hash", sa.String(length=64), nullable=False),
            sa.Column("policy_outcome", sa.String(length=32), nullable=False),
            sa.Column(
                "evidence_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "decision_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("rejection_reason", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=128), nullable=False),
            sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_ai_full_mode_decisions"),
            sa.ForeignKeyConstraint(
                ["research_space_id"],
                [graph_spaces_fk],
                name="fk_ai_full_mode_decisions_space",
            ),
            sa.CheckConstraint(
                "target_type IN ('concept_proposal', 'graph_change_proposal')",
                name="ck_ai_full_mode_decisions_target_type",
            ),
            sa.CheckConstraint(
                "action IN ('APPROVE', 'MERGE', 'REJECT', 'REQUEST_CHANGES', "
                "'APPLY_RESOLUTION_PLAN')",
                name="ck_ai_full_mode_decisions_action",
            ),
            sa.CheckConstraint(
                "status IN ('SUBMITTED', 'REJECTED', 'APPLIED')",
                name="ck_ai_full_mode_decisions_status",
            ),
            sa.CheckConstraint(
                "risk_tier IN ('low', 'medium', 'high')",
                name="ck_ai_full_mode_decisions_risk_tier",
            ),
            sa.CheckConstraint(
                "policy_outcome IN ('human_required', 'ai_allowed', "
                "'ai_allowed_when_low_risk', 'blocked')",
                name="ck_ai_full_mode_decisions_policy_outcome",
            ),
            sa.CheckConstraint(
                "confidence >= 0.0 AND confidence <= 1.0",
                name="ck_ai_full_mode_decisions_confidence",
            ),
            schema=schema,
        )
        op.create_index(
            "idx_ai_full_mode_decisions_space_target",
            "ai_full_mode_decisions",
            ["research_space_id", "target_type", "target_id"],
            schema=schema,
        )

    if not _has_table(conn, "connector_proposals", schema):
        op.create_table(
            "connector_proposals",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("research_space_id", sa.UUID(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("connector_slug", sa.String(length=128), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("connector_kind", sa.String(length=64), nullable=False),
            sa.Column("domain_context", sa.String(length=64), nullable=False),
            sa.Column(
                "metadata_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "mapping_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "validation_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column(
                "approval_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column(
                "evidence_payload",
                json_type,
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("proposed_by", sa.String(length=128), nullable=False),
            sa.Column("reviewed_by", sa.String(length=128), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decision_reason", sa.Text(), nullable=True),
            sa.Column("source_ref", sa.String(length=1024), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id", name="pk_connector_proposals"),
            sa.ForeignKeyConstraint(
                ["research_space_id"],
                [graph_spaces_fk],
                name="fk_connector_proposals_space",
            ),
            sa.ForeignKeyConstraint(
                ["domain_context"],
                [domain_contexts_fk],
                name="fk_connector_proposals_domain_context",
            ),
            sa.UniqueConstraint(
                "research_space_id",
                "connector_slug",
                name="uq_connector_proposals_space_slug",
            ),
            sa.UniqueConstraint(
                "research_space_id",
                "source_ref",
                name="uq_connector_proposals_space_source_ref",
            ),
            sa.CheckConstraint(
                "status IN ('SUBMITTED', 'CHANGES_REQUESTED', 'APPROVED', "
                "'REJECTED')",
                name="ck_connector_proposals_status",
            ),
            schema=schema,
        )
        op.create_index(
            "idx_connector_proposals_space_status",
            "connector_proposals",
            ["research_space_id", "status"],
            schema=schema,
        )
        op.create_index(
            "idx_connector_proposals_space_domain",
            "connector_proposals",
            ["research_space_id", "domain_context"],
            schema=schema,
        )


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    drops = (
        ("connector_proposals", ("idx_connector_proposals_space_domain", "idx_connector_proposals_space_status")),
        ("ai_full_mode_decisions", ("idx_ai_full_mode_decisions_space_target",)),
        ("graph_change_proposals", ("idx_graph_change_proposals_space_status",)),
        ("concept_proposals", ("idx_concept_proposals_space_label", "idx_concept_proposals_space_status")),
    )
    for table_name, index_names in drops:
        if not _has_table(conn, table_name, schema):
            continue
        for index_name in index_names:
            op.drop_index(index_name, table_name=table_name, schema=schema)
        op.drop_table(table_name, schema=schema)
