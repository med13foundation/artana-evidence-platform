# Source Workflow Monitor And Pipeline Trace Guide

Last updated: 2026-03-09

This guide documents the new pipeline trace, run timing, run cost, and
workflow monitor features for data sources such as PubMed. It is written for
three audiences:

- operators who want to inspect one run in the UI
- engineers who want to extend the trace model
- agents or scripts that need a stable diagnostic surface

The implementation is Postgres-first and uses an append-only event ledger for
run history.

---

## What This Feature Does

For each pipeline run, the platform now persists a machine-readable run trace
instead of relying only on mutable summary rows and logs.

That gives you a single place to answer:

- What query was used for this PubMed run?
- Which papers were found?
- Which documents were enriched or extracted?
- How long did each stage and document take?
- How much direct AI/tool cost did the run incur?
- Who owns the run?
- Which warnings and errors occurred?
- What signals suggest the run should be improved?

The current user-facing entry point is the source workflow page:

`/spaces/{spaceId}/data-sources/{sourceId}/workflow`

The page reads from the workflow monitor APIs and, when enabled, keeps itself
updated with SSE.

---

## Main Concepts

### Pipeline run

A pipeline run is one end-to-end orchestration attempt for one source.
Everything for that attempt is keyed by `pipeline_run_id`.

### Append-only event ledger

Every important step emits an immutable event into `pipeline_run_events`.
Events are not rewritten in place. New facts are represented as new rows.

### Workflow monitor

The workflow monitor is the read model that combines:

- source snapshot
- pipeline run summary
- workflow timeline events
- document and extraction summaries
- graph/review summaries
- Artana progress and trace links

### Direct run cost

Cost means direct AI/tool spend only in V1. It is derived from provider/Artana
cost signals and does not include infrastructure cost such as Cloud Run,
database, or storage.

---

## What You Can See Today

### In the UI

Open:

`/spaces/{spaceId}/data-sources/{sourceId}/workflow`

Optional query params:

- `run_id={runId}`: focuses the page on one run
- `tab=setup|run|review|graph|trace`: opens a specific tab

The tabs are:

| Tab | Purpose |
|---|---|
| `Setup` | Source config, saved query, schedule, model, readiness checks |
| `Run Monitor` | Run status, startup visibility, executed query, timing, cost, timeline, documents, agent decisions, changes, warnings/errors |
| `Review` | Relation review queues and review-related rows |
| `Graph` | Graph impact summary |
| `Trace` | Linked Artana trace for the selected run |

### In the API

The workflow monitor routes expose the same information as typed read models.
These routes are research-space scoped and require normal auth and membership.

---

## Event Model

Each persisted event stores the following core fields.

| Field | Meaning |
|---|---|
| `seq` | Monotonic event sequence within the ledger |
| `research_space_id` | Owning research space |
| `source_id` | Owning source |
| `pipeline_run_id` | The run this event belongs to |
| `event_type` | What happened |
| `stage` | Pipeline stage such as ingestion, enrichment, extraction, graph |
| `scope_kind` | What the event is about |
| `scope_id` | Optional identifier for the scoped item |
| `level` | `info`, `warning`, or `error` |
| `status` | Outcome such as `running`, `completed`, `failed`, `partial` |
| `agent_kind` | Optional agent family such as `query_generation`, `content_enrichment`, `entity_recognition` |
| `agent_run_id` | Linked Artana/provider run id when available |
| `error_code` | Optional machine-readable error tag |
| `message` | Human-readable summary |
| `occurred_at` | Event timestamp |
| `started_at` | Optional start time for timed work |
| `completed_at` | Optional completion time |
| `duration_ms` | Elapsed time for the step |
| `queue_wait_ms` | Optional wait time before work started |
| `timeout_budget_ms` | Optional timeout budget |
| `payload` | Extra machine-readable details |

Supported `scope_kind` values:

- `run`
- `query`
- `document`
- `dictionary`
- `concept`
- `relation`
- `graph`
- `agent`
- `tool`
- `cost`

Current V1 instrumentation heavily uses `run`, `query`, `document`, `graph`,
and `cost`. The schema already supports more granular dictionary/concept/
relation events as coverage expands.

---

## Representative Event Types

Current representative event types include:

- `run_queued`
- `run_claimed`
- `run_started`
- `run_finished`
- `stage_started`
- `stage_finished`
- `query_generated`
- `papers_fetched`
- `document_found`
- `enrichment_batch_started`
- `document_started`
- `document_finished`
- `enrichment_batch_finished`
- `extraction_batch_started`
- `extraction_batch_finished`
- `cost_snapshot`

Representative payloads:

### Query generation event

