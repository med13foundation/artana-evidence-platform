"""Service-local SQLAlchemy models for graph-harness runtime state."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from uuid import uuid4

from artana_evidence_api.db_schema import (
    harness_table_options,
    qualify_harness_foreign_key_target,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    review_items: Mapped[list[HarnessReviewItemModel]] = relationship(
        "HarnessReviewItemModel",
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_harness_runs_space_created_at", "space_id", "created_at"),
        harness_table_options(comment="Durable graph-harness run metadata."),
    )


class HarnessIntentModel(Base):
    """Durable intent plan for one harness run."""

    __tablename__ = "harness_run_intents"

    run_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey(
            qualify_harness_foreign_key_target("harness_runs.id"),
            ondelete="CASCADE",
        ),
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
        harness_table_options(comment="Intent plans for graph-harness runs."),
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
        ForeignKey(
            qualify_harness_foreign_key_target("harness_runs.id"),
            ondelete="CASCADE",
        ),
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
        harness_table_options(comment="Approval decisions for graph-harness runs."),
    )


class HarnessProposalModel(Base):
    """Durable candidate proposals staged by the harness layer."""

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
        ForeignKey(
            qualify_harness_foreign_key_target("harness_runs.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    proposal_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey(
            qualify_harness_foreign_key_target("harness_documents.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
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
    claim_fingerprint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    run: Mapped[HarnessRunModel] = relationship(
        "HarnessRunModel",
        back_populates="proposals",
    )

    __table_args__ = (
        Index("idx_harness_proposals_space_status", "space_id", "status"),
        Index("idx_harness_proposals_space_rank", "space_id", "ranking_score"),
        Index("idx_harness_proposals_document_id", "document_id"),
        harness_table_options(
            comment="Candidate proposals staged by graph-harness runs.",
        ),
    )


class HarnessReviewItemModel(Base):
    """Durable review-only items staged by the harness layer."""

    __tablename__ = "harness_review_items"

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
        ForeignKey(
            qualify_harness_foreign_key_target("harness_runs.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    review_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_family: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    document_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey(
            qualify_harness_foreign_key_target("harness_documents.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ranking_score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
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
    review_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    linked_proposal_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    linked_approval_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    run: Mapped[HarnessRunModel] = relationship(
        "HarnessRunModel",
        back_populates="review_items",
    )

    __table_args__ = (
        Index(
            "uq_harness_review_items_space_review_fingerprint",
            "space_id",
            "review_fingerprint",
            unique=True,
            postgresql_where=text("review_fingerprint IS NOT NULL"),
            sqlite_where=text("review_fingerprint IS NOT NULL"),
        ),
        Index(
            "uq_harness_review_items_space_type_source_key_null_fp",
            "space_id",
            "review_type",
            "source_key",
            unique=True,
            postgresql_where=text("review_fingerprint IS NULL"),
            sqlite_where=text("review_fingerprint IS NULL"),
        ),
        Index("idx_harness_review_items_space_status", "space_id", "status"),
        Index("idx_harness_review_items_space_rank", "space_id", "ranking_score"),
        Index("idx_harness_review_items_document_id", "document_id"),
        harness_table_options(
            comment="Review-only items staged by graph-harness runs.",
        ),
    )


class HarnessDocumentModel(Base):
    """Tracked source documents staged through the harness layer."""

    __tablename__ = "harness_documents"

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
    created_by: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    byte_size: Mapped[int] = mapped_column(nullable=False)
    page_count: Mapped[int | None] = mapped_column(nullable=True)
    text_content: Mapped[str] = mapped_column(Text, nullable=False)
    text_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    raw_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enriched_storage_key: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
    )
    ingestion_run_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey(
            qualify_harness_foreign_key_target("harness_runs.id"),
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    last_enrichment_run_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey(
            qualify_harness_foreign_key_target("harness_runs.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    last_extraction_run_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        ForeignKey(
            qualify_harness_foreign_key_target("harness_runs.id"),
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    enrichment_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    extraction_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
    )
    metadata_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    __table_args__ = (
        Index("idx_harness_documents_space_updated_at", "space_id", "updated_at"),
        harness_table_options(comment="Tracked harness-side source documents."),
    )


class SourceSearchRunModel(Base):
    """Durable captured direct source-search result."""

    __tablename__ = "source_search_runs"

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
    created_by: Mapped[str] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=False,
        index=True,
    )
    source_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    query_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_payload: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    source_capture: Mapped[JSONObject] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index(
            "idx_source_search_runs_space_source_created",
            "space_id",
            "source_key",
            "created_at",
        ),
        Index("idx_source_search_runs_source_key", "source_key"),
        Index("idx_source_search_runs_status", "status"),
        harness_table_options(comment="Durable captured direct source-search runs."),
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
    active_trigger_claim_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=False),
        nullable=True,
        index=True,
    )
    active_trigger_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_harness_schedules_space_updated_at", "space_id", "updated_at"),
        harness_table_options(
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
        harness_table_options(comment="Structured research-state snapshots per space."),
    )


class HarnessGraphSnapshotModel(Base):
    """Durable run-scoped graph-context snapshots captured by the harness layer."""

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
        ForeignKey(
            qualify_harness_foreign_key_target("harness_runs.id"),
            ondelete="CASCADE",
        ),
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
        harness_table_options(comment="Run-scoped graph-context snapshots."),
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
        harness_table_options(comment="Graph-harness chat session metadata."),
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
        ForeignKey(
            qualify_harness_foreign_key_target("harness_chat_sessions.id"),
            ondelete="CASCADE",
        ),
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
        harness_table_options(
            comment="Message history for graph-harness chat sessions.",
        ),
    )


__all__ = [
    "HarnessApprovalModel",
    "HarnessChatMessageModel",
    "HarnessChatSessionModel",
    "HarnessDocumentModel",
    "HarnessGraphSnapshotModel",
    "HarnessIntentModel",
    "HarnessProposalModel",
    "HarnessResearchStateModel",
    "HarnessRunModel",
    "HarnessScheduleModel",
    "SourceSearchRunModel",
]
