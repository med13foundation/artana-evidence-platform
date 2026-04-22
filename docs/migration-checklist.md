# Migration Checklist

This checklist is the operational tracker for the extraction work.

Legend:

- `[ ]` not started
- `[x]` completed
- `[-]` intentionally deferred

## Current Snapshot

- Date anchored: April 22, 2026
- Repo status: planning scaffold created
- Code imported: no
- Active milestone: M0

## M0: Repo Scaffold

- [x] Create the new GitHub repository
- [x] Add a root README that explains the extraction target
- [x] Add a detailed migration plan
- [x] Add a progress checklist
- [ ] Decide whether to work directly on `main` or use a migration branch

## M1: Bootable Baseline Import

- [ ] Import `services/artana_evidence_db`
- [ ] Import `services/artana_evidence_api`
- [ ] Import `src/` as temporary shared runtime code
- [ ] Import service-relevant `scripts/`
- [ ] Import service-relevant `docs/`
- [ ] Import `tests/e2e/artana_evidence_api/`
- [ ] Import `pytest.ini`
- [ ] Import `.dockerignore`
- [ ] Add a slim root `Makefile` focused on extracted services only
- [ ] Verify both services import in the new repo
- [ ] Verify both Dockerfiles still build in the new repo

## M1 Gates

- [ ] Run graph OpenAPI export check
- [ ] Run evidence API OpenAPI export check
- [ ] Run graph lint/type/test gate
- [ ] Run evidence API lint/type/test gate
- [ ] Confirm the new repo can boot both services locally

## M2: Graph Service Final Standalone Pass

- [ ] Inventory remaining production `src` imports in `services/artana_evidence_db`
- [ ] Replace the shared unified search dependency with graph-owned code
- [ ] Remove `src/` from graph-service runtime packaging
- [ ] Re-run graph boundary validation
- [ ] Re-run graph OpenAPI export check
- [ ] Re-run graph test gate
- [ ] Confirm graph-service Docker image no longer copies `src/`

## M2 Commands

- [ ] `rg "from src\\.|import src\\." services/artana_evidence_db -g '!**/tests/**'`
- [ ] `python scripts/validate_graph_service_boundary.py`
- [ ] `python scripts/export_graph_openapi.py --output services/artana_evidence_db/openapi.json --check`

## M3: Evidence API Dependency Unwind

### E1 Research Space and Membership

- [ ] Inventory remaining platform-style research-space and membership imports
- [ ] Replace or localize membership role/model dependencies
- [ ] Replace or localize research-space repository dependencies
- [ ] Re-run evidence API type-check

### E2 Agent Contracts and Fact Assessment

- [ ] Inventory agent contract imports from `src`
- [ ] Decide what becomes service-local versus repo-shared
- [ ] Move fact-assessment helpers behind repo-owned modules
- [ ] Re-run extraction and graph-connection tests

### E3 Research Init and Source Enrichment

- [ ] Inventory research-init imports from `src`
- [ ] Move or localize source-document repository usage
- [ ] Move or localize alias-yield reporting helpers
- [ ] Move or localize source gateway dependencies needed by the service
- [ ] Re-run research-init tests

### E4 Orchestrator Helpers

- [ ] Inventory orchestrator-only helper imports from `src`
- [ ] Move or localize remaining helper dependencies
- [ ] Re-run orchestrator tests

## M3 Commands

- [ ] `rg "from src\\.|import src\\." services/artana_evidence_api -g '!**/tests/**'`
- [ ] `python scripts/validate_artana_evidence_api_service_boundary.py`
- [ ] `python scripts/export_artana_evidence_api_openapi.py --output services/artana_evidence_api/openapi.json --check`

## M4: SDK, Docs, CI, and Deploy Alignment

- [ ] Decide whether `packages/artana_api` moves in phase 1 or phase 2
- [ ] If moving SDK: import `packages/artana_api`
- [ ] If deferring SDK: remove or rewrite extracted doc references to it
- [ ] Add CI workflow for graph-service checks
- [ ] Add CI workflow for evidence API service checks
- [ ] Add deployment workflow for graph service
- [ ] Add deployment workflow for evidence API
- [ ] Document environment variables for both services
- [ ] Add staging smoke-test notes or scripts

## M5: Cutover

- [ ] Announce short freeze for extracted services in the monorepo
- [ ] Replay final upstream changes into this repo
- [ ] Regenerate both OpenAPI artifacts
- [ ] Run all extracted service gates
- [ ] Deploy staging from this repo
- [ ] Verify graph service smoke flows
- [ ] Verify evidence API smoke flows
- [ ] Mark this repo as source of truth
- [ ] Deprecate or remove old monorepo copies

## Decisions to Close

- [ ] Keep `src/` name temporarily or rename after M1
- [ ] Separate databases immediately or use temporary shared Postgres topology
- [ ] Include Python SDK now or later
- [ ] Decide whether first code import lands on `main` or a migration branch

## Progress Notes

Use this section as the running log while executing the migration.

### Notes

- April 22, 2026: repo scaffold created with plan and checklist

### Known Facts to Preserve During Migration

- `artana_evidence_db` is the standalone governed graph service
- `artana_evidence_api` is the AI evidence/orchestration service
- the graph service is closer to full extraction than the evidence API
- the evidence API still depends on temporary shared runtime code from `src`
