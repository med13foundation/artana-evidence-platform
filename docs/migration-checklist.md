# Migration Checklist

This checklist is the operational tracker for the extraction work.

Legend:

- `[ ]` not started
- `[x]` completed
- `[-]` intentionally deferred

## Current Snapshot

- Date anchored: April 23, 2026
- Repo status: source-of-truth cutover completed; temporary top-level `src/` removal completed
- Code imported: yes
- Active milestone: M7 optional runtime restoration
- Important status note: M5 means the service ownership cutover is complete; it
  did not mean the temporary `src/` package had been physically removed from
  this repository. M6 is the post-cutover cleanup milestone that removed it.

## M0: Repo Scaffold

- [x] Create the new GitHub repository
- [x] Add a root README that explains the extraction target
- [x] Add a detailed migration plan
- [x] Add a progress checklist
- [x] Decide whether to work directly on `main` or use a migration branch

## M1: Bootable Baseline Import

- [x] Import `services/artana_evidence_db`
- [x] Import `services/artana_evidence_api`
- [x] Import `src/` as temporary shared runtime code
- [x] Import service-relevant `scripts/`
- [x] Import service-relevant `docs/`
- [x] Import `tests/e2e/artana_evidence_api/`
- [x] Import `pytest.ini`
- [x] Import `.dockerignore`
- [x] Add a slim root `Makefile` focused on extracted services only
- [x] Verify both services import in the new repo
- [x] Verify both Dockerfiles still build in the new repo

## M1 Gates

- [x] Run graph OpenAPI export check
- [x] Run evidence API OpenAPI export check
- [x] Run graph lint/type/test gate
- [x] Run evidence API lint/type/test gate
- [x] Confirm the new repo can boot both services locally

## M2: Graph Service Final Standalone Pass

- [x] Inventory remaining production `src` imports in `services/artana_evidence_db`
- [x] Replace the shared unified search dependency with graph-owned code
- [x] Remove `src/` from graph-service runtime packaging
- [x] Re-run graph boundary validation
- [x] Re-run graph OpenAPI export check
- [x] Re-run graph test gate
- [x] Confirm graph-service Docker image no longer copies `src/`

## M2 Commands

- [x] `rg "from src\\.|import src\\." services/artana_evidence_db -g '!**/tests/**'`
- [x] `python scripts/validate_graph_service_boundary.py`
- [x] `python scripts/export_graph_openapi.py --output services/artana_evidence_db/openapi.json --check`

## M3: Evidence API Dependency Unwind

### E1 Research Space and Membership

- [x] Inventory remaining platform-style research-space and membership imports
- [x] Replace or localize membership role/model dependencies
- [x] Replace or localize research-space repository dependencies
- [x] Re-run evidence API type-check

### E2 Agent Contracts and Fact Assessment

- [x] Inventory agent contract imports from `src`
- [x] Decide what becomes service-local versus repo-shared
- [x] Move fact-assessment helpers behind repo-owned modules
  Graph connection, chat graph-write, research bootstrap, and variant-aware extraction now use service-local fact-assessment and extraction contracts; the remaining shared extraction runtime is only reachable through the service-owned lazy bridge in `services/artana_evidence_api/variant_extraction_bridges.py`.
- [x] Re-run extraction and graph-connection tests

### E3 Research Init and Source Enrichment

- [x] Inventory research-init imports from `src`
- [x] Move or localize source-document repository usage
- [x] Move or localize alias-yield reporting helpers
- [x] Move or localize source gateway dependencies needed by the service
  Research-init now goes through service-owned source-enrichment bridge builders in `services/artana_evidence_api/source_enrichment_bridges.py`, and MARRVEL uses the local discovery service. As of M6, the source-enrichment bridge no longer lazy-loads shared `src` gateways; non-MARRVEL structured-source gateways now fail closed until service-local gateway implementations are added.
- [x] Re-run research-init tests

### E4 Orchestrator Helpers

- [x] Inventory orchestrator-only helper imports from `src`
- [x] Move or localize remaining helper dependencies
- [x] Re-run orchestrator tests

## M3 Commands

- [x] `rg "from src\\.|import src\\." services/artana_evidence_api -g '!**/tests/**'`
- [x] `python scripts/validate_artana_evidence_api_service_boundary.py`
- [x] `python scripts/export_artana_evidence_api_openapi.py --output services/artana_evidence_api/openapi.json --check`

