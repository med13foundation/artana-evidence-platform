# SRP Hardening Plan: Source Adapters, Candidate Generation, And Extraction

## Purpose

Make the Evidence API datasource, candidate-generation, and extraction pipeline
fully single-responsibility and strongly encapsulated.

Current status: the main source-adapter, candidate-generation, source-document,
runtime-serialization, and document-extraction SRP slices are implemented and
verified. The final gates passed: `make artana-evidence-api-service-checks`,
`make service-checks`, and `git diff --check`. Claude second-opinion is
recorded separately in the closeout gates and verification log.

This plan starts from first principles:

- A source should own its own behavior, not require scattered source-specific
  conditionals across runtime modules.
- Candidate generation should create, score, deduplicate, and classify
  candidates through focused services with narrow contracts.
- Extraction should turn selected evidence into reviewable proposals through
  source-owned policy and extraction adapters, not broad orchestration modules.
- Runtime orchestration should sequence services and persist artifacts; it should
  not also contain the detailed ranking, staging, extraction, and graph-write
  rules.

This is the active progress tracker for the next architecture pass. Keep updates
append-only where possible and mark progress honestly against live code.

## Current Live State

### Already Stronger

- Source metadata is centralized in
  `services/artana_evidence_api/source_registry.py`.
- Source record behavior is centralized in
  `services/artana_evidence_api/source_policies.py`.
  - `SourceRecordPolicy` owns provider identifiers, source family,
    normalization, variant-awareness, request schema, result schema, and handoff
    target metadata.
- Agentic query planning is centralized in
  `services/artana_evidence_api/evidence_selection_source_playbooks.py`.
  - `SourceQueryPlaybook` owns per-source query payload construction.
- Source plan validation is isolated in
  `services/artana_evidence_api/evidence_selection_plan_validation.py`.
- Review/extraction staging has source-specific policy in
  `services/artana_evidence_api/evidence_selection_extraction_policy.py`.
- Variant-aware extraction already has a stronger boundary:
  - `services/artana_evidence_api/variant_extraction_contracts.py`
  - `services/artana_evidence_api/variant_extraction_bridges.py`
  - `services/artana_evidence_api/variant_aware_document_extraction.py`
- Boundary tests exist:
  - `services/artana_evidence_api/tests/unit/test_source_boundary_contract.py`
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py`
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_extraction_policy.py`
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_plan_validation.py`

### Still Not SRP-Clean Enough

- `services/artana_evidence_api/evidence_selection_runtime.py` is now a smaller
  orchestration module at 715 lines. Candidate screening, handoff creation,
  review staging, workspace snapshot construction, source-plan artifact
  construction, and result payload serialization have been extracted.
  - It orchestrates runs.
  - It runs live source searches.
  - It applies selection/defer/skip decisions.
- Candidate decisions now move through screening, handoff creation, review
  staging, and runtime as typed `EvidenceSelectionCandidateDecision` objects.
  Runtime serializes them to `JSONObject` payloads only at artifact/API result
  boundaries.
- Deferred selected records now carry explicit typed deferral reasons and
  preserve the original selected relevance label when a selected candidate is
  demoted by per-search budget, run handoff budget, or shadow mode.
- `services/artana_evidence_api/source_document_bridges.py` is now a
  compatibility facade at 87 lines. Source-document models, repository
  SQL, deterministic extraction, graph writes, and extraction orchestration are
  split into focused modules.
- `source_document_bridges.py` still exists as a compatibility import path, but
  production callers have been migrated to focused modules and an architecture
  test blocks new production dependencies on the facade.
- `services/artana_evidence_api/document_extraction.py` is still broad at 1,007
  lines, but contracts/types, prompt schemas, review-context normalization,
  relation taxonomy, graph-entity draft resolution, LLM entity-label cleanup,
  document-context summarization, and draft-review scoring helpers have been
  extracted.
  - Candidate extraction and proposal-review diagnostics are typed in
  `document_extraction_contracts.py`; status/error normalization now lives in
  `document_extraction_diagnostics.py`.
- Sources now have one typed adapter surface for metadata, record policy, query
  playbook, live-search validation, extraction policy, and candidate context.
  The source-search runner still owns network execution dispatch and remains a
  future plugin-encapsulation target.

## Target Architecture

### Source Adapter Boundary

Introduce a single typed source adapter contract that composes existing
source-owned behaviors behind one interface.

Target responsibilities:

- Source identity and metadata.
- Query payload planning.
- Live source-search payload validation.
- Result record normalization.
- Provider external ID extraction.
- Variant-aware recommendation.
- Candidate-screening hints.
- Extraction/review staging policy.
- Handoff eligibility and target policy.

The adapter should not perform orchestration, persistence, or external network
calls directly unless the existing source-search runner pattern is intentionally
moved into the adapter in a later phase.

Candidate module target:

- `services/artana_evidence_api/source_adapters.py`

Initial adapter shape:

```python
class EvidenceSourceAdapter(Protocol):
    source_key: str
    source_family: str

    def definition(self) -> SourceDefinition: ...
    def query_playbook(self) -> SourceQueryPlaybook: ...
    def record_policy(self) -> SourceRecordPolicy: ...
    def extraction_policy(self) -> EvidenceSelectionExtractionPolicy: ...
    def validate_live_search(self, search: EvidenceSelectionLiveSourceSearch) -> None: ...
    def build_candidate_context(self, record: JSONObject) -> JSONObject: ...
