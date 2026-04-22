"""
Infrastructure implementation for executing queries against external data sources.

This client handles both URL generation for link-based sources and API calls
for programmatic sources, following Clean Architecture principles.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, assert_never
from urllib.parse import quote

import aiohttp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.domain.entities.data_discovery_parameters import (
    AdvancedQueryParameters,
    QueryParameters,
    QueryParameterType,
)
from src.domain.entities.data_discovery_session import SourceCatalogEntry
from src.domain.repositories.data_discovery_repository import SourceQueryClient
from src.type_definitions.common import JSONObject, JSONValue

if TYPE_CHECKING:
    from aiohttp import ClientResponse

logger = logging.getLogger(__name__)


class SessionLike:
    """Thin wrapper around requests.Session with a locally typed surface."""

    def __init__(self) -> None:
        self._session = requests.Session()

    def mount(self, prefix: str | bytes, adapter: object) -> None:
        """Attach an adapter for the specified prefix."""
        if not isinstance(adapter, HTTPAdapter):
            msg = "adapter must be an HTTPAdapter instance"
            raise TypeError(msg)
        self._session.mount(prefix, adapter)

    def update_headers(self, headers: dict[str, str]) -> None:
        """Update default session headers."""
        self._session.headers.update(headers)

    def close(self) -> None:
        """Close the session."""
        self._session.close()


class QueryExecutionError(Exception):
    """Exception raised when a query execution fails."""

    def __init__(self, message: str, source_id: str, status_code: int | None = None):
        super().__init__(message)
        self.source_id = source_id
        self.status_code = status_code


class HTTPQueryClient(SourceQueryClient):
    """
    HTTP-based implementation of SourceQueryClient.

    Handles both URL generation and API calls with proper error handling,
    timeouts, and rate limiting.
    """

    def __init__(
        self,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        user_agent: str = "MED13-Workbench/1.0",
    ):
        """
        Initialize the HTTP query client.

        Args:
            timeout_seconds: Default timeout for requests
            max_retries: Maximum number of retries for failed requests
            user_agent: User agent string to send with requests
        """
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.user_agent = user_agent

        # Create a session with retry strategy
        self._session = self._create_session()

    def _create_session(self) -> SessionLike:
        """Create a requests session with retry strategy."""
        session = SessionLike()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
        )

        # Mount adapters with retry strategy
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.update_headers(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/plain, */*",
            },
        )

        return session

    async def execute_query(
        self,
        catalog_entry: SourceCatalogEntry,
        parameters: QueryParameters,
        timeout_seconds: int = 30,
    ) -> JSONObject:
        """
        Execute a query against an external data source.

        Args:
            catalog_entry: The catalog entry describing the source
            parameters: Query parameters to use
            timeout_seconds: Timeout for the query

        Returns:
            Query result data

        Raises:
            QueryExecutionError: If the query fails
        """
        if catalog_entry.param_type != QueryParameterType.API:
            msg = f"Source {catalog_entry.id} does not support API execution"
            raise QueryExecutionError(msg, catalog_entry.id)

        try:
            return await self._execute_api_query(
                catalog_entry,
                parameters,
                timeout_seconds,
            )
        except Exception as e:
            if isinstance(e, QueryExecutionError):
                raise
            msg = f"Query execution failed for source {catalog_entry.id}: {e}"
            raise QueryExecutionError(
                msg,
                catalog_entry.id,
            ) from e

    def generate_url(
        self,
        catalog_entry: SourceCatalogEntry,
        parameters: QueryParameters,
    ) -> str | None:
        """
        Generate a URL for external link sources.

        Args:
            catalog_entry: The catalog entry
            parameters: Query parameters

        Returns:
            URL string or None if parameters are invalid
        """
        if not catalog_entry.url_template:
            return None

        template = catalog_entry.url_template

        # Replace parameters in template
        if parameters.gene_symbol:
            template = template.replace("${gene}", quote(parameters.gene_symbol))

        if parameters.search_term:
            template = template.replace("${term}", quote(parameters.search_term))

        # Check if all required parameters were replaced
        if "${gene}" in template and not parameters.gene_symbol:
            return None
        if "${term}" in template and not parameters.search_term:
            return None

        return template

    def validate_parameters(
        self,
        catalog_entry: SourceCatalogEntry,
        parameters: QueryParameters,
    ) -> bool:
        """
        Validate that parameters are suitable for the source.

        Args:
            catalog_entry: The catalog entry
            parameters: Parameters to validate

        Returns:
            True if parameters are valid
        """
        if catalog_entry.param_type == QueryParameterType.GENE:
            return parameters.has_gene()
        if catalog_entry.param_type == QueryParameterType.TERM:
            return parameters.has_term()
        if catalog_entry.param_type == QueryParameterType.GENE_AND_TERM:
            return parameters.has_gene() and parameters.has_term()
        if catalog_entry.param_type == QueryParameterType.NONE:
            return True
        if catalog_entry.param_type == QueryParameterType.API:
            # API sources may have custom validation
            return True
        assert_never(catalog_entry.param_type)

    async def _execute_api_query(
        self,
        catalog_entry: SourceCatalogEntry,
        parameters: QueryParameters,
        timeout_seconds: int,
    ) -> JSONObject:
        """
        Execute an API query using aiohttp for async HTTP requests.

        Args:
            catalog_entry: The catalog entry
            parameters: Query parameters
            timeout_seconds: Request timeout

        Returns:
            API response data

        Raises:
            QueryExecutionError: If the API call fails
        """
        if not catalog_entry.api_endpoint:
            msg = f"No API endpoint configured for source {catalog_entry.id}"
            raise QueryExecutionError(msg, catalog_entry.id)

        url = catalog_entry.api_endpoint
        request_params = self._build_request_params(catalog_entry, parameters)

        try:
            async with (
                aiohttp.ClientSession(
                    headers={"User-Agent": self.user_agent},
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                ) as session,
                session.get(url, params=request_params) as response,
            ):
                response.raise_for_status()
                return await self._parse_response_payload(response)

        except aiohttp.ClientError as exc:
            msg = f"HTTP error for source {catalog_entry.id}: {exc}"
            raise QueryExecutionError(
                msg,
                catalog_entry.id,
                getattr(exc, "status", None),
            ) from exc
        except TimeoutError:
            msg = f"Timeout error for source {catalog_entry.id}"
            raise QueryExecutionError(
                msg,
                catalog_entry.id,
            ) from asyncio.TimeoutError

    def _build_request_params(
        self,
        catalog_entry: SourceCatalogEntry,
        parameters: QueryParameters,
    ) -> dict[str, str]:
        """Construct request parameters for API queries."""
        request_params: dict[str, str] = {}

        self._add_basic_params(request_params, parameters)
        self._add_advanced_params(request_params, parameters)
        self._add_config_params(request_params, catalog_entry)

        return request_params

    def _add_basic_params(
        self,
        request_params: dict[str, str],
        parameters: QueryParameters,
    ) -> None:
        if parameters.gene_symbol:
            request_params["gene"] = parameters.gene_symbol

        if parameters.search_term:
            request_params["term"] = parameters.search_term

    def _add_advanced_params(
        self,
        request_params: dict[str, str],
        parameters: QueryParameters,
    ) -> None:
        if not isinstance(parameters, AdvancedQueryParameters):
            return

        # ClinVar parameters
        if parameters.variation_types:
            request_params["variation_type"] = ",".join(parameters.variation_types)
        if parameters.clinical_significance:
            request_params["clinical_significance"] = ",".join(
                parameters.clinical_significance,
            )

        # UniProt parameters
        if parameters.is_reviewed is not None:
            request_params["reviewed"] = "true" if parameters.is_reviewed else "false"
        if parameters.organism:
            request_params["organism"] = parameters.organism

    def _add_config_params(
        self,
        request_params: dict[str, str],
        catalog_entry: SourceCatalogEntry,
    ) -> None:
        configuration = getattr(catalog_entry, "configuration", None)
        if not configuration:
            return

        if hasattr(configuration, "model_dump"):
            config_dict = configuration.model_dump()
        elif isinstance(configuration, dict):
            config_dict = configuration
        else:
            config_dict = None

        if isinstance(config_dict, dict):
            api_params = config_dict.get("api_params", {})
            if isinstance(api_params, dict):
                request_params.update(
                    {str(key): str(value) for key, value in api_params.items()},
                )

    async def _parse_response_payload(
        self,
        response: "ClientResponse",
    ) -> JSONObject:
        """Parse API response payload with JSON/text fallback."""
        try:
            raw_payload = await response.json()
            data = self._coerce_json_value(raw_payload)
        except aiohttp.ContentTypeError:
            text = await response.text()
            data = {"response": text, "content_type": response.content_type}

        return {
            "status_code": response.status,
            "data": data,
            "url": str(response.url),
            "timestamp": asyncio.get_event_loop().time(),
        }

    def close(self) -> None:
        """Close the underlying HTTP session."""
        if hasattr(self, "_session"):
            self._session.close()

    @staticmethod
    def _coerce_json_value(value: object) -> JSONValue:
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        if isinstance(value, dict):
            return {
                str(key): HTTPQueryClient._coerce_json_value(val)
                for key, val in value.items()
            }
        if isinstance(value, list):
            return [HTTPQueryClient._coerce_json_value(item) for item in value]
        return str(value)
