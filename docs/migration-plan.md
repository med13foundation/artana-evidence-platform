# Migration Plan

> Historical note: this plan records the extraction strategy from the early
> cutover. For the current checkout shape, use [README.md](../README.md) and
> [migration-checklist.md](./migration-checklist.md); the temporary `src/`
> package and `packages/artana_api` SDK are no longer present here.

## Summary

This document tracks the extraction of the Artana evidence services from the
monorepo into `artana-evidence-platform`.

Status update as of April 22, 2026:

- M0 repo scaffold is complete
- M1 bootable baseline import is complete
- M2 graph-service standalone unwind is complete
- the repo now owns the copied service code, temporary shared runtime, and
  service-local validation commands
- next focus is M3 evidence API shared-runtime unwind

The migration should be treated as a two-stage program:

1. land a bootable extracted repo with minimal path churn
2. unwind remaining shared-runtime dependencies until the services are truly
   standalone

The key reason for this sequencing is that the two services are not equally
detached today:

- `artana_evidence_db` is close to standalone, but still has a small remaining
  production dependency on monorepo `src` code
- `artana_evidence_api` still has a meaningful set of runtime imports from
  monorepo `src` modules, especially in research-init, extraction, and
  membership/research-space paths

## Snapshot

This plan is based on the monorepo state inspected on April 22, 2026.

Working assumptions from that inspection:

- the graph service already has service-local packaging, migrations, runtime
  config, and release gates
- the graph service still copies `src/` in its Docker image and still has one
  live production `src` import in its search router
- the evidence API still copies both `services/artana_evidence_db` and `src/`
  into its runtime image
- the evidence API still has live production imports from `src` in:
  - research-init runtime and enrichment paths
  - extraction and fact-assessment paths
  - research-space membership and lifecycle paths
  - some orchestrator helper paths

This means a direct copy of only the two service folders would not be enough.

## Goals

- create a dedicated repository for the extracted evidence services
- preserve a working local developer loop from the first import
- preserve existing contract checks and boundary checks where they still apply
- keep the graph service deterministic and free of AI runtime concerns
- keep the evidence API talking to the graph service over HTTP as the long-term
  architectural boundary
- make progress visible with milestone-based acceptance gates

## Non-Goals

- extracting `services/research_inbox`
- extracting `services/research_inbox_runtime`
- redesigning product scope during the migration
- renaming packages and paths before the repo is bootable
- building compatibility shims unless an active consumer forces them

## Recommended Target Layout

The first successful extraction should preserve existing paths as much as
possible:

```text
artana-evidence-platform/
├── README.md
├── Makefile
├── pytest.ini
├── .dockerignore
├── docs/
├── scripts/
├── src/                           temporary shared runtime package
├── services/
│   ├── artana_evidence_db/
│   └── artana_evidence_api/
├── tests/
│   └── e2e/
│       └── artana_evidence_api/
└── packages/
    └── artana_api/                optional in phase 1 or phase 2
```

The initial repo should not try to improve naming yet. Preserving path stability
is more valuable than cleanup during the first cut.

## Migration Principles

### 1. Favor a bootable import over a perfect import

If a choice trades off cleanliness versus a fast green baseline, prefer the
green baseline first.

### 2. Preserve current service paths on day one

Do not rename `services/` or `src/` during the initial import.

### 3. Treat `src/` as explicitly owned temporary shared runtime

`src/` is not accidental baggage. It is real runtime dependency surface. The
new repo should own it intentionally until dependency unwind is complete.

### 4. Extract the graph service fully before finishing the evidence API unwind

The graph service is the lower-risk win and provides the cleanest early success
signal.

### 5. Keep the HTTP boundary between services as the target architecture

The long-term target remains:

```text
client or worker
  -> artana_evidence_api
  -> typed HTTP boundary
  -> artana_evidence_db
```

## Workstreams

## Workstream A: Repo Bootstrap

Objective: create a new repo that can host the extracted services without
breaking imports immediately.

Deliverables:

- root README
- migration tracker docs
- root Makefile with service-focused commands only
- root pytest and docker ignore files needed by service packaging/tests
- initial CI workflow skeleton

Success criteria:

- contributors can clone the repo and understand scope immediately
- repo layout matches the first extraction target

## Workstream B: Baseline Code Import

Objective: import the minimum code required to boot both services.

Recommended first import:

- `services/artana_evidence_db`
- `services/artana_evidence_api`
- `src/`
- `scripts/` required by service gates
- `docs/` required by packaging/tests
- `tests/e2e/artana_evidence_api/`
- `pytest.ini`
- `.dockerignore`

Optional in the same milestone:

- `packages/artana_api`

Success criteria:

- both services import and build in the new repo
- no path rewrites are needed just to get the repo running

## Workstream C: Quality Gates and Boundary Checks

Objective: preserve the service-local release gates that make extraction safe.

Required preserved checks:

- graph service boundary validation
- evidence API service-boundary validation
- graph OpenAPI export check
- evidence API OpenAPI export check
- graph service lint, type-check, and tests
- evidence API lint, type-check, and tests

Recommended commands to preserve or recreate:

```bash
python scripts/validate_graph_service_boundary.py
python scripts/validate_artana_evidence_api_service_boundary.py
python scripts/export_graph_openapi.py --output services/artana_evidence_db/openapi.json --check
python scripts/export_artana_evidence_api_openapi.py --output services/artana_evidence_api/openapi.json --check
```

Success criteria:

- the extracted repo has its own green service gates
- CI in the new repo is authoritative for extracted services

## Workstream D: Graph Service Final Standalone Pass

Objective: finish the graph service extraction so it no longer has production
`src` dependencies.

Known remaining production dependency from the April 22, 2026 inspection:

- search router imports shared search and dependency-injection code from `src`

Tasks:

- move unified search implementation into `services/artana_evidence_db`
  directly, or into a tiny repo-local shared package owned by this repo
- remove `COPY src ./src` from the graph service Dockerfile once no longer
  needed
- rerun graph service gates

Success criteria:

- `rg "from src\\.|import src\\." services/artana_evidence_db -g '!**/tests/**'`
  returns no production hits
- graph Docker image no longer depends on `src/`
- graph service checks remain green

## Workstream E: Evidence API Shared-Runtime Unwind

Objective: make the evidence API explicit about what it owns locally versus what
still lives in the temporary shared runtime package.

The unwind should happen by dependency bucket, not by random file edits.

### Bucket E1: Research Space and Membership Glue

Expected areas:

- dependencies
- graph transport typing/helpers
- SQLAlchemy stores that still rely on platform mapping
- space lifecycle sync

Goal:

- replace platform-specific research-space and membership imports with
  repo-owned service contracts or service-local models

### Bucket E2: Agent Contracts and Fact Assessment Helpers

Expected areas:

- agent contracts
- graph connection runtime
- research bootstrap runtime
- chat graph write workflow
- variant-aware extraction

Goal:

- either move the needed contracts into the evidence API package or define a
  clearly owned shared package in this repo

### Bucket E3: Research Init and Source Enrichment

Expected areas:

- research init runtime
- research init brief assembly
- research init source enrichment

Goal:

- make research-init dependencies first-class citizens of this new repo rather
  than hidden imports from the old monorepo

### Bucket E4: Orchestrator Helper Dependencies

Expected areas:

- full AI orchestrator helper imports that still point into monorepo `src`

Goal:

- localize orchestrator-only helper code or split it into a clearly named shared
  package inside this repo

Success criteria:

- every remaining evidence API `src` import is intentional, documented, and
  owned by this repo
- the final target is zero production imports from a generic monorepo `src`

## Workstream F: SDK and Contract Assets

Objective: decide whether the public Python SDK should move now or later.

Status update:

- `packages/artana_api` was imported with the baseline cut so existing
  references and service-adjacent assets continue to resolve in this repo

Reasons to move `packages/artana_api` early:

- service docs already refer to it
- examples and tests may be useful during rollout
- the evidence API relies on the graph service frozen OpenAPI contract

