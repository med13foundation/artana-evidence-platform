# Artana Knowledge Graph: Engineering Plan

> **Status note (April 2026):** This is the platform's master design document. Sections labeled "Current implementation note" and "Current state" describe the state at the time the section was written and may have been overtaken by shipped work — see [`docs/project_status.md`](./project_status.md) and [`docs/remaining_work_priorities.md`](./remaining_work_priorities.md) for the current implementation state.

## 1. Vision & Design Principles

Artana is a general-purpose biomedical reasoning engine built on a curated, evidence-first knowledge graph. Users ingest evidence from literature and structured databases, explore connections through a graph explorer, generate hypotheses via AI-assisted reasoning, and promote validated findings through expert review.

The graph is the system of record. Every edge has provenance, confidence, and curation status.

### What the platform enables

The same graph structure supports multiple reasoning modes:

- **Diagnosis**: traverse from patient phenotypes to candidate genes and variants through mechanistic chains
- **Hypothesis generation**: discover connections that span papers -- no single publication contains the answer, but the graph does
- **Drug repurposing**: traverse from disrupted pathways to approved drugs targeting those pathways
- **Biomarker discovery**: find measurable signals correlated with mechanisms across publications
- **Contradiction detection**: identify claims from different publications that conflict on the same entity pair
- **Mechanism mapping**: build visual causal chains from evidence, connecting variants to protein domains to biological processes to phenotypes

### Design principles

1. **Evidence-first**: every edge has provenance and confidence. Claims are the scientific assertion ledger; canonical relations are derived projections.
2. **Governed promotion**: AI agents propose; a policy engine decides. In the default mode (HUMAN_IN_LOOP), all promotions require human review. In FULL_AUTO mode, configurable rules can auto-promote high-confidence, well-evidenced proposals. Either way, no agent has direct write access to canonical knowledge.
3. **Graph density enables discovery**: sparse graphs only answer questions you already know. The knowledge model must maximize the facts captured per paper.
4. **Constraints prevent garbage, not novelty**: the constraint system blocks biologically nonsensical combinations, not unexpected discoveries.
5. **The knowledge model is the product**: infrastructure (Postgres, in-process traversal in the graph service repository, future graph DB) is swappable. The entity types, relation types, and constraint strategy define what the platform can reason about.

### Architecture (unchanged)

- Postgres-backed graph model with in-process traversal in the graph service repository layer (BFS / multi-hop / gap queries live in `services/artana_evidence_db/_relation_query_mixin.py`)
- Clean Architecture: domain entities, application services, infrastructure adapters
- Stable graph API contract insulating clients from storage changes
- Claim-based evidence model with participant roles (SUBJECT, OBJECT, CONTEXT, QUALIFIER, MODIFIER)
- Optional future migration to dedicated graph DB preserves API contract
- Research spaces as the unit of isolation -- all data, entities, relations, and permissions are space-scoped

### Domain-agnostic kernel, biomedical domain profile

The kernel (graph ledger, dictionary service, governance engine, pipeline orchestration) is **domain-agnostic**. It stores entities, relations, claims, and evidence without knowing what "GENE" or "CAUSES" means. All domain semantics live in the **domain profile** -- the entity types, relation types, constraints, synonyms, forbidden triples, and qualifier registry defined in this plan.

This plan describes the **biomedical domain profile**: the first and primary profile loaded via the `GraphDictionaryLoadingConfig` seed mechanism. The kernel infrastructure (sections 2-5) is reusable for any domain. The biomedical vocabulary (sections 7-9) is the specific profile.

---

## 2. Evidence & Claims

The graph has two layers: **claims** (what papers say) and **canonical relations** (what the graph asserts). Understanding this distinction is critical -- it's the foundation of the entire evidence model.

### The two-layer model


| Layer                   | What it is                                                                                      | Who writes                                      | Mutability                                                                                                                                       |
| ----------------------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Claims**              | Raw scientific assertions extracted from papers. "Paper X says Gene A causes Disease B."        | Extraction agents                               | Immutable once created. Can be triaged (OPEN → RESOLVED / REJECTED / NEEDS_MAPPING) but never edited.                                            |
| **Canonical relations** | The graph's asserted knowledge. "Gene A causes Disease B, supported by 5 claims from 3 papers." | Projection from claims, after governance review | Mutable: curation status changes (DRAFT → UNDER_REVIEW → APPROVED → REJECTED → RETRACTED). Aggregate confidence updates as new evidence arrives. |


Claims **project** into canonical relations through a materialization pipeline. Claims about the same assertion from different papers strengthen the same canonical relation. This is how the graph aggregates evidence.

**Critical invariant**: "same assertion" is defined by the **canonicalization key**, not just the subject-relation-object triple. See "Claim-to-relation projection" below.

### Claim structure

Each claim has:

- **Participants**: entities in specific roles (SUBJECT, OBJECT, CONTEXT, QUALIFIER, MODIFIER, OUTCOME). A claim can have multiple participants -- this is how conditionality, digenic effects, and qualified assertions are represented.
- **Evidence**: one or more evidence rows, each with a verbatim text span (or generated sentence), confidence level (low/medium/high), and source document reference.
- **Polarity**: SUPPORT, REFUTE, UNCERTAIN, or HYPOTHESIS. A refuting claim is negative evidence -- "Paper Y says Gene A does NOT cause Disease B."
- **Provenance**: source_document_id, agent_run_id, source_type. Full lineage from paper to claim to canonical relation.

### Evidence tiers

- **Per-fact assessment**: fact-producing agents emit structured qualitative assessments, not freehand decimals. For relation and observation extraction this is the fact-assessment shape (`support_band`, `grounding_level`, `mapping_status`, `speculation_level`, `confidence_rationale`). Other agent families use task-shaped variants of the same pattern.
- **Derived numeric evidence weight** (0.0-1.0): backend code converts the qualitative assessment into a deterministic numeric weight for thresholds, ranking, and graph aggregation. This is policy data, not a model-authored probability.
- **Evidence sentence source**: verbatim_span (directly quoted from paper) vs. artana_generated (synthesized by the agent)
- **Evidence sentence confidence**: low/medium/high confidence attached to generated evidence phrasing. This is distinct from fact assessment and from derived numeric evidence weight.
- **Assertion class**: SourceBackedClaim, CuratedAssertion, or ComputationalHypothesis (see "Assertion classes" below)
- **Highest evidence tier**: the best tier across all evidence for a relation

For aggregation rules, canonicalization semantics, and the computational evidence boundary, see the dedicated subsections below.

### Canonicalization rules

A claim is the atomic scientific assertion. A canonical relation is a scoped projection of one or more compatible claims. Projection must preserve meaning, not just triple shape.

- A claim is eligible for projection only when its participants are normalized and its assertion class permits projection.
- Canonical relations are keyed by `space_id + relation_type + subject_fingerprint + object_fingerprint + context_fingerprint`.
- `subject_fingerprint` is a single canonical entity for ordinary claims and an ordered participant set for combinatorial claims. A digenic claim never merges with a single-subject claim.
- `context_fingerprint` includes all materially scoping context: tissue, cell type, organism or model system, disease subtype, population, experimental condition, and any explicit CONTEXT participants.
- Claims with different context fingerprints do not merge into the same canonical relation.
- Qualifiers fall into two classes: **scoping qualifiers** and **descriptive qualifiers**. Scoping qualifiers (for example `population`, `organism`, `developmental_stage`, and any qualifier explicitly marked as scoping in the qualifier registry) contribute to the canonicalization key and produce distinct canonical relations. Descriptive qualifiers (for example `penetrance`, `odds_ratio`, `effect_size`, `p_value`, and `sample_size`) are stored as canonical relation attributes and do not split canonical relations by default.
- `SUPPORT` claims may strengthen a canonical relation. `REFUTE`, `UNCERTAIN`, and `HYPOTHESIS` claims remain first-class claims and attach to the relevant canonical relation as conflicting or non-asserting evidence; they do not strengthen the asserted edge directly.
- Relations are stored in one canonical direction only. Inverse and symmetric forms are derived in the query layer to avoid duplicate storage and double counting.
- Projection is idempotent. Reprocessing the same claim must not create a second canonical relation or inflate distinct source counts.

### Confidence aggregation rules

Aggregate confidence is computed from independent support units, not from raw evidence rows. More text spans from the same paper should not look like more evidence.

- A support unit is one normalized claim from one independent source family.
- Multiple spans, sentences, or structured fields from the same source document collapse into a single support unit.
- Sources that repackage the same upstream assertion count as one source family for aggregation unless provenance shows independent evidence.
- Each support unit receives a `unit_score` derived from the claim's qualitative assessment, evidence form, and source-quality weight. In other words, agent output is qualitative-first; numeric aggregation inputs are backend-derived.
- Verbatim evidence ranks above synthesized evidence. Curated structured sources may receive a configurable quality weight by source family.
- Aggregate support confidence uses diminishing returns so the tenth similar source helps less than the second:

```text
aggregate_support_confidence = 1 - product(1 - capped_unit_score)
```

