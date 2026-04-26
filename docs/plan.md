# Engineering Plan

Status date: April 25, 2026.

This plan describes the target direction for the current extracted backend
repo. It intentionally excludes the old monorepo UI, old top-level `src`
runtime package, and deleted SDK package.

## Detailed Goal

Artana Evidence Platform should turn messy biomedical evidence into a trusted,
reviewable evidence graph.

The public product should be easy to explain:

```text
research space
  -> source discovery
  -> evidence capture
  -> extraction
  -> proposed updates
  -> review
  -> trusted evidence graph
  -> search, chat, monitoring, and repeated discovery
```

The key rule is that discovery and AI extraction may propose knowledge, but
normal researcher workflows must not silently mutate trusted graph state.
Proposed claims, entities, observations, and relations should move through the
review/governance boundary before they become trusted graph knowledge.

## Product Shape

The platform is an evidence-first research backend:

```text
space
  -> sources
  -> evidence/documents
  -> extraction
  -> review
  -> graph
  -> search/chat/discovery
```

Research plans and direct source searches are two entry points into the same
source capability model:

```text
direct source search
  -> captured evidence
  -> extraction/proposals
  -> review
  -> graph

research plan
  -> selected sources
  -> captured evidence
  -> extraction/proposals
  -> review
  -> graph
```

PubMed and MARRVEL are not special public concepts. They are two entries in a
source registry that also describes ClinVar, DrugBank, AlphaFold, UniProt, HGNC,
ClinicalTrials.gov, MGI, ZFIN, MONDO, uploaded text, and uploaded PDF evidence.

## Architecture Principles

- Keep the repo as two backend services: Evidence API and graph service.
- Keep graph internals behind the graph service HTTP/API contract.
- Keep identity low-friction during testing, but route it through
  `IdentityGateway`.
- Treat OpenAPI and generated graph TypeScript contracts as release artifacts.
- Prefer service-local modules over resurrecting the removed top-level `src`
  package.
- Keep direct graph writes for advanced/system workflows; normal researcher
  flows should pass through proposals and review.
- Make v2 the product-shaped public API and keep v1 as compatibility-only while
  the cutover finishes.
- Represent sources through shared capabilities instead of one-off route
  decisions.

## Current Target Topology

```text
client
  -> services/artana_evidence_api
       identity gateway
       source registry and source adapters
       documents and evidence capture
       extraction and proposed updates
       proposals and review queue
       AI/workflow runtimes
       graph HTTP client
  -> services/artana_evidence_db
       dictionary
       claims and relations
       provenance and observations
       graph views and workflows
       graph validation and governance
```

## Public API Direction

The v2 public surface should make the product model visible:

```text
GET  /v2/sources
GET  /v2/sources/{source_key}

POST /v2/spaces
POST /v2/spaces/{space_id}/research-plan

POST /v2/spaces/{space_id}/sources/{source_key}/searches
GET  /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}

POST /v2/spaces/{space_id}/documents/text
POST /v2/spaces/{space_id}/documents/pdf
POST /v2/spaces/{space_id}/documents/{document_id}/extraction

GET  /v2/spaces/{space_id}/review-items
POST /v2/spaces/{space_id}/review-items/{item_id}/decision

GET  /v2/spaces/{space_id}/evidence-map/entities
GET  /v2/spaces/{space_id}/evidence-map/claims
GET  /v2/spaces/{space_id}/evidence-map/claims/{claim_id}/evidence
```

`/v2/sources` tells clients which sources support search, enrichment,
document capture, proposal generation, live external calls, credentials, and
research-plan-only usage. Generic source search routes wrap PubMed, MARRVEL,
ClinVar, ClinicalTrials.gov, UniProt, AlphaFold, DrugBank, MGI, and ZFIN. MONDO,
HGNC, text, and PDF remain non-direct source flows.

## Source Capability Model

Each source should have one registry entry with:

- `source_key`
- display name and description
- supported capabilities: `search`, `ingestion`, `enrichment`,
  `document_capture`, `proposal_generation`, `research_plan`
- credential and live-network requirements
- request schema and result schema summary
- whether direct source-search endpoints are enabled
- whether the source currently runs only through `research-plan`
- how results become source documents, structured evidence, or proposed updates

The source lifecycle should stay consistent even when source internals differ:

```text
discover
  -> capture
  -> extract or normalize
  -> propose
  -> review
  -> promote
```

## Work Plan

### 1. Source Registry And Capabilities

Goal:
Create one canonical source registry used by docs, v2 source endpoints, direct
source searches, and research-plan orchestration.

Completed design:

- Add service-local source capability models in `services/artana_evidence_api`.
- Register PubMed, MARRVEL, ClinVar, DrugBank, AlphaFold, UniProt, HGNC,
  ClinicalTrials.gov, MGI, ZFIN, MONDO, text, and PDF.
- Add `GET /v2/sources` and `GET /v2/sources/{source_key}`.
- Add tests for registry serialization, unknown source errors, and OpenAPI
  coverage.

Exit criteria:

- Clients can discover all supported sources from the API.
- The API clearly distinguishes direct-search sources from
  research-plan-only sources.

### 2. Generic Source Search Surface

Goal:
Make source-specific search feel consistent without breaking existing PubMed and
MARRVEL routes.

Tasks:

- Add `POST /v2/spaces/{space_id}/sources/{source_key}/searches`.
- Add `GET /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}`.
- Route `pubmed` and `marrvel` through the generic source search layer first.
- Keep existing v1 and v2 PubMed/MARRVEL aliases working during the cutover.
- Return clear `501` or capability errors when a source exists but does not yet
  support direct search.

Exit criteria:

- PubMed and MARRVEL work through both old routes and the generic route.
- Unsupported direct searches fail in a product-readable way.

### 3. Shared Evidence Capture Contract

Goal:
Make every source result flow into evidence capture before extraction or
proposal generation.

Tasks:

- Define the source-result to evidence/document conversion contract.
- Normalize source metadata such as locator, source family, external ID,
  citation, retrieval time, and provenance.
- Ensure structured sources can produce reviewable proposals without bypassing
  capture/provenance.
- Keep advanced/system direct-write paths separate from normal researcher
  workflows.

Exit criteria:

- Source results are traceable back to their connector, query, locator, and run.
- Normal researcher workflows do not write trusted graph records directly.

### 4. Research-Plan Integration

Goal:
Make `research-plan` use the same source registry and capability checks as
direct source search.

Tasks:

- Replace hard-coded source availability assumptions with registry lookups.
- Validate requested sources against the registry.
- Record per-source execution summaries using the same source keys and
  capability language exposed by `/v2/sources`.
- Keep PubMed replay/test hooks internal and clearly marked as non-product
  behavior.

Exit criteria:

- `research-plan` and direct source endpoints describe source behavior the same
  way.
- Docs no longer imply every source has a direct endpoint unless the registry
  says it does.

### 5. Additional Direct Source Adapters

Goal:
Add direct source search only where it gives users real control and the adapter
has a stable public shape. This is implemented for ClinVar, ClinicalTrials.gov,
UniProt, AlphaFold, DrugBank, MGI, and ZFIN. MONDO, HGNC, text, and PDF are
intentionally non-direct for now.

Suggested order:

1. ClinVar - direct search implemented.
2. ClinicalTrials.gov - direct search implemented.
3. UniProt - direct search implemented.
4. AlphaFold - direct search implemented.
5. DrugBank - direct search implemented when `DRUGBANK_API_KEY` is configured.
6. MGI - direct search implemented.
7. ZFIN - direct search implemented.
8. MONDO - intentionally kept non-direct because the current code is an
   ontology release loader/grounding step, not a bounded search adapter.

Tasks per source:

- Define request/response models.
- Add adapter tests with deterministic fixtures.
- Add generic route support.
- Add capture/provenance tests.
- Add docs examples only after the endpoint is stable.

Exit criteria:

- Each added direct-search source follows the same discover -> captured source
  result lifecycle, persists the captured search result, and exposes
  `source_capture` provenance.
- Proposal/review still happens through downstream extraction, document capture,
  or `research-plan`; direct search does not silently promote graph knowledge.
- Live external API checks remain opt-in.

### 6. Contracts, Docs, And Cutover

Goal:
Make the new source model safe for external testers.

Tasks:

- Regenerate or check Evidence API OpenAPI artifacts when route/schema changes.
- Update user guide source sections to explain direct search versus
  research-plan orchestration.
- Add migration notes for old PubMed/MARRVEL source paths.
- Keep v1 compatibility until v2 docs, tests, and smoke checks are primary.
- Keep `make artana-evidence-api-service-checks` and `make graph-service-checks`
  green before merging.

Exit criteria:

- Product docs, OpenAPI, and behavior tell the same story.
- External users can understand which source action to call next.

### 7. Direct Source Capture-To-Extraction Handoff

Goal:
Close the remaining production-readiness gap after durable direct search:
selected direct source-search records should be explicitly handed off into
durable extraction or normalization inputs without silently promoting graph
facts.

Current status:

- Structured direct source-search runs are durably persisted in Evidence API
  storage.
- Search responses include source provenance and can be fetched after a fresh
  app/store instance.
- Variant-aware extraction already supports PubMed, text, PDF, ClinVar, and
  MARRVEL document source types.
- The durable bridge now exists for `source_search_runs`-backed structured
  sources through
  `POST /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}/handoffs`.
- PubMed, ClinVar, MARRVEL, ClinicalTrials.gov, UniProt, AlphaFold, DrugBank,
  MGI, and ZFIN handoff creates durable source documents with source-capture
  metadata. Variant-signal ClinVar and MARRVEL records enter the variant-aware
  extraction branch; non-variant records stay as source documents for generic or
  future source-specific extraction instead of stopping at `not_extractable`.
- Handoff-created source documents include source-family metadata, a
  source-specific normalized record profile, readable extraction text, and the
  raw selected record for auditability.
- PubMed and MARRVEL compatibility searches are adapter-wrapped into durable
  `source_search_runs`, so both can use the same handoff endpoint as the other
  structured direct sources.
- The typed v2 PubMed POST and GET keep legacy job-status compatibility for
  incomplete jobs: queued, running, or failed legacy jobs return the legacy job
  payload without creating a durable handoff row; completed jobs are captured in
  `source_search_runs`.
- Handoff persistence now owns an explicit SQLAlchemy unit-of-work boundary.
  The normal path commits the pending handoff, run, document, run status, and
  completed handoff together. If document creation fails, the normal transaction
  rolls back and a deliberate failed run plus failed handoff are persisted in a
  separate failure transaction for safe replay.
- Idempotent replay means the same idempotency key returns the same completed
  or failed handoff outcome. A deliberate retry after a failed handoff should
  use a new idempotency key.

Tasks:

- Add an explicit handoff command or endpoint for durable direct source-search
  results.
- Prefer per-record handoff so a user can extract selected search results
  instead of every record in a response.
- Define the idempotency key, using `space_id`, `source_key`, `search_id`, and
  either a provider `external_id` or stable record hash.
- Add a separate `source_search_handoffs` ledger instead of overloading
  `source_search_runs`; one search run may hand off multiple selected records
  to different downstream targets.
- Store a request hash with each handoff idempotency key. Replays with the same
  key and same request should return the existing handoff; replays with the
  same key and a different request should fail clearly.
- Preserve provider IDs, locators, citations, `source_capture`, original
  payload, and source-search run linkage during handoff.
- Convert selected ClinVar records with variant signals into durable inputs
  for the existing variant-aware extraction path.
