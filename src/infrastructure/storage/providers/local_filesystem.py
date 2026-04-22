"""
Local filesystem storage provider implementation.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from src.domain.services.storage_providers import StorageProviderPlugin
from src.domain.services.storage_providers.errors import (
    StorageConnectionError,
    StorageOperationError,
    StorageValidationError,
)
from src.type_definitions.storage import (
    LocalFilesystemConfig,
    StorageOperationType,
    StorageProviderCapability,
    StorageProviderConfigModel,
    StorageProviderMetadata,
    StorageProviderName,
    StorageUseCase,
)


class LocalFilesystemStorageProvider(StorageProviderPlugin):
    """Storage provider that writes files to the local filesystem."""

    provider_name = StorageProviderName.LOCAL_FILESYSTEM
    config_type = LocalFilesystemConfig

    async def validate_config(
        self,
        config: StorageProviderConfigModel,
    ) -> LocalFilesystemConfig:
        raw_config = await super().validate_config(config)
        if not isinstance(raw_config, LocalFilesystemConfig):
            raise StorageValidationError(
                operation=None,
                provider=self.provider_name,
                details={"reason": "Expected local filesystem configuration"},
            )
        validated = raw_config
        base_path = Path(validated.base_path).expanduser()
        if not base_path.is_absolute():
            raise StorageValidationError(
                operation=None,
                provider=self.provider_name,
                details={
                    "base_path": validated.base_path,
                    "reason": "absolute path required",
                },
            )
        normalized = base_path
        if validated.create_directories:
            await asyncio.to_thread(normalized.mkdir, parents=True, exist_ok=True)
        return validated.model_copy(update={"base_path": str(normalized)})

    async def ensure_storage_exists(
        self,
        config: StorageProviderConfigModel,
    ) -> bool:
        local_config = self._ensure_local_config(config)
        base_path = Path(local_config.base_path)
        try:
            await asyncio.to_thread(base_path.mkdir, parents=True, exist_ok=True)
        except OSError as exc:  # pragma: no cover - OS errors bubbled up
            raise StorageConnectionError(
                operation=StorageOperationType.STORE,
                provider=self.provider_name,
                details={"error": str(exc)},
            ) from exc
        return True

    async def store_file(
        self,
        config: StorageProviderConfigModel,
        file_path: Path,
        *,
        key: str,
        content_type: str | None = None,
    ) -> str:
        del content_type  # Not used for local storage, kept for signature parity
        local_config = self._ensure_local_config(config)
        destination = Path(local_config.base_path) / key
        await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(shutil.copy2, file_path, destination)
        except OSError as exc:
            raise StorageOperationError(
                operation=StorageOperationType.STORE,
                provider=self.provider_name,
                details={"error": str(exc)},
            ) from exc
        return key

    async def get_file_url(
        self,
        config: StorageProviderConfigModel,
        key: str,
    ) -> str:
        local_config = self._ensure_local_config(config)
        path = Path(local_config.base_path) / key
        if not path.exists():
            raise StorageOperationError(
                operation=StorageOperationType.RETRIEVE,
                provider=self.provider_name,
                details={"key": key, "reason": "missing"},
            )
        if local_config.expose_file_urls:
            return path.resolve().as_uri()
        # Fall back to absolute path when URLs are disabled
        return str(path.resolve())

    async def list_files(
        self,
        config: StorageProviderConfigModel,
        prefix: str | None = None,
    ) -> list[str]:
        local_config = self._ensure_local_config(config)
        base_path = Path(local_config.base_path)
        if not base_path.exists():
            return []
        resolved_prefix = prefix or ""
        files: list[str] = []

        def _scan() -> None:
            for path in base_path.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(base_path).as_posix()
                    if not resolved_prefix or relative.startswith(resolved_prefix):
                        files.append(relative)

        await asyncio.to_thread(_scan)
        return files

    async def delete_file(
        self,
        config: StorageProviderConfigModel,
        key: str,
    ) -> bool:
        local_config = self._ensure_local_config(config)
        path = Path(local_config.base_path) / key
        try:
            await asyncio.to_thread(path.unlink, missing_ok=True)
        except OSError as exc:
            raise StorageOperationError(
                operation=StorageOperationType.DELETE,
                provider=self.provider_name,
                details={"error": str(exc), "key": key},
            ) from exc
        return True

    async def get_storage_info(
        self,
        config: StorageProviderConfigModel,
    ) -> StorageProviderMetadata:
        local_config = self._ensure_local_config(config)
        base_path = Path(local_config.base_path)
        exists = base_path.exists()
        total_files = 0
        total_size = 0

        if exists:
            for file_path in base_path.rglob("*"):
                if file_path.is_file():
                    total_files += 1
                    total_size += file_path.stat().st_size

        return StorageProviderMetadata(
            provider=self.provider_name,
            capabilities={
                StorageProviderCapability.PDF,
                StorageProviderCapability.EXPORT,
                StorageProviderCapability.RAW_SOURCE,
            },
            default_path=str(base_path),
            notes=f"{total_files} files, {total_size} bytes stored" if exists else None,
        )

    def supports_use_case(self, _use_case: StorageUseCase) -> bool:
        return True

    def _ensure_local_config(
        self,
        config: StorageProviderConfigModel,
    ) -> LocalFilesystemConfig:
        if not isinstance(config, LocalFilesystemConfig):
            raise StorageValidationError(
                operation=None,
                provider=self.provider_name,
                details={"reason": "Local filesystem configuration required"},
            )
        return config
