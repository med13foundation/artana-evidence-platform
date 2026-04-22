"""Add deterministic entity-resolution columns and alias storage."""

# ruff: noqa: S608

from __future__ import annotations

import unicodedata
from collections import defaultdict

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "022_entity_resolution_hardening"
down_revision = "014_entity_mechanism_paths"
branch_labels = None
depends_on = None

_BYPASS_RLS = (
    "COALESCE(NULLIF(current_setting('app.bypass_rls', true), '')::boolean, false)"
)
_IS_ADMIN = (
    "COALESCE(NULLIF(current_setting('app.is_admin', true), '')::boolean, false)"
)
_CURRENT_USER_ID = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"


def _qualified_table(table_name: str) -> str:
    schema = graph_schema_name()
    if schema is None:
        return table_name
    return f'"{schema}"."{table_name}"'


def _graph_space_memberships() -> str:
    schema = graph_schema_name()
    if schema is None:
        return "graph_space_memberships"
    return f'"{schema}".graph_space_memberships'


def _graph_spaces() -> str:
    schema = graph_schema_name()
    if schema is None:
        return "graph_spaces"
    return f'"{schema}".graph_spaces'


def _space_access_condition(space_column: str) -> str:
    return f"""
        (
            {_BYPASS_RLS}
            OR {_IS_ADMIN}
            OR (
                {_CURRENT_USER_ID} IS NOT NULL
                AND {space_column} IN (
                    SELECT gsm.space_id
                    FROM {_graph_space_memberships()} AS gsm
                    WHERE gsm.user_id = {_CURRENT_USER_ID}
                      AND gsm.is_active = TRUE
                    UNION
                    SELECT gs.id
                    FROM {_graph_spaces()} AS gs
                    WHERE gs.owner_id = {_CURRENT_USER_ID}
                )
            )
        )
    """


def _canonicalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.split())


def _normalize(value: str) -> str:
    return _canonicalize(value).casefold()


def _has_table(
    inspector: sa.Inspector,
    table_name: str,
    *,
    schema: str | None,
) -> bool:
    return inspector.has_table(table_name, schema=schema)


def _has_column(
    inspector: sa.Inspector,
    table_name: str,
    column_name: str,
    *,
    schema: str | None,
) -> bool:
    if not _has_table(inspector, table_name, schema=schema):
        return False
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name, schema=schema)
    )


def _has_index(
    inspector: sa.Inspector,
    table_name: str,
    index_name: str,
    *,
    schema: str | None,
) -> bool:
    if not _has_table(inspector, table_name, schema=schema):
        return False
    return any(
        index["name"] == index_name
        for index in inspector.get_indexes(table_name, schema=schema)
    )


