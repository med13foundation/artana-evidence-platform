# Extracted Services Deploy Runbook

This runbook documents the deployment/runtime contract for the extracted
services in this repository and the minimum staging smoke checks to run after a
promotion.

It is grounded in the current extracted repo code and workflows:

- graph runtime: `services/artana_evidence_db/config.py`,
  `services/artana_evidence_db/database.py`,
  `services/artana_evidence_db/schema_support.py`
- evidence API runtime: `services/artana_evidence_api/config.py`,
  `services/artana_evidence_api/database.py`,
  `services/artana_evidence_api/db_schema.py`,
  `services/artana_evidence_api/auth.py`,
  `services/artana_evidence_api/evidence_db_auth.py`
- deploy/runtime sync: `scripts/deploy/sync_graph_cloud_run_runtime_config.sh`,
  `scripts/deploy/sync_artana_evidence_api_cloud_run_runtime_config.sh`
- GitHub Actions: `.github/workflows/artana-evidence-db-deploy.yml`,
  `.github/workflows/artana-evidence-api-deploy.yml`

## Shared Deploy Prerequisites

Both deploy workflows assume these GitHub Actions settings already exist:

- Secret: `GCP_PROJECT_ID`
- Variable: `GCP_WORKLOAD_IDENTITY_PROVIDER`
- Variable: `GCP_DEPLOYER_SERVICE_ACCOUNT`

Both workflows also assume Artifact Registry and Cloud Run live in
`us-central1`, matching the current workflow defaults.

Environment-specific workflow settings use one of these suffixes:

- `DEV`
- `STAGING`
- `PROD`

## Graph Service Runtime Contract

These are the runtime variables the graph container actually reads today.

| Variable | Required | Purpose | Current default / note |
| --- | --- | --- | --- |
| `GRAPH_DATABASE_URL` | Yes | Primary SQLAlchemy database URL for the standalone graph service. | No default in deployed use. Required by `get_settings()`. |
| `GRAPH_DB_SCHEMA` | No | Graph-owned PostgreSQL schema name. | Defaults to `graph_runtime`. Use `public` only when intentionally sharing schema space. |
| `GRAPH_JWT_SECRET` | Yes in deployed use | Secret used to validate graph bearer tokens. | Local/dev fallback exists, but production/staging should always set it. |
| `GRAPH_JWT_ALGORITHM` | No | JWT signing algorithm. | Defaults to `HS256`. |
| `GRAPH_JWT_ISSUER` | No | Expected JWT issuer for graph auth. | Falls back to the active graph domain pack issuer. |
| `GRAPH_SERVICE_NAME` | No | Human-readable service name returned by `/health`. | Falls back to the active graph domain pack runtime identity. |
| `GRAPH_SERVICE_HOST` | No | Bind host for the HTTP server. | Defaults to `0.0.0.0`. |
| `GRAPH_SERVICE_PORT` | No | Bind port for the HTTP server. | Defaults to `8090` locally; deploy workflow pins `8080`. |
| `GRAPH_SERVICE_RELOAD` | No | Dev reload toggle. | Defaults to `false`; deploy workflow pins `0`. |
| `GRAPH_ALLOW_TEST_AUTH_HEADERS` | No | Allows test auth headers outside JWT flows. | Keep off in deployed environments. |
| `GRAPH_DB_POOL_SIZE` | No | SQLAlchemy pool size. | Defaults to `10`. |
| `GRAPH_DB_MAX_OVERFLOW` | No | SQLAlchemy max overflow. | Defaults to `10`. |
| `GRAPH_DB_POOL_TIMEOUT_SECONDS` | No | SQLAlchemy pool timeout. | Defaults to `30`. |
| `GRAPH_DB_POOL_RECYCLE_SECONDS` | No | SQLAlchemy pool recycle interval. | Defaults to `1800`. |
| `GRAPH_DB_POOL_USE_LIFO` | No | SQLAlchemy LIFO pool toggle. | Defaults to `true`. |
| `GRAPH_ENABLE_ENTITY_EMBEDDINGS` | No | Enables graph embedding flows. | Deploy workflow can set it through runtime sync. |
| `GRAPH_ENABLE_SEARCH_AGENT` | No | Enables graph search agent behavior. | Deploy workflow can set it through runtime sync. |
| `GRAPH_ENABLE_RELATION_SUGGESTIONS` | No | Enables relation suggestion runtime features. | Deploy workflow can set it through runtime sync. |
| `GRAPH_ENABLE_HYPOTHESIS_GENERATION` | No | Enables hypothesis generation flows. | Deploy workflow can set it through runtime sync. |
| `ARTANA_POOL_MIN_SIZE` | No | Shared Artana runtime worker-pool minimum. | Runtime-sync managed in deploy environments. |
| `ARTANA_POOL_MAX_SIZE` | No | Shared Artana runtime worker-pool maximum. | Runtime-sync managed in deploy environments. |
| `ARTANA_COMMAND_TIMEOUT_SECONDS` | No | Shared Artana runtime command timeout. | Runtime-sync managed in deploy environments. |

