# Harness Implementation Progress

## Objective

Build `services/artana_evidence_api` as the AI control layer while keeping
`services/artana_evidence_db` deterministic infrastructure only.

## Status

- Date: 2026-03-14
- Phase: Runtime alignment and quality-gate completion
- Overall: Runtime alignment complete
- Runtime cutover: Artana now owns the default run lifecycle, artifact,
  workspace, progress, event, resume-point, and worker-lease paths; manual
  workflow routes queue kernel-backed runs and execute them through the worker
  path instead of route-local orchestration
- Cleanup: the obsolete SQLAlchemy lifecycle tables and ORM models for
  artifacts, workspaces, progress, and events have been removed; `harness_runs`
  remains as the durable run catalog and SQLAlchemy keeps only harness-domain
  state that is not kernel-owned

## Completed

- Clarified the target boundary in
  `docs/harness/plan.md`: `artana_evidence_db` is deterministic-only and
  `artana_evidence_api` owns Artana/OpenAI runtime concerns.
- Created the initial `services/artana_evidence_api` service scaffold.
- Added deterministic `health` and `harnesses` endpoints for the new service.
- Added a service-local harness registry with the first workflow templates.
- Added harness-owned graph API gateway wiring for deterministic infra control.
- Added typed run creation, listing, and detail endpoints.
- Added typed artifact and workspace endpoints seeded from run creation.
- Added typed intent and approval endpoints for governed harness actions.
- Added harness-owned AI graph-search run endpoint and result artifact storage.
- Added harness-owned AI graph-connection run endpoint and result artifact storage.
- Added harness-owned AI hypothesis exploration run endpoint and staged
  candidate artifacts.
- Removed graph-search AI composition from `services/artana_evidence_db`; graph search in
  the graph service now composes as deterministic-only.
- Removed graph-connection AI composition from `services/artana_evidence_db`; graph
  connection is now hosted by the harness layer instead of the graph service.
- Removed auto-generated hypothesis exploration from `services/artana_evidence_db`; the
  graph service now keeps only deterministic hypothesis list/manual behavior.
- Removed dead graph-side hypothesis-generation composition from
  `services/artana_evidence_db/composition.py` now that harness owns AI exploration
  flows.
- Added a graph-service boundary guard so `services/artana_evidence_db` fails validation
  if it imports `src.infrastructure.llm`, `artana`, or `openai`.
- Removed `artana.toml` from the `services/artana_evidence_db` image build context.
- Split `services/artana_evidence_db` container packaging onto
  `services/artana_evidence_db/requirements.txt` so the image no longer installs the
  shared root package and no longer pulls `artana-kernel` through
  `pip install .`.
- Removed entity similarity, entity embedding refresh, and relation suggestion
  endpoints from `services/artana_evidence_db` so those embedding-backed workflows are no
  longer part of the deterministic graph-service API.
- Extended the graph-service boundary validator to reject embedding-backed
  service imports inside `services/artana_evidence_db`.
- Removed semantic dictionary term search and dictionary re-embedding from
  `services/artana_evidence_db`; graph dictionary governance now keeps deterministic CRUD
  and domain-scoped listing only.
- Rewired graph governance dictionary composition onto a repository-backed
  deterministic search harness with no embedding provider.
- Deleted the dead unmounted `services/artana_evidence_db/routers/graph_connections.py`
  module.
- Removed stale graph-service integration coverage for deleted AI and
  embedding-backed routes so the integration suite now matches the deterministic
  `artana_evidence_db` contract.
- Removed stale Python graph-service client surface for graph-side hypothesis
  auto-generation.
- Removed stale web/admin UI surface for deleted semantic graph-service
  endpoints, including dead relation-suggestion and similarity panels.
- Routed web hypothesis auto-generation through the harness-owned
  `/v1/spaces/{space_id}/agents/hypotheses/runs` endpoint instead of the
  deleted graph-service `/hypotheses/generate` route.