- The system stores at least these separate fields: `support_confidence`, `refute_confidence`, `distinct_source_count`, and `distinct_source_family_count`.
- Governance decisions use `support_confidence` together with conflict policy. A single blended scalar must not hide strong contradictory evidence.
- Computational hypotheses do not contribute to support confidence, distinct source count, or evidence tier.

### Assertion classes: source-backed claims vs computational hypotheses

Not all assertions should count as evidence. The system must separate external scientific evidence from internally generated hypotheses.

- `SourceBackedClaim`: extracted from literature, structured databases, or curator-supplied external records with explicit provenance. Eligible for canonical projection.
- `CuratedAssertion`: human-authored or curator-confirmed statement with rationale and source linkage. Eligible for canonical projection.
- `ComputationalHypothesis`: inferred from graph topology, similarity, embeddings, transfer reasoning, or model-generated traversal. Stored as a proposal, not as canonical evidence.

Computational hypotheses are useful, but they must remain a separate class.

- They may appear in search, ranking, work queues, and hypothesis-generation views.
- They may reference supporting paths, model version, prompt version, and feature scores.
- They do not raise evidence tier, do not count as distinct sources, and do not auto-approve canonical relations.

Promotion path:

1. Computational hypothesis is generated.
2. A curator or downstream workflow requests verification or evidence acquisition.
3. A source-backed claim or curated assertion is added.
4. Only then may the canonical relation be created or strengthened.

If FULL_AUTO is enabled, it applies only to `SourceBackedClaim` records that match `EXPECTED` profiles (see Section 8) and satisfy governance thresholds.

---

## 3. Agent Architecture

AI agents are hypothesis generators. They propose; the governance policy engine decides whether to promote. No agent has direct write access to canonical knowledge -- every mutation passes through the governance service, which applies configurable rules (see Section 4). In HUMAN_IN_LOOP mode, a human must approve. In FULL_AUTO mode, the policy engine auto-promotes if configured thresholds are met. Either way, the agent itself never promotes.

### Agent types


| Agent                     | What it does                                                                      | Output contract                                                                                    |
| ------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| **Extraction**            | Reads source records and documents, extracts observations and relation claims     | ExtractionContract: observations, relations, rejected facts                                        |
| **Extraction Policy**     | Reviews undefined relation patterns, proposes constraint updates                  | ExtractionPolicyContract: constraint proposals, mapping proposals                                  |
| **Graph Connection**      | Proposes new edges between existing entities based on graph neighborhood analysis | ProposedRelation with qualitative assessment, evidence, and backend-derived weight                 |
| **Graph Search**          | Answers natural-language questions by traversing the graph                        | GraphSearchContract: interpreted intent, result/evidence-chain assessments, and derived confidence |
| **Query Generation**      | Generates source-specific search query strings for external data sources (PubMed, ClinVar, etc.) | QueryGenerationContract: query string, source_type, query_complexity, estimated_result_count       |
| **Hypothesis Generation** | Generates mechanistic hypotheses via multi-hop traversal and transfer reasoning   | Ranked candidates with paths, scores, and supporting evidence                                      |
| **Entity Recognition**    | Identifies and normalizes biomedical entities in text                             | Recognized entities/observations with recognition-specific assessments and aliases                 |
| **Mapping Judge**         | Evaluates proposed entity/relation mappings for correctness                       | Resolution decision plus mapping-specific qualitative assessment                                   |
| **Content Enrichment**    | Enriches extracted entities with additional context and metadata                  | Enriched entity records                                                                            |


### Assessment-first scoring model

The platform now separates two jobs that were previously conflated:

1. **The model judges the evidence qualitatively.**
  - Fact-producing agents emit structured assessments.
  - The exact schema is agent-family-specific.
  - Facts use support/grounding/mapping/speculation fields.
  - Recognition and mapping agents use task-shaped variants of the same idea.
2. **The backend makes policy decisions numerically when it actually needs math.**
  - Governance thresholds, ranking, and graph aggregation still operate on numeric values.
  - Those numeric values are deterministically derived from the qualitative assessment.
  - Aggregate graph confidence remains a backend computation, not a direct LLM output.

This keeps agent outputs honest and auditable while preserving the numeric machinery needed for promotion and ranking.

### Bounded proposal layer

Every agent contract has a `decision` field: `generated`, `fallback`, or `escalate`.

- **generated**: agent produced a coherent output with explicit qualitative assessment. Governance service evaluates it.
- **fallback**: agent used a degraded path (e.g., heuristic extraction instead of LLM). The output remains auditable, but assessment and derived weight are intentionally conservative.
- **escalate**: agent could not produce a sufficiently grounded assessment. The proposal enters a review queue for human evaluation. No graph mutation happens.

This is the enforcement boundary. The agent cannot bypass the governance service -- the contract structure makes ungoverned writes architecturally impossible. Whether the governance service requires human approval or applies auto-promotion rules is a policy decision, not an agent decision.

### Shadow mode

Agents can run in shadow mode (`shadow_mode: true`), where all side effects are suppressed. The full extraction and proposal pipeline runs, but nothing is written to the graph. This is used for:

- Testing new extraction prompts against real papers
- Evaluating agent quality without risking graph pollution
- A/B testing different agent configurations

---

## 4. Governance & Curation

The governance layer sits between agent output and graph mutations. It is a **policy engine** -- configurable rules determine whether a proposal requires human review or can be auto-promoted.

### Governance modes (per space)


| Mode                        | Who promotes  | Behavior                                                                                                                                                                                                                                                         |
| --------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **HUMAN_IN_LOOP** (default) | Human curator | All agent proposals require human review. Claims are created but canonical relations stay in DRAFT until a curator approves. This is the default for clinical and research spaces.                                                                               |
| **FULL_AUTO**               | Policy engine | Applies only to `SourceBackedClaim` records that match `EXPECTED` constraint profiles (Section 8) and satisfy governance thresholds. `ComputationalHypothesis` and `REVIEW_ONLY` claims are never auto-promoted. Auto-promoted relations can be retracted later. |


In both modes, the **agent never promotes directly**. The difference is whether promotion requires a human action or can be delegated to configurable governance rules. FULL_AUTO is narrowly scoped: it applies only to source-backed claims matching expected profiles. This is a deliberate product choice for high-volume ingestion -- not a bypass of governance.

The mode is configurable per research space via `relation_governance_mode` in space settings.

### Governance decision flow

1. Agent produces a contract (extraction, graph connection, hypothesis), with item-level qualitative assessments where applicable
2. Governance service normalizes those assessments into derived numeric policy weights, then evaluates thresholds, evidence requirements, auto-approve toggle, and per-relation-type overrides
3. Output: `GovernanceDecision { allow_write, requires_review, shadow_mode, reason }`
4. If `allow_write` and not `requires_review`: claim is persisted and projected to canonical relation
5. If `requires_review`: claim is persisted in OPEN status, projected to a DRAFT canonical relation when projection preconditions are met, and enters review queue
6. If shadow mode: nothing is persisted, but the full pipeline runs for evaluation

### Curation status lifecycle

Canonical relations follow this lifecycle:

```
DRAFT → UNDER_REVIEW → APPROVED → (optionally) RETRACTED
                     ↘ REJECTED
```

- **DRAFT**: created by extraction, not yet reviewed
- **UNDER_REVIEW**: curator has opened it for evaluation
- **APPROVED**: human-validated, appears in canonical graph views
- **REJECTED**: human-rejected, excluded from canonical views but preserved for audit
- **RETRACTED**: previously approved, withdrawn (e.g., due to paper retraction or contradicting evidence)

### Space settings that shape governance

Research spaces have 30+ configurable settings that control governance behavior:

- `auto_approve` / `require_review`: global toggles
- `review_threshold`: minimum derived confidence for auto-approval
- `relation_review_thresholds`: per-relation-type overrides
- `min_distinct_sources` / `min_aggregate_confidence`: auto-promotion thresholds
- `block_if_conflicting_evidence`: halt auto-promotion if contradicting claims exist
- `min_evidence_tier`: minimum evidence quality for auto-promotion
- `concept_policy_mode`: PRECISION (strict matching), BALANCED, or DISCOVERY (broad matching) -- controls how aggressively the system creates new entities
- `dictionary_agent_creation_policy`: whether agents can create new entity types as ACTIVE or PENDING_REVIEW

---

## 5. Pipeline Orchestration

The system runs as a background pipeline with durable job claiming, heartbeats, and stage-based execution.

### Pipeline stages

```
Ingestion → Enrichment → Extraction → Graph Projection
```

Each stage:

1. Claims a job from the queue with a worker heartbeat
2. Executes the stage logic (fetch data, run LLM, persist results)
3. Records events to the pipeline event log
4. Advances to the next stage or marks the job as failed

### Operational monitoring

The source workflow monitor tracks real-time state across:

- Document counts (ingested, pending, failed)
- Extraction queue status (PENDING, EXTRACTED, FAILED, SKIPPED, TIMEOUT_FAILED)
- Relation review counts (OPEN, RESOLVED, REJECTED)
- Paper candidate tracking
- Event streaming for live dashboard updates

