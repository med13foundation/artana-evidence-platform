"""Move graph governance tables into the configured graph schema."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "009_graph_gov_schema"
down_revision = "008_graph_cp_schema"
branch_labels = None
depends_on = None

_GRAPH_GOVERNANCE_TABLES: tuple[str, ...] = (
    "dictionary_data_types",
    "dictionary_domain_contexts",
    "dictionary_sensitivity_levels",
    "dictionary_entity_types",
    "dictionary_relation_types",
    "dictionary_relation_synonyms",
    "value_sets",
    "value_set_items",
    "variable_definitions",
    "variable_synonyms",
    "transform_registry",
    "entity_resolution_policies",
    "relation_constraints",
    "dictionary_changelog",
    "concept_sets",
    "concept_members",
    "concept_aliases",
    "concept_links",
    "concept_policies",
    "concept_decisions",
    "concept_harness_results",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    target_schema = graph_schema_name()
    if target_schema is None:
        return

    inspector = sa.inspect(bind)
    op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{target_schema}"'))

    for table_name in _GRAPH_GOVERNANCE_TABLES:
        if inspector.has_table(table_name, schema=target_schema):
            continue
        if not inspector.has_table(table_name, schema="public"):
            continue
        op.execute(
            sa.text(
                f'ALTER TABLE public."{table_name}" SET SCHEMA "{target_schema}"',
            ),
        )
        inspector = sa.inspect(bind)


def downgrade() -> None:
    return None
