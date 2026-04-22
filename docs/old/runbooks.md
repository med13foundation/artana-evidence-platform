# Artana Resource Library - Operational Runbooks

This document contains runbooks for common operational tasks, development workflows, and troubleshooting procedures.

## Table of Contents

1. [Storage Plugin Onboarding](#storage-plugin-onboarding)
2. [Preset Management](#preset-management)
3. [PDF Automation Troubleshooting](#pdf-automation-troubleshooting)

---

## Storage Plugin Onboarding

**Objective**: Add support for a new storage backend (e.g., S3, Azure Blob) to the Unified Storage Platform.
**Role**: Backend Engineer
**Prerequisites**: Python environment, `src/type_definitions/storage.py`, `src/infrastructure/storage/` access.
**Reference**: See [docs/storage_provider_onboarding.md](./storage_provider_onboarding.md) for a detailed implementation guide.

### 1. Define Configuration Model

Add the provider-specific configuration schema in `src/type_definitions/storage.py`.

```python
class S3StorageConfig(StorageProviderConfig):
    provider_type: Literal[StorageProviderName.S3] = StorageProviderName.S3
    bucket_name: str
    region: str
    prefix: str = ""
    access_key_id: str | None = None  # Use Secret Manager in prod
    secret_access_key: str | None = None
```

### 2. Update Enums and Unions

Update `StorageProviderName` and `StorageProviderConfigModel` in `src/type_definitions/storage.py`.

```python
class StorageProviderName(StrEnum):
    LOCAL_FS = "local_fs"
    GOOGLE_CLOUD_STORAGE = "gcs"
    S3 = "s3"  # <-- Add this

# ...

StorageProviderConfigModel = LocalFilesystemConfig | GoogleCloudStorageConfig | S3StorageConfig
```

### 3. Implement Provider Interface

Create a new class in `src/infrastructure/storage/providers/s3_provider.py` implementing `StorageProvider`.

```python
from src.domain.repositories.storage_repository import StorageProvider

class S3Provider(StorageProvider):
    def __init__(self, config: S3StorageConfig):
        self.config = config
        # Initialize boto3 client...

    async def test_connection(self) -> StorageProviderTestResult:
        # Implement connectivity check
        pass

    async def upload_file(self, source: BinaryIO, destination: str) -> StorageOperationResult:
        # Implement upload logic
        pass

    # Implement other methods: download_file, delete_file, list_files, etc.
```

### 4. Register Implementation

Update `src/infrastructure/storage/factory.py` to map the enum to the class.

```python
def create_provider(config: StorageConfiguration) -> StorageProvider:
    match config.provider:
        case StorageProviderName.S3:
            return S3Provider(config.config)
        # ...
```

### 5. Validation & Testing

1.  Add unit tests in `tests/unit/infrastructure/storage/test_s3_provider.py`.
2.  Verify strict type checking with `make type-check`.
3.  Run integration tests if possible (using `moto` or similar mocks).

---

## Preset Management

**Objective**: Create and manage discovery presets for reproducible literature searches.
**Role**: Researcher / Admin
**Interface**: Next.js Admin UI / REST API

### 1. Creating Presets

**Via UI**:
1.  Navigate to **Data Discovery > PubMed**.
2.  Configure advanced search parameters (Date range, Article types, etc.).
3.  Click **"Save as Preset"**.
4.  Enter a Name and Description.
5.  Select Scope:
    *   **User**: Private to you.
    *   **Space**: Shared with the current Research Space.

**Via API**:
`POST /api/data-discovery/pubmed/presets`

```json
{
  "name": "Recent Clinical Trials",
  "provider": "pubmed",
  "scope": "space",
  "parameters": {
    "term": "MED13",
    "article_types": ["Clinical Trial"],
    "min_date": "2023-01-01"
  }
}
```

### 2. Managing Scope

*   **User Scope**: Visible only to the creator. Useful for personal drafts.
*   **Space Scope**: Visible to all members of the Research Space. Requires `WRITE` permission on the space to create/edit.

### 3. Applying Presets

1.  In the Discovery interface, click **"Load Preset"**.
2.  Select a preset from the list.
3.  Parameters are instantly populated.
4.  Modify if needed (does not affect the saved preset unless you click Update).

---

## PDF Automation Troubleshooting

**Objective**: Diagnose and resolve failures in automated PDF retrieval for discovery results.
**Role**: DevOps / Support
**Tools**: Logs, Admin Dashboard, Database

### 1. Check Storage Operation Records

Failures are logged as `StorageOperationRecord` entries in the database.

**SQL Query**:
```sql
SELECT * FROM storage_operation_records
WHERE status = 'failed'
AND operation_type = 'WRITE'
ORDER BY created_at DESC
LIMIT 10;
```

**Admin UI**:
Check the **Storage Dashboard > Operations** log (if enabled) or the **Discovery Session** details.

### 2. Verify Storage Configuration Health

Ensure the target storage backend is healthy.

1.  Go to **Admin > Storage**.
2.  Check the status of the active configuration for the `PDF` use case.
3.  Run **"Test Connection"**.
4.  If "Quota Exceeded" or "Auth Error" appears, fix the backend credentials or capacity.

### 3. Check Ingestion Logs

PDF downloads are handled by background workers. Check the logs for `src/background/ingestion_scheduler.py` or the specific worker.

```bash
grep "PDFDownloadService" logs/backend.log
```

Common errors:
*   `403 Forbidden`: PubMed/Publisher blocked the IP. (Check rate limits).
*   `404 Not Found`: The full-text link is invalid or requires a subscription.
*   `StorageQuotaError`: The destination storage is full.

### 4. Retry Mechanism

Failed downloads are not automatically retried indefinitely to prevent bans.

**To manual retry**:
1.  Identify the `DiscoverySession` or specific `Publication` ID.
2.  Trigger the download endpoint again via API:
    `POST /api/data-discovery/pubmed/download/{pubmed_id}`

If the storage backend was the issue, fixing the config and re-triggering the search/download will resolve it.
