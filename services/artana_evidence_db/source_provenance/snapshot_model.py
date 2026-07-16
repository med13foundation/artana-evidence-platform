"""Immutable graph-owned source evidence snapshot persistence model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.orm_base import Base, require_table
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
    qualify_graph_table_name,
)
from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Mapped, Mapper

_source_evidence_snapshots_table = Base.metadata.tables.get(
    qualify_graph_table_name("source_evidence_snapshots"),
)
if _source_evidence_snapshots_table is None:
    _source_evidence_snapshots_table = Table(
        "source_evidence_snapshots",
        Base.metadata,
        Column("id", PGUUID(as_uuid=True), primary_key=True, default=uuid4),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("graph_spaces.id"),
                ondelete="RESTRICT",
            ),
            nullable=False,
        ),
        Column("upstream_service", String(64), nullable=False),
        Column("upstream_research_space_id", PGUUID(as_uuid=True), nullable=False),
        Column("upstream_document_id", PGUUID(as_uuid=True), nullable=False),
        Column("attested_at", TIMESTAMP(timezone=True), nullable=False),
        Column("identity_fingerprint", String(64), nullable=False),
        Column("source_kind", String(32), nullable=False),
        Column("authoritative_identifier", String(512), nullable=False),
        Column("canonical_url", Text, nullable=False),
        Column("retrieved_at", TIMESTAMP(timezone=True), nullable=False),
        Column("content_sha256", String(64), nullable=False),
        Column("version", String(255), nullable=True),
        Column("artifact_sha256", String(64), nullable=True),
        Column("canonical_text", Text, nullable=False),
        Column("source_identity_payload", JSONB, nullable=False),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        UniqueConstraint(
            "research_space_id",
            "identity_fingerprint",
            name="uq_source_evidence_snapshots_space_identity",
        ),
        Index(
            "idx_source_evidence_snapshots_space_authority",
            "research_space_id",
            "source_kind",
            "authoritative_identifier",
        ),
        Index(
            "idx_source_evidence_snapshots_content_sha256",
            "content_sha256",
        ),
        **graph_table_options(
            comment="Immutable graph-owned source text snapshots for evidence proof",
        ),
    )


class SourceEvidenceSnapshotModel(Base):
    """Durable canonical source text and identity captured at verification time."""

    __table__ = require_table(_source_evidence_snapshots_table)

    if TYPE_CHECKING:
        id: Mapped[UUID]
        research_space_id: Mapped[UUID]
        upstream_service: Mapped[str]
        upstream_research_space_id: Mapped[UUID]
        upstream_document_id: Mapped[UUID]
        attested_at: Mapped[datetime]
        identity_fingerprint: Mapped[str]
        source_kind: Mapped[str]
        authoritative_identifier: Mapped[str]
        canonical_url: Mapped[str]
        retrieved_at: Mapped[datetime]
        content_sha256: Mapped[str]
        version: Mapped[str | None]
        artifact_sha256: Mapped[str | None]
        canonical_text: Mapped[str]
        source_identity_payload: Mapped[JSONObject]
        created_at: Mapped[datetime]


def _reject_snapshot_update(
    _mapper: Mapper[SourceEvidenceSnapshotModel],
    _connection: object,
    _target: SourceEvidenceSnapshotModel,
) -> None:
    msg = "source evidence snapshots are immutable"
    raise ValueError(msg)


def _reject_snapshot_delete(
    _mapper: Mapper[SourceEvidenceSnapshotModel],
    _connection: object,
    _target: SourceEvidenceSnapshotModel,
) -> None:
    msg = "source evidence snapshots cannot be deleted"
    raise ValueError(msg)


event.listen(SourceEvidenceSnapshotModel, "before_update", _reject_snapshot_update)
event.listen(SourceEvidenceSnapshotModel, "before_delete", _reject_snapshot_delete)


__all__ = ["SourceEvidenceSnapshotModel"]
