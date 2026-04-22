"""
Base ingestor for Artana Resource Library data acquisition.
Provides common functionality for API clients with rate limiting and error handling.
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from types import TracebackType

import httpx

from src.domain.value_objects import DataSource, Provenance
from src.type_definitions.common import JSONObject, JSONPrimitive, JSONValue, RawRecord


class IngestionStatus(Enum):
    """Status of an ingestion operation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class IngestionError(Exception):
    """Base exception for ingestion operations."""

    def __init__(
        self,
        message: str,
        source: str,
        details: JSONObject | None = None,
    ):
        super().__init__(message)
        self.source = source
        self.details = details or {}


@dataclass
class IngestionResult:
    """Result of an ingestion operation."""

    source: str
    status: IngestionStatus
    records_processed: int
    records_failed: int
    data: list[RawRecord]
    provenance: Provenance
    errors: list[IngestionError]
    duration_seconds: float
    timestamp: datetime


class RateLimiter:
    """Simple token bucket rate limiter."""

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute: int = requests_per_minute
        self.requests_per_second: float = requests_per_minute / 60.0
        self.tokens: float = float(requests_per_minute)
        self.last_update: float = time.time()
        self.max_tokens: float = float(requests_per_minute)

    def acquire(self) -> bool:
        """Acquire a token. Returns True if successful."""
        now = time.time()
        elapsed = now - self.last_update

        # Add tokens based on elapsed time
        self.tokens = min(
            self.max_tokens,
            self.tokens + elapsed * self.requests_per_second,
        )
        self.last_update = now

        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False

    async def wait_for_token(self) -> None:
        """Wait until a token is available."""
        while not self.acquire():
            await asyncio.sleep(1.0)


QueryParams = Mapping[str, JSONPrimitive]
HeaderMap = Mapping[str, str]


