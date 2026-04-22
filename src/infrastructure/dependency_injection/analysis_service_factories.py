"""
Factory mixin for analysis and reporting application services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from artana_evidence_db.kernel_repositories import (
        KernelEntityRepository,
        KernelObservationRepository,
        KernelRelationRepository,
    )
    from sqlalchemy.orm import Session

    from src.application.export import BulkExportService
    from src.application.search import UnifiedSearchService
    from src.application.services import (
        DashboardService,
        StorageConfigurationService,
    )


class AnalysisServiceFactoryMixin:
    """Provides factory methods for analysis and reporting application services."""

    if TYPE_CHECKING:

        def create_storage_configuration_service(
            self,
            session: Session,
        ) -> StorageConfigurationService: ...

        def _build_entity_repository(
            self,
            session: Session,
        ) -> KernelEntityRepository: ...

        def _build_observation_repository(
            self,
            session: Session,
        ) -> KernelObservationRepository: ...

        def _build_relation_repository(
            self,
            session: Session,
        ) -> KernelRelationRepository: ...

    def create_export_service(
        self,
        session: Session,
    ) -> BulkExportService:
        from src.application import export as export_module

        return export_module.BulkExportService(
            entity_repo=self._build_entity_repository(session),
            observation_repo=self._build_observation_repository(session),
            relation_repo=self._build_relation_repository(session),
            storage_service=self.create_storage_configuration_service(session),
        )

    def create_search_service(
        self,
        session: Session,
    ) -> UnifiedSearchService:
        from src.application import search as search_module

        return search_module.UnifiedSearchService(
            entity_repo=self._build_entity_repository(session),
            observation_repo=self._build_observation_repository(session),
            relation_repo=self._build_relation_repository(session),
        )

    def create_dashboard_service(self, session: Session) -> DashboardService:
        from src.application.services import DashboardService

        return DashboardService(
            entity_repository=self._build_entity_repository(session),
        )
