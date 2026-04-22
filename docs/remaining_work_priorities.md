# Artana Remaining Work Priorities

**Status date:** April 12, 2026

This document supersedes the earlier "ops only" framing. The platform is broadly functional and much of `docs/plan.md` is implemented, but the code review of `docs/plan.md` and `docs/project_status.md` found several real remaining engineering items. The most important remaining gaps are now measured alias-yield follow-through, small rollout operations, and a deferred Phase 5 strategy decision.

## Current Verified Baseline

### Core platform that is substantially delivered

- **Graph service topology:** `services/artana_evidence_db/app.py` wires the standalone graph service with claims, entities, relations, graph views, observations, provenance, dictionary, operations, and search routers.
- **Harness/API topology:** `services/artana_evidence_api/app.py` wires proposals, approvals, PubMed, MARRVEL, research init, supervisor runs, graph search, graph curation, and related runtime routes.
- **Knowledge model counts:** runtime constants in `services/artana_evidence_db/graph_domain_config.py` currently provide 5 domain contexts, 18 entity types, 35 relation types, 208 relation synonyms, 106 relation constraints, and 32 forbidden constraints.
- **Claim/canonical relation split:** relation claims carry assertion class, status, polarity, participants, and evidence; canonical relations carry support/refute confidence fields and canonicalization fingerprints. Migration 026 adds the P0/P2 schema columns.
- **Discovery endpoints:** contradiction detection, single-source fragility filtering, seed-based reachability gaps, and mechanistic gap detection are all exposed as graph-service HTTP endpoints.
- **Batch ontology loading:** `/entities/batch`, `OntologyIngestionService` chunking, and `GraphOntologyEntityWriter.upsert_terms_batch()` are implemented.
- **Research brief delivery:** research-init brief markdown is delivered as the first inbox message when present.
- **PDF upload extraction:** PDF upload, extraction, and file-upload bridge paths exist in the harness and research-init runtime.
- **Automated relation synonym proposal support:** relation mapping proposals can create pending-review relation synonyms via the extraction policy path.

### Source coverage, precisely stated

There are **15 source types** in `SourceType`: PubMed, ClinVar, MARRVEL, UniProt, DrugBank, HGNC, AlphaFold, MONDO, HPO, UBERON, Cell Ontology, Gene Ontology, ClinicalTrials.gov, MGI, and ZFIN.

The steady-state scheduler baseline before P1.1 had **11 ingestion services wired** in `src/infrastructure/factories/ingestion_scheduler_factory.py`: PubMed, ClinVar, MARRVEL, HPO, UBERON, Cell Ontology, Gene Ontology, MONDO, DrugBank, AlphaFold, and UniProt.

PR #331 added scheduler-compatible ingestion for ClinicalTrials.gov, MGI, and ZFIN. The scheduler map now covers the original 14 source families, and PR #336 added HGNC as a deterministic alias-only source. `docs/project_status.md` now distinguishes the historical 11-source scheduler baseline, the current 14-source scheduler support, and HGNC's alias-loader role.

## Truth-Semantics PR Status

### P0.1 Qualifier scoping alignment

Resolved in PR #328. `penetrance` and `frequency` are now runtime descriptive qualifiers, matching `docs/plan.md` and the seeded graph dictionary config. They remain typed and validated, but they no longer contribute to canonicalization fingerprints or split canonical relations.

**Regression coverage**

- `tests/unit/domain/test_claim_participant_semantics.py` verifies `penetrance` and `frequency` are descriptive while `population` remains scoping.
- `tests/unit/domain/test_context_aware_canonicalization.py` verifies descriptive qualifier changes do not change canonicalization fingerprints, while real scoping qualifiers still do.

### P0.2 Digenic/combinatorial projection

Resolved in the digenic projection branch. Multi-`SUBJECT` and multi-`OBJECT` claims now add ordered endpoint participant sets to the canonicalization fingerprint, so a digenic claim cannot collapse into a single-subject canonical relation. Projection also validates all endpoint participants have entity anchors before materialization.

**Regression coverage**

- `tests/unit/domain/test_context_aware_canonicalization.py` verifies ordered multi-subject participant sets are fingerprinted deterministically.
- `tests/unit/application/services/test_kernel_relation_projection_materialization_service.py` verifies single-subject and digenic claims do not merge, matching digenic claims aggregate idempotently, and changing participant order changes relation identity.

