"""
Domain contracts for file upload processing.

Defines shared data structures and protocols for parsing uploaded files
while delegating filesystem and parsing concerns to infrastructure adapters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from src.type_definitions.common import JSONObject  # noqa: TCH001


class _SourceConfigurationProtocol(Protocol):
    """Structural typing for file upload configuration usage."""


if TYPE_CHECKING:
    from src.domain.entities.user_data_source import (
        SourceConfiguration as _SourceConfiguration,
    )

    SourceConfiguration = _SourceConfiguration
else:
    SourceConfiguration = _SourceConfigurationProtocol


class FileUploadResult(BaseModel):
    """Result of a file upload operation."""

    success: bool
    file_path: str | None = None
    record_count: int = 0
    file_size: int = 0
    detected_format: str | None = None
    errors: list[str] = Field(default_factory=list)
    metadata: JSONObject = Field(default_factory=dict)


class DataRecord(BaseModel):
    """Represents a single data record from uploaded files."""

    data: JSONObject
    line_number: int | None = None
    validation_errors: list[str] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """Check if the record is valid."""
        return len(self.validation_errors) == 0


@runtime_checkable
class FileUploadGateway(Protocol):
    """Protocol describing infrastructure responsibilities for file processing."""

    def process_upload(
        self,
        *,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        configuration: SourceConfiguration,
        max_records: int = 5_000,
    ) -> FileUploadResult: ...

    def parse_records(
        self,
        *,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        max_records: int = 5_000,
    ) -> list[DataRecord]: ...


class FileUploadService:
    """
    Domain-level coordinator for file uploads.

    Delegates parsing and persistence to the configured gateway so the
    domain layer remains agnostic of filesystem or library details.
    """

    def __init__(self, gateway: FileUploadGateway):
        self._gateway = gateway

    def process_upload(
        self,
        *,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        configuration: SourceConfiguration,
        max_records: int = 5_000,
    ) -> FileUploadResult:
        """Delegate upload processing to the gateway."""
        return self._gateway.process_upload(
            filename=filename,
            content_type=content_type,
            file_bytes=file_bytes,
            configuration=configuration,
            max_records=max_records,
        )

    def parse_records(
        self,
        *,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        max_records: int = 5_000,
    ) -> list[DataRecord]:
        """Delegate record parsing to the gateway."""
        return self._gateway.parse_records(
            filename=filename,
            content_type=content_type,
            file_bytes=file_bytes,
            max_records=max_records,
        )