## M4: SDK, Docs, CI, and Deploy Alignment

- [x] Decide whether `packages/artana_api` moves in phase 1 or phase 2
- [x] If moving SDK: import `packages/artana_api`
- [-] If deferring SDK: remove or rewrite extracted doc references to it
- [x] Add CI workflow for graph-service checks
- [x] Add CI workflow for evidence API service checks
- [x] Add deployment workflow for graph service
- [x] Add deployment workflow for evidence API
- [x] Document environment variables for both services
- [x] Add staging smoke-test notes or scripts

## M5: Cutover

- [x] Announce short freeze for extracted services in the monorepo
- [x] Replay final upstream changes into this repo as a no-op audit
- [x] Regenerate both OpenAPI artifacts
- [x] Run all extracted service gates
- [x] Deploy staging from this repo
- [x] Verify graph service smoke flows
- [x] Verify evidence API smoke flows
- [x] Mark this repo as source of truth
- [x] Deprecate or remove old monorepo copies

## M6: Remove Temporary `src/` Package

- [x] Make the checklist distinguish completed cutover from incomplete `src/` removal
- [x] Inventory remaining `src` references by runtime, packaging, scripts, tests, and workflows
- [x] Confirm production service modules no longer have direct `src` imports
- [x] Remove graph-service check and deploy path dependencies on `src`
- [x] Remove graph-service Makefile check paths that still execute monorepo support tests
- [x] Remove or replace evidence API lazy bridge dependencies on `src`
- [x] Remove source-enrichment bridge dependencies on `src`
- [x] Remove source-document bridge dependencies on `src`
- [x] Remove ontology-runtime bridge dependencies on `src`
- [x] Remove variant-extraction bridge dependencies on `src`
- [x] Remove `COPY src ./src` from the evidence API Dockerfile
- [x] Remove or archive monorepo-era scripts that still import `src`
- [x] Move remaining reusable test fixtures away from `tests/conftest.py` `src` imports
- [x] Remove `src` from packaging, lint, type, and coverage config
- [x] Delete the physical `src/` directory
- [x] Re-run both extracted service gates without `src/`

## M7: Restore Optional Runtime Features

- [x] Restore service-local Variant LLM extraction runtime
- [ ] Restore non-MARRVEL structured-source gateways
- [x] Restore service-local ClinVar structured-source gateway
- [ ] Restore service-local DrugBank structured-source gateway
- [ ] Restore service-local AlphaFold structured-source gateway
- [ ] Restore service-local UniProt structured-source gateway
- [ ] Restore service-local ClinicalTrials.gov structured-source gateway
- [ ] Restore service-local MGI structured-source gateway
- [ ] Restore service-local ZFIN structured-source gateway
- [ ] Restore MONDO ingestion as a service-local runtime
- [ ] Restore shared entity-recognition runtime as a service-local runtime

## Decisions to Close

- [x] Keep `src/` name temporarily or rename after M1
- [x] Separate databases immediately or use temporary shared Postgres topology
- [x] Include Python SDK now or later
- [x] Decide whether first code import lands on `main` or a migration branch

## Progress Notes

Use this section as the running log while executing the migration.

### Notes

