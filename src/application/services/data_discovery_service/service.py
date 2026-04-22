"""
Application service for Data Discovery operations.

Orchestrates data discovery sessions, source catalog management, and query testing
following Clean Architecture principles with dependency injection.
"""

import logging

from pydantic import BaseModel, ConfigDict

from src.application.services.data_source_activation_service import (
    DataSourceActivationService,
)
from src.application.services.pubmed_query_builder import PubMedQueryBuilder
from src.application.services.source_management_service import SourceManagementService
from src.domain.repositories.data_discovery_repository import (
    DataDiscoverySessionRepository,
    QueryTestResultRepository,
    SourceCatalogRepository,
    SourceQueryClient,
)
from src.domain.repositories.source_template_repository import SourceTemplateRepository

from .test_methods import QueryExecutionMixin

logger = logging.getLogger(__name__)


class DataDiscoveryServiceDependencies(BaseModel):
    """Optional dependencies for data discovery service wiring."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source_template_repository: SourceTemplateRepository | None = None
    activation_service: DataSourceActivationService | None = None
    pubmed_query_builder: PubMedQueryBuilder | None = None


class DataDiscoveryService(QueryExecutionMixin):
    """
    Application service for Data Discovery operations.

    Orchestrates data discovery sessions, source discovery, query testing,
    and integration with data source management.
    """

    def __init__(  # noqa: PLR0913 - explicit dependency wiring for Clean Architecture
        self,
        data_discovery_session_repository: DataDiscoverySessionRepository,
        source_catalog_repository: SourceCatalogRepository,
        query_result_repository: QueryTestResultRepository,
        source_query_client: SourceQueryClient,
        source_management_service: SourceManagementService,
        dependencies: DataDiscoveryServiceDependencies | None = None,
    ):
        self._session_repo = data_discovery_session_repository
        self._catalog_repo = source_catalog_repository
        self._query_repo = query_result_repository
        self._query_client = source_query_client
        self._source_service = source_management_service
        resolved_dependencies = dependencies or DataDiscoveryServiceDependencies()
        self._template_repo = resolved_dependencies.source_template_repository
        self._activation_service = resolved_dependencies.activation_service
        self._pubmed_query_builder = (
            resolved_dependencies.pubmed_query_builder or PubMedQueryBuilder()
        )