### P0.3 REFUTE/conflict semantics

Resolved in PR #330. REFUTE claim polarity, not low numeric support confidence, now drives refute confidence and auto-promotion conflict blocking.

## Remaining Work

**Active branch:** `alvaro/measure-alias-yield-imports`

The active branch adds the measured alias-yield import report path so the next
status update can be generated from completed ingestion-job metadata rather than
manual log transcription.

### P0 — Fix truth-preservation semantics

The P0 truth-preservation items have landed. Do not start more P0 work from this list unless review feedback reopens one of those semantics.

#### P0.3 Fix REFUTE/conflict semantics and auto-promotion blocking

The status doc says refute evidence is tracked separately and auto-promotion is blocked when conflicting evidence is present. The code partially supports conflict discovery by grouping linked SUPPORT/REFUTE claims, but relation aggregation and auto-promotion do not consistently use claim polarity.

Resolved in PR #330:

- `refute_confidence` is derived from linked REFUTE claim units instead of relation evidence rows with `confidence < 0.5`.
- Canonical relation evidence remains SUPPORT-only; linked REFUTE claims feed the separate refute-confidence and conflict-blocking paths.
- Auto-promotion blocks on linked REFUTE claims, not on weak SUPPORT evidence.
- Weak SUPPORT evidence stays SUPPORT; it can lower confidence, but it does not become REFUTE evidence merely because its numeric score is low.

**Implemented work**

- Uses `linked_relation_id` as the explicit canonical relation association for REFUTE claims in this PR.
- Derives `refute_confidence` from non-computational linked REFUTE claims and their claim-evidence rows.
- Updates auto-promotion to block on linked REFUTE claim polarity for the same canonical relation.
- Adds tests for:
  - strong SUPPORT + strong REFUTE blocks auto-promotion;
  - weak SUPPORT alone does not become REFUTE evidence;
  - conflict summaries return meaningful support/refute confidences;
  - computational hypotheses remain excluded from support/refute confidence.

**Evidence**

- Status claim: `docs/project_status.md:352`
- Conflict grouping exists: `services/artana_evidence_db/relation_claim_repository.py:321`
- Refute confidence aggregation: `services/artana_evidence_db/_relation_curation_mixin.py`
- Auto-promotion conflict check: `services/artana_evidence_db/_relation_auto_promotion_mixin.py`
- Projection prunes non-active SUPPORT claims: `services/artana_evidence_db/relation_projection_materialization_service.py:420`

### P1 — Source/runtime and promotion contracts

#### P1.1 Add steady-state ingestion services for ClinicalTrials.gov, MGI, and ZFIN

**Merged PR:** #331 (`alvaro/add-translational-steady-state-ingestion`)

The old project-status language "all 14 base data sources shipped end-to-end" was too broad. Before PR #331, these three sources were shipped for research-init enrichment and extraction processing, but did not have steady-state scheduler ingestion services in the `ingestion_services` map.

In simple terms, this PR made the three translational sources work in the normal scheduled ingestion loop, not only during initial research setup. A scheduled ClinicalTrials.gov, MGI, or ZFIN source can now fetch records, persist source documents/records, enqueue extraction work, and then let the existing extraction processors hand Tier 2 claim generation to the governed AI path.

**Resolved in PR #331**

- Added scheduler-compatible ingestion services for ClinicalTrials.gov, MGI, and ZFIN.
- Registered `SourceType.CLINICAL_TRIALS`, `SourceType.MGI`, and `SourceType.ZFIN` in the scheduler factory ingestion map.
- The new services fetch upstream records, normalize JSON payloads, upsert source-document records when the scheduler provides a document repository, feed the kernel ingestion pipeline when a research space is attached, and return extraction targets for the existing extraction queue.
- Added regression coverage for direct service behavior, scheduling dispatch/extraction queue handoff, scheduler-factory registration, and Research Inbox wizard source visibility/onboarding prompt copy.
- Confirmed the Research Inbox space creation wizard includes ClinicalTrials.gov, MGI, and ZFIN in source selection, progress/review copy, and onboarding objective construction.

**Documentation status**

- `docs/project_status.md` now distinguishes "14 historical source families available" from "11 legacy steady-state sources plus 3 translational sources now added to scheduler support"; it also notes HGNC as the 15th deterministic alias-only source added in PR #336.