- Added a dedicated web harness base-url resolver for graph-harness service
  calls.
- Split AI-facing web API helpers into a dedicated
  `src/web/lib/api/graph-harness.ts` module.
- Routed web knowledge-graph search through the harness-owned
  `/v1/spaces/{space_id}/agents/graph-search/runs` endpoint instead of calling
  `artana_evidence_db` directly.
- Restored `src/web/lib/api/kernel.ts` to deterministic graph-service helpers
  only.
- Added a typed Python graph-harness client/runtime under
  `src/infrastructure/platform_graph/graph_harness`.
- Moved platform pipeline orchestration graph-search and graph-connection seed
  adapters from graph-service HTTP wiring to harness-owned HTTP wiring.
- Updated pipeline route/factory composition so backend orchestration now imports
  graph AI adapters from
  `src.infrastructure.platform_graph.graph_harness.pipeline`.
- Corrected the local default `artana_evidence_api` service port to `8091` so it
  no longer collides with graph-service defaults.
- Switched the ingestion scheduler post-ingestion graph hook from the old
  graph-service pipeline module to
  `src.infrastructure.platform_graph.graph_harness.pipeline`.
- Deleted the stale `src/infrastructure/graph_service/pipeline.py` module and
  its obsolete unit coverage now that production callers have moved to the
  harness-side adapters.
- Added service-local auth/authz enforcement to `services/artana_evidence_api` so
  harness reads require an authenticated active user and harness writes require
  researcher-or-higher role access.
- Added dedicated `tests/integration/artana_evidence_api/` and
  `tests/e2e/artana_evidence_api/` suites to cover the Artana-backed run API,
  scheduler-to-worker execution path, chat graph-write review flow, and
  approval-gated claim-curation resume flow.
- Expanded the dedicated harness-owned acceptance suites so the plan-level
  validation matrix now includes bootstrap snapshot/proposal promotion,
  schedule `run-now` to `delta_report`, mechanism-discovery candidate staging,
  proposal promotion into graph claim flow, and supervisor bootstrap/chat/
  curation pause-resume coverage alongside the existing lifecycle and
  claim-curation paths.
- Extended harness unit coverage to validate anonymous `401` responses and
  viewer-role `403` responses for protected harness mutations.
- Added standalone packaging for `services/artana_evidence_api` with a
  service-local `requirements.txt`, a dedicated Dockerfile, and explicit
  `artana.toml` inclusion for AI runtime config.
- Documented the harness runtime contract and required environment in
  `services/artana_evidence_api/README.md`.
- Added durable SQLAlchemy models and an Alembic migration for harness runs,
  artifacts, workspaces, intents, and approvals.
- Replaced the default harness service process-local run/artifact/approval
  stores with request-scoped SQLAlchemy-backed persistence.
- Added durable SQLAlchemy models and an Alembic migration for harness chat
  sessions and message history.
- Added typed chat-session create, list, detail, and message-send endpoints,
  with graph-chat runs persisting transcript state plus `graph_chat_result` and
  `chat_summary` artifacts.
- Added durable SQLAlchemy models and an Alembic migration for harness run
  progress snapshots and lifecycle events.
- Added typed run progress, event listing, and resume endpoints, with approval
  intents now pausing runs at an approval gate and resume requiring all pending
  approvals to be resolved first.
- Added durable SQLAlchemy models and an Alembic migration for service-local
  harness proposals, including candidate-claim ranking metadata and decision
  state.
- Added typed proposal list, detail, promote, and reject endpoints, with
  hypothesis runs now staging ranked `candidate_claim` proposals plus a
  `proposal_pack` artifact for review.
- Added a graph-service `POST /claims` write path plus harness-side promotion
  wiring so promoted `candidate_claim` proposals now create unresolved graph
  claims with participants and evidence before the harness proposal is marked
  `promoted`.
