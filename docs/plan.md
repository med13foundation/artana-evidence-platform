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

Tasks:

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