```json
{
  "event_type": "query_generated",
  "stage": "ingestion",
  "scope_kind": "query",
  "agent_kind": "query_generation",
  "payload": {
    "executed_query": "(MED13 OR MED-13) AND fibrosis",
    "decision": "generated",
    "confidence": 0.92,
    "execution_mode": "agent",
    "fallback_reason": null,
    "fetched_records": 42,
    "processed_records": 18
  }
}
```

### Document extraction event

```json
{
  "event_type": "document_finished",
  "stage": "extraction",
  "scope_kind": "document",
  "status": "completed",
  "agent_kind": "entity_recognition",
  "duration_ms": 3812,
  "payload": {
    "document_id": "9ebd...",
    "external_record_id": "40123456",
    "review_required": true,
    "persisted_relations_count": 3,
    "concept_members_created_count": 1,
    "concept_aliases_created_count": 0,
    "concept_decisions_proposed_count": 1,
    "dictionary_variables_created": 0,
    "dictionary_synonyms_created": 2,
    "dictionary_entity_types_created": 0,
    "errors": []
  }
}
```

### Cost snapshot event

```json
{
  "event_type": "cost_snapshot",
  "scope_kind": "cost",
  "status": "captured",
  "payload": {
    "total_cost_usd": 0.0841,
    "stage_costs_usd": {
      "query_generation": 0.0042,
      "enrichment": 0.0201,
      "extraction": 0.0498,
      "graph": 0.0100
    },
    "linked_run_ids": ["artana_run_1", "artana_run_2"]
  }
}
```

---

## Ownership, Timing, And Cost Semantics

### Run owner attribution

Run ownership is resolved in this order:

1. `IngestionJob.triggered_by`
2. source `owner_id`
3. `system`

The run summary exposes:

- `run_owner_user_id`
- `run_owner_source`

`run_owner_source` is one of:

- `triggered_by`
- `source_owner`
- `system`

### Timing

Timing is stored at three useful levels:

- full run timing
- per-stage timing
- per-document timed events

The workflow monitor currently surfaces:

- `total_duration_ms`
- per-stage timing under `timing_summary.stage_timings`
- queue wait before the worker starts execution
- phase handoff gaps derived from stage start/end timestamps
- per-document extraction durations from document-scoped events
- derived `p50` and `p95` extraction timing signals

The `Run Monitor` tab now shows a dedicated `Stage Timing` section with:

- slowest phase
- fastest phase
- longest handoff gap
- queue wait
- per-stage `Started`, `Completed`, `Duration`, `Gap From Previous`,
  `Stage Queue Wait`, and `Timeout Budget`

### Cost

Cost is derived from Artana/provider snapshot rows linked back to the pipeline
run through discovered stage run ids. V1 includes:

- total direct cost in USD
- per-stage cost rollups when available
- linked agent/provider run ids

V1 does not include:

- database cost
- storage cost
- compute cost
- network cost

---

## Diagnostic Signals

The run summary enriches each run with derived signals meant for both humans
and agents.

Current signals include:

- `extraction_failure_ratio`
- `full_text_rescue_dependence`
- `cost_per_extracted_document`
- `cost_per_persisted_relation`
- `review_burden`
- `review_burden_ratio`
- `review_required_document_count`
- `undefined_relation_rate`
- `dictionary_churn_count`
- `concept_churn_count`
- `warning_event_count`
- `error_event_count`
- `timeout_hotspot_count`
- `timeout_scope_ids`
- `p50_document_extraction_duration_ms`
- `p95_document_extraction_duration_ms`
- `document_extraction_duration_samples`

Use these signals to spot patterns such as:

- the query is too broad
- enrichment is failing or rescuing too often
- extraction is slow on specific papers
- relation quality is low
- dictionary/concept churn is unexpectedly high
- review load is increasing

---

## How To Use It In Simple Terms

### For a human operator

If you want to understand one PubMed run:

1. Open the workflow page for the source.
2. Select the run by adding `?run_id={runId}` if needed.
3. Open the `Run Monitor` tab.
4. Read the cards at the top:
   - run status
   - total duration
   - direct cost
   - extracted docs
5. Read the phase timing cards:
   - slowest phase
   - fastest phase
   - longest handoff gap
   - queue wait
6. Read the `Stage Timing` table to see:
   - where the run was slow
   - which handoff between phases stalled
   - whether extraction or graph used large timeout budgets
7. Read the `Overview` panel:
   - run id
   - owner
   - executed query
   - ingestion/enrichment/extraction/graph status
8. Read the `Timeline` table to see what happened in order.
9. Read `Agent Decisions` to understand why the system did what it did.
10. Read `Changes` to see dictionary/concept/relation/graph deltas.
11. Read `Errors And Warnings` to see where the run struggled.
12. Open the `Trace` tab if you need deeper Artana-level detail.

