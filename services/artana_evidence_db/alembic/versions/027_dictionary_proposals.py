"""Add governed dictionary proposals."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name
from sqlalchemy.dialects import postgresql

revision = "027_dictionary_proposals"
down_revision = "026_p0_p2_schema_columns"
branch_labels = None
depends_on = None


def _has_table(conn: sa.Connection, table: str, schema: str) -> bool:
    insp = sa.inspect(conn)
    return table in insp.get_table_names(schema=schema)


def upgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if _has_table(conn, "dictionary_proposals", schema):
        return
    evidence_payload_type: sa.TypeEngine[object]
    evidence_payload_default: sa.TextClause | str
    if conn.dialect.name == "postgresql":
        evidence_payload_type = postgresql.JSONB(astext_type=sa.Text())
        evidence_payload_default = sa.text("'{}'::jsonb")
        expected_properties_type = postgresql.JSONB(astext_type=sa.Text())
        expected_properties_default = sa.text("'{}'::jsonb")
        synonyms_type = postgresql.JSONB(astext_type=sa.Text())
        synonyms_default = sa.text("'[]'::jsonb")
    else:
        evidence_payload_type = sa.JSON()
        evidence_payload_default = "{}"
        expected_properties_type = sa.JSON()
        expected_properties_default = "{}"
        synonyms_type = sa.JSON()
        synonyms_default = "[]"
    relation_constraints_fk = (
        "relation_constraints.id"
        if schema is None
        else f"{schema}.relation_constraints.id"
    )
    entity_types_fk = (
        "dictionary_entity_types.id"
        if schema is None
        else f"{schema}.dictionary_entity_types.id"
    )
    relation_types_fk = (
        "dictionary_relation_types.id"
        if schema is None
        else f"{schema}.dictionary_relation_types.id"
    )
    domain_contexts_fk = (
        "dictionary_domain_contexts.id"
        if schema is None
        else f"{schema}.dictionary_domain_contexts.id"
    )
    relation_synonyms_fk = (
        "dictionary_relation_synonyms.id"
        if schema is None
        else f"{schema}.dictionary_relation_synonyms.id"
    )
    value_sets_fk = "value_sets.id" if schema is None else f"{schema}.value_sets.id"
    value_set_items_fk = (
        "value_set_items.id" if schema is None else f"{schema}.value_set_items.id"
    )

    op.create_table(
        "dictionary_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("proposal_type", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="SUBMITTED",
        ),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("relation_type", sa.String(length=64), nullable=True),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("value_set_id", sa.String(length=64), nullable=True),
        sa.Column("variable_id", sa.String(length=64), nullable=True),
        sa.Column("code", sa.String(length=128), nullable=True),
        sa.Column("synonym", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("display_label", sa.String(length=255), nullable=True),
        sa.Column("domain_context", sa.String(length=64), nullable=True),
        sa.Column("external_ontology_ref", sa.String(length=255), nullable=True),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column(
            "expected_properties",
            expected_properties_type,
            nullable=False,
            server_default=expected_properties_default,
        ),
        sa.Column(
            "synonyms",
            synonyms_type,
            nullable=False,
            server_default=synonyms_default,
        ),
        sa.Column("is_directional", sa.Boolean(), nullable=True),
        sa.Column("inverse_label", sa.String(length=128), nullable=True),
        sa.Column("is_extensible", sa.Boolean(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("is_active_value", sa.Boolean(), nullable=True),
        sa.Column("is_allowed", sa.Boolean(), nullable=True),
        sa.Column("requires_evidence", sa.Boolean(), nullable=True),
        sa.Column("profile", sa.String(length=32), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column(
            "evidence_payload",
            evidence_payload_type,
            nullable=False,
            server_default=evidence_payload_default,
        ),
        sa.Column("proposed_by", sa.String(length=128), nullable=False),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("applied_domain_context_id", sa.String(length=64), nullable=True),
        sa.Column("applied_entity_type_id", sa.String(length=64), nullable=True),
        sa.Column("applied_relation_type_id", sa.String(length=64), nullable=True),
        sa.Column("applied_relation_synonym_id", sa.Integer(), nullable=True),
        sa.Column("applied_value_set_id", sa.String(length=64), nullable=True),
        sa.Column("applied_value_set_item_id", sa.Integer(), nullable=True),
        sa.Column("applied_constraint_id", sa.Integer(), nullable=True),
        sa.Column("source_ref", sa.String(length=1024), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "proposal_type IN ("
            "'DOMAIN_CONTEXT', 'ENTITY_TYPE', 'RELATION_TYPE', "
            "'RELATION_CONSTRAINT', 'RELATION_SYNONYM', "
            "'VALUE_SET', 'VALUE_SET_ITEM'"
            ")",
            name="ck_dictionary_proposals_type",
        ),
        sa.CheckConstraint(
            "status IN ('SUBMITTED', 'APPROVED', 'REJECTED')",
            name="ck_dictionary_proposals_status",
        ),
        sa.ForeignKeyConstraint(
            ["applied_domain_context_id"],
            [domain_contexts_fk],
        ),
        sa.ForeignKeyConstraint(
            ["applied_entity_type_id"],
            [entity_types_fk],
        ),
        sa.ForeignKeyConstraint(
            ["applied_relation_type_id"],
            [relation_types_fk],
        ),
        sa.ForeignKeyConstraint(
            ["applied_relation_synonym_id"],
            [relation_synonyms_fk],
        ),
        sa.ForeignKeyConstraint(
            ["applied_value_set_id"],
            [value_sets_fk],
        ),
        sa.ForeignKeyConstraint(
            ["applied_value_set_item_id"],
            [value_set_items_fk],
        ),
        sa.ForeignKeyConstraint(
            ["applied_constraint_id"],
            [relation_constraints_fk],
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index(
        "ix_dictionary_proposals_proposal_type",
        "dictionary_proposals",
        ["proposal_type"],
        schema=schema,
    )
    op.create_index(
        "ix_dictionary_proposals_status",
        "dictionary_proposals",
        ["status"],
        schema=schema,
    )
    op.create_index(
        "idx_dictionary_proposals_relation_triple",
        "dictionary_proposals",
        ["source_type", "relation_type", "target_type"],
        schema=schema,
    )


def downgrade() -> None:
    schema = graph_schema_name()
    conn = op.get_bind()
    if not _has_table(conn, "dictionary_proposals", schema):
        return
    op.drop_index(
        "idx_dictionary_proposals_relation_triple",
        table_name="dictionary_proposals",
        schema=schema,
    )
    op.drop_index(
        "ix_dictionary_proposals_status",
        table_name="dictionary_proposals",
        schema=schema,
    )
    op.drop_index(
        "ix_dictionary_proposals_proposal_type",
        table_name="dictionary_proposals",
        schema=schema,
    )
    op.drop_table("dictionary_proposals", schema=schema)
