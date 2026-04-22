"""
Domain repository interfaces - abstract contracts for data access.

These interfaces define the contracts that domain services depend on,
enabling dependency inversion and testability.
"""

from .base import QuerySpecification, Repository
from .data_source_activation_repository import DataSourceActivationRepository
from .extraction_queue_repository import ExtractionQueueRepository
from .ingestion_job_repository import IngestionJobRepository
from .ingestion_scheduler_job_repository import IngestionSchedulerJobRepository
from .ingestion_source_lock_repository import IngestionSourceLockRepository
from .pipeline_run_event_repository import PipelineRunEventRepository
from .publication_extraction_repository import PublicationExtractionRepository
from .publication_repository import PublicationRepository
from .research_space_repository import ResearchSpaceRepository
from .source_document_repository import SourceDocumentRepository
from .source_record_ledger_repository import SourceRecordLedgerRepository
from .source_sync_state_repository import SourceSyncStateRepository
from .source_template_repository import SourceTemplateRepository
from .storage_repository import (
    StorageConfigurationRepository,
    StorageOperationRepository,
)
from .system_status_repository import SystemStatusRepository
from .user_data_source_repository import UserDataSourceRepository

__all__ = [
    "ExtractionQueueRepository",
    "IngestionJobRepository",
    "IngestionSchedulerJobRepository",
    "IngestionSourceLockRepository",
    "PublicationExtractionRepository",
    "PipelineRunEventRepository",
    "PublicationRepository",
    "ResearchSpaceRepository",
    "QuerySpecification",
    "Repository",
    "SourceTemplateRepository",
    "SourceDocumentRepository",
    "SourceRecordLedgerRepository",
    "SourceSyncStateRepository",
    "StorageConfigurationRepository",
    "StorageOperationRepository",
    "SystemStatusRepository",
    "UserDataSourceRepository",
    "DataSourceActivationRepository",
]
