"""
Infrastructure implementation for API source operations.

Uses httpx to execute API requests while conforming to the
domain-level `APISourceGateway` protocol.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from src.domain.services.api_source_service import (
    APIConnectionTest,
    APIRequestResult,
    APISourceGateway,
)
from src.type_definitions.common import (  # noqa: TCH001
    JSONObject,
    JSONValue,
    SourceMetadata,
)

AuthHeaders = dict[str, str]
QueryParamValue = str | int | float | bool | None
QueryParamsDict = dict[str, QueryParamValue]

if TYPE_CHECKING:
    from src.domain.entities.user_data_source import SourceConfiguration

AuthConfig = Mapping[str, object]
AuthMethod = Callable[[AuthConfig], AuthHeaders | None]


class HttpxAPISourceGateway(APISourceGateway):
    """httpx-powered implementation of the API source gateway."""

    def __init__(self, timeout_seconds: int = 30, max_retries: int = 3):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.auth_methods: dict[str, AuthMethod] = {
            "none": self._auth_none,
            "bearer": self._auth_bearer,
            "basic": self._auth_basic,
            "api_key": self._auth_api_key,
            "oauth2": self._auth_oauth2,
        }

    async def test_connection(
        self,
        configuration: SourceConfiguration,
    ) -> APIConnectionTest:
        if not configuration.url:
            return APIConnectionTest(success=False, error_message="No URL provided")

        start_time = datetime.now(UTC)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                headers = self._prepare_headers(configuration)
                auth_headers = self._prepare_auth(configuration)
                if auth_headers:
                    headers.update(auth_headers)

                params: QueryParamsDict = {}
                metadata = self._metadata(configuration)
                params["limit"] = self._coerce_limit(metadata.get("limit"), default=1)

                response = await client.request(
                    method="HEAD",
                    url=configuration.url,
                    headers=headers,
                    params=params,
                )

                response_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

                method_not_allowed = 405
                if response.status_code == method_not_allowed:
                    response = await client.get(
                        url=configuration.url,
                        headers=headers,
                        params=params,
                    )
                    response_time = (
                        datetime.now(UTC) - start_time
                    ).total_seconds() * 1000

                http_ok = 200
                http_multiple_choices = 300
                success = http_ok <= response.status_code < http_multiple_choices

                sample_data = None
                if success and response.headers.get("content-type", "").startswith(
                    "application/json",
                ):
                    with contextlib.suppress(Exception):
                        sample_payload = response.json()
                        sample_data = self._ensure_json_object(sample_payload)

                return APIConnectionTest(
                    success=success,
                    response_time_ms=response_time,
                    status_code=response.status_code,
                    error_message=(
                        None
                        if success
                        else f"HTTP {response.status_code}: {response.text[:200]}"
                    ),
                    response_headers=dict(response.headers),
                    sample_data=sample_data,
                )

        except Exception as exc:  # noqa: BLE001
            response_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            return APIConnectionTest(
                success=False,
                response_time_ms=response_time,
                error_message=str(exc),
            )

    async def fetch_data(
        self,
        configuration: SourceConfiguration,
        request_parameters: Mapping[str, JSONValue] | None = None,
    ) -> APIRequestResult:
        if not configuration.url:
            return APIRequestResult(success=False, errors=["No URL provided"])

        start_time = datetime.now(UTC)
        base_params: Mapping[str, object] = (
            request_parameters if request_parameters is not None else {}
        )
        params: QueryParamsDict = self._normalize_params(base_params)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                headers = self._prepare_headers(configuration)
                auth_headers = self._prepare_auth(configuration)
                if auth_headers:
                    headers.update(auth_headers)

                metadata = self._metadata(configuration)
                url = configuration.url
                method_value = metadata.get("method")
                method = (
                    method_value.upper() if isinstance(method_value, str) else "GET"
                )
                query_params = metadata.get("query_params", {})
                if isinstance(query_params, dict):
                    params.update(self._normalize_params(query_params))

                await self._apply_rate_limiting(configuration)

                response = await self._make_request_with_retries(
                    client=client,
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                )

                if response is None:
                    return APIRequestResult(
                        success=False,
                        errors=["Failed to receive response after retries"],
                    )

                response_time = (datetime.now(UTC) - start_time).total_seconds() * 1000

                data: JSONObject | None = None
                if response.headers.get("content-type", "").startswith(
                    "application/json",
                ):
                    payload = response.json()
                    data = self._ensure_json_object(payload)

                errors: list[str] = []
                success = response.is_success and data is not None
                if not success:
                    errors.append(
                        f"HTTP {response.status_code}: {response.text[:200]}",
                    )

                metadata_payload: JSONObject = {
                    "request_url": url,
                    "params": {str(k): str(v) for k, v in params.items()},
                    "method": method,
                    "headers": dict(headers),
                }

                return APIRequestResult(
                    success=success,
                    data=data if success else None,
                    record_count=self._count_records(data),
                    response_time_ms=response_time,
                    status_code=response.status_code,
                    errors=errors,
                    metadata=metadata_payload,
                )

        except Exception as exc:  # noqa: BLE001
            response_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            return APIRequestResult(
                success=False,
                errors=[str(exc)],
                response_time_ms=response_time,
            )

    def _prepare_headers(self, configuration: SourceConfiguration) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if configuration.metadata and "headers" in configuration.metadata:
            metadata_headers = configuration.metadata["headers"]
            if isinstance(metadata_headers, dict):
                headers.update(
                    {str(key): str(value) for key, value in metadata_headers.items()},
                )

        if configuration.auth_type == "api_key" and configuration.auth_credentials:
            api_key = configuration.auth_credentials.get("key")
            header_name = configuration.auth_credentials.get("header", "X-API-Key")
            if api_key:
                headers[str(header_name)] = str(api_key)

        return headers

    def _prepare_auth(self, configuration: SourceConfiguration) -> AuthHeaders | None:
        auth_type = configuration.auth_type or "none"
        auth_method = self.auth_methods.get(auth_type)
        if auth_method and configuration.auth_credentials:
            credentials = configuration.auth_credentials
            if isinstance(credentials, dict):
                return auth_method(credentials)
        if auth_type == "none":
            return None
        if auth_method is None:
            return None
        empty_config: AuthConfig = {}
        return auth_method(empty_config)

    def _metadata(self, configuration: SourceConfiguration) -> SourceMetadata:
        return configuration.metadata

    def _coerce_limit(self, value: object | None, default: int) -> int:
        if isinstance(value, int | float | str):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return default
            return parsed if parsed > 0 else default
        return default

    async def _apply_rate_limiting(
        self,
        configuration: SourceConfiguration,
    ) -> None:
        rate_limit = configuration.requests_per_minute or 60
        delay_seconds = 60.0 / rate_limit
        if delay_seconds > 0:
            await asyncio.sleep(delay_seconds)

    async def _make_request_with_retries(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        headers: dict[str, str],
        params: QueryParamsDict,
    ) -> httpx.Response | None:
        for attempt in range(self.max_retries):
            try:
                return await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                )
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
        return None

    def _count_records(self, data: JSONObject | None) -> int:
        if data is None:
            return 0
        for key in ["data", "results", "records", "items"]:
            value = data.get(key)
            if isinstance(value, list):
                return len(value)
        return 1

    def _normalize_params(
        self,
        raw_params: Mapping[str, object],
    ) -> QueryParamsDict:
        normalized: QueryParamsDict = {}
        for key, value in raw_params.items():
            normalized[str(key)] = self._format_param_value(value)
        return normalized

    def _format_param_value(self, value: object) -> QueryParamValue:
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        return json.dumps(value)

    def _ensure_json_object(
        self,
        payload: object,
    ) -> JSONObject:
        if isinstance(payload, dict):
            return {
                str(key): self._coerce_json_value(value)
                for key, value in payload.items()
            }
        return {"value": self._coerce_json_value(payload)}

    def _coerce_json_value(self, value: object) -> JSONValue:
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        if isinstance(value, list):
            return [self._coerce_json_value(item) for item in value]
        if isinstance(value, dict):
            return {
                str(key): self._coerce_json_value(val) for key, val in value.items()
            }
        return str(value)

    def _auth_none(self, _config: AuthConfig) -> None:
        return None

    def _auth_bearer(self, config: AuthConfig) -> AuthHeaders | None:
        token = config.get("token", "")
        if token:
            return {"Authorization": f"Bearer {token}"}
        return None

    def _auth_basic(self, config: AuthConfig) -> AuthHeaders | None:
        username = config.get("username", "")
        password = config.get("password", "")
        if username and password:
            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {auth_string}"}
        return None

    def _auth_api_key(self, _config: AuthConfig) -> None:
        return None

    def _auth_oauth2(self, config: AuthConfig) -> AuthHeaders | None:
        token = config.get("access_token", "")
        if token:
            return {"Authorization": f"Bearer {token}"}
        return None
