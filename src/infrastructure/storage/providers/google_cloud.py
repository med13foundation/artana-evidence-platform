"""
Google Cloud Storage provider implementation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable  # noqa: TC003
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from types import ModuleType  # noqa: TC003
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Callable

from src.domain.services.storage_providers import StorageProviderPlugin
from src.domain.services.storage_providers.errors import (
    StorageConnectionError,
    StorageOperationError,
    StorageValidationError,
)
from src.type_definitions.storage import (
    GoogleCloudStorageConfig,
    StorageOperationType,
    StorageProviderCapability,
    StorageProviderConfigModel,
    StorageProviderMetadata,
    StorageProviderName,
    StorageUseCase,
)


@runtime_checkable
class StorageBlobProtocol(Protocol):
    name: str

    @property
    def public_url(self) -> str: ...

    def upload_from_filename(
        self,
        filename: str,
        content_type: str | None = ...,
    ) -> None: ...

    def generate_signed_url(
        self,
        expiration: datetime,
        version: str = ...,
    ) -> str: ...

    def delete(self) -> None: ...


@runtime_checkable
class StorageBucketProtocol(Protocol):
    def blob(self, name: str) -> StorageBlobProtocol: ...


@runtime_checkable
class StorageClientProtocol(Protocol):
    project: str

    def bucket(self, name: str) -> StorageBucketProtocol: ...

    def list_blobs(
        self,
        bucket_name: str,
        prefix: str | None = None,
    ) -> Iterable[StorageBlobProtocol]: ...

    def lookup_bucket(self, bucket_name: str) -> object: ...


gcs_storage: ModuleType | None
GoogleCloudError: type[Exception]
try:  # pragma: no cover - optional dependency
    gcs_storage = import_module("google.cloud.storage")
    google_exceptions = import_module("google.cloud.exceptions")
    GoogleCloudError = google_exceptions.GoogleCloudError
except ImportError:  # pragma: no cover - dependency may be unavailable in tests
    gcs_storage = None
    GoogleCloudError = Exception


class GoogleCloudStorageProvider(StorageProviderPlugin):
    """Storage provider backed by Google Cloud Storage."""

    provider_name = StorageProviderName.GOOGLE_CLOUD_STORAGE
    config_type = GoogleCloudStorageConfig

    def __init__(self) -> None:
        self._client_factory: Callable[[Path], StorageClientProtocol] | None
        if gcs_storage is None:
            self._client_factory = None
        else:
            self._client_factory = self._create_client_from_credentials

    async def validate_config(
        self,
        config: StorageProviderConfigModel,
    ) -> GoogleCloudStorageConfig:
        raw_config = await super().validate_config(config)
        if not isinstance(raw_config, GoogleCloudStorageConfig):
            raise StorageValidationError(
                operation=None,
                provider=self.provider_name,
                details={"reason": "Expected Google Cloud storage configuration"},
            )
        validated = raw_config
        if not validated.bucket_name.strip():
            raise StorageValidationError(
                operation=None,
                provider=self.provider_name,
                details={"reason": "bucket_name is required"},
            )
        if not validated.credentials_secret_name.strip():
            raise StorageValidationError(
                operation=None,
                provider=self.provider_name,
                details={
                    "reason": "credentials_secret_name must reference a JSON credential",
                },
            )
        return validated

    async def ensure_storage_exists(
        self,
        config: StorageProviderConfigModel,
    ) -> bool:
        gcs_config = self._ensure_gcs_config(config)
        client = self._get_client(gcs_config)
        try:
            await asyncio.to_thread(client.lookup_bucket, gcs_config.bucket_name)
        except GoogleCloudError as exc:  # pragma: no cover - network error paths
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
        gcs_config = self._ensure_gcs_config(config)
        client = self._get_client(gcs_config)
        blob_name = self._build_blob_name(gcs_config, key)
        bucket = client.bucket(gcs_config.bucket_name)
        blob = bucket.blob(blob_name)
        try:
            await asyncio.to_thread(
                blob.upload_from_filename,
                str(file_path),
                content_type=content_type,
            )
        except GoogleCloudError as exc:
            raise StorageOperationError(
                operation=StorageOperationType.STORE,
                provider=self.provider_name,
                details={"error": str(exc), "bucket": gcs_config.bucket_name},
            ) from exc
        return blob_name

    async def get_file_url(
        self,
        config: StorageProviderConfigModel,
        key: str,
    ) -> str:
        gcs_config = self._ensure_gcs_config(config)
        client = self._get_client(gcs_config)
        blob_name = self._build_blob_name(gcs_config, key)
        bucket = client.bucket(gcs_config.bucket_name)
        blob = bucket.blob(blob_name)
        if gcs_config.public_read:
            return str(blob.public_url)
        expires = datetime.now(UTC) + timedelta(
            seconds=gcs_config.signed_url_ttl_seconds,
        )
        try:
            return await asyncio.to_thread(
                blob.generate_signed_url,
                expiration=expires,
                version="v4",
            )
        except GoogleCloudError as exc:
            raise StorageOperationError(
                operation=StorageOperationType.RETRIEVE,
                provider=self.provider_name,
                details={"error": str(exc), "bucket": gcs_config.bucket_name},
            ) from exc

    async def list_files(
        self,
        config: StorageProviderConfigModel,
        prefix: str | None = None,
    ) -> list[str]:
        gcs_config = self._ensure_gcs_config(config)
        client = self._get_client(gcs_config)
        search_prefix = self._build_blob_name(gcs_config, prefix or "")

        def _fetch() -> list[str]:
            blobs = client.list_blobs(gcs_config.bucket_name, prefix=search_prefix)
            return [blob.name for blob in blobs]

        try:
            return await asyncio.to_thread(_fetch)
        except GoogleCloudError as exc:
            raise StorageOperationError(
                operation=StorageOperationType.LIST,
                provider=self.provider_name,
                details={"error": str(exc)},
            ) from exc

    async def delete_file(
        self,
        config: StorageProviderConfigModel,
        key: str,
    ) -> bool:
        gcs_config = self._ensure_gcs_config(config)
        client = self._get_client(gcs_config)
        blob_name = self._build_blob_name(gcs_config, key)
        bucket = client.bucket(gcs_config.bucket_name)
        blob = bucket.blob(blob_name)
        try:
            await asyncio.to_thread(blob.delete)
        except GoogleCloudError as exc:
            raise StorageOperationError(
                operation=StorageOperationType.DELETE,
                provider=self.provider_name,
                details={"error": str(exc), "key": blob_name},
            ) from exc
        return True

    async def get_storage_info(
        self,
        config: StorageProviderConfigModel,
    ) -> StorageProviderMetadata:
        gcs_config = self._ensure_gcs_config(config)
        client = self._get_client(gcs_config)
        info = {
            "base_path": gcs_config.base_path,
            "project": client.project,
        }
        return StorageProviderMetadata(
            provider=self.provider_name,
            capabilities={
                StorageProviderCapability.PDF,
                StorageProviderCapability.EXPORT,
                StorageProviderCapability.RAW_SOURCE,
            },
            default_path=gcs_config.base_path,
            notes=str(info),
        )

    def supports_use_case(self, _use_case: StorageUseCase) -> bool:
        return True

    def _get_client(
        self,
        config: GoogleCloudStorageConfig,
    ) -> StorageClientProtocol:
        if self._client_factory is None:
            raise StorageConnectionError(
                operation=None,
                provider=self.provider_name,
                details={"reason": "google-cloud-storage dependency not installed"},
            )
        credentials_path = Path(config.credentials_secret_name).expanduser()
        if not credentials_path.exists():
            raise StorageConnectionError(
                operation=None,
                provider=self.provider_name,
                details={
                    "reason": "credential path not found",
                    "path": str(credentials_path),
                },
            )
        return self._client_factory(credentials_path)

    @staticmethod
    def _build_blob_name(config: GoogleCloudStorageConfig, key: str) -> str:
        prefix = config.base_path.strip("/")
        normalized_key = key.lstrip("/")
        return f"{prefix}/{normalized_key}" if prefix else normalized_key

    def _ensure_gcs_config(
        self,
        config: StorageProviderConfigModel,
    ) -> GoogleCloudStorageConfig:
        if not isinstance(config, GoogleCloudStorageConfig):
            raise StorageValidationError(
                operation=None,
                provider=self.provider_name,
                details={"reason": "Google Cloud configuration required"},
            )
        return config

    def _create_client_from_credentials(
        self,
        credentials_path: Path,
    ) -> StorageClientProtocol:
        if gcs_storage is None:
            raise StorageConnectionError(
                operation=None,
                provider=self.provider_name,
                details={"reason": "google-cloud-storage dependency not installed"},
            )
        client = gcs_storage.Client.from_service_account_json(str(credentials_path))
        if not isinstance(client, StorageClientProtocol):
            raise StorageConnectionError(
                operation=None,
                provider=self.provider_name,
                details={"reason": "Loaded client does not match expected protocol"},
            )
        return client
