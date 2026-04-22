# Storage Provider Onboarding Guide

This guide outlines the steps to implement and register a new storage provider plugin in the Artana Resource Library. The storage platform follows a strict Clean Architecture approach with Type Safety First principles.

## Architecture Overview

Storage providers are implemented as infrastructure plugins that adapt external storage services (S3, GCS, Azure Blob, etc.) to the domain's storage interface.

- **Domain Layer**: Defines the `StorageProviderPlugin` abstract base class and `StorageConfiguration` entities.
- **Infrastructure Layer**: Implements the specific provider logic (e.g., `GoogleCloudStoragePlugin`).
- **Application Layer**: Orchestrates storage operations via `StorageConfigurationService` without knowing provider details.

## Implementation Steps

To add a new provider (e.g., `AWS S3`), follow these steps:

### 1. Update Domain Types

First, register the new provider in the domain type definitions.

**File**: `src/type_definitions/storage.py`

```python
class StorageProviderName(StrEnum):
    """Enumerates supported storage providers."""
    LOCAL_FILESYSTEM = "local_filesystem"
    GOOGLE_CLOUD_STORAGE = "google_cloud_storage"
    AWS_S3 = "aws_s3"  # <--- Add this
```

### 2. Define Configuration Model

Create a Pydantic model for your provider's configuration. This model ensures strict runtime validation of credentials and settings.

**File**: `src/type_definitions/storage.py`

```python
class AwsS3Config(StorageProviderConfig):
    """Configuration for AWS S3 provider."""

    provider: StorageProviderName = Field(
        default=StorageProviderName.AWS_S3,
        frozen=True,
    )
    bucket_name: str = Field(..., min_length=3)
    region_name: str = Field(..., pattern=r"^[a-z0-9-]+$")
    access_key_id_secret: str = Field(
        ...,
        description="Secret Manager name for Access Key ID",
    )
    secret_access_key_secret: str = Field(
        ...,
        description="Secret Manager name for Secret Access Key",
    )
    prefix: str = Field(default="")
```

**Important**: Update the union type `StorageProviderConfigModel` to include your new config:

```python
StorageProviderConfigModel = (
    LocalFilesystemConfig | GoogleCloudStorageConfig | AwsS3Config
)
```

### 3. Implement the Plugin

Create the plugin implementation in the infrastructure layer.

**File**: `src/infrastructure/storage/plugins/aws_s3.py` (Create if needed)

```python
from pathlib import Path
from typing import Any

from src.domain.services.storage_providers import (
    StorageProviderPlugin,
    StorageConnectionError,
    StorageOperationError,
)
from src.type_definitions.storage import (
    StorageProviderName,
    StorageProviderMetadata,
    StorageProviderCapability,
    StorageUseCase,
)

class AwsS3Plugin(StorageProviderPlugin):
    provider_name = StorageProviderName.AWS_S3
    config_type = AwsS3Config

    async def ensure_storage_exists(self, config: AwsS3Config) -> bool:
        # Check if bucket exists
        client = self._get_client(config)
        try:
            await client.head_bucket(Bucket=config.bucket_name)
            return True
        except Exception as e:
            raise StorageConnectionError(f"Bucket check failed: {e}")

    async def store_file(
        self,
        config: AwsS3Config,
        file_path: Path,
        *,
        key: str,
        content_type: str | None = None,
    ) -> str:
        client = self._get_client(config)
        full_key = f"{config.prefix}/{key}".strip("/")
        try:
            with open(file_path, "rb") as f:
                await client.put_object(
                    Bucket=config.bucket_name,
                    Key=full_key,
                    Body=f,
                    ContentType=content_type or "application/octet-stream",
                )
            return full_key
        except Exception as e:
            raise StorageOperationError(f"Upload failed: {e}")

    async def get_file_url(self, config: AwsS3Config, key: str) -> str:
        # Generate signed URL or public URL
        pass

    async def list_files(
        self,
        config: AwsS3Config,
        prefix: str | None = None,
    ) -> list[str]:
        # List objects
        pass

    async def delete_file(self, config: AwsS3Config, key: str) -> bool:
        # Delete object
        pass

    async def get_storage_info(
        self,
        config: AwsS3Config,
    ) -> StorageProviderMetadata:
        return StorageProviderMetadata(
            provider=self.provider_name,
            capabilities={
                StorageProviderCapability.PDF,
                StorageProviderCapability.RAW_SOURCE,
                StorageProviderCapability.EXPORT,
            },
            notes=f"S3 Bucket: {config.bucket_name} ({config.region_name})",
        )

    def _get_client(self, config: AwsS3Config) -> Any:
        # Instantiate boto3 client using secrets
        pass
```

### 4. Register the Plugin

Finally, register your plugin in the `initialize_storage_plugins` function.

**File**: `src/infrastructure/config/storage_registry.py` (or wherever initialization happens)

```python
def initialize_storage_plugins() -> StoragePluginRegistry:
    registry = StoragePluginRegistry()
    registry.register(LocalFilesystemPlugin())
    registry.register(GoogleCloudStoragePlugin())
    registry.register(AwsS3Plugin())  # <--- Register here
    return registry
```

## Best Practices

1.  **Security**: Never store credentials in the `config` model directly if they are sensitive. Use references to Secret Manager (e.g., `credentials_secret_name`).
2.  **Error Handling**: Wrap provider-specific exceptions (e.g., `boto3.exceptions.ClientError`) in domain exceptions (`StorageConnectionError`, `StorageOperationError`).
3.  **Testing**: Implement integration tests using a mock service (like `moto` for AWS) to ensure your plugin works without hitting real cloud APIs during CI/CD.
4.  **Type Safety**: Ensure 100% MyPy coverage. Do not use `Any` for the configuration object.

## Verification

Run the following commands to verify your new provider:

```bash
make type-check  # Verify Pydantic models and type strictness
pytest tests/integration/storage/test_storage_platform.py  # Run general storage tests
```
