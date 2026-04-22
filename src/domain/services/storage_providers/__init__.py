"""Storage provider plugin interfaces and registry."""

from .base import StorageProviderPlugin
from .errors import (
    StorageConnectionError,
    StorageOperationError,
    StorageQuotaError,
    StorageValidationError,
)
from .registry import StoragePluginRegistry, default_storage_registry

__all__ = [
    "StorageConnectionError",
    "StorageOperationError",
    "StoragePluginRegistry",
    "StorageProviderPlugin",
    "StorageQuotaError",
    "StorageValidationError",
    "default_storage_registry",
]