```

The exact names can change during implementation, but the goal should remain:
callers ask the adapter for source behavior rather than importing many separate
source registries.

### Candidate Generation Boundary

Extract candidate generation and screening from `evidence_selection_runtime.py`
into focused modules.

Target modules:

- `services/artana_evidence_api/evidence_selection_candidates.py`
  - `EvidenceSelectionCandidateSearch`
  - selected/skipped/deferred decision models
  - candidate search/result contracts
- `services/artana_evidence_api/evidence_selection_candidate_screening.py`
  - term extraction
  - relevance scoring
  - exclusion matching
  - duplicate detection
  - per-search and run-level candidate limits
- `services/artana_evidence_api/evidence_selection_candidate_handoffs.py`
  - selected-record handoff creation
  - handoff error normalization

Runtime should only call these services in sequence.

### Extraction Boundary

Extract review/extraction staging from `evidence_selection_runtime.py` and split
large document/source-document modules.

Target modules:

- `services/artana_evidence_api/evidence_selection_review_staging.py`
  - proposal draft creation for selected source records
  - review item draft creation
  - normalized extraction metadata assembly
- `services/artana_evidence_api/source_document_models.py`
  - source-document Pydantic models and lifecycle enums
- `services/artana_evidence_api/source_document_repository.py`
  - SQLAlchemy repository implementation only
- `services/artana_evidence_api/source_document_entity_extraction.py`
  - deterministic entity mention extraction only
- `services/artana_evidence_api/source_document_graph_writer.py`
  - graph entity/observation persistence only
- `services/artana_evidence_api/source_document_extraction_service.py`
  - orchestration across repository, extractor, graph writer, and metadata
    updater

Document extraction should be reviewed separately after the candidate/source
document split. It is the largest file and should be broken down incrementally,
not in one risky rewrite.

## Workstreams

### Workstream A: Source Adapter Hardening

Status: implemented; public-contract compatibility is closed through ingress
normalization

Goals:

- Create a typed source adapter registry that composes:
  - `SourceDefinition`
  - `SourceRecordPolicy`
  - `SourceQueryPlaybook`
  - `EvidenceSelectionExtractionPolicy`
  - live source-search validation
- Replace direct runtime/handoff imports of separate source behavior with adapter
  calls where practical.
- Keep existing public contracts stable.

Implementation steps:

- [x] Add adapter protocol/dataclass and registry.
- [x] Add one adapter per direct-search source:
  - PubMed
  - MARRVEL
  - ClinVar
  - ClinicalTrials.gov
  - UniProt
  - AlphaFold
  - DrugBank
  - MGI
  - ZFIN
- [x] Make adapter parity tests prove every direct-search source has exactly one
  adapter.
- [x] Route query playbook, record policy, extraction policy, and validation
  lookups through the adapter registry.
- [x] Keep old helper functions as thin compatibility wrappers until callers are
  migrated.
- [x] Add a source-boundary architecture test so production callers cannot
  import source-owned helper functions directly and bypass the adapter.
- [x] Make adapter validation canonical-source-key only, keep adapter registry
  construction lazy, and return stable candidate-context keys.
- [x] Verify and document whether canonical-source-key validation is an
  intentional public contract. If aliases/case variants are still part of the
  public API, normalize them at ingress before adapter validation.

Acceptance criteria:

- Adding a new direct-search source requires registering one adapter and adding
  source-specific tests.
- No runtime module needs its own source-key map for metadata, query planning,
  extraction policy, or handoff eligibility.
- Existing OpenAPI behavior remains stable unless an intentional contract change
  is documented.

### Workstream B: Candidate Generation SRP Cleanup

Status: implemented for the candidate-generation hardening slice; future runtime
serialization cleanup remains separate

Goals:

- Move candidate search contracts and screening decisions out of
  `evidence_selection_runtime.py`.
- Make candidate generation deterministic, testable, and independently
  reusable.
- Keep runtime orchestration small and readable.

Implementation steps:

- [x] Move `EvidenceSelectionCandidateSearch` and screening result/decision
  contracts into a focused candidate module.
- [x] Extract `_screen_candidate_searches`, `_decision_for_record`,
  `_decision_is_duplicate`, `_mark_decision_seen`, scoring helpers, caveat
  helpers, and relevance-label helpers into candidate screening.
- [x] Convert JSON-shaped decision dictionaries into typed internal models where
  feasible, then serialize only at artifact boundaries.
- [x] Keep duplicate detection source-document aware, but hide source-document
  metadata parsing behind a small protocol/helper.
- [x] Move handoff-budget demotion into candidate screening so runtime does not
  rank and demote selected candidates itself.
- [x] Unify deferred-record semantics so per-search budget, run handoff budget,
  shadow mode, missing search, and weak/off-objective records have explicit,
  typed fields for `decision`, original relevance, and demotion reason.
- [x] Move shadow-mode selected-to-deferred demotion out of runtime into a
  focused decision-mode helper or screening service.
- [x] Keep `evidence_selection_runtime.py` responsible only for:
  - creating the run
  - building/validating the source plan
  - invoking live source searches
  - invoking candidate screening
  - invoking handoff/review staging
  - writing artifacts/progress/final status

Acceptance criteria:

- Candidate screening can be tested without constructing a full harness run.
- Candidate decisions have explicit selected/skipped/deferred/relevance-label
  semantics.
- Per-search limits, run-level handoff limits, duplicate detection, exclusion
  handling, and weak-match handling have focused regression tests.
- Source-record hash and source-document hash canonicalization are tested
  together so deduplication cannot silently diverge.

### Workstream C: Review And Extraction Staging SRP Cleanup

Status: implemented for first hardening slice; facade deprecation remains

Goals:

- Move proposal/review item staging out of `evidence_selection_runtime.py`.
- Make extraction policy the only place that maps source-specific review type,
  proposal type, evidence role, limitations, and normalized fields.
- Keep selected-record review staging independent from run orchestration.

Implementation steps:

- [x] Create `evidence_selection_review_staging.py`.
- [x] Move `_stage_selected_records_for_review`,
  `_proposal_draft_for_decision`, `_review_item_draft_for_decision`,
  `_review_metadata`, and source-specific proposal/review summary calls into the
  staging module.
- [x] Route source policy lookup through the new source adapter registry.
- [x] Add tests that stage selected records without running the whole runtime.
- [x] Keep existing proposal/review payload shape stable.

Acceptance criteria:

- Runtime delegates review staging to one focused service.
- Every staged review item includes source key, source family, selected record
  hash, relevance label, normalized extraction, source limitations, and pending
  human review gate.
- Existing evidence-selection runtime tests still pass with minimal changes.

### Workstream D: Source Document Bridge Split

Status: implemented for first hardening slice

Goals:

- Split `source_document_bridges.py` into focused responsibilities.
- Keep repository, deterministic extraction, graph write, metadata update, and
  orchestration separate.

Implementation steps:

- [x] Move models/enums/protocols into `source_document_models.py`.
- [x] Move SQLAlchemy persistence into `source_document_repository.py`.
- [x] Move `_extract_entity_candidates` and related deterministic extraction
  helpers into `source_document_entity_extraction.py`.
- [x] Move entity/observation persistence into `source_document_graph_writer.py`.
- [x] Move extraction orchestration and metadata status updates into
  `source_document_extraction_service.py`.
- [x] Keep `source_document_bridges.py` as a compatibility facade during the
  first pass, or replace imports in one controlled migration if low risk.
- [x] Add a removal/deprecation plan for the compatibility facade, or migrate
  production callers to the focused modules and add a guardrail against new
  facade imports.
- [x] Add regression tests for repository import paths, pending extraction,
  stale recovery, graph-write failure behavior, and metadata status updates.
- [x] Add focused tests for deterministic source-document entity extraction.
- [x] Add direct orchestration tests for
  `source_document_extraction_service.py`, separate from the bridge-facade
  compatibility tests.

Acceptance criteria:

- No single source-document module owns lifecycle models, repository SQL,
  extraction heuristics, graph writes, and service orchestration at the same
  time.
- Existing callers keep working or are migrated in the same pass.
- Graph-write failures still fail closed and preserve metadata diagnostics.

### Workstream E: Document Extraction Decomposition

Status: remaining, after Workstreams B-D

Goals:

- Reduce `document_extraction.py` without a broad rewrite.
- Preserve current extraction behavior while moving cohesive pieces into focused
  modules.

Possible target modules:

- `document_extraction_contracts.py`
- `document_extraction_prompting.py`
- `document_extraction_relation_taxonomy.py`
- `document_extraction_entities.py`
- `document_extraction_review.py`
- `document_extraction_drafts.py`
- `document_extraction_diagnostics.py`
- `document_context_summary.py`

Acceptance criteria:

- Each extracted module has one clear reason to change.
- Current document extraction tests continue to pass.
- Variant-aware extraction remains separate and does not regress.

## Suggested Implementation Order

The original implementation order is now mostly complete for Workstreams A-D.
The remaining work should close the architectural gaps in dependency order, not
by file size.

## First-Principles Closure Plan

### Closure Invariants

The SRP hardening is complete only when these invariants are true:

- Source-specific behavior is reachable through one adapter boundary by
  production callers.
- Candidate decisions are typed in memory and are serialized only at artifact,
  API, or persistence boundaries.
- Deferred records have one explicit contract that separates:
  - the current decision (`selected`, `skipped`, `deferred`);
  - the original relevance label;
  - the reason a selected record was demoted or deferred;
  - whether a record would have been selected in shadow mode.
- Runtime sequences services and records artifacts; it does not hand-build
  candidate decision rewrites.
- Source-document identity, repository persistence, extraction, graph writes,
  and orchestration each have one owning module and one test surface.
- Compatibility facades are temporary, documented, and guarded against new
  production dependencies.
- `document_extraction.py` is reduced through small behavior-preserving
  extractions, not a risky rewrite.

### Phase 1: Candidate Decision Contract

Status: implemented

Why first:

- Candidate decisions are the shared contract between screening, handoff,
  review staging, runtime artifacts, and tests.
- Deferred-label ambiguity cannot be fixed cleanly while decisions are untyped
  dictionaries.

Implementation steps:

- [x] Add typed internal models in `evidence_selection_candidates.py`:
  - `EvidenceSelectionDecision`
  - `EvidenceSelectionDecisionState`
  - `EvidenceSelectionRelevanceLabel`
  - `EvidenceSelectionDeferralReason`
  - `EvidenceSelectionCandidateContext`
- [x] Keep model fields explicit for source key, source family, search id,
  record index, record hash, title, score, matched/excluded terms, caveats,
  reason, relevance label, original relevance label, demotion reason,
  candidate context, and shadow selection marker.
- [x] Add `to_artifact_payload()` or equivalent serializer so JSON conversion
  happens only at artifact/API boundaries.
- [x] Update candidate screening, handoff-budget application, review staging,
  and runtime to pass typed decisions internally.
- [x] Keep external response/artifact payload shapes backward compatible unless
  a deliberate contract change is documented.

Acceptance gates:

- [x] `test_evidence_selection_candidates.py` covers hash helpers, score
  coercion, relevance labels, decision serialization, and typed deferral state.
- [x] Existing evidence-selection runtime and router tests pass without
  weakening assertions.

### Phase 2: Unified Deferral And Shadow Semantics

Status: implemented

Why second:

- Deferral semantics are product-facing audit data. They must be consistent
  before claiming the candidate pipeline is SRP-clean.

Implementation steps:

- [x] Replace stringly deferred rewrites with one helper, for example
  `defer_selected_decision(decision, reason=..., mode=...)`.
- [x] Make per-search budget, run handoff budget, missing source search, shadow
  mode, duplicate selection, weak match, and off-objective cases use the same
  typed decision contract.
- [x] Preserve original relevance labels for demoted selected records.
- [x] Use a separate typed demotion/deferral reason instead of overloading
  `relevance_label`.
- [x] Move shadow-mode selected-to-deferred demotion out of
  `evidence_selection_runtime.py` into candidate screening or a focused
  `evidence_selection_decision_modes.py` module.

Acceptance gates:

- [x] Focused tests prove deferred populations have consistent typed fields for
  missing searches, per-search budget, run handoff budget, and shadow mode.
- [x] Shadow-mode tests prove selected relevance is preserved and
  `would_have_been_selected` or its typed replacement is explicit.
- [x] Runtime no longer hand-builds selected-to-deferred dictionaries.

### Phase 3: Source-Key Public Contract Closure

Status: implemented for ingress normalization; docs/public contract remains
unchanged

Why third:

- Source adapters now enforce canonical source keys. That is internally clean,
  but public callers may still expect aliases/case variants to be normalized.

Implementation steps:

- [x] Inspect router request models and public/e2e tests for source-key alias
  behavior.
- [x] Decide the product contract:
  - normalize aliases/case variants at ingress, then adapters receive only
    canonical keys; or
  - reject non-canonical source keys and document the contract.
- [x] If normalization remains public behavior, add/keep router tests proving
  aliases normalize before runtime.
- [x] Canonical-only adapter validation remains internal. Public router request
  models normalize supported aliases before runtime/adapters see the request.

Acceptance gates:

- [x] Public API behavior is tested: router request models normalize aliases at
  ingress and adapters receive canonical source keys.
- [x] OpenAPI remains stable.

### Phase 4: Source-Document Identity And Extraction Closure

Status: implemented

Why fourth:

- The source-document split is structurally clean, but two closure gaps remain:
  identity canonicalization and direct orchestration tests.

Implementation steps:

- [x] Add direct tests proving `record_hash(record)` and
  `source_document_record_hash(document)` match for the same selected record.
- [x] Cover at least one variant-aware source and one simple source.
- [x] Add `test_source_document_extraction_service.py` that tests
  `SourceDocumentExtractionService` directly, without going through
  `source_document_bridges.py`.
- [x] Test success, no-candidate, graph-write-failure, metadata update, and
  deduplicated seed entity summary behavior.

Acceptance gates:

- [x] Source-document deduplication cannot silently diverge from candidate
  record hashing.
- [x] Extraction-service orchestration is tested directly.

### Phase 5: Compatibility Facade Closure

Status: implemented for production callers; facade remains for compatibility

Why fifth:

- `source_document_bridges.py` is now small, but it is still a second import
  path. A facade without a removal rule becomes long-term architectural debt.

Implementation steps:

- [x] Inventory production imports of `source_document_bridges.py`.
- [x] Choose one path:
  - migrate production callers to focused modules and keep the facade only for
    tests/backward compatibility; or
  - keep the facade temporarily, document a removal deadline, and add an
    architecture test preventing new production imports.
- [x] Update docs and tests to reflect the chosen path.

Acceptance gates:

- [x] There is no ambiguous ownership between facade and focused modules.
- [x] New production code cannot grow the facade dependency by accident.

### Phase 6: Runtime Serialization Cleanup

Status: implemented; final service gates pending for this latest slice

Why sixth:

- Runtime still owns workspace snapshot and artifact serialization helpers.
  This is less risky than typed decisions, so it should happen after the
  decision contract is stable.

Implementation steps:

- [x] Move workspace snapshot construction to
  `evidence_selection_workspace_snapshot.py`.
- [x] Move source-plan artifact construction to
  `evidence_selection_source_plan_artifact.py` or into
  `evidence_selection_source_planning.py`.
- [x] Move proposal/review result serializers out of runtime if they remain
  large enough to obscure orchestration.

Acceptance gates:

- [x] Runtime is mostly run lifecycle, service invocation, progress, and final
  artifact persistence.
- [x] Snapshot/source-plan payload tests remain stable.

### Phase 7: Incremental Document Extraction Decomposition

Status: implemented; final service gates pending for this latest slice

Why last:

- `document_extraction.py` is the largest remaining module and has broad blast
  radius. It should be decomposed after the evidence-selection decision and
  source-document boundaries are stable.

Implementation steps:

- [x] Extract pure contracts/types first into `document_extraction_contracts.py`.
- [x] Extract prompt/schema assembly into `document_extraction_prompting.py`.
- [x] Extract LLM relation taxonomy into
  `document_extraction_relation_taxonomy.py`.
- [x] Extract entity label cleanup and graph resolution into
  `document_extraction_entities.py`.
- [x] Extract review-context scoring and draft-review metadata helpers into
  `document_extraction_review.py`.
- [x] Extract proposal draft assembly into `document_extraction_drafts.py`.
- [x] Extract diagnostics/error normalization into
  `document_extraction_diagnostics.py`.
- [x] Extract chat document-context summarization into
  `document_context_summary.py`.
- [x] Keep variant-aware extraction separate and verify it does not regress.

Acceptance gates:

- [x] `test_document_extraction.py` and
  `test_variant_aware_document_extraction.py` pass after each small extraction.
- [x] No public API, OpenAPI, migration, or generated artifact changes unless
  intentionally documented.

### Final Closeout Gates

Run these before calling the SRP hardening complete:

- [x] `venv/bin/ruff check` on touched files.
- [x] Focused unit tests for all new/changed modules.
- [x] `venv/bin/pytest services/artana_evidence_api/tests/unit/test_document_extraction.py services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py -q`
- [x] `make artana-evidence-api-service-checks`
- [x] `make service-checks`
- [x] `git diff --check`
- [x] Claude second-opinion review focused on remaining SRP gaps.
- [x] Confirm `coverage.xml` and unrelated user-tree changes are not included
  unless explicitly requested.

## Parallelization Plan

Can run in parallel:

- Phase 3 source-key public contract verification.
- Phase 4 source-document identity tests and extraction-service tests.
- Phase 5 source-document facade import inventory.
- Phase 7 document-extraction inventory, without editing until earlier phases
  stabilize.

Should be linear:

- Phase 1 typed decision models before Phase 2 unified deferral semantics.
- Phase 2 before Phase 6 runtime serialization cleanup.
- Phase 4 before Phase 5 if the facade migration depends on the final focused
  source-document service surface.
- Phase 7 after Phases 1-6 unless a very small contracts-only extraction is
  clearly independent.

## Test Plan

Focused tests to add or update:

- `services/artana_evidence_api/tests/unit/test_source_adapter_registry.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_handoffs.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_review_staging.py`
- `services/artana_evidence_api/tests/unit/test_source_document_entity_extraction.py`
- `services/artana_evidence_api/tests/unit/test_source_document_repository.py`
- `services/artana_evidence_api/tests/unit/test_source_document_graph_writer.py`
- `services/artana_evidence_api/tests/unit/test_source_document_extraction_service.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_candidates.py`
- Existing:
  - `test_source_boundary_contract.py`
  - `test_evidence_selection_runtime.py`
  - `test_evidence_selection_router.py`
  - `test_evidence_selection_extraction_policy.py`
  - `test_source_document_bridges.py`
  - `test_document_extraction.py`
  - `test_variant_aware_document_extraction.py`

Verification gates:

- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_adapter_registry.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_review_staging.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_handoffs.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_document_bridges.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_document_extraction_service.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_candidates.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_document_extraction.py services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py -q`
- `make artana-evidence-api-service-checks`
- `make service-checks`
- Claude second-opinion review before final closeout.

