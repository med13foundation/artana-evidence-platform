"""Transform registry ORM model for dictionary governance."""

from __future__ import annotations

from datetime import datetime

from artana_evidence_db.common_types import JSONValue
from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

_ACTIVE_VALIDITY_CHECK = (
    "((is_active AND valid_to IS NULL) OR ((NOT is_active) AND valid_to IS NOT NULL))"
)


class _TimestampAuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Record creation timestamp",
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        doc="Last update timestamp",
    )


class TransformRegistryModel(_TimestampAuditMixin, Base):
    """Registry of safe, pre-compiled unit conversions and transforms."""

    __tablename__ = "transform_registry"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        doc="Transform ID, e.g. TR_LBS_KG",
    )
    input_unit: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Source unit",
    )
    output_unit: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        doc="Target unit",
    )
    category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="UNIT_CONVERSION",
        doc="Transform category: UNIT_CONVERSION, NORMALIZATION, DERIVATION",
    )
    input_data_type: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_data_types.id")),
        nullable=True,
        doc="Optional expected input kernel data type",
    )
    output_data_type: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey(qualify_graph_foreign_key_target("dictionary_data_types.id")),
        nullable=True,
        doc="Optional output kernel data type",
    )
    implementation_ref: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Function reference, e.g. func:std_lib.convert.lbs_to_kg",
    )
    is_deterministic: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Whether transform is deterministic and side-effect free",
    )
    is_production_allowed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=false(),
        doc="Whether transform can be used by production normalization flows",
    )
    test_input: Mapped[JSONValue | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Verification input payload for runtime validation",
    )
    expected_output: Mapped[JSONValue | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Expected output payload for verification",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Human-readable transform description",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="ACTIVE or DEPRECATED",
    )
    created_by: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        server_default="seed",
        doc="Entry creator: seed, manual:{user_id}, or agent:{run_id}",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=true(),
        doc="Soft-delete flag for temporal validity",
    )
    valid_from: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        doc="Timestamp when this row became valid",
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when this row stopped being valid",
    )
    superseded_by: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Replacement transform identifier when superseded",
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        doc="Optional source reference for entry creation",
    )
    review_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default="ACTIVE",
        doc="Review status: ACTIVE, PENDING_REVIEW, REVOKED",
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        doc="Reviewer identifier",
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        doc="Timestamp when review status was updated",
    )
    revocation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Reason for revocation when review_status is REVOKED",
    )

    __table_args__ = (
        Index("idx_transform_units", "input_unit", "output_unit"),
        Index("idx_transform_category", "category"),
        Index("idx_transform_production", "is_production_allowed"),
        CheckConstraint(
            "category IN ('UNIT_CONVERSION', 'NORMALIZATION', 'DERIVATION')",
            name="ck_transform_registry_category",
        ),
        CheckConstraint(
            _ACTIVE_VALIDITY_CHECK,
            name="ck_transform_registry_active_validity",
        ),
        graph_table_options(
            comment="Registry of safe, pre-compiled unit conversions",
        ),
    )


__all__ = ["TransformRegistryModel"]
