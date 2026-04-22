# Graph Admin Guide

This guide is for admins and operators responsible for running, validating, and
troubleshooting the graph service.

## What Admins Own

Admins are responsible for the graph-service layer, not the entire MED13
platform.

That usually means:

- ensuring the graph service is reachable and correctly configured
- selecting and validating the intended built-in domain pack for the runtime
- keeping graph-space registry and membership state aligned with platform truth
- checking graph readiness before or after rollout
- running repair and rebuild workflows when graph state drifts
- inspecting operation-run history
- managing graph-specific dictionary governance

## What The Service Exposes For Admins

### Health And Runtime

- `GET /health`
  Basic liveness check
- graph-service runtime contract
  documented in [../reference/deployment-topology.md](../reference/deployment-topology.md)

### Graph Control Plane

- `/v1/admin/spaces`
- `/v1/admin/spaces/{space_id}`
- `/v1/admin/spaces/{space_id}/memberships`
- `/v1/admin/spaces/{space_id}/memberships/{user_id}`
- `/v1/admin/spaces/{space_id}/sync`

These endpoints let the standalone graph service manage its own graph-space
registry and graph-space membership snapshot.

### Operational Maintenance

- `/v1/admin/projections/readiness`
- `/v1/admin/projections/repair`
- `/v1/admin/reasoning-paths/rebuild`
- `/v1/admin/operations/runs`
- `/v1/admin/operations/runs/{run_id}`

These endpoints support readiness auditing, repair, path rebuilds, and run
history inspection.

### Dictionary Governance

All `/v1/dictionary/...` endpoints require graph-admin access and support
dictionary search, review-state changes, revoke/merge flows, re-embedding,
relation constraints, relation synonyms, value sets, variables, entity types,
relation types, and transform operations.

The exact contract is in [../reference/endpoints.md](../reference/endpoints.md).

## Common Admin Tasks

## 1. Check That The Service Is Alive

Use:

- `GET /health`

Look for:

- service reachable
- expected version returned
- no auth requirement on health

If this fails, start with deployment/runtime checks in
[../reference/deployment-topology.md](../reference/deployment-topology.md).

## 2. Verify Graph Runtime Wiring

Check the required runtime contract:

- `GRAPH_DATABASE_URL`
- optional `GRAPH_DB_SCHEMA`
- `GRAPH_JWT_SECRET`
- optional `GRAPH_ALLOW_TEST_AUTH_HEADERS`
- `GRAPH_DOMAIN_PACK`
- graph DB pool env vars when explicitly configured
- `GRAPH_SERVICE_URL` in backend/runtime callers
- `INTERNAL_GRAPH_API_URL` or `GRAPH_API_BASE_URL`
- `NEXT_PUBLIC_GRAPH_API_URL`

Built-in pack values today:

- `biomedical`
- `sports`

For deployment and promotion checks, use:

- `make graph-topology-validate`
- `make graph-service-checks`
- `make graph-phase6-release-check`
- `make graph-phase7-cross-domain-check`
- `.github/workflows/artana-evidence-db-deploy.yml`
- `scripts/deploy/validate_shared_instance_graph_topology.py`

Reference:
[../reference/deployment-topology.md](../reference/deployment-topology.md)
[../reference/runtime-alias-policy.md](../reference/runtime-alias-policy.md)

## 3. Reconcile Graph Spaces

Use graph-space sync when the graph service needs to be reconciled with
platform-owned space and membership truth.

Operational entrypoints:

- `make graph-space-sync`
- `scripts/sync_graph_spaces.py`
- `POST /v1/admin/spaces/{space_id}/sync`

Use this when:

- a space exists in the platform but not in the graph service
- memberships drifted
- graph-owned tenant metadata needs to be rebuilt from platform truth

## 4. Audit Readiness

Use readiness checks before rollout or after significant graph changes.

Operational entrypoints:

- `make graph-readiness`
- `scripts/check_claim_projection_readiness.py`
- `GET /v1/admin/projections/readiness`

The readiness audit looks for:

- orphan relations
- missing claim participants
- missing claim evidence
- linked-relation mismatches
- invalid projection relations

Reference:
[../reference/use-cases.md](../reference/use-cases.md) and
[../reference/examples.md](../reference/examples.md)

## 5. Repair Projection Issues

