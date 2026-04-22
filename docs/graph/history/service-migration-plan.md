# Graph Service Migration Plan

This document defines the complete migration plan for extracting the current
graph/kernel bounded context into an independent Python API service.

The target is a standalone `graph-service` that:

- owns the graph API
- owns graph persistence and graph-governing validation data
- preserves `space_id` as the multitenant isolation boundary
- is consumed only over HTTP by this platform and future services
- has no UI dependency

The graph contract remains:

```text
evidence -> claims -> projections -> canonical graph -> reasoning artifacts
```

## Status

- Service style: Python-only API service
- External API style: `/v1/spaces/{space_id}/...`
- Tenant model: spaces remain the primary isolation boundary
- Dictionary model: graph service owns graph-governing dictionary validation data
- Runtime model: no permanent proxy layer through the current app
- Database topology: support both shared-Postgres-first and dedicated-Postgres-later
- Progress: phases 0, 1, 2, 3, 4, 5, 6, 7, and 9 are complete in-repo; phase 8 remains open only for the first successful real deployed shared-instance topology-validation run
- Current implementation:
  - `services/artana_evidence_db/` service package
  - service-local auth and DB session wiring
  - schema-level foreign key coupling from graph-owned tables to `users` and `source_documents` has been removed
  - standalone graph-service authz now resolves space access through a graph-local space access port instead of the platform membership service
  - graph-connection composition now resolves tenant settings through a graph-local space settings port instead of the platform `ResearchSpaceRepository`
  - graph-owned runtime now resolves tenant metadata through a graph-local space registry adapter for owner checks, settings lookup, auto-promotion policy resolution, and global reasoning-path rebuild enumeration
  - graph-owned tenant metadata now persists in a graph-owned `graph_spaces` table plus standalone admin registry APIs instead of being read from the platform `research_spaces` table
  - graph-service authz and tenant-member sync now use graph-owned `graph_space_memberships` plus standalone admin membership APIs instead of the platform `research_space_memberships` table
  - standalone graph-service admin APIs now support atomic graph-space sync, including full graph-owned membership snapshot replacement for one space
  - platform space lifecycle and membership write routes now push authoritative tenant snapshots into the standalone graph service after successful platform writes
  - platform space and membership application services now own graph tenant sync through a graph control-plane port instead of repeating route-level sync calls
  - platform now has a dedicated tenant reconciliation service and `scripts/sync_graph_spaces.py` / `make graph-space-sync` to rebuild graph-space state from platform space and membership truth
  - architecture validation now runs `scripts/validate_graph_service_boundary.py` to fail on new direct imports of graph internals outside the standalone service and an explicit shrinking legacy allowlist
  - the legacy platform provenance route now calls the standalone graph service over HTTP and no longer requires a direct kernel-service allowlist exception
  - the legacy platform reasoning-path route now calls the standalone graph service over HTTP and no longer requires a direct kernel-service allowlist exception
  - the legacy platform graph-view route now calls the standalone graph service over HTTP and no longer requires a direct kernel-service allowlist exception
  - the legacy platform entity route now calls the standalone graph service over HTTP and no longer requires a direct kernel-service allowlist exception
  - the legacy platform observation route now calls the standalone graph service over HTTP and no longer requires a direct kernel-service allowlist exception
  - kernel graph tables no longer carry direct foreign keys to the platform `research_spaces` table, and baseline/Postgres RLS policy checks now resolve tenant access through `graph_spaces` plus `graph_space_memberships`
  - graph control-plane routes now require a graph-service-local admin claim instead of inferring admin access from the platform `UserRole.ADMIN` role
  - standalone graph-service runtime now requires an explicit `GRAPH_DATABASE_URL`, uses graph-local `GRAPH_DB_*` pool settings, and has its own `python -m services.artana_evidence_db` entrypoint instead of inheriting the platform database resolver contract
  - graph-service DB wait/migrate operations now run through `python -m services.artana_evidence_db.manage` and dedicated `make graph-db-wait` / `make graph-db-migrate` targets instead of the shared platform migration command path
  - graph-service Alembic config and migration assets now live under `services/artana_evidence_db/alembic.ini` and `services/artana_evidence_db/alembic/`, and both the service runtime and repo test/bootstrap paths execute migrations through that service-local config
  - service-local container packaging now exists under `services/artana_evidence_db/Dockerfile`
  - graph-service Cloud Run runtime sync now exists under `scripts/deploy/sync_graph_cloud_run_runtime_config.sh`
  - graph-service promotion now has a dedicated GitHub Actions workflow under `.github/workflows/artana-evidence-db-deploy.yml`
  - service-local quality/contract automation now exists under `make graph-service-lint`, `make graph-service-type-check`, `make graph-service-contract-check`, `make graph-service-test`, and `make graph-service-checks`
  - shared-instance deploy validation can now be run manually with `make graph-topology-validate` in addition to the workflow-integrated validator
  - graph-service OpenAPI export now lives under `scripts/export_graph_openapi.py` and the generated contract artifact under `services/artana_evidence_db/openapi.json`
  - generated TypeScript graph-service contract types now live under `src/web/types/artana-evidence-db.generated.ts`
  - neutral shared graph-runtime helpers now live under `src/database/graph_schema.py`, `src/infrastructure/queries/graph_security_queries.py`, `src/infrastructure/dependency_injection/graph_runtime_factories.py`, and related neutral `src/...` modules, so platform code no longer imports `services.artana_evidence_db.*`
  - neutral shared graph API schema definitions now live under `src/type_definitions/graph_api_schemas/`, and `src/type_definitions/graph_service_contracts.py` no longer depends on route-layer schema modules
  - graph view assembly now depends on a graph-local source-document reference port instead of the platform `SourceDocumentRepository` contract
  - standalone read endpoints under `/v1/spaces/{space_id}/...`
  - entity endpoints under `/v1/spaces/{space_id}/entities/...`
  - observation endpoints under `/v1/spaces/{space_id}/observations/...`
  - provenance endpoints under `/v1/spaces/{space_id}/provenance/...`
  - canonical relation create and curation-update endpoints under `/v1/spaces/{space_id}/relations/...`
  - canonical graph export and unified graph document endpoints
  - claim-ledger reads, triage mutation, and claim-relation endpoints
  - graph-view and mechanism-chain endpoints
  - graph-search endpoint under `/v1/spaces/{space_id}/graph/search`
  - graph-connection discovery endpoints under `/v1/spaces/{space_id}/graph/connections/...`
  - relation-suggestion endpoint under `/v1/spaces/{space_id}/graph/relation-suggestions`
  - dictionary governance endpoints under `/v1/dictionary/...`
  - concept governance endpoints under `/v1/spaces/{space_id}/concepts/...`
  - hypothesis workflow endpoints under `/v1/spaces/{space_id}/hypotheses/...`
  - service-local governance adapters/builders now own dictionary/concept composition inside `services/artana_evidence_db/`
  - typed Python client under `src/infrastructure/graph_service/` for entity, observation, provenance, relation write, read, search, relation-suggestion, hypothesis, export/document, and graph-connection discovery APIs
  - typed TypeScript graph client surface under `src/web/lib/api/graph-client.ts` that re-exports the supported web graph API helper layer
  - operational readiness and reasoning-rebuild scripts now call the graph service over HTTP
  - `make graph-readiness` and `make graph-reasoning-rebuild` now target the service boundary
  - pipeline orchestration graph-seed discovery now calls the standalone graph service over HTTP
  - user-triggered pipeline graph seed inference now uses a user-scoped graph-service search adapter over HTTP
  - durable pipeline workers now use service-to-service graph search and graph-connection adapters over HTTP
  - post-ingestion graph discovery hooks now call the standalone graph service over HTTP
  - the minimal full-workflow script now uses standalone graph search and graph-connection service clients
  - web entity/observation/provenance/relation-write/graph/concept/search/hypothesis/relation-suggestion/graph-connection API helpers now target the standalone graph service base URL for extracted `/v1/spaces/{space_id}/...` endpoints
  - platform API/admin deploy runtime wiring now injects graph-service URLs so extracted callers do not fall back to localhost in deployed environments
  - platform research-space integration tests now keep a file-local minimal recording graph-sync stub for tenant control-plane coverage only, and shared platform API test harness code no longer carries graph-specific setup
  - standalone graph-service auth now derives JWT-backed synthetic caller emails under `@graph-service.example.com`, with regression coverage for the token-auth path
  - graph-specific AI runtime construction now delegates through `services/artana_evidence_db/composition.py`, and graph-specific Artana-backed search/connection execution no longer needs platform-side runtime wiring
  - hypothesis generation is now assembled locally inside `services/artana_evidence_db/composition.py` and no longer resolves through the legacy platform dependency container
  - service-owned maintenance endpoints for backfill, readiness audit/repair, and reasoning-path rebuild
  - service-owned operation history now persists in `graph_operation_runs` and is queryable under `/v1/admin/operations/runs`
  - platform graph runtime now requires explicit `GRAPH_SERVICE_URL` outside local/test environments, and the web graph API resolver now requires `INTERNAL_GRAPH_API_URL` or `NEXT_PUBLIC_GRAPH_API_URL` outside local development
  - deploy/runtime sync scripts now fail fast when graph URLs, graph secrets, or the configured graph migration job are missing
  - the active graph docs now publish the standalone `/v1/...` contract plus a complete graph-service inventory under `docs/graph/reference/service-inventory.md`
  - `/admin/dictionary/...` compatibility routes now forward over the typed graph-service client instead of building kernel dictionary services in-process
  - the shared route-support helpers under `src/routes/research_spaces/_kernel_*_dependencies.py` now delegate to the legacy dependency container instead of importing graph services and repositories directly
  - `analysis_service_factories.py` now consumes kernel observation and relation repositories through factory methods instead of importing those repositories directly
  - `service_factories.py` now consumes kernel graph repositories through kernel factory builder methods instead of importing those repositories directly, and it no longer requires a graph-boundary allowlist exception
  - claim-projection and reasoning/hypothesis factory mixins now consume repository builders through `KernelCoreServiceFactoryMixin`, shrinking the remaining DI/common graph-boundary surface
  - `ingestion_pipeline_factory.py` now constructs graph ingestion dependencies through the legacy container builder path instead of importing kernel services and repositories directly, and it no longer requires a graph-boundary allowlist exception
  - claim-projection and reasoning/hypothesis DI mixins now delegate kernel service construction through a graph-service bridge module under `services/artana_evidence_db/`, and those two files no longer require graph-boundary allowlist exceptions
  - `_kernel_core_service_factories.py` is now a thin delegator into the graph-service bridge module under `services/artana_evidence_db/` and no longer requires a graph-boundary allowlist exception
  - `_pipeline_run_trace_run_id_loader.py` now resolves relation-evidence run ids through a graph-service observability helper under `services/artana_evidence_db/` and no longer requires a graph-boundary allowlist exception
  - `_artana_observability_pipeline_resolution.py` now resolves relation-evidence run ids through the graph-service observability helper under `services/artana_evidence_db/` and no longer requires a graph-boundary allowlist exception
  - initial graph-service integration tests