**Evidence**

- Source types exist: `src/domain/entities/user_data_source.py:39`
- Extraction processors registered: `src/infrastructure/factories/ingestion_scheduler_factory.py:114`
- Scheduler ingestion map now includes ClinicalTrials.gov, MGI, and ZFIN: `src/infrastructure/factories/ingestion_scheduler_factory.py:424`
- Research-init runtime path exists: `services/artana_evidence_api/research_init_runtime.py:1967`

#### P1.2 Normalize bootstrap connector claim paths

**Merged PR:** #332 (`alvaro/normalize-bootstrap-claim-paths`)

`docs/plan.md` says new relation claims should go through the AI-mediated Tier 2 claim path unless they are approved loader/import facts. Research-init still has direct proposal builders for structured sources such as ClinVar and AlphaFold.

This branch made bootstrap research setup obey the same truth rules as normal ingestion: deterministic connector code may ground source records, entities, identifiers, and attributes, but new biological or clinical relation claims should not be silently auto-promoted into the graph through source-specific shortcuts.

Current code review found the direct proposal path is wider than the older wording suggested. ClinVar, AlphaFold, ClinicalTrials.gov, MGI, ZFIN, and the shared MARRVEL OMIM helper all create `HarnessProposalDraft` relation proposals directly from structured records; before PR #332, `research_init_runtime.py` also promoted those enrichment proposals directly into graph relations during bootstrap.

**Resolved in PR #332**

- Added a bootstrap structured proposal review boundary that applies categorical factual support, goal relevance, and priority before deriving numeric confidence/ranking.
- Direct structured-source proposal builders now emit neutral unreviewed drafts with `requires_qualitative_review=true` and `direct_graph_promotion_allowed=false`, including the older MARRVEL OMIM draft helper.
- Research-init stores reviewed bootstrap drafts as pending proposals; it no longer has the direct enrichment proposal -> `create_relation()` promotion helper.
- ClinicalTrials.gov `TREATS` drafts are intentionally tentative until reviewed, because trial registration does not prove treatment effect by itself.
- MARRVEL OMIM drafts now use the same neutral-draft contract and receive a named qualitative review before any derived score is stored.
- Added regressions proving reviewed bootstrap drafts carry qualitative review metadata and that the direct enrichment promotion helper remains absent.

**Documentation status**

- `docs/project_status.md` now states the new bootstrap boundary: structured research-init enrichments may create reviewed proposal drafts, but do not directly write graph relations.
- `docs/plan.md` may still need a future master-design cleanup pass if the team wants it to mirror the shipped bootstrap boundary.

**Evidence**

- Plan Tier 2 requirement: `docs/plan.md:356`
- ClinVar bootstrap draft path: `services/artana_evidence_api/research_init_source_enrichment.py:226`
- AlphaFold bootstrap draft path: `services/artana_evidence_api/research_init_source_enrichment.py:570`
- ClinicalTrials.gov bootstrap draft path: `services/artana_evidence_api/research_init_source_enrichment.py:1438`
- MGI bootstrap draft path: `services/artana_evidence_api/research_init_source_enrichment.py:1714`
- ZFIN bootstrap draft path: `services/artana_evidence_api/research_init_source_enrichment.py:2053`
- MARRVEL OMIM bootstrap draft path: `services/artana_evidence_api/marrvel_enrichment.py:484`
- Bootstrap review boundary: `services/artana_evidence_api/bootstrap_proposal_review.py`
- Reviewed proposal storage path: `services/artana_evidence_api/research_init_runtime.py:712`

#### P1.3 Stop storing a relation id in `graph_claim_id`

Proposal promotion now routes through `POST /relations`, which creates a support claim and materializes a canonical relation. Earlier promotion metadata stored `relation.id` in both `graph_claim_id` and `graph_relation_id`.

Resolved in the earlier proposal-metadata PR. Current code reads `relation.source_claim_id` for `graph_claim_id` and keeps the canonical relation id in `graph_relation_id`, with a regression test proving the two ids differ for canonical-relation promotions.

**Resolved work**

- `graph_claim_id` is populated from the graph relation response's source claim id when available.
- `graph_relation_id` remains the canonical relation id.
- Canonical promotion metadata no longer points both fields at the relation id.

