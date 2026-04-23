# Artana Resource Library - Current Project Status

**Status date:** April 23, 2026 (updated for extracted-repo service topology)

## Purpose

Artana is currently a biomedical, evidence-first knowledge graph platform built around a domain-agnostic kernel. The intended product shape in [plan.md](./plan.md) is a governed graph where:

- claims are the scientific assertion ledger
- canonical relations are derived graph assertions
- agents propose but governance decides
- research spaces remain the isolation boundary
- Postgres is the system of record, with traversal/query layers built on top

This document summarizes what is implemented now, what only partially matches the current plan, and what still remains planned.

## Executive Summary

The repository already contains the core pieces of the planned graph platform:

- a standalone graph service
- a claim-first evidence model
- governance settings and auto-promotion policy
- a durable background pipeline with queue claiming and heartbeats
- extraction, graph connection, graph search, content enrichment, query generation, extraction policy, and hypothesis-generation services
- a special bootstrap runtime for research initialization

As of April 12, 2026, all four phases of the plan are substantively implemented, with the remaining work split into rollout, measured import follow-through, and deferred Phase 5 strategy:

- **Phase 1 (Foundation)**: knowledge model finalized (35/35 relation types, 18 entity types, 5 domain contexts including anatomy and translational, 208 relation synonyms, 106 relation constraints, 32 forbidden triples with wildcard target support); proposal-to-relation projection landed (promoted proposals route through `POST /relations` and create canonical relations atomically); edge production gaps closed; AI-generated ontology evidence sentences shipped with a per-namespace rollout vector (`ARTANA_ONTOLOGY_LLM_EVIDENCE_SENTENCES_HP=1` etc.) and per-namespace observability stats so the rollout can be validated from prod logs without enabling the harness blindly. Default OFF, awaiting flag flip in Cloud Run.
- **Phase 2 (Density)**: cross-source orchestration with driven Round 2 (PubMed gene mention extraction drives enrichment queries) + theme-organized brief; cross-source overlap detection; brief delivery as the first onboarding message; deterministic alias harvesting exists for HPO, UniProt, DrugBank, and HGNC, with PR #337 adding normalized backend-derived alias-yield reporting.
- **Phase 3 (Reasoning)**: ClinicalTrials.gov, MGI (mouse), and ZFIN (zebrafish) now have research-init enrichment and extraction processing in the extracted evidence API. MGI and ZFIN share service-local Alliance gateway code in `services/artana_evidence_api/alliance_gene_gateways.py`.
- **Phase 4 (Discovery)**: all four Tier 4 discovery queries from the plan exposed as HTTP endpoints — contradiction detection, single-source fragility, reachability gap analysis, and mechanistic explanation gap detection (which now accepts a `max_hops` query param 2..4 with bridge-path response field, extending the original 2-hop bridge test to find longer mechanism chains via a constrained BFS with visited-node cap and early termination).
- **Performance**: MONDO batch entity creation endpoint added (capped at 500 rows/request, atomic commit). `OntologyIngestionService` now runs a two-pass loop that turns ~26k single POSTs into ~130 batch POSTs, eliminating the per-entity HTTP + commit overhead that dominated load time.

Remaining work is **not another model-build phase**. The live follow-up is:

- run real HPO/UniProt/DrugBank/HGNC imports, then use `scripts/measure_alias_yield_imports.py` to record measured backend-derived alias-yield counts;
- complete operational rollout tasks: migration 026 deploy, `DRUGBANK_API_KEY` provisioning, source metadata backfill, and per-ontology AI evidence sentence rollout;
- keep whole-space gap discovery, the full AI orchestrator, and Phase 5 definition as explicit deferred strategic work.

## Current Architecture

### Service topology

The current extracted repo contains two service packages:

- `services/artana_evidence_db`: graph service and graph-owned schema/API
- `services/artana_evidence_api`: harness, bootstrap, proposal, and workflow runtimes

