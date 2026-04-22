"""Domain-specific storage exceptions."""

from __future__ import annotations

from dataclasses import dataclass

from src.type_definitions.storage import (  # noqa: TC001
    StorageOperationType,
    StorageProviderName,
)


@dataclass(slots=True)
class StorageOperationError(Exception):
    """Base exception for storage operations."""

    operation: StorageOperationType | None
    provider: StorageProviderName
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        operation = self.operation.value if self.operation else "operation"
        base = f"{self.provider.value} {operation} failed"
        if self.details:
            return f"{base}: {self.details}"
        return base


class StorageConnectionError(StorageOperationError):
    """Raised when a provider cannot be reached."""


class StorageQuotaError(StorageOperationError):
    """Raised when quotas or limits are exceeded."""


class StorageValidationError(StorageOperationError):
    """Raised when configuration validation fails."""


__all__ = [
    "StorageConnectionError",
    "StorageOperationError",
    "StorageQuotaError",
    "StorageValidationError",
]