**Evidence**

- Graph client says `POST /relations` creates claim + relation: `services/artana_evidence_api/graph_client.py:441`
- Graph route creates the claim and materializes the relation: `services/artana_evidence_db/routers/relations.py:647`
- Current metadata uses `relation.source_claim_id`: `services/artana_evidence_api/proposal_actions.py:748`
- Regression test: `services/artana_evidence_api/tests/unit/test_proposal_actions.py:492`

### P2 — Model density and dictionary follow-through

#### P2.1 Complete entity alias harvesting targets

**Merged PR:** #333 (`alvaro/prepare-alias-harvesting-priority`)

`docs/plan.md` still lists entity alias harvesting from HGNC, UniProt, DrugBank, and HPO as a remaining synonym-strategy sub-target. The graph has entity alias storage and ontology alias registration paths, but the plan's alias-volume target is not tracked as complete.

In simple terms, this PR made phenotype synonyms actually usable by the graph. HPO already parsed synonyms and the ingestion service counted them, but the graph writer sent empty alias lists during batch upsert and its `register_alias()` method was a no-op. That meant the loader could report aliases as "registered" without proving they were persisted as graph aliases.

**Resolved in PR #333**

- Persist HPO term synonyms as real graph entity aliases, not just run-level counts.
- Make the ontology graph writer forward aliases in batch entity upserts and ensure aliases through the graph entity update path when a term resolves to an existing entity.
- Add `aliases_persisted` and `aliases_persisted_by_namespace_entity_type` metrics so HPO can report persisted alias counts separately from fetched synonym counts.
- Add idempotency coverage so re-importing HPO does not duplicate aliases or inflate persisted counts.
- Keep this PR focused on HPO; UniProt and DrugBank landed in PR #335, while HGNC landed in PR #336.

**Follow-up alias lanes**

- UniProt alias extraction and graph persistence landed in PR #335.
- DrugBank synonym/name extraction and graph persistence landed in PR #335.
- HGNC gene-symbol alias harvesting landed in PR #336 by adding a first-class deterministic source/loader path rather than another parser-only change.

**Evidence**

- Plan remaining sub-target: `docs/plan.md:590`
- Plan alias volume target: `docs/plan.md:952`
- Entity alias table exists: `services/artana_evidence_db/alembic/versions/022_entity_resolution_hardening.py`
- HPO/ontology ingestion tracks alias registration and persistence counts: `src/application/services/ontology_ingestion_service.py:123`
- HPO/ontology ingestion calls `register_alias()` for term synonyms: `src/application/services/ontology_ingestion_service.py:279`
- Ontology alias helper normalizes/deduplicates synonym labels: `src/infrastructure/ingest/ontology_entity_aliases.py:11`
- Ontology batch upsert forwards aliases: `src/infrastructure/ingest/graph_ontology_entity_writer.py:147`
- Ontology writer ensures aliases through graph entity updates: `src/infrastructure/ingest/graph_ontology_entity_writer.py:240`
- Ontology summary exposes persisted alias metrics: `src/domain/services/ontology_ingestion.py:70`
- Scheduler logs source-scoped alias persistence stats: `src/infrastructure/factories/ingestion_scheduler_ontology.py:140`
- Graph API gateway supports entity alias updates: `services/artana_evidence_api/graph_client.py:342`
- UniProt structured alias extraction landed in PR #335: `src/application/services/structured_source_aliases.py:57`
- DrugBank structured alias extraction landed in PR #335: `src/application/services/structured_source_aliases.py:129`
- HGNC source type landed in P2.4: `src/domain/entities/user_data_source.py:35`

#### P2.2 Add coverage/observability for relation synonym harvesting

**Merged PR:** #334 (`alvaro/prepare-relation-synonym-observability`)

The policy path can propose pending-review relation synonyms from mapping proposals, so this was not a missing primitive. PR #334 proves that it is active in the relevant extraction flows and observable enough for production.

In simple terms, this PR made relation synonym learning observable and regression-proof. When the extraction policy maps an observed relation label like `GENETIC_INTERACTION` to a canonical relation type like `GENETIC_INTERACTION_IMPAIRMENT`, the system now returns a structured synonym-proposal outcome and reports whether the synonym was created, skipped, or failed.

**Resolved in PR #334**

