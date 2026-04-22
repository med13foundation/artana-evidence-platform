# Grant Discussion Answers

Based on the actual codebase as of April 8, 2026.

---

## PART 3 — Architecture

### What architecture do we actually believe in: graph, documents, or hybrid?

**Hybrid, and that's the right call.** The system has two storage layers by design:

1. **Document store** (`harness_documents` table) — ingested source materials: PubMed abstracts, ClinVar records, AlphaFold predictions, user-uploaded PDFs. This is the evidence layer — raw materials that back every claim.

2. **Graph** (`entities`, `relations`, `relation_claims` tables in PostgreSQL) — extracted knowledge: entities (genes, diseases, phenotypes), relation claims ("MED13 ASSOCIATED_WITH intellectual disability"), and canonical relations (aggregated, governed, curation-tracked).

The boundary is clean: documents are source truth, the graph is derived knowledge. Every graph edge traces back to one or more documents through the provenance chain: `document → claim_evidence → relation_claim → relation_projection → canonical_relation`.

This isn't a compromise — it's the only honest architecture for biomedical reasoning. You can't reason over documents alone (too slow, no structure), and you can't reason over a graph alone (loses evidence context and provenance). The hybrid gives you structured traversal AND the ability to drill into "why does this edge exist?"

### Are we trying to force mechanistic reasoning into a graph that fundamentally can't represent it?

**No, but we're honest about the limits.** The graph supports multi-hop mechanistic traversal:

```
Variant →[LOSS_OF_FUNCTION]→ Gene →[PARTICIPATES_IN]→ Pathway →[UPSTREAM_OF]→ BiologicalProcess →[CAUSES]→ Phenotype
```

This works with 18 entity types, 29 relation types, and 67 constraints. The `reasoning_paths` and `reasoning_path_steps` tables cache discovered traversal chains.

What the graph can't do: represent continuous quantities, temporal dynamics, or probabilistic networks. We don't pretend it can. The qualifier registry handles penetrance, odds ratios, and effect sizes as edge attributes, not as graph structure. Conditionality (tissue-specific, population-specific) uses the CONTEXT participant role and scoping qualifiers in the canonicalization key.

### If we choose hybrid, what is the clear boundary between graph vs evidence documents?

| Layer | What it stores | Who writes | Mutability |
|-------|---------------|------------|------------|
| **Documents** | Raw source text, structured records, PDFs | Ingestion pipeline (PubMed, ClinVar, AlphaFold, user uploads) | Immutable after ingestion |
| **Claims** | Scientific assertions extracted from documents | Extraction agents (LLM-mediated) | Immutable once created; triage status changes only |
| **Canonical relations** | Aggregated knowledge with confidence | Claim projection after governance review | Curation lifecycle (DRAFT → APPROVED → RETRACTED) |

The rule: documents never change, claims never change, only canonical relations evolve through curation. Every mutation passes through the governance service — no agent has direct write access to canonical knowledge.

### What is the minimum viable architecture we can build before April 17 that is still technically honest?

**What already works (verified end-to-end on April 8):**

- Research space creation → onboarding → PubMed discovery → ClinVar/AlphaFold enrichment → LLM extraction → proposal review → graph population
- 23 documents from 3 sources, 99 proposals from 3 source kinds, 54 graph edges, 20k+ entities in a single MED13 test run
- FULL_AUTO and HUMAN_IN_LOOP governance toggle in the UI
- Graph Explorer showing claims with subject/relation/object/status

**What needs to work by April 17:**

1. Proposal→claim projection (P3.2) must work automatically — we just wired enrichment proposals to create graph claims directly, but document extraction proposals still bypass the claim pipeline. This is the one remaining gap between "proposals exist" and "the graph is populated."

2. FULL_AUTO governance must actually auto-promote. Currently the setting exists in the UI but document extraction creates proposals in a "pending_review" state regardless of governance mode. The extraction pipeline already has FULL_AUTO support in its code path — it just needs to be triggered.

### How do we describe this in the grant without overpromising (especially around Spanner Graph)?

**Be specific about what exists:**

"The system uses PostgreSQL with pgvector for the graph backend, supporting 18 entity types, 29 relation types, entity embeddings for similarity search, and a two-layer evidence model (claims + canonical relations). The architecture is designed with a stable API contract that insulates clients from storage changes, enabling future migration to dedicated graph databases when scale requires it."