## Progress Checklist

### Done

- [x] Datasource registry exists.
- [x] Source record policy exists.
- [x] Source query playbooks exist.
- [x] Source plan validation exists.
- [x] Evidence-selection extraction policy exists.
- [x] Variant-aware extraction has typed contracts and a focused adapter.
- [x] Single typed source adapter registry exists.
- [x] Candidate screening module exists.
- [x] Candidate handoff module exists.
- [x] Candidate decisions are typed internally and serialized only at
  artifact/API result boundaries.
- [x] Per-search budget, run handoff budget, shadow mode, and missing-search
  deferrals use typed decision/deferral fields.
- [x] Review staging module exists.
- [x] Source-document selected-record identity helper exists for deduplication.
- [x] Source-document models and deterministic entity extraction were split out
  behind compatibility imports.
- [x] Source-document repository, graph writer, and extraction service were
  split out behind compatibility imports.
- [x] Production callers no longer import `source_document_bridges.py`; the
  facade remains only as a compatibility import path covered by tests.
- [x] Direct source-document extraction-service orchestration tests cover
  success, no-candidate, and graph-write-failure paths.
- [x] Claude second-opinion follow-up fixes were applied for adapter guardrails,
  lazy adapter construction, source-document dedup ownership, stable candidate
  context, handoff-budget demotion, and shadow relevance preservation.