Reasons to defer:

- smaller initial extraction
- less release surface on day one

Recommendation:

- keep the imported SDK for now so service docs and adjacent assets remain
  coherent during the extraction
- revisit whether it stays in this repo as part of M4 release and CI alignment

Success criteria:

- no broken doc references
- no tests depend on missing SDK assets

## Workstream G: Deployment and Runtime Topology

Objective: rebuild standalone deployment in the new repo without carrying
monorepo assumptions forward.

Graph service runtime contract to preserve:

- `GRAPH_DATABASE_URL`
- `GRAPH_JWT_SECRET`
- optional `GRAPH_DB_SCHEMA`
- graph-local DB pool settings

Evidence API runtime contract to preserve:

- `GRAPH_API_URL`
- `DATABASE_URL` or `ARTANA_STATE_URI`
- `OPENAI_API_KEY` or `ARTANA_OPENAI_API_KEY`
- graph JWT settings
- scheduler and worker settings

Recommendation:

- use separate deployment workflows for the two services
- prefer separate databases or, at minimum, separate credentials and schemas
- validate service-to-service auth only through the HTTP boundary

Success criteria:

- staging deploy works from the new repo
- evidence API calls graph service over HTTP only

## Workstream H: Cutover

Objective: make this repo the source of truth for the extracted services.

Recommended cutover process:

1. announce a short freeze window for these services in the monorepo
2. replay any last upstream changes
3. regenerate OpenAPI artifacts
4. run all service gates
5. deploy staging
6. verify smoke flows
7. switch active development to this repo
8. deprecate or remove old monorepo copies

Success criteria:

- new feature work lands here
- monorepo no longer acts as the primary home for these services

## Milestones

| Milestone | Outcome | Status |
| --- | --- | --- |
| M0 | Repo scaffold and tracking docs exist | Complete |
| M1 | Bootable baseline import with temporary `src/` | Complete |
| M2 | Graph service fully standalone | Complete |
| M3 | Evidence API green with owned shared-runtime boundaries | Not started |
| M4 | SDK, docs, CI, and deploy topology aligned | Not started |
| M5 | Cutover complete and monorepo copy deprecated | Not started |

## Acceptance Gates

### Gate for M1

- both services import in the new repo
- local run commands work
- OpenAPI export scripts run
- service test commands run

### Gate for M2

- graph production code has no `src` imports
- graph Dockerfile no longer copies `src`
- graph boundary checks stay green

### Gate for M3

- evidence API dependency inventory is complete
- remaining shared code is intentionally owned by this repo
- no accidental platform-only imports remain

### Gate for M4

- docs reflect actual repo layout
- CI runs from this repo
- deployment config is owned by this repo
- optional SDK decision is closed

### Gate for M5

- this repo is the source of truth
- old monorepo locations are retired or explicitly deprecated

## Risks and Mitigations

### Risk: Trying to over-clean in the first import

Mitigation:

- preserve current paths for the first bootable baseline

### Risk: Graph service looks extracted but still depends on shared code

Mitigation:

- explicitly finish graph service standalone work before calling extraction done

### Risk: Evidence API unwind becomes a diffuse refactor

Mitigation:

- work by dependency bucket with milestone gates

### Risk: Docs and tests drift from actual repo layout

Mitigation:

- treat doc path fixes and contract exports as part of the migration, not a
  later cleanup

### Risk: Hidden runtime dependencies remain in scripts and CI

Mitigation:

- recreate only the service-relevant scripts and run them inside the new repo

## Open Decisions

- include `packages/artana_api` in phase 1 or defer to phase 2
- keep `src/` name long-term or rename after stabilization
- separate databases immediately or keep a shared Postgres topology temporarily
- do cutover directly to `main` or use a dedicated migration branch until M1

## Rough Effort

- M0-M1: 1-2 focused days
- M2: 2-4 days
- M3: 1-2 weeks depending on how much shared research-init and extraction code
  should move versus remain shared
- M4-M5: 2-4 days depending on deploy and cutover friction

These are rough engineering estimates, not commitments.
