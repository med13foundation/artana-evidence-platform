# Graph Service Deployment Topology

This document defines the supported deployment topologies for the standalone
graph service and the forward migration path from a shared Postgres instance to
a dedicated graph database.

It also reflects the current pack-aware runtime contract:

- the graph service starts through explicit pack registration
- the active pack is selected with `GRAPH_DOMAIN_PACK`
- the built-in packs are `biomedical` and `sports`

## Supported topologies

### Shared-instance topology

This is the active production/dev topology.

- The platform app and graph service run as separate services.
- The graph service is the only service allowed to mutate graph-owned tables.
- Both services may point at the same Postgres instance.
- The graph service uses its own runtime contract and its own database secret:
  - `GRAPH_DATABASE_URL`
  - optional `GRAPH_DB_SCHEMA`
  - `GRAPH_JWT_SECRET`
- In deployed environments, the graph DB secret name must differ from the
  platform `DATABASE_URL` secret name even when both services still target the
  same Postgres instance.
- Platform callers reach the graph service over HTTP only:
  - backend callers use `GRAPH_SERVICE_URL`
  - server-side web callers use `INTERNAL_GRAPH_API_URL` or `GRAPH_API_BASE_URL`
  - browser callers use `NEXT_PUBLIC_GRAPH_API_URL`
- Outside local/test environments, graph callers do not fall back to
  `localhost`.

Operational implications:

- Graph schema changes are applied through `python -m services.artana_evidence_db.manage`
  and the graph-service deploy workflow.
- When `GRAPH_DB_SCHEMA` is set to a non-`public` value, graph-owned
  control-plane tables (`graph_spaces`, `graph_space_memberships`,
  `graph_operation_runs`) and graph governance tables (dictionary/concept
  management storage) run from that schema and graph-service Postgres sessions
  use a schema-aware `search_path`.
- Graph rebuild/readiness/backfill/reasoning operations are executed through the
  graph service admin APIs.
- Platform deploy/runtime sync must provide graph URL env vars so platform code
  never reverts to in-process or localhost graph behavior.

### Dedicated-database topology

This is the target topology for future isolation.

- The graph service points at its own Postgres instance using `GRAPH_DATABASE_URL`.
- The platform app no longer shares the graph database instance at all.
- API shape does not change.
- The graph control-plane APIs remain the tenant-sync boundary for graph-owned
  `graph_spaces` and `graph_space_memberships`.

## Required runtime configuration

### Graph service

- `GRAPH_DATABASE_URL`
- `GRAPH_DB_SCHEMA`
- `GRAPH_JWT_SECRET`
- optional `GRAPH_ALLOW_TEST_AUTH_HEADERS`
- `GRAPH_DOMAIN_PACK`
- `GRAPH_DB_POOL_SIZE`
- `GRAPH_DB_MAX_OVERFLOW`
- `GRAPH_DB_POOL_TIMEOUT_SECONDS`
- `GRAPH_DB_POOL_RECYCLE_SECONDS`
- `GRAPH_DB_POOL_USE_LIFO`

### Platform backend

- `GRAPH_SERVICE_URL`

### Web/admin runtime

- `INTERNAL_GRAPH_API_URL` or `GRAPH_API_BASE_URL`
- `NEXT_PUBLIC_GRAPH_API_URL`

## Shared-instance production checklist

- Graph deploy workflow uses `GRAPH_DATABASE_URL_SECRET_NAME`.
- Graph deploy/runtime validation rejects `GRAPH_DATABASE_URL_SECRET_NAME` when
  it matches the platform `DATABASE_URL_SECRET_NAME`.
- Graph deploy workflow uses `GRAPH_JWT_SECRET_NAME`.
- Platform deploy/runtime sync injects `GRAPH_SERVICE_URL`.
- Platform deploy/runtime sync injects admin/web graph URL env vars.
- Graph migration job exists when `GRAPH_MIGRATION_JOB_NAME` is configured.
- Deploy workflows run `scripts/deploy/validate_shared_instance_graph_topology.py`
  after runtime sync to confirm graph URL wiring, admin/web graph env wiring,
  graph migration job presence, and shared Cloud SQL alignment from deployed
  Cloud Run metadata.
- The same validation can be run manually with `make graph-topology-validate`
  when the required deploy env vars and `gcloud` auth are present.
- Graph callers do not rely on localhost fallback in non-local environments.
- Graph boundary validation passes before deploy.
- Graph invariant and performance gates pass against the standalone service
  boundary.