- [x] Fresh Claude second-opinion pass found no hard blocker to closing this
  Phases 1-5 slice. Follow-up hardening improved graph-write diagnostics,
  replaced graph-writer runtime `assert`s with explicit exceptions, removed a
  handoff-budget sort sentinel, and added candidate-screening tests for missing
  searches, weak matches, and explicit exclusion matches.
- [x] Runtime workspace snapshots, source-plan artifacts, and proposal/review
  result serialization were extracted out of `evidence_selection_runtime.py`.
- [x] Document extraction contracts/types, prompt schemas, review-context and
  draft-building helpers were extracted into focused modules.

### Needs Implementation

- [x] No remaining implementation tasks are known for this SRP hardening plan.

### Needs Verification

- [x] No source-specific behavior remains hidden in runtime modules after
  adapter migration for metadata, query playbook, record policy, extraction
  policy, and live-search validation.
- [x] Public behavior for non-canonical source-key aliases is intentionally
  documented or normalized at ingress.
- [x] Source-record hash and source-document hash canonicalization match.
- [x] Source-document extraction service has direct tests outside the bridge
  facade.
- [x] Runtime file shrinks and mostly orchestrates evidence-selection services.
- [x] Runtime serialization helpers live outside
  `evidence_selection_runtime.py`.
