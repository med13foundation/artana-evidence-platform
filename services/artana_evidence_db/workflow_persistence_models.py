"""Persistence models for unified graph workflows."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.orm_base import Base
from artana_evidence_db.schema_support import (
    graph_table_options,
    qualify_graph_foreign_key_target,
)
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class _TimestampAuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class GraphWorkflowModel(_TimestampAuditMixin, Base):
    """Current state for one product-mode graph workflow."""

    __tablename__ = "graph_workflows"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("graph_spaces.id")),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(48), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    operating_mode: Mapped[str] = mapped_column(String(48), nullable=False)
    input_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    plan_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    generated_resources_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    decision_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    policy_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    explanation_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    source_ref: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    workflow_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "research_space_id",
            "source_ref",
            name="uq_graph_workflows_space_source_ref",
        ),
        CheckConstraint(
            "kind IN ('evidence_approval', 'batch_review', "
            "'ai_evidence_decision', 'conflict_resolution', "
            "'continuous_learning_review', 'bootstrap_review')",
            name="ck_graph_workflows_kind",
        ),
        CheckConstraint(
            "status IN ('SUBMITTED', 'PLAN_READY', 'WAITING_REVIEW', 'APPLIED', "
            "'REJECTED', 'CHANGES_REQUESTED', 'BLOCKED', 'FAILED')",
            name="ck_graph_workflows_status",
        ),
        CheckConstraint(
            "operating_mode IN ('manual', 'ai_assist_human_batch', "
            "'human_evidence_ai_graph', 'ai_full_graph', 'ai_full_evidence', "
            "'continuous_learning')",
            name="ck_graph_workflows_operating_mode",
        ),
        Index("idx_graph_workflows_space_status", "research_space_id", "status"),
        Index("idx_graph_workflows_space_kind", "research_space_id", "kind"),
        Index("idx_graph_workflows_space_source_ref", "research_space_id", "source_ref"),
        graph_table_options(comment="Unified graph workflow current-state ledger"),
    )


class GraphWorkflowEventModel(Base):
    """Append-only action history for unified graph workflows."""

    __tablename__ = "graph_workflow_events"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workflow_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(
            qualify_graph_foreign_key_target("graph_workflows.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    research_space_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey(qualify_graph_foreign_key_target("graph_spaces.id")),
        nullable=False,
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    before_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    after_status: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_tier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    computed_confidence: Mapped[float | None] = mapped_column(nullable=True)
    confidence_assessment_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    confidence_model_version: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    policy_outcome_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    generated_resources_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_payload: Mapped[JSONObject] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "after_status IN ('SUBMITTED', 'PLAN_READY', 'WAITING_REVIEW', "
            "'APPLIED', 'REJECTED', 'CHANGES_REQUESTED', 'BLOCKED', 'FAILED')",
            name="ck_graph_workflow_events_after_status",
        ),
        CheckConstraint(
            "before_status IS NULL OR before_status IN ('SUBMITTED', "
            "'PLAN_READY', 'WAITING_REVIEW', 'APPLIED', 'REJECTED', "
            "'CHANGES_REQUESTED', 'BLOCKED', 'FAILED')",
            name="ck_graph_workflow_events_before_status",
        ),
        CheckConstraint(
            "risk_tier IS NULL OR risk_tier IN ('low', 'medium', 'high')",
            name="ck_graph_workflow_events_risk_tier",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_graph_workflow_events_confidence",
        ),
        CheckConstraint(
            "computed_confidence IS NULL OR "
            "(computed_confidence >= 0.0 AND computed_confidence <= 1.0)",
            name="ck_graph_workflow_events_computed_confidence",
        ),
        Index("idx_graph_workflow_events_workflow", "workflow_id", "created_at"),
        Index("idx_graph_workflow_events_space", "research_space_id", "created_at"),
        graph_table_options(comment="Append-only unified graph workflow events"),
    )


__all__ = ["GraphWorkflowEventModel", "GraphWorkflowModel"]