Use repair when readiness finds fixable graph-state problems.

Operational entrypoints:

- `POST /v1/admin/projections/repair`

The repair flow can:

- backfill participants
- materialize missing claims
- detach invalid projections
- persist an operation-run record

Always inspect the recorded run under `/v1/admin/operations/runs`.

## 6. Rebuild Reasoning Paths

Use path rebuilds when claim space changed enough that stored reasoning paths
may be stale.

Operational entrypoints:

- `make graph-reasoning-rebuild`
- `scripts/rebuild_reasoning_paths.py`
- `POST /v1/admin/reasoning-paths/rebuild`

Use this after:

- major claim triage changes
- claim-relation review updates
- bulk ingestion that materially changes grounded support paths

If graph-query latency regresses or rebuild/consistency behavior is in doubt,
also use the read-model validation material:

- `make graph-phase4-read-model-check`
- `make graph-read-model-benchmark`
- `docs/graph/reference/read-model-ownership.md`
- `docs/graph/reference/read-model-benchmarks.md`

## 7. Inspect Operation History

Use:

- `GET /v1/admin/operations/runs`
- `GET /v1/admin/operations/runs/{run_id}`

Run history is useful for:

- validating whether a repair or rebuild actually ran
- comparing request payload and summary payload
- spotting failed maintenance operations
- keeping an audit trail for graph-specific operational workflows

## 8. Manage Dictionary Governance

Use `/v1/dictionary/...` when graph-specific dictionary and governance state
needs intervention.

Typical actions:

- search dictionary entries
- update review status
- revoke or merge entries
- manage value sets and variables
- manage relation constraints and synonyms
- verify or promote transforms
- re-embed dictionary descriptions

### Relation Synonym Review Workflow

Extraction-policy mapping proposals can create relation synonyms with
`review_status=PENDING_REVIEW`. These proposed synonyms do not affect canonical
relation normalization until a graph admin approves them.

Recommended review steps:

1. List pending relation synonyms with
   `GET /v1/dictionary/relation-synonyms?review_status=PENDING_REVIEW`.
2. Confirm the synonym text should resolve to the proposed canonical relation
   type, using the source document or extraction run that produced the proposal.
3. Approve valid entries with
   `PATCH /v1/dictionary/relation-synonyms/{synonym_id}/review-status`.
4. Revoke invalid or ambiguous entries with
   `POST /v1/dictionary/relation-synonyms/{synonym_id}/revoke`.

After approval, future extraction runs can resolve that observed relation label
through deterministic dictionary synonym lookup before falling back to policy
mapping.

## Admin Access Model

Admin/control-plane operations require the graph-service-local `graph_admin`
claim.

Important distinctions:

- graph-space membership alone is not enough for `/v1/admin/...`
- graph-space membership alone is not enough for `/v1/dictionary/...`
- `POST /v1/spaces/{space_id}/relations` also requires `graph_admin`, even
  though it is a space-scoped route
- auth and tenancy semantics are pack-neutral; current cross-pack proof exists
  for both `biomedical` and `sports`

Reference:
[../developers/developer-guide.md](../developers/developer-guide.md)

## Common Failure Modes

### Service Unreachable

Usually means:

- bad runtime URL wiring
- deploy/runtime sync failure
- Cloud Run/service startup failure

Start with:

- `/health`
- deploy workflow logs
- topology validation

### 401 Or 403 On Admin Routes

Usually means:

- caller token missing `graph_admin`
- caller token invalid
- wrong runtime secret or issuer/algorithm mismatch

### Graph Space Drift

Usually means:

- platform truth changed but graph-space sync did not complete
- graph-owned tenant metadata is stale

Start with:

- space sync
- graph-space membership reads
- operation-run history

### Readiness Audit Not Clean

Usually means:

- claim data is incomplete
- projection lineage drift exists
- participant/evidence repair has not been run

Start with:

- readiness audit
- repair
- re-audit

## What To Read Next

- Exact API and access inventory: [../reference/endpoints.md](../reference/endpoints.md)
- Deployment/runtime model: [../reference/deployment-topology.md](../reference/deployment-topology.md)
- Runtime/module inventory: [../reference/service-inventory.md](../reference/service-inventory.md)
- Historical extraction context: [../history/service-migration-plan.md](../history/service-migration-plan.md)