- [x] Source-document bridge no longer mixes persistence, graph writes, and
  metadata updates.
- [x] Document extraction contracts, prompt schemas, and draft building live
  outside `document_extraction.py`.
- [x] Document extraction diagnostics/status normalization lives outside
  `document_extraction.py`.
- [x] Public API/OpenAPI remains stable unless explicitly changed.
- [x] Existing evidence-selection, source-document, document-extraction, and
  variant-aware extraction tests pass.

### Out Of Scope For This Plan

- New external datasource integrations.
- Graph-service schema changes.
- Frontend/UI work.
- Changing user-facing endpoint names.
- Changing review approval semantics.
- Committing generated `coverage.xml` unless explicitly requested.

## Verification Log

- Latest SRP extraction implementation
  - Result: extracted runtime workspace snapshots to
    `evidence_selection_workspace_snapshot.py`, source-plan artifacts to
    `evidence_selection_source_plan_artifact.py`, proposal/review result
    serialization to `evidence_selection_result_serialization.py`, document
    contracts to `document_extraction_contracts.py`, prompts and output schemas
    to `document_extraction_prompting.py`, LLM relation taxonomy to
    `document_extraction_relation_taxonomy.py`, entity label/graph resolution
    helpers and LLM entity-label cleanup to
    `document_extraction_entities.py`, review-context scoring to
    `document_extraction_review.py`, draft assembly to
    `document_extraction_drafts.py`, diagnostics builders to
    `document_extraction_diagnostics.py`, and chat document-context summaries
    to `document_context_summary.py`.
