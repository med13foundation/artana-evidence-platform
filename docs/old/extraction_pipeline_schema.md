# Extraction Pipeline Schema and Interfaces

**Status date:** January 23, 2026
**Scope:** PubMed extraction queue (immediate post-ingestion).

---

## 1) Database Schema (extraction_queue)

**Table:** `extraction_queue`

**Columns (proposed):**
- `id` (UUID, PK)
- `publication_id` (INT, FK -> publications.id, indexed)
- `pubmed_id` (STRING, nullable, indexed)
- `source_id` (UUID, FK -> user_data_sources.id, indexed)
- `ingestion_job_id` (UUID, FK -> ingestion_jobs.id, indexed)
- `status` (ENUM: pending | processing | completed | failed, indexed)
- `attempts` (INT, default 0)
- `last_error` (TEXT, nullable)
- `extraction_version` (INT, default 1, indexed)
- `metadata_payload` (JSON, default {})
- `queued_at` (DATETIME, default now)
- `started_at` (DATETIME, nullable)
- `completed_at` (DATETIME, nullable)
- `created_at` (DATETIME, default now)
- `updated_at` (DATETIME, default now)

**Unique constraint:**
- `(publication_id, source_id, extraction_version)`

**Indexes:**
- `status`
- `publication_id`
- `source_id`
- `ingestion_job_id`
- `extraction_version`

---

## 2) Domain Entity

**File:** `src/domain/entities/extraction_queue_item.py`

Key fields:
- `id: UUID`
- `publication_id: int`
- `pubmed_id: str | None`
- `source_id: UUID`
- `ingestion_job_id: UUID`
- `status: ExtractionStatus`
- `attempts: int`
- `last_error: str | None`
- `extraction_version: int`
- `metadata: JSONObject`
- `queued_at / started_at / completed_at / updated_at`

---

## 3) Repository Interface

**File:** `src/domain/repositories/extraction_queue_repository.py`

Core methods:
```python
class ExtractionQueueRepository(Repository[ExtractionQueueItem, UUID, ExtractionQueueUpdate]):
    def enqueue_many(self, items: list[ExtractionQueueItem]) -> list[ExtractionQueueItem]: ...
    def list_pending(self, limit: int, source_id: UUID | None = None,
                     ingestion_job_id: UUID | None = None) -> list[ExtractionQueueItem]: ...
    def claim_pending(self, limit: int, source_id: UUID | None = None,
                      ingestion_job_id: UUID | None = None) -> list[ExtractionQueueItem]: ...
    def mark_completed(self, item_id: UUID, metadata: JSONObject | None = None) -> ExtractionQueueItem: ...
    def mark_failed(self, item_id: UUID, error_message: str) -> ExtractionQueueItem: ...
```

---

## 4) Application Service Interfaces

**File:** `src/application/services/extraction_queue_service.py`

Core methods:
```python
class ExtractionQueueService:
    def enqueue_for_ingestion(
        self,
        *,
        source_id: UUID,
        ingestion_job_id: UUID,
        publication_ids: Sequence[int],
        extraction_version: int | None = None,
    ) -> ExtractionEnqueueSummary: ...
```

**File:** `src/application/services/extraction_runner_service.py`

Core methods:
```python
class ExtractionRunnerService:
    def run_for_ingestion_job(
        self,
        *,
        source_id: UUID,
        ingestion_job_id: UUID,
        expected_items: int,
        batch_size: int | None = None,
    ) -> ExtractionRunSummary: ...
```

**File:** `src/application/services/ports/extraction_processor_port.py`

Core interfaces:
```python
class ExtractionProcessorPort(Protocol):
    def extract_publication(
        self,
        *,
        queue_item: ExtractionQueueItem,
        publication: Publication | None,
    ) -> ExtractionProcessorResult: ...
```

**Current behavior:**
- Queueing is implemented.
- A runner processes queued items using a rule-based processor and stores
  extraction outputs in `publication_extractions`.

---

## 5) Extraction Outputs (publication_extractions)

**Table:** `publication_extractions`

**Columns (proposed):**
- `id` (UUID, PK)
- `publication_id` (INT, FK -> publications.id, indexed)
- `pubmed_id` (STRING, nullable, indexed)
- `source_id` (UUID, FK -> user_data_sources.id, indexed)
- `ingestion_job_id` (UUID, FK -> ingestion_jobs.id, indexed)
- `queue_item_id` (UUID, FK -> extraction_queue.id, unique)
- `status` (ENUM: completed | failed | skipped, indexed)
- `extraction_version` (INT, default 1, indexed)
- `processor_name` (STRING)
- `processor_version` (STRING, nullable)
- `text_source` (STRING)
- `document_reference` (STRING, nullable)
- `facts` (JSON array, default [])
- `metadata_payload` (JSON, default {})
- `extracted_at` (DATETIME, default now)
- `created_at` (DATETIME, default now)
- `updated_at` (DATETIME, default now)

**Indexes:**
- `status`
- `publication_id`
- `pubmed_id`
- `source_id`
- `ingestion_job_id`
- `queue_item_id`
- `extraction_version`

---

## 5) Immediate Post-Ingestion Hook

**Location:** `src/application/services/ingestion_scheduling_service.py`

Behavior:
- After a PubMed ingestion run completes, queue all created/updated
  publication IDs for extraction using `ExtractionQueueService`.
- Immediately run extraction for newly queued items via
  `ExtractionRunnerService` (rule-based processor for now).

---

## 6) API Endpoints

**Routes:**
- `GET /extractions` (filterable list)
- `GET /extractions/{extraction_id}` (single record)
