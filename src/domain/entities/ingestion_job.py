"""
Domain entity for data ingestion jobs in Artana Resource Library.

Ingestion jobs track the execution of data acquisition from user sources,
providing monitoring, error handling, and provenance tracking.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domain.value_objects import Provenance
from src.type_definitions.common import JSONObject


class IngestionStatus(str, Enum):
    """Status of an ingestion job."""

    PENDING = "pending"  # Job created, waiting to start
    RUNNING = "running"  # Job is currently executing
    COMPLETED = "completed"  # Job finished successfully
    FAILED = "failed"  # Job failed with error
    CANCELLED = "cancelled"  # Job was cancelled
    PARTIAL = "partial"  # Job completed but with some errors


class IngestionTrigger(str, Enum):
    """What triggered the ingestion job."""

    MANUAL = "manual"  # User manually triggered
    SCHEDULED = "scheduled"  # Scheduled execution
    API = "api"  # Via API call
    WEBHOOK = "webhook"  # External webhook trigger
    RETRY = "retry"  # Retry of failed job


class IngestionJobKind(str, Enum):
    """Logical workload class stored in the ingestion-jobs table."""

    INGESTION = "ingestion"
    PIPELINE_ORCHESTRATION = "pipeline_orchestration"


class JobMetrics(BaseModel):
    """Performance and result metrics for an ingestion job."""

    records_processed: int = Field(
        default=0,
        description="Number of records successfully processed",
    )
    records_failed: int = Field(
        default=0,
        description="Number of records that failed processing",
    )
    records_skipped: int = Field(default=0, description="Number of records skipped")
    bytes_processed: int = Field(default=0, description="Number of bytes processed")
    api_calls_made: int = Field(default=0, description="Number of API calls made")

    duration_seconds: float | None = Field(
        None,
        description="Total job duration in seconds",
    )
    records_per_second: float | None = Field(None, description="Processing rate")

    def calculate_rate(self) -> None:
        """Calculate processing rate if duration is available."""
        if self.duration_seconds and self.duration_seconds > 0:
            total_records = (
                self.records_processed + self.records_failed + self.records_skipped
            )
            self.records_per_second = total_records / self.duration_seconds

    @property
    def total_records(self) -> int:
        """Get total records handled."""
        return self.records_processed + self.records_failed + self.records_skipped

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        total = self.total_records
        return (self.records_processed / total * 100) if total > 0 else 0.0


class IngestionError(BaseModel):
    """Error information for failed ingestion operations."""

    error_type: str = Field(..., description="Type of error that occurred")
    error_message: str = Field(..., description="Human-readable error message")
    error_details: JSONObject = Field(
        default_factory=dict,
        description="Additional error details",
    )
    record_id: str | None = Field(None, description="ID of record that caused error")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When error occurred",
    )

    @property
    def is_recoverable(self) -> bool:
        """Check if error is likely recoverable."""
        recoverable_errors = [
            "timeout",
            "rate_limit",
            "temporary_failure",
            "network_error",
            "service_unavailable",
        ]
        return self.error_type in recoverable_errors


UpdatePayload = dict[str, object]


class IngestionJob(BaseModel):
    """
    Domain entity representing a data ingestion job execution.

    Tracks the complete lifecycle of data acquisition from a user source,
    including performance metrics, errors, and provenance information.
    """

    model_config = ConfigDict(frozen=True)  # Immutable - changes create new instances

    # Identity
    id: UUID = Field(..., description="Unique identifier for the ingestion job")
    source_id: UUID = Field(..., description="ID of the source being ingested")
    job_kind: IngestionJobKind = Field(
        default=IngestionJobKind.INGESTION,
        description="Logical job type stored in the shared ingestion-jobs table",
    )

    # Execution details
    trigger: IngestionTrigger = Field(..., description="What triggered this job")
    triggered_by: UUID | None = Field(
        None,
        description="User who triggered the job (if applicable)",
    )
    triggered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When job was triggered",
    )

    # Status and progress
    status: IngestionStatus = Field(
        default=IngestionStatus.PENDING,
        description="Current job status",
    )
    started_at: datetime | None = Field(
        None,
        description="When job execution started",
    )
    completed_at: datetime | None = Field(
        None,
        description="When job execution completed",
    )

    # Results and metrics
    metrics: JobMetrics = Field(
        default_factory=lambda: JobMetrics(
            records_processed=0,
            records_failed=0,
            records_skipped=0,
            bytes_processed=0,
            api_calls_made=0,
            duration_seconds=None,
            records_per_second=None,
        ),
        description="Job performance metrics",
    )
    errors: list[IngestionError] = Field(
        default_factory=list,
        description="Errors encountered during execution",
    )

    # Provenance and metadata
    provenance: Provenance = Field(..., description="Data provenance information")
    metadata: JSONObject = Field(
        default_factory=dict,
        description="Additional job metadata",
    )

    # Configuration snapshot (what was used for this job)
    source_config_snapshot: JSONObject = Field(
        default_factory=dict,
        description="Source configuration at job time",
    )
    dictionary_version_used: int = Field(
        default=0,
        ge=0,
        description="Dictionary changelog/version snapshot used during this run",
    )
    replay_policy: Literal["strict", "allow_prompt_drift", "fork_on_drift"] = Field(
        default="strict",
        description="Replay policy used for AI orchestration steps in this run",
    )

    def _clone_with_updates(self, updates: UpdatePayload) -> "IngestionJob":
        """Internal helper to produce updated immutable ingestion job instances."""
        return self.model_copy(update=updates)

    def start_execution(self) -> "IngestionJob":
        """Create new instance with execution started."""
        now = datetime.now(UTC)
        update_payload: UpdatePayload = {
            "status": IngestionStatus.RUNNING,
            "started_at": now,
        }
        return self._clone_with_updates(update_payload)

    def complete_successfully(self, metrics: JobMetrics) -> "IngestionJob":
        """Create new instance with successful completion."""
        now = datetime.now(UTC)
        updated_metrics = metrics.model_copy()
        updated_metrics.calculate_rate()

        update_payload: UpdatePayload = {
            "status": IngestionStatus.COMPLETED,
            "completed_at": now,
            "metrics": updated_metrics,
        }
        return self._clone_with_updates(update_payload)

    def fail(self, error: IngestionError) -> "IngestionJob":
        """Create new instance with failure status."""
        now = datetime.now(UTC)
        update_payload: UpdatePayload = {
            "status": IngestionStatus.FAILED,
            "completed_at": now,
            "errors": [*self.errors, error],
        }
        return self._clone_with_updates(update_payload)

    def add_error(self, error: IngestionError) -> "IngestionJob":
        """Create new instance with additional error."""
        update_payload: UpdatePayload = {
            "errors": [*self.errors, error],
        }
        return self._clone_with_updates(update_payload)

    def cancel(self) -> "IngestionJob":
        """Create new instance with cancelled status."""
        now = datetime.now(UTC)
        update_payload: UpdatePayload = {
            "status": IngestionStatus.CANCELLED,
            "completed_at": now,
        }
        return self._clone_with_updates(update_payload)

    def update_metrics(self, metrics: JobMetrics) -> "IngestionJob":
        """Create new instance with updated metrics."""
        updated_metrics = metrics.model_copy()
        updated_metrics.calculate_rate()

        update_payload: UpdatePayload = {
            "metrics": updated_metrics,
        }
        return self._clone_with_updates(update_payload)

    @property
    def is_running(self) -> bool:
        """Check if job is currently running."""
        return self.status == IngestionStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        """Check if job has finished (success or failure)."""
        return self.status in [
            IngestionStatus.COMPLETED,
            IngestionStatus.FAILED,
            IngestionStatus.CANCELLED,
        ]

    @property
    def duration(self) -> float | None:
        """Get job duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def has_errors(self) -> bool:
        """Check if job encountered any errors."""
        return len(self.errors) > 0

    @property
    def success_rate(self) -> float:
        """Get overall success rate."""
        return self.metrics.success_rate

    @property
    def can_retry(self) -> bool:
        """Check if job can be retried."""
        return self.status in [IngestionStatus.FAILED, IngestionStatus.PARTIAL] and any(
            error.is_recoverable for error in self.errors
        )

    def __str__(self) -> str:
        """String representation of the ingestion job."""
        return (
            f"IngestionJob(id={self.id}, source={self.source_id}, "
            f"kind={self.job_kind.value}, status={self.status.value}, "
            f"records={self.metrics.total_records})"
        )