- `wc -l services/artana_evidence_api/document_extraction.py services/artana_evidence_api/document_extraction_contracts.py services/artana_evidence_api/document_extraction_prompting.py services/artana_evidence_api/document_extraction_relation_taxonomy.py services/artana_evidence_api/document_extraction_entities.py services/artana_evidence_api/document_extraction_review.py services/artana_evidence_api/document_extraction_drafts.py services/artana_evidence_api/document_extraction_diagnostics.py services/artana_evidence_api/document_context_summary.py services/artana_evidence_api/evidence_selection_runtime.py services/artana_evidence_api/evidence_selection_workspace_snapshot.py services/artana_evidence_api/evidence_selection_source_plan_artifact.py services/artana_evidence_api/evidence_selection_result_serialization.py`
  - Result: `document_extraction.py` is 1,007 lines,
    `document_extraction_contracts.py` is 195 lines,
    `document_extraction_prompting.py` is 164 lines,
    `document_extraction_relation_taxonomy.py` is 272 lines,
    `document_extraction_entities.py` is 363 lines,
    `document_extraction_review.py` is 405 lines,
    `document_extraction_drafts.py` is 177 lines,
    `document_extraction_diagnostics.py` is 109 lines,
    `document_context_summary.py` is 32 lines,
    `evidence_selection_runtime.py` is 715 lines,
    `evidence_selection_workspace_snapshot.py` is 234 lines,
    `evidence_selection_source_plan_artifact.py` is 116 lines, and
    `evidence_selection_result_serialization.py` is 39 lines.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_document_extraction_modules.py services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py -q`
  - Result: passed, `10 passed`. These tests directly cover the newly extracted
    document and evidence-selection artifact modules.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_document_extraction_modules.py services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py services/artana_evidence_api/tests/unit/test_evidence_selection_router.py services/artana_evidence_api/tests/unit/test_evidence_selection_model_planner.py services/artana_evidence_api/tests/unit/test_document_extraction.py services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py services/artana_evidence_api/tests/unit/test_documents_router.py services/artana_evidence_api/tests/unit/test_output_schema_registry.py -q`
  - Result: passed with one existing FastAPI deprecation warning.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_document_extraction.py services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py -q`
  - Result: passed, `32 passed`.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py services/artana_evidence_api/tests/unit/test_evidence_selection_router.py services/artana_evidence_api/tests/unit/test_evidence_selection_model_planner.py services/artana_evidence_api/tests/unit/test_document_extraction.py services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py services/artana_evidence_api/tests/unit/test_documents_router.py services/artana_evidence_api/tests/unit/test_output_schema_registry.py -q`
  - Result: passed with one existing FastAPI deprecation warning.
- `venv/bin/ruff check` on touched implementation files
  - Result: passed.
- `make artana-evidence-api-static-checks`
  - Result: passed. Ruff, mypy, boundary check, OpenAPI check, and
    architecture-size check passed.
- `make artana-evidence-api-service-checks`
  - Result: passed. Evidence API lint, type-check, boundary check, OpenAPI
    check, architecture-size check, migrations, and database-backed pytest
    passed. Live external API and localhost service checks remained skipped by
    their normal opt-in guards.
- `make service-checks`
  - Result: passed. Graph-service checks, generated contract checks, Evidence
    API checks, OpenAPI checks, architecture-size checks, migrations, and
    database-backed tests passed. Coverage was 88.43%, above the required 86%.
    Live external API and localhost service checks remained skipped by their
    normal opt-in guards. This run regenerated `coverage.xml`, which remains
    generated churn unless explicitly included.