The monorepo UI/runtime packages are not present in this checkout. Router
ownership for the extracted backend surfaces lives in the service-local packages.

### Identity and tenancy

The evidence API uses a local identity boundary for low-friction testing:

- `services/artana_evidence_api/identity/contracts.py`
- `services/artana_evidence_api/identity/local_gateway.py`

Users, API keys, spaces, memberships, and space-access decisions should flow
through this gateway. The current implementation is SQL-backed and local to the
Evidence API, with `X-Artana-Key` as the tester-friendly access path. A future
standalone identity service should replace the gateway adapter rather than
rewriting workflow code.

### Core graph model

The graph service already implements the two-layer model described in the plan:

- **claims** are persisted separately from canonical relations
- **canonical relations** are persisted with curation status, confidence, and evidence
- projection/materialization from claims to canonical relations exists

At a high level, the current implementation supports:

- relation claims
- claim participants
- claim evidence
- canonical relations
- relation evidence
- provenance
- curation lifecycle on canonical relations

### Governance and policy

The current codebase already supports major governance features from the plan:

- `HUMAN_IN_LOOP` and `FULL_AUTO` relation governance modes
- space-scoped policy settings
- review thresholds and relation-specific overrides
- auto-approve and require-review toggles
- distinct-source and aggregate-confidence thresholds
- conflicting-evidence checks
- evidence-tier checks
- concept creation policy and concept matching mode

### Durable pipeline orchestration

The general background pipeline is implemented and matches the plan's high-level stage order:

```text
Ingestion -> Enrichment -> Extraction -> Graph
```

The system includes:

- durable queueing on ingestion jobs
- worker claiming
- heartbeats
- retry metadata
- pipeline event logging
- stage summaries and progress tracking

### Connector architecture

The repo is closest to a three-family connector model:

- literature connectors
- structured database connectors
- ontology loaders

The target architecture is stronger than just "three families." The intended end state is:

- source-specific fetch and normalization by connector family
- deterministic grounding as Tier 1 for entities, identifiers, and structured source facts
- LLM-mediated Tier 2 for every new relation claim
- one governed claim path into canonical graph truth

This is directionally strong because source-specific complexity stays at the fetch and normalization edge while the kernel, claim model, and governance rules stay shared.

The current implementation is now converged on this target for graph-truth writes:

- steady-state PubMed ingestion and pipeline-backed source ingestion fit the shared-kernel direction
- bootstrap runtimes are documented in `docs/research_init_architecture.md` and produce proposal drafts that flow through the same governed write path as steady-state ingestion
- ClinVar, MARRVEL, DrugBank, AlphaFold, and the translational sources (ClinicalTrials.gov, MGI, ZFIN) all follow the Tier 1 deterministic grounding → Tier 2 AI-mediated claim generation pattern in the shared extraction runtime
- MARRVEL's direct entity-seeding route was retired in favor of the shared extraction/runtime path with deterministic grounding bridged into the shared AI runtime
- ontology loaders (MONDO, HPO, UBERON, Cell Ontology, Gene Ontology) are a first-class loader family with shared contracts and now share a batched entity-creation fast path (P7.1) for large ontologies
- HGNC is intentionally scoped as a deterministic alias-only source unless a future PR adds governed Tier 2 relation-claim extraction for it.

### Bootstrap/runtime workflows

The repository also contains runtime-specific workflows that are not described directly in `plan.md`, most importantly:

- `research_init_runtime`
- `research_bootstrap_runtime`
- hypothesis-generation runtime
- graph-search and graph-connection harness runtimes

These are real product flows, but they are not the same thing as the general durable pipeline.

## Status Against `docs/plan.md`

### Strong Alignment

#### Evidence-first graph direction

The following are already true in code and aligned with the plan:

- the graph is treated as the system of record
- claims and canonical relations are distinct persistence layers
- canonical relations have curation lifecycle state
- provenance and evidence are first-class
- governance stands between agent output and canonical graph promotion

#### Agent boundary