class BaseIngestor(ABC):
    """
    Abstract base class for data ingestion from biomedical sources.

    Provides common functionality for:
    - Rate limiting and retry logic
    - Error handling and circuit breaker patterns
    - Provenance tracking
    - Raw data storage
    - Progress tracking
    """

    def __init__(  # noqa: PLR0913
        self,
        source_name: str,
        base_url: str,
        requests_per_minute: int = 60,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        raw_data_dir: Path | None = None,
    ):
        self.source_name: str = source_name
        self.base_url: str = base_url
        self.rate_limiter = RateLimiter(requests_per_minute)
        self.timeout_seconds: int = timeout_seconds
        self.max_retries: int = max_retries
        # Circuit breaker threshold for consecutive failures
        self.failure_threshold: int = 3

        # Raw data storage
        self.raw_data_dir: Path = raw_data_dir or Path("data/raw") / source_name
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)

        # Circuit breaker state
        self.failure_count: int = 0
        self.last_failure_time: datetime | None = None
        self.circuit_open: bool = False

        # HTTP client
        self.client: httpx.AsyncClient = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"User-Agent": "Artana-Resource-Library/1.0 (research@artana.org)"},
        )

    async def __aenter__(self) -> "BaseIngestor":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.client.aclose()

    @abstractmethod
    async def fetch_data(self, **kwargs: JSONValue) -> list[RawRecord]:
        """
        Abstract method to fetch data from the source.

        Args:
            **kwargs: Source-specific parameters

        Returns:
            List of raw data records
        """

    async def ingest(self, **kwargs: JSONValue) -> IngestionResult:
        """
        Main ingestion method with error handling and provenance tracking.

        Args:
            **kwargs: Parameters passed to fetch_data

        Returns:
            IngestionResult with all operation details
        """
        start_time = datetime.now(UTC)
        # Map source name to DataSource enum
        data_source_enum = DataSource(self.source_name)

        provenance = Provenance(
            source=data_source_enum,
            source_version=None,
            source_url=self.base_url,
            acquired_at=start_time,
            acquired_by="Artana-Resource-Library",
            processing_steps=(f"Ingested from {self.source_name}",),
            validation_status="pending",
            quality_score=1.0,
        )

        errors: list[IngestionError] = []
        data: list[RawRecord] = []

        # Check circuit breaker before guarded operations
        if self.circuit_open:
            message = f"Circuit breaker open for {self.source_name}"
            raise IngestionError(
                message,
                self.source_name,
                {"circuit_breaker": True},
            )

        try:
            # Fetch data
            data = await self.fetch_data(**kwargs)

            # Store raw data
            await self._store_raw_data(data, start_time)

            # Update provenance
            provenance = provenance.add_processing_step(
                f"Retrieved {len(data)} records",
            )

            return IngestionResult(
                source=self.source_name,
                status=IngestionStatus.COMPLETED,
                records_processed=len(data),
                records_failed=0,
                data=data,
                provenance=provenance,
                errors=errors,
                duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
                timestamp=start_time,
            )

        except Exception as e:  # noqa: BLE001 - top-level ingest guard
            # Record failure
            self._record_failure()
            error = IngestionError(
                str(e),
                self.source_name,
                {"exception_type": type(e).__name__},
            )
            errors.append(error)

            return IngestionResult(
                source=self.source_name,
                status=IngestionStatus.FAILED,
                records_processed=len(data),
                records_failed=len(data) if data else 1,
                data=data,
                provenance=provenance,
                errors=errors,
                duration_seconds=(datetime.now(UTC) - start_time).total_seconds(),
                timestamp=start_time,
            )

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        *,
        params: QueryParams | None = None,
        headers: HeaderMap | None = None,
    ) -> httpx.Response:
        """
        Make HTTP request with rate limiting and retry logic.

        Args:
            method: HTTP method
            endpoint: API endpoint (relative to base_url)
            **kwargs: Additional request parameters

        Returns:
            HTTP response

        Raises:
            IngestionError: If request fails after retries
        """
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        rate_limit_status = 429
        server_error_min = 500

        for attempt in range(self.max_retries):
            try:
                # Wait for rate limit token
                await self.rate_limiter.wait_for_token()

                response = await self.client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                )

                # Check for rate limiting
                if response.status_code == rate_limit_status:
                    # Exponential backoff for rate limiting
                    wait_time = 2**attempt
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if (
                    e.response.status_code >= server_error_min
                    and attempt < self.max_retries - 1
                ):
                    # Server error - retry
                    await asyncio.sleep(2**attempt)
                    continue
                message = f"HTTP {e.response.status_code}: {e.response.text}"
                raise IngestionError(message, self.source_name) from e
            except (httpx.RequestError, ValueError) as e:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2**attempt)
                    continue
                message = f"Request failed: {e!s}"
                raise IngestionError(message, self.source_name) from e
            else:
                return response

        message = f"Failed after {self.max_retries} attempts"
        raise IngestionError(message, self.source_name)

    async def _store_raw_data(
        self,
        data: list[RawRecord],
        timestamp: datetime,
    ) -> Path:
        """
        Store raw data to filesystem with timestamp.

        Args:
            data: Raw data to store
            timestamp: Timestamp for filename

        Returns:
            Path to stored file
        """
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"{self.source_name}_{timestamp_str}.json"
        filepath = self.raw_data_dir / filename

        with filepath.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "source": self.source_name,
                    "timestamp": timestamp.isoformat(),
                    "records": data,
                },
                f,
                indent=2,
                default=str,
            )

        return filepath

    def _record_failure(self) -> None:
        """Record a failure for circuit breaker logic."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(UTC)

        # Open circuit after N consecutive failures
        if self.failure_count >= self.failure_threshold:
            self.circuit_open = True

    @staticmethod
    def _coerce_json_value(value: object) -> JSONValue:
        """Ensure arbitrary values conform to JSONValue contract."""
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        if isinstance(value, Mapping):
            json_obj: JSONObject = {}
            for key, item in value.items():
                json_obj[str(key)] = BaseIngestor._coerce_json_value(item)
            return json_obj
        if isinstance(value, Sequence) and not isinstance(
            value,
            str | bytes | bytearray,
        ):
            return [BaseIngestor._coerce_json_value(item) for item in value]
        message = f"Unsupported JSON value: {type(value)!r}"
        raise ValueError(message)

    @classmethod
    def _ensure_raw_record(cls, payload: object) -> RawRecord:
        """Convert arbitrary payloads into RawRecord dictionaries."""
        if not isinstance(payload, Mapping):
            message = "Expected JSON object from API response"
            raise TypeError(message)
        record: RawRecord = {}
        for key, value in payload.items():
            if isinstance(key, str):
                record[key] = cls._coerce_json_value(value)
        return record

    def reset_circuit_breaker(self) -> None:
        """Reset circuit breaker state."""
        self.failure_count = 0
        self.circuit_open = False
        self.last_failure_time = None