## Remaining extraction gaps

The in-repo migration is code-complete. The remaining gap is operational only:
the deployed shared-instance topology validator still needs to pass during the
next real production promotion.

## Migration phase progress

This table shows actual in-flight progress, not just whether a phase is fully
finished.

| Phase | Status | Checklist progress | Completed so far | Remaining to finish the phase |
| --- | --- | --- | --- | --- |
| 0. Contract freeze and inventory | Completed | 5/5 | API namespace, target boundary, ownership map, graph invariants, graph-owned dictionary subset, and a full active graph-service inventory are documented. | None. |
| 1. Service skeleton | Completed | 5/5 | Standalone FastAPI app, entrypoint, local config/auth/session wiring, local run target, service integration tests, service-local lint/typecheck/CI entrypoints, and OpenAPI/client-generation automation all exist and are wired into the graph-service workflow. | None. |
| 2. Data ownership decoupling | Completed | 8/8 | Graph-owned tables are decoupled from `users`, `source_documents`, and platform `research_spaces`; tenant access/settings/registry now flow through graph-local ports; graph-owned tenant metadata lives in `graph_spaces` plus `graph_space_memberships`; platform space/member writes reconcile into the graph control plane; admin graph-space sync now persists graph-owned sync metadata/fingerprints and is idempotent for unchanged tenant snapshots; graph claim/evidence/projection/cache rows now carry graph-owned `source_document_ref` fields; graph-owned control-plane, governance, and remaining kernel tables all support a dedicated `GRAPH_DB_SCHEMA` with schema-aware Alembic/runtime/RLS wiring; and the authoritative Postgres-backed graph suite plus graph performance suite pass with `GRAPH_DB_SCHEMA=graph_runtime`. | None. |
| 3. Deterministic graph core extraction | Completed | 4/4 | Standalone routes cover entities, observations, provenance, claims, claim-relations, canonical relations, graph export/document, subgraph/neighborhood, reasoning paths, graph views, and admin graph-space registry/membership APIs; graph-document builder/support moved under `services/artana_evidence_db/`; and the platform app no longer owns graph route compatibility surfaces. | None. |
| 4. Dictionary and concept extraction | Completed | 4/4 | Standalone admin APIs exist for dictionary governance and space-scoped concepts, the service builds that wiring locally, service-local governance adapters/builders own graph-service dictionary/concept composition for materialization, rebuild, search, graph-connection, and hypothesis paths, and governance persistence now runs through service-local repository implementations under `services/artana_evidence_db/`. | None. |
| 5. Client cutover | Completed | 11/11 | Typed Python and TypeScript graph clients are in place; operational scripts, lifecycle sync, pipeline orchestration, worker flows, and remaining platform callers use HTTP or graph control-plane APIs; shared schema/helpers/runtime code now lives in neutral `src/...` modules; and non-graph code no longer imports `services.artana_evidence_db.*`. | None. |
| 6. Graph intelligence extraction | Completed | 6/6 | Graph search, graph connection, relation suggestion, and hypothesis execution routes exist inside the standalone service, graph-specific Artana/runtime wiring is confined to the graph boundary, and hypothesis generation is assembled from service-local composition without calling the platform dependency container. | None. |
| 7. Operational workflow extraction | Completed | 6/6 | Readiness audit/repair, projection rebuild, participant backfill, and reasoning-path rebuild now exist as standalone service APIs; legacy scripts execute through that API; graph-space reconciliation has its own operational command path; and operation history is now persisted and queryable under `/v1/admin/operations/runs`. | None. |
| 8. Deployment and topology hardening | In progress | 11/12 | Standalone runtime requires `GRAPH_DATABASE_URL`, has graph-local `GRAPH_DB_*` settings, ships service-local module and DB-manage entrypoints, has dedicated graph DB commands, a dedicated container, a dedicated deploy workflow/runtime sync, fails fast when required graph URLs or secrets are missing, enforces distinct graph DB secret names in deployed environments, documents the supported shared-instance topology and dedicated-database playbook, writes topology-validation results into workflow summaries, has a green `make graph-service-checks` gate, and now uses service-local Alembic config/assets under `services/artana_evidence_db/`. | Run the shared-instance topology validator through the next real production promotion. |
| 9. Legacy removal | Completed | 8/8 | Boundary enforcement is active with an empty legacy allowlist, the platform research-spaces router no longer registers graph routes, compatibility-only route/admin proxy layers have been removed, platform imports of `services.artana_evidence_db.*` are gone, shared graph-runtime modules now live under neutral `src/...` paths, and the shared graph-service contract no longer depends on route-layer schema modules. | None. |