- Added a typed `RelationSynonymProposalResult` with explicit `created`, `skipped`, and `failed` statuses plus skip/failure reasons.
- Fixed the policy synonym write to call the dictionary service contract with `relation_type_id`, `created_by`, and pending-review dictionary settings.
- Threaded relation synonym counts through policy proposal storage, extraction logs, extraction outcome fields, extraction metadata, and the extraction funnel.
- Added direct unit tests for dictionary-missing, malformed mapping, identical relation type, low-confidence, success, existing synonym, conflict, and create-failure cases.
- Added policy-store metric tests for created and duplicate/skipped synonym proposals.
- Added a claim-first regression proving a mapping proposal both canonicalizes the relation claim and creates the pending-review relation synonym.
- Added a resolver regression proving pending-review relation synonyms do not affect deterministic normalization until approval.
- Added graph-admin `review_status` filtering for relation synonyms so pending items can be reviewed without mixing them with approved aliases.
- Documented the graph-admin review workflow for pending relation synonyms.

**Evidence**

- Plan deliverable: `docs/plan.md:596` and `docs/plan.md:887`
- Synonym proposal result contract: `src/application/agents/services/_extraction_relation_synonym_proposal.py:21`
- Pending-review relation synonym write: `src/application/agents/services/_extraction_relation_synonym_proposal.py:172`
- Policy proposal store result counters: `src/application/agents/services/_extraction_relation_synonym_proposal_store.py:20`
- Policy proposal store aggregates synonym statuses: `src/application/agents/services/_extraction_relation_synonym_proposal_store.py:42`
- Policy proposal log reports synonym counters: `src/application/agents/services/_extraction_relation_persistence_helpers.py:327`
- Extraction funnel exposes synonym counters: `src/application/agents/services/_extraction_relation_persistence_helpers.py:556`
- Pending-review synonym API filter: `services/artana_evidence_db/routers/dictionary.py:1007`
- Policy contract already carries mapping proposals as first-class data: `src/domain/agents/contracts/extraction_policy.py:35`
- Direct synonym proposal tests: `tests/unit/application/services/test_extraction_relation_synonym_proposal.py:139`
- Policy-store metric tests: `tests/unit/application/services/test_extraction_relation_synonym_proposal.py:273`
- Claim-first canonicalization + synonym proposal regression: `tests/unit/application/services/test_extraction_claim_first_persistence.py:891`
- Pending-review resolver safety regression: `tests/unit/infrastructure/test_kernel_dictionary_repository.py:668`
- Relation synonym review workflow: `docs/graph/admins/admin-guide.md:220`

#### P2.3 Extend source alias harvesting beyond HPO

**Merged PR:** #335 (`alvaro/prepare-source-alias-harvesting-followups`)

HPO alias persistence is now proven, but the broader plan target still calls out HGNC, UniProt, and DrugBank alias harvesting. PR #335 took the HPO alias persistence contract and applied it to structured source records so names and synonyms already present upstream become graph aliases, not just metadata or grounding facts.

In simple terms, this PR made protein, gene, and drug aliases searchable by the graph. If UniProt knows a protein has alternative names, or DrugBank knows a drug has synonyms, those labels can now help resolve the same entity later instead of being trapped inside one source record.

**Resolved in PR #335**

- Added a shared structured-source alias candidate contract and graph-backed writer that creates/resolves kernel entities, attaches aliases through the entity service, and reports backend-derived `alias_candidates_count`, `aliases_persisted`, `aliases_skipped`, `alias_entities_touched`, and `alias_errors`.
- UniProt ingestion now extracts and persists aliases for protein records and associated gene symbols: UniProt accessions, entry names, protein alternative names, primary gene names, and gene aliases become graph aliases for `PROTEIN` and `GENE` candidates.
- DrugBank ingestion now extracts and persists drug aliases beyond the DrugBank ID: display names, generic names, synonyms, brand names, product names, and DrugBank IDs become graph aliases for `DRUG` candidates.
- Older parser/grounding paths now preserve alias fields: UniProt parser emits `alternative_names` and `gene_aliases`; DrugBank parser/grounding carries source synonyms into the grounded drug entity alias payload.
- Added HGNC alias-candidate extraction for approved symbols, previous symbols, alias symbols, approved names, previous names, and alias names. HGNC still needed a first-class source/loader path after PR #335, which landed in PR #336.
- Added regression coverage for alias extraction, parser boundaries, graph-backed idempotent persistence, service-level metrics, scheduler wiring, and DrugBank Tier 1 grounding aliases.

