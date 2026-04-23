# Research Initialization Architecture

## Overview

The research initialization flow is the primary entry point for starting a new research investigation in a space. It orchestrates a multi-phase pipeline that discovers relevant literature, extracts evidence, and stages governed relation claims.

## Two Runtimes, One Flow

The flow involves two runtimes that are related as **parent → child**:

```
User creates space → Onboarding → research_init (parent)
                                       │
                                       ├─ Phase 1: PubMed discovery
                                       ├─ Phase 2: Document ingestion
                                       ├─ Phase 3: Entity extraction
                                       ├─ Phase 4: Observation bridge
                                       ├─ Phase 5: research_bootstrap (child)
                                       │               ├─ Graph connection
                                       │               ├─ Hypothesis generation
                                       │               └─ Claim curation staging
                                       └─ Phase 6: Result consolidation
```

### research_init_runtime

**Role:** Document-driven discovery and extraction.

**Entry point:** `POST /v1/spaces/{space_id}/research-init`

**What it does:**
1. Builds PubMed queries from the research objective and seed terms
2. Fetches and filters PubMed abstracts
3. Ingests documents into the harness document store
4. Runs entity extraction on each document (creating proposals)
5. Runs the observation bridge (persisting source_documents + observations to graph_runtime)
6. Optionally calls research_bootstrap as a child phase
7. Returns consolidated results

**Key characteristic:** Operates on raw documents. Most of its work is text-driven extraction.

### research_bootstrap_runtime

**Role:** Graph-driven refinement and claim governance.

**Entry point:** `POST /v1/spaces/{space_id}/agents/research-bootstrap/runs`

**What it does:**
1. Takes seed entity IDs from the parent init run
2. Runs graph connection to find related entities and relations
3. Generates hypothesis candidates
4. Stages governed claim curation (claim-curation run with approval queue)
5. Returns refined proposals and a research brief

**Key characteristic:** Operates on the graph. Most of its work is relation-driven reasoning.

### MARRVEL Enrichment

MARRVEL (Model organism Aggregated Resources for Rare Variant ExpLoration) was historically a separate enrichment step that created proposals directly during research_init and bootstrap. As of the P0.6 connector convergence work, MARRVEL now follows the same shared extraction path as other connectors:

1. **Old behavior (retired):** research_init and bootstrap called `_prepare_marrvel_enrichment_drafts()` and `_stage_marrvel_proposals_for_bootstrap()` to create `marrvel_omim` proposals directly via `proposal_store.create_proposals()`.

2. **Current behavior:** MARRVEL records are ingested as source documents with Tier 1 grounding attached (`marrvel_grounding` in raw_record metadata). The `MarrvelExtractionProcessor` returns `status="skipped"` with `ai_required=True`, deferring to the entity recognition + extraction AI pipeline for Tier 2 claim generation.

3. **Governance:** MARRVEL claims now flow through the same governed claim path as PubMed and ClinVar: extraction contract → relation claims → governed claim ledger → projection.

The direct proposal creation paths (`_run_marrvel_enrichment`, `_stage_marrvel_proposals_for_bootstrap`) are retired. The `/marrvel/ingest` endpoint is also retired.

### Why Two Runtimes?

The separation exists because:

1. **Different cost profiles:** Document extraction (init) is I/O-heavy and parallelizable. Graph connection (bootstrap) is compute-heavy and sequential.

2. **Different retry semantics:** Init can re-discover documents independently. Bootstrap depends on entities already existing in the graph.

3. **Different governance needs:** Init creates raw proposals. Bootstrap creates governed claims that require curation approval.

## Terminology

| Term | Meaning |
|------|---------|
| **Research init** | The full parent flow from PubMed discovery to proposal staging |
| **Research bootstrap** | The graph-driven child phase that refines entities into governed claims |
| **Observation bridge** | The step within init that persists source documents and observations to graph_runtime |
| **Claim curation** | The governance step within bootstrap that stages claims for human review |
| **Onboarding** | The conversational pre-init flow that collects objective, seed terms, and source preferences |

## How They Differ from the General Pipeline

| Aspect | General Pipeline | Research Init/Bootstrap |
|--------|-----------------|----------------------|
| **Trigger** | Scheduled ingestion jobs | User-initiated via onboarding |
| **Source selection** | Per-source configuration | Dynamic PubMed queries from objective |
| **Extraction** | Queued, async | Inline, synchronous within the run |
| **Governance** | Extraction → claim → auto-promotion | Extraction → bootstrap → governed curation |
| **Scope** | One source at a time | Multiple sources in one flow |

## Convergence Decision

**Bootstrap is a child phase of research_init, not a standalone harness.**

While the API exposes bootstrap as an independent endpoint (for testing and direct invocation), in production it is always called from within research_init. The standalone endpoint exists for:
- Integration testing
- Manual re-runs of the bootstrap phase without re-running PubMed discovery
- Development/debugging

Long-term, bootstrap may converge with general orchestration once graph-connection and hypothesis-generation become standard pipeline stages. Until then, it remains a special runtime because hypothesis reasoning is a distinct product workflow.

## File Reference

| File | Purpose |
|------|---------|
| `services/artana_evidence_api/research_init_runtime.py` | Parent runtime: discovery → extraction → bootstrap |
| `services/artana_evidence_api/research_bootstrap_runtime.py` | Child runtime: graph connection → hypotheses → curation |
| `services/artana_evidence_api/routers/research_init.py` | API endpoint for research init |
| `services/artana_evidence_api/routers/research_bootstrap_runs.py` | API endpoint for standalone bootstrap |
| External UI client | The Research Inbox UI is not present in this extracted checkout |