- Added the chat-side `POST /chat-sessions/{session_id}/proposals/graph-write`
  endpoint so the latest `graph_chat_result` and `chat_summary` artifacts can
  be converted into ranked `candidate_claim` proposals plus a
  `graph_write_proposals` artifact.
- Added a runnable `POST /agents/graph-curation/runs` workflow that batches
  reviewed `candidate_claim` proposals into a paused approval-gated curation
  run, writes `review_plan` and `approval_intent` artifacts, and on resume
  applies approved and rejected decisions into proposal state plus
  `curation_actions` and `curation_summary` artifacts.
- Added durable harness schedules plus the phase-3 `continuous-learning`
  workflow: `POST /agents/continuous-learning/runs` now writes `delta_report`,
  `new_paper_list`, `candidate_claims`, and `next_questions` artifacts while
  staging only net-new `candidate_claim` proposals, and the new `/schedules`
  API supports create/list/detail/update/pause/resume/run-now for recurring
  continuous-learning definitions.
- Cut over the default harness run and artifact providers to
  Artana-backed adapters in `services/artana_evidence_api/artana_stores.py` and
  `services/artana_evidence_api/dependencies.py`, so new runs now persist their
  lifecycle summaries, progress snapshots, events, artifacts, and workspace
  state through the shared Artana kernel runtime instead of the old
  SQLAlchemy-only lifecycle tables.
- Split recurring execution into a queueing scheduler and a leased worker:
  `services/artana_evidence_api/scheduler.py` now only creates queued
  `continuous-learning` runs and advances schedule bookkeeping, while
  `services/artana_evidence_api/worker.py` acquires Artana leases and executes
  queued runs against the existing continuous-learning workflow.
- Added explicit `run_budget` guardrails for `continuous-learning` runs and
  schedules, attached the default budget to harness discovery, and enforced
  `max_tool_calls`, `max_external_queries`, `max_new_proposals`, and
  `max_runtime_seconds` in harness control flow with `run_budget` and
  `budget_status` artifacts plus failed-run lifecycle events when a limit is
  exceeded.
- Added the phase-4 `mechanism-discovery` workflow:
  `POST /agents/mechanism-discovery/runs` now reads active mechanism reasoning
  paths, ranks converging targets deterministically, writes
  `mechanism_candidates`, `mechanism_score_report`, and
  `candidate_hypothesis_pack` artifacts, and stages reviewable
  `mechanism_candidate` proposals.
- Extended proposal promotion so reviewed `mechanism_candidate` proposals can
  now promote into graph-side manual hypotheses, while `candidate_claim`
  promotions continue to create unresolved graph claims.
- Added graph-backed claim-curation preflight checks: claim-curation runs now
  read graph claims, participants, evidence counts, and relation conflicts to
  build a `curation_packet`, flag exact duplicate graph claims and invariant
  failures, and only create approval-gated actions for proposals that remain
  eligible after those checks.
- Added durable research-memory tables plus the phase-1 bootstrap workflow:
  `POST /agents/research-bootstrap/runs` now captures a graph-context snapshot,
  writes `graph_summary`, `source_inventory`, `candidate_claim_pack`, and
  `research_brief` artifacts, stages initial `candidate_claim` proposals, and
  persists structured per-space research state with the latest snapshot id and
  pending question backlog.
- Wired persisted research memory into downstream workflows: graph-chat runs
  now load the latest research objective, pending questions, and graph snapshot
  into a `memory_context` artifact and workspace state, while
  `continuous-learning` runs and schedule triggers now carry forward the prior
  snapshot id, refresh graph-context snapshots after each cycle, and persist an
  updated `research_state_snapshot` artifact.
- Added explicit grounded-answer verification for graph-chat runs: each chat
  result now records a verification status and reason, writes a
  `grounded_answer_verification` artifact, exposes the status in workspace
  state, and blocks `chat-sessions/{session_id}/proposals/graph-write` unless
  the latest chat answer cleared the verification gate.