**Remaining follow-up**

- Run real HPO/UniProt/DrugBank/HGNC imports in P3.1 and update `docs/project_status.md` with measured alias-yield counts rather than planned targets.

**Evidence**

- Plan remaining sub-target: `docs/plan.md:590`
- Plan alias volume target: `docs/plan.md:952`
- HPO alias persistence contract and metrics landed in PR #333.
- Graph API gateway supports entity alias updates: `services/artana_evidence_api/graph_client.py:342`
- UniProt alias extraction helper: `src/application/services/structured_source_aliases.py:57`
- DrugBank alias extraction helper: `src/application/services/structured_source_aliases.py:129`
- `SourceType` has UniProt, DrugBank, and HGNC: `src/domain/entities/user_data_source.py:21`
- Structured source alias candidates: `src/application/services/structured_source_aliases.py`
- Graph-backed structured alias writer: `src/infrastructure/ingestion/structured_source_alias_writer.py`
- UniProt alias persistence metrics: `src/application/services/uniprot_ingestion_service.py`
- DrugBank alias persistence metrics: `src/application/services/drugbank_ingestion_service.py`

#### P2.4 Add HGNC alias loader/import path

**Merged PR:** #336 (`alvaro/prepare-hgnc-alias-loader`)

The source-alias PR added `build_hgnc_alias_candidates()`, but there was no HGNC source type, gateway, loader, scheduler path, or approved import command that fed real HGNC records into that extractor. PR #336 closed that narrow model-density gap by making HGNC an operational alias source, not just a parser contract.

In simple terms, this PR lets us take an HGNC record with an approved symbol, previous symbols, alias symbols, names, and an HGNC ID, and make those labels searchable aliases on the canonical `GENE` entity. It is idempotent: running the same HGNC input twice should not duplicate aliases or inflate persisted counts.

**Implemented in PR #336**

- Added `SourceType.HGNC` and aligned the legacy SQLAlchemy source enums plus the Alembic enum-expansion migration.
- Added an HGNC REST gateway for approved human gene nomenclature records using the public HGNC REST API.
- Added `HGNCIngestionService`, which fetches records, reuses `build_hgnc_alias_candidates()`, and writes aliases through the graph-backed structured alias writer.
- Registered HGNC in the steady-state scheduler factory as a deterministic alias-only ingestion service.
- Added HGNC to research-init source preferences, source status bookkeeping, and the Research Inbox space creation wizard.
- Added regression tests for HGNC field parsing, gateway record normalization/deduping, service metrics, alias-writer idempotency, scheduler registration, source preference persistence, and wizard visibility.

**Remaining follow-up**

- Keep HGNC scoped to deterministic identity aliases unless a future PR adds a governed Tier 2 relation-claim extraction path.

**Evidence**

- HGNC alias extractor exists: `src/application/services/structured_source_aliases.py:163`
- Graph-backed structured alias writer exists: `src/infrastructure/ingestion/structured_source_alias_writer.py:1`
- Gene resolution policy uses `hgnc_id`: `services/artana_evidence_db/dictionary_management_service.py:70`
- HGNC source type: `src/domain/entities/user_data_source.py:35`
- HGNC gateway: `src/infrastructure/data_sources/hgnc_gateway.py`
- HGNC ingestion service: `src/application/services/hgnc_ingestion_service.py`
- HGNC scheduler registration: `src/infrastructure/factories/ingestion_scheduler_factory.py:363`
- HGNC source enum migration: `services/artana_evidence_api/alembic/versions/015_add_hgnc_and_current_source_types.py`
- HGNC wizard option: `services/research_inbox/components/spaces/CreateSpaceWizard.tsx:618`
- MARRVEL already extracts HGNC IDs from structured records: `src/domain/services/marrvel_grounding.py:69`

#### P2.5 Normalize alias-yield measurement and reporting

**Merged PR:** #337 (`alvaro/prepare-alias-yield-measurement`)

HPO, UniProt, DrugBank, and HGNC now all have deterministic alias persistence paths, and PR #337 normalized their loader-local metrics into one backend-derived alias-yield shape. This turns "alias harvesting exists" into "we know how many aliases were found, persisted, skipped, and which source produced them."