## Objectives

1. Turn the graph from a Python import boundary into a network boundary.
2. Make the graph service the sole owner of graph writes and graph repair jobs.
3. Preserve explainability, projection invariants, and research-space isolation.
4. Allow this platform and future systems to consume the graph over a stable API.

## Non-goals

- Building a graph-specific UI.
- Keeping long-lived direct database access from non-graph services.
- Keeping long-lived direct imports of graph repositories or graph services from
  non-graph code.
- Preserving current route paths exactly if cleaner versioned service routes are
  better for long-term independence.

## Target service boundary

The standalone graph service will own:

- entities
- entity identifiers
- entity embeddings used by graph retrieval
- observations
- relation claims
- claim participants
- claim evidence
- claim relations
- canonical relations
- relation projection lineage
- derived relation evidence
- reasoning paths and reasoning path steps
- graph views
- graph documents
- graph search
- graph connection execution
- hypotheses and hypothesis generation
- provenance records required by graph workflows
- concepts and graph-local concept resolution support
- graph-governing dictionary validation data and APIs
- graph readiness, rebuild, repair, and backfill operations

The platform app or other services will keep:

- source discovery
- generic ingestion scheduling
- content enrichment outside graph ownership
- membership and organization management as a business capability
- non-graph admin and dashboard workflows
- UI concerns

## Current extraction seam

The current codebase already exposes the main extraction seam:

- Application services: `src/application/services/kernel/`
- Repositories: `src/infrastructure/repositories/kernel/`
- Routes: `src/routes/research_spaces/`

The graph is not yet independent because it still relies on:

- shared FastAPI app bootstrapping in `src/main.py`
- shared route registration in `src/routes/research_spaces/router.py`
- shared dependency injection in `src/infrastructure/dependency_injection/`
- shared database session and RLS assumptions in `src/database/session.py`
- in-process callers such as `src/routes/research_spaces/pipeline_orchestration_routes.py`
- model-level coupling to external bounded contexts such as `research_spaces`,
  `users`, and `source_documents`

## Future API shape

The new service will expose a versioned API under:

```text
/v1/spaces/{space_id}/...
```

Representative resources:

- `/v1/spaces/{space_id}/entities`
- `/v1/spaces/{space_id}/observations`
- `/v1/spaces/{space_id}/claims`
- `/v1/spaces/{space_id}/claim-participants`
- `/v1/spaces/{space_id}/claim-evidence`
- `/v1/spaces/{space_id}/claim-relations`
- `/v1/spaces/{space_id}/relations`
- `/v1/spaces/{space_id}/graph/subgraph`
- `/v1/spaces/{space_id}/graph/neighborhood/{entity_id}`
- `/v1/spaces/{space_id}/graph/views/...`
- `/v1/spaces/{space_id}/graph/documents/...`
- `/v1/spaces/{space_id}/reasoning-paths`
- `/v1/spaces/{space_id}/hypotheses`
- `/v1/spaces/{space_id}/graph/search`
- `/v1/spaces/{space_id}/graph/connections/...`
- `/v1/spaces/{space_id}/concepts/...`
- `/v1/admin/readiness/...`
- `/v1/admin/rebuild/...`
- `/v1/admin/backfill/...`
- `/v1/dictionary/...`