- Added automatic fresh-literature refresh for non-verified graph-chat answers:
  graph-chat runs now derive a PubMed query from the latest question and
  research objective, attach `fresh_literature` results to the chat response,
  write a `fresh_literature` artifact, and expose the latest literature-refresh
  state in the chat workspace snapshot.
- Added second-pass literature synthesis for graph-chat: when a fresh PubMed
  refresh runs, the assistant answer now appends a concise `Fresh literature to
  review` section with the top preview records so users get actionable next
  papers directly in the chat response.
- Added an Artana harness-dispatch layer in
  `services/artana_evidence_api/harness_runtime.py` so
  `research-bootstrap`, `graph-chat`, `continuous-learning`,
  `mechanism-discovery`, `claim-curation`, and `supervisor` now execute
  through Artana `BaseHarness` / `SupervisorHarness` wrappers instead of
  route-owned orchestration.
- Unified worker-owned execution across all runnable harnesses: manual workflow
  endpoints and `POST /runs/{run_id}/resume` now queue kernel-backed runs and
  synchronously wait on the leased worker path instead of executing a separate
  inline lifecycle implementation.
- Completed the graph-harness quality gates for the aligned runtime: the
  touched harness/runtime files are MyPy-clean, the checked-in
  `services/artana_evidence_api/openapi.json` contract is current, repo-wide
  `make type-check` passes, and repo-wide `make test` passes under pytest's
  `--import-mode=importlib` collection mode.
- Added the phase-6 `supervisor` workflow:
  `POST /agents/supervisor/runs` now creates a parent `supervisor` run that
  composes `research-bootstrap`, an optional briefing `graph-chat` session, and
  optional approval-gated `claim-curation` creation into one forward-only
  orchestration path while keeping each child run independently inspectable.
- Extended supervisor lifecycle control so the parent run now pauses at the
  child claim-curation approval gate, records child-run links as artifacts and
  workspace state, and `POST /runs/{run_id}/resume` now resumes or reconciles
  the child curation run before completing the parent workflow.
- Extended supervisor curation sourcing so `POST /agents/supervisor/runs` can
  now stage verified chat-derived `graph_write` proposals from the briefing
  chat run and feed those proposal ids into the approval-gated
  `claim-curation` child workflow instead of only curating bootstrap-staged
  candidate claims.
- Replaced the supervisor's manual `chat_graph_write_candidates` payload with a
  forward-only auto-derivation path: verified briefing-chat evidence entities
  now call a deterministic `POST /relations/suggestions` graph-service route,
  convert returned relation suggestions into `chat_graph_write` proposals, and
  pass those proposals directly into child claim-curation.
- Extended verified graph-chat runs so they now auto-derive relation
  suggestions through `POST /relations/suggestions`, return those
  `graph_write_candidates` in the chat response, and persist
  `graph_write_candidate_suggestions` artifacts plus workspace metadata for
  later review.
- Added deterministic ranking for chat-derived graph-write candidates so
  verified graph-chat runs now score relation suggestions against evidence
  strength, sort them, and keep only the top candidate set before surfacing
  them in chat responses or passing them into later workflows.
- Extended verified graph-chat answer synthesis so those top-ranked
  `graph_write_candidates` are now summarized in a short `Reviewable
  graph-write candidates` section inside the assistant answer text, not only in
  response metadata and artifacts.
- Added direct inline review for chat-derived graph writes:
  `POST /chat-sessions/{session_id}/graph-write-candidates/{candidate_index}/review`
  now resolves the selected stored candidate from the latest verified chat run,
  reuses an existing pending proposal when present, and immediately promotes or
  rejects that candidate without requiring a separate staging-only call.
