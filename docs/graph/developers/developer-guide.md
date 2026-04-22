# Graph Developer Guide

This guide is for developers who need to call, extend, or maintain the
standalone graph service.

## What You Are Working On

The graph service is a standalone FastAPI service inside the monorepo:

- runtime package: `services/artana_evidence_db/`
- ASGI entrypoint: `services.artana_evidence_db.main:app`

It owns the graph HTTP boundary while still reusing shared graph
domain/application/repository code under `src/`.

The important distinction is:

- `services/artana_evidence_db/`
  graph-service runtime boundary, auth, composition, routers, local helpers
- `src/...`
  shared domain/application/repository code reused by the graph service

Current implementation status:

- `graph-core` now lives under `src/graph/core/`
- built-in domain packs now live under `src/graph/domain_biomedical/` and
  `src/graph/domain_sports/`
- pack registration and active-pack selection are owned by
  `src/graph/pack_registry.py` and `src/graph/runtime.py`
- the migration and product-boundary work tracked in
  `docs/graph/history/migration-phase2*.md` is implemented and validated in the
  repo

## What To Read First

1. [../overview/what-this-service-does.md](../overview/what-this-service-does.md)
2. [../reference/endpoints.md](../reference/endpoints.md)
3. [../reference/architecture.md](../reference/architecture.md)
4. [../reference/domain-pack-lifecycle.md](../reference/domain-pack-lifecycle.md)
5. [../reference/service-inventory.md](../reference/service-inventory.md)
6. [../reference/read-model-ownership.md](../reference/read-model-ownership.md)
7. [../reference/release-policy.md](../reference/release-policy.md)

Use [../history/service-migration-plan.md](../history/service-migration-plan.md)
only when you need extraction history or rationale for why the boundary looks
the way it does.

## Source Of Truth

- `services/artana_evidence_db/openapi.json`
  Generated request/response contract
- `services/artana_evidence_db/routers/`
  Live route implementations
- `services/artana_evidence_db/artana-evidence-db.generated.ts`
  Generated TypeScript contract
- [../reference/endpoints.md](../reference/endpoints.md)
  Human-readable route inventory
- [../reference/architecture.md](../reference/architecture.md)
  Data model, projection, and invariant reference

If prose docs and generated contract disagree, trust `openapi.json`.

## Local Workflow

Run locally with:

```bash
make graph-db-migrate
make run-graph-service
```

Useful validation commands:

```bash
make graph-service-openapi
make graph-service-client-types
make graph-service-sync-contracts
make graph-service-checks
make graph-phase4-read-model-check
make graph-phase6-release-check
make graph-phase7-cross-domain-check
```

These cover:

- OpenAPI export
- generated TS client types
- graph-service lint/type/test/contract checks

## Runtime Contract

Required runtime env:

- `GRAPH_DATABASE_URL`
- `GRAPH_JWT_SECRET`
- optional `GRAPH_ALLOW_TEST_AUTH_HEADERS`

Common optional env:

- `GRAPH_DB_SCHEMA`
- `GRAPH_DB_POOL_SIZE`
- `GRAPH_DB_MAX_OVERFLOW`
- `GRAPH_DB_POOL_TIMEOUT_SECONDS`
- `GRAPH_DB_POOL_RECYCLE_SECONDS`
- `GRAPH_DB_POOL_USE_LIFO`
- `GRAPH_SERVICE_HOST`
- `GRAPH_SERVICE_PORT`
- `GRAPH_SERVICE_RELOAD`
- optional `GRAPH_DOMAIN_PACK`
  Defaults to `biomedical` today and controls pack-provided runtime defaults

Built-in pack values today:

- `biomedical`
- `sports`

Pack lifecycle reference:

- [../reference/domain-pack-lifecycle.md](../reference/domain-pack-lifecycle.md)
  Documents how packs are registered, selected, and consumed by runtime code

Cross-service caller env:

- backend callers use `GRAPH_SERVICE_URL`
- server-side web callers use `INTERNAL_GRAPH_API_URL` or `GRAPH_API_BASE_URL`
- browser callers use `NEXT_PUBLIC_GRAPH_API_URL`

Full deployment/runtime details:
[../reference/deployment-topology.md](../reference/deployment-topology.md)

## Auth And Access Model

### Authentication

- `GET /health` is unauthenticated
- all `/v1/...` endpoints require an authenticated caller
- end-user initiated calls use bearer JWTs
- local/test auth can use test headers when test auth is enabled

### Authorization

- space-scoped reads usually require graph-space membership
- most space-scoped writes require `researcher+`
- curation/review mutations require `curator+`
- `/v1/admin/...` and `/v1/dictionary/...` require `graph_admin`
- `POST /v1/spaces/{space_id}/relations` requires both space access and
  `graph_admin`

