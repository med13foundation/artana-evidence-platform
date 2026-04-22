"""
Domain contracts for API source operations.

Defines the type-safe data structures that represent API connection
tests and fetch results, along with the gateway protocol used by
infrastructure implementations. Business validation helpers live here,
while HTTP concerns are delegated to infrastructure adapters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from src.type_definitions.common import JSONObject  # noqa: TCH001

JSONPrimitive = str | int | float | bool | None


class _SourceConfigurationProtocol(Protocol):
    """Structural typing for API source configuration usage."""

    url: str | None
    auth_type: str | None
    auth_credentials: dict[str, JSONPrimitive] | None
    requests_per_minute: int | None


if TYPE_CHECKING:
    from src.domain.entities.user_data_source import (
        SourceConfiguration as _SourceConfiguration,
    )

    SourceConfiguration = _SourceConfiguration
else:
    SourceConfiguration = _SourceConfigurationProtocol


class APIRequestResult(BaseModel):
    """Result of an API request operation."""

    success: bool
    data: JSONObject | None = None
    record_count: int = 0
    response_time_ms: float = 0.0
    status_code: int | None = None
    errors: list[str] = Field(default_factory=list)
    metadata: JSONObject = Field(default_factory=dict)


class APIConnectionTest(BaseModel):
    """Result of API connection testing."""

    success: bool
    response_time_ms: float = 0.0
    status_code: int | None = None
    error_message: str | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    sample_data: JSONObject | None = None


@runtime_checkable
class APISourceGateway(Protocol):
    """Protocol describing infrastructure responsibilities for API calls."""

    async def test_connection(
        self,
        configuration: SourceConfiguration,
    ) -> APIConnectionTest: ...

    async def fetch_data(
        self,
        configuration: SourceConfiguration,
        request_parameters: JSONObject | None = None,
    ) -> APIRequestResult: ...


class APISourceService:
    """
    Domain service that coordinates API source operations.

    Handles business validation rules and delegates HTTP interactions
    to an injected infrastructure gateway.
    """

    SUPPORTED_AUTH_TYPES = {"none", "bearer", "basic", "api_key", "oauth2"}

    def __init__(self, gateway: APISourceGateway):
        """Initialize the service with an infrastructure gateway."""
        self._gateway = gateway

    async def test_connection(
        self,
        configuration: SourceConfiguration,
    ) -> APIConnectionTest:
        """Delegate connection testing to the gateway."""
        return await self._gateway.test_connection(configuration)

    async def fetch_data(
        self,
        configuration: SourceConfiguration,
        request_parameters: JSONObject | None = None,
    ) -> APIRequestResult:
        """Delegate data retrieval to the gateway."""
        params = request_parameters or {}
        return await self._gateway.fetch_data(configuration, params)

    def validate_configuration(self, configuration: SourceConfiguration) -> list[str]:
        """Validate API source configuration."""
        errors: list[str] = []
        errors.extend(self._validate_url(configuration))
        errors.extend(self._validate_auth(configuration))
        errors.extend(self._validate_rate_limit(configuration))
        return errors

    @staticmethod
    def _validate_url(configuration: SourceConfiguration) -> list[str]:
        errs: list[str] = []
        if not configuration.url:
            errs.append("API URL is required")
            return errs
        if configuration.url and not configuration.url.startswith(
            ("http://", "https://"),
        ):
            errs.append("URL must start with http:// or https://")
        return errs

    def _validate_auth(self, configuration: SourceConfiguration) -> list[str]:
        errs: list[str] = []
        auth_type = configuration.auth_type or "none"
        if auth_type not in self.SUPPORTED_AUTH_TYPES:
            errs.append(f"Unsupported authentication type: {auth_type}")
            return errs

        if auth_type != "none":
            required_fields = self._get_auth_required_fields(auth_type)
            missing_fields = [
                field
                for field in required_fields
                if not configuration.auth_credentials
                or field not in configuration.auth_credentials
            ]
            if missing_fields:
                errs.append(
                    f"Missing authentication fields for {auth_type}: {missing_fields}",
                )
        return errs

    @staticmethod
    def _validate_rate_limit(configuration: SourceConfiguration) -> list[str]:
        errs: list[str] = []
        max_rpm = 1000
        if configuration.requests_per_minute and not (
            1 <= configuration.requests_per_minute <= max_rpm
        ):
            errs.append("Requests per minute must be between 1 and 1000")
        return errs

    @staticmethod
    def _get_auth_required_fields(auth_type: str) -> list[str]:
        """Get required fields for authentication type."""
        auth_fields = {
            "bearer": ["token"],
            "basic": ["username", "password"],
            "api_key": ["key"],
            "oauth2": ["access_token"],
        }
        return auth_fields.get(auth_type, [])
