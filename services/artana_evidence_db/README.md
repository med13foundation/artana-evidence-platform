# Graph API Service

This package is the standalone graph service.

Current scope:

- independent FastAPI app
- service-local config, database session, and auth helpers
- standalone graph-service authz now resolves space access through a graph-local space access port instead of the platform membership service
- graph-connection composition now resolves tenant settings through a graph-local space settings port instead of the platform `ResearchSpaceRepository`
- graph-owned runtime now resolves tenant metadata through a graph-local space registry adapter for owner checks, settings lookup, auto-promotion policy resolution, and global reasoning-path rebuild enumeration
- graph-owned tenant metadata now persists in a graph-owned `graph_spaces` table with standalone admin registry APIs
- graph-service authz now resolves non-owner members through graph-owned `graph_space_memberships` instead of the platform membership table
- graph-owned control-plane and governance tables can now live in a dedicated `GRAPH_DB_SCHEMA` instead of always living in `public`
- standalone admin APIs now support atomic graph-space sync, including full graph-owned membership snapshot replacement for a space
- platform space and membership application services now push graph tenant sync through a graph control-plane port instead of repeating route-level helper calls
- the platform now has a dedicated tenant reconciliation path under `scripts/sync_graph_spaces.py` and `make graph-space-sync` for rebuilding graph-space state from platform truth, and `make run-all` invokes it automatically for the local stack
- architecture validation now runs `scripts/validate_graph_service_boundary.py` so new direct imports of graph internals outside the standalone service fail
- graph control-plane APIs now require a graph-service-local admin claim instead of depending on the platform `UserRole.ADMIN` role
- standalone runtime now requires an explicit `GRAPH_DATABASE_URL` instead of inheriting the platform `DATABASE_URL` resolver contract
- standalone runtime now supports `GRAPH_DB_SCHEMA` so graph-owned control-plane and governance tables can run from a dedicated schema with a graph-aware Postgres `search_path`
- standalone runtime now uses graph-local DB pool settings under `GRAPH_DB_*` instead of the shared platform Postgres/pool env contract
- service-local DB operations now exist under `python -m artana_evidence_db.manage` and back the dedicated `make graph-db-wait` / `make graph-db-migrate` commands
- service-local container packaging now exists under `services/artana_evidence_db/Dockerfile`
- service-local runtime dependencies now live in
  `services/artana_evidence_db/requirements.txt` so the graph container does not install
  the shared root package or Artana runtime
- graph-owned embedding refresh, embedding readiness, entity similarity, and
  relation suggestions live in the graph service; harness consumes those
  heuristics over HTTP and must tolerate explicit readiness lag
- graph-service Cloud Run runtime sync now exists under `scripts/deploy/sync_graph_cloud_run_runtime_config.sh`
- graph-service promotion now has a dedicated GitHub Actions workflow in `.github/workflows/artana-evidence-db-deploy.yml`
- service-local composition for graph, dictionary, and concept services
- service-local governance adapters/builders now expose shared dictionary and concept service composition under `services/artana_evidence_db/governance.py`
- `services/artana_evidence_db/dictionary_repository.py` and `services/artana_evidence_db/concept_repository.py` are compatibility re-exports over the shared graph-governance persistence layer
- service-local OpenAPI export now lives under `scripts/export_graph_openapi.py`, with the current artifact at `services/artana_evidence_db/openapi.json`
- service-local quality gates now run under `make graph-service-checks`
- graph-owned schema no longer carries foreign keys to platform `users` or `source_documents`
- graph view assembly now uses a graph-local source-document reference port instead of the platform document repository contract
- entity endpoints under `/v1/spaces/{space_id}/entities/...`
- observation endpoints under `/v1/spaces/{space_id}/observations/...`
- provenance endpoints under `/v1/spaces/{space_id}/provenance/...`
- deterministic graph read endpoints under `/v1/spaces/{space_id}/...`
- canonical relation create and curation-update endpoints under `/v1/spaces/{space_id}/relations/...`
- canonical graph export and unified graph document endpoints
- claim-ledger reads and claim-status mutation endpoints
- claim-relation write and review endpoints
- graph-view and mechanism-chain endpoints
- service-owned maintenance endpoints for participant backfill, projection readiness, projection repair, and reasoning-path rebuilds
- service-owned operation history endpoints under `/v1/admin/operations/runs` for readiness, repair, backfill, and rebuild workflows
- service-owned graph-space registry endpoints under `/v1/admin/spaces/...`
- service-owned graph-space sync endpoint under `/v1/admin/spaces/{space_id}/sync`
- service-owned graph-space membership endpoints under `/v1/admin/spaces/{space_id}/memberships/...`
- service-owned dictionary governance endpoints under `/v1/dictionary/...`, including revoke, merge, changelog, deterministic domain listing, and transform registry workflows
- service-owned concept governance endpoints under `/v1/spaces/{space_id}/concepts/...`
- service-owned hypothesis workflow endpoints under `/v1/spaces/{space_id}/hypotheses/...`
- service-owned V2 product-mode workflow endpoints under
  `/v1/spaces/{space_id}/workflows/...` for evidence approval, batch review,
  AI evidence decisions, conflict resolution, continuous learning review, and
  bootstrap review