- April 22, 2026: repo scaffold created with plan and checklist
- April 22, 2026: bootable baseline import landed with `services/`, temporary `src/`, root tooling, selected tests, scripts, and docs
- April 22, 2026: verified `make graph-service-checks` and `make artana-evidence-api-service-checks` from this repo
- April 22, 2026: verified both services boot locally from this repo after adjusting `setup-postgres` to reuse an already reachable `DATABASE_URL`
- April 22, 2026: verified both runtime Docker images build from this repo
- April 22, 2026: graph-service standalone unwind completed by localizing unified search and embedding-provider runtime dependencies, removing `COPY src ./src`, and making boundary validation part of graph-service checks
- April 22, 2026: evidence API E1 completed by introducing service-local graph space sync payloads/protocols in `services/artana_evidence_api/space_sync_types.py` and removing the remaining research-space and membership sync imports from shared `src`
- April 22, 2026: evidence API E2 partially completed by moving graph-connection, chat graph-write, research-bootstrap, and graph agent-contract fact assessments onto `services/artana_evidence_api/types/graph_fact_assessment.py`; variant-aware extraction still depends on shared extraction contracts and remains pending
- April 22, 2026: evidence API E3 alias-yield reporting helper moved local to `services/artana_evidence_api/alias_yield_reporting.py`, with focused research-init tests and the evidence API boundary check passing afterward
- April 22, 2026: localized the shadow-planner OpenAI pricing helper into `services/artana_evidence_api/llm_costs.py`, localized graph schema resolution for the observation bridge into `services/artana_evidence_api/graph_db_schema.py`, and verified the relevant planner and research-init tests before re-running the full evidence API service checks
- April 22, 2026: localized variant-aware extraction JSON and fact-assessment helper logic into `services/artana_evidence_api/shared_fact_assessment_helpers.py`, reducing that bridge to the remaining shared extraction/runtime contracts only, and re-ran the focused variant extraction and worker tests before re-running the full evidence API service checks
- April 22, 2026: localized research-init structured-source entrypoints onto `services/artana_evidence_api/source_enrichment_bridges.py`, switched MARRVEL enrichment onto the service-local discovery runtime, removed the remaining direct `src` imports from `research_init_source_enrichment.py`, and re-ran focused source-enrichment tests plus the full evidence API service checks
- April 22, 2026: localized the observation-bridge source-document/runtime seam onto `services/artana_evidence_api/source_document_bridges.py`, removed the direct `src` imports from `research_init_runtime.py` for source documents and shared DI, rewired the observation-bridge tests to the service-owned bridge factories, and re-ran the focused observation-bridge tests plus the full evidence API service checks
- April 22, 2026: localized the deferred MONDO/ontology runtime seam onto `services/artana_evidence_api/ontology_runtime_bridges.py`, removed the remaining direct `src` imports from `research_init_runtime.py`, and re-ran focused deferred-source tests plus the full evidence API service checks
- April 22, 2026: localized the remaining variant-aware extraction seam onto `services/artana_evidence_api/variant_extraction_contracts.py` and `services/artana_evidence_api/variant_extraction_bridges.py`, removed the last direct production `src` imports from `variant_aware_document_extraction.py` and `shared_fact_assessment_helpers.py`, re-ran focused variant extraction/router tests, and re-ran the full evidence API service checks
- April 22, 2026: added GitHub Actions workflows in `.github/workflows/graph-service-checks.yml` and `.github/workflows/evidence-api-service-checks.yml`, each backed by a pgvector Postgres service and the repo’s existing `make ...-checks` targets, and locally validated the workflow YAML syntax
- April 22, 2026: added deploy-only GitHub Actions workflows in `.github/workflows/artana-evidence-db-deploy.yml` and `.github/workflows/artana-evidence-api-deploy.yml`, porting the extracted repo’s Cloud Run promotion flow onto the existing `scripts/deploy/*cloud_run_runtime_config.sh` runtime-sync scripts and validating all workflow YAML locally
- April 22, 2026: added `docs/deployment/extracted-services-runbook.md`, documenting the code-backed runtime env contract for both services plus the GitHub Actions deploy-variable contract and a minimal staging smoke checklist, and linked it from the repo README
- April 22, 2026: completed the M5 upstream replay audit as a no-op sync; the extracted repo was not missing any files from the imported monorepo scope, and the remaining clean diffs were confirmed as intentional extraction-owned changes in graph boundary validation, graph search wiring, Docker packaging, and generated OpenAPI shape
- April 23, 2026: regenerated both OpenAPI artifacts, re-ran `make graph-service-checks` and `make artana-evidence-api-service-checks` locally, then verified the same gates again through the extracted repo GitHub Actions runs `24809280090` and `24809280080`
- April 23, 2026: configured the extracted repo's GitHub Actions deploy settings and extended the existing GitHub workload-identity provider plus deployer service-account IAM bindings so `med13foundation/artana-evidence-platform` can deploy directly
- April 23, 2026: deployed staging from this repo through GitHub Actions runs `24809418596` and `24809418691`, promoting commit `93079378e32f4474f43cf66cb5f68d515162c6ef` to `artana-evidence-db-staging` and `artana-evidence-api-staging`
- April 23, 2026: completed staging smoke verification: graph `/health` and `/openapi.json` returned 200, evidence `/health` and `/openapi.json` returned 200, evidence runtime config now points `GRAPH_API_URL` at the staging graph service rather than localhost, and bootstrap auth smoke returned HTTP 409 `Bootstrap has already been completed for this deployment`
- April 23, 2026: marked this repository as the source of truth and added freeze/deprecation notices to the monorepo service READMEs and docs READMEs
- April 23, 2026: opened M6 for post-cutover removal of the temporary `src/` package, confirmed service production modules have no direct `src` imports, and started the cleanup by removing graph-service Makefile check paths plus graph-service check/deploy workflow path dependencies on `src`
- April 23, 2026: verified the first M6 graph-service cleanup slice with `make graph-service-checks`; the slimmer graph gate passes without lint/type/test path dependencies on monorepo `src`
- April 23, 2026: removed the source-enrichment bridge's lazy `src` imports, rewired the source-enrichment unit tests to patch service-owned builder seams, and verified `services/artana_evidence_api/tests/unit/test_research_init_source_enrichment.py` plus `scripts/validate_artana_evidence_api_service_boundary.py`; non-MARRVEL optional source gateways now fail closed until service-local implementations are added
- April 23, 2026: localized the observation-bridge source-document model and SQLAlchemy repository into `services/artana_evidence_api/source_document_bridges.py`, removed that bridge's lazy `src` imports, and verified the focused observation-bridge unit tests, `services/artana_evidence_api/tests/integration/test_observation_bridge_persistence.py`, `scripts/validate_artana_evidence_api_service_boundary.py`, and `make artana-evidence-api-type-check`; the old shared entity-recognition runtime now fails closed until it is ported service-local
- April 23, 2026: removed the ontology-runtime bridge's lazy `src` imports, rewired MONDO tests to patch `research_init_runtime.build_mondo_ingestion_service`, and verified the deferred/guarded MONDO tests, the research-init e2e pipeline test, `scripts/validate_artana_evidence_api_service_boundary.py`, and `make artana-evidence-api-type-check`; MONDO ingestion now fails closed until it is ported service-local
- April 23, 2026: localized deterministic variant signal parsing into `services/artana_evidence_api/variant_extraction_bridges.py`, removed that bridge's lazy extraction-runtime `src` imports, and verified the variant-aware extraction tests plus `make artana-evidence-api-service-checks`; the LLM extraction adapter now returns a fallback contract until it is ported service-local, and production `services/artana_evidence_api` has no remaining `src` references
- April 23, 2026: completed M6 by removing `COPY src ./src` from the evidence API Dockerfile, deleting/archiving monorepo-era scripts and tests that depended on top-level `src`, narrowing packaging/lint/type/coverage configuration to service packages plus the SDK, replacing reusable test-fixture imports with service-local models, deleting the physical top-level `src/` directory, and re-running `make graph-service-checks` plus `make artana-evidence-api-service-checks` successfully without that directory
- April 23, 2026: started M7 optional runtime restoration by wiring `services/artana_evidence_api/variant_extraction_bridges.py` to the service-local Artana single-step runtime for Variant LLM extraction, using the evidence-extraction model registry capability, deterministic run/step keys, schema validation through `ExtractionContract`, and fail-closed fallback when the key/runtime/schema is unavailable; verified focused variant-aware extraction tests and `make artana-evidence-api-service-checks`
- April 23, 2026: restored the service-local ClinVar structured-source gateway in `services/artana_evidence_api/clinvar_gateway.py`, backed by NCBI ESearch/ESummary through the evidence API's own `httpx` runtime, normalizing records into the existing research-init document/proposal fields without reintroducing the deleted top-level `src` package

### Known Facts to Preserve During Migration

- `artana_evidence_db` is the standalone governed graph service
- `artana_evidence_api` is the AI evidence/orchestration service
- the graph service no longer has production `src` imports and no longer copies `src/` into its runtime image
- the evidence API no longer has production `src` imports or lazy `src` bridge references, and no longer copies `src/` into its runtime image
- the top-level temporary `src/` package has been deleted from this repository
- remaining `src` references are package-local SDK paths such as `packages/artana_api/src`, boundary-validator forbidden-prefix strings, or historical docs; they are not the removed monorepo runtime package
- Variant LLM extraction has been restored service-local; without a usable `OPENAI_API_KEY`, it still intentionally falls back to deterministic variant signals
- ClinVar structured-source enrichment has been restored service-local; the remaining non-MARRVEL structured gateways are DrugBank, AlphaFold, UniProt, ClinicalTrials.gov, MGI, and ZFIN
- the M5 upstream replay audit found no missing imported-scope monorepo files to port into this repo before staging cutover
- keep the temporary shared Postgres topology for now; database separation is deferred beyond the completed source-of-truth cutover
- M6 is complete: both extracted service gates pass with no physical top-level `src/` directory
