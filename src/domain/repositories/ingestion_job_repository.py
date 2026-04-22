"""
Repository interface for Ingestion Job entities.

Defines the contract for data access operations on data ingestion jobs,
providing monitoring and tracking capabilities for data source ingestion.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from src.domain.entities.ingestion_job import (
    IngestionError,
    IngestionJob,
    IngestionJobKind,
    IngestionStatus,
    IngestionTrigger,
    JobMetrics,
)
from src.type_definitions.common import JSONObject


class IngestionJobRepository(ABC):
    """
    Abstract repository for IngestionJob entities.

    Defines the interface for CRUD operations and specialized queries
    related to data ingestion job executions.
    """

    @abstractmethod
    def save(self, job: IngestionJob) -> IngestionJob:
        """
        Save an ingestion job to the repository.

        Args:
            job: The IngestionJob entity to save

        Returns:
            The saved IngestionJob with any generated fields populated
        """

    @abstractmethod
    def find_by_id(self, job_id: UUID) -> IngestionJob | None:
        """
        Find an ingestion job by its ID.

        Args:
            job_id: The unique identifier of the job

        Returns:
            The IngestionJob if found, None otherwise
        """

    @abstractmethod
    def find_by_source(
        self,
        source_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        """
        Find all ingestion jobs for a specific data source.

        Args:
            source_id: The ID of the data source
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of IngestionJob entities for the source
        """

    @abstractmethod
    def find_by_trigger(
        self,
        trigger: IngestionTrigger,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        """
        Find all ingestion jobs triggered by a specific method.

        Args:
            trigger: The trigger type to filter by
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of IngestionJob entities with the specified trigger
        """

    @abstractmethod
    def find_by_status(
        self,
        status: IngestionStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        """
        Find all ingestion jobs with a specific status.

        Args:
            status: The status to filter by
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of IngestionJob entities with the specified status
        """

    @abstractmethod
    def find_running_jobs(self, skip: int = 0, limit: int = 50) -> list[IngestionJob]:
        """
        Find all currently running ingestion jobs.

        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of running IngestionJob entities
        """

    @abstractmethod
    def find_failed_jobs(
        self,
        since: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        """
        Find all failed ingestion jobs, optionally since a specific time.

        Args:
            since: Only return jobs failed after this time (optional)
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of failed IngestionJob entities
        """

    @abstractmethod
    def find_recent_jobs(
        self,
        hours: int = 24,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        """
        Find ingestion jobs from the last N hours.

        Args:
            hours: Number of hours to look back
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of recent IngestionJob entities
        """

    @abstractmethod
    def find_by_triggered_by(
        self,
        user_id: UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        """
        Find all ingestion jobs triggered by a specific user.

        Args:
            user_id: The ID of the user who triggered the jobs
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return

        Returns:
            List of IngestionJob entities triggered by the user
        """

    @abstractmethod
    def update_status(
        self,
        job_id: UUID,
        status: IngestionStatus,
    ) -> IngestionJob | None:
        """
        Update the status of an ingestion job.

        Args:
            job_id: The ID of the job to update
            status: The new status

        Returns:
            The updated IngestionJob if found, None otherwise
        """

    @abstractmethod
    def update_metrics(
        self,
        job_id: UUID,
        metrics: JobMetrics,
    ) -> IngestionJob | None:
        """
        Update the metrics of an ingestion job.

        Args:
            job_id: The ID of the job to update
            metrics: The new metrics

        Returns:
            The updated IngestionJob if found, None otherwise
        """

    @abstractmethod
    def add_error(self, job_id: UUID, error: IngestionError) -> IngestionJob | None:
        """
        Add an error to an ingestion job.

        Args:
            job_id: The ID of the job
            error: The error to add

        Returns:
            The updated IngestionJob if found, None otherwise
        """

    @abstractmethod
    def start_job(self, job_id: UUID) -> IngestionJob | None:
        """
        Mark a job as started.

        Args:
            job_id: The ID of the job

        Returns:
            The updated IngestionJob if found, None otherwise
        """

    @abstractmethod
    def complete_job(self, job_id: UUID, metrics: JobMetrics) -> IngestionJob | None:
        """
        Mark a job as completed with final metrics.

        Args:
            job_id: The ID of the job
            metrics: The final job metrics

        Returns:
            The updated IngestionJob if found, None otherwise
        """

    @abstractmethod
    def fail_job(self, job_id: UUID, error: IngestionError) -> IngestionJob | None:
        """
        Mark a job as failed with an error.

        Args:
            job_id: The ID of the job
            error: The error that caused the failure

        Returns:
            The updated IngestionJob if found, None otherwise
        """

    @abstractmethod
    def cancel_job(self, job_id: UUID) -> IngestionJob | None:
        """
        Mark a job as cancelled.

        Args:
            job_id: The ID of the job

        Returns:
            The updated IngestionJob if found, None otherwise
        """

    @abstractmethod
    def delete_old_jobs(self, days: int = 90) -> int:
        """
        Delete ingestion jobs older than the specified number of days.

        Args:
            days: Number of days of history to keep

        Returns:
            Number of jobs deleted
        """

    @abstractmethod
    def count_by_source(self, source_id: UUID) -> int:
        """
        Count the number of ingestion jobs for a specific source.

        Args:
            source_id: The source ID

        Returns:
            The count of jobs for the source
        """

    @abstractmethod
    def count_by_status(self, status: IngestionStatus) -> int:
        """
        Count the number of jobs with a specific status.

        Args:
            status: The status to count

        Returns:
            The count of jobs with the specified status
        """

    @abstractmethod
    def count_by_trigger(self, trigger: IngestionTrigger) -> int:
        """
        Count the number of jobs triggered by a specific method.

        Args:
            trigger: The trigger type to count

        Returns:
            The count of jobs with the specified trigger
        """

    @abstractmethod
    def exists(self, job_id: UUID) -> bool:
        """
        Check if an ingestion job exists.

        Args:
            job_id: The ID to check

        Returns:
            True if exists, False otherwise
        """

    @abstractmethod
    def get_job_statistics(self, source_id: UUID | None = None) -> JSONObject:
        """
        Get statistics about ingestion jobs, optionally for a specific source.

        Args:
            source_id: Optional source ID to filter by

        Returns:
            Dictionary with various statistics
        """

    @abstractmethod
    def get_recent_failures(
        self,
        limit: int = 10,
    ) -> list[tuple[IngestionJob, IngestionError]]:
        """
        Get the most recent failed jobs with their primary error.

        Args:
            limit: Maximum number of failures to return

        Returns:
            List of tuples containing (job, primary_error)
        """

    @abstractmethod
    def find_latest_by_source_and_kind(
        self,
        *,
        source_id: UUID,
        job_kind: IngestionJobKind,
        limit: int = 50,
    ) -> list[IngestionJob]:
        """Return recent jobs for one source filtered by logical job kind."""

    @abstractmethod
    def find_active_pipeline_job_for_source(
        self,
        *,
        source_id: UUID,
        exclude_run_id: str | None = None,
    ) -> IngestionJob | None:
        """Return the queued, retrying, or running pipeline job for a source."""

    @abstractmethod
    def count_active_pipeline_queue_jobs(self) -> int:
        """Return the number of queued or retrying pipeline jobs."""

    @abstractmethod
    def claim_next_pipeline_job(
        self,
        *,
        worker_id: str,
        as_of: datetime,
    ) -> IngestionJob | None:
        """Atomically claim the next queued pipeline job for worker execution."""

    @abstractmethod
    def heartbeat_pipeline_job(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        heartbeat_at: datetime,
    ) -> IngestionJob | None:
        """Refresh pipeline-run worker heartbeat metadata for an active job."""

    @abstractmethod
    def mark_pipeline_job_retryable(
        self,
        *,
        job_id: UUID,
        worker_id: str,
        next_attempt_at: datetime,
        last_error: str,
        error_category: str | None,
    ) -> IngestionJob | None:
        """Return a running pipeline job to the queue for retry."""