- service-owned operating-mode endpoints under
  `/v1/spaces/{space_id}/operating-mode...` for selecting manual,
  human-plus-AI, or AI-full governance behavior per graph space
- service-owned explanation endpoints under
  `/v1/spaces/{space_id}/explain/...` and
  `/v1/spaces/{space_id}/validate/explain`
- first typed platform HTTP client under `src/infrastructure/graph_service/`, including graph-space registry and membership management
- platform space lifecycle and membership write routes now sync graph tenant state into the standalone service over HTTP after successful platform writes
- web entity, observation, provenance, and relation write helpers now target the standalone graph service for extracted endpoints
- operational readiness and reasoning-rebuild scripts now consume the graph service over HTTP
- pipeline orchestration graph-seed discovery now consumes graph-connection over the standalone graph-service HTTP client
- durable worker-side graph search and graph-connection flows now use service-to-service graph adapters over HTTP
- post-ingestion graph hooks and the minimal full-workflow script now use the standalone graph-service client for extracted graph operations
- runnable entrypoints at `artana_evidence_db.main:app` and `python -m artana_evidence_db`

Current non-goals:

- background rebuild jobs
- typed client cutover for non-graph callers

The service now runs from the service-local package and dependency set while
keeping a dedicated HTTP boundary around graph-owned runtime concerns.

## V2 Governed Graph Engine

The graph service is now more than a low-level graph CRUD API. It can be used
as a reusable governed graph engine by other projects.

The main public product-mode flow is:

```text
set operating mode -> create workflow -> inspect workflow -> take action -> explain result
```

This keeps the API easier to use while preserving lower-level proposal,
dictionary, entity, relation, claim, and validation APIs for advanced callers.

### Operating Modes

Each graph space stores its operating mode in `graph_spaces.settings`.

Endpoints:

```http
GET   /v1/spaces/{space_id}/operating-mode
PATCH /v1/spaces/{space_id}/operating-mode
GET   /v1/spaces/{space_id}/operating-mode/capabilities
```

Supported modes:

- `manual`: humans review and apply graph changes.
- `ai_assist_human_batch`: AI can help prepare batches, humans apply them.
- `human_evidence_ai_graph`: humans approve evidence while trusted AI can help
  repair missing graph structure.
- `ai_full_graph`: trusted AI can apply low-risk graph repair when policy,
  confidence, validation, and hash checks pass.
- `ai_full_evidence`: trusted AI can also make evidence decisions when policy
  allows.
- `continuous_learning`: supports ongoing AI review and learning workflows.

Example operating-mode payload:

```json
{
  "mode": "human_evidence_ai_graph",
  "workflow_policy": {
    "allow_ai_graph_repair": true,
    "allow_ai_evidence_decisions": false,
    "batch_auto_apply_low_risk": false,
    "trusted_ai_principals": ["agent:artana-kernel:graph-governor-v1"],
    "min_ai_confidence": 0.85
  }
}
```

`min_ai_confidence` means minimum DB-computed policy confidence. It is not an
LLM-authored self-score.

### Unified Workflow API

The primary workflow endpoints are:

```http
POST /v1/spaces/{space_id}/workflows
GET  /v1/spaces/{space_id}/workflows
GET  /v1/spaces/{space_id}/workflows/{workflow_id}
POST /v1/spaces/{space_id}/workflows/{workflow_id}/actions
```

Workflow kinds:

- `evidence_approval`
- `batch_review`
- `ai_evidence_decision`
- `conflict_resolution`
- `continuous_learning_review`
- `bootstrap_review`

Workflow statuses:

- `SUBMITTED`
- `PLAN_READY`
- `WAITING_REVIEW`
- `APPLIED`
- `REJECTED`
- `CHANGES_REQUESTED`
- `BLOCKED`
- `FAILED`

