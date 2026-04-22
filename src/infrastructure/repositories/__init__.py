"""Repository adapters for infrastructure layer."""

from .core import (
    SqlAlchemyDataSourceActivationRepository,
    SqlAlchemyExtractionQueueRepository,
    SqlAlchemyIngestionJobRepository,
    SqlAlchemyIngestionSchedulerJobRepository,
    SqlAlchemyIngestionSourceLockRepository,
    SqlAlchemyPipelineRunEventRepository,
    SqlAlchemyResearchSpaceRepository,
    SqlAlchemySessionRepository,
    SqlAlchemySourceDocumentRepository,
    SqlAlchemySourceRecordLedgerRepository,
    SqlAlchemySourceSyncStateRepository,
    SqlAlchemySourceTemplateRepository,
    SqlAlchemyStorageConfigurationRepository,
    SqlAlchemyStorageOperationRepository,
    SqlAlchemySystemStatusRepository,
    SqlAlchemyUserDataSourceRepository,
    SqlAlchemyUserRepository,
)
from .data_discovery import (
    SQLAlchemyDataDiscoverySessionRepository,
    SQLAlchemyDiscoveryPresetRepository,
    SQLAlchemyDiscoverySearchJobRepository,
    SQLAlchemyQueryTestResultRepository,
    SQLAlchemySourceCatalogRepository,
)
from .publication_extraction_repository import SqlAlchemyPublicationExtractionRepository
from .publication_repository import SqlAlchemyPublicationRepository

__all__ = [
    "SQLAlchemyDataDiscoverySessionRepository",
    "SQLAlchemyDiscoveryPresetRepository",
    "SQLAlchemyDiscoverySearchJobRepository",
    "SQLAlchemyQueryTestResultRepository",
    "SQLAlchemySourceCatalogRepository",
    "SqlAlchemyDataSourceActivationRepository",
    "SqlAlchemyExtractionQueueRepository",
    "SqlAlchemyIngestionJobRepository",
    "SqlAlchemyIngestionSchedulerJobRepository",
    "SqlAlchemyIngestionSourceLockRepository",
    "SqlAlchemyPipelineRunEventRepository",
    "SqlAlchemyPublicationExtractionRepository",
    "SqlAlchemyPublicationRepository",
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
