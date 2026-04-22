"""
Base storage provider plugin interfaces.

Defines the abstract plugin contract used by the storage platform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.type_definitions.storage import (
    StorageProviderCapability,
    StorageProviderConfigModel,
    StorageProviderMetadata,
    StorageProviderName,
    StorageProviderTestResult,
    StorageUseCase,
)

if TYPE_CHECKING:
    from pathlib import Path
    from uuid import UUID


class StorageProviderPlugin(ABC):
    """Abstract base class for all storage provider plugins."""

    provider_name: StorageProviderName
    config_type: type[StorageProviderConfigModel]

    def __init__(self) -> None:
        if not hasattr(self, "provider_name"):
            msg = "Storage providers must define provider_name"
            raise ValueError(msg)
        if not hasattr(self, "config_type"):
            msg = "Storage providers must declare config_type"
            raise ValueError(msg)

    def capabilities(self) -> set[StorageProviderCapability]:
        """Return the capabilities supported by this provider."""
        return {
            StorageProviderCapability.PDF,
            StorageProviderCapability.EXPORT,
            StorageProviderCapability.RAW_SOURCE,
        }

    def supports_use_case(self, use_case: StorageUseCase) -> bool:
        """Check if this provider can handle a given use case."""
        return use_case in {
            StorageUseCase.PDF,
            StorageUseCase.EXPORT,
            StorageUseCase.RAW_SOURCE,
            StorageUseCase.DOCUMENT_CONTENT,
        }

    async def validate_config(
        self,
        config: StorageProviderConfigModel,
    ) -> StorageProviderConfigModel:
        """
        Validate and cast the configuration to the provider-specific type.

        Subclasses can override to add provider-specific validation.
        """

        if not isinstance(config, self.config_type):
            msg = (
                f"Invalid configuration type for {self.provider_name.value}: "
                f"expected {self.config_type.__name__}"
            )
            raise TypeError(msg)
        return config

    @abstractmethod
    async def ensure_storage_exists(self, config: StorageProviderConfigModel) -> bool:
        """Ensure the backing storage exists and is reachable."""

    @abstractmethod
    async def store_file(
        self,
        config: StorageProviderConfigModel,
        file_path: Path,
        *,
        key: str,
        content_type: str | None = None,
    ) -> str:
        """Store a file and return the canonical storage key."""

    @abstractmethod
    async def get_file_url(
        self,
        config: StorageProviderConfigModel,
        key: str,
    ) -> str:
        """Return an accessible URL for a stored file."""

    @abstractmethod
    async def list_files(
        self,
        config: StorageProviderConfigModel,
        prefix: str | None = None,
    ) -> list[str]:
        """Return a list of stored keys."""

    @abstractmethod
    async def delete_file(self, config: StorageProviderConfigModel, key: str) -> bool:
        """Delete a stored object."""

    @abstractmethod
    async def get_storage_info(
        self,
        config: StorageProviderConfigModel,
    ) -> StorageProviderMetadata:
        """Return metadata about the storage backend."""

    async def test_connection(
        self,
        config: StorageProviderConfigModel,
        *,
        configuration_id: UUID,
    ) -> StorageProviderTestResult:
        """Execute a connection test and return structured results."""

        metadata = await self.get_storage_info(config)
        return StorageProviderTestResult(
            configuration_id=configuration_id,
            provider=self.provider_name,
            success=True,
            message="Storage backend reachable",
            checked_at=datetime.now(UTC),
            capabilities=metadata.capabilities,
            metadata=metadata.model_dump(),
        )


__all__ = ["StorageProviderPlugin"]
