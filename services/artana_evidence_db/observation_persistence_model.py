"""Service-local ORM model for typed graph observations."""

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
    Boolean,
    CheckConstraint,
    Column,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID


def _existing_table(table_name: str) -> Table | None:
    table = Base.metadata.tables.get(table_name)
    if table is not None:
        return table
    return Base.metadata.tables.get(qualify_graph_table_name(table_name))


if TYPE_CHECKING:
    from decimal import Decimal

    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Mapped
_observations_table = _existing_table("observations")
if _observations_table is None:
    _observations_table = Table(
        "observations",
        Base.metadata,
        Column(
            "id",
            PGUUID(as_uuid=True),
            primary_key=True,
            default=uuid4,
            doc="Unique observation ID",
        ),
        Column(
            "research_space_id",
            PGUUID(as_uuid=True),
            nullable=False,
            doc="Owning research space",
        ),
        Column(
            "subject_id",
            PGUUID(as_uuid=True),
            ForeignKey(
                qualify_graph_foreign_key_target("entities.id"),
                ondelete="CASCADE",
            ),
            nullable=False,
            doc="Entity this observation belongs to",
        ),
        Column(
            "variable_id",
            String(64),
            ForeignKey(qualify_graph_foreign_key_target("variable_definitions.id")),
            nullable=False,
            doc="What was measured, FK to dictionary",
        ),
        Column(
            "value_numeric",
            Numeric,
            nullable=True,
            doc="Numeric value (INTEGER, FLOAT)",
        ),
        Column(
            "value_text",
            Text,
            nullable=True,
            doc="Free-text value (STRING)",
        ),
        Column(
            "value_date",
            TIMESTAMP(timezone=True),
            nullable=True,
            doc="Date/timestamp value (DATE)",
        ),
        Column(
            "value_coded",
            String(255),
            nullable=True,
            doc="Ontology code, e.g. HP:0001250 (CODED)",
        ),
        Column(
            "value_boolean",
            Boolean,
            nullable=True,
            doc="Boolean value (BOOLEAN)",
        ),
        Column(
            "value_json",
            JSONB(none_as_null=True),
            nullable=True,
            doc="Complex structured value (JSON)",
        ),
        Column(
            "unit",
            String(64),
            nullable=True,
            doc="Normalised unit after transform",
        ),
        Column(
            "observed_at",
            TIMESTAMP(timezone=True),
            nullable=True,
            doc="When the observation was recorded",
        ),
        Column(
            "provenance_id",
            PGUUID(as_uuid=True),
            ForeignKey(qualify_graph_foreign_key_target("provenance.id")),
            nullable=True,
            doc="Extraction/ingestion provenance chain",
        ),
        Column(
            "confidence",
            Float,
            nullable=False,
            server_default="1.0",
            doc="Confidence score 0.0-1.0",
        ),
        Column(
            "created_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
        ),
        Column(
            "updated_at",
            TIMESTAMP(timezone=True),
            nullable=False,
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
        ),
        CheckConstraint(
            (
                "(CASE WHEN value_numeric IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_text IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_date IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_coded IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_boolean IS NOT NULL THEN 1 ELSE 0 END + "
                "CASE WHEN value_json IS NOT NULL THEN 1 ELSE 0 END) = 1"
            ),
            name="ck_observations_exactly_one_value",
        ),
        Index("idx_obs_subject", "subject_id"),
        Index("idx_obs_space_variable", "research_space_id", "variable_id"),
        Index("idx_obs_space_created_at", "research_space_id", "created_at"),
        Index("idx_obs_subject_time", "subject_id", "observed_at"),
        Index("idx_obs_provenance", "provenance_id"),
        **graph_table_options(
            comment="Typed observations (EAV with dictionary validation)",
        ),
    )

_observations_table_model_table = require_table(_observations_table)

class GraphObservationModel(Base):
    """A typed observation row."""


    __table__ = _observations_table_model_table

    if TYPE_CHECKING:
        id: Mapped[UUID]
        research_space_id: Mapped[UUID]
        subject_id: Mapped[UUID]
        variable_id: Mapped[str]
        value_numeric: Mapped[Decimal | None]
        value_text: Mapped[str | None]
        value_date: Mapped[datetime | None]
        value_coded: Mapped[str | None]
        value_boolean: Mapped[bool | None]
        value_json: Mapped[JSONObject | None]
        unit: Mapped[str | None]
        observed_at: Mapped[datetime | None]
        provenance_id: Mapped[UUID | None]
        confidence: Mapped[float]
        created_at: Mapped[datetime]
        updated_at: Mapped[datetime]


ObservationModel = GraphObservationModel

__all__ = ["ObservationModel"]