- `git diff --check`
  - Result: passed.
- Claude second-opinion review after user-requested rerun
  - Result: flagged that this plan had pre-claimed the final Claude result and
    that generated `coverage.xml` was still dirty. Follow-up fixes removed the
    pre-claimed final result from this tracker, kept the Claude closeout gate
    open until rerun, removed the generated `coverage.xml` diff, dropped
    `resolve_graph_entity_label` from the document-extraction facade `__all__`,
    and added direct relation-taxonomy tests.
- Claude second-opinion final blocker check
  - Result: confirmed `coverage.xml` was clean, `resolve_graph_entity_label` was
    removed from the document-extraction facade `__all__`, and direct
    relation-taxonomy tests existed. The only remaining blocker was the
    current-status sentence pre-claiming Claude completion while the closeout
    checkbox was open; this tracker now records Claude as a separate completed
    closeout gate.
- `wc -l services/artana_evidence_api/evidence_selection_runtime.py services/artana_evidence_api/source_document_bridges.py services/artana_evidence_api/document_extraction.py services/artana_evidence_api/evidence_selection_candidate_screening.py services/artana_evidence_api/evidence_selection_review_staging.py services/artana_evidence_api/source_document_repository.py services/artana_evidence_api/source_document_graph_writer.py`
  - Result: after this SRP pass, `evidence_selection_runtime.py` is 1,030
    lines, `source_document_bridges.py` is 87 lines, and
    `document_extraction.py` remains 2,420 lines. Focused extracted modules are
    smaller: candidate contracts are 241 lines, candidate screening is 554
    lines, candidate handoffs are 90 lines, review staging is 232 lines,
    source-document extraction service is 209 lines, source-document repository
    is 388 lines, and source-document graph writer is 207 lines.
- `rg` inventory of current boundaries
  - Result: confirmed live source-policy, source-playbook, extraction-policy,
    candidate-screening, review-staging, source-document bridge, and
    variant-aware extraction paths listed above.
- Documentation update
  - Result: this plan replaces the empty `docs/plan.md` with the SRP hardening
    tracker and now records the implementation status and verification results.
- Source adapter implementation
  - Result: added `services/artana_evidence_api/source_adapters.py` and
    `services/artana_evidence_api/tests/unit/test_source_adapter_registry.py`.
    The adapter registry composes source definition, query playbook, record
    policy, extraction policy, live-search validation, and candidate context for
    every direct-search source. Follow-up hardening added lazy adapter registry
    construction, canonical-source-key validation, stable candidate-context
    keys, and an architecture test that blocks production callers from
    bypassing the adapter for source-owned helper functions.
- Candidate/review staging implementation
  - Result: extracted candidate contracts, screening, handoff creation, and
    review staging into focused modules. `evidence_selection_runtime.py` now
    delegates these responsibilities and dropped from about 1,797 lines to 1,038
    lines. Handoff-budget demotion now lives in candidate screening, and shadow
    deferrals preserve the selected record relevance label while adding a
    `shadow_decision` marker.
- Source-document split implementation
  - Result: moved source-document lifecycle models/protocols into
    `source_document_models.py`, SQLAlchemy persistence into
    `source_document_repository.py`, deterministic entity extraction into
    `source_document_entity_extraction.py`, graph entity/observation writes
    into `source_document_graph_writer.py`, and extraction orchestration plus
    metadata status updates into `source_document_extraction_service.py`.
    `source_document_bridges.py` remains the compatibility facade and dropped
    from about 1,020 lines to 87 lines.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py services/artana_evidence_api/tests/unit/test_evidence_selection_review_staging.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py services/artana_evidence_api/tests/unit/test_evidence_selection_router.py services/artana_evidence_api/tests/unit/test_evidence_selection_model_planner.py services/artana_evidence_api/tests/unit/test_worker.py -q`
  - Result: passed with one existing FastAPI deprecation warning.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_document_entity_extraction.py services/artana_evidence_api/tests/unit/test_source_document_repository.py services/artana_evidence_api/tests/unit/test_source_document_graph_writer.py services/artana_evidence_api/tests/unit/test_source_document_bridges.py -q`
  - Result: passed, `10 passed`.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_handoffs.py services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py services/artana_evidence_api/tests/unit/test_evidence_selection_review_staging.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_document_entity_extraction.py services/artana_evidence_api/tests/unit/test_source_document_repository.py services/artana_evidence_api/tests/unit/test_source_document_graph_writer.py services/artana_evidence_api/tests/unit/test_source_document_bridges.py -q`
  - Result: passed, `59 passed`.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py services/artana_evidence_api/tests/unit/test_evidence_selection_plan_validation.py services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_model_planner.py services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_handoffs.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py services/artana_evidence_api/tests/unit/test_evidence_selection_router.py services/artana_evidence_api/tests/unit/test_source_search_handoff.py -q`
  - Result: passed after Claude second-opinion follow-up fixes, with one
    existing FastAPI deprecation warning.
- `venv/bin/ruff check` on touched implementation and focused test files
  - Result: passed.
