# Artana Evidence API Service

This service is the AI control layer for graph-backed research workflows.

Current intent:

- host the canonical Artana runtime for harness lifecycle and model orchestration
- expose harness discovery, run lifecycle, artifact, review-queue, and
  approval APIs
- host harness-owned AI graph-search orchestration
- host harness-owned AI graph-connection orchestration
- host harness-owned AI hypothesis exploration
- host harness-owned research-bootstrap runs with durable research state and
  graph-context snapshots
- verify grounded graph-chat answers before allowing chat-derived graph-write
  proposals
- surface and persist reviewable graph-write candidates directly on verified
  graph-chat runs so callers can inspect them before staging proposals
- rank and cap verified chat graph-write candidates so chat surfaces only the
  top deterministic suggestions instead of every raw relation suggestion
- append a compact review section for those ranked graph-write candidates
  directly into verified chat answers
- let chat callers promote or reject those inline graph-write candidates
  directly from the chat session flow
- let the public chat graph-write endpoint reuse the latest verified chat run's
  stored graph-write candidates when callers omit an explicit candidate list
- refresh PubMed literature automatically for graph-chat answers that still
  need review or remain unverified
- synthesize fresh-literature leads back into non-verified graph-chat answers
  so the user gets immediate papers to review, not only metadata
- host harness-owned continuous-learning cycles and schedule definitions
- host harness-owned mechanism-discovery runs and reviewable hypothesis staging
- host governed claim-curation runs with graph-backed duplicate/conflict preflight
- host a supervisor workflow that composes bootstrap, briefing chat, and
  governed claim-curation into one parent run while preserving child runs,
  pausing/resuming the parent across the child approval gate, and optionally
  curating auto-derived, verified chat-backed graph-write proposals instead of
  only bootstrap-staged proposals
- let supervisor callers directly promote or reject briefing-chat graph-write
  candidates unless that review has already been delegated to child curation
- keep direct supervisor briefing-chat review history in the parent
  `supervisor_summary` artifact so orchestration and manual review stay in one
  canonical snapshot
- expose that supervisor briefing-chat review history directly in typed
  supervisor API responses
- expose a typed supervisor detail endpoint so callers can reload canonical
  composed state, progress, nested child bootstrap/chat/curation summaries,
  curation outcome, and briefing-chat review history without stitching
  together generic run and artifact reads
- expose a typed supervisor list endpoint that filters to supervisor workflows
  and returns the same child summaries plus parent/child artifact keys for
  list views
- support typed supervisor list filters for parent status, curation source,
  and whether briefing-chat graph-write reviews exist
- support typed supervisor list sorting and pagination so larger UI views can
  order by creation/update time or review count and page through typed
  supervisor workflow rows
- expose aggregate supervisor list summary counts so list responses include
  paused, completed, reviewed, unreviewed, and curation-source totals for
  dashboard cards without client-side reduction
- support typed supervisor list time-window filters over parent `created_at`
  and `updated_at` so recent orchestration activity can be segmented without a
  separate reporting endpoint
- expose a typed supervisor dashboard endpoint that returns only the canonical
  supervisor summary/trends for the same filtered set, without paginated run
  rows, plus deep-link highlights for latest completed, latest reviewed, and
  oldest paused runs, plus latest `bootstrap` and latest
  `chat_graph_write` runs, plus approval-focused highlights for the latest run
  paused at approval, the run with the largest pending review backlog, and the
  largest pending review backlog within `bootstrap` vs `chat_graph_write`,
  including child curation run ids plus approval artifact keys for direct
  deep-links
- expose typed supervisor trend buckets so list responses include recent-24h,
  recent-7d, recent completed, and recent reviewed counts, plus daily created,
  completed, reviewed, and unreviewed counts plus daily
  bootstrap-vs-chat-graph-write curation source counts from the same filtered
  supervisor set
- enforce explicit run budgets for continuous-learning schedules and runs
- call `services/artana_evidence_db` over typed HTTP boundaries
- keep `services/artana_evidence_db` deterministic and free of AI runtime concerns
- package as a standalone AI-capable service via
  `services/artana_evidence_api/Dockerfile`
- install service-local runtime dependencies from
  `services/artana_evidence_api/requirements.txt`
- load model/runtime defaults from the repo `artana.toml`

Greenfield mode applies to this service:

- no compatibility shims
- no fallback service boundary
- no legacy migration paths unless explicitly requested

Internal graph boundary:

- `GraphTransportBundle`
  - default typed graph surface for normal application code
  - exposes read/query, validation, dictionary, and workflow transports only
  - no hidden AI preflight, proposal creation, or request rewriting
- `GraphRawMutationTransport`
  - internal-only direct mutation transport for allowlisted system flows
  - owns `upsert_entity_direct`, `create_unresolved_claim_direct`,
    `materialize_relation_direct`, `create_entities_batch_direct`, and
    `update_entity_direct`
- `GraphAIPreflightService`
  - shared DB-first graph resolution layer
  - resolves exact entity matches, active relation synonyms, active relation
    types, dictionary-search candidates, and allowed relation suggestions
    before asking Artana Kernel
- `GraphWorkflowSubmissionService`
  - shared governed write/proposal submission layer
  - centralizes workflow requests, proposal requests, AI-decision envelopes,
    idempotency/source refs, and explicit authority selection