### Scheduling

- **Ingestion scheduler**: durable loop that runs due ingestion jobs on a configurable interval
- **Pipeline worker**: async background loop claiming jobs with configurable concurrency (staging=1, prod=2)
- **Heartbeat**: 15s default, prevents stale claims from blocking the queue
- **Resume points**: pipeline can resume from any stage on failure

---

## 6. Data Sources

The graph is only as useful as the evidence fed into it. Data sources are a first-class concept, but they do not all have the same shape. The platform supports multiple connector families that share one governed kernel write boundary, so new sources can be added without changing the graph model.

### Current sources (implemented)

**Design principle**: every data source must contribute **connections** (edges) to the graph, not just entities (nodes). A source that imports nodes without edges is an incomplete integration. The graph's discovery value comes from edge density -- the more cross-references, hierarchy edges, and relation claims each source contributes, the more hidden connections the system can find through multi-hop traversal.


| Source        | Type                    | What it provides                                                                                                                                  | Extraction                                                                                       | Target graph contribution |
| ------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------- |
| **PubMed**    | Literature              | Abstracts and full-text papers. The primary source for gene-disease associations, mechanisms, and therapeutic evidence.                           | AI-heavy literature extraction with relevance gating and optional full-text rescue.              | Relation claims (AI-extracted from text) |
| **ClinVar**   | Genomic variants        | Variant pathogenicity classifications with clinical significance, review status, and submitter evidence.                                          | Structured extraction with field-level evidence grounding.                                       | Relation claims (variant→gene, variant→disease, clinical significance) |
| **MARRVEL**   | Gene-centric aggregator | Aggregates across ClinVar, OMIM, dbNSFP, Geno2MP, gnomAD, DGV, DIOPT orthologs, GTEx expression, and Pharos drug targets -- all for a given gene. | Deterministic structured parsing for ingestion; proposal-oriented enrichment in bootstrap flows. | Relation claims (gene→phenotype, gene→expression, variant→frequency) |
| **MONDO**     | Disease ontology        | 26k+ disease terms with hierarchy, synonyms, and cross-references to OMIM, DOID, MeSH, ICD, NCIT.                                                | Ontology loader with ID-prefix filtering (MONDO OBO bundles imported ontologies). Entity type: DISEASE. | Entities + hierarchy edges (is_a) + cross-reference edges (equivalentTo OMIM/DOID/MeSH). Enables disease grounding for all other sources. |
| **UniProt**   | Protein data            | Protein identity, aliases, molecular function, domain/location, publication linkage.                                                              | Tier 1 grounding with 4 fact families; Tier 2 defers to AI pipeline.                            | Relation claims (protein→function, protein→domain, protein→pathway) |
| **DrugBank**  | Drug-target interactions | Drug names, targets, mechanisms of action, interactions. Drug repurposing queries.                                                                 | Tier 1 structured grounding; Tier 2 generates DRUG→TARGETS→GENE and DRUG→TREATS→DISEASE claims. Requires DRUGBANK_API_KEY. | Relation claims (drug→target, drug→enzyme, drug→disease) |
| **AlphaFold** | Protein structure       | Predicted protein structures, domain boundaries, confidence scores.                                                                                | Tier 1 domain boundary parsing; Tier 2 generates PROTEIN_DOMAIN→PART_OF→PROTEIN claims. Open API. | Relation claims (domain→protein, structure similarity→functional hypothesis) |


### Supported formats (ingestion-ready)


| Format      | Use case                                          |
| ----------- | ------------------------------------------------- |
| PDF         | User-uploaded papers, reports, clinical documents |
| Text        | Plain text evidence, notes                        |
| File upload | Generic file ingestion                            |
| CSV / JSON  | Structured datasets                               |


### Planned future sources


| Source                 | What it would provide                                                                                                                                                             | Phase   |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------- |
| **OMIM**               | Disease descriptions, gene-phenotype relationships, inheritance patterns. Currently accessed indirectly via MARRVEL.                                                              | Phase 1 |
| **MGI**                | Mouse genome informatics. Knockout phenotypes, gene expression. Required for MODEL_ORGANISM evidence.                                                                             | Phase 3 |
| **ZFIN**               | Zebrafish information network. Model organism phenotypes. Required for MODEL_ORGANISM evidence.                                                                                   | Phase 3 |
| **ClinicalTrials.gov** | Registered clinical trials. Required for CLINICAL_TRIAL entity seeding.                                                                                                           | Phase 3 |

Current implementation note: HPO, UBERON, Cell Ontology, Gene Ontology, and MONDO are implemented as a first-class ontology-loader connector family. MONDO ontology hierarchy (`IS_A`) and cross-reference edges are persisted via the two-pass loop in `OntologyIngestionService` (`persist_hierarchy_edge` + `persist_xref_edge`). DrugBank and AlphaFold are fully integrated with API clients, ingestion services, and extraction processors that follow the Tier 1 grounding + defer-to-AI Tier 2 pattern (`status="skipped"`, `ai_required=True`, `reason="<source>_tier1_grounding_complete_defer_to_ai_pipeline"`), so the shared AI extraction pipeline picks up the documents for Tier 2 relation generation.


### Target connector architecture

The connector layer is source-specific on fetch and normalization, but source-agnostic at the governance and relation-claim boundary, with explicit loader/import rules for non-claim seed data.

1. Each connector family owns its own fetch and normalization logic.
  Literature connectors fetch documents and metadata.
   Structured database connectors fetch record-oriented JSON or XML payloads.
   Ontology loaders fetch versioned vocabularies and hierarchies.
2. All graph-producing connectors must emit standard platform outputs.
  Deterministic grounding outputs still use standard platform shapes for entities, identifiers, observations, and provenance.
   Claim-producing connectors use the same output shape for new relation claims: observations, relation claims, rejected facts, and provenance.
   `ExtractionContract` remains the standard contract for connectors that produce claim-like facts.
3. All new relation claims go through one governed write path.
  The required claim path is:
   `claim ledger -> validation/governance -> canonical projection`
   No connector-specific direct claim write path should bypass this flow.
   Approved loader/import flows may still seed entities, identifiers, aliases, and ontology hierarchy edges directly with provenance and versioning.
4. The platform supports three connector families.
  **Literature connectors**: query-driven or upload-driven document sources such as PubMed and PDFs. These use document fetch, optional enrichment, and AI-mediated extraction.
   **Structured database connectors**: entity-driven or identifier-driven sources such as MARRVEL, ClinVar, DrugBank, and UniProt. These use deterministic grounding plus AI-mediated relation-claim generation.
   **Ontology loaders**: bulk vocabulary and hierarchy imports such as HPO, UBERON, Cell Ontology, and Gene Ontology. These seed entities, identifiers, aliases, and hierarchy relations through the approved loader/import path. If they also contribute new biological relation claims from definitions or descriptions, those claims still go through the same AI-mediated claim path as every other source.
5. Two-tier extraction is the target pattern for every connector that wants to contribute new relation claims.
  **Tier 1: deterministic grounding** parses source fields into entities, identifiers, aliases, structured attributes, and other grounding facts with explicit provenance. This tier is source-specific, cheap, and fast.
   **Tier 2: AI-mediated claim generation** reads the Tier 1 grounding plus the source record's structured fields and available text, then emits relation claims through the standard `ExtractionContract`. This is the only path for creating new relation claims from connectors.
   Tier 2 is mandatory for every new relation claim. Without Tier 2, a connector can still seed entities, identifiers, aliases, observations, and approved loader/import facts, but it does not assert new relation claims.
   Tier 1 grounding feeds Tier 2 context. The LLM should build on source-normalized entities and attributes rather than rediscovering them.
   LLM mediation may generate normalized claim wording from structured evidence, but it must not create a `SourceBackedClaim` unless the source record itself supports that relation with explicit provenance.
   Loader/import hierarchy edges are not treated as new relation claims and do not require fake literature-style prompting.
   Current implementation note: ClinVar and MARRVEL now both have explicit conformance coverage for this pattern, including queued Tier 1 grounding handoff, Tier 2 extraction, and shared claim-path writes under governance.
6. New sources require family-appropriate components.
  Literature and structured connectors need a gateway/ingestor, normalization logic, deterministic grounding, AI claim-generation logic, and a `SourceType` entry.
   Ontology loaders need a loader/importer, identifier and versioning strategy, hierarchy handling, optional AI claim-generation logic for non-hierarchy relations, and a `SourceType` entry when they are exposed as user-manageable sources.
   Current implementation note: HPO, UBERON, Cell Ontology, Gene Ontology, and MONDO now share the same ontology-loader family shape in code, scheduler wiring, and product catalog exposure.
7. The graph does not know or care which source produced an edge.
  A `GENE -> CAUSES -> DISEASE` assertion should look the same in the claim ledger whether it came from PubMed, ClinVar, MARRVEL, or a user-uploaded PDF. The evidence, provenance, and governance outcomes differ, but the graph contract does not.