### Graph Deploy Workflow Settings

The graph deploy workflow maps GitHub Actions settings into runtime env vars,
Cloud Run secrets, and the optional migration job.

| GitHub Actions setting | Required | Used for |
| --- | --- | --- |
| `DATABASE_URL_SECRET_NAME_<ENV_SUFFIX>` | Recommended | Platform DB secret name passed only for distinct-secret validation. |
| `GRAPH_CLOUDSQL_CONNECTION_NAME_<ENV_SUFFIX>` | No | Cloud SQL attachment for the graph service and migration job. |
| `GRAPH_DATABASE_URL_SECRET_NAME_<ENV_SUFFIX>` | Yes | Secret injected as `GRAPH_DATABASE_URL`. |
| `GRAPH_JWT_SECRET_NAME_<ENV_SUFFIX>` | Yes | Secret injected as `GRAPH_JWT_SECRET`. |
| `OPENAI_API_KEY_SECRET_NAME_<ENV_SUFFIX>` | No | Secret injected as `OPENAI_API_KEY` when graph AI features need it. |
| `GRAPH_MIN_INSTANCES_<ENV_SUFFIX>` | No | Cloud Run min instances. |
| `GRAPH_PUBLIC_<ENV_SUFFIX>` | No | Whether the service should allow unauthenticated invocations. |
| `GRAPH_DB_POOL_SIZE_<ENV_SUFFIX>` | No | Runtime pool size override. |
| `GRAPH_DB_MAX_OVERFLOW_<ENV_SUFFIX>` | No | Runtime max overflow override. |
| `GRAPH_DB_POOL_TIMEOUT_SECONDS_<ENV_SUFFIX>` | No | Runtime pool timeout override. |
| `GRAPH_DB_POOL_RECYCLE_SECONDS_<ENV_SUFFIX>` | No | Runtime pool recycle override. |
| `GRAPH_DB_POOL_USE_LIFO_<ENV_SUFFIX>` | No | Runtime pool LIFO override. |
| `GRAPH_MIGRATION_JOB_NAME_<ENV_SUFFIX>` | No | Optional Cloud Run job name for graph migrations. |
| `ARTANA_ENABLE_GRAPH_SEARCH_AGENT_<ENV_SUFFIX>` | No | Graph runtime feature flag. |
| `ARTANA_ENABLE_RELATION_SUGGESTIONS_<ENV_SUFFIX>` | No | Graph runtime feature flag. |
| `ARTANA_ENABLE_HYPOTHESIS_GENERATION_<ENV_SUFFIX>` | No | Graph runtime feature flag. |
| `ARTANA_POOL_MIN_SIZE_<ENV_SUFFIX>` | No | Shared Artana pool minimum. |
| `ARTANA_POOL_MAX_SIZE_<ENV_SUFFIX>` | No | Shared Artana pool maximum. |
| `ARTANA_COMMAND_TIMEOUT_SECONDS_<ENV_SUFFIX>` | No | Shared Artana command timeout. |