- Convert selected MARRVEL records through the same durable
  `source_search_runs` store used by the other structured direct sources.
- Treat MARRVEL as panel-aware: route ClinVar/variant panels through
  variant-aware normalization, and route OMIM, ortholog, expression,
  constraint, and target panels through deterministic or deferred
  source-specific normalization.
- Avoid duplicate ClinVar proposal paths. If ClinVar handoff uses
  variant-aware extraction, deterministic ClinVar bootstrap proposals must be
  deduplicated, demoted, or made lower precedence.
- Keep PubMed, text, and PDF behavior on the existing variant-aware document
  extraction path when variant signals are detected.
- Keep the implementation focused on `source_search_runs`-backed structured
  sources. PubMed and MARRVEL compatibility routes are adapter-wrapped into
  durable `source_search_runs`.
- Define explicit behavior for ClinicalTrials.gov, UniProt, AlphaFold,
  DrugBank, MGI, and ZFIN: create durable source documents that preserve the
  selected record, source-capture metadata, source family, normalized fields,
  and readable extraction text.
- Make research-plan enrichment documents use the variant-aware branch when
  their source type and signals qualify, so direct-source handoff and
  research-plan enrichment do not diverge.
- Harden the durable direct-source store before composing it with handoff
  writes: transaction ownership is now explicit for the handoff path,
  direct-source store writes participate in the shared unit-of-work helper,
  and the in-memory store is kept test-only. Controlled degraded reads are a
  future resilience option, not a blocker for this plan.
- Decide whether `source_search_runs` intentionally has no foreign-key cascade
  because it is an audit/capture ledger.

Exit criteria:

- A selected durable direct source-search record can be handed off
  idempotently into a durable source document or normalized source record.
- Repeated handoff of the same selected record does not create duplicate
  documents, proposals, or review items.
- ClinVar and MARRVEL variant handoff records enter the variant-aware
  extraction document path.
- Variant-aware extraction creates candidates, proposals, or review items only;
  it does not directly promote trusted graph facts.
- Non-variant structured sources have explicit product behavior rather than a
  silent no-op.
- OpenAPI and tests cover the new handoff contract.

Subagent implementation plan:

Use one lead integrator plus focused subagents with disjoint ownership. The
lead keeps API semantics, migrations, OpenAPI, and final verification coherent;
subagents work on bounded slices and do not revert each other's edits.

1. Store/API contract subagent
   - Ownership: `services/artana_evidence_api/direct_source_search.py`,
     `services/artana_evidence_api/models/harness.py`, Evidence API Alembic
     migration files, a new handoff store/helper module, and durable-store unit
     tests.
   - Tasks:
     - Add a `source_search_handoffs` model and migration with fields for
       `id`, `space_id`, `source_key`, `search_id`, `target_kind`,
       `idempotency_key`, `request_hash`, `status`, `created_by`,
       `search_snapshot_payload`, `source_capture_snapshot`, `handoff_payload`,
       target ids, error message, and timestamps.
     - Add a uniqueness constraint on `space_id`, `source_key`, `search_id`,
       `target_kind`, and `idempotency_key`.
     - Define a stable per-record selector and idempotency key.
     - Freeze the selected search response and source-capture snapshot into the
       handoff row so later search-row changes do not alter handoff semantics.
     - Clarify transaction ownership so handoff writes compose safely across
       the handoff ledger, run registry, and document store.
     - Validate `created_by` as a UUID at the service boundary.
     - Mark the in-memory direct-source store as test-only.
   - Output:
     - Durable model/migration patch.
     - Store methods for reading selected records and recording handoff state.
     - Unit tests for idempotency, wrong-space access, payload-version
       handling, and malformed selected-record requests.

