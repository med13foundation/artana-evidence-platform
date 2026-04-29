# Getting Started

## What This Service Is

`artana_evidence_db` is the standalone graph service.

It is the system that stores and serves:

- entities
- observations
- relations
- provenance
- claim-first curation records
- reasoning paths
- graph-space registry and memberships
- graph dictionary and concept governance data

In one sentence:

`artana_evidence_db` is the containerized HTTP boundary around the graph database model.

## What The Container Contains

The runtime container is defined in
[Dockerfile](../Dockerfile).

At runtime it contains:

- Python
- the `services/artana_evidence_db` package
- the service-local requirements from `services/artana_evidence_db/requirements.txt`

It does not need the full platform app runtime to start.

Its job is simple:

1. accept authenticated HTTP requests
2. verify graph-space access
3. read or write graph-owned tables
4. return typed JSON responses

## Default Local And Container Ports

- Local module run default: `8090`
- Container default: `8080`

Why both exist:

- local `python -m artana_evidence_db` uses `GRAPH_SERVICE_PORT` and defaults to `8090`
- the Docker image sets `GRAPH_SERVICE_PORT=8080`

## Run Locally

From the repository root:

```bash
source venv/bin/activate
make graph-db-migrate
PYTHONPATH="$(pwd)/services" python -m artana_evidence_db
```

Open:

- Interactive docs: `http://localhost:8090/docs`
- OpenAPI JSON: `http://localhost:8090/openapi.json`
- Health check: `http://localhost:8090/health`

If you override `GRAPH_SERVICE_PORT`, use that port instead.

## Run The Container

Build it from the repository root:

```bash
docker build -f services/artana_evidence_db/Dockerfile -t artana-evidence-db .
```

Run it:

```bash
docker run --rm -p 8090:8080 \
  -e GRAPH_DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5432/med13 \
  -e GRAPH_JWT_SECRET=change-me \
  artana-evidence-db
```

Open:

- Interactive docs: `http://localhost:8090/docs`
- OpenAPI JSON: `http://localhost:8090/openapi.json`
- Health check: `http://localhost:8090/health`

## Required Environment Variables

Required:

- `GRAPH_DATABASE_URL`
- `GRAPH_JWT_SECRET`

Common optional settings:

- `GRAPH_DB_SCHEMA`
- `GRAPH_SERVICE_NAME`
- `GRAPH_SERVICE_HOST`
- `GRAPH_SERVICE_PORT`
- `GRAPH_SERVICE_RELOAD`
- `GRAPH_JWT_ALGORITHM`
- `GRAPH_JWT_ISSUER`
- `GRAPH_ALLOW_TEST_AUTH_HEADERS`
- `GRAPH_DB_POOL_SIZE`
- `GRAPH_DB_MAX_OVERFLOW`
- `GRAPH_DB_POOL_TIMEOUT_SECONDS`
- `GRAPH_DB_POOL_RECYCLE_SECONDS`
- `GRAPH_DB_POOL_USE_LIFO`
- `GRAPH_DOMAIN_PACK`

## Authentication

Normal usage:

- send `Authorization: Bearer <token>`

The service resolves the JWT locally through `GRAPH_JWT_SECRET`.

Graph admin access is separate from normal space membership:

- normal graph-space routes require membership in the target space
- graph admin routes require the service-local `graph_admin` claim

## Local Test Auth Shortcut

For local non-production work, test headers are supported when
`GRAPH_ALLOW_TEST_AUTH_HEADERS=1`.

Example:

```bash
export GRAPH_URL="http://localhost:8090"

curl -s "$GRAPH_URL/v1/spaces/11111111-1111-1111-1111-111111111111/entities" \
  -H "X-TEST-USER-ID: 11111111-1111-1111-1111-111111111111" \
  -H "X-TEST-USER-EMAIL: researcher@example.com" \
  -H "X-TEST-USER-ROLE: researcher"
```

To simulate graph admin access locally:

```bash
curl -s "$GRAPH_URL/v1/admin/spaces/$SPACE_ID" \
  -H "X-TEST-USER-ID: 11111111-1111-1111-1111-111111111111" \
  -H "X-TEST-USER-EMAIL: admin@example.com" \
  -H "X-TEST-USER-ROLE: admin" \
  -H "X-TEST-GRAPH-ADMIN: 1"
```

Use this only for local development and tests.

## First Five Calls To Make

1. Check health:

```bash
curl -s "$GRAPH_URL/health"
```

2. List entities in one graph space:

```bash
curl -s "$GRAPH_URL/v1/spaces/$SPACE_ID/entities" \
  -H "Authorization: Bearer $TOKEN"
```

3. List relations in one graph space:

```bash
curl -s "$GRAPH_URL/v1/spaces/$SPACE_ID/relations" \
  -H "Authorization: Bearer $TOKEN"
```

4. List claim ledger rows:

```bash
curl -s "$GRAPH_URL/v1/spaces/$SPACE_ID/claims" \
  -H "Authorization: Bearer $TOKEN"
```

5. Export one graph document:

```bash
curl -s "$GRAPH_URL/v1/spaces/$SPACE_ID/graph/export" \
  -H "Authorization: Bearer $TOKEN"
```

## The Simplest Mental Model

Use this order:

1. The dictionary defines allowed types and variables.
2. An entity is a node.
3. An observation is a fact about one entity.
4. A relation is a canonical edge between two entities.
5. Provenance explains where a fact came from.
6. Claims are pre-canonical extracted relation candidates.
7. Read models and reasoning paths are derived views built from canonical graph state.
