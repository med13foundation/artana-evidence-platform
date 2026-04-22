"""SQLAlchemy models for the graph-harness run catalog and domain state."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.graph_schema import graph_table_options
from src.type_definitions.common import JSONObject  # noqa: TC001

from .base import Base


class HarnessRunModel(Base):
    """Durable metadata for one harness run."""

    __tablename__ = "harness_runs"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    harness_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    graph_service_status: Mapped[str] = mapped_column(String(64), nullable=False)
    graph_service_version: Mapped[str] = mapped_column(String(128), nullable=False)

    intent: Mapped[HarnessIntentModel | None] = relationship(
        "HarnessIntentModel",
        back_populates="run",
        cascade="all, delete-orphan",
        uselist=False,
    )
    approvals: Mapped[list[HarnessApprovalModel]] = relationship(
        "HarnessApprovalModel",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    proposals: Mapped[list[HarnessProposalModel]] = relationship(
        "HarnessProposalModel",
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_harness_runs_space_created_at", "space_id", "created_at"),
        graph_table_options(comment="Durable graph-harness run metadata."),
    )


class HarnessIntentModel(Base):
    """Durable intent plan for one harness run."""

    __tablename__ = "harness_run_intents"

    run_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("harness_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_actions_payload: Mapped[list[JSONObject]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    run: Mapped[HarnessRunModel] = relationship(
        "HarnessRunModel",
        back_populates="intent",
    )

    __table_args__ = (
        Index("idx_harness_run_intents_space_run", "space_id", "run_id"),
        graph_table_options(comment="Intent plans for graph-harness runs."),
    )


class HarnessApprovalModel(Base):
    """Durable approval decisions for one harness run."""

    __tablename__ = "harness_run_approvals"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    run_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("harness_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    approval_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(128), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    run: Mapped[HarnessRunModel] = relationship(
        "HarnessRunModel",
        back_populates="approvals",
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "approval_key",
            name="uq_harness_run_approvals_run_id_approval_key",
        ),
        Index("idx_harness_run_approvals_space_run", "space_id", "run_id"),
        graph_table_options(comment="Approval decisions for graph-harness runs."),
    )


class HarnessProposalModel(Base):
    """Durable candidate proposal staged by the harness layer."""

    __tablename__ = "harness_proposals"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("harness_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ranking_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    reasoning_path: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    evidence_bundle_payload: Mapped[list[JSONObject]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    payload: Mapped[JSONObject] = mapped_column(JSON, nullable=False, default=dict)
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    run: Mapped[HarnessRunModel] = relationship(
        "HarnessRunModel",
        back_populates="proposals",
    )

    __table_args__ = (
        Index("idx_harness_proposals_space_status", "space_id", "status"),
        Index("idx_harness_proposals_space_rank", "space_id", "ranking_score"),
        graph_table_options(
            comment="Candidate proposals staged by graph-harness runs.",
        ),
    )


class HarnessScheduleModel(Base):
    """Durable schedule definitions for graph-harness workflows."""

    __tablename__ = "harness_schedules"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    harness_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    cadence: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    configuration_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    last_run_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    __table_args__ = (
        Index("idx_harness_schedules_space_updated_at", "space_id", "updated_at"),
        graph_table_options(
            comment="Schedule definitions for graph-harness workflows.",
        ),
    )


class HarnessResearchStateModel(Base):
    """Durable structured research-state snapshot for one research space."""

    __tablename__ = "harness_research_state"

    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
    )
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_hypotheses_payload: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    explored_questions_payload: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    pending_questions_payload: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    last_graph_snapshot_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    last_learning_cycle_at: Mapped[datetime | None] = mapped_column(
        DateTime(),
        nullable=True,
    )
    active_schedules_payload: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    confidence_model_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    budget_policy_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    __table_args__ = (
        Index("idx_harness_research_state_updated_at", "updated_at"),
        graph_table_options(comment="Structured research-state snapshots per space."),
    )


class HarnessGraphSnapshotModel(Base):
    """Durable run-scoped graph-context snapshot captured by the harness layer."""

    __tablename__ = "harness_graph_snapshots"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    source_run_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("harness_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_ids_payload: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    relation_ids_payload: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    graph_document_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    run: Mapped[HarnessRunModel] = relationship("HarnessRunModel")

    __table_args__ = (
        Index(
            "idx_harness_graph_snapshots_space_created_at",
            "space_id",
            "created_at",
        ),
        graph_table_options(comment="Run-scoped graph-context snapshots."),
    )


class HarnessChatSessionModel(Base):
    """Durable chat session metadata for graph-harness conversations."""

    __tablename__ = "harness_chat_sessions"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    created_by: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    last_run_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    messages: Mapped[list[HarnessChatMessageModel]] = relationship(
        "HarnessChatMessageModel",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_harness_chat_sessions_space_updated_at", "space_id", "updated_at"),
        graph_table_options(comment="Graph-harness chat session metadata."),
    )


class HarnessChatMessageModel(Base):
    """Durable message history for graph-harness chat sessions."""

    __tablename__ = "harness_chat_messages"

    id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    session_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey("harness_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    space_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    session: Mapped[HarnessChatSessionModel] = relationship(
        "HarnessChatSessionModel",
        back_populates="messages",
    )

    __table_args__ = (
        Index(
            "idx_harness_chat_messages_session_created_at",
            "session_id",
            "created_at",
        ),
        Index("idx_harness_chat_messages_space_session", "space_id", "session_id"),
        graph_table_options(comment="Message history for graph-harness chat sessions."),
    )


__all__ = [
    "HarnessApprovalModel",
    "HarnessChatMessageModel",
    "HarnessChatSessionModel",
    "HarnessGraphSnapshotModel",
    "HarnessIntentModel",
    "HarnessProposalModel",
    "HarnessResearchStateModel",
    "HarnessRunModel",
    "HarnessScheduleModel",
]