2. Public API subagent
   - Ownership: `services/artana_evidence_api/routers/v2_public.py`,
     dependency wiring, OpenAPI artifacts, and route tests.
   - Tasks:
     - Add an explicit handoff endpoint or command, for example
       `POST /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}/handoffs`.
     - Keep the existing direct-search `POST` and `GET` behavior unchanged.
     - Return clear statuses for idempotent replay, unsupported sources,
       missing records, wrong space, and non-extractable source behavior.
     - Return conflict when the same idempotency key is replayed with a
       different request body.
     - Support `source_search_runs`-backed structured sources. PubMed and
       MARRVEL compatibility routes are adapter-wrapped into the same durable
       store, so their handoffs use the same endpoint.
     - Ensure DrugBank credential behavior remains unchanged.
   - Output:
     - Request/response models and OpenAPI updates.
     - Route regression tests covering 200/201 success, idempotent replay,
       `404`, `501` or capability responses, and `503` credential behavior.

3. Variant handoff subagent
   - Ownership:
     `services/artana_evidence_api/variant_aware_document_extraction.py`,
     `services/artana_evidence_api/research_init_source_enrichment.py`,
     direct-source handoff helper modules, and variant extraction tests.
   - Tasks:
     - Convert selected ClinVar and MARRVEL direct-search records into durable
       extraction inputs with `source_type` set to `clinvar` or `marrvel`.
     - Make MARRVEL panel routing explicit so variant panels do not get mixed
       with OMIM, ortholog, expression, constraint, and target panels.
     - Prevent duplicate ClinVar proposals between deterministic structured
       drafts and variant-aware extraction output.
     - Preserve original record payload, provider ID, locator, citation,
       `source_capture`, and source-search run linkage.
     - Route variant-signal records into the existing variant-aware extraction
       path.
     - Convert incomplete variant anchors into review items or deferred
       extraction state instead of trusted graph facts.
     - Ensure research-plan enrichment documents can take the same
       variant-aware extraction branch when their source type and signals
       qualify.
   - Output:
     - Handoff-to-document/record builder.
     - Tests proving ClinVar and MARRVEL selected records can produce
       variant-aware candidates or review items.

4. Non-variant source policy subagent
   - Ownership: source registry metadata, handoff policy helpers, route tests,
     and user-facing capability messages.
   - Tasks:
     - Define explicit behavior for ClinicalTrials.gov, UniProt, AlphaFold,
       DrugBank, MGI, and ZFIN.
     - Choose one of: normalized source-specific proposal path, deferred
       extraction state, or clear "captured but not extractable yet" response.
     - Keep UniProt/protein, AlphaFold/structure, DrugBank/drug,
       ClinicalTrials.gov/clinical, and MGI/ZFIN/model-organism sources off the
       variant-aware path by default unless explicit variant text is detected.
     - Keep MONDO, HGNC, text, and PDF aligned with existing non-direct
       capability behavior.
   - Output:
     - Handoff policy table keyed by source.
     - Tests for each structured source family so no source silently no-ops.

5. Review-gating and graph-boundary subagent
   - Ownership: proposal/review-item integration tests and graph-boundary
     assertions.
   - Tasks:
     - Verify handoff-created extraction output creates candidates, proposals,
       or review items only.
     - Assert no direct trusted graph writes happen from direct source handoff.
     - Add tests around proposal/review queue behavior for accepted and
       incomplete variant records.
   - Output:
     - Regression tests proving graph promotion remains review-gated.

6. Documentation and final QA subagent
   - Ownership: `docs/plan.md`, user guide source sections,
     `docs/research_init_architecture.md`, and final verification notes.
   - Tasks:
     - Update docs after contracts settle.
     - Keep GitHub issue #10 aligned with final behavior.
     - Run focused tests, OpenAPI check, `git diff --check`, and
       `make artana-evidence-api-service-checks`.
   - Output:
     - Docs patch and QA summary.

Execution order:

1. Lead integrator freezes the endpoint shape, idempotency key, and persistence
   model before implementation begins.
