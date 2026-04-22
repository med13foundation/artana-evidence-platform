"""
Data source type definitions for Artana Resource Library.

Provides typed contracts for data source testing results.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Literal, TypedDict, TypeVar
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.type_definitions.common import JSONObject  # noqa: TC001

MetadataModelT = TypeVar("MetadataModelT", bound=BaseModel)


class IngestionIdempotencyMetadata(BaseModel):
    """Canonical idempotency metadata for ingestion runs."""

    model_config = ConfigDict(extra="forbid")

    query_signature: str | None = None
    checkpoint_kind: str | None = None
    checkpoint_before: JSONObject | None = None
    checkpoint_after: JSONObject | None = None
    new_records: int = Field(default=0, ge=0)
    updated_records: int = Field(default=0, ge=0)
    unchanged_records: int = Field(default=0, ge=0)
    skipped_records: int = Field(default=0, ge=0)

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for ingestion job metadata."""
        return {
            "query_signature": self.query_signature,
            "checkpoint_kind": self.checkpoint_kind,
            "checkpoint_before": self.checkpoint_before,
            "checkpoint_after": self.checkpoint_after,
            "new_records": self.new_records,
            "updated_records": self.updated_records,
            "unchanged_records": self.unchanged_records,
            "skipped_records": self.skipped_records,
        }


class IngestionQueryGenerationMetadata(BaseModel):
    """Typed metadata for AI query generation decisions."""

    model_config = ConfigDict(extra="forbid")

    run_id: str | None = None
    model: str | None = None
    decision: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    execution_mode: str | None = None
    fallback_reason: str | None = None
    downstream_fetched_records: int | None = Field(default=None, ge=0)
    downstream_processed_records: int | None = Field(default=None, ge=0)

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for ingestion job metadata."""
        return {
            "run_id": self.run_id,
            "model": self.model,
            "decision": self.decision,
            "confidence": self.confidence,
            "execution_mode": self.execution_mode,
            "fallback_reason": self.fallback_reason,
            "downstream_fetched_records": self.downstream_fetched_records,
            "downstream_processed_records": self.downstream_processed_records,
        }


class AliasYieldSourceMetadata(BaseModel):
    """Backend-derived alias persistence counts for one source run."""

    model_config = ConfigDict(extra="forbid")

    source_key: str
    alias_candidates_count: int = Field(default=0, ge=0)
    aliases_registered: int | None = Field(default=None, ge=0)
    aliases_persisted: int = Field(default=0, ge=0)
    aliases_skipped: int = Field(default=0, ge=0)
    alias_entities_touched: int = Field(default=0, ge=0)
    alias_errors: list[str] = Field(default_factory=list)
    aliases_persisted_by_namespace_entity_type: dict[str, int] = Field(
        default_factory=dict,
    )

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for run/reporting metadata."""
        payload: JSONObject = {
            "source_key": self.source_key,
            "alias_candidates_count": self.alias_candidates_count,
            "aliases_persisted": self.aliases_persisted,
            "aliases_skipped": self.aliases_skipped,
            "alias_entities_touched": self.alias_entities_touched,
            "alias_errors": list(self.alias_errors),
        }
        if self.aliases_registered is not None:
            payload["aliases_registered"] = self.aliases_registered
        if self.aliases_persisted_by_namespace_entity_type:
            payload["aliases_persisted_by_namespace_entity_type"] = dict(
                sorted(
                    self.aliases_persisted_by_namespace_entity_type.items(),
                ),
            )
        return payload


