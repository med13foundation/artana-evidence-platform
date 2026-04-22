"""Storage infrastructure utilities."""

from src.domain.services.storage_providers import (
    StoragePluginRegistry,
    default_storage_registry,
)

from .providers.google_cloud import GoogleCloudStorageProvider
from .providers.local_filesystem import LocalFilesystemStorageProvider


def initialize_storage_plugins(
    registry: StoragePluginRegistry | None = None,
) -> StoragePluginRegistry:
    """Register built-in storage providers."""

    target = registry or default_storage_registry
    target.register(LocalFilesystemStorageProvider(), override=True)
    target.register(GoogleCloudStorageProvider(), override=True)
    return target


__all__ = ["initialize_storage_plugins"]