- `GraphCallContext`
  - explicit per-call graph identity envelope with `user_id`, `role`,
    `graph_admin`, `graph_ai_principal`, `graph_service_capabilities`, and
    request id
  - normal human/read flows do not attach AI authority
  - only explicit AI-decision submission paths attach `graph_ai_principal`
  - scoped sync paths mint `graph_service_capabilities=["space_sync"]`

Graph integration rule of thumb:

```text
normal app code
  -> GraphTransportBundle
  -> GraphAIPreflightService
  -> GraphWorkflowSubmissionService
  -> artana_evidence_db

raw graph mutation
  -> GraphRawMutationTransport
  -> allowlisted system flows only
```

Run locally with:

```bash
make run-artana-evidence-api-service
```

Run the schedule queueing loop with:

```bash
PYTHONPATH="$(pwd)/services" python -m artana_evidence_api.scheduler
```

Run the leased worker loop with:

```bash
PYTHONPATH="$(pwd)/services" python -m artana_evidence_api.worker
```

User-facing service docs live in:

- `services/artana_evidence_api/docs/user-guide.md`
- `services/artana_evidence_api/docs/README.md`
- `services/artana_evidence_api/docs/getting-started.md`
- `services/artana_evidence_api/docs/full-research-workflow.md`
- `services/artana_evidence_api/docs/concepts.md`
- `services/artana_evidence_api/docs/transparency.md`
- `services/artana_evidence_api/docs/api-reference.md`
- `services/artana_evidence_api/docs/use-cases.md`
- `services/artana_evidence_api/docs/use-cases.md`

Required runtime environment:

- `GRAPH_API_URL`
- `ARTANA_EVIDENCE_API_SERVICE_HOST`
- `ARTANA_EVIDENCE_API_SERVICE_PORT`
- optional `ARTANA_EVIDENCE_API_SERVICE_RELOAD`
- optional `ARTANA_EVIDENCE_API_GRAPH_API_TIMEOUT_SECONDS`
- `GRAPH_JWT_SECRET`
- optional `GRAPH_JWT_ISSUER` when the graph service issuer is not the default
- optional `GRAPH_ALLOW_TEST_AUTH_HEADERS`
- `OPENAI_API_KEY` or `ARTANA_OPENAI_API_KEY`
- `DATABASE_URL` or `ARTANA_STATE_URI`
- optional `ARTANA_EVIDENCE_API_SCHEDULER_POLL_SECONDS`
- optional `ARTANA_EVIDENCE_API_SCHEDULER_RUN_ONCE`
- optional `ARTANA_EVIDENCE_API_WORKER_ID`
- optional `ARTANA_EVIDENCE_API_WORKER_POLL_SECONDS`
- optional `ARTANA_EVIDENCE_API_WORKER_RUN_ONCE`
- optional `ARTANA_EVIDENCE_API_WORKER_LEASE_TTL_SECONDS`

Deployment/runtime notes:

- container packaging uses `services/artana_evidence_api/Dockerfile`
- the image copies `services/artana_evidence_api/artana.toml` into
  `/app/artana.toml` for model/runtime config
- runtime images now copy only `services/artana_evidence_api` into
  `/app/artana_evidence_api`, plus service-local test assets in the separate
  `test` stage
- the harness service remains the only graph-side runtime that should install
  Artana/OpenAI dependencies
- graph writes now flow through a split boundary:
  transport-only graph client, shared AI preflight, and shared governed
  submission services
- AI graph authority is explicit per call. The service does not silently mint
  AI-authority graph tokens for ordinary human or read traffic
- observation promotion now requires an already-existing subject entity; it does
  not create missing subject entities as a side effect of promoting an
  observation candidate
- extraction retries now reuse matching staged proposals and review items when a
  previous attempt already created them, instead of returning a false empty
  result after dedupe
- run lifecycle, artifacts, workspace state, progress, and events now default
  to Artana-backed adapters; the obsolete SQLAlchemy lifecycle tables have been
  dropped, and SQLAlchemy now retains only the durable run catalog plus
  harness-domain state that is not kernel-owned
- recurring schedules now queue kernel-backed runs, and the separate worker
  loop acquires Artana leases before executing those runs
- manual workflow routes and `POST /runs/{run_id}/resume` now use the same
  queue + leased-worker execution path as scheduled runs instead of maintaining
  a separate route-local orchestration flow
- the aligned runtime currently passes repo-wide `make type-check`,
  repo-wide `make test`, and `python scripts/export_artana_evidence_api_openapi.py
  --output services/artana_evidence_api/openapi.json --check`
- dedicated acceptance coverage for the aligned runtime now lives in
  `services/artana_evidence_api/tests/integration/test_runtime_paths.py` and
  `tests/e2e/artana_evidence_api/test_user_flows.py`, covering lifecycle/resume,
  bootstrap proposal staging and promotion, schedule `run-now` to
  `delta_report`, mechanism-discovery candidate staging, chat graph-write
  review, claim-curation approval/resume, supervisor bootstrap/chat/
  curation pause-resume flows, and the transparency endpoints that expose run
  capabilities plus observed tool/manual-review policy decisions