In simple terms, this PR gave us a single comparable table for alias yield: HPO phenotype aliases, UniProt protein/gene aliases, DrugBank drug aliases, and HGNC gene aliases. The number comes from backend persistence results, not from an LLM or planned targets.

**Resolved in PR #337**

- Added a shared alias-yield metadata contract for one source and cross-source rollups, covering `alias_candidates_count`, optional `aliases_registered`, `aliases_persisted`, `aliases_skipped`, `alias_entities_touched`, and `alias_errors`.
- Normalized HPO/ontology metrics with the structured-source metrics returned by UniProt, DrugBank, and HGNC.
- Added scheduler metadata support so completed ingestion jobs can carry backend-derived alias-yield counts.
- Added research-init source-result rollups and an Alias Yield section in the research brief.
- Added regression tests proving alias-yield counts reach the API payload and the brief output, not just service-local summaries.

**Remaining follow-up**

- Run real HPO/UniProt/DrugBank/HGNC imports in P3.1 and update `docs/project_status.md` with measured alias-yield counts.

**Evidence**

- Shared structured-source alias metric contract: `src/application/services/structured_source_aliases.py:25`
- Graph-backed writer computes persisted/skipped counts from backend state: `src/infrastructure/ingestion/structured_source_alias_writer.py:83`
- UniProt alias metrics: `src/application/services/uniprot_ingestion_service.py:56`
- DrugBank alias metrics: `src/application/services/drugbank_ingestion_service.py:56`
- HGNC alias metrics: `src/application/services/hgnc_ingestion_service.py:55`
- HPO/ontology alias metrics: `src/domain/services/ontology_ingestion.py:70`
- HPO metrics population: `src/application/services/ontology_ingestion_service.py:124`
- Shared alias-yield reporting helper: `src/application/services/alias_yield_reporting.py`
- Ingestion job metadata carries alias-yield: `src/type_definitions/data_sources.py`
- Scheduler metadata attaches alias-yield: `src/application/services/_ingestion_scheduling_metadata_helpers.py`
- Research-init result payload attaches the alias-yield rollup: `services/artana_evidence_api/research_init_runtime.py`
- Research brief renders the Alias Yield section: `services/artana_evidence_api/research_init_brief.py`
- Regression tests: `tests/unit/application/test_alias_yield_reporting.py`, `services/artana_evidence_api/tests/unit/test_research_init.py`, `services/artana_evidence_api/tests/unit/test_research_init_brief.py`

### P3 — Operational rollout and status alignment

**Merged PR:** #338 (`alvaro/docs-next-work-after-alias-yield`)

This item was a status/docs cleanup PR that made the remaining rollout work explicit and removed stale claims from `docs/project_status.md`.

In simple terms, this PR made the docs say: "the code path is built; now we need measured import counts and deployment/config rollout." That keeps future PRs from chasing already-merged work.

#### P3.0 Align project status after merged P0-P2 work

**Resolved in PR #338**

- Updated `docs/project_status.md` to stop saying the remaining work is ops only.
- Replaced "all 14 sources shipped end-to-end" with the precise current source story: 14 historical source families were the baseline; PR #331 added steady-state scheduler ingestion for the three translational sources that were previously research-init-only; PR #336 added HGNC as a 15th deterministic alias-only source.
- Added the PR #337 alias-yield reporting state and made clear that real HPO/UniProt/DrugBank/HGNC import runs are still needed before status docs can claim measured alias counts.
- Kept P4 items clearly deferred: the full AI orchestrator agent, whole-space gap discovery, and Phase 5 definition.

**Evidence**

- Stale status framing was replaced in `docs/project_status.md`.
- Source coverage is now precisely stated in this file's "Source coverage" baseline.
- Bootstrap/research-init boundary was normalized in PR #332 and is reflected in `docs/project_status.md`.
- Alias-yield reporting landed in PR #337, but measured counts require real import runs.

#### P3.1 Run measured alias-yield imports

**Active branch:** `alvaro/measure-alias-yield-imports`

This branch makes the measured-count step reproducible and fail-closed. It does
not invent counts. It reads normalized `alias_yield` metadata from completed
ingestion jobs, chooses the latest measured job for each required source, and
exits nonzero if HPO, UniProt, DrugBank, or HGNC is missing.