### For a team lead reviewing quality or spend

Focus on:

- `Direct cost`
- `Slowest phase`
- `Longest handoff gap`
- `Queue wait`
- `Extraction failure ratio`
- `Cost / extracted doc`
- `Cost / relation`
- `Review burden`
- `warning_event_count`
- `error_event_count`
- `p95_document_extraction_duration_ms`

### For an agent or script

Use this sequence:

1. fetch run summary
2. fetch workflow events
3. fetch query trace
4. fetch timing summary
5. fetch cost summary
6. fetch document traces for the slowest or failed documents
7. optionally compare this run with another run

That gives the agent a stable path from high-level diagnosis down to one
document or one stage.

---

## UI Behavior And Live Updates

The workflow page is server-rendered initially and then refreshed live.

### Streaming

Source-level workflow streaming route:

`/research-spaces/{spaceId}/sources/{sourceId}/workflow-stream`

Space-level workflow card stream:

`/research-spaces/{spaceId}/workflow-stream`

### Live update behavior

- The workflow page uses SSE when available.
- On connect, it receives a bootstrap payload.
- It then receives snapshot updates and incremental workflow events.
- If SSE repeatedly fails, the client falls back to periodic page refresh.

### Startup visibility

The first seconds of a run now have explicit visibility:

1. The client shows a local queued state immediately after the run is submitted.
2. The backend persists `run_queued`.
3. When a worker claims the job, the backend persists `run_claimed`.
4. The backend then persists `run_started`.
5. Stage-specific events such as `stage_started` for ingestion follow.

This means the monitor should no longer appear blank while a healthy run is
waiting for the worker or just entering the ingestion phase.

### SSE flags

Server-side flag:

- `MED13_ENABLE_WORKFLOW_SSE`

Client-side flag:

- `NEXT_PUBLIC_WORKFLOW_SSE_ENABLED`

Default behavior is enabled unless explicitly disabled.

---

## API Reference

All routes below are under:

`/research-spaces/{spaceId}`

### Source-scoped monitor routes

| Route | Purpose |
|---|---|
| `/sources/{sourceId}/pipeline-runs` | List recent runs for one source |
| `/sources/{sourceId}/workflow-monitor` | Get the composite workflow monitor snapshot |
| `/sources/{sourceId}/workflow-events` | Get the persisted event timeline |
| `/sources/{sourceId}/pipeline-runs/{runId}/summary` | Get one run summary |
| `/sources/{sourceId}/pipeline-runs/{runId}/documents/{documentId}/trace` | Get a document-level trace |
| `/sources/{sourceId}/pipeline-runs/{runId}/query-trace` | Get query generation detail for one run |
| `/sources/{sourceId}/pipeline-runs/{runId}/timing` | Get timing summary for one run |
| `/sources/{sourceId}/pipeline-runs/{runId}/cost` | Get direct cost summary for one run |
| `/sources/{sourceId}/pipeline-runs/compare` | Compare two runs for the same source |

### Cost report routes

| Route | Purpose |
|---|---|
| `/pipeline-run-costs` | Cost report for a research space |
| `/users/{userId}/pipeline-run-costs` | Cost report for one user in a research space |

### Important query params

For `workflow-monitor`:

- `run_id`
- `limit`
- `include_graph`

For `workflow-events`:

- `run_id`
- `limit`
- `since`
- `stage`
- `level`
- `scope_kind`
- `scope_id`
- `agent_kind`

For cost reports:

- `source_type`
- `user_id`
- `date_from`
- `date_to`
- `limit`

For run comparison:

- `run_a`
- `run_b`

---

## Example API Calls

These examples assume the caller already has a bearer token and the user is a
member of the research space.

### Get the main monitor snapshot

```bash
curl \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/research-spaces/$SPACE_ID/sources/$SOURCE_ID/workflow-monitor?run_id=$RUN_ID&limit=50&include_graph=true"
```

### Get only failed extraction events

```bash
curl \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/research-spaces/$SPACE_ID/sources/$SOURCE_ID/workflow-events?run_id=$RUN_ID&stage=extraction&level=error&limit=200"
```

### Get query trace

```bash
curl \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/research-spaces/$SPACE_ID/sources/$SOURCE_ID/pipeline-runs/$RUN_ID/query-trace"
```

### Get one document trace

```bash
curl \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/research-spaces/$SPACE_ID/sources/$SOURCE_ID/pipeline-runs/$RUN_ID/documents/$DOCUMENT_ID/trace"
```

### Get one run's timing summary

```bash
curl \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/research-spaces/$SPACE_ID/sources/$SOURCE_ID/pipeline-runs/$RUN_ID/timing"
```