## Space and multitenancy model

Spaces remain the first-class tenant boundary.

Required properties:

- every graph record is partitioned by `space_id`
- no write in one space can affect another space
- tokens and service credentials are space-aware
- service-level authorization is enforced before any write or read operation
- database-level isolation may still use RLS when Postgres is the backing store

The graph service should own a local tenant registry for spaces rather than
depending on cross-schema foreign keys to the platform's `research_spaces`
table. The service may receive space lifecycle updates from the platform, but it
must not depend on platform database ownership to function.

## Dictionary and concept ownership

The graph service will own the dictionary data needed to validate and operate
the graph. This includes, at minimum:

- entity types used by graph entities
- relation types used by claims and canonical relations
- variable definitions required by observations
- graph relation constraints
- entity resolution policies required by graph operations
- concept sets and concept membership data used by graph-local resolution

The graph service must expose API operations for managing or synchronizing this
validation data. It must not require a separate dictionary service call during
core claim materialization or canonical relation rebuilds.

## Data ownership model

### Service-owned data

The graph service is the sole writer for all graph-owned tables.

No other service may:

- connect directly to graph tables
- import graph repositories for persistence
- mutate graph data outside the graph API

### Cross-context references

Current model-level dependencies on external tables must be removed or replaced
with opaque identifiers before the final extraction.

Examples:

- `research_space_id` foreign keys become graph-owned tenant references
- `triaged_by` and similar user references become actor IDs without FK coupling
- `source_document_id` becomes an external document reference rather than a DB FK

### Database topology

The service must support both modes without API changes:

1. Shared Postgres instance, graph-owned schema
2. Dedicated Postgres instance, graph-owned database

Initial recommendation:

- start with one Postgres instance to control cost
- create a graph-owned schema and graph-owned DB user
- keep graph migrations and operational ownership exclusive to the graph service
- preserve a single `GRAPH_DATABASE_URL` contract so a dedicated database can be
  adopted later without changing service code or clients

## Auth and authorization model

The graph service must authenticate and authorize requests itself.

Required model:

- bearer JWT for end-user initiated requests
- service-to-service token for internal platform callers
- claims include actor identity, allowed space context, and a graph-service-local admin claim for control-plane operations
- graph service verifies access to the requested `space_id`
- graph service sets DB session context for RLS when using Postgres

The current shared app dependency pattern in the platform app should not remain
the graph service boundary.

## Service packaging

The service should live as an independent Python package/app inside the monorepo
first, for example:

```text
services/artana-evidence-db/
```

Suggested internal structure:

```text
services/artana-evidence-db/
├── src/graph_service/
│   ├── main.py
│   ├── routes/
│   ├── application/
│   ├── domain/
│   ├── infrastructure/
│   ├── database/
│   └── clients/
├── alembic/
├── tests/
└── pyproject.toml
```

The graph service may temporarily reuse code from the current repo during the
transition, but the end state should be clear ownership by the service package,
not continued dependence on platform-internal modules.

## Module migration map

### Move into the graph service

- `src/application/services/kernel/`
- `src/infrastructure/repositories/kernel/`
- graph-relevant ORM models under `src/models/database/kernel/`
- graph route modules in `src/routes/research_spaces/`:
  - `kernel_entities_routes.py`
  - `kernel_observations_routes.py`
  - `kernel_relations_routes.py`
  - `claim_graph_routes.py`
  - `kernel_graph_view_routes.py`
  - `kernel_graph_document_routes.py`
  - `kernel_reasoning_path_routes.py`
  - `hypothesis_routes.py`
  - `kernel_graph_search_routes.py`
  - `graph_connection_routes.py`
  - `concept_routes.py`
- graph-specific support and dependency modules:
  - `_kernel_*`
  - `_claim_graph_route_support.py`
  - `_claim_evidence_paper_links.py`

### Replace with API clients

- graph calls made from orchestration code such as
  `src/routes/research_spaces/pipeline_orchestration_routes.py`
- any future platform workflow that creates claims, rebuilds projections, reads
  graph documents, or triggers reasoning/hypothesis generation

### Keep outside the graph service

- non-graph route modules
- data-source lifecycle
- discovery pipelines
- dashboard and UI code
- membership and organization business logic
- platform-level auth issuance

## No-proxy rule

The current platform app must not become a permanent forwarding layer for the
graph service.

Allowed:

- short-lived transition adapters during cutover

Not allowed:

- permanent pass-through routes that hide the independent graph service
- permanent duplicate graph write paths
- permanent dual ownership of graph persistence

## Migration phases

### Phase 0: Contract freeze and inventory

- [x] Freeze the target public API shape under `/v1/spaces/{space_id}/...`
- [x] Inventory every current graph route, service, repository, model, script,
  and caller
- [x] Classify each module as `move`, `replace with client`, or `stay outside`
- [x] Freeze the graph invariants in `docs/graph/reference/architecture.md` as the
  non-negotiable service contract
- [x] Define the graph-owned dictionary subset required for independent
  operation

### Phase 1: Service skeleton

- [x] Create `services/artana-evidence-db/` with its own FastAPI entrypoint
- [x] Add service-local dependency wiring, config, health checks, and startup
  lifecycle
- [x] Add service-local testing and local run entrypoints
- [x] Add service-local linting, type-checking, and CI entrypoints
- [x] Add service-local OpenAPI generation and client generation pipeline

### Phase 2: Data ownership decoupling

- [x] Introduce graph-owned schema and graph-owned migrations
- [x] Remove or replace cross-context foreign keys to platform-owned tables
- [x] Add graph-local space registry and authorization-ready tenant metadata
- [x] Replace standalone graph-service authz direct membership/research-space repository usage with a graph-local space access port
- [x] Replace standalone graph-service graph-connection settings hydration from the platform `ResearchSpaceRepository` with a graph-local space settings port
- [x] Introduce a graph-local space registry adapter and route graph-owned runtime metadata reads through it
- [x] Add actor/document external reference fields where DB FKs are removed
- [x] Validate that graph hard guarantees still hold after decoupling