class AliasYieldTotalsMetadata(BaseModel):
    """Backend-derived alias persistence totals across source runs."""

    model_config = ConfigDict(extra="forbid")

    source_count: int = Field(default=0, ge=0)
    alias_candidates_count: int = Field(default=0, ge=0)
    aliases_registered: int = Field(default=0, ge=0)
    aliases_persisted: int = Field(default=0, ge=0)
    aliases_skipped: int = Field(default=0, ge=0)
    alias_entities_touched: int = Field(default=0, ge=0)
    alias_error_count: int = Field(default=0, ge=0)

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for run/reporting metadata."""
        return {
            "source_count": self.source_count,
            "alias_candidates_count": self.alias_candidates_count,
            "aliases_registered": self.aliases_registered,
            "aliases_persisted": self.aliases_persisted,
            "aliases_skipped": self.aliases_skipped,
            "alias_entities_touched": self.alias_entities_touched,
            "alias_error_count": self.alias_error_count,
        }


class AliasYieldRollupMetadata(BaseModel):
    """Backend-derived alias persistence rollup across source runs."""

    model_config = ConfigDict(extra="forbid")

    sources: dict[str, AliasYieldSourceMetadata] = Field(default_factory=dict)
    totals: AliasYieldTotalsMetadata = Field(default_factory=AliasYieldTotalsMetadata)

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for run/reporting metadata."""
        return {
            "sources": {
                key: source.to_json_object()
                for key, source in sorted(self.sources.items())
            },
            "totals": self.totals.to_json_object(),
        }


class IngestionExtractionQueueMetadata(BaseModel):
    """Typed metadata for extraction queue enqueue operations."""

    model_config = ConfigDict(extra="forbid")

    requested: int = Field(default=0, ge=0)
    queued: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    version: int = Field(default=1, ge=1)

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for ingestion job metadata."""
        return {
            "requested": self.requested,
            "queued": self.queued,
            "skipped": self.skipped,
            "version": self.version,
        }


class IngestionExtractionRunMetadata(BaseModel):
    """Typed metadata for extraction runner execution."""

    model_config = ConfigDict(extra="forbid")

    source_id: str | None = None
    ingestion_job_id: str | None = None
    requested: int = Field(default=0, ge=0)
    processed: int = Field(default=0, ge=0)
    completed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for ingestion job metadata."""
        return {
            "source_id": self.source_id,
            "ingestion_job_id": self.ingestion_job_id,
            "requested": self.requested,
            "processed": self.processed,
            "completed": self.completed,
            "skipped": self.skipped,
            "failed": self.failed,
            "started_at": (
                self.started_at.isoformat(timespec="seconds")
                if self.started_at is not None
                else None
            ),
            "completed_at": (
                self.completed_at.isoformat(timespec="seconds")
                if self.completed_at is not None
                else None
            ),
        }


class PipelineRunOwnerMetadata(BaseModel):
    """Typed ownership attribution for one orchestrated pipeline run."""

    model_config = ConfigDict(extra="forbid")

    run_owner_user_id: str | None = None
    run_owner_source: Literal["triggered_by", "source_owner", "system"] = "system"

    def to_json_object(self) -> JSONObject:
        return {
            "run_owner_user_id": self.run_owner_user_id,
            "run_owner_source": self.run_owner_source,
        }