8. **Every source must contribute edges, not just nodes.**
  A source integration is incomplete if it only imports entities. The graph's discovery value comes from connection density. Specific requirements by connector family:
   **Ontology loaders** must import hierarchy edges (`is_a`, `part_of`) and cross-reference edges (`equivalentTo`, `closeMatch`) as loader/import relations with provenance. MONDO→OMIM, MONDO→DOID, HPO→UMLS cross-references are connections that enable entity resolution and cross-source joins. These edges go directly to the graph since they are curated ontological facts, but they are not bare triples -- see requirement 9 below.
   **Structured database connectors** must route records through the kernel ingestion pipeline to produce relation claims, not just store raw data. DrugBank drug-target interactions are pre-validated connections. AlphaFold domain boundaries are structural facts. Both should produce governed claims.
   **Literature connectors** already produce claims through AI extraction. No change needed.
9. **Every edge must carry a human-readable evidence sentence.**
  Even deterministic edges from ontology loaders must have an AI-generated evidence sentence that explains what the edge means in plain language. A graph edge that a human cannot read and understand is useless for discovery. Examples:
   `MONDO:0005148 → IS_A → MONDO:0005015` must carry an evidence sentence like: *"Type 2 diabetes mellitus is classified as a subtype of diabetes mellitus in the Monarch Disease Ontology. This groups T2DM with other forms of diabetes (type 1, gestational, MODY), enabling cross-subtype variant and treatment analysis."*
   `MONDO:0005148 → EQUIVALENT_TO → OMIM:125853` must carry: *"The Monarch Disease Ontology maps type 2 diabetes mellitus (MONDO:0005148) as equivalent to OMIM entry 125853, linking clinical variant data in OMIM to the standardized disease classification in MONDO."*
   For ontology edges, evidence sentences are generated once at import time by AI reading the source term definitions, synonyms, and context. The evidence sentence is `artana_generated` (not verbatim) and carries `source_type: ontology_import` provenance. These sentences make the graph explorable by researchers who need to understand why an edge exists, not just that it exists.

### Cross-source orchestration

The current system treats each source independently. PubMed runs, then ClinVar runs, then MARRVEL runs -- each in isolation. No agent reasons across sources to find connections that only emerge when you combine evidence from multiple databases.

**Target architecture**: a research orchestrator agent that reads the researcher's objective and seed entities, then intelligently coordinates all enabled sources to build the richest possible knowledge graph for that research question. The orchestrator is an AI agent -- it does not follow a fixed script. It reads results, decides what to query next, and synthesizes findings into a coherent narrative.

**Guiding principle**: optimize for the best results, not speed. The orchestrator should pursue every promising lead across sources before presenting findings. A thorough first research pass that takes 2-3 minutes is far more valuable than a fast one that misses connections.

#### Source execution order

Sources have natural dependencies. The orchestrator executes them in this order:

**Round 1 — Foundation (ontologies and literature)**

1. **Ontology loaders first** (MONDO, HPO, UBERON, GO, Cell Ontology): import entity nodes, hierarchy edges, and cross-reference edges. These must run before any other source so that disease, phenotype, and process mentions from PubMed/ClinVar/MARRVEL can resolve to canonical ontology entities. Every imported edge carries an AI-generated evidence sentence.
2. **PubMed**: search literature using the research objective AND seed entities. AI extracts relation claims from abstracts. This is the primary discovery source -- it identifies the genes, variants, diseases, drugs, and pathways relevant to the research question.

**Round 2 — Structured enrichment (driven by PubMed findings)**

The orchestrator reads PubMed results, identifies all newly discovered entities (genes, variants, diseases, proteins), and queries structured sources for each:

3. **ClinVar**: fetch variant pathogenicity classifications for every gene identified by PubMed. Produces governed relation claims (variant→gene, variant→disease).
4. **MARRVEL**: fetch gene-level panels (expression, orthologs, phenotype associations, allele frequencies) for every gene. Produces governed relation claims.
5. **DrugBank**: fetch drugs targeting the genes/proteins identified. Produces governed relation claims (drug→target, drug→disease).
6. **UniProt**: fetch protein function, domains, and pathway membership. Produces governed relation claims.
7. **AlphaFold**: fetch protein structures and domain boundaries for drug targets and key proteins. Produces governed relation claims (domain→protein).

**Round 3 — Iterative discovery (chase new leads)**

Round 2 will reveal new entities not present in the seed set or the initial PubMed results. The orchestrator evaluates which new entities are most relevant to the research objective and runs a second PubMed search plus targeted structured queries for those entities.

**Iteration strategy**: the orchestrator runs up to **3 discovery rounds** (the initial round plus 2 chase rounds). Each chase round:
- Identifies entities discovered in the previous round that were not in the seed set
- Filters to the top entities by relevance to the research objective (max 10 new entities per round to bound cost)
- Runs PubMed + structured source queries for those entities
- Extracts claims and generates proposals

Three rounds is the target because:
- Round 1 finds direct connections to the seed entities
- Round 2 finds connections one hop away (the gene PubMed mentioned, the drug that targets it)
- Round 3 finds connections two hops away (the pathway that drug disrupts, the other diseases sharing that pathway)
- Beyond 3 rounds, diminishing returns dominate -- the cost of additional queries outweighs the marginal discovery value

The orchestrator may stop early if a round produces fewer than 3 new relevant entities.

#### Cross-source synthesis

After all rounds complete, the orchestrator must **synthesize** findings into a research brief -- not just dump proposals. The brief is an AI-written narrative document that:

1. **Summarizes what was found** across all sources, organized by theme (not by source). Example: "Three pathogenic BRCA1 variants (from ClinVar) are located in the BRCT domain (from AlphaFold), which is required for DNA repair (from PubMed). Olaparib (from DrugBank) targets PARP1, which compensates for BRCA1 loss-of-function (from PubMed) -- this is the synthetic lethality mechanism behind PARP inhibitor therapy."
2. **Highlights cross-source connections** that no single source contains. These are the hidden connections the platform exists to find. Example: "The ClinVar variant c.5266dupC disrupts the BRCT domain (AlphaFold structure), which PubMed literature links to homologous recombination deficiency, making carriers candidates for PARP inhibitor therapy (DrugBank: Olaparib, Rucaparib, Talazoparib)."
3. **Identifies gaps and next questions** -- what the system could not find, what the researcher should investigate further. Example: "No expression data available for BRCA1 in ovarian tissue (MARRVEL returned no GTEx data). Consider uploading ovarian cancer-specific papers."
4. **Lists all proposals generated** with their source provenance, grouped by confidence and review priority.

The research brief is delivered to the researcher as the first substantive message in the onboarding thread, replacing the current pattern of a generic system message followed by a list of ingested documents.

Current implementation note: research-init now runs PubMed in Phase 2a, then a Phase 2b enrichment block that wires ClinVar, DrugBank, AlphaFold, MARRVEL, ClinicalTrials.gov, MGI, and ZFIN through their respective `run_*_enrichment` helpers in `research_init_source_enrichment.py`. The orchestrator drives Round 2 enrichment from gene mentions extracted from PubMed abstracts (`extract_gene_mentions_from_text`), not just user seed terms. Cross-source overlap detection (`compute_cross_source_overlaps`) feeds a theme-organized AI-written brief (`research_init_brief.py`) which is then delivered to the researcher as the first substantive inbox message via `_research_init_success_content` in `services/research_inbox_runtime/service.py` (subject = brief title, body = rendered brief markdown).

Bootstrap, discovery, and proposal-oriented runtimes may stage work outside the steady-state ingestion pipeline, but they should still converge on the same governed claim path before asserting graph truth.

Research-space lifecycle should converge the same way. The target create-space path is:
`public.research_spaces + memberships -> graph-owned tenant sync -> inbox/runtime onboarding -> harness/bootstrap staging`.
Graph-runtime authorization should not depend on a later repair or reconciliation step for a newly created space.

Current implementation note: local verification of fresh UI-created `covid19` spaces now shows the supported create path creating platform truth, graph-owned tenant sync, inbox runtime/projection, and harness state/proposals together. The first research pass can now also persist graph-owned `source_documents` and `observations` through the shared observation-ingestion path while proposals and claim-curation work are staged. Canonical `relation_claims` may still remain empty until governed review is applied. That is a status note, not the target design.
Current implementation note: the bootstrap/runtime split is now documented in `docs/research_init_architecture.md`, including `research_init_runtime`, `research_bootstrap_runtime`, MARRVEL enrichment, and the convergence decision.

---

## 7. Knowledge Model

### 7.1 Entity Types

18 types across 5 domain contexts. All entities participate in the graph as first-class nodes.

#### Genomics


