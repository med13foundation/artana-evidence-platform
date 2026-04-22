"""
Request models for storage configuration operations.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.type_definitions.common import JSONObject  # noqa: TC001
from src.type_definitions.storage import (  # noqa: TC001
    StorageProviderCapability,
    StorageProviderConfigModel,
    StorageProviderName,
    StorageUseCase,
)


class CreateStorageConfigurationRequest(BaseModel):
    """Request contract for creating a storage configuration."""

    name: str
    provider: StorageProviderName
    config: StorageProviderConfigModel
    supported_capabilities: set[StorageProviderCapability] | None = None
    default_use_cases: set[StorageUseCase] | None = None
    enabled: bool = True
    metadata: JSONObject = Field(default_factory=dict)
    ensure_storage_ready: bool = True

    model_config = ConfigDict(arbitrary_types_allowed=True)


class UpdateStorageConfigurationRequest(BaseModel):
    """Request contract for updating storage configurations."""

    name: str | None = None
    config: StorageProviderConfigModel | None = None
    supported_capabilities: set[StorageProviderCapability] | None = None
    default_use_cases: set[StorageUseCase] | None = None
    metadata: JSONObject | None = None
    enabled: bool | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


__all__ = [
    "CreateStorageConfigurationRequest",
    "UpdateStorageConfigurationRequest",
]