## Evidence API Runtime Contract

These are the runtime variables the evidence API container actually reads today.

| Variable | Required | Purpose | Current default / note |
| --- | --- | --- | --- |
| `ARTANA_EVIDENCE_API_DATABASE_URL` or `DATABASE_URL` | Yes | Primary SQLAlchemy database URL for the evidence API runtime. | Deploy workflow injects `ARTANA_EVIDENCE_API_DATABASE_URL`. |
| `ARTANA_EVIDENCE_API_DB_SCHEMA` | No | Harness-owned PostgreSQL schema. | Defaults to `artana_evidence_api`. |
| `GRAPH_DB_SCHEMA` | No | Graph schema appended into the harness search path. | Defaults to `graph_runtime`. |
| `ARTANA_EVIDENCE_API_APP_NAME` | No | Service name returned by `/health`. | Defaults to `Artana Evidence API`. |
| `ARTANA_EVIDENCE_API_SERVICE_HOST` | No | Bind host for the HTTP server. | Defaults to `0.0.0.0`. |
| `ARTANA_EVIDENCE_API_SERVICE_PORT` | No | Bind port for the HTTP server. | Defaults to `8080` via `PORT` fallback; deploy workflow pins `8080`. |
| `ARTANA_EVIDENCE_API_SERVICE_RELOAD` | No | Dev reload toggle. | Defaults to `false`; deploy workflow pins `0`. |
| `ARTANA_EVIDENCE_API_SERVICE_WORKERS` | No | API worker count. | Defaults to `1`. |
| `GRAPH_API_URL` | Yes | Typed HTTP base URL for the graph service. | Local default is `http://127.0.0.1:8090`; deploy must override it. |
| `ARTANA_EVIDENCE_API_GRAPH_API_TIMEOUT_SECONDS` | No | Timeout for graph HTTP calls. | Defaults to `30.0`. |
| `AUTH_JWT_SECRET` | Yes in staging/production | Secret used for harness auth token validation. | Development fallback exists only outside staging/production. |
| `AUTH_ALLOW_TEST_AUTH_HEADERS` | No | Allows test auth headers. | Keep off in deployed environments. |
| `ARTANA_EVIDENCE_API_BOOTSTRAP_KEY` | Recommended for fresh environments | Allows the one-time bootstrap API-key flow. | Can be removed later through runtime sync. |
| `GRAPH_JWT_SECRET` | Yes when evidence calls the graph service | Secret used to mint service-to-service graph tokens. | Development fallback exists; deploy should set it. |
| `GRAPH_JWT_ISSUER` | No | Issuer for service-to-service graph tokens. | Defaults to `graph-biomedical`. |
| `GRAPH_SERVICE_SERVICE_USER_ID` | No | Default graph-side service user id used by evidence API calls. | Falls back to `00000000-0000-0000-0000-000000000001`. |
| `GRAPH_SERVICE_AI_PRINCIPAL` | No | Optional default graph AI principal claim. | Only needed for AI-authority submissions. |
| `OPENAI_API_KEY` or `ARTANA_OPENAI_API_KEY` | Recommended for AI-backed flows | Enables Artana/OpenAI model calls. | Required for real extraction/search/onboarding behavior. |
| `DRUGBANK_API_KEY` | No | Enables DrugBank-backed flows when used. | Optional. |
| `ARTANA_EVIDENCE_API_DB_POOL_SIZE` | No | SQLAlchemy pool size. | Defaults to `10`. |
| `ARTANA_EVIDENCE_API_DB_MAX_OVERFLOW` | No | SQLAlchemy max overflow. | Defaults to `10`. |
| `ARTANA_EVIDENCE_API_DB_POOL_TIMEOUT_SECONDS` | No | SQLAlchemy pool timeout. | Defaults to `30`. |
| `ARTANA_EVIDENCE_API_DB_POOL_RECYCLE_SECONDS` | No | SQLAlchemy pool recycle interval. | Defaults to `1800`. |
| `ARTANA_EVIDENCE_API_DB_POOL_USE_LIFO` | No | SQLAlchemy LIFO pool toggle. | Defaults to `true`. |
| `ARTANA_EVIDENCE_API_SCHEDULER_POLL_SECONDS` | No | Scheduler loop poll interval. | Defaults to `300`. |
| `ARTANA_EVIDENCE_API_SCHEDULER_RUN_ONCE` | No | Scheduler one-shot mode. | Defaults to `false`. |
| `ARTANA_EVIDENCE_API_WORKER_ID` | No | Leased worker identity. | Defaults to `artana-evidence-api-worker`. |
| `ARTANA_EVIDENCE_API_WORKER_POLL_SECONDS` | No | Worker poll interval. | Defaults to `1`. |
| `ARTANA_EVIDENCE_API_WORKER_RUN_ONCE` | No | Worker one-shot mode. | Defaults to `false`. |
| `ARTANA_EVIDENCE_API_WORKER_LEASE_TTL_SECONDS` | No | Worker lease TTL. | Defaults to `300`. |
| `ARTANA_EVIDENCE_API_SYNC_WAIT_TIMEOUT_SECONDS` | No | Inline sync wait timeout. | Defaults to `55`. |
| `ARTANA_EVIDENCE_API_SYNC_WAIT_POLL_SECONDS` | No | Inline sync wait poll interval. | Defaults to `0.25`. |
| `ARTANA_EVIDENCE_API_STORAGE_BASE_PATH` | No | Local document/artifact storage base path. | Defaults to a tempdir-backed path. |
| `SPACE_ACL_MODE` | No | Space ACL handling mode. | Defaults to `audit`. |
| `ARTANA_POOL_MIN_SIZE` | No | Shared Artana runtime worker-pool minimum. | Runtime-sync managed in deploy environments. |
| `ARTANA_POOL_MAX_SIZE` | No | Shared Artana runtime worker-pool maximum. | Runtime-sync managed in deploy environments. |
| `ARTANA_COMMAND_TIMEOUT_SECONDS` | No | Shared Artana runtime command timeout. | Runtime-sync managed in deploy environments. |