| Entity Type       | Description                          | Why needed                                                                                                                         |
| ----------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| `GENE`            | Protein-coding or non-coding gene    | Core molecular entity. Root of most mechanistic chains.                                                                            |
| `PROTEIN`         | Protein or translated gene product   | Drug target, interaction partner. Distinct from gene because post-translational behavior matters.                                  |
| `VARIANT`         | Sequence variant or allelic change   | Root cause in genetic disease. The starting point for variant interpretation.                                                      |
| `PROTEIN_COMPLEX` | Stable multi-subunit assembly        | Mediator complex, ribosomes, spliceosomes. Many disease mechanisms involve complex disruption, not single-protein failure.         |
| `PROTEIN_DOMAIN`  | Structural/functional protein region | Two variants in the same gene cause different diseases if they hit different domains. Required for genotype-phenotype specificity. |


#### Clinical


| Entity Type | Description                                              | Why needed                                                                                             |
| ----------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `PHENOTYPE` | Observable trait or clinical feature (HPO)               | Patient presentation layer. The "output" of mechanistic chains.                                        |
| `DISEASE`   | Disease or diagnostic condition (OMIM/Mondo)             | Diagnostic endpoint. Distinct from phenotype -- a disease is a named constellation of phenotypes.      |
| `SYNDROME`  | Named syndrome or clinically recognized disorder pattern | Clinical grouping. Rare disease diagnosis often names the syndrome before the mechanism is understood. |
| `DRUG`      | Therapeutic compound or intervention                     | Drug repurposing, treatments, safety signal detection.                                                 |


#### Anatomy


| Entity Type            | Description                     | Why needed                                                                                                                                                                                                                       |
| ---------------------- | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TISSUE`               | Anatomical tissue type (UBERON) | Where genes are expressed, where phenotypes manifest. A variant in the same gene causes cardiomyopathy in heart tissue and intellectual disability in neurons. Without tissue, you can't answer "why these specific phenotypes?" |
| `CELL_TYPE`            | Cell type (Cell Ontology)       | More specific than tissue. Expression context, cellular dysfunction. GABAergic neuron vs. glutamatergic neuron matters for neurological disease.                                                                                 |
| `CELLULAR_COMPARTMENT` | Subcellular location (GO:CC)    | Where molecular events occur. Protein mislocalization is a major disease mechanism -- a protein in the cytoplasm that should be in the nucleus.                                                                                  |


#### General


| Entity Type          | Description                                | Why needed                                                                                                                                     |
| -------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `SIGNALING_PATHWAY`  | Biological signaling or regulatory pathway | Mechanistic context. Wnt signaling, Notch signaling, mTOR pathway.                                                                             |
| `BIOLOGICAL_PROCESS` | Biological process (GO:BP)                 | Broader than signaling pathway. Covers apoptosis, autophagy, DNA repair, chromatin remodeling, mRNA splicing -- the "why" behind associations. |
| `MOLECULAR_FUNCTION` | Biochemical activity (GO:MF)               | Functional annotation. Kinase activity, DNA binding, transcription factor activity. Bridges proteins to processes.                             |
| `PUBLICATION`        | Published scientific article               | Evidence source. Every fact traces back to one or more publications.                                                                           |


#### Translational


| Entity Type      | Description                        | Why needed                                                                                                                                                      |
| ---------------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MODEL_ORGANISM` | Animal model evidence (MGI, ZFIN)  | Mouse/zebrafish/fly validation. "Knockout of Med13 in mice causes cardiac defects" is critical evidence that doesn't come from human papers.                    |
| `CLINICAL_TRIAL` | Registered clinical trial (NCT ID) | Translational evidence bridge. Connects molecular findings to clinical action. "This drug is being tested for this condition" closes the bench-to-bedside loop. |


### 7.2 Relation Types

35 types across 3 functional categories.

#### Core Causal (11 types)

Relations that describe cause, effect, and intervention.


| Relation Type               | Directional | Inverse           | Description                                                                                                                        |
| --------------------------- | ----------- | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `ASSOCIATED_WITH`           | yes         | `ASSOCIATED_WITH` | Generic statistical association. The catch-all when causation is unknown.                                                          |
| `CAUSES`                    | yes         | `CAUSED_BY`       | Direct causal relationship. Stronger claim than association.                                                                       |
| `TREATS`                    | yes         | `TREATED_BY`      | Therapeutic relationship. Drug to Disease/Phenotype.                                                                               |
| `TARGETS`                   | yes         | `TARGETED_BY`     | Molecular targeting. Drug to Gene/Protein/Pathway.                                                                                 |
| `BIOMARKER_FOR`             | yes         | `HAS_BIOMARKER`   | Measurable signal for a condition or mechanism.                                                                                    |
| `PHYSICALLY_INTERACTS_WITH` | **no**      | itself            | Physical binding. Protein-protein, protein-DNA. The only non-directional core relation.                                            |
| `ACTIVATES`                 | yes         | `ACTIVATED_BY`    | Positive regulation. Turns something on.                                                                                           |
| `REGULATES`                 | yes         | `REGULATED_BY`    | Generic regulation. Neutral direction -- use when activation vs. inhibition is unclear.                                            |
| `INHIBITS`                  | yes         | `INHIBITED_BY`    | Negative regulation. Turns something off.                                                                                          |
| `SENSITIZES_TO`             | yes         | `SENSITIZED_BY`   | Drug sensitivity. "Variant X sensitizes to Drug Y." Pharmacogenomics.                                                              |
| `PHENOCOPY_OF`              | **no**      | itself            | Diseases that look clinically identical but have different molecular causes. Daily reality in rare disease differential diagnosis. |


#### Extended Scientific (16 types)

Relations that describe structure, location, ordering, and function.


| Relation Type      | Directional | Inverse           | Description                                                                                                                                                                  |
| ------------------ | ----------- | ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `UPSTREAM_OF`      | yes         | `DOWNSTREAM_OF`   | Pathway ordering. A comes before B in a mechanistic chain.                                                                                                                   |
| `DOWNSTREAM_OF`    | yes         | `UPSTREAM_OF`     | Inverse of UPSTREAM_OF.                                                                                                                                                      |
| `PART_OF`          | yes         | `HAS_PART`        | Compositional. Subunit of a complex, domain of a protein.                                                                                                                    |
| `COMPONENT_OF`     | yes         | `HAS_COMPONENT`   | Member of a larger assembly. More specific than PART_OF for molecular complexes.                                                                                             |
| `EXPRESSED_IN`     | yes         | `EXPRESSES`       | Gene/Protein expression in a tissue or cell type. The spatial dimension of biology.                                                                                          |
| `PARTICIPATES_IN`  | yes         | `HAS_PARTICIPANT` | Entity takes part in a process or pathway.                                                                                                                                   |
| `LOCATED_IN`       | yes         | `CONTAINS`        | Spatial location. Variant in a protein domain, protein in a cellular compartment, gene at a locus.                                                                           |
| `LOSS_OF_FUNCTION` | yes         | `HAS_LOF_VARIANT` | Variant mechanism: haploinsufficiency, null allele. The most commonly needed variant-mechanism relation. Same gene can have LOF and GOF variants causing different diseases. |
| `GAIN_OF_FUNCTION` | yes         | `HAS_GOF_VARIANT` | Variant mechanism: dominant negative, constitutive activation.                                                                                                               |
| `COLOCALIZES_WITH` | **no**      | itself            | Spatial co-occurrence in cell/tissue. Weaker than PHYSICALLY_INTERACTS_WITH.                                                                                                 |
| `COMPENSATED_BY`   | yes         | `COMPENSATES_FOR` | Functional compensation/redundancy. Gene B rescues loss of Gene A. Explains variable expressivity and suggests therapeutic targets.                                          |
| `SUBSTRATE_OF`     | yes         | `HAS_SUBSTRATE`   | Enzyme-substrate relationship.                                                                                                                                               |
| `TRANSPORTS`       | yes         | `TRANSPORTED_BY`  | Molecular transport.                                                                                                                                                         |
| `MODULATES`        | yes         | `MODULATED_BY`    | Weaker than REGULATES. Allosteric effects, indirect modulation.                                                                                                              |
| `PREDISPOSES_TO`   | yes         | `PREDISPOSED_BY`  | Risk relationship weaker than CAUSES. Incomplete penetrance, polygenic risk. "Variant X increases risk of Disease Y."                                                        |
| `CO_OCCURS_WITH`   | **no**      | itself            | Statistical co-occurrence without causal claim. Weaker than ASSOCIATED_WITH -- purely observational.                                                                         |


#### Document Governance (8 types)

Relations that describe evidence provenance, not biology.


| Relation Type | Directional | Inverse          | Description                                              |
| ------------- | ----------- | ---------------- | -------------------------------------------------------- |
| `SUPPORTS`    | yes         | `SUPPORTED_BY`   | Evidence backs a claim. Publication to entity/claim.     |
| `REFINES`     | yes         | `REFINED_BY`     | More specific version of a statement.                    |
| `GENERALIZES` | yes         | `SPECIALIZED_BY` | More abstract version of a statement.                    |
| `INSTANCE_OF` | yes         | `HAS_INSTANCE`   | Specific case of a general class.                        |
| `MENTIONS`    | yes         | `MENTIONED_BY`   | Publication references an entity. Weakest evidence link. |
| `CITES`       | yes         | `CITED_BY`       | Paper-to-paper citation.                                 |
| `HAS_AUTHOR`  | yes         | `AUTHOR_OF`      | Authorship.                                              |
| `HAS_KEYWORD` | yes         | `KEYWORD_OF`     | Keyword tagging.                                         |