def upgrade() -> None:  # noqa: PLR0912, PLR0915
    schema = graph_schema_name()
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    entities_table = _qualified_table("entities")
    identifiers_table = _qualified_table("entity_identifiers")
    aliases_table = _qualified_table("entity_aliases")

    if not _has_column(
        inspector,
        "entities",
        "display_label_normalized",
        schema=schema,
    ):
        with op.batch_alter_table("entities", schema=schema) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "display_label_normalized",
                    sa.String(length=512),
                    nullable=True,
                ),
            )
        inspector = sa.inspect(bind)

    identifier_columns_to_add: list[sa.Column[object]] = []
    if not _has_column(
        inspector,
        "entity_identifiers",
        "research_space_id",
        schema=schema,
    ):
        identifier_columns_to_add.append(
            sa.Column("research_space_id", sa.UUID(), nullable=True),
        )
    if not _has_column(
        inspector,
        "entity_identifiers",
        "identifier_normalized",
        schema=schema,
    ):
        identifier_columns_to_add.append(
            sa.Column(
                "identifier_normalized",
                sa.String(length=512),
                nullable=True,
            ),
        )
    if identifier_columns_to_add:
        with op.batch_alter_table("entity_identifiers", schema=schema) as batch_op:
            for column in identifier_columns_to_add:
                batch_op.add_column(column)
        inspector = sa.inspect(bind)

    if not _has_table(inspector, "entity_aliases", schema=schema):
        op.create_table(
            "entity_aliases",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entity_id", sa.UUID(), nullable=False),
            sa.Column("research_space_id", sa.UUID(), nullable=False),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("alias_label", sa.String(length=512), nullable=False),
            sa.Column("alias_normalized", sa.String(length=512), nullable=False),
            sa.Column("source", sa.String(length=64), nullable=True),
            sa.Column(
                "created_by",
                sa.String(length=128),
                nullable=False,
                server_default="migration:022",
            ),
            sa.Column("source_ref", sa.String(length=1024), nullable=True),
            sa.Column(
                "review_status",
                sa.String(length=32),
                nullable=False,
                server_default="ACTIVE",
            ),
            sa.Column("reviewed_by", sa.String(length=128), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revocation_reason", sa.Text(), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "valid_from",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
            sa.Column("superseded_by", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["entity_id"],
                [f"{schema + '.' if schema else ''}entities.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["entity_type"],
                [f"{schema + '.' if schema else ''}dictionary_entity_types.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["superseded_by"],
                [f"{schema + '.' if schema else ''}entity_aliases.id"],
                ondelete="SET NULL",
            ),
            sa.CheckConstraint(
                "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))",
                name="ck_entity_aliases_active_validity",
            ),
            sa.CheckConstraint(
                "review_status IN ('ACTIVE', 'PENDING_REVIEW', 'REVOKED')",
                name="ck_entity_aliases_review_status",
            ),
            schema=schema,
            comment="Normalized aliases for deterministic entity resolution",
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "entity_aliases",
        "idx_entity_aliases_entity_active",
        schema=schema,
    ):
        op.create_index(
            "idx_entity_aliases_entity_active",
            "entity_aliases",
            ["entity_id", "is_active"],
            schema=schema,
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "entity_aliases",
        "idx_entity_aliases_space_type_normalized",
        schema=schema,
    ):
        op.create_index(
            "idx_entity_aliases_space_type_normalized",
            "entity_aliases",
            ["research_space_id", "entity_type", "alias_normalized"],
            schema=schema,
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "entity_aliases",
        "uq_entity_aliases_active_alias_scope",
        schema=schema,
    ):
        op.create_index(
            "uq_entity_aliases_active_alias_scope",
            "entity_aliases",
            ["research_space_id", "entity_type", "alias_normalized"],
            unique=True,
            schema=schema,
            postgresql_where=sa.text("is_active"),
            sqlite_where=sa.text("is_active = 1"),
        )
        inspector = sa.inspect(bind)

    entity_rows = list(
        bind.execute(
            sa.text(
                f"""
                SELECT id, research_space_id, entity_type, display_label
                FROM {entities_table}
                """,
            ),
        ).mappings(),
    )
    label_counts: dict[tuple[object, object, str], int] = defaultdict(int)
    label_rows: list[tuple[object, object, object, str, str]] = []
    for row in entity_rows:
        display_label = row["display_label"]
        if not isinstance(display_label, str):
            continue
        canonical_label = _canonicalize(display_label)
        if not canonical_label:
            continue
        normalized_label = _normalize(canonical_label)
        bind.execute(
            sa.text(
                f"""
                UPDATE {entities_table}
                SET display_label_normalized = :normalized_label
                WHERE id = :entity_id
                """,
            ),
            {
                "normalized_label": normalized_label,
                "entity_id": row["id"],
            },
        )
        key = (
            row["research_space_id"],
            row["entity_type"],
            normalized_label,
        )
        label_counts[key] += 1
        label_rows.append(
            (
                row["id"],
                row["research_space_id"],
                row["entity_type"],
                canonical_label,
                normalized_label,
            ),
        )

    for (
        entity_id,
        research_space_id,
        entity_type,
        alias_label,
        alias_normalized,
    ) in label_rows:
        key = (research_space_id, entity_type, alias_normalized)
        if label_counts[key] != 1:
            continue
        bind.execute(
            sa.text(
                f"""
                INSERT INTO {aliases_table} (
                    entity_id,
                    research_space_id,
                    entity_type,
                    alias_label,
                    alias_normalized,
                    source,
                    created_by,
                    review_status,
                    is_active,
                    valid_from
                ) VALUES (
                    :entity_id,
                    :research_space_id,
                    :entity_type,
                    :alias_label,
                    :alias_normalized,
                    :source,
                    :created_by,
                    :review_status,
                    :is_active,
                    CURRENT_TIMESTAMP
                )
                """,
            ),
            {
                "entity_id": entity_id,
                "research_space_id": research_space_id,
                "entity_type": entity_type,
                "alias_label": alias_label,
                "alias_normalized": alias_normalized,
                "source": "display_label_backfill",
                "created_by": "migration:022",
                "review_status": "ACTIVE",
                "is_active": True,
            },
        )

    identifier_rows = list(
        bind.execute(
            sa.text(
                f"""
                SELECT
                    ei.id,
                    ei.identifier_value,
                    ei.sensitivity,
                    e.research_space_id
                FROM {identifiers_table} AS ei
                JOIN {entities_table} AS e ON e.id = ei.entity_id
                """,
            ),
        ).mappings(),
    )
    for row in identifier_rows:
        normalized_identifier: str | None = None
        identifier_value = row["identifier_value"]
        sensitivity = row["sensitivity"]
        if (
            isinstance(identifier_value, str)
            and isinstance(sensitivity, str)
            and sensitivity.strip().upper() != "PHI"
        ):
            canonical_identifier = _canonicalize(identifier_value)
            if canonical_identifier:
                normalized_identifier = _normalize(canonical_identifier)
        bind.execute(
            sa.text(
                f"""
                UPDATE {identifiers_table}
                SET research_space_id = :research_space_id,
                    identifier_normalized = :identifier_normalized
                WHERE id = :identifier_id
                """,
            ),
            {
                "research_space_id": row["research_space_id"],
                "identifier_normalized": normalized_identifier,
                "identifier_id": row["id"],
            },
        )

    with op.batch_alter_table("entity_identifiers", schema=schema) as batch_op:
        batch_op.alter_column("research_space_id", nullable=False)

    inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "entities",
        "idx_entities_space_type_label_normalized",
        schema=schema,
    ):
        op.create_index(
            "idx_entities_space_type_label_normalized",
            "entities",
            ["research_space_id", "entity_type", "display_label_normalized"],
            schema=schema,
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "entity_identifiers",
        "idx_identifier_space_ns_normalized",
        schema=schema,
    ):
        op.create_index(
            "idx_identifier_space_ns_normalized",
            "entity_identifiers",
            ["research_space_id", "namespace", "identifier_normalized"],
            schema=schema,
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "entity_identifiers",
        "uq_identifier_space_ns_normalized",
        schema=schema,
    ):
        op.create_index(
            "uq_identifier_space_ns_normalized",
            "entity_identifiers",
            ["research_space_id", "namespace", "identifier_normalized"],
            unique=True,
            schema=schema,
            postgresql_where=sa.text(
                "identifier_normalized IS NOT NULL AND sensitivity <> 'PHI'",
            ),
            sqlite_where=sa.text(
                "identifier_normalized IS NOT NULL AND sensitivity <> 'PHI'",
            ),
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "entity_identifiers",
        "uq_identifier_space_ns_blind",
        schema=schema,
    ):
        op.create_index(
            "uq_identifier_space_ns_blind",
            "entity_identifiers",
            ["research_space_id", "namespace", "identifier_blind_index"],
            unique=True,
            schema=schema,
            postgresql_where=sa.text("identifier_blind_index IS NOT NULL"),
            sqlite_where=sa.text("identifier_blind_index IS NOT NULL"),
        )

    if bind.dialect.name != "postgresql":
        return

    condition = _space_access_condition("entity_aliases.research_space_id")
    op.execute(sa.text(f"ALTER TABLE {aliases_table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {aliases_table} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f'DROP POLICY IF EXISTS "rls_entity_aliases_access" ON {aliases_table}',
        ),
    )
    op.execute(
        sa.text(
            f"""
            CREATE POLICY "rls_entity_aliases_access"
            ON {aliases_table}
            FOR ALL
            USING ({condition})
            WITH CHECK ({condition})
            """,
        ),
    )


def downgrade() -> None:
    schema = graph_schema_name()
    bind = op.get_bind()
    aliases_table = _qualified_table("entity_aliases")
    inspector = sa.inspect(bind)

    if bind.dialect.name == "postgresql" and _has_table(
        inspector,
        "entity_aliases",
        schema=schema,
    ):
        op.execute(
            sa.text(
                f'DROP POLICY IF EXISTS "rls_entity_aliases_access" ON {aliases_table}',
            ),
        )
        op.execute(sa.text(f"ALTER TABLE {aliases_table} NO FORCE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"ALTER TABLE {aliases_table} DISABLE ROW LEVEL SECURITY"))

    if _has_index(
        inspector,
        "entity_identifiers",
        "uq_identifier_space_ns_blind",
        schema=schema,
    ):
        op.drop_index(
            "uq_identifier_space_ns_blind",
            table_name="entity_identifiers",
            schema=schema,
        )
    if _has_index(
        inspector,
        "entity_identifiers",
        "uq_identifier_space_ns_normalized",
        schema=schema,
    ):
        op.drop_index(
            "uq_identifier_space_ns_normalized",
            table_name="entity_identifiers",
            schema=schema,
        )
    if _has_index(
        inspector,
        "entity_identifiers",
        "idx_identifier_space_ns_normalized",
        schema=schema,
    ):
        op.drop_index(
            "idx_identifier_space_ns_normalized",
            table_name="entity_identifiers",
            schema=schema,
        )
    if _has_index(
        inspector,
        "entity_identifiers",
        "idx_identifier_blind_lookup",
        schema=schema,
    ):
        op.drop_index(
            "idx_identifier_blind_lookup",
            table_name="entity_identifiers",
            schema=schema,
        )
    if _has_index(
        inspector,
        "entities",
        "idx_entities_space_type_label_normalized",
        schema=schema,
    ):
        op.drop_index(
            "idx_entities_space_type_label_normalized",
            table_name="entities",
            schema=schema,
        )
    if _has_index(
        inspector,
        "entity_aliases",
        "uq_entity_aliases_active_alias_scope",
        schema=schema,
    ):
        op.drop_index(
            "uq_entity_aliases_active_alias_scope",
            table_name="entity_aliases",
            schema=schema,
        )
    if _has_index(
        inspector,
        "entity_aliases",
        "idx_entity_aliases_space_type_normalized",
        schema=schema,
    ):
        op.drop_index(
            "idx_entity_aliases_space_type_normalized",
            table_name="entity_aliases",
            schema=schema,
        )
    if _has_index(
        inspector,
        "entity_aliases",
        "idx_entity_aliases_entity_active",
        schema=schema,
    ):
        op.drop_index(
            "idx_entity_aliases_entity_active",
            table_name="entity_aliases",
            schema=schema,
        )
    if _has_table(inspector, "entity_aliases", schema=schema):
        op.drop_table("entity_aliases", schema=schema)

    with op.batch_alter_table("entity_identifiers", schema=schema) as batch_op:
        batch_op.drop_column("identifier_normalized")
        batch_op.drop_column("research_space_id")

    with op.batch_alter_table("entities", schema=schema) as batch_op:
        batch_op.drop_column("display_label_normalized")