### Phase 3: Deterministic graph core extraction

- [x] Move entities, observations, claims, participants, evidence, relations,
  projection lineage, readiness, graph views, and reasoning paths into the
  graph service runtime
- [x] Expose a first standalone slice of deterministic graph read and write APIs
- [x] Keep a dedicated standalone service integration suite green
- [x] Add architecture tests preventing non-graph code from importing graph
  persistence directly

### Phase 4: Dictionary and concept extraction

- [x] Move graph-governing dictionary validation data under graph-service
  ownership
- [x] Expose admin APIs for graph dictionary and concept management
- [x] Remove graph-service dependence on platform route helper composition for
  dictionary and concept wiring
- [x] Remove runtime dependence on external dictionary DB access for claim
  materialization and graph rebuilds

### Phase 5: Client cutover

- [x] Generate typed Python client for platform backends
- [x] Expose a stable typed TypeScript graph client surface for direct web calls
- [x] Replace at least one non-graph operational caller with API calls
- [x] Route `graph-readiness` and `graph-reasoning-rebuild` through the
  standalone graph-service client
- [x] Replace the first long-lived backend graph caller with API calls
- [x] Narrow the remaining platform integration harness to graph tenant-sync coverage only
- [x] Replace remaining in-process graph service calls in non-graph modules with API calls
- [x] Replace any direct graph repository usage outside the graph service
- [x] Remove new-write capability from legacy in-process graph call sites

### Phase 6: Graph intelligence extraction

- [x] Move graph search execution into the graph service
- [x] Move graph connection execution into the graph service
- [x] Move relation suggestion execution into the graph service
- [x] Move hypothesis generation execution into the graph service
- [x] Ensure all graph AI workflows operate against graph-owned APIs and
  persistence only
- [x] Keep Artana or other AI runtime dependencies confined to the graph service

### Phase 7: Operational workflow extraction

- [x] Move readiness checks into graph-service admin APIs/jobs
- [x] Move projection rebuild/repair workflows into graph-service admin APIs/jobs
- [x] Move participant backfill into graph-service admin APIs/jobs
- [x] Move reasoning-path rebuild into graph-service admin APIs/jobs
- [x] Cut over the operational readiness/rebuild scripts to those service APIs
- [x] Add service-local observability for rebuilds, staleness, and repair actions

### Phase 8: Deployment and topology hardening

- [x] Require explicit `GRAPH_DATABASE_URL` for standalone runtime
- [x] Expose a service-local `python -m services.artana_evidence_db` entrypoint
- [x] Move graph DB wait/migrate operations into `python -m services.artana_evidence_db.manage`
- [x] Add dedicated `make graph-db-wait` / `make graph-db-migrate` commands
- [x] Deploy the graph service independently from the platform app
- [x] Point platform callers to the graph service over internal HTTP
- [x] Require explicit graph-service URL wiring outside local development
- [x] Enforce graph-only DB credentials for graph-owned schema
- [x] Keep `make graph-service-checks` green as the authoritative standalone service gate
- [ ] Run deployed shared-instance topology validation cleanly in production
- [x] Reduce repo-global packaging/migration coupling so graph-service runtime depends only on neutral shared `src/...` modules and service-local Alembic assets
- [x] Prepare dedicated-database migration playbook for future separation

### Phase 9: Legacy removal

- [x] Remove permanent graph route ownership from the platform app
- [x] Remove direct imports of graph services from non-graph packages
- [x] Remove direct imports of graph repositories from non-graph packages
- [x] Remove obsolete compatibility layers and pass-through code
- [x] Mark the graph service as the only supported graph integration surface

## Testing and release gates

The graph service migration is not complete until the graph invariant suite
passes against the new service boundary.

Required gates:

- graph invariant tests
- graph read-model consistency tests
- research-space isolation tests
- dictionary hard-guarantee tests
- readiness/rebuild operational tests
- graph-specific performance tests

The current graph matrix in `tests/graph/README.md` should be carried into the
service and used as the authoritative checklist.

## Definition of done

The migration is complete when all of the following are true:

- other services use the graph only through the graph API client
- graph-owned tables are mutated only by the graph service
- graph-governing dictionary validation data is owned by the graph service
- spaces remain the tenant boundary and are enforced by the graph service
- graph search, graph connection, and hypotheses execute inside the graph service
- graph readiness and rebuild workflows are owned by the graph service
- the platform app no longer exposes permanent graph write/read routes as its
  primary graph implementation
- the graph service can run against either a shared Postgres instance or a
  dedicated Postgres instance without API changes

## Progress log

Use this section to record milestone completion over time.

Important: the checkboxes below indicate full phase completion only. They stay
unchecked until the entire phase is done, which is why they looked empty even
though substantial partial progress already exists.

### Phase completion snapshot

| Phase | Current state | What that means right now |
| --- | --- | --- |
| Phase 0 | Complete | The public contract, ownership model, and active graph-service inventory are now fully documented. |
| Phase 1 | Complete | The standalone service has its own runtime, quality gates, contract generation, and CI workflow coverage. |
| Phase 2 | Complete | Graph-owned tenant, governance, and kernel data boundaries are decoupled from platform tables and validated under a dedicated schema-aware Postgres gate. |
| Phase 3 | Complete | Deterministic graph APIs and runtime ownership are fully served by the standalone graph service, with no platform graph route compatibility layer left. |
| Phase 4 | Complete | Governance APIs, governance composition, and governance persistence are now all owned under `services/artana_evidence_db/` for the standalone service runtime. |
| Phase 5 | Complete | Platform callers now use HTTP clients or graph control-plane APIs, and shared graph runtime/schema/query code lives in neutral `src/...` modules instead of `services.artana_evidence_db.*`. |
| Phase 6 | Complete | Graph AI execution is service-local, including hypothesis generation, which is now assembled from `services/artana_evidence_db/composition.py` instead of the legacy platform DI container. |
| Phase 7 | Complete | Core admin/rebuild workflows are service-owned and now persist/query their own operation history through `/v1/admin/operations/runs`. |
| Phase 8 | Partial | Runtime/deploy foundation is in place, the standalone service gate is green, and migration entrypoints now live under `services/artana_evidence_db/`; the only remaining step is the first real deployed topology-validation run. |
| Phase 9 | Complete | Legacy route ownership is gone, the allowlist is empty, platform imports of `services.artana_evidence_db.*` are gone, and the shared graph contract no longer depends on route-layer schema modules. |