### RLS Behavior

The service sets DB session context for graph-space and graph-admin-aware reads
and writes. That means authz is enforced at both service and Postgres-session
levels when the backing store uses RLS-aware paths.

## Feature Flags And Optional Behavior

- `GRAPH_ENABLE_ENTITY_EMBEDDINGS`
  Enables entity similarity and embedding refresh
- `GRAPH_ENABLE_RELATION_SUGGESTIONS`
  Enables constrained relation suggestions
- `GRAPH_ENABLE_HYPOTHESIS_GENERATION`
  Enables auto-generated hypotheses
- `GRAPH_ENABLE_SEARCH_AGENT`
  Enables optional agent-assisted graph-search execution

Important nuance:

- graph search still exists without the graph-search agent
- graph connections still exist even if the Artana runtime is unavailable; the
  service falls back instead of removing the endpoint

Pack-owned behavior now includes:

- graph view types
- graph-search prompt and step-key behavior
- graph-connection prompt/default-source behavior
- relation-suggestion thresholds
- dictionary-loading defaults
- domain-context policy
- read-side heuristics and bootstrap content

## How A Typical Request Flows

1. A caller reaches a graph-service route in `services/artana_evidence_db/routers/`.
2. Auth resolves the caller and checks graph-admin or graph-space access.
3. Dependency providers build the needed services/repositories for the route.
4. The route calls shared graph application/domain services under `src/`.
5. The service returns typed responses through FastAPI/OpenAPI.

Useful runtime files:

- `services/artana_evidence_db/app.py`
- `services/artana_evidence_db/auth.py`
- `services/artana_evidence_db/config.py`
- `services/artana_evidence_db/database.py`
- `services/artana_evidence_db/dependencies.py`
- `services/artana_evidence_db/composition.py`
- `src/graph/pack_registry.py`
- `src/graph/runtime.py`
- `src/graph/core/`
- `src/graph/domain_biomedical/`
- `src/graph/domain_sports/`

## Where To Find Things

### Route Layer

- `services/artana_evidence_db/routers/`

### Runtime Wiring

- `services/artana_evidence_db/auth.py`
- `services/artana_evidence_db/config.py`
- `services/artana_evidence_db/database.py`
- `services/artana_evidence_db/dependencies.py`
- `services/artana_evidence_db/composition.py`

### Service-Local Helpers

- `services/artana_evidence_db/governance.py`
- `services/artana_evidence_db/dictionary_repository.py` (compatibility re-export)
- `services/artana_evidence_db/concept_repository.py` (compatibility re-export)
- `services/artana_evidence_db/graph_document_builder.py`
- `services/artana_evidence_db/operation_runs.py`

### Shared Graph Runtime Reused By The Service

- `src/graph/core/`
- `src/graph/runtime.py`
- `src/graph/product_contract.py`
- `src/application/services/kernel/`
- `src/application/agents/services/graph_search_service.py`
- `src/application/agents/services/graph_connection_service.py`
- `src/infrastructure/repositories/kernel/`
- `src/models/database/kernel/`

## How To Think About The Data Model

At a high level:

- claims are the detailed ledger
- canonical relations are the stable projection
- evidence and provenance explain what exists
- generic and reasoning read models accelerate supported reads, but remain
  derived and rebuildable
- hypotheses stay in claim space unless explicitly curated into stronger states

For the exact rules, read
[../reference/architecture.md](../reference/architecture.md).

## When To Use Each Reference Doc

- [../reference/endpoints.md](../reference/endpoints.md)
  When you need exact route inventory and access expectations
- [../reference/architecture.md](../reference/architecture.md)
  When you need to understand invariants and truth-model rules
- [../reference/use-cases.md](../reference/use-cases.md)
  When you want workflow-level behavior
- [../reference/examples.md](../reference/examples.md)
  When you want concrete payload and response examples
- [../reference/service-inventory.md](../reference/service-inventory.md)
  When you need to find runtime modules, callers, scripts, and tests
- [../reference/deployment-topology.md](../reference/deployment-topology.md)
  When you need runtime env, deploy, or topology details
- [../reference/read-model-ownership.md](../reference/read-model-ownership.md)
  When you need truth-boundary and rebuild rules for read models
- [../reference/release-policy.md](../reference/release-policy.md)
  When you need API versioning and generated-client ownership rules
- [../reference/cross-domain-validation-matrix.md](../reference/cross-domain-validation-matrix.md)
  When you need proof that the shared model works across the built-in packs

## What To Validate Before Shipping

- contract still matches `services/artana_evidence_db/openapi.json`
- generated TS types still match the API
- graph-service checks still pass
- boundary validation still passes
- feature-flagged behavior still documents enable/disable expectations
- admin/runtime env assumptions are still consistent with deployment topology