2. Store/API contract and non-variant policy subagents work in parallel because
   their write sets can remain separate.
3. Public API subagent starts after the persistence contract is available.
4. Variant handoff subagent starts after selected-record access is available.
5. Review-gating subagent runs against the integrated handoff path.
6. Documentation/final QA runs last and resolves OpenAPI/docs drift.

Integration gates:

- No source-search response shape regressions.
- Durable search retrieval continues to work across fresh store/app instances.
- Handoff is idempotent under repeated calls.
- Wrong-space access returns not found or forbidden without leaking records.
- ClinVar handoff path produces review-gated extraction inputs; MARRVEL
  variant panels now use the same durable handoff path while context panels
  remain captured but not extractable.
- Non-variant sources return explicit, documented behavior.
- Live external API tests remain opt-in.
- `make artana-evidence-api-service-checks` passes before merge.

## Progress Checklist

Use this checklist to track implementation progress.

### Design And Contracts

- [x] Source capability model drafted.
- [x] Source registry module added.
- [x] Source registry includes PubMed and MARRVEL.
- [x] Source registry includes research-plan-only sources.
- [x] Direct-search versus research-plan-only behavior documented in code.
- [x] v2 source endpoint response models defined.
- [x] OpenAPI contract checked after source endpoints land.

### API Implementation

- [x] `GET /v2/sources` implemented.
- [x] `GET /v2/sources/{source_key}` implemented.
- [x] Generic `POST /v2/spaces/{space_id}/sources/{source_key}/searches`
  implemented.
- [x] Generic `GET /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}`
  implemented.
- [x] Generic source search routes support PubMed.
- [x] Generic source search routes support MARRVEL.
- [x] Generic source search routes support ClinVar.
- [x] Generic source search routes support ClinicalTrials.gov.
- [x] Generic source search routes support UniProt.
- [x] Generic source search routes support AlphaFold.
- [x] Generic source search routes support DrugBank with configured credentials.
- [x] Generic source search routes support MGI.
- [x] Generic source search routes support ZFIN.
- [x] MONDO remains explicitly non-direct because it is an ontology grounding
  loader rather than a bounded source-search adapter.
- [x] Capability error behavior implemented for unsupported direct searches.
- [x] Existing PubMed/MARRVEL v1 and typed v2 routes preserved as compatibility
  routes.

### Evidence Flow

- [x] Source-result capture contract defined.
- [x] Source metadata/provenance normalized.
- [x] PubMed search results use the shared capture/provenance shape.
- [x] MARRVEL search results use the shared capture/provenance shape.
- [x] Structured direct-search sources use the shared capture/provenance shape.
- [x] Structured direct-search results are persisted in durable Evidence API
  storage instead of process-local memory.
- [x] Structured-source proposal generation stays review-gated.
- [x] Advanced direct-write paths are clearly documented as non-normal flows.

### Research-Plan Integration

- [x] `research-plan` validates source keys through the registry.
- [x] `research-plan` source execution summary uses registry source keys.
- [x] PubMed replay/test hooks remain internal.
- [x] Research-plan docs explain source selection and source limitations.

### Tests And QA

- [x] Registry unit tests added.
- [x] v2 source endpoint API tests added.
- [x] Generic PubMed search regression tests added.
- [x] Generic MARRVEL search regression tests added.
- [x] Generic structured-source search regression tests added.
- [x] Durable direct-source search store tests added.
- [x] Fresh app/store route regression tests added for durable structured source
  searches.
- [x] DrugBank missing-credential behavior returns a clear service error.
- [x] Research-plan source validation tests added.
- [x] Compatibility tests for old PubMed/MARRVEL paths added.
- [x] `make artana-evidence-api-service-checks` passes.
- [x] `make graph-service-checks` not required; graph contracts were untouched.
- [x] Evidence API migration added for durable direct source-search runs.

### Direct Source Handoff Follow-Up