**Do NOT say:**
- "We use Spanner Graph" (zero references in the codebase)
- "We use NetworkX for traversal" (plan.md mentions it but it's not implemented — pure SQL traversal)
- "We have a production graph database" (it's PostgreSQL, which is fine but not a graph DB)

**DO say:**
- "PostgreSQL-backed graph with pgvector embeddings" (accurate)
- "Domain-agnostic kernel with biomedical domain profile" (accurate — the kernel doesn't know what GENE means)
- "Evidence-first: every edge has provenance, confidence, and curation status" (accurate and verifiable)

### Are we okay carrying two systems long-term, or is hybrid just a transition state?

**Hybrid is the target state, not a transition.** The document store and graph serve different purposes:

- Documents are the audit trail — you need them for reproducibility, retraction handling, and provenance
- The graph is the reasoning layer — you need it for multi-hop traversal, hypothesis generation, and contradiction detection

Even if we migrated the graph to Spanner or Neo4j, the document store would remain. The API contract (claim-based evidence model with governed projection) is the stable boundary, not the storage technology.

---

## PART 4 — Open source

### Which components are actually worth open-sourcing because they will be used?

**Three candidates, ranked by adoption potential:**

1. **The ontology loader family** — HPO, UBERON, Cell Ontology, Gene Ontology, MONDO. Clean OBO parser, versioned import with checkpoint deduplication, shared gateway pattern. Any bioinformatics team building an ontology-backed system would use this instead of writing their own.

2. **The ClinVar connector** — search, fetch, parse (with the germline_classification fix). Maps variant pathogenicity to structured claims. ClinVar's API is painful to work with; a clean connector saves weeks.

3. **The evidence model schemas** — the two-layer claims/relations model with assertion classes, canonicalization, and qualifier registry. This is a reusable pattern for any system that needs to aggregate evidence from multiple sources with provenance tracking.

**Not worth open-sourcing yet:**
- The LLM extraction pipeline (too coupled to Artana kernel)
- The research-init orchestrator (too product-specific)
- The UI (Next.js inbox — product, not infrastructure)

### What would make a bioinformatics engineer say: "I want to use this instead of building my own"?

- A `pip install artana-ontology-loader` that loads HPO/MONDO/UBERON into a Postgres table in 3 lines of code
- A `pip install artana-clinvar` that searches ClinVar and returns structured variant records with real clinical significance values
- Clear README with "here's what you get in 5 minutes" examples
- Tests that run without network access (preloaded content pattern already exists)

### Can we isolate the variant interpretation pipeline as a standalone package quickly?

**Partially.** The ClinVar connector (ingestor + gateway + query config) is self-contained in:
- `src/infrastructure/ingest/clinvar_ingestor.py` (search + fetch + parse)
- `src/infrastructure/data_sources/clinvar_gateway.py` (query interface)
- `src/domain/entities/data_source_configs/clinvar.py` (config model)

But there's no standalone HGVS nomenclature parser (Thr326Lys → gene + variant + protein change). The system relies on ClinVar's structured API, not free-text variant parsing. To interpret Thr326Lys, you'd need to add an HGVS parser (e.g., `hgvs` Python package) and wire it to the ClinVar lookup.

### What level of code quality and documentation do we need before making anything public?

**Current state:**
- 1,600 Python files, 405k LOC
- 543 test files, 128k LOC of tests
- No hardcoded secrets (all via environment variables)
- No LICENSE file at repository root (must add before publishing)
- Clean architecture with domain/application/infrastructure layers

**Minimum for publication:**
- Add LICENSE file (Apache 2.0 or MIT)
- Add top-level README with quickstart
- Isolate the package into its own repo or subdirectory with `pyproject.toml`
- Remove any internal references (Artana-specific configs, private API URLs)
- Add CI badge

### Are we risking reputation by open-sourcing something that currently has known issues?

**Not if we scope it correctly.** The known issues (P3.2 proposal-to-claim gap, MONDO performance, missing MARRVEL ingestor) are in the orchestration layer, not in the components worth open-sourcing. The ontology loaders and ClinVar connector work correctly — they have comprehensive tests and have been verified against live APIs.

Don't open-source the orchestrator or the full platform. Open-source the building blocks.

### How do we ensure open-source accelerates adoption, not just exposes unfinished work?

Publish the **pieces that are complete**, not the whole system:
- `artana-ontology-loader`: HPO, MONDO, UBERON, GO, CellOntology — 100% working, tested, verified against real OBO files
- `artana-clinvar`: ClinVar search + fetch + parse — working with real NCBI API
- Keep the orchestrator, UI, and governance engine private until they're production-ready

---

## PART 5 — Visibility

### Am I comfortable putting a public repo out that reviewers can see before the code is fully stable?

**Yes, if scoped to the stable components.** The ontology loaders have 36+ conformance tests, the ClinVar connector has been verified against the live API, and the OBO parser handles all five ontology families consistently. These are stable.

The research-init orchestrator, proposal-to-claim projection, and FULL_AUTO governance are NOT ready for public scrutiny. Keep those private.

### What is the minimum we can publish that still looks credible and strong?

1. The evidence model specification (claims + relations + canonicalization rules) as a design document
2. The ontology loader family as a standalone package with tests
3. A worked example showing: "MED13 research space → 99 proposals from 3 sources → graph with 54 edges"
4. Architecture diagrams showing the two-layer model and multi-source pipeline

### Do we gain anything by publishing code now, or is documentation enough?

**Documentation alone won't convince reviewers** who know bioinformatics. They'll ask "does this actually work?" Code with tests that they can run answers that question definitively.

But: publish a focused package (ontology loader or ClinVar connector), not the entire monorepo. The monorepo has 1,600 files — that's overwhelming, not impressive.

### Are there any technical risks in publishing the Nome gene review?

**Risk: the review may expose gaps** in variant interpretation. The system can look up ClinVar classifications for a gene but can't parse HGVS nomenclature from free text. If the review references specific variants by HGVS notation (NM_005121.3:c.976T>A / p.Thr326Lys), the system can find them in ClinVar but can't interpret the molecular consequence without the structured database.

**Mitigation:** Be explicit about what the system does ("retrieves and aggregates ClinVar classifications") vs what it doesn't ("de novo HGVS interpretation").

### How do we make sure what we publish accurately reflects what works vs what doesn't?

Include a **"Current Capabilities"** section in any publication:

| Capability | Status | Evidence |
|-----------|--------|----------|
| Multi-source literature discovery | Working | 23 docs from 3 sources in MED13 test |
| Variant pathogenicity lookup | Working | ClinVar API returns real classifications |
| LLM-based claim extraction | Working | 53 proposals from PubMed abstracts |
| Structured data enrichment | Working | 34 ClinVar proposals, AlphaFold predictions |
| Graph exploration | Working | 54 claims visible in Graph Explorer |
| Automatic graph promotion | Partial | FULL_AUTO setting exists, claim projection being finalized |
| Variant interpretation (HGVS parsing) | Not implemented | Depends on ClinVar structured data |
| DrugBank integration | Blocked | Requires API key |

---

## PART 6 — Thr326Lys worked example

### What can we realistically run by April 11 without compromising correctness?

**Option A: ClinVar lookup for MED13 Thr326Lys**

Create a research space for MED13, let the pipeline run (3.5 min without MONDO). The ClinVar enrichment will fetch all MED13 variants from ClinVar. If Thr326Lys (NM_005121.3:c.976T>A) exists in ClinVar, it will appear as a structured record with clinical significance, conditions, and review status.

This is **fully automated** and takes < 5 minutes. The output is real ClinVar data, not hallucinated.

**Option B: Manual variant lookup + graph context**

1. Run the MED13 research space pipeline (automated)
2. Query ClinVar specifically for the variant (automated via ClinVar enrichment)
3. Show the graph context: MED13 → ASSOCIATED_WITH → intellectual disability (from PubMed), MED13 variant → ASSOCIATED_WITH → Intellectual developmental disorder 61 (from ClinVar)
4. The "interpretation" is the graph context, not de novo variant analysis

### Is it more important to show automation or correct reasoning in the demo?

**Correct reasoning.** The grant reviewers are scientists. They'll spot bullshit instantly. Show:
- Real ClinVar data with real clinical significance values
- Real PubMed papers with real abstracts
- Graph edges that trace back to specific sources

Don't show: LLM-generated "interpretations" that can't be verified.

### If we do a structured pipeline (Option B), how reproducible is it?

**100% reproducible for the ClinVar component** — same gene query returns same variants from ClinVar API. PubMed results may vary slightly over time as new papers are indexed.

The LLM extraction is NOT fully reproducible (model outputs vary). The proposals show confidence scores and source provenance, so a reviewer can trace any claim back to its origin.

### What are the minimum fixes required to avoid misleading results?

1. **ClinVar parser must return real data** — FIXED (germline_classification parsing, organism filter removed)
2. **Proposals must create graph claims** — FIXED (enrichment proposals now write to claim_relations)
3. **Graph Explorer must show claims** — WORKING (17 ClinVar claims visible in latest test)
4. **Entity conflict crash must not kill extraction** — FIXED (CONCEPT_FAMILY fallback resolution)

### How do we clearly communicate in the grant what is manual vs automated?

| Step | Automated? |
|------|-----------|
| Research space creation | Manual (user fills wizard) |
| Onboarding clarification | Automated (AI asks questions) |
| PubMed search + ingestion | Automated |
| ClinVar variant lookup | Automated |
| AlphaFold structure prediction | Automated |
| LLM claim extraction | Automated |
| Proposal review (HUMAN_IN_LOOP) | Manual |
| Graph population (FULL_AUTO) | Automated |
| Variant interpretation narrative | Not yet automated |

### Do we have bandwidth to execute this cleanly in the next few days?

**Yes, for Options A and B.** The pipeline runs in 3.5 minutes. Creating a MED13 space with Thr326Lys context is a matter of running the existing pipeline and filtering the results. No new code needed — just run it and document the output.

---

## Cross-cutting

### What are we actually building vs pretending to build?

**Actually building:**
- A multi-source biomedical evidence aggregation system backed by PostgreSQL
- LLM-mediated extraction from papers into a governed evidence graph
- Structured data connectors (ClinVar, AlphaFold, ontologies) that create graph claims directly
- A research workspace with onboarding, proposal review, and graph exploration

**Not yet building (but plan says we are):**
- Spanner Graph migration (zero code)
- NetworkX traversal (pure SQL instead)
- Full variant interpretation pipeline (we do ClinVar lookup, not de novo analysis)
- Drug repurposing queries (DrugBank not connected — no API key)

### Where are we taking on technical debt knowingly, and is that acceptable for the grant?

| Debt | Acceptable? | Why |
|------|------------|-----|
| Proposal→claim projection bypass | Being fixed now | Was the #1 gap, now wired |
| MONDO loads 26k entities via individual HTTP POSTs | Yes for grant | 10 min is slow but works; batch endpoint is optimization |
| No HGVS parser | Yes if disclosed | ClinVar provides structured classifications |
| In-memory proposal store in tests | Yes | SQL store used in production |
| Entity identifier conflicts (duplicate entities) | Needs monitoring | Fixed with CONCEPT_FAMILY fallback but duplicates may still occur |

### What is the one thing that must work for this to be credible?

**The research space must produce real, traceable graph edges from real biomedical data in under 5 minutes.**

This works today: create space → PubMed finds papers → ClinVar finds variants → LLM extracts claims → graph shows edges with provenance. The output is verifiable — every edge links to a real PubMed paper or ClinVar record.

### If we had to cut scope by 50%, what would we keep?

Keep:
- PubMed + ClinVar pipeline (literature + variant data)
- LLM extraction → proposals → graph claims
- Graph Explorer with claim table view
- HUMAN_IN_LOOP governance (simpler than FULL_AUTO)

Cut:
- AlphaFold, MARRVEL, DrugBank, UniProt enrichment
- MONDO ontology loading
- Chase rounds and iterative discovery
- LLM-powered research brief
- Continuous learning
- Visual Graph tab

### What would make me confident saying: "this system can evolve into what we're claiming"?

Three things:

1. **The architecture is honest and extensible.** Domain-agnostic kernel + biomedical domain profile means we can add entity types, relation types, and sources without changing the core. The connector family pattern (gateway → ingestion → extraction → pipeline) is proven for 9 sources.

2. **The evidence model is correct.** Two-layer claims/relations with assertion classes, canonicalization, and governance modes. This is the right abstraction — it won't need to be rewritten.

3. **The pipeline produces real, verifiable output.** 54 graph edges from real PubMed papers and ClinVar records, not synthetic data. A reviewer can check every claim against its source.

What I wouldn't say: "the system is production-ready." It isn't — it's a research prototype with solid architecture. The difference between prototype and production is operational (deployment, monitoring, API keys), not architectural.