- `make artana-evidence-api-service-checks`
  - Result: passed. Evidence API lint/type/boundary/OpenAPI/architecture-size
    checks passed, database migrations applied against an ephemeral test
    database, and the Evidence API pytest suite passed. Live external API and
    localhost service checks remained skipped by their normal opt-in guards.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_candidates.py services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_handoffs.py services/artana_evidence_api/tests/unit/test_evidence_selection_review_staging.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py services/artana_evidence_api/tests/unit/test_evidence_selection_router.py services/artana_evidence_api/tests/unit/test_evidence_selection_benchmarks.py services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py services/artana_evidence_api/tests/unit/test_source_document_entity_extraction.py services/artana_evidence_api/tests/unit/test_source_document_extraction_service.py services/artana_evidence_api/tests/unit/test_source_document_graph_writer.py services/artana_evidence_api/tests/unit/test_source_document_repository.py services/artana_evidence_api/tests/unit/test_source_document_bridges.py -q`
  - Result: passed. This validates typed candidate decisions, unified deferral
    semantics, source-key ingress normalization, source-document identity
    hashing, direct extraction-service orchestration, and the production
    facade-import guardrail.
- `make artana-evidence-api-service-checks`
  - Result: passed after the typed candidate decision and source-document
    facade-closure updates. Evidence API lint, type-check, boundary, OpenAPI,
    architecture-size, migrations, and pytest passed. Live external API and
    localhost service checks remained skipped by their normal opt-in guards.
- `make service-checks`
  - Result: passed. Graph-service checks, generated contract checks,
    Evidence API checks, OpenAPI checks, architecture-size checks, migrations,
    and database-backed tests passed. Coverage was 87.78%, above the required
    86%. Live external API and localhost service checks remained skipped by
    their normal opt-in guards. This run regenerated `coverage.xml`, which
    remains treated as generated churn unless explicitly included.
- Claude second-opinion review after implementation
  - Result: flagged actionable issues around source-document graph-write failure
    signaling, deterministic handoff-budget ordering, duplicated decision
    taxonomies, normal records emitting shadow-only payload fields, and missing
    regression tests for those behaviors. Follow-up fixes now mark graph-write
    failures as `DocumentExtractionStatus.FAILED`, surface the warning in
    `SourceDocumentExtractionSummary.errors` and
    `entity_recognition_ingestion_errors`, make handoff-budget ranking
    deterministic with explicit tie-breakers, use enum decision/relevance
    values as the single internal taxonomy, omit
    `would_have_been_selected` from normal non-shadow payloads, preserve
    original relevance on selected-to-skipped duplicate demotion, and add/update
    focused tests for these cases.
- Fresh Claude second-opinion review after follow-up fixes
  - Result: no hard blocker to closing the Phases 1-5 SRP slice. The review
    recommended extra polish around graph-write diagnostics, retry semantics for
    failed source documents, replacing graph-writer `assert`s, avoiding a
    handoff-budget sort sentinel, and verifying several candidate-screening
    regressions. Follow-up fixes included exception messages in graph-write
    diagnostics, replaced graph-writer `assert`s with explicit `ValueError`
    checks, removed the sort sentinel, renamed the local source-record hash
    parameter to avoid shadowing, and added tests for missing-source-search
    deferral, weak-match human-review skips, and explicit-exclusion skips. The
    retry policy for `FAILED` source documents remains a follow-up operational
    decision rather than a blocker for this slice.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py services/artana_evidence_api/tests/unit/test_source_document_extraction_service.py services/artana_evidence_api/tests/unit/test_source_document_bridges.py services/artana_evidence_api/tests/unit/test_source_document_graph_writer.py services/artana_evidence_api/tests/unit/test_evidence_selection_candidates.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py -q`
  - Result: passed after the fresh Claude follow-up fixes.
- `make artana-evidence-api-service-checks`
  - Result: passed after the fresh Claude follow-up fixes. Evidence API lint,
    type-check, boundary, OpenAPI, architecture-size, migrations, and pytest
    passed. Live external API and localhost service checks remained skipped by
    their normal opt-in guards.
- `make service-checks`
  - Result: passed after the fresh Claude follow-up fixes. Graph-service checks,
    generated contract checks, Evidence API checks, OpenAPI checks,
    architecture-size checks, migrations, and database-backed tests passed.
    Coverage was 87.78%, above the required 86%. Live external API and localhost
    service checks remained skipped by their normal opt-in guards. This run
    regenerated `coverage.xml`, which remains treated as generated churn unless
    explicitly included.
- Claude second-opinion review
  - Result: review flagged adapter-bypass guardrails, source-document dedup
    ownership, import-time adapter registry construction, canonical source-key
    validation, unstable candidate-context shape, runtime handoff-budget logic,
    and shadow-mode relevance-label loss. Follow-up fixes added the adapter
    architecture test, moved source-document selection identity out of
    candidate screening, made adapter registry construction lazy, rejected
    non-canonical live-search keys at the adapter boundary, always emits
    `provider_external_id`, moved handoff-budget demotion into candidate
    screening, and preserved original relevance labels for shadow deferrals.
    `make artana-evidence-api-service-checks`, `make service-checks`, and
    `git diff --check` passed after those fixes.
- Claude second-opinion review rerun
  - Result: no immediate broken-code finding, but the review correctly flagged
    remaining completion gaps before calling the SRP hardening fully done:
    deferred-record label/demotion semantics are inconsistent, typed candidate
    decisions are still missing, shadow-mode demotion still lives in runtime,
    canonical source-key behavior needs explicit public-contract verification,
    source-document hash canonicalization needs a direct regression test,
    `source_document_bridges.py` needs a deprecation/migration guardrail, and
    `source_document_extraction_service.py` needs direct orchestration tests.
    These are now tracked above as remaining implementation/verification work.