### Final phase-complete checkboxes

- [x] Phase 0 complete
- [x] Phase 1 complete
- [x] Phase 2 complete
- [x] Phase 3 complete
- [x] Phase 4 complete
- [x] Phase 5 complete
- [x] Phase 6 complete
- [x] Phase 7 complete
- [ ] Phase 8 complete
- [x] Phase 9 complete

### Recent updates

- 2026-03-13: Phase 0 completed: active graph-service ownership is now documented in `docs/graph/reference/service-inventory.md`, covering service-owned runtime modules, platform callers, scripts, CI/deploy entrypoints, authoritative tests, and the current `/v1/...` public contract.
- 2026-03-13: Phase 1 completed: service-local lint/typecheck/contract/test targets now exist under `make graph-service-*`, `scripts/export_graph_openapi.py` publishes `services/artana_evidence_db/openapi.json`, generated TS contract types now live in `src/web/types/artana-evidence-db.generated.ts`, and `artana-evidence-db-deploy.yml` runs those quality gates in CI.
- 2026-03-13: Phase 2 completed: the remaining graph kernel tables now move into the configured `GRAPH_DB_SCHEMA` via `010_graph_kernel_schema`, the dedicated-schema Postgres graph gate is green, and graph-owned schema/migration support now covers control-plane, governance, and kernel tables end to end.
- 2026-03-13: Phases 5, 6, and 9 completed in-repo: platform imports of `services.artana_evidence_db.*` were eliminated by moving shared runtime helpers into neutral `src/...` modules, hypothesis generation was rebuilt from service-local composition, and shared graph API schemas moved into `src/type_definitions/graph_api_schemas/`.
- 2026-03-13: Phase 8 advanced again: `make graph-service-checks` and `scripts/validate_graph_service_boundary.py` are both green, the remaining service-local gate issue in `services/artana_evidence_db/database.py` was fixed, graph-service Alembic config/assets live under `services/artana_evidence_db/alembic.ini` and `services/artana_evidence_db/alembic/`, and repo/test migration entrypoints execute through that service-local config. The only remaining Phase 8 item is the first successful real deployed shared-instance topology-validation run.
- 2026-03-13: Phase 6 advanced substantially earlier in the day: graph-specific search/connection runtime construction now delegated through `services/artana_evidence_db/composition.py`; hypothesis generation was completed later the same day and Phase 6 is now fully complete.
- 2026-03-13: Phase 9 advanced substantially earlier in the day: active graph docs now published only the standalone `/v1/...` graph-service contract; the remaining service-package imports from platform code were removed later the same day and Phase 9 is now fully complete.
- 2026-03-12: Phase 2 advanced again: graph-owned control-plane tables (`graph_spaces`, `graph_space_memberships`, `graph_operation_runs`) now support a dedicated `GRAPH_DB_SCHEMA`, graph-service Postgres connections set a schema-aware search path, Alembic baseline/incremental migrations and RLS policy references now honor that schema, and both the Postgres-backed `graph and not performance` and graph performance suites passed after the new schema-support migration landed.
- 2026-03-13: Phase 2 advanced again: graph governance tables are now schema-aware under `GRAPH_DB_SCHEMA`, the shared Postgres test bootstrap provisions graph schema/extension prerequisites before metadata bootstrap, graph-service integration seeds no longer depend on platform `users` / `research_spaces` except where the source-document reference port explicitly requires them, and the dedicated-schema Postgres graph gates now pass with `GRAPH_DB_SCHEMA=graph_runtime` (`79 passed, 6 skipped` for `graph and not performance`; `3 passed` for graph performance).
- 2026-03-12: Phase 2 advanced again: graph-space control-plane sync now persists graph-owned sync metadata on `graph_spaces` (`sync_source`, `sync_fingerprint`, `source_updated_at`, `last_synced_at`), `/v1/admin/spaces/{space_id}/sync` is now idempotent for unchanged tenant snapshots, the typed graph client and platform graph-space sync helper now pass deterministic sync fingerprints, and the authoritative Postgres-backed `graph and not performance` suite passed again after the new migration and router/repository changes.
- 2026-03-12: Phase 2 advanced again: `relation_claims`, `claim_evidence`, `claim_relations`, `relation_projection_sources`, and `relation_evidence` now persist graph-owned `source_document_ref` values alongside any legacy `source_document_id`, materialization/backfill now carries those refs end to end, graph-service claim/relation/document read models expose them, and the authoritative Postgres-backed `graph and not performance` plus graph performance suites both passed after the migration.
- 2026-03-12: Phase 4 advanced: graph-service dictionary/concept composition is now owned by `services/artana_evidence_db/governance.py`, and materialization, rebuild, graph search, graph connection, and hypothesis paths now consume those service-local governance adapters instead of constructing governance services directly from shared repository imports inside the standalone service.
- 2026-03-12: Phase 4 completed: dictionary and concept persistence moved fully under `services/artana_evidence_db/` via service-local governance repository implementations in `services/artana_evidence_db/dictionary_repository.py` and `services/artana_evidence_db/concept_repository.py`, with focused unit coverage in `tests/unit/services/artana_evidence_db/test_governance.py` and a clean rerun of the authoritative Postgres graph suite.
- 2026-03-12: Phase 7 advanced to completion: graph maintenance workflows now persist operation history in `graph_operation_runs`, readiness repair / participant backfill / reasoning-path rebuild responses now return `operation_run_id`, and new admin observability endpoints under `/v1/admin/operations/runs` provide list/detail reads for those runs.
- 2026-03-12: Phase 5 cleanup continued: the platform integration harness in `tests/integration/api/conftest.py` was narrowed again so it only supports graph tenant-sync coverage instead of broader removed graph-route compatibility.
- 2026-03-12: Phase 5 cleanup continued again: the remaining platform integration harness no longer boots an in-process graph service at all, and now uses a minimal recording graph-sync client stub for tenant control-plane flows only.
- 2026-03-12: Phase 5 cleanup continued again: the shared `tests/integration/api/conftest.py` graph-sync harness was removed entirely, and the minimal recording tenant-sync stub now lives only in `tests/integration/api/test_research_spaces_api.py`, so the rest of the platform API suite no longer carries graph-specific harness code by default.
- 2026-03-12: Phase 5 advanced substantially: the existing typed web helper layer is now formalized behind `src/web/lib/api/graph-client.ts`, with direct coverage proving the supported TS graph-client entrypoint re-exports kernel, concept, dictionary, and graph base-url helpers from one stable module.
- 2026-03-12: Phase 8 hardening continued: platform and script-side graph runtime resolution now requires explicit `GRAPH_SERVICE_URL` outside local/test environments, the web graph URL resolver now requires `INTERNAL_GRAPH_API_URL` or `NEXT_PUBLIC_GRAPH_API_URL` outside local development, and deploy/runtime sync now fails fast when graph URLs, graph secrets, or the configured graph migration job are missing.
- 2026-03-12: Phase 8 hardening continued again: graph-service deploy/runtime sync now fails fast if `GRAPH_DATABASE_URL_SECRET_NAME` matches the platform `DATABASE_URL_SECRET_NAME`, and the graph-service deploy workflow now passes the platform DB secret name into that validation so deployed environments cannot silently reuse the platform DB secret contract.
- 2026-03-12: The standalone-service release gate passed end to end: `scripts/validate_graph_service_boundary.py`, the graph-service/unit client layers, the Postgres-backed `graph and not performance` suite, and `tests/performance/test_graph_query_performance.py -m "graph and performance"` all passed after fixing the test bootstrap so `GRAPH_DATABASE_URL` follows the isolated Postgres test database and seeding the required `general` dictionary domain context explicitly in the concept-governance graph-service fixture.
- 2026-03-12: Phase 8 hardening continued: active graph docs now include `docs/graph/reference/deployment-topology.md`, which documents the supported shared-instance production topology, the required graph-service runtime/env contract, and the forward-only dedicated-database migration playbook.
- 2026-03-12: Phase 8 hardening continued again: deploy-time shared-instance topology validation now exists in `scripts/deploy/validate_shared_instance_graph_topology.py`, both deploy workflows run it after runtime sync, and focused unit coverage now exercises success and URL-mismatch failure paths with a fake `gcloud` binary.
- 2026-03-12: Phase 7 tenant-control-plane reconciliation landed via `scripts/sync_graph_spaces.py` and `make graph-space-sync`, giving the platform an explicit graph-space repair path in addition to per-write sync.
- 2026-03-12: Phase 9 boundary enforcement landed via `scripts/validate_graph_service_boundary.py`, and `validate-architecture` now fails on new direct graph-internal imports outside the standalone service and the temporary legacy allowlist.
- 2026-03-12: Phase 9 legacy burn-down started at the file level: `kernel_provenance_routes.py` and `kernel_reasoning_path_routes.py` now use the graph-service client over HTTP and no longer require allowlist exceptions.
- 2026-03-12: Phase 9 legacy burn-down continued: `kernel_graph_view_routes.py` now uses the graph-service client over HTTP and no longer requires an allowlist exception.
- 2026-03-12: Phase 9 legacy burn-down continued: `kernel_entities_routes.py` now uses the graph-service client over HTTP and no longer requires an allowlist exception.
- 2026-03-12: Phase 9 legacy burn-down continued: `kernel_observations_routes.py` now uses the graph-service client over HTTP and no longer requires an allowlist exception.
- 2026-03-12: Phase 9 legacy burn-down continued: `graph_connection_routes.py` now uses the graph-service client over HTTP for batch discovery, single-entity discovery, and relation suggestions, and no longer requires an allowlist exception.
- 2026-03-12: Phase 9 legacy burn-down continued: `hypothesis_routes.py` now uses the graph-service client over HTTP for list, manual create, and generate flows, and no longer requires an allowlist exception.
- 2026-03-12: Phase 9 legacy burn-down continued: `kernel_graph_search_routes.py` now uses the graph-service client over HTTP, and platform graph-search tests run through the extracted boundary when the Artana-backed search dependency is available.
- 2026-03-12: Phase 9 legacy burn-down continued: `kernel_graph_document_routes.py` now uses the graph-service client over HTTP, and the graph-document builder/support implementation moved under `services/artana_evidence_db/` so the temporary boundary allowlist no longer needs the old platform helper modules.
- 2026-03-12: Phase 9 legacy burn-down continued inside `kernel_relations_routes.py`: graph export, bounded subgraph, and neighborhood reads now forward over the graph-service client instead of building those read models in-process.
- 2026-03-12: Phase 9 legacy burn-down continued: `claim_graph_routes.py` now forwards claims-by-entity, claim participants, participant backfill/coverage, and claim-relation list/create/update flows over the graph-service client instead of calling kernel services directly.
- 2026-03-12: Phase 9 legacy burn-down continued inside `kernel_relations_routes.py`: relation list/create/update plus relation-claim list/evidence/conflicts/triage now forward over the graph-service client instead of executing graph logic in the platform app.
- 2026-03-12: Phase 9 legacy burn-down continued below the route layer: graph-only relation evidence and subgraph helpers moved from `src/routes/research_spaces/` into `services/artana_evidence_db/`, `kernel_graph_view_schemas.py` and `kernel_reasoning_path_schemas.py` no longer import kernel service modules, and those four files were removed from the temporary boundary allowlist.
- 2026-03-12: Phase 9 legacy burn-down continued in the admin layer: `/admin/concepts` now forwards to the standalone graph service over the typed client, the old kernel-backed `concept_route_common.py` helper was removed, and that allowlist entry is gone.
- 2026-03-12: Phase 5 and Phase 9 advanced again in the admin layer: the standalone graph service now exposes full dictionary-admin parity for revoke, merge, changelog, reembed, domain search, and transform registry operations; `/admin/dictionary/...` now forwards over the typed graph-service client; `dictionary_route_common.py` no longer imports kernel services; and that final admin dictionary allowlist entry has been removed.
- 2026-03-12: Phase 9 legacy burn-down continued in the shared route-support layer: `_kernel_claim_projection_dependencies.py`, `_kernel_dictionary_entity_dependencies.py`, `_kernel_graph_operation_dependencies.py`, and `_kernel_reasoning_hypothesis_dependencies.py` now delegate to the legacy dependency container instead of importing graph services or repositories directly, and those four allowlist entries were removed from `scripts/validate_graph_service_boundary.py`.
- 2026-03-12: Phase 9 legacy burn-down continued in the DI/common layer: `analysis_service_factories.py` now builds export/search services from kernel-core factory methods instead of importing kernel observation and relation repositories directly, and that allowlist entry has been removed.
- 2026-03-12: Phase 9 legacy burn-down continued in the DI/common layer: `service_factories.py` now consumes graph relation/claim/query repositories through kernel factory builder methods instead of importing kernel repositories directly, and that allowlist entry has been removed.
- 2026-03-12: Phase 9 legacy burn-down continued in the DI/common layer: claim-projection and reasoning/hypothesis factory mixins now reuse repository builders from `KernelCoreServiceFactoryMixin`, so the remaining allowlisted DI files are narrower and `service_factories.py` is the last shared top-level factory removed from the graph-boundary exception list.
- 2026-03-12: Phase 9 legacy burn-down continued in the ingestion layer: `ingestion_pipeline_factory.py` now builds dictionary, observation, entity, and provenance dependencies through the legacy container builder path instead of importing kernel services and repositories directly, and that allowlist entry has been removed.
- 2026-03-12: Phase 9 legacy burn-down continued in the DI/core layer: `_kernel_claim_projection_service_factories.py` and `_kernel_reasoning_hypothesis_service_factories.py` now delegate kernel service construction through `services/artana_evidence_db/legacy_dependency_factories.py`, and both allowlist entries have been removed.
- 2026-03-12: Phase 9 legacy burn-down completed for the shared DI/core layer: `_kernel_core_service_factories.py` now delegates into `services/artana_evidence_db/legacy_dependency_factories.py`, its allowlist entry has been removed, and the boundary allowlist is down to the remaining non-DI application-service files plus `phi_backfill.py`.
- 2026-03-12: Phase 9 legacy burn-down continued in the non-DI application-service layer: `_pipeline_run_trace_run_id_loader.py` now resolves relation-evidence run ids through `services/artana_evidence_db/legacy_observability_queries.py`, its allowlist entry has been removed, and the boundary allowlist is down to three application-service files plus `phi_backfill.py`.
- 2026-03-12: Phase 9 legacy burn-down continued in the non-DI application-service layer: `_artana_observability_pipeline_resolution.py` now resolves relation-evidence run ids through `services/artana_evidence_db/legacy_observability_queries.py`, its allowlist entry has been removed, and the boundary allowlist is down to two application-service files plus `phi_backfill.py`.
- 2026-03-12: Phase 9 boundary cleanup completed for the remaining non-DI files: `_artana_observability_queries.py` and `_source_workflow_monitor_relations.py` now route their graph-table reads through `services/artana_evidence_db/legacy_observability_queries.py`, `phi_backfill.py` now loads PHI identifier batches through `services/artana_evidence_db/legacy_security_queries.py`, focused unit coverage was added for those seams, and `scripts/validate_graph_service_boundary.py` now passes with an empty `LEGACY_ALLOWLIST`.
- 2026-03-12: Phase 9 route-removal cleanup started in the platform app: the shared research-spaces router no longer registers the legacy graph document, graph search, graph view, provenance, or reasoning-path route modules; those route modules and their platform-only route tests were deleted; the temporary platform integration harness was narrowed accordingly; and the remaining mixed platform integration file still passes for the surviving relation/entity surfaces.
- 2026-03-12: Phase 9 route-removal cleanup completed for the remaining platform graph route modules: `claim_graph_routes.py`, `concept_routes.py`, `graph_connection_routes.py`, `hypothesis_routes.py`, `kernel_entities_routes.py`, `kernel_observations_routes.py`, and `kernel_relations_routes.py` were deleted, the research-spaces router now registers no graph routes, the mixed platform graph integration tests were replaced by a smaller non-graph platform suite plus the standalone `tests/integration/graph_service/test_artana_evidence_db.py`, and architecture validation now passes with the graph client depending on `src/type_definitions/graph_service_contracts.py` instead of route-layer schema modules.
- 2026-03-12: Phase 5 and Phase 9 advanced again for governance/admin access: platform admin access tokens now carry the `graph_admin` claim for real admin sessions, the Next.js dictionary client now calls `/v1/dictionary/...` on the standalone graph service directly, and the obsolete platform admin graph-governance route modules (`/admin/dictionary/...` and `/admin/concepts/...`) plus their platform-only tests were deleted.
- 2026-03-12: Platform API integration tests now run extracted legacy graph pass-through routes against an in-process graph-service harness that mirrors platform tenant state into graph-owned tenant tables.
- 2026-03-12: Standalone graph-service JWT auth now derives synthetic caller emails under `@graph-service.example.com`, with a direct regression test covering token-backed caller resolution.

### Current milestone notes

- Phases 0, 1, 2, 3, 4, 5, 6, 7, and 9 are complete in-repo: the standalone graph service owns the graph API/runtime, graph data boundaries are decoupled from platform tables, non-graph platform code no longer imports the service package directly, graph intelligence is composed locally inside the service, and the operational graph control plane persists/query its own run history.
- Phase 8 is the only remaining open phase.
- The current standalone-service release gate is green: `scripts/validate_graph_service_boundary.py` and `make graph-service-checks` both pass, including the isolated Postgres graph-service suite.
- Packaging and migration ownership are closed for the current monorepo extraction target: the service runs with service-local Alembic config/assets, and the remaining shared `src/...` modules are neutral shared runtime code rather than platform route/DI ownership leaks.
- The only remaining migration item is the first successful real deployed shared-instance topology-validation run.
