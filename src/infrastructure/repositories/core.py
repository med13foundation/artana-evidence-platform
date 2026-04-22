"""Aggregated core repositories."""

from .data_source_activation_repository import SqlAlchemyDataSourceActivationRepository
from .extraction_queue_repository import SqlAlchemyExtractionQueueRepository
from .ingestion_job_repository import SqlAlchemyIngestionJobRepository
from .ingestion_scheduler_job_repository import (
    SqlAlchemyIngestionSchedulerJobRepository,
)
from .ingestion_source_lock_repository import SqlAlchemyIngestionSourceLockRepository
from .pipeline_run_event_repository import SqlAlchemyPipelineRunEventRepository
from .research_space_repository import SqlAlchemyResearchSpaceRepository
from .source_document_repository import SqlAlchemySourceDocumentRepository
from .source_record_ledger_repository import SqlAlchemySourceRecordLedgerRepository
from .source_sync_state_repository import SqlAlchemySourceSyncStateRepository
from .source_template_repository import SqlAlchemySourceTemplateRepository
from .sqlalchemy_session_repository import SqlAlchemySessionRepository
from .sqlalchemy_user_repository import SqlAlchemyUserRepository
from .storage_repository import (
    SqlAlchemyStorageConfigurationRepository,
    SqlAlchemyStorageOperationRepository,
)
from .system_status_repository import SqlAlchemySystemStatusRepository
from .user_data_source_repository import SqlAlchemyUserDataSourceRepository

__all__ = [
    "SqlAlchemyDataSourceActivationRepository",
    "SqlAlchemyExtractionQueueRepository",
    "SqlAlchemyIngestionJobRepository",
    "SqlAlchemyIngestionSchedulerJobRepository",
    "SqlAlchemyIngestionSourceLockRepository",
    "SqlAlchemyPipelineRunEventRepository",
    "SqlAlchemyResearchSpaceRepository",
    "SqlAlchemySourceDocumentRepository",
    "SqlAlchemySourceRecordLedgerRepository",
    "SqlAlchemySourceSyncStateRepository",
    "SqlAlchemySourceTemplateRepository",
    "SqlAlchemySessionRepository",
    "SqlAlchemyStorageConfigurationRepository",
    "SqlAlchemyStorageOperationRepository",
    "SqlAlchemySystemStatusRepository",
    "SqlAlchemyUserDataSourceRepository",
    "SqlAlchemyUserRepository",
]