In simple terms, this PR gives us the measuring stick. After real imports run in
an approved environment, the report command produces the exact JSON and Markdown
table that should be used to update `docs/project_status.md`.

**Required work**

- Run real HPO, UniProt, DrugBank, and HGNC imports against an approved environment.
- Run `./venv/bin/python scripts/measure_alias_yield_imports.py --json-out reports/alias_yield_imports.json --markdown-out reports/alias_yield_imports.md`.
- Use the generated Markdown table to update `docs/project_status.md` with measured counts, not planned targets.

**Implemented in this branch**

- Added a measurement report service that normalizes completed job metadata into one required-source report.
- Added an operational script that queries the latest completed ingestion job per required source, scopes by optional `--research-space-id`, and bypasses RLS only for this admin reporting read.
- Added JSON-input mode so exported metadata can be checked offline and regression-tested without a live database.
- Added regression tests proving the report uses the latest job per source, accepts direct alias-yield payloads, fails closed when a required source is missing, and writes complete JSON output when all required sources are present.

**Evidence**

- Measurement report service: `src/application/services/alias_yield_import_measurement.py`
- Operational report command: `scripts/measure_alias_yield_imports.py`
- Regression tests: `tests/unit/application/test_alias_yield_import_measurement.py`

#### P3.2 Operational rollout checklist

These are deployment or data-maintenance tasks, not product semantics.

1. Run migration 026 on staging/prod. See `docs/migration_026_deployment_notes.md`.
2. Provision `DRUGBANK_API_KEY` in GCP Secret Manager and run the Cloud Run sync script with `DRUGBANK_API_KEY_SECRET_NAME` set.
3. Backfill historical orphan claims/proposals with `source_document_ref` where possible.
4. Roll out ontology AI evidence sentences per namespace, starting with HPO, then UBERON, GO, CL, and MONDO last. Watch the per-namespace `requested`, `generated`, `fallback`, `cache_hit`, and `total_sentence_chars` stats before expanding.

### P4 — Deferred strategic work

These are real but intentionally deferred. They should not be described as Phase 1-4 blockers.

- **Full AI orchestrator agent:** replace deterministic research-init phases with an agent that reads intermediate results and decides which sources to query next.
- **Whole-space gap discovery:** seed-free reachability/gap discovery across an entire research space. This likely needs a materialized reachability projection to avoid expensive all-pairs traversal.
- **Phase 5 definition:** `docs/plan.md` does not define Phase 5. Candidate themes include active learning, multi-space synthesis, reasoning explainability UI, patient-data integration, or the full orchestrator.

## Documentation Corrections Remaining

- Align the qualifier-registry description in `docs/plan.md` if a future docs pass updates the master design text; runtime behavior and this status doc already reflect PR #328.
- After real alias imports land, update `docs/project_status.md` with measured HPO/UniProt/DrugBank/HGNC alias counts, not just planned targets.

## Phase Readiness Summary

| Phase | Current status | Real blockers |
|-------|----------------|---------------|
| Phase 1 — Foundation | Mostly complete | Runtime/status docs aligned; `docs/plan.md` master text may still need future cleanup |
| Phase 2 — Density | Mostly complete | Alias-yield reporting landed in PR #337; this branch adds the report command for measured HPO/UniProt/DrugBank/HGNC import counts, but real import runs still need to be executed before `docs/project_status.md` can include final measured numbers; HGNC loader landed in PR #336; UniProt/DrugBank persistence landed in PR #335; relation-synonym observability landed in PR #334 |
| Phase 3 — Reasoning | Partially complete | Governed bootstrap boundary landed in PR #332; rollout operations are next; full orchestrator remains deferred |
| Phase 4 — Discovery | Mostly complete | Seed-based endpoints shipped; whole-space gap discovery deferred |

## Bottom Line

Artana is past the broad platform-build stage: the graph service, harness runtime, knowledge model, discovery endpoints, batch ontology loading, PDF flow, research brief flow, and most source integrations are real. The remaining work is not "no concrete code work." It is a focused set of correctness and completion tasks:

1. run real HPO/UniProt/DrugBank/HGNC imports, generate the alias-yield report, and update status docs with backend-derived counts;
2. run the remaining deployment and rollout operations;
3. decide what Phase 5 should be.