The plan says agents propose and governance decides. That is broadly true in the current implementation:

- extraction and enrichment flows produce drafts, claims, or reviewable outputs
- bootstrap and MARRVEL enrichment create proposal drafts rather than directly asserting canonical truth
- shadow/fallback/escalation concepts already exist in agent contracts and services

#### Pipeline fundamentals

The plan's durable pipeline goals are already represented:

- stage-based execution
- queue claiming
- heartbeats
- event logging
- resumable/retryable job metadata

#### Source coverage

All planned Phase 1, Phase 2, and Phase 3 sources are implemented:

- PubMed: implemented (literature connector)
- ClinVar: implemented (structured database connector with Tier 1 + Tier 2)
- MARRVEL: implemented (structured database connector)
- UniProt: implemented (Tier 1 grounding with 4 fact families: protein identity, molecular function, domain/location, publication linkage)
- DrugBank: implemented (full connector with API client, Tier 1 grounding, Tier 2 claim stubs)
- AlphaFold: implemented (full connector with API client, domain boundary parsing, claim stubs)
- Ontology loaders: implemented (MONDO, HPO, UBERON, Cell Ontology, Gene Ontology)
- ClinicalTrials.gov: implemented (Phase 3 translational; v2 REST API client, Tier 1 grounding, defer-to-AI Tier 2)
- MGI (mouse): implemented (Phase 3 translational; Alliance of Genome Resources REST API filtered to *Mus musculus*)
- ZFIN (zebrafish): implemented (Phase 3 translational; same Alliance API filtered to *Danio rerio*, with extra `expression_terms` extraction for zebrafish anatomy expression patterns)
- HGNC: implemented as the 15th deterministic alias-only source/loader for approved human gene nomenclature aliases

#### Kernel-first connector direction

The strongest architectural decision around sources is already true in broad terms:

- the graph kernel is source-agnostic
- governance is intended to sit between source output and canonical graph projection
- literature and structured sources can feed the same claim/canonical relation model

This is the right foundation for future connectors even though some current runtimes still bypass the ideal path.

### Partial Alignment / Known Gaps

#### ~~Connector architecture target is clear, but the two-tier claim path is not yet unified~~ Connector architecture is converged

All connector families now follow the target architecture for relation truth:

- **Literature connectors** (PubMed): AI-heavy extraction with relevance gating
- **Structured database connectors** (ClinVar, MARRVEL, UniProt, DrugBank): Tier 1 deterministic grounding → Tier 2 AI-mediated claim generation → governed write path
- **Protein structure connectors** (AlphaFold): Tier 1 domain boundary parsing → Tier 2 claim stubs → governed write path
- **Ontology loaders** (HPO, UBERON, Cell Ontology, Gene Ontology): first-class loader family with shared contracts
- **Alias-only loaders** (HGNC): deterministic identity alias persistence only

The scheduler factory now covers the original 14 source families, and HGNC is registered as a deterministic alias-only source. DrugBank and AlphaFold have real HTTP API clients (BaseIngestor with rate limiting, retry, and error handling). UniProt has Tier 1 grounding with 4 fact families.

#### ~~Entity vocabulary is partial, not complete~~ Entity vocabulary is complete

All **18** planned biomedical entity types are seeded as built-ins across **5** domain contexts (general, clinical, genomics, anatomy, translational), with **106** relation constraints, **208** relation synonyms, and **32** forbidden triples (including wildcard target support for cross-cutting prohibitions).

#### ~~Relation model is broader than the extraction whitelist~~ Extraction whitelist matches the full relation model

All **35** seeded relation types are now in the extraction whitelist (core causal, extended scientific, document governance categories).

#### ~~Canonical projection is less context-aware than the plan~~ Context-aware canonicalization is implemented

Canonical relation uniqueness includes a `canonicalization_fingerprint` derived from scoping qualifiers and CONTEXT participant anchors. A qualifier registry defines scoping vs descriptive qualifiers.