### Evidence API Deploy Workflow Settings

| GitHub Actions setting | Required | Used for |
| --- | --- | --- |
| `GRAPH_HARNESS_CLOUDSQL_CONNECTION_NAME_<ENV_SUFFIX>` | No | Cloud SQL attachment for the evidence API service and migration job. |
| `GRAPH_HARNESS_DATABASE_URL_SECRET_NAME_<ENV_SUFFIX>` | Yes | Secret injected as `ARTANA_EVIDENCE_API_DATABASE_URL`. |
| `ARTANA_JWT_SECRET_NAME_<ENV_SUFFIX>` | Yes in staging/production | Secret injected as `AUTH_JWT_SECRET`. |
| `OPENAI_API_KEY_SECRET_NAME_<ENV_SUFFIX>` | Recommended | Secret injected as `OPENAI_API_KEY` for AI-backed flows. |
| `DRUGBANK_API_KEY_SECRET_NAME_<ENV_SUFFIX>` | No | Secret injected as `DRUGBANK_API_KEY` when needed. |
| `ARTANA_EVIDENCE_API_BOOTSTRAP_KEY_SECRET_NAME_<ENV_SUFFIX>` | Recommended for fresh environments | Secret injected as `ARTANA_EVIDENCE_API_BOOTSTRAP_KEY`. |
| `ARTANA_EVIDENCE_API_REMOVE_BOOTSTRAP_KEY_<ENV_SUFFIX>` | No | Removes the bootstrap key after initial setup if desired. |
| `GRAPH_PUBLIC_URL_<ENV_SUFFIX>` | Yes | Passed through as `GRAPH_API_URL`. |
| `GRAPH_HARNESS_MIN_INSTANCES_<ENV_SUFFIX>` | No | Cloud Run min instances. |
| `GRAPH_HARNESS_PUBLIC_<ENV_SUFFIX>` | No | Whether the evidence API should allow unauthenticated invocations. |
| `GRAPH_HARNESS_DB_POOL_SIZE_<ENV_SUFFIX>` | No | Runtime pool size override. |
| `GRAPH_HARNESS_DB_MAX_OVERFLOW_<ENV_SUFFIX>` | No | Runtime max overflow override. |
| `GRAPH_HARNESS_DB_POOL_TIMEOUT_SECONDS_<ENV_SUFFIX>` | No | Runtime pool timeout override. |
| `GRAPH_HARNESS_DB_POOL_RECYCLE_SECONDS_<ENV_SUFFIX>` | No | Runtime pool recycle override. |
| `GRAPH_HARNESS_DB_POOL_USE_LIFO_<ENV_SUFFIX>` | No | Runtime pool LIFO override. |
| `GRAPH_HARNESS_MIGRATION_JOB_NAME_<ENV_SUFFIX>` | No | Optional Cloud Run job name for evidence API migrations. |
| `ARTANA_POOL_MIN_SIZE_<ENV_SUFFIX>` | No | Shared Artana pool minimum. |
| `ARTANA_POOL_MAX_SIZE_<ENV_SUFFIX>` | No | Shared Artana pool maximum. |
| `ARTANA_COMMAND_TIMEOUT_SECONDS_<ENV_SUFFIX>` | No | Shared Artana command timeout. |

