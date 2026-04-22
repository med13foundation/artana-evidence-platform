"""Query execution mixin for data discovery service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID, uuid4  # noqa: TCH003

from src.domain.entities import (
    data_discovery_parameters,
    data_discovery_session,
    user_data_source,
)

from .source_configuration_methods import QuerySourceConfigurationMixin

if TYPE_CHECKING:
    from src.application.services.data_discovery_service.requests import (
        AddSourceToSpaceRequest,
        ExecuteQueryTestRequest,
    )
    from src.application.services.pubmed_query_builder import PubMedQueryBuilder
    from src.application.services.source_management_service import (
        SourceManagementService,
    )
    from src.domain.repositories.data_discovery_repository import (
        QueryTestResultRepository,
        SourceQueryClient,
    )
    from src.domain.repositories.source_template_repository import (
        SourceTemplateRepository,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class QueryExecutionMixin(QuerySourceConfigurationMixin):
    _query_repo: QueryTestResultRepository
    _query_client: SourceQueryClient
    _source_service: SourceManagementService
    _template_repo: SourceTemplateRepository | None
    _pubmed_query_builder: PubMedQueryBuilder

    async def execute_query_test(
        self,
        request: ExecuteQueryTestRequest,
        owner_id: UUID | None = None,
    ) -> data_discovery_session.QueryTestResult | None:
        # Get session and catalog entry
        session = (
            self._session_repo.find_owned_session(request.session_id, owner_id)
            if owner_id
            else self._session_repo.find_by_id(request.session_id)
        )
        catalog_entry = self._catalog_repo.find_by_id(request.catalog_entry_id)

        if not session or not catalog_entry:
            logger.warning(
                "Session %s or catalog entry %s not found",
                request.session_id,
                request.catalog_entry_id,
            )
            return None

        if not self._can_execute_source(
            request.catalog_entry_id,
            session.research_space_id,
        ):
            logger.warning(
                "Catalog entry %s disabled for execution in session %s",
                request.catalog_entry_id,
                request.session_id,
            )
            return None

        # Use request parameters if provided, else session parameters
        parameters = request.parameters or session.current_parameters

        # Validate parameters
        if not self._query_client.validate_parameters(
            catalog_entry,
            parameters,
        ):
            logger.warning("Invalid parameters for source %s", request.catalog_entry_id)
            # Create failed result
            failed_result = data_discovery_session.QueryTestResult(
                id=uuid4(),
                catalog_entry_id=request.catalog_entry_id,
                session_id=request.session_id,
                parameters=parameters,
                status=data_discovery_parameters.TestResultStatus.VALIDATION_FAILED,
                error_message="Invalid parameters for this source",
                response_data=None,
                response_url=None,
                execution_time_ms=None,
                data_quality_score=None,
                completed_at=None,
            )
            return self._query_repo.save(failed_result)

        error_message: str | None = None
        response_data: JSONObject | None = None
        response_url: str | None = None

        try:
            # Execute the query
            if (
                catalog_entry.param_type
                == data_discovery_parameters.QueryParameterType.API
            ):
                # For API sources, execute actual query
                result_data = await self._query_client.execute_query(
                    catalog_entry,
                    parameters,
                    request.timeout_seconds,
                )
                status = data_discovery_parameters.TestResultStatus.SUCCESS
                response_data = result_data
                response_url = None
            else:
                # For URL sources, generate URL
                response_url = self._query_client.generate_url(
                    catalog_entry,
                    parameters,
                )
                status = (
                    data_discovery_parameters.TestResultStatus.SUCCESS
                    if response_url
                    else data_discovery_parameters.TestResultStatus.ERROR
                )
                response_data = None
                if not response_url:
                    error_message = "Failed to generate URL"

            # Create test result
            test_result = data_discovery_session.QueryTestResult(
                id=uuid4(),
                catalog_entry_id=request.catalog_entry_id,
                session_id=request.session_id,
                parameters=parameters,
                status=status,
                response_data=response_data,
                response_url=response_url,
                error_message=error_message,
                execution_time_ms=None,
                data_quality_score=None,
                completed_at=None,
            )

            # Save result
            saved_result = self._query_repo.save(test_result)

            # Update session statistics
            updated_session = session.record_test(
                request.catalog_entry_id,
                success=status == data_discovery_parameters.TestResultStatus.SUCCESS,
            )
            self._session_repo.save(updated_session)

            # Update catalog usage stats
            self._catalog_repo.update_usage_stats(
                request.catalog_entry_id,
                success=status == data_discovery_parameters.TestResultStatus.SUCCESS,
            )

        except Exception as e:
            logger.exception(
                "Query test failed for source %s",
                request.catalog_entry_id,
            )

            # Create error result
            error_result = data_discovery_session.QueryTestResult(
                id=uuid4(),
                catalog_entry_id=request.catalog_entry_id,
                session_id=request.session_id,
                parameters=session.current_parameters,
                status=data_discovery_parameters.TestResultStatus.ERROR,
                error_message=str(e),
                response_data=None,
                response_url=None,
                execution_time_ms=None,
                data_quality_score=None,
                completed_at=None,
            )
            saved_result = self._query_repo.save(error_result)

            # Update session with failed test
            updated_session = session.record_test(
                request.catalog_entry_id,
                success=False,
            )
            self._session_repo.save(updated_session)

            return saved_result
        else:
            logger.info(
                "Executed query test for source %s in session %s",
                request.catalog_entry_id,
                request.session_id,
            )
            return saved_result

    def get_session_test_results(
        self,
        session_id: UUID,
    ) -> list[data_discovery_session.QueryTestResult]:
        return self._query_repo.find_by_session(session_id)

    async def add_source_to_space(
        self,
        request: AddSourceToSpaceRequest,
        owner_id: UUID | None = None,
    ) -> UUID | None:
        session, catalog_entry = self._get_session_and_entry(request, owner_id)
        if not session or not catalog_entry:
            return None

        if not self._can_execute_source(
            request.catalog_entry_id,
            session.research_space_id,
        ):
            logger.warning(
                "Catalog entry %s lacks permission for space %s",
                request.catalog_entry_id,
                request.research_space_id,
            )
            return None

        # Check if source has a template
        template = None
        if catalog_entry.source_template_id and self._template_repo:
            template = self._template_repo.find_by_id(catalog_entry.source_template_id)

        resolved_source_type = self._normalize_source_type(
            template.source_type if template else catalog_entry.source_type,
            request.catalog_entry_id,
        )
        if (
            request.catalog_entry_id.lower() == "pubmed"
            and resolved_source_type == user_data_source.SourceType.API
        ):
            logger.warning(
                "Catalog entry %s resolved to api; coercing to pubmed",
                request.catalog_entry_id,
            )
            resolved_source_type = user_data_source.SourceType.PUBMED

        # Create UserDataSource
        source_config = request.source_config or {}
        source_config = self._prepare_source_configuration(
            resolved_source_type,
            source_config,
            catalog_entry,
            session.current_parameters,
        )
        configuration = user_data_source.SourceConfiguration.model_validate(
            source_config,
        )
        owner_id = session.owner_id or request.requested_by
        if owner_id is None:
            logger.warning(
                "Unable to determine owner for add_to_space; session %s",
                request.session_id,
            )
            return None
        from src.application.services.source_management_service import (
            CreateSourceRequest,
        )

        create_request = CreateSourceRequest(
            owner_id=owner_id,
            name=f"{catalog_entry.name} (from Data Discovery)",
            source_type=resolved_source_type or user_data_source.SourceType.API,
            description=f"Added from Data Source Discovery: {catalog_entry.description}",
            template_id=catalog_entry.source_template_id,
            configuration=configuration,
            research_space_id=request.research_space_id,
            tags=["data-discovery", catalog_entry.category.lower()],
            ingestion_schedule=self._build_ingestion_schedule(catalog_entry),
        )

        try:
            # Create the data source
            data_source = self._source_service.create_source(create_request)

            # Update session to mark source as added to space
            # Note: This would require extending the session entity to track added sources

        except Exception:
            logger.exception("Failed to add source to space")
            return None
        else:
            logger.info(
                "Added source %s to space %s",
                request.catalog_entry_id,
                request.research_space_id,
            )
            return data_source.id

    def _normalize_source_type(
        self,
        value: user_data_source.SourceType | str | None,
        catalog_entry_id: str,
    ) -> user_data_source.SourceType:
        if isinstance(value, user_data_source.SourceType):
            return value
        if isinstance(value, str):
            try:
                return user_data_source.SourceType(value.lower())
            except ValueError:
                logger.warning(
                    "Unknown source_type %s for catalog entry %s; defaulting to api",
                    value,
                    catalog_entry_id,
                )
        else:
            logger.warning(
                "Missing source_type for catalog entry %s; defaulting to api",
                catalog_entry_id,
            )
        return user_data_source.SourceType.API

    def _get_session_and_entry(
        self,
        request: AddSourceToSpaceRequest,
        owner_id: UUID | None,
    ) -> tuple[
        data_discovery_session.DataDiscoverySession | None,
        data_discovery_session.SourceCatalogEntry | None,
    ]:
        session = (
            self._session_repo.find_owned_session(request.session_id, owner_id)
            if owner_id
            else self._session_repo.find_by_id(request.session_id)
        )
        catalog_entry = self._catalog_repo.find_by_id(request.catalog_entry_id)

        if not session:
            logger.warning(
                "Session %s not found (owner_id: %s)",
                request.session_id,
                owner_id,
            )
            return None, None

        if not catalog_entry:
            logger.warning(
                "Catalog entry %s not found",
                request.catalog_entry_id,
            )
            return None, None

        return session, catalog_entry
