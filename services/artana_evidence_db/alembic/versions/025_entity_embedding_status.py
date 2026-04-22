"""Add graph-owned entity embedding readiness state."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from artana_evidence_db.schema_support import graph_schema_name

revision = "025_entity_embedding_status"
down_revision = "024_source_document_audit"
branch_labels = None
depends_on = None

_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_DEFAULT_EMBEDDING_VERSION = 1


def _canonical_embedding_text(
    *,
    entity_type: str,
    display_label: str | None,
) -> str:
    normalized_parts = [
        part.strip()
        for part in (entity_type, display_label or "")
        if isinstance(part, str) and part.strip()
    ]
    return " ".join(normalized_parts)


def _fingerprint(
    *,
    entity_type: str,
    display_label: str | None,
) -> str:
    return hashlib.sha256(
        _canonical_embedding_text(
            entity_type=entity_type,
            display_label=display_label,
        ).encode("utf-8"),
    ).hexdigest()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    schema = graph_schema_name()
    if inspector.has_table("entity_embedding_status", schema=schema):
        return

    op.create_table(
        "entity_embedding_status",
        sa.Column("research_space_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("entity_id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("desired_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=100), nullable=False),
        sa.Column(
            "embedding_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "last_requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.String(length=2000), nullable=True),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            [f"{schema}.entities.id" if schema is not None else "entities.id"],
            ondelete="CASCADE",
        ),
        schema=schema,
    )
    op.create_index(
        "idx_entity_embedding_status_space",
        "entity_embedding_status",
        ["research_space_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "idx_entity_embedding_status_state",
        "entity_embedding_status",
        ["state"],
        unique=False,
        schema=schema,
    )

    if not inspector.has_table("entities", schema=schema):
        return

    metadata = sa.MetaData()
    entities = sa.Table("entities", metadata, autoload_with=bind, schema=schema)
    embeddings = (
        sa.Table("entity_embeddings", metadata, autoload_with=bind, schema=schema)
        if inspector.has_table("entity_embeddings", schema=schema)
        else None
    )
    status_table = sa.Table(
        "entity_embedding_status",
        metadata,
        autoload_with=bind,
        schema=schema,
    )

    entity_rows = bind.execute(
        sa.select(
            entities.c.research_space_id,
            entities.c.id,
            entities.c.entity_type,
            entities.c.display_label,
        ),
    ).mappings()
    now = datetime.now(UTC)
    status_rows: list[dict[str, object]] = []
    embedding_by_entity_id: dict[object, dict[str, object]] = {}
    if embeddings is not None:
        embedding_rows = bind.execute(
            sa.select(
                embeddings.c.entity_id,
                embeddings.c.embedding_model,
                embeddings.c.embedding_version,
                embeddings.c.updated_at,
            ),
        ).mappings()
        embedding_by_entity_id = {row["entity_id"]: dict(row) for row in embedding_rows}

    for row in entity_rows:
        embedding_row = embedding_by_entity_id.get(row["id"])
        state = "ready" if embedding_row is not None else "pending"
        refreshed_at = (
            embedding_row.get("updated_at") if embedding_row is not None else None
        )
        status_rows.append(
            {
                "research_space_id": row["research_space_id"],
                "entity_id": row["id"],
                "state": state,
                "desired_fingerprint": _fingerprint(
                    entity_type=str(row["entity_type"]),
                    display_label=(
                        str(row["display_label"])
                        if row["display_label"] is not None
                        else None
                    ),
                ),
                "embedding_model": (
                    str(embedding_row["embedding_model"])
                    if embedding_row is not None
                    and embedding_row.get("embedding_model") is not None
                    else _DEFAULT_EMBEDDING_MODEL
                ),
                "embedding_version": (
                    int(embedding_row["embedding_version"])
                    if embedding_row is not None
                    and embedding_row.get("embedding_version") is not None
                    else _DEFAULT_EMBEDDING_VERSION
                ),
                "last_requested_at": now,
                "last_attempted_at": refreshed_at,
                "last_refreshed_at": refreshed_at,
                "last_error_code": None,
                "last_error_message": None,
            },
        )

    if status_rows:
        op.bulk_insert(status_table, status_rows)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    schema = graph_schema_name()
    if not inspector.has_table("entity_embedding_status", schema=schema):
        return
    op.drop_index(
        "idx_entity_embedding_status_state",
        table_name="entity_embedding_status",
        schema=schema,
    )
    op.drop_index(
        "idx_entity_embedding_status_space",
        table_name="entity_embedding_status",
        schema=schema,
    )
    op.drop_table("entity_embedding_status", schema=schema)