- Extended that direct-review flow into supervisor orchestration:
  `POST /agents/supervisor/runs/{run_id}/chat-graph-write-candidates/{candidate_index}/review`
  now resolves the parent run's briefing chat, applies the same promote or
  reject path against the briefing-chat candidate, records supervisor-side
  review artifacts and workspace state, and blocks when chat-derived review has
  already been delegated to a child `claim-curation` run.
- Extended supervisor canonical state so direct briefing-chat review decisions
  now append into `supervisor_summary` as `chat_graph_write_reviews`, update a
  latest-review snapshot, and add a `chat_graph_write_review` step entry instead
  of leaving that manual review history only in workspace keys.
- Exposed that supervisor chat-review state in typed responses:
  `SupervisorRunResponse` now carries empty review-history fields from the start
  of the workflow, and
  `POST /agents/supervisor/runs/{run_id}/chat-graph-write-candidates/{candidate_index}/review`
  now returns the updated `chat_graph_write_reviews`,
  `latest_chat_graph_write_review`, and `chat_graph_write_review_count` without
  requiring a follow-up artifact fetch.
- Added a typed supervisor detail endpoint:
  `GET /agents/supervisor/runs/{run_id}` now reloads the canonical
  `supervisor_summary` plus current run progress into one typed response so
  callers can fetch composed parent state, nested child
  `research-bootstrap`/`graph-chat`/`claim-curation` summaries, curation
  outcome, and briefing-chat review history without combining generic run,
  progress, and artifact reads.
- Added a typed supervisor list endpoint and artifact-key contract:
  `GET /agents/supervisor/runs` now filters to supervisor workflows and
  returns the same typed child summaries used by the detail route, plus
  explicit parent/child artifact keys so list views can link into canonical
  bootstrap, chat, and curation artifacts without hardcoded key knowledge.
- Extended the typed supervisor list endpoint with query filters:
  callers can now filter `GET /agents/supervisor/runs` by parent `status`,
  `curation_source`, and `has_chat_graph_write_reviews` to drive list views
  that separate paused approval work, chat-derived curation flows, and runs
  that already have direct briefing-chat review decisions.
- Extended the typed supervisor list endpoint with sorting and pagination:
  callers can now apply `sort_by`, `sort_direction`, `offset`, and `limit` to
  `GET /agents/supervisor/runs`, with sorting over parent timestamps or
  `chat_graph_write_review_count` and pagination applied after the typed
  supervisor filters.
- Extended the typed supervisor list endpoint with aggregate summary counts:
  list responses now include a typed `summary` object with filtered
  pre-pagination totals for paused, completed, reviewed, unreviewed, and
  curation-source buckets so dashboard cards do not need client-side
  aggregation.
- Extended the typed supervisor list endpoint with time-window filters:
  callers can now filter `GET /agents/supervisor/runs` by `created_after`,
  `created_before`, `updated_after`, and `updated_before`, with the typed list
  summary and pagination still derived from that same canonical filtered set.
- Extended the typed supervisor list summary with trend buckets:
  list responses now include typed `trends` for `recent_24h_count`,
  `recent_7d_count`, recent completed/reviewed counters, plus daily created,
  completed, reviewed, and unreviewed groupings, plus daily
  bootstrap-vs-chat-graph-write curation-source groupings, all derived from
  the same filtered pre-pagination supervisor set using canonical
  `completed_at` and `reviewed_at` timestamps instead of inferring from
  `updated_at`.
- Added a typed `GET /agents/supervisor/dashboard` endpoint that returns only
  the canonical supervisor summary/trends for the same filtered set used by
  `GET /agents/supervisor/runs`, plus deep-link highlights for latest
  completed, latest reviewed, oldest paused, latest `bootstrap`, and latest
  `chat_graph_write` runs, plus approval-focused highlights for the latest run
  paused at approval, the run with the largest pending review backlog, and the
  largest pending review backlog within `bootstrap` vs `chat_graph_write`,
  including child curation run ids plus approval artifact keys for direct
  deep-links, so dashboard cards do not need to depend on paginated list
  responses.