## Staging Smoke Checklist

These are the minimum post-deploy checks to run after promoting to staging.

Set these first:

```bash
export GRAPH_URL="https://<graph-service-staging-url>"
export EVIDENCE_URL="https://<evidence-api-staging-url>"
```

### 1. Graph service liveness

```bash
curl -fsS "$GRAPH_URL/health"
curl -fsS "$GRAPH_URL/openapi.json" | jq '.info.title, .info.version'
```

Expected:

- `/health` returns HTTP 200
- response `status` is `ok`
- `service` and `version` are non-empty
- `/openapi.json` returns a valid schema document

### 2. Evidence API liveness

```bash
curl -fsS "$EVIDENCE_URL/health"
curl -fsS "$EVIDENCE_URL/openapi.json" | jq '.info.title, .info.version'
```

Expected:

- `/health` returns HTTP 200
- response `status` is `ok`
- `service` and `version` are non-empty
- `/openapi.json` returns a valid schema document

Notes:

- `scheduler` and `worker` may legitimately show `unknown` unless those loops
  are also running in staging and writing heartbeat files.
- `artana_model.probe.status` may be `degraded` if model credentials are absent
  in that environment; treat that as a deployment issue only when the staging
  environment is supposed to exercise AI-backed flows.

### 3. Evidence API auth smoke

If staging already has a valid user token:

```bash
export TOKEN="<staging-user-token>"
curl -fsS "$EVIDENCE_URL/v1/auth/me" \
  -H "Authorization: Bearer $TOKEN"
```

If this is the first bootstrap on a fresh staging environment:

```bash
export BOOTSTRAP_KEY="<staging-bootstrap-key>"
curl -fsS -X POST "$EVIDENCE_URL/v1/auth/bootstrap" \
  -H "Content-Type: application/json" \
  -H "X-Artana-Bootstrap-Key: $BOOTSTRAP_KEY" \
  -d '{
    "email": "staging-admin@example.com",
    "username": "staging-admin",
    "full_name": "Staging Admin",
    "role": "admin",
    "create_default_space": true,
    "api_key_name": "Staging Smoke Key",
    "api_key_description": "Initial staging smoke bootstrap"
  }'
```

Expected:

- authenticated `GET /v1/auth/me` returns HTTP 200 and the expected user
- bootstrap returns HTTP 201 on a fresh environment, or HTTP 409 once staging
  has already been bootstrapped

### 4. Escalate if any of these fail

- graph `/health` is not `ok`
- evidence `/health` is not `ok`
- the graph or evidence OpenAPI document is unavailable
- staging auth fails when valid credentials are supplied
- the evidence API still points at `localhost` for `GRAPH_API_URL`
  after deploy/runtime sync