#### ~~Assertion classes are not yet first-class schema concepts~~ Assertion classes are explicit

The claim model carries an explicit `assertion_class` field (SOURCE_BACKED, CURATED, COMPUTATIONAL). All creation paths set it. Projection, search, and auto-promotion check it directly.

#### ~~Claim participant roles are not fully aligned~~ Claim participant roles are aligned

The participant role vocabulary includes OUTCOME. A qualifier registry with validation is wired into the participant write path.

#### ~~Computational promotion semantics still need tightening~~ Computational promotion boundary is enforced

Computational-only evidence is categorically blocked from auto-promotion. REVIEW_ONLY constraints also block auto-promotion.

## Current Execution Paths

### General durable pipeline

The general orchestration service represents the main background pipeline:

```text
Ingestion -> Enrichment -> Extraction -> Graph
```

This is the best description of the planned steady-state ingestion system.

### Research initialization bootstrap

`research_init_runtime` is a separate, special-purpose bootstrap runtime. Its observed order is closer to:

```text
PubMed discovery -> document ingestion -> document extraction -> bootstrap
```

MARRVEL enrichment is prepared alongside the bootstrap phase and applied afterward as proposal drafts.

This is not a contradiction of the general pipeline. It is a different workflow for bootstrapping a new space.

### MARRVEL gene inference fallback

The plan does not describe this explicitly, but the runtime currently includes a targeted MARRVEL gene-inference fallback path:

- try to resolve candidate genes from the graph
- if needed, infer MARRVEL gene labels from the research objective
- fetch MARRVEL associations
- stage proposals for review

This is real implementation detail and should be treated as part of the current runtime behavior, not the canonical description of the whole platform.

## UI Status

This extracted checkout does not include an authenticated UI package. The
backend workflow surfaces are available through `services/artana_evidence_api`
HTTP routes and generated OpenAPI docs. Any frontend status should be checked in
the UI-owning repository or monorepo snapshot, not inferred from this repo.

## Security and Compliance Status

The codebase includes substantial security-oriented infrastructure, including:

- audit-related services and docs
- PHI encryption support
- governance and access policy wiring
- space-scoped controls

This document does **not** re-audit HIPAA readiness. Security posture should be treated as "substantial controls exist, but compliance readiness must still be verified separately."

## Recommended Next Steps

The original "Recommended Next Steps" list (8 items as of April 5) is now complete. Items #1-#6 are landed; items #7-#8 are docs/cleanup tasks that have been substantively addressed (`docs/research_init_architecture.md` covers the bootstrap flows; service boundaries are consolidated and `src/routes` references have been removed from the operational architecture description above).

What actually remains, as of April 12, 2026 (full detail in [`docs/remaining_work_priorities.md`](./remaining_work_priorities.md)):

1. **Measured alias-yield imports.** PR #337 added normalized backend-derived alias-yield reporting for HPO, UniProt, DrugBank, and HGNC. The measurement follow-up adds `scripts/measure_alias_yield_imports.py`, which reads completed ingestion-job metadata and fails closed if any required source is missing. The next data follow-up is to run real imports in an approved environment, run the report command, and update this file with measured `alias_candidates_count`, optional `aliases_registered`, `aliases_persisted`, `aliases_skipped`, `alias_entities_touched`, and `alias_errors`.

2. **Ops: run migration 026 on staging/prod.** Already merged on `main` (commit `451881bf`); see `docs/migration_026_deployment_notes.md`. Online-safe DDL with automatic backfill via server-side defaults.

3. **Ops: provision `DRUGBANK_API_KEY`.** Free for academic use. The Cloud Run sync-script wiring landed in PR #321 — `scripts/deploy/sync_artana_evidence_api_cloud_run_runtime_config.sh` now conditionally provisions the secret when `DRUGBANK_API_KEY_SECRET_NAME` is exported in the deploy shell, mirroring the existing `OPENAI_API_KEY_SECRET_NAME` block. Remaining steps: create the secret in GCP Secret Manager, export `DRUGBANK_API_KEY_SECRET_NAME=<secret-name>` before running the sync, then re-run. Without it, DrugBank enrichment continues to skip gracefully at runtime.

