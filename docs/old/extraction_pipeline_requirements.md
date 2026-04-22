# Extraction Pipeline Requirements (PubMed -> Knowledge Graph)

**Status date:** January 23, 2026
**Scope:** Immediate post-ingestion extraction for PubMed sources.
**Purpose:** Convert newly ingested PubMed records into structured facts that can
be stored and later connected in the mechanism-centered knowledge graph.

---

## 1) Summary (Plain Language)

We already ingest PubMed data (often via AI-generated queries) and store
publications. The next step is to **extract structured facts** from those
papers (variants, phenotypes, mechanisms, drugs, pathways). Extraction should
**run immediately after ingestion** and **must not reprocess the same paper**
unless extraction logic changes. The MVP must be scalable to full-text
extraction by recording the text source and document reference.

---

## 2) Goals

- Run extraction **immediately after ingestion** for each PubMed source run.
- Prevent duplicate extraction of the same paper.
- Support **concurrent ingestion runs** safely (multiple pipelines at once).
- Maintain **traceability** (which ingestion run produced which extraction).
- Preserve **type safety** and Clean Architecture boundaries.
- Provide a stable foundation for the future mechanism-centered graph.

---

## 3) Non-Goals (for this phase)

- Building the full knowledge graph and graph APIs.
- Automated agent-based reasoning or hypothesis scoring.
- Full NLP extraction or LLM-why a re we based paper parsing (can be staged later).

---

## 4) Current State (Baseline)

- PubMed ingestion is implemented with AI-assisted query generation.
- Publications are persisted and de-duplicated by PubMed ID.
- Raw ingestion records can be stored via storage backends.
- Scheduling exists for ingestion jobs.

---

## 5) Required Workflow (Immediate Extraction)

### Ingestion -> Extraction Handoff
1) **Ingestion run completes** for a PubMed source.
2) Newly ingested publications are **queued for extraction**.
3) Extraction job **runs immediately** for those queued items.

### Extraction Run (per publication)
- Load raw record and/or publication metadata.
- Extract structured facts (MVP: variants, phenotypes, gene mentions).
- Persist extraction outputs into a dedicated table for re-use.
- Mark the publication as **extracted** (or **failed** with error).

---

## 6) Data Model Requirements (Queue + Status)

### Extraction Queue (required)
- A dedicated table or entity to track extraction status per publication.
- Keys should include:
  - `publication_id` (or `pubmed_id`)
  - `source_id`
  - `ingestion_job_id`
  - `status` (pending | processing | completed | failed)
  - `attempts`
  - `last_error`
  - `extraction_version`
- timestamps: `queued_at`, `started_at`, `completed_at`

### Extraction Outputs (required)
- A dedicated table to store extracted facts and metadata.
- Keys should include:
  - `publication_id`
  - `source_id`
  - `ingestion_job_id`
  - `queue_item_id`
  - `status` (completed | failed | skipped)
  - `facts` (JSON array)
  - `text_source` (title_abstract | full_text | etc.)
  - `document_reference` (pointer to stored full text if used)
  - timestamps: `extracted_at`, `created_at`, `updated_at`

### Status Transitions
- `pending` -> `processing` -> `completed`
- `pending` -> `processing` -> `failed`
- `failed` -> `pending` (if retryable)

---

## 7) Idempotency Requirements

- If a publication is already `completed` for the current
  **extraction_version**, it should **not** be reprocessed.
- If extraction logic changes, increment `extraction_version` and allow
  reprocessing.

---

## 8) Concurrency & Queue Safety

Multiple ingestion pipelines may run at the same time. Extraction must:

- Use a **row-claiming** strategy in the queue (e.g., atomic update or
  `SELECT ... FOR UPDATE SKIP LOCKED`).
- Ensure **at-most-once** extraction per publication per version.
- Avoid duplicate writes when two ingestion runs touch the same PubMed ID.

---

## 9) Scheduler Integration

- Extraction should **run immediately after ingestion** finishes.
- It should be invoked by the same scheduler cycle (no separate cron needed).
- It should still support **manual trigger** and **retry** flows.

---

## 10) Type Safety & Architecture

- Domain logic lives in `src/domain`.
- Orchestration in `src/application/services`.
- Infrastructure adapters in `src/infrastructure`.
- **No `Any`** types. Use existing TypedDicts and JSON types.
- Extraction outputs should use typed models or staged TypedDicts
  (reuse from `src/type_definitions` where possible).

---

## 11) Observability & Audit

- Link each extraction to:
  - ingestion job id
  - source id
  - timestamps
- Record metrics:
  - publications processed
  - successes/failures
  - processing duration
 - Provide read-only API access to extraction outputs for UI consumption.

---

## 12) Security & Safety

- Do not store PHI in extraction outputs.
- Follow existing audit logging patterns.

---

## 13) Acceptance Criteria (Phase 1 Extraction)

- Ingestion triggers extraction **immediately** and automatically.
- A publication is extracted **only once** per extraction version.
- Concurrent pipeline runs do **not** double-process the same publication.
- Extraction status and retries are visible in logs or admin endpoints.

---

## 14) Open Questions (to resolve before implementation)

- Should extraction operate on **raw stored records** or on the normalized
  Publication entity only?
- Where should structured extraction outputs live (new tables vs. existing)?
- What is the minimal MVP output for mechanisms (free-text vs. typed entity)?