- [x] Freeze endpoint shape, selected-record selector, and idempotency contract.
- [x] Assign subagent ownership for store/API, public routes, variant handoff,
  non-variant policy, review-gating, and docs/QA.
- [x] Design handoff request/response models for selected direct source-search
  records.
- [x] Add `source_search_handoffs` model and migration with uniqueness for the
  per-record idempotency key.
- [x] Add an idempotent handoff endpoint or command for durable direct
  source-search results.
- [x] Use a stable per-record idempotency key based on search id plus provider
  id or record hash.
- [x] Store handoff request hashes and reject conflicting replays.
- [x] Convert selected ClinVar records into durable variant-aware extraction
  inputs.
- [x] Convert selected MARRVEL records into durable variant-aware extraction
  inputs.
- [x] Add panel-aware routing for MARRVEL handoff records.
- [x] Prevent duplicate ClinVar proposals between deterministic and
  variant-aware paths.
- [x] Make research-plan enrichment documents use the variant-aware extraction
  branch when source type and signals qualify.
- [x] Preserve source-search run linkage and `source_capture` metadata on
  generated documents or normalized records.
- [x] Define source-document behavior for ClinicalTrials.gov, UniProt,
  AlphaFold, DrugBank, MGI, and ZFIN handoff attempts.
- [x] Add source-family metadata and normalized record profiles for PubMed,
  ClinicalTrials.gov, UniProt, AlphaFold, DrugBank, MGI, and ZFIN handoff
  documents.
- [x] Back PubMed and MARRVEL compatibility searches with durable
  `source_search_runs` so handoff retrieval survives process restart.
- [x] Add an explicit handoff unit-of-work boundary for SQL-backed handoff,
  document, and run writes.
- [x] Make durable direct-source SQL saves participate in the shared
  unit-of-work helper and replay duplicate saves.
- [x] Add failure/replay tests proving a rolled-back handoff persists a
  deliberate failed run plus failed handoff without creating repeated runs.
- [x] Ensure handoff-created extraction output stays review-gated and does not
  directly promote graph facts.
- [x] Add tests for wrong-space handoff rejection.
- [x] Add tests for handoff idempotency and duplicate prevention.
- [x] Add tests for ClinVar handoff into variant-aware extraction input.
- [x] Add tests for MARRVEL handoff into variant-aware extraction after
  durable MARRVEL search storage exists.
- [x] Add tests for incomplete variant anchors creating review items or
  deferred extraction state.
- [x] Add OpenAPI coverage for the handoff contract.
- [x] Complete documentation and GitHub issue alignment after implementation.
- [x] Re-run `make artana-evidence-api-service-checks`.

### Docs

- [x] `docs/user-guide/03-workflow-overview.md` updated.
- [x] `docs/user-guide/04-adding-evidence.md` updated.
- [x] `docs/user-guide/09-endpoint-index.md` updated.
- [x] `docs/research_init_architecture.md` updated.
- [x] `docs/v2_api_migration_plan.md` cross-references this source plan.
- [x] Deprecated or compatibility routes are clearly marked.

## Rough Delivery Size

Minimum useful version:

- Source registry.
- `GET /v2/sources`.
- Generic source search route for PubMed and MARRVEL.
- Tests, OpenAPI check, and user-guide updates.

Expected effort: about one week.

Solid external-tester version:

- Minimum version plus research-plan registry integration.
- Shared capture/provenance contract.
- Direct source search across PubMed, MARRVEL, ClinVar, ClinicalTrials.gov,
  UniProt, AlphaFold, DrugBank, MGI, and ZFIN.
- Stronger smoke tests and docs.

Expected effort: about two to three weeks.

## Deferred Work

These are not part of the current backend extraction:

- rebuilding the deleted frontend in this repo;
- restoring `packages/artana_api`;
- restoring the old monorepo `src` package;
- turning identity into a standalone service before tester needs justify it;
- adding direct public endpoints for every source before the source has a stable
  direct-search user story.