4. **Ops: backfill historical orphan claims/proposals with `source_document_ref`.** This is data maintenance, not a new semantic model.

5. **Ops: roll out AI ontology evidence sentences per ontology.** Per-namespace flags and per-namespace observability stats landed in PR #322. Recommended sequence: enable `ARTANA_ONTOLOGY_LLM_EVIDENCE_SENTENCES_HP=1` first (HPO is small and well-defined), watch the next ontology load for the `AI evidence sentence stats for ontology=HP: requested=N generated=N fallback=N avg_sentence_chars=N` log line to validate the harness is working, then enable `_UBERON`, `_GO`, `_CL` one at a time, with `_MONDO` last (~26k terms; benefits from waiting until the prior 4 have validated the harness behavior at smaller scale). Feature defaults OFF; failures fall back to the deterministic template sentence.

6. **Deferred Phase 4 follow-up: whole-space gap discovery.** The current `/relations/reachability-gaps` endpoint requires a `seed_entity_id`. A whole-space variant ("show me every implied-but-unattested edge in the whole space") would need a materialized reachability projection because computing it on-demand is O(N²) on entity count. Deferred until usage data justifies the work — the seed-based version covers most workflows. (Deeper mechanism chains, the other previously-listed P4 follow-up, shipped in PR #321 — see Phase 4 description above.)

7. **Deferred: full AI orchestrator agent.** Replace the deterministic Phase 2/2b/3 structure with an agent that reads results and decides which source to query next. Significant rewrite; the current driven-Round-2 + chase-rounds combination already covers the main intelligence gap.

8. **Phase 5 conversation.** `plan.md` does not go past Phase 4. With Phases 1-4 substantively implemented, the next significant engineering work needs a strategic decision about which Phase 5 theme to pursue. Candidates: active learning loop (extraction priors / synonym auto-promotion / constraint refinement from review decisions), multi-space synthesis (connect findings across research spaces), patient-data integration (real VCF / phenotype data), reasoning explainability UI (surface BFS paths and gap analyses in the inbox), or the deferred AI orchestrator from item 7 above.

## Bottom Line

Artana has substantively implemented the `docs/plan.md` Phase 1-4 platform scope. The repository contains a working graph platform with claims, canonical relations, governance, durable pipelines, extraction services, and bootstrap workflows — and now also contains steady-state translational source coverage, deterministic HGNC alias loading, normalized alias-yield reporting, and the full Phase 4 discovery query surface.

The project's current status is best described as:

- **graph foundation implemented**
- **governance and pipeline implemented**
- **kernel architecture strong; connector paths converged on the two-tier (Tier 1 grounding + Tier 2 AI claim generation) governed write boundary**
- **biomedical domain profile complete** (18/18 entity types, 35/35 relation types, 5 domain contexts, 208 synonyms, 106 constraints, 32 forbidden triples)
- **source coverage precisely stated**: 14 historical source families now have scheduler/research-init coverage after PR #331 added ClinicalTrials.gov, MGI, and ZFIN steady-state ingestion; PR #336 added HGNC as a 15th deterministic alias-only source
- **alias-yield reporting implemented** for HPO, UniProt, DrugBank, and HGNC via backend-derived metrics; the measurement report command now makes production/staging count capture reproducible, but measured counts still require real import runs
- **all four Phase 4 discovery queries exposed as HTTP endpoints**
- **performance hardened**: MONDO loading dropped from ~10 min (26k single POSTs) to under a minute (130 batch POSTs) via the new `/entities/batch` endpoint
- **bootstrap/runtime workflows implemented and documented** in `docs/research_init_architecture.md`

What remains is a small, explicit set of follow-ups: run real alias-yield imports and record measured counts with `scripts/measure_alias_yield_imports.py`; complete operational rollout work (migration 026 deploy, DrugBank API key provisioning, source metadata backfill, and per-ontology AI sentence rollout); keep whole-space gap discovery and the full AI orchestrator deferred; and decide what Phase 5 should be, since `plan.md` does not go past Phase 4.

## Implementation Completion Summary

### P0 -- Truth-Preservation Foundations (completed)

- **P0.1 Assertion classes**: Explicit `assertion_class` field (SOURCE_BACKED, CURATED, COMPUTATIONAL) on every claim; projection and governance check it directly.
- **P0.2 Claim participant roles**: Full role vocabulary (SUBJECT, OBJECT, CONTEXT, QUALIFIER, MODIFIER, OUTCOME) with qualifier registry and validation on the write path.
- **P0.3 Computational promotion boundary**: Computational-only evidence categorically blocked from auto-promotion; legacy computational threshold fields removed from policy.
- **P0.4 Context-aware canonicalization**: `canonicalization_fingerprint` derived from scoping qualifiers (tissue, organism, population, developmental stage, sex) and CONTEXT participants; qualifier registry distinguishes scoping vs descriptive qualifiers.

### P1 -- Biomedical Domain Profile (completed)

- **P1.1 Entity vocabulary**: All 18 planned entity types seeded as built-ins across 5 domain contexts (general, clinical, genomics, anatomy, translational).
- **P1.2 Relation model**: All 35 seeded relation types match the builtin catalog (11 core causal, 16 extended scientific, 8 document governance); document-extraction whitelist covers the full vocabulary.
- **P1.3 Relation synonyms**: 208 synonyms defined for normalization and LLM extraction.
- **P1.4 Constraint profiles**: EXPECTED, ALLOWED, REVIEW_ONLY, and FORBIDDEN validation profiles with 106 total constraints enforced on claim creation, including 32 FORBIDDEN triples with wildcard target support.

### P2 -- Connector Convergence (completed)

- **P2.1 Ontology loader family**: HPO, UBERON, Cell Ontology, and Gene Ontology have first-class loader contracts, scheduler wiring, and catalog exposure.
- **P2.2 ClinVar conformance**: Tier 1 grounding through Tier 2 extraction into the shared governed claim path with conformance coverage.
- **P2.3 MARRVEL convergence**: Direct entity-seeding route retired; MARRVEL uses the shared extraction/runtime path with deterministic grounding bridged into the shared AI runtime.
- **P2.4 Artana-kernel LLM boundary**: Adapter-level generation routed through kernel-managed model-port boundaries; architecture enforcement prevents direct provider imports.

### P3 -- Runtime and Pipeline Hardening (completed)

- **P3.1 Bootstrap runtime architecture**: Documented in `docs/research_init_architecture.md` covering research_init, research_bootstrap, MARRVEL enrichment, and the convergence decision.
- **P3.2 Research space lifecycle**: Space creation, graph-runtime propagation, onboarding thread projection, and harness proposal staging verified end-to-end on the supported UI/API create path.
- **P3.3 Observation persistence**: `research_init_runtime` persists shared `source_documents` and `observations` before governed claim promotion; bridged source documents created during research init.
- **P3.4 Proposal queue surfacing**: Governed proposal queues surfaced through the canonical Proposals experience rather than hidden child runs.
- **P3.5 Evidence quality semantics**: Support-unit collapsing by source family key, diminishing returns aggregation formula, computational evidence excluded from support_confidence, refute evidence tracked separately, distinct_source_family_count on canonical relations.
- **P3.6 Conflict detection**: Contradiction detection via mixed SUPPORT/REFUTE claim polarity linked to the same canonical relation; auto-promotion blocked when conflicting evidence present.

### P4 -- Discovery Services (completed)

All four Tier 4 discovery queries from the plan are exposed as HTTP endpoints on the graph service:

- **P4.1 Contradiction detection**: `GET /v1/spaces/{space_id}/relations/conflicts` returns `KernelRelationConflictSummary` rows with support/refute counts and confidences for relations with mixed-polarity claims.
- **P4.2 Single-source fragility detection**: `GET /v1/spaces/{space_id}/relations?fragile_only=true` (or `max_source_family_count=N`) filters canonical relations by `distinct_source_family_count` to surface relations supported by N or fewer independent source families. Implemented at the repository level so existing pagination, evidence loading, and authorization apply.
- **P4.3 Reachability gap analysis**: `GET /v1/spaces/{space_id}/relations/reachability-gaps?seed_entity_id={uuid}&max_path_length=N` finds entities reachable from a seed via multi-hop paths (length 2-5) but with no direct edge — the "structurally implied but unattested" connections. Reuses the existing `find_neighborhood()` BFS, no new traversal code. Each gap row carries an optional `bridge_entity_id` so the caller can walk a concrete path.
- **P4.4 Mechanistic explanation gap detection**: `GET /v1/spaces/{space_id}/relations/mechanistic-gaps?source_entity_type=GENE&target_entity_type=DISEASE&max_hops=N` is the inverse of reachability gap — finds direct relations (default `ASSOCIATED_WITH`) where no entity of an intermediate "mechanism" type (default: BIOLOGICAL_PROCESS, SIGNALING_PATHWAY, MOLECULAR_FUNCTION, PROTEIN_DOMAIN) bridges the two endpoints. Surfaces the "we noticed a correlation but can't explain why" candidates from the plan. The `max_hops` query param (default 2, ge=2, le=4, shipped in PR #321) drives a constrained BFS over mechanism-typed neighbors so callers can find longer chains like `GENE → KINASE → PROTEIN → PROCESS → DISEASE` that the original 2-hop test missed. Performance guardrails: per-BFS visited-node cap (5000), early termination on first path found, depth cap of `max_hops - 1` intermediates. The response includes an additive `bridge_path: list[UUID]` field carrying the ordered chain of intermediate entity ids.

### P5 -- Phase 3 Translational Sources (completed)

All three translational sources are shipped end-to-end (gateway + ingestor + extraction processor + research-init enrichment helper + Phase 2b runtime wiring + wizard toggle + tests):

- **P5.1 ClinicalTrials.gov**: `SourceType.CLINICAL_TRIALS`, `run_clinicaltrials_enrichment`, full v2 REST API client. Emits `DRUG → TREATS → DISEASE` proposals when interventions are drugs and `CLINICAL_TRIAL → TARGETS → DISEASE` otherwise.
- **P5.2 MGI (Mouse Genome Informatics)**: `SourceType.MGI`, `run_mgi_enrichment`, Alliance of Genome Resources REST API client filtered to `Mus musculus`. Emits `GENE → ASSOCIATED_WITH → PHENOTYPE` (mouse model phenotypes) and `GENE → CAUSES → DISEASE` (disease associations from mouse models).
- **P5.3 ZFIN (Zebrafish Information Network)**: `SourceType.ZFIN`, `run_zfin_enrichment`, same Alliance API client filtered to `Danio rerio`. Adds `_extract_expression_terms` to capture zebrafish anatomy expression patterns and emits `GENE → EXPRESSED_IN → TISSUE` proposals on top of the phenotype/disease ones.
- **P5.4 Shared Alliance Genome gateway**: `services/artana_evidence_api/alliance_gene_gateways.py` consolidates the duplicated MGI/ZFIN fetch path into a service-local `_AllianceGeneSourceGateway` base plus `MGISourceGateway` and `ZFINSourceGateway` specializations. Future model-organism sources should extend that service-local gateway pattern rather than resurrecting the removed top-level `src/` ingestion package.

### P6 -- Cross-Source Orchestration and Brief Delivery (completed)

- **P6.1 Driven Round 2**: enrichment sources (ClinVar, DrugBank, AlphaFold, MARRVEL) now query for entity mentions extracted from PubMed abstracts (`extract_gene_mentions_from_text` with stopword filtering), not just user seed terms. The MGI/ZFIN/ClinicalTrials.gov enrichment helpers participate in this loop via the same `_extract_likely_gene_symbols` filter.
- **P6.2 Cross-source overlap detection**: `compute_cross_source_overlaps()` finds entities mentioned by 2+ sources, surfaced as concrete connection candidates in the brief.
- **P6.3 Theme-organized brief**: LLM prompt restructured to organize findings by theme (mechanism chains, drug-target, variant impact) instead of per-source counts; grounds the LLM in real overlap candidates.
- **P6.4 Brief generation for onboarding delivery**: the evidence API can generate the theme-organized research brief used by onboarding flows; UI/inbox delivery code is outside this extracted checkout.

### P7 -- Performance and Polish (completed)

- **P7.1 MONDO batch entity creation**: New `POST /v1/spaces/{space_id}/entities/batch` endpoint (`KernelEntityBatchCreateRequest` / `KernelEntityBatchCreateResponse`, capped at 500 entities/request) processes a chunk in a single transaction with the same identifier dedup, alias collision, and rollback semantics as the existing single-entity path. `OntologyIngestionService` now runs in two passes: bulk-upsert all non-obsolete terms in 200-row chunks via the writer's `upsert_terms_batch()` method, then per-term aliases/hierarchy/xref edges using the cached IDs. Per-chunk fallback to per-term `upsert_term` so a single bad term doesn't abort the load. For MONDO at 26k terms this turns ~26k single POSTs into ~130 batch POSTs — eliminating the per-entity HTTP + commit overhead that dominated load time. The same speedup applies to HPO/UBERON/GO/Cell Ontology loaders.
- **P7.2 AI-generated ontology evidence sentences**: `GraphOntologyEntityWriter` now accepts an optional `EvidenceSentenceHarnessPort`. When an AI-evidence flag is set, IS_A hierarchy edges get AI-generated evidence sentences grounded in the parsed OBO definitions and synonyms (1-3 sentences via the existing Artana evidence-sentence harness). Results are cached per `(child_id, parent_id)` for one load. Any harness failure (timeout, rate limit, validation mismatch, too-short output) silently falls back to the existing template sentence. Wired in both construction sites (scheduler factory and `research_init_runtime` MONDO background loader). Defaults OFF. **Per-namespace rollout vector** (PR #322): in addition to the original global `ARTANA_ONTOLOGY_LLM_EVIDENCE_SENTENCES=1` flag (back-compat preserved), the writer now reads per-namespace flags `ARTANA_ONTOLOGY_LLM_EVIDENCE_SENTENCES_HP=1`, `_MONDO=1`, `_UBERON=1`, `_GO=1`, `_CL=1` so each ontology can be enabled independently. Recommended sequence: HPO → UBERON → GO → CL → MONDO. **Per-namespace observability**: the writer tracks per-namespace counters (`requested`, `generated`, `fallback`, `cache_hit`, `total_sentence_chars`) exposed via `get_ai_sentence_stats()`, and both wiring sites log a one-line summary at the end of every ontology load so the rollout can be validated from prod logs without enabling the harness blindly.
- **P7.3 Proposal-to-relation projection**: Promoted proposals now route through `POST /relations` (not `POST /claims`), creating a RESOLVED+SUPPORT claim with participants, evidence, and a materialized canonical relation in a single transaction. All four call sites (proposals router, chat router, supervisor runs, claim curation runtime) updated. Backward compatible — `graph_claim_id` key preserved.
- **P7.4 Edge production gaps closed**: DrugBank and AlphaFold extraction processors now follow the ClinVar pattern (return `status=skipped` with `ai_required=True` and structured Tier 1 grounding in metadata, so the AI extraction pipeline handles Tier 2 relation generation). Ontology xref persistence implemented: `persist_xref_edge()` parses cross-reference strings (`OMIM:125853`, `DOID:9352`) and stores them as entity identifiers for cross-source entity resolution.