The response includes:

- `total_duration_ms`
- `stage_timings.ingestion`
- `stage_timings.enrichment`
- `stage_timings.extraction`
- `stage_timings.graph`

Each stage timing can include:

- `started_at`
- `completed_at`
- `duration_ms`
- `queue_wait_ms`
- `timeout_budget_ms`

### Get one run's cost summary

```bash
curl \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/research-spaces/$SPACE_ID/sources/$SOURCE_ID/pipeline-runs/$RUN_ID/cost"
```

### Compare two runs

```bash
curl \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/research-spaces/$SPACE_ID/sources/$SOURCE_ID/pipeline-runs/compare?run_a=$RUN_A&run_b=$RUN_B"
```

### Get a cost report for one user

```bash
curl \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/research-spaces/$SPACE_ID/users/$USER_ID/pipeline-run-costs?date_from=2026-03-01T00:00:00Z&date_to=2026-03-31T23:59:59Z&limit=200"
```

---

## Local And Staging Usage

The feature is meant to work the same way in local and staging.

### Local

Recommended usage:

- run the backend and web app normally
- keep workflow SSE enabled
- use the workflow page while a source run is active
- inspect the run after completion with `run_id`

Local is best for:

- prompt and query tuning
- debugging one failed run
- checking event payloads
- validating timing and cost rollups

### Staging

Recommended usage:

- inspect the same workflow page for real staged runs
- use the cost report endpoints for spend review
- compare repeated runs for the same source
- review p50/p95 timing and warning/error counts before production rollout

Staging is best for:

- validating operator visibility
- validating agent diagnostics
- validating run ownership attribution
- validating spend monitoring

### Differences to keep in mind

- direct AI/tool cost depends on linked provider/Artana snapshots
- live PubMed acceptance tests remain separately gated
- staging usually gives better signal for realistic timing and cost

---

## Known Limitations In V1

- There is no dedicated standalone cost-report page in the UI yet.
  The cost report is currently API-first.
- Cross-run timing comparison is still API-first. The UI now shows one run's
  stage timing clearly, but comparing many runs is still better done through
  the timing and comparison endpoints.
- The `Run Monitor` page shows per-run cost and diagnostics, but cross-run
  comparison is currently API-first.
- The schema supports fine-grained dictionary/concept/relation scope kinds,
  but not every mutation is yet emitted as its own first-class event row.
  Some of those deltas currently appear in document event payloads and run
  summaries.
- Infrastructure cost is out of scope in V1.
- Historical runs are not backfilled from older monitor data.

---

## Extending The Feature

If you need to extend the pipeline trace or monitor, start with these areas.

### Write side

- `alembic/versions/037_pipeline_run_events.py`
- `src/domain/entities/pipeline_run_event.py`
- `src/models/database/pipeline_run_event.py`
- `src/domain/repositories/pipeline_run_event_repository.py`
- `src/infrastructure/repositories/pipeline_run_event_repository.py`
- `src/application/services/pipeline_run_trace_service.py`

### Read side

- `src/application/services/source_workflow_monitor_service.py`
- `src/application/services/_source_workflow_monitor_events.py`
- `src/application/services/_source_workflow_monitor_pipeline.py`
- `src/routes/research_spaces/workflow_monitor_routes.py`
- `src/routes/research_spaces/workflow_monitor_schemas.py`

### UI

- `src/web/app/(dashboard)/spaces/[spaceId]/data-sources/[sourceId]/workflow/page.tsx`
- `src/web/app/(dashboard)/spaces/[spaceId]/data-sources/[sourceId]/workflow/source-workflow-monitor-view.tsx`
- `src/web/app/(dashboard)/spaces/[spaceId]/data-sources/[sourceId]/workflow/source-workflow-monitor-run-tab-section.tsx`
- `src/web/hooks/use-source-workflow-stream.ts`
- `src/web/lib/api/kernel.ts`

### Good extension candidates

- emit first-class dictionary/concept/relation mutation events
- add a dedicated cost-report UI
- add saved comparison views for repeated runs
- add export/download for run traces
- add agent-facing tool wrappers on top of the current API routes

---

## Recommended Operating Pattern

For day-to-day learning from runs, use this pattern:

1. Trigger or wait for a run.
2. Open the workflow page for that source.
3. Focus on one `run_id`.
4. Read `Run Monitor`.
5. Check the Artana `Trace` tab if the run looked surprising.
6. Use the query trace, document trace, timing, and cost endpoints for deeper review.
7. Compare with an earlier run before changing prompts, dictionary entries, or stage settings.

This keeps the workflow monitor as the single operational surface while still
giving engineers and agents deeper APIs when needed.