- Dedicated-schema validation (`GRAPH_DB_SCHEMA=graph_runtime`) passes for the
  Postgres-backed graph suite and graph performance suite.

## Promotion and validation procedure

Use this procedure for the first real dev/staging/production promotion and for
subsequent shared-instance topology checks.

### Required deploy/runtime values

- Graph service deploy/runtime:
  - `GRAPH_DATABASE_URL_SECRET_NAME`
  - `GRAPH_JWT_SECRET_NAME`
  - `GRAPH_PUBLIC_URL`
  - `GRAPH_CLOUDSQL_CONNECTION_NAME`
  - optional `GRAPH_MIGRATION_JOB_NAME`
- Platform API deploy/runtime:
  - `GRAPH_SERVICE_URL`
  - `CLOUDSQL_CONNECTION_NAME`
- Admin/web deploy/runtime:
  - `INTERNAL_GRAPH_API_URL` or `GRAPH_API_BASE_URL`
  - `NEXT_PUBLIC_GRAPH_API_URL`

### Workflow path

1. Run the graph-service deploy workflow for the target environment.
2. Let the workflow complete runtime sync for the graph service.
3. Let the workflow run the `Validate shared-instance graph topology (...)`
   step.
4. Confirm the workflow summary contains a dedicated
   `Shared-instance topology validation (...)` block with the validator output.
5. Run the platform deploy workflow for the same environment.
6. Confirm the platform workflow summary also contains the matching topology
   validation block after runtime sync.

### Manual path

Use this when validating outside the GitHub workflow:

1. Authenticate `gcloud` against the target project.
2. Export the same env vars used by the workflow for the target environment.
3. Run `make graph-topology-validate`.
4. Record the validator output in the deployment notes or release log.

### Expected success signals

- The validator exits `0`.
- The workflow summary shows the validator output block.
- The validator confirms:
  - graph service URL matches the configured public graph URL
  - platform API runtime points at that graph URL
  - admin/web runtime graph URLs point at that graph URL
  - platform and graph services share the expected Cloud SQL instance
  - the configured graph migration job exists when specified

For current product-boundary validation beyond topology, also use:

- `make graph-service-checks`
- `make graph-phase6-release-check`
- `make graph-phase7-cross-domain-check`

### Rollback trigger

Rollback or stop promotion if any of these happen:

- validator exits non-zero
- workflow summary shows a mismatch for graph URL wiring
- workflow summary shows a Cloud SQL mismatch
- workflow summary shows a missing graph migration job

Rollback action:

- revert the runtime config change or image promotion that introduced the
  mismatch
- rerun the topology validator
- do not continue the environment promotion until the validator passes cleanly

## Dedicated-database migration playbook

This is the forward-only migration path when the team decides to move off the
shared Postgres instance.

### 1. Prepare the target database

- Provision a new Postgres instance for the graph service.
- Create a graph-specific runtime user and a graph-specific migration user.
- Store the dedicated runtime connection string in a new graph secret.

### 2. Validate schema parity

- Run `python -m services.artana_evidence_db.manage migrate` against the new database.
- Confirm the dedicated database reaches the current Alembic head.
- Verify graph-owned tables exist:
  - `graph_spaces`
  - `graph_space_memberships`
  - `graph_operation_runs`
  - all graph kernel tables owned by the service

### 3. Copy graph-owned data

- Freeze graph writes briefly at the graph-service layer.
- Export graph-owned tables from the shared instance.
- Import them into the dedicated graph database.
- Verify row counts and primary key parity for:
  - graph tenant tables
  - claim-ledger tables
  - canonical relation tables
  - reasoning-path tables
  - governance tables
  - operation history tables

### 4. Switch graph runtime

- Update only the graph service secret/config to the dedicated
  `GRAPH_DATABASE_URL`.
- Do not change platform caller URLs or graph API routes.
- Run graph readiness and reasoning rebuild audits after cutover.

### 5. Validate post-cutover invariants

- Run the graph invariant suite.
- Run Postgres graph isolation/RLS tests.
- Run graph performance tests.
- Confirm graph admin endpoints and graph control-plane sync still work.

### 6. Remove shared-instance dependency

- Remove graph-table access from the old shared-instance operational path.
- Keep the platform app pointed only at the graph HTTP API.
- Retain the shared-instance DB backup until the new topology is validated.

## Rollback approach

If the dedicated-database cutover fails:

- restore the graph service to the previous shared-instance
  `GRAPH_DATABASE_URL`
- rerun graph readiness/rebuild checks
- investigate data drift before retrying the migration

The platform app does not need a contract rollback because the graph API does
not change across the topology move.