class PipelineStageTimingMetadata(BaseModel):
    """Typed timing envelope for one pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    status: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    queue_wait_ms: int | None = Field(default=None, ge=0)
    timeout_budget_ms: int | None = Field(default=None, ge=0)

    def to_json_object(self) -> JSONObject:
        return {
            "stage": self.stage,
            "status": self.status,
            "started_at": (
                self.started_at.isoformat(timespec="seconds")
                if self.started_at is not None
                else None
            ),
            "completed_at": (
                self.completed_at.isoformat(timespec="seconds")
                if self.completed_at is not None
                else None
            ),
            "duration_ms": self.duration_ms,
            "queue_wait_ms": self.queue_wait_ms,
            "timeout_budget_ms": self.timeout_budget_ms,
        }


class PipelineRunTimingMetadata(BaseModel):
    """Typed timing summary for one orchestrated pipeline run."""

    model_config = ConfigDict(extra="forbid")

    total_duration_ms: int | None = Field(default=None, ge=0)
    stage_timings: dict[str, PipelineStageTimingMetadata] = Field(default_factory=dict)

    def to_json_object(self) -> JSONObject:
        return {
            "total_duration_ms": self.total_duration_ms,
            "stage_timings": {
                stage: summary.to_json_object()
                for stage, summary in self.stage_timings.items()
            },
        }


class PipelineRunCostMetadata(BaseModel):
    """Typed direct AI/tool cost summary for one orchestrated pipeline run."""

    model_config = ConfigDict(extra="forbid")

    currency: Literal["USD"] = "USD"
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    stage_costs_usd: dict[str, float] = Field(default_factory=dict)
    linked_run_ids: list[str] = Field(default_factory=list)

    def to_json_object(self) -> JSONObject:
        return {
            "currency": self.currency,
            "total_cost_usd": self.total_cost_usd,
            "stage_costs_usd": {
                str(key): value for key, value in self.stage_costs_usd.items()
            },
            "linked_run_ids": list(self.linked_run_ids),
        }


class IngestionJobMetadata(BaseModel):
    """Canonical typed envelope for ingestion job metadata."""

    model_config = ConfigDict(extra="forbid")

    executed_query: str | None = None
    query_generation: IngestionQueryGenerationMetadata | None = None
    idempotency: IngestionIdempotencyMetadata | None = None
    alias_yield: AliasYieldSourceMetadata | None = None
    extraction_queue: IngestionExtractionQueueMetadata | None = None
    extraction_run: IngestionExtractionRunMetadata | None = None

    def to_json_object(self) -> JSONObject:
        """Serialize non-empty metadata sections for persistence."""
        payload: JSONObject = {}
        if self.executed_query is not None:
            payload["executed_query"] = self.executed_query
        if self.query_generation is not None:
            payload["query_generation"] = self.query_generation.to_json_object()
        if self.idempotency is not None:
            payload["idempotency"] = self.idempotency.to_json_object()
        if self.alias_yield is not None:
            payload["alias_yield"] = self.alias_yield.to_json_object()
        if self.extraction_queue is not None:
            payload["extraction_queue"] = self.extraction_queue.to_json_object()
        if self.extraction_run is not None:
            payload["extraction_run"] = self.extraction_run.to_json_object()
        return payload

    @classmethod
    def parse_optional(cls, raw_metadata: object) -> IngestionJobMetadata | None:
        """Parse metadata payload into typed contract when possible."""
        if not isinstance(raw_metadata, dict):
            return None
        try:
            parsed = cls.model_validate(raw_metadata)
        except ValidationError:
            return None
        return parsed if parsed.to_json_object() else None


def normalize_ingestion_job_metadata(raw_metadata: object) -> JSONObject:
    """Normalize known ingestion metadata fields to typed contracts when possible."""
    if not isinstance(raw_metadata, dict):
        return {}
    parsed = IngestionJobMetadata.parse_optional(raw_metadata)
    if parsed is not None:
        return parsed.to_json_object()

    known_sections = {
        "executed_query",
        "query_generation",
        "idempotency",
        "alias_yield",
        "extraction_queue",
        "extraction_run",
    }
    normalized_payload: JSONObject = {
        str(key): value
        for key, value in raw_metadata.items()
        if str(key) not in known_sections
    }
    updates: dict[str, object] = {}
    executed_query = raw_metadata.get("executed_query")
    if isinstance(executed_query, str):
        updates["executed_query"] = executed_query

    query_generation = _parse_metadata_section(
        raw_metadata=raw_metadata,
        key="query_generation",
        model_type=IngestionQueryGenerationMetadata,
    )
    if query_generation is not None:
        updates["query_generation"] = query_generation

    idempotency = _parse_metadata_section(
        raw_metadata=raw_metadata,
        key="idempotency",
        model_type=IngestionIdempotencyMetadata,
    )
    if idempotency is not None:
        updates["idempotency"] = idempotency

    alias_yield = _parse_metadata_section(
        raw_metadata=raw_metadata,
        key="alias_yield",
        model_type=AliasYieldSourceMetadata,
    )
    if alias_yield is not None:
        updates["alias_yield"] = alias_yield

    extraction_queue = _parse_metadata_section(
        raw_metadata=raw_metadata,
        key="extraction_queue",
        model_type=IngestionExtractionQueueMetadata,
    )
    if extraction_queue is not None:
        updates["extraction_queue"] = extraction_queue

    extraction_run = _parse_metadata_section(
        raw_metadata=raw_metadata,
        key="extraction_run",
        model_type=IngestionExtractionRunMetadata,
    )
    if extraction_run is not None:
        updates["extraction_run"] = extraction_run

    typed_payload = IngestionJobMetadata.model_validate(updates)
    normalized_payload.update(typed_payload.to_json_object())
    return normalized_payload


def _parse_metadata_section(
    *,
    raw_metadata: dict[object, object],
    key: str,
    model_type: type[MetadataModelT],
) -> MetadataModelT | None:
    section_raw = raw_metadata.get(key)
    if not isinstance(section_raw, dict):
        return None
    try:
        return model_type.model_validate(section_raw)
    except ValidationError:
        return None


class DataSourceAiTestLink(BaseModel):
    """Reference link to a finding surfaced during AI testing."""

    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class DataSourceAiTestFinding(BaseModel):
    """Lightweight finding record surfaced during AI test execution."""

    model_config = ConfigDict(extra="forbid")

    title: str
    pubmed_id: str | None = None
    doi: str | None = None
    pmc_id: str | None = None
    publication_date: str | None = None
    journal: str | None = None
    links: list[DataSourceAiTestLink] = Field(default_factory=list)


class AgentRunTableSummary(BaseModel):
    """Summary of runtime state table rows recorded during a run."""

    model_config = ConfigDict(extra="forbid")

    table_name: str
    row_count: int = Field(ge=0)
    latest_created_at: datetime | None = None
    sample_rows: list[JSONObject] = Field(default_factory=list)


class DataSourceAiTestResult(BaseModel):
    """Result payload from testing an AI-managed data source configuration."""

    model_config = ConfigDict(extra="forbid")

    source_id: UUID
    model: str | None = None
    success: bool
    message: str
    executed_query: str | None = None
    search_terms: list[str] = Field(default_factory=list)
    fetched_records: int = Field(ge=0)
    sample_size: int = Field(ge=1)
    findings: list[DataSourceAiTestFinding] = Field(default_factory=list)
    checked_at: datetime
    agent_run_id: str | None = None
    agent_run_tables: list[AgentRunTableSummary] = Field(default_factory=list)


class SourceCatalogEntrySeed(TypedDict, total=False):
    """Typed seed data for source catalog entries."""

    id: str
    name: str
    description: str
    category: str
    param_type: str
    url_template: str
    api_endpoint: str
    tags: list[str]
    is_active: bool
    requires_auth: bool
    source_type: str
    query_capabilities: JSONObject


__all__ = [
    "AliasYieldRollupMetadata",
    "AliasYieldSourceMetadata",
    "AliasYieldTotalsMetadata",
    "DataSourceAiTestFinding",
    "DataSourceAiTestLink",
    "DataSourceAiTestResult",
    "AgentRunTableSummary",
    "IngestionExtractionQueueMetadata",
    "IngestionExtractionRunMetadata",
    "IngestionIdempotencyMetadata",
    "IngestionJobMetadata",
    "IngestionQueryGenerationMetadata",
    "PipelineRunCostMetadata",
    "PipelineRunOwnerMetadata",
    "PipelineRunTimingMetadata",
    "PipelineStageTimingMetadata",
    "normalize_ingestion_job_metadata",
    "SourceCatalogEntrySeed",
]