### 7.3 Domain Contexts


| Context         | Description                                        |
| --------------- | -------------------------------------------------- |
| `general`       | Domain-agnostic defaults                           |
| `clinical`      | Clinical and biomedical literature                 |
| `genomics`      | Genomics and variant interpretation                |
| `anatomy`       | Tissue, cell type, and subcellular compartment     |
| `translational` | Model organisms, clinical trials, bench-to-bedside |


### 7.4 Synonym Strategy

The LLM uses natural language. Scientists write "suppresses", "abolishes", "attenuates", "blocks" -- all of which mean INHIBITS. The synonym table is the translation layer between how scientists write and how the graph stores.

**Status (April 2026)**: Target met for relation synonyms — **207 synonyms shipped** in `graph_domain_config.py`, exceeding the 200+ target. Entity alias harvesting from HGNC/UniProt/DrugBank/HPO is the remaining sub-target.

Strategy:

1. **Relation synonyms**: expand from 10 to 200+ by adding common NLP extraction variants for each relation type. Source from biomedical NLP literature and observed extraction patterns.
2. **Entity aliases**: leverage gene symbol aliases from HGNC, protein names from UniProt, drug names from DrugBank, phenotype synonyms from HPO.
3. **Automated synonym harvesting**: when the extraction agent encounters a relation label that maps to an existing canonical type, auto-propose the synonym via the policy agent. This is already supported by the existing RelationTypeMappingProposal contract.

### 7.5 Inverse and Symmetric Relation Normalization

Relations are stored in one canonical direction only. Inverse and symmetric forms are derived in the query layer. (This is also specified in the canonicalization rules in Section 2.)

- **Directional relations** (e.g., CAUSES/CAUSED_BY): store only the forward direction. `GENE → CAUSES → DISEASE` is stored; `DISEASE → CAUSED_BY → GENE` is derived by the query layer when traversing in reverse.
- **Symmetric relations** (e.g., PHYSICALLY_INTERACTS_WITH, PHENOCOPY_OF, CO_OCCURS_WITH): store once with deterministic ordering (lower entity ID first).
- **Extraction normalization**: if the LLM extracts "Disease Y is CAUSED_BY Gene X", the extraction adapter normalizes to `Gene X → CAUSES → Disease Y` before persistence.

---

## 8. Constraint Strategy

### 8.1 The Problem with Whitelisting

The original whitelist had 23 allowed triples out of ~2,783 possible combinations (0.83% coverage), leaving 14 of 23 relation types with zero constraints and 3 entity types (SYNDROME, PROTEIN_COMPLEX, MOLECULAR_FUNCTION) unable to participate in any relations.

**Status (April 2026)**: This problem is resolved. The platform now ships **106 constraints** spanning all 35 relation types and all 18 entity types, including **32 FORBIDDEN triples** (with wildcard target support for cross-cutting prohibitions), EXPECTED profiles for the common biology, and REVIEW_ONLY profiles for plausible-but-novel combinations. The original premise — that whitelisting contradicts the goal of a discovery engine — drove the move to the Forbidden / Expected / Review-Only model described in Section 8.2 below.

### 8.2 Constraint Model: Forbidden, Expected, Review-Only

The platform should not choose between a tiny whitelist and total permissiveness. Validation should reject nonsense, accept common biology, and route novelty to review.

- `FORBIDDEN`: biologically nonsensical combinations. These are rejected immediately and persisted as rejected facts with reasons.
- `EXPECTED`: common, well-profiled combinations for a relation type. These can proceed through normal governance and may be auto-approved if space policy allows.
- `REVIEW_ONLY`: plausible but novel, weakly profiled, or semantically unusual combinations. These are persisted as claims and routed to review, but they are never auto-promoted.

Expected profiles should define more than source and target types.

- They may include typical subject and object families, required participant roles, context requirements, and disallowed qualifiers.
- They should support soft domain and range expectations rather than brittle hard whitelists.
- Unknown combinations default to `REVIEW_ONLY`, not `EXPECTED`.

### 8.3 Constraint Provenance

Constraint provenance describes how a profile was created and how much it is trusted:


| Tier           | How Created                    | Trust Level                                      |
| -------------- | ------------------------------ | ------------------------------------------------ |
| **BUILTIN**    | Hardcoded seed data            | Highest -- always active                         |
| **TRUSTED**    | Created by expert curation     | High -- human-reviewed                           |
| **DISCOVERED** | Created by extraction pipeline | Medium -- auto-created, evidence-threshold-gated |


Enforcement, however, uses `FORBIDDEN`, `EXPECTED`, and `REVIEW_ONLY` because those map directly to runtime behavior. Provenance tiers describe *origin*, enforcement classes describe *what happens*.

### 8.4 Validation Flow

1. Reject if the claim matches a `FORBIDDEN` profile.
2. Allow normal governance if it matches an `EXPECTED` profile.
3. Persist and route to review if it is plausible but outside expected profiles (`REVIEW_ONLY`).

All rejected facts continue to be persisted with reasons for audit. The policy agent continues to propose profile updates for undefined patterns.

### 8.5 Forbidden Triples

The forbidden list prevents biologically nonsensical combinations. Expected size: 30-50 entries. Wildcards mean the source type can never appear with that relation type regardless of target.


| Source Type            | Relation Type               | Target Type | Why                                                                 |
| ---------------------- | --------------------------- | ----------- | ------------------------------------------------------------------- |
| `PUBLICATION`          | `CAUSES`                    | *           | Publications describe causation, they don't cause biological events |
| `PUBLICATION`          | `TREATS`                    | *           | Publications don't treat conditions                                 |
| `PUBLICATION`          | `PHYSICALLY_INTERACTS_WITH` | *           | Publications are not molecular                                      |
| `PUBLICATION`          | `ACTIVATES`                 | *           | Publications don't activate molecules                               |
| `PUBLICATION`          | `INHIBITS`                  | *           | Publications don't inhibit molecules                                |
| `PUBLICATION`          | `EXPRESSED_IN`              | *           | Publications are not expressed                                      |
| `PUBLICATION`          | `LOSS_OF_FUNCTION`          | *           | Publications don't have variants                                    |
| `PUBLICATION`          | `GAIN_OF_FUNCTION`          | *           | Publications don't have variants                                    |
| `DRUG`                 | `EXPRESSED_IN`              | *           | Drugs are not expressed in tissues                                  |
| `DRUG`                 | `LOSS_OF_FUNCTION`          | *           | Drugs don't have LOF variants                                       |
| `DRUG`                 | `GAIN_OF_FUNCTION`          | *           | Drugs don't have GOF variants                                       |
| `DRUG`                 | `PARTICIPATES_IN`           | *           | Drugs don't participate in biological processes (they modify them)  |
| `PHENOTYPE`            | `TARGETS`                   | *           | Phenotypes don't target molecules                                   |
| `PHENOTYPE`            | `ACTIVATES`                 | *           | Phenotypes don't activate molecules                                 |
| `PHENOTYPE`            | `INHIBITS`                  | *           | Phenotypes don't inhibit molecules                                  |
| `PHENOTYPE`            | `TREATS`                    | *           | Phenotypes don't treat conditions                                   |
| `PHENOTYPE`            | `EXPRESSED_IN`              | *           | Phenotypes are not expressed (they manifest)                        |
| `DISEASE`              | `TARGETS`                   | *           | Diseases don't target molecules                                     |
| `DISEASE`              | `ACTIVATES`                 | *           | Diseases don't activate molecules                                   |
| `DISEASE`              | `INHIBITS`                  | *           | Diseases don't inhibit molecules                                    |
| `DISEASE`              | `TREATS`                    | *           | Diseases don't treat conditions                                     |
| `DISEASE`              | `EXPRESSED_IN`              | *           | Diseases are not expressed                                          |
| `TISSUE`               | `CAUSES`                    | `DISEASE`   | Tissues don't cause disease (disease manifests in tissue)           |
| `TISSUE`               | `TREATS`                    | *           | Tissues don't treat conditions                                      |
| `TISSUE`               | `TARGETS`                   | *           | Tissues don't target molecules                                      |
| `CLINICAL_TRIAL`       | `PHYSICALLY_INTERACTS_WITH` | *           | Trials are not molecular                                            |
| `CLINICAL_TRIAL`       | `EXPRESSED_IN`              | *           | Trials are not expressed                                            |
| `CLINICAL_TRIAL`       | `CAUSES`                    | *           | Trials don't cause biological events                                |
| `MODEL_ORGANISM`       | `TREATS`                    | *           | Model organisms don't treat conditions                              |
| `MODEL_ORGANISM`       | `TARGETS`                   | *           | Model organisms don't target molecules                              |
| `CELLULAR_COMPARTMENT` | `CAUSES`                    | *           | Compartments don't cause events                                     |
| `CELLULAR_COMPARTMENT` | `TREATS`                    | *           | Compartments don't treat conditions                                 |