- Simplified `POST /chat-sessions/{session_id}/proposals/graph-write` so
  callers can now omit `candidates` and the route will stage zero or more
  `chat_graph_write` proposals from the latest verified chat run's stored
  candidate suggestions instead of re-deriving them.
- Removed the remaining public `/v1/spaces/{space_id}/graph/search` endpoint
  from `services/artana_evidence_db`; graph-search HTTP entry now lives only in
  `services/artana_evidence_api`.
- Removed the stale graph-service client `search_graph()` method and its now-dead
  graph-service integration/unit coverage.
- Removed the dead graph-service graph-connection fallback builder and dependency
  provider now that `artana_evidence_db` no longer exposes any graph-connection runtime
  surface.
- Wired optional harness runtime URL sync into deploy/runtime config so backend
  callers can receive `ARTANA_EVIDENCE_API_SERVICE_URL` and the admin UI can receive
  `ARTANA_EVIDENCE_API_API_BASE_URL`, `INTERNAL_ARTANA_EVIDENCE_API_URL`, and
  `NEXT_PUBLIC_ARTANA_EVIDENCE_API_URL` when those deployment vars are configured.
- Added unit tests covering service startup and harness discovery.

## In Progress

- None for this plan.

## Next

- Future harness work should be tracked as new scope, not as completion work
  for this runtime-alignment plan.

## Notes

- Greenfield mode is active for this work.
- No backward-compatibility shims or migration scaffolding are being added in
  this track unless explicitly requested.
- Validation completed for this slice with:
  `venv/bin/python -m compileall tests/integration/graph_service/test_artana_evidence_db.py
  src/infrastructure/graph_service/client.py
  tests/unit/infrastructure/graph_service/test_client.py
  services/artana_evidence_db services/artana_evidence_api
  scripts/validate_graph_service_boundary.py`.
- Boundary validation completed for this slice with:
  `venv/bin/python scripts/validate_graph_service_boundary.py`.
- Python test validation completed for this slice with:
  `venv/bin/pytest tests/unit/infrastructure/graph_service/test_client.py
  tests/unit/services/artana_evidence_api/test_app.py
  tests/integration/graph_service/test_artana_evidence_db.py`.
- Backend harness validation completed for this slice with:
  `venv/bin/python -m compileall src/infrastructure/graph_harness
  src/routes/research_spaces/pipeline_orchestration_routes.py
  src/infrastructure/factories/pipeline_orchestration_factory.py
  services/artana_evidence_api/config.py`.
- Backend cleanup validation completed for this slice with:
  `venv/bin/python -m compileall src/infrastructure/graph_harness
  src/infrastructure/graph_service/__init__.py
  src/infrastructure/factories/ingestion_scheduler_factory.py
  src/routes/research_spaces/pipeline_orchestration_routes.py
  src/infrastructure/factories/pipeline_orchestration_factory.py`.
- Backend harness test validation completed for this slice with:
  `venv/bin/pytest tests/unit/infrastructure/graph_harness/test_client.py
  tests/unit/infrastructure/graph_harness/test_runtime.py
  tests/unit/infrastructure/graph_harness/test_pipeline.py
  tests/unit/routes/test_pipeline_orchestration_routes.py
  tests/unit/infrastructure/test_pipeline_orchestration_factory.py`.
- Harness auth validation completed for this slice with:
  `venv/bin/python -m compileall services/artana_evidence_api` and
  `venv/bin/pytest tests/unit/services/artana_evidence_api/test_app.py`.
- Harness packaging validation completed for this slice with:
  `venv/bin/python -m compileall services/artana_evidence_api`,
  `venv/bin/pytest tests/unit/services/artana_evidence_api/test_app.py`, and
  `venv/bin/python scripts/validate_graph_service_boundary.py`.
