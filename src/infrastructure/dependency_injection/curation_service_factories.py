"""
Factory mixin for curation and extraction application services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.domain.entities.user_data_source import SourceType
from src.infrastructure.extraction import (
    AiRequiredPubMedExtractionProcessor,
    ClinVarExtractionProcessor,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from src.application.services import (
        ExtractionQueueService,
        ExtractionRunnerService,
        PublicationExtractionService,
        StorageOperationCoordinator,
    )


class CurationServiceFactoryMixin:
    """Provides factory methods for curation and extraction application services."""

    if TYPE_CHECKING:

        def create_storage_operation_coordinator(
            self,
            session: Session,
        ) -> StorageOperationCoordinator: ...

    def create_publication_extraction_service(
        self,
        session: Session,
    ) -> PublicationExtractionService:
        from src.application.services import PublicationExtractionService
        from src.infrastructure.repositories import (
            SqlAlchemyPublicationExtractionRepository,
        )

        extraction_repository = SqlAlchemyPublicationExtractionRepository(session)
        return PublicationExtractionService(extraction_repository)

    def create_extraction_queue_service(
        self,
        session: Session,
    ) -> ExtractionQueueService:
        from src.application.services import ExtractionQueueService
        from src.infrastructure.repositories import SqlAlchemyExtractionQueueRepository

        queue_repository = SqlAlchemyExtractionQueueRepository(session)
        return ExtractionQueueService(queue_repository=queue_repository)

    def create_extraction_runner_service(
        self,
        session: Session,
    ) -> ExtractionRunnerService:
        from src.application.services import ExtractionRunnerService
        from src.infrastructure.repositories import (
            SqlAlchemyExtractionQueueRepository,
            SqlAlchemyPublicationExtractionRepository,
            SqlAlchemyPublicationRepository,
        )

        queue_repository = SqlAlchemyExtractionQueueRepository(session)
        publication_repository = SqlAlchemyPublicationRepository(session)
        extraction_repository = SqlAlchemyPublicationExtractionRepository(session)
        processor = AiRequiredPubMedExtractionProcessor()
        storage_coordinator = self.create_storage_operation_coordinator(session)
        return ExtractionRunnerService(
            queue_repository=queue_repository,
            publication_repository=publication_repository,
            extraction_repository=extraction_repository,
            processor_registry={
                SourceType.PUBMED.value: processor,
                SourceType.CLINVAR.value: ClinVarExtractionProcessor(),
            },
            storage_coordinator=storage_coordinator,
        )