---

## 9. Structural Capabilities

These capabilities are achievable within the existing schema using claim participants and qualifiers. No database migrations needed.

### 9.1 Negation

**Problem**: "Gene X does NOT cause Disease Y" cannot currently be represented.

**Solution**: claims already carry polarity (`SUPPORT`, `REFUTE`, `UNCERTAIN`, `HYPOTHESIS`). A negated assertion is a `REFUTE` claim. Extraction agents tag negated claims during NLP. Graph views filter or annotate refuting claims. The `polarity` qualifier on claim participants is a convenience alias for the claim-level polarity when needed at the participant level.

### 9.2 Conditionality

**Problem**: "Gene X causes Disease Y only in brain tissue" cannot be expressed as a simple triple.

**Solution**: use the existing CONTEXT participant role. A conditional relation is a claim where the CONTEXT role is populated:

```
SUBJECT(Gene X) → CAUSES → OBJECT(Disease Y), CONTEXT(Tissue = Brain)
```

The claim participant model already supports this pattern (SUBJECT, OBJECT, CONTEXT, QUALIFIER, MODIFIER roles). This is a usage convention on existing infrastructure.

### 9.3 Penetrance & Quantitative Attributes

**Problem**: "Variant X causes Disease Y with 70% penetrance" is not representable beyond free text. Ad-hoc JSONB keys drift across agents and prompt versions.

**Solution**: a **qualifier registry** defines the allowed qualifier keys, their value types, and validation rules. Qualifiers are stored in claim participant `qualifiers` JSONB but are schema-validated against the registry before persistence. Qualifiers that define scope (population, organism) affect the canonicalization key (Section 2) and produce distinct canonical relations.

**Registered qualifier keys:**


| Key                   | Type   | Validation        | Description                                           |
| --------------------- | ------ | ----------------- | ----------------------------------------------------- |
| `penetrance`          | float  | 0.0-1.0           | Proportion of carriers who express the phenotype      |
| `frequency`           | float  | 0.0-1.0           | Allele frequency in population                        |
| `odds_ratio`          | float  | > 0.0             | Effect size for association                           |
| `p_value`             | float  | 0.0-1.0           | Statistical significance                              |
| `effect_size`         | float  | any               | Generic effect magnitude                              |
| `population`          | string | enum or free text | Population context (e.g., "European", "East Asian")   |
| `organism`            | string | enum              | Source organism (e.g., "human", "mouse", "zebrafish") |
| `developmental_stage` | string | free text         | When in development (e.g., "E14.5", "postnatal")      |
| `polarity`            | string | SUPPORT           | REFUTE                                                |
| `sample_size`         | int    | > 0               | Number of individuals/samples                         |
| `sex`                 | string | enum              | Sex-specific context                                  |


The registry is extensible -- new keys can be added via the dictionary service. But extraction agents are constrained to registered keys, preventing ad-hoc qualifier drift across different agents or prompt versions.

AI agents use these in hypothesis scoring. Graph projection surfaces them as edge attributes. Only qualifiers marked as scoping in the qualifier registry contribute to the canonicalization key; descriptive qualifiers remain attributes on the canonical relation.

### 9.4 Combinatorial / Digenic Effects

**Problem**: "Variant A + Variant B together cause Disease C" (hyperedge) cannot be expressed in a standard triple.

**Solution**: reified claims with multiple SUBJECT participants. The existing claim participant model has a `position: int` field:

```
SUBJECT(Variant A, position=0) + SUBJECT(Variant B, position=1) → CAUSES → OBJECT(Disease C)
```

Graph projection treats multi-subject claims as hyperedge-equivalent structures.

### 9.5 Contradiction Detection

`SUPPORT` and `REFUTE` claims coexist with their evidence. Contradiction is detected at query time by finding claims with conflicting polarity (`SUPPORT` vs `REFUTE`) for the same canonicalization key, including materially matching context participants. Contradiction score = min(support_confidence, refute_confidence) -- a high score means strong evidence on both sides, which is a genuine scientific disagreement worth surfacing.

---

## 10. Query Patterns the Graph Must Support

The graph's value is measured by the questions it can answer. These are organized in tiers of increasing sophistication.

### Tier 1: Association Lookup

Basic entity-to-entity queries. The foundation.

- "What phenotypes are associated with Gene X?"
- "What drugs target Protein Y?"
- "What publications mention Variant Z?"
- "Where is Gene X expressed?" (requires TISSUE entity + EXPRESSED_IN)
- "What biological processes does Gene X participate in?" (requires BIOLOGICAL_PROCESS + PARTICIPATES_IN)

### Tier 2: Mechanistic Path Traversal

Multi-hop queries that follow causal chains. The core of the platform.

- "What is the mechanism chain from Variant X to Phenotype Y?"
  - Path: Variant →[LOSS_OF_FUNCTION]→ Gene →[PARTICIPATES_IN]→ Pathway →[UPSTREAM_OF]→ BiologicalProcess →[CAUSES]→ Phenotype
- "Does expression pattern match the phenotype?" (tissue concordance)
  - Path: Gene →[EXPRESSED_IN]→ Tissue; Phenotype →[ASSOCIATED_WITH]→ Tissue -- check overlap
- "What protein domain does this variant affect, and what function does that domain serve?"
  - Path: Variant →[LOCATED_IN]→ ProteinDomain →[PART_OF]→ Protein →[PARTICIPATES_IN]→ MolecularFunction
- "What other diseases share this molecular mechanism?"
  - Path: Disease A ←[CAUSES]← Mechanism →[CAUSES]→ Disease B

### Tier 3: Cross-Domain Hypothesis Generation

Queries that span biological domains and generate novel hypotheses. The differentiator.

- "Find drugs that target pathways disrupted by this variant" (drug repurposing)
  - Path: Variant →[LOF]→ Gene →[PARTICIPATES_IN]→ Pathway ←[TARGETS]← Drug
- "What model organisms have been used to study this gene?"
  - Path: Gene →[ASSOCIATED_WITH]→ ModelOrganism ←[MENTIONS]← Publication
- "Find biomarkers for this disease mechanism"
  - Path: Mechanism →[DOWNSTREAM_OF]→ Gene/Protein →[BIOMARKER_FOR]→ Disease
- "What variants sensitize patients to Drug X?"
  - Path: Variant →[SENSITIZES_TO]→ Drug
- "What genes compensate for this loss-of-function?"
  - Path: Gene A →[COMPENSATED_BY]→ Gene B

### Tier 4: Contradiction & Gap Detection

Meta-queries about the graph itself. Research intelligence.

- "Where do published papers contradict each other about Gene X?"
  - Detection: claims with conflicting polarity (`SUPPORT` vs `REFUTE`) for the same canonicalization key, including materially matching context participants
- "What connections are structurally implied but have no direct evidence?"
  - Detection: multi-hop paths exist but no direct relation or publication support
- "What gene-disease associations lack a mechanistic explanation?"
  - Detection: GENE →[ASSOCIATED_WITH]→ DISEASE exists, but no intermediate path through mechanism/pathway/process
- "What connections are supported by only a single source?" (fragility analysis)
  - Detection: relations with distinct_source_count = 1

---

## 11. Phased Rollout

Phases are defined by capability milestones, not calendar dates. Each phase unlocks a tier of query patterns.

### Phase 1: Foundation

**Milestone**: all entity types can participate in relations. Tier 1 queries work.

Entity types added:

- `TISSUE` (anatomy), `CELL_TYPE` (anatomy), `BIOLOGICAL_PROCESS` (general)

Relation types added:

- `LOCATED_IN`, `LOSS_OF_FUNCTION`, `GAIN_OF_FUNCTION`

Data sources:

- Complete HPO ontology ingestion (phenotype hierarchy and cross-references)
- Complete OMIM integration (direct, not just via MARRVEL)
- Seed ontology sources: UBERON (tissue), Cell Ontology (cell types), GO (BP, MF, CC)
- MONDO disease ontology: import hierarchy edges (is_a) and cross-reference edges (OMIM, DOID, MeSH, ICD) as loader/import relations, not just entity nodes
- Harden PubMed + ClinVar + MARRVEL extraction pipelines as primary evidence sources
- DrugBank: route drug-target, drug-enzyme, and drug-disease records through the claim pipeline to produce governed relation claims
- AlphaFold: route domain boundary predictions through the claim pipeline to produce PROTEIN_DOMAIN→PART_OF→PROTEIN claims
- Formalize the three connector families and remove connector-specific direct graph-write paths
- Activate all enabled sources during research-init (not just PubMed), so ClinVar, MARRVEL, MONDO, and others run as part of the initial research pass

Key deliverables:

- Fix 3 orphaned entity types (SYNDROME, PROTEIN_COMPLEX, MOLECULAR_FUNCTION) with constraints
- Seed BUILTIN constraints for all new entity + relation type combinations
- Expand synonym table to 60+ relation synonyms
- Implement claim-level polarity handling for negation, with participant-level polarity alias where needed
- Establish the typed qualifier registry for penetrance, frequency, population, organism, and related attributes
- Add `anatomy` domain context
- Seed TISSUE from UBERON, CELL_TYPE from Cell Ontology, BIOLOGICAL_PROCESS from GO:BP
- Every source produces edges: ontology loaders emit hierarchy + cross-reference edges with AI-generated evidence sentences; DrugBank and AlphaFold route records through the claim pipeline; no source is entity-only
- Every edge carries an AI-generated human-readable evidence sentence explaining what the connection means
- Cross-source research orchestrator: replaces the current PubMed-only research-init with an AI agent that coordinates all enabled sources in 3 discovery rounds, chasing new leads across sources
- Research brief: the orchestrator synthesizes all findings into a narrative document delivered as the first message in the onboarding thread, highlighting cross-source connections and gaps

**Queries unlocked**: gene expression tissue lookup, variant mechanism classification (LOF vs GOF), basic tissue-phenotype concordance, negated claim representation, all entity types queryable, cross-source discovery (drug targets for genes found in literature, disease classification for ClinVar conditions via MONDO hierarchy, structural domain analysis for variant impact).

### Phase 2: Density

**Milestone**: multi-hop mechanistic traversal works. Hybrid constraint enforcement is active. Tier 2 queries work.

Entity types added:

- `PROTEIN_DOMAIN` (genomics), `CELLULAR_COMPARTMENT` (anatomy)

Relation types added:

- `PREDISPOSES_TO`, `PHENOCOPY_OF`, `CO_OCCURS_WITH`, `COLOCALIZES_WITH`, `SUBSTRATE_OF`, `TRANSPORTS`, `MODULATES`

Data sources:

- DrugBank integration for drug entities, targets, and mechanisms of action
- AlphaFold/UniProt domain ingestion for PROTEIN_DOMAIN entities
- PDF upload extraction pipeline (user-uploaded papers processed through same LLM extraction)

Key deliverables:

- Activate hybrid constraint enforcement (`FORBIDDEN`, `EXPECTED`, `REVIEW_ONLY`)
- Implement constraint provenance tiers (`BUILTIN`, `TRUSTED`, `DISCOVERED`)
- Expand synonym table to 200+ relation synonyms
- Automated synonym harvesting pipeline active
- AlphaFold/UniProt domain ingestion for PROTEIN_DOMAIN entities
- Document conditionality and digenic claim patterns in extraction agent prompts

**Queries unlocked**: multi-hop mechanistic path traversal, protein domain impact analysis, subcellular localization context, risk vs. causation distinction, phenocopy discovery, variant-to-domain-to-function chains.

### Phase 3: Reasoning

**Milestone**: cross-domain hypothesis generation works. Tier 3 queries work.

Entity types added:

- `MODEL_ORGANISM` (translational), `CLINICAL_TRIAL` (translational)

Relation types added:

- `SENSITIZES_TO`, `COMPENSATED_BY`

Data sources:

- MGI (mouse genome informatics) for model organism phenotypes and gene expression
- ZFIN (zebrafish information network) for model organism phenotypes
- ClinicalTrials.gov for registered clinical trials

Key deliverables:

- Drug repurposing query service
- Model organism evidence ingestion (MGI, ZFIN sources)
- Clinical trial linkage (ClinicalTrials.gov)
- Hypothesis generation uses penetrance, conditionality, and multi-hop traversal
- Add `translational` domain context

**Queries unlocked**: drug repurposing traversal, model organism evidence integration, clinical trial linkage, drug sensitivity prediction, functional compensation discovery.

### Phase 4: Discovery Engine

**Milestone**: meta-queries about the graph itself work. Tier 4 queries work. Platform demonstrated on multiple use cases beyond diagnosis.

No new entity or relation types. Focus on density, quality, and query capability.

Key deliverables:

- Contradiction detection service
- Gap analysis service (structurally implied but unattested connections)
- Single-source fragility detection
- Mechanistic explanation gap detection
- Platform validated across diagnosis, drug repurposing, and biomarker discovery use cases

**Queries unlocked**: contradiction detection, gap analysis, fragility analysis, mechanistic explanation gaps.

---

## 12. Success Metrics

Measured by graph capability, not calendar dates or single-disease outcomes.

### Graph Health


| Metric                                                            | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
| ----------------------------------------------------------------- | ------- | ------- | ------- | ------- |
| Entity types with active constraints                              | 18/18   | 18/18   | 18/18   | 18/18   |
| Relation types with >= 1 active use                               | 35/35   | 35/35   | 35/35   | 35/35   |
| Forbidden triples defined                                         | 32      | 32      | refined | mature  |
| Relation synonyms                                                 | 207     | 207     | 207+    | 207+    |
| Entity aliases                                                    | 500+    | 2000+   | 3000+   | 5000+   |
| Graph density (edges/node, per space)                             | 3+      | 5+      | 7+      | 8+      |
| Rejected fact rate (% of extracted facts rejected by constraints) | < 30%   | < 10%   | < 5%    | < 5%    |

*Note: As of April 2026, the entity-types and relation-types rows are constant across all four phases because the biomedical built-ins are now seeded in full from the start (see `graph_domain_config.py`) rather than introduced incrementally per phase. The original rollout numbers (14/14 → 18/18, 26/26 → 35/35) are preserved in git history.*


### Query Capability


| Metric                               | Phase 1  | Phase 2  | Phase 3  | Phase 4  |
| ------------------------------------ | -------- | -------- | -------- | -------- |
| Tier 1 (association lookup)          | complete | complete | complete | complete |
| Tier 2 (mechanistic traversal)       | partial  | complete | complete | complete |
| Tier 3 (cross-domain hypothesis)     | --       | partial  | complete | complete |
| Tier 4 (contradiction/gap detection) | --       | --       | partial  | complete |
| Max useful traversal depth (hops)    | 2        | 4        | 5+       | 5+       |


### Discovery Value


| Metric                       | Description                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Novel connections per space  | Connections not present in any single ingested paper, only discoverable through multi-hop traversal           |
| Contradiction pairs surfaced | Entity pairs with conflicting evidence from different publications                                            |
| Hypothesis acceptance rate   | % of AI-generated hypotheses promoted to validated knowledge after human review                               |
| Cross-use-case validation    | Platform demonstrated on 3+ distinct reasoning modes (diagnosis, drug repurposing, biomarker discovery, etc.) |


---

## 13. Verification Criteria

System invariants that must hold at all times. These are testable properties, not aspirations.

### Graph integrity

- **No orphan canonical relations**: every canonical relation has at least one linked claim. A relation with zero claims is a data corruption bug.
- **No approved relation without provenance**: every APPROVED canonical relation traces back to at least one source document via its claim evidence chain.
- **Idempotent projection**: re-projecting the same claim onto the same canonical relation produces no change in aggregate confidence, source count, or curation status.
- **Forbidden triples are always blocked**: regardless of governance mode, evidence quality, or confidence level, a forbidden triple never enters the graph. Verified by constraint-check-before-write in the persistence layer.

### Evidence integrity

- **Duplicate source ingestion does not inflate confidence**: evidence from the same underlying source (e.g., ClinVar ingested directly and via MARRVEL) counts once in aggregate confidence. Verified by source-family deduplication on a normalized upstream provenance key or `source_family_id`, not raw `(source_document_id, source_type)` alone.
- **Computational hypotheses do not self-reinforce**: computational hypotheses are excluded from canonical projection and from traversal sets used by inference agents until grounded by source-backed evidence. Verified by assertion-class filters in the projection and graph search services.
- **Shadow mode guarantees zero writes**: when `shadow_mode: true`, no claims, relations, evidence rows, or dictionary entries are created or modified. Verified by transaction rollback in shadow mode pipeline paths.

### Governance integrity

- **Agent contracts cannot bypass governance**: every claim-to-relation projection passes through the governance service. There is no code path from agent output to canonical relation that skips the `GovernanceDecision` check.
- **HUMAN_IN_LOOP blocks auto-promotion**: in HUMAN_IN_LOOP mode, no canonical relation transitions from DRAFT to APPROVED without a `reviewed_by` user ID and `reviewed_at` timestamp.
- **Retraction is always available**: an APPROVED relation can be retracted at any time. Retraction does not delete data -- it changes curation status and preserves the full audit trail.

### Query integrity

- **Contradiction detection requires context matching**: two claims only contradict if they share the same canonicalization key (including context participants). A brain-specific positive claim and a liver-specific negative claim are not contradictions.
- **Inverse relations are never double-stored**: for every directional relation type, only the canonical direction is persisted. The inverse is derived at query time. Verified by a unique constraint on `(source_entity_id, relation_type, target_entity_id, canonicalization_key_hash)`.
- **Symmetric relations use deterministic ordering**: for symmetric relations, the entity with the lower ID is always stored as the source. Verified by a check constraint or normalization in the persistence layer.