- Graph-search boundary validation completed for this slice with:
  `venv/bin/python -m compileall services/artana_evidence_db
  src/infrastructure/graph_service
  tests/integration/graph_service/test_artana_evidence_db.py
  tests/unit/infrastructure/graph_service/test_client.py`,
  `venv/bin/python scripts/export_graph_openapi.py`,
  `venv/bin/pytest tests/unit/infrastructure/graph_service/test_client.py
  tests/integration/graph_service/test_artana_evidence_db.py
  tests/unit/services/artana_evidence_api/test_app.py`, and
  `venv/bin/python scripts/validate_graph_service_boundary.py`.
- Web test validation completed for this slice with:
  `npm test -- --runInBand src/web/__tests__/lib/api/kernel.test.ts
  src/web/__tests__/lib/api/graph-harness.test.ts
  src/web/__tests__/app/knowledge-graph-client.test.tsx
  src/web/__tests__/app/hypothesis-generation-feedback.test.ts
  src/web/__tests__/app/curation-hypotheses-card.test.tsx`.
- Web type validation completed for this slice with:
  `npm run type-check`.
- Research-memory consumption validation completed for this slice with:
  `venv/bin/python -m compileall services/artana_evidence_api
  tests/unit/services/artana_evidence_api/test_app.py
  tests/unit/services/artana_evidence_api/test_scheduler.py` and
  `venv/bin/pytest tests/unit/services/artana_evidence_api/test_scheduler.py
  tests/unit/services/artana_evidence_api/test_app.py
  tests/unit/services/artana_evidence_api/test_sqlalchemy_stores.py
  tests/unit/database/test_alembic_migration_regressions.py -q`.
- Grounded-answer verification validation completed for this slice with:
  `venv/bin/python -m compileall services/artana_evidence_api
  tests/unit/services/artana_evidence_api/test_app.py
  tests/unit/services/artana_evidence_api/test_graph_chat_runtime.py`,
  `venv/bin/pytest tests/unit/services/artana_evidence_api/test_graph_chat_runtime.py
  tests/unit/services/artana_evidence_api/test_app.py -q`, and
  `venv/bin/ruff check services/artana_evidence_api/graph_chat_runtime.py
  services/artana_evidence_api/routers/chat.py
  tests/unit/services/artana_evidence_api/test_app.py
  tests/unit/services/artana_evidence_api/test_graph_chat_runtime.py`.
- Graph-chat literature refresh validation completed for this slice with:
  `venv/bin/python -m compileall services/artana_evidence_api
  tests/unit/services/artana_evidence_api/test_app.py
  tests/unit/services/artana_evidence_api/test_graph_chat_runtime.py`,
  `venv/bin/pytest tests/unit/services/artana_evidence_api/test_graph_chat_runtime.py
  tests/unit/services/artana_evidence_api/test_app.py -q`, and
  `venv/bin/ruff check services/artana_evidence_api/chat_literature.py
  services/artana_evidence_api/dependencies.py
  services/artana_evidence_api/graph_chat_runtime.py
  services/artana_evidence_api/routers/chat.py
  tests/unit/services/artana_evidence_api/test_app.py
  tests/unit/services/artana_evidence_api/test_graph_chat_runtime.py`.
- Graph-chat literature synthesis validation completed for this slice with:
  `venv/bin/python -m compileall services/artana_evidence_api
  tests/unit/services/artana_evidence_api/test_app.py
  tests/unit/services/artana_evidence_api/test_chat_literature.py`,
  `venv/bin/pytest tests/unit/services/artana_evidence_api/test_chat_literature.py
  tests/unit/services/artana_evidence_api/test_graph_chat_runtime.py
  tests/unit/services/artana_evidence_api/test_app.py -q`, and
  `venv/bin/ruff check services/artana_evidence_api/chat_literature.py
  services/artana_evidence_api/routers/chat.py
  tests/unit/services/artana_evidence_api/test_app.py
  tests/unit/services/artana_evidence_api/test_chat_literature.py`.