Workflow actions:

- `apply_plan`
- `approve`
- `reject`
- `request_changes`
- `split`
- `defer_to_human`
- `mark_resolved`

### Evidence Approval

Use `evidence_approval` when a caller wants to add evidence such as
`source relates to target`.

The service validates:

- source and target entity existence.
- relation type and relation constraint.
- evidence-required rules.
- duplicate and conflicting claims.
- dictionary or graph pieces that are missing.

If everything is valid and the operating mode allows it, the workflow can create
the official claim immediately.

If vocabulary or graph repair is missing, the workflow creates governed
proposals and stores the claim as `pending_claim_request`. The official claim is
created only after required dictionary and graph repair resources are resolved
and the claim validates again.

Example:

```json
{
  "kind": "evidence_approval",
  "input_payload": {
    "claim_request": {
      "source_entity_id": "00000000-0000-0000-0000-000000000001",
      "target_entity_id": "00000000-0000-0000-0000-000000000002",
      "relation_type": "ASSOCIATED_WITH",
      "assessment": {
        "support_band": "SUPPORTED",
        "grounding_level": "SPAN",
        "mapping_status": "RESOLVED",
        "speculation_level": "DIRECT",
        "confidence_rationale": "The cited source directly supports the claim."
      },
      "claim_text": "MED13 is associated with developmental delay.",
      "evidence_summary": "Synthetic example evidence.",
      "source_document_ref": "pubmed:example",
      "source_ref": "project:evidence:123"
    }
  },
  "source_ref": "project:workflow:123"
}
```

### Batch Review

Use `batch_review` when a caller wants to review mixed generated resources in
one governed packet.

Supported batch resource actions:

- `concept_proposal`: `approve`, `merge`, `reject`, `request_changes`.
- `dictionary_proposal`: `approve`, `reject`, `request_changes`.
- `graph_change_proposal`: `apply`, `reject`, `request_changes`.
- `connector_proposal`: `approve`, `reject`, `request_changes`.
- `claim`: `resolve`, `reject`, `needs_mapping`.
- `workflow`: `approve`, `reject`, `request_changes`, `defer_to_human`.

Example:

```json
{
  "kind": "batch_review",
  "input_payload": {
    "generated_resources": [
      {
        "resource_type": "concept_proposal",
        "resource_id": "00000000-0000-0000-0000-000000000010",
        "action": "approve",
        "input_hash": "current-resource-hash",
        "decision_payload": {},
        "reason": "Concept is valid."
      },
      {
        "resource_type": "graph_change_proposal",
        "resource_id": "00000000-0000-0000-0000-000000000011",
        "action": "apply",
        "input_hash": "current-resource-hash",
        "decision_payload": {},
        "reason": "Graph repair is valid."
      }
    ]
  },
  "source_ref": "project:batch:1"
}
```

Batch review applies resources through their normal governed services. It does
not mutate proposal tables directly.

Results are stored in the workflow payload:

- `applied_resource_refs`
- `failed_resource_refs`
- `batch_results`

If every item applies, the workflow becomes `APPLIED`. If some items fail, the
workflow becomes `CHANGES_REQUESTED`. Replaying the same batch is safe for
already-applied resources and should not duplicate official graph state.

### AI Authority

The graph DB does not trust the request body alone for AI authority.

For AI workflow actions and `/ai-decisions`, the body still includes
`ai_principal` for audit, but it must match the authenticated principal carried
by the graph-service token.

JWT claim:

```json
{
  "graph_ai_principal": "agent:artana-kernel:graph-governor-v1"
}
```

Test-only header, enabled only when test auth headers are allowed:

```text
X-TEST-GRAPH-AI-PRINCIPAL: agent:artana-kernel:graph-governor-v1
```

An AI action is accepted only when:

- the authenticated principal matches the declared body principal.
- the principal is trusted by the graph space policy.
- the input hash is current.
- the risk tier and operating mode allow the action.
- DB-computed confidence is above policy threshold.
- graph validation and evidence rules pass.
- no unresolved blocker or cross-space resource attempt exists.

Rejected workflow AI attempts are recorded in `graph_workflow_events` before
the API returns the error. Rejected `/ai-decisions` are persisted as rejected AI
decision records.

### Deterministic AI Confidence

The graph DB does not let an LLM decide its own numeric confidence.

AI callers submit qualitative evidence in a DB-owned `FactAssessment` shape:

```json
{
  "support_band": "STRONG",
  "grounding_level": "SPAN",
  "mapping_status": "RESOLVED",
  "speculation_level": "DIRECT",
  "confidence_rationale": "The cited span directly supports the decision."
}
```

The DB computes policy confidence with deterministic caps from:

- fact assessment strength.
- validation state.
- evidence state.
- duplicate or conflict state.
- source reliability.
- risk tier.

The computed confidence is a governance weight, not a true probability.

Hard blockers include:

- required evidence missing.
- invalid relation constraint.
- stale workflow or proposal hash.
- cross-space resource attempt.
- untrusted or mismatched AI principal.
- unresolved conflict.

### Explanation API

Use explanations to understand why a resource exists or why validation produced
a result.

Endpoints:

```http
GET  /v1/spaces/{space_id}/explain/{resource_type}/{resource_id}
POST /v1/spaces/{space_id}/validate/explain
```

Explanation responses are intended to answer:

- why this exists.
- who or what approved it.
- what evidence supported it.
- what policy allowed or blocked it.
- what generated resources were created.
- what next action is available.

### Lower-Level APIs

The workflow API is the main product-mode surface, but the graph service still
exposes lower-level APIs for direct control:

- graph spaces and memberships.
- entities, observations, provenance, relations, claims, and claim evidence.
- dictionary governance proposals.
- concept proposals and concept governance.
- graph-change proposals.
- connector proposals.
- AI decisions.
- validation and graph read models.

These lower-level APIs are useful for administrative tools, migrations,
specialized review surfaces, and advanced clients. The workflow API should be
the default integration path for new product flows.

Run locally with:

```bash
make graph-db-migrate
make run-graph-service
```

Docs:

- `services/artana_evidence_db/docs/README.md`
- interactive API docs at `/docs`
- raw OpenAPI at `services/artana_evidence_db/openapi.json`

Quality/contract checks:

```bash
make graph-service-checks
```

Required runtime environment:

- `GRAPH_DATABASE_URL`
- optional `GRAPH_DB_SCHEMA`
- `GRAPH_JWT_SECRET`
- optional `GRAPH_ALLOW_TEST_AUTH_HEADERS`
- optional `GRAPH_DB_POOL_SIZE`
- optional `GRAPH_DB_MAX_OVERFLOW`
- optional `GRAPH_DB_POOL_TIMEOUT_SECONDS`
- optional `GRAPH_DB_POOL_RECYCLE_SECONDS`
- optional `GRAPH_DB_POOL_USE_LIFO`
- optional `GRAPH_DOMAIN_PACK`
- optional `GRAPH_SERVICE_HOST`
- optional `GRAPH_SERVICE_PORT`
- optional `GRAPH_SERVICE_RELOAD`

Pack lifecycle reference:

- `docs/graph/reference/domain-pack-lifecycle.md`
  Documents how built-in packs are registered at startup, how
  `GRAPH_DOMAIN_PACK` selects the active pack, and where runtime composition is
  expected to consume pack-owned extensions.

Deployment/runtime notes:

- Cloud Run packaging uses `services/artana_evidence_db/Dockerfile`
- runtime images now copy only `services/artana_evidence_db` into `/app/artana_evidence_db`,
  plus service-local test assets in the separate `test` stage
- the Dockerfile now keeps a dedicated `test` stage for pytest inputs and a
  separate `runtime` stage so production images do not ship test assets
- local container flows can build the runtime image with `make graph-docker-build`
  or the test image with `make graph-docker-test-build`, then execute the test
  image with `make graph-docker-test`
- the dedicated deploy workflow is `.github/workflows/artana-evidence-db-deploy.yml`
- platform API/admin deploys now inject graph-service URLs through
  `scripts/deploy/sync_cloud_run_runtime_config.sh` so extracted callers do not
  fall back to `localhost`
- runtime and operational scripts now require explicit `GRAPH_SERVICE_URL`
  outside local/test environments
- when `GRAPH_DB_SCHEMA` is set to a non-`public` value, graph-service runtime
  sessions and graph migrations target that schema for graph-owned
  control-plane and governance tables
- dedicated-schema Postgres validation now passes for the standalone graph gate
  with `GRAPH_DB_SCHEMA=graph_runtime`
- deploy/runtime sync fails fast if graph URLs, graph secrets, or the configured
  graph migration job are missing
- deployed graph runtime validation also rejects reuse of the platform
  `DATABASE_URL` secret name for `GRAPH_DATABASE_URL`
