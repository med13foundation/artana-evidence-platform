# Datasource Plugin Encapsulation Plan

Archived status date: April 30, 2026.

This is a historical implementation tracker for the datasource/source-plugin
encapsulation work. Use the current developer guide at
`docs/source_plugins.md` and the current roadmap at
`docs/remaining_work_priorities.md` for active guidance.

## Purpose

Move from the current adapter-facade architecture to true per-source plugins.

The current implementation is already strongly encapsulated for production
callers: callers use `source_adapters.py` and do not receive raw source policy,
query playbook, or extraction policy objects. This plan covers the next,
larger hardening step: each datasource should own its metadata, query planning,
validation, execution, record normalization, extraction/review policy, and
handoff policy together.

## Current Live State

Code-backed facts from the current repository:

- `services/artana_evidence_api/source_adapters.py`
  - Public adapter boundary exists.
  - `EvidenceSourceAdapter` exposes adapter-level behavior.
  - Concrete `_PluginSourceAdapter` wraps a source plugin for every
    direct-search source.
  - `SourceCandidateContext` is typed and serialized at artifact boundaries.
- `services/artana_evidence_api/source_plugins/`
  - Holds typed plugin contracts, helper functions, an explicit ordered
    registry, one source-owned plugin module per direct-search source, and
    non-direct evidence-source plugins for MONDO, HGNC, PDF, and text.
  - Direct-search plugins cover PubMed, MARRVEL, ClinVar, DrugBank,
    AlphaFold, UniProt, ClinicalTrials.gov, MGI, and ZFIN.
  - Authority plugins cover MONDO and HGNC.
  - Document-ingestion plugins cover PDF and text.
- `services/artana_evidence_api/source_registry.py`
  - Keeps public compatibility helpers, alias normalization, source-key list
    views, and registry invariants.
  - Public `SourceDefinition` values are now plugin-owned and returned through
    plugin registry views.
- `services/artana_evidence_api/source_policies.py`
  - Is now a plugin-backed compatibility facade for older record-policy
    imports.
  - It no longer keeps central per-source record normalization or provider-ID
    maps.
- `services/artana_evidence_api/evidence_selection_source_playbooks.py`
  - Is now a plugin-backed compatibility facade for query planning imports.
  - It no longer keeps central per-source query-playbook maps.
- `services/artana_evidence_api/evidence_selection_extraction_policy.py`
  - Is now a plugin-backed compatibility facade for extraction/review policy
    imports.
  - It no longer keeps a central per-source extraction-policy map.
- `services/artana_evidence_api/evidence_selection_source_search.py`
  - Is now a thin live-search runner.
  - It enforces canonical source keys and dispatches execution through source
    plugins via `source_plugin_for_execution`.
  - It no longer keeps per-source handler maps or live-search validator maps.
- `services/artana_evidence_api/source_plugins/registry.py`
  - Keeps explicit plugin listing, typed registry views, validation, and
    runner-scoped execution factory registration.
  - PubMed and MARRVEL execution dependency wrapping is now source-owned by
    plugin-local factory functions; the registry no longer branches on those
    source keys.
- `services/artana_evidence_api/direct_source_search.py`
  - Still owns public direct-source request/response schemas, persistence
    envelopes, route-compatible helper functions, and gateway protocol
    contracts.
  - This is retained for public API/import stability. Source-specific planning,
    validation, execution entrypoints, normalization, review policy, candidate
    context, and handoff policy are plugin-owned.
- `services/artana_evidence_api/source_search_handoff.py`
  - Uses adapter-backed source behavior for durable source-search handoff.
- `services/artana_evidence_api/source_route_contracts.py`
  - Holds the typed public route plugin contract, typed route declaration
    contract, and generic `DirectSourceRouteDependencies` bag.
- `services/artana_evidence_api/source_route_dependencies.py`
  - Collects FastAPI dependencies for the generic source-key route and returns
    a generic `DirectSourceRouteDependencies` bag.
  - The route contract no longer exposes one public field per datasource.
- `services/artana_evidence_api/source_route_helpers.py`
  - Holds shared route-edge mechanics: generic request-model validation,
    stored-result lookup, JSON encoding, and gateway-unavailable errors.
- `services/artana_evidence_api/source_route_plugins.py`
  - Is the only public direct-source route plugin registry.
  - It explicitly registers typed FastAPI routes in the same order as
    `direct_search_source_keys()`.
  - It also owns generic `/sources/{source_key}/searches` create/get dispatch.
  - Validation fails closed if the route plugin list drifts from the
    direct-search source registry order.
- `services/artana_evidence_api/source_route_*.py`
  - Focused route modules own the concrete public typed source-search route
    declarations for PubMed, MARRVEL, ClinVar, DrugBank, AlphaFold, UniProt,
    ClinicalTrials.gov, MGI, and ZFIN.
  - These modules own route paths, request/response model binding, route-level
    dependency declarations, OpenAPI summaries, generic-route payload parsing,
    source gateway execution, and compatibility response shaping.
  - `routers/v2_public.py` no longer declares concrete direct-source route
    paths; it only calls `register_direct_source_typed_routes(router)` before
    registering the generic source-search routes, then delegates generic
    source-search create/get through `source_route_plugins.py`.
  - Shared route validation formatting lives in `source_route_errors.py`.
  - Route-specific behavior remains public API compatibility only; source
    planning, validation, normalization, candidate context, and handoff policy
    remain source-plugin/route-plugin owned.

Approximate relevant code size:

- `source_registry.py`: 225 lines
- `source_plugins/`: about 4,900 lines across focused modules, including
  shared contracts, helpers, and one file per direct-search source
- `source_adapters.py`: 409 lines
- `source_policies.py`: 86 lines
- `evidence_selection_source_playbooks.py`: 108 lines
- `evidence_selection_extraction_policy.py`: 83 lines
- `evidence_selection_source_search.py`: 116 lines
- `direct_source_search.py`: 1,119 lines
- `source_search_handoff.py`: 1,276 lines
- public source-route compatibility surface: about 2,500 lines across
  `source_route_contracts.py`, `source_route_dependencies.py`,
  `source_route_helpers.py`, `source_route_plugins.py`,
  `source_route_errors.py`, and focused `source_route_*.py` source modules

Total directly adjacent surface: about 10,900 lines, including source plugin
modules, stable public direct-source/search-handoff surfaces, and the public
source-route plugin edge.

## Target Architecture

Each evidence source should be represented by one typed plugin object or module,
but not every evidence source uses the same contract.

Direct-search source plugin responsibilities:

- Canonical source key and aliases.
- Public source metadata and capability flags.
- Request and result schema references.
- Query payload planning.
- Live source-search payload validation.
- Live source-search execution or execution delegation.
- Result record shaping.
- Record normalization.
- Provider external ID extraction.
- Variant-aware recommendation.
- Extraction/review staging policy.
- Proposal and review-item summary text.
- Candidate context construction.
- Handoff eligibility and handoff target policy.

Authority-source plugin responsibilities:

- Canonical source key and aliases.
- Public source metadata and capability flags.
- Identifier normalization.
- Entity grounding.
- Authority-reference construction.
- Provenance for grounded IDs and labels.
- Grounding limitations.

Document-ingestion source plugin responsibilities:

- Canonical source key and aliases.
- Public source metadata and capability flags.
- Input validation for user-provided documents or text.
- Document metadata normalization.
- Extraction-context construction.
- Evidence extraction entrypoint selection.
- Ingestion limitations.

Logical target layout:

```text
services/artana_evidence_api/source_plugins/
  __init__.py
  contracts.py
  registry.py
  direct_search/
    pubmed.py
    marrvel.py
    clinvar.py
    clinical_trials.py
    uniprot.py
    alphafold.py
    drugbank.py
    mgi.py
    zfin.py
  authority/
    mondo.py
    hgnc.py
  ingestion/
    pdf.py
    text.py
```

Current implementation note: direct-search plugins remain flat under
`source_plugins/` to avoid pure file-move churn during the behavior migration.
Authority and document-ingestion plugins now use dedicated
`source_plugins/authority/` and `source_plugins/ingestion/` packages, matching
the contract taxonomy in `source_plugins/contracts.py`.

The exact module paths can change, but the non-negotiable invariant is:

> To understand one datasource, a developer should mostly read one plugin file
> and its focused tests, not five central source maps.

## Anti-Monolith Rules

Follow these rules during implementation:

- Do not create one giant `source_plugins.py` file.
- Keep shared plugin contracts in `source_plugins/contracts.py`.
- Keep plugin discovery/ordering in `source_plugins/registry.py`.
- Keep source-specific behavior in one source-specific file.
- Keep shared helper functions tiny and generic; if a helper knows about a
  specific source key, it belongs in that source plugin.
- Register plugins by explicit listing in `source_plugins/registry.py`.
  Do not use `@register_plugin` decorators, class-body registration, or import
  side effects for discovery.
- Preserve existing public API behavior unless a contract change is explicitly
  documented and regenerated.
- Move behavior in thin vertical slices, one source or one execution pattern at
  a time.
- Keep compatibility wrappers temporary and guarded by boundary tests.
- Do not remove the current adapter boundary until plugin parity tests pass for
  all direct-search sources.

## Execution Estimate

Working estimate: **3-5 weeks for one engineer** if the migration is mostly
internal and public schemas stay stable. Plan for **5-7 weeks** if request or
response schemas move, PubMed/MARRVEL require new live integration coverage, or
`direct_source_search.py` and `source_search_handoff.py` need deeper splitting
than expected. The six agents below reduce discovery and review time; the
estimate still assumes one lead engineer owns integration and final code
changes.

This is a large refactor because execution, validation, result shaping,
metadata, query planning, normalization, and extraction policy are currently
centralized across multiple modules. PubMed and MARRVEL are special enough that
they should be planned separately from the more mechanical gateway-style
sources.

## Required Decisions Before Phase 1

Resolve these before writing plugin contracts:

- [x] Decide whether non-direct sources are plugins:
  - MONDO and HGNC are authority/grounding plugins. They create evidence
    support by grounding disease and gene entities to normalized IDs,
    labels, aliases, and provenance. They do not create clinical/scientific
    claims by themselves.
  - PDF and text are document-ingestion plugins. They create evidence by
    validating user-provided content, normalizing document metadata, and
    returning extraction context that orchestration passes to document
    extraction and review.
  - Direct-search, authority, and ingestion sources use separate contracts
    because they create evidence through different paths.
- [x] Decide protocol shape:
  - Preferred: narrow protocols composed into one plugin object:
    - `SourceMetadataPlugin`
    - `SourcePlanningPlugin`
    - `DirectSearchSourcePlugin`
    - `SourceExecutionPlugin`
    - `SourceRecordPlugin`
    - `SourceReviewPlugin`
    - `SourceHandoffPlugin`
    - `AuthoritySourcePlugin`
    - `DocumentIngestionSourcePlugin`
  - Avoid one oversized "everything" protocol unless the implementation proves
    it stays readable.
- [x] Decide rollout strategy:
  - Preferred: plugin code lands behind the existing adapter boundary.
  - Direct-search plugins landed first behind `source_adapters.py`.
  - Authority and ingestion plugins should land next as separate registries or
    typed registry views; they should not be added to the direct-search
    adapter registry unless they support live source-search.

## Security And Contract Invariants

Plugins must preserve existing backend invariants:

- Plugin modules must not open database sessions directly.
- Plugin modules must not bypass graph RLS session context.
- Plugin modules must not import graph database internals.
- Plugin modules must not bypass PHI encryption or source-document encryption
  helpers.
- Plugin modules should not own persistence; persistence stays in stores,
  repositories, or orchestration services.
- Plugin modules must not import routers, SQLAlchemy models, stores, graph
  database modules, RLS bypass helpers, or source-document persistence modules.
- OpenAPI output must remain stable unless a phase explicitly documents a
  public contract change.
- If public request/response schemas change, run and record
  `make artana-evidence-api-contract-check`.
- New plugin code must avoid `Any`; use typed protocols, dataclasses, Pydantic
  models, or concrete service-local types.
- Plugins should receive gateway/discovery execution dependencies through
  explicit constructor arguments, factories, or execution context objects.
  Plugins should not reach into router or persistence layers to find those
  dependencies.

## File Decomposition Plan

### `direct_source_search.py`

Stays for this refactor:

- Durable direct-source search store contracts and implementations.
- Shared source-search run persistence models.
- Shared capture envelope helpers.
- Public request/response schemas used by the FastAPI contract.
- Route-compatible gateway helper functions kept for import and schema
  stability.

Moved into source plugins:

- Per-source planning and live-search validation entrypoints.
- Evidence-selection execution dispatch.
- PubMed and MARRVEL source-result shaping for the evidence-selection runner.
- Per-source normalization, provider-ID, variant-aware, extraction/review, and
  candidate-context behavior.

Deferred non-gap cleanup:

- Public request/response models can move into plugin modules later only if
  compatibility imports and OpenAPI prove no public schema drift.
- Route-compatible `run_*_direct_search` helpers can be moved later as file
  decomposition work. They are no longer used as central orchestration maps.

Guardrail:

- If request/response classes move, keep compatibility imports until OpenAPI
  and route tests prove there is no public schema drift.

### `evidence_selection_source_search.py`

Likely stays:

- Shared live-search runner orchestration.
- Shared execution input/output contracts.
- Shared error type.

Moved into source plugins:

- Per-source live-search validators.
- Per-source execution handlers.
- PubMed direct-record shaping.
- MARRVEL panel-record and HGVS/variant shaping.

Guardrail:

- The central runner should dispatch through plugin methods, not a source-key
  handler map.

### `source_search_handoff.py`

Likely stays:

- Durable handoff persistence.
- Handoff request/response API models.
- Idempotency and transaction handling.

Moved into source plugins:

- Handoff eligibility.
- Handoff target kind.
- Provider external ID behavior.
- Variant-aware recommendation behavior.
- Normalized source-record behavior.

Guardrail:

- Handoff orchestration can ask the plugin/adapter for source behavior, but it
  should not grow per-source conditionals.

## Parity Matrix

Before removing any legacy central-map entry, each migrated source must prove
plugin parity against the legacy behavior:

| Behavior | Required parity proof |
| --- | --- |
| Source metadata | Same source key, display name, family, capabilities, schema refs |
| Aliases | Same public aliases normalize to the same canonical key |
| Query planning | Same query payload for frozen source intents |
| Live validation | Same accepted and rejected payloads |
| Execution | Same stored capture shape for mocked gateway/discovery results |
| Record normalization | Same normalized record for frozen fixture records |
| Provider ID | Same provider external ID for fixture records |
| Variant-aware hint | Same true/false result for variant and non-variant fixtures |
| Extraction policy | Same proposal type, review type, limitations, normalized fields |
| Candidate context | Same serialized candidate context keys and values |
| Handoff policy | Same target kind and eligibility |

Parity tests should live next to each plugin test while legacy code still
exists. Remove legacy entries only after these tests pass.

## Progress Checklist

Status legend:

- `[x]` done
- `[ ]` remaining
- `[~]` in progress
- `[?]` needs design decision

## Subagent Orchestration

Use six parallel agents for discovery and implementation planning, with the lead
agent owning integration, conflict resolution, final test gates, and updates to
this plan.

The six agents are discovery/design scouts unless a later implementation phase
assigns disjoint write ownership explicitly. The lead agent owns final file
edits, integration, and test gates unless a phase says otherwise.

### Agent 1: Plugin Contract Scout

Scope:

- `services/artana_evidence_api/source_plugins/contracts.py`
- Contract/protocol split.
- Typed execution input/output shape.
- Anti-monolith protocol design.

Deliverables:

- Recommended narrow protocol set.
- Required dataclasses/protocols/Pydantic models.
- Contract test plan.
- Risks before Phase 1 implementation.

### Agent 2: Registry And Ordering Scout

Scope:

- `services/artana_evidence_api/source_registry.py`
- `services/artana_evidence_api/source_adapters.py`
- Source aliases, ordering, and compatibility wrappers.

Deliverables:

- Deterministic plugin registry design.
- Source ordering and alias preservation checks.
- Drift-check strategy.
- Registry compatibility risk list.

### Agent 3: Gateway Sources Scout

Scope:

- ClinVar
- ClinicalTrials.gov
- UniProt
- AlphaFold
- DrugBank
- MGI
- ZFIN
- Gateway portions of `direct_source_search.py`.

Deliverables:

- Source-by-source migration complexity.
- Shared gateway plugin pattern.
- Functions/models that move into plugins.
- Direct-source request/response model and runner decomposition plan.
- Per-source tests and commands.

### Agent 4: PubMed Plugin Scout

Scope:

- PubMed metadata, query planning, validation, execution, result shaping,
  normalization, extraction policy, and handoff policy.

Deliverables:

- PubMed-specific migration plan.
- PubMed result-shaping and source-capture invariants.
- PubMed tests and public-schema risks.

### Agent 5: MARRVEL Plugin Scout

Scope:

- MARRVEL metadata, query planning, panel defaults, validation, execution,
  panel result shaping, HGVS/variant derivation, normalization, extraction
  policy, and handoff policy.

Deliverables:

- MARRVEL-specific migration plan.
- Panel/HGVS/variant-aware invariants.
- MARRVEL tests and public-schema risks.

### Agent 6: Test And Guardrail Scout

Scope:

- Plugin parity tests.
- Source boundary tests.
- AST source-map detection.
- Anti-monolith checks.
- Verification command matrix.
- `source_search_handoff.py` source-behavior decomposition guardrails.

Deliverables:

- Test and guardrail plan.
- Exact pytest/make commands by phase.
- Gaps that must be closed before deleting central maps.

### Phase Ownership Notes

- Phase 1 owner: lead + Agent 1.
- Phase 2 owner: lead + Agent 2.
- Phase 3 owner: lead + Agent 3.
- Phase 4 owner: lead + Agent 4.
- Phase 5 owner: lead + Agent 5.
- Phase 6 owner: lead + Agent 2.
- Phase 7 owner: lead + Agent 2 + Agent 6.
- Test/guardrail ownership across all phases: lead + Agent 6.
- `direct_source_search.py` decomposition: Agent 3 scouts source-specific
  runner/model movement; lead owns implementation.
- `source_search_handoff.py` decomposition: Agent 6 scouts guardrails; lead
  owns implementation.

### Lead Agent Responsibilities

- Keep file ownership disjoint during implementation.
- Prevent overlapping edits to the same plugin files.
- Integrate subagent findings into this tracker.
- Run focused tests after each phase.
- Run `make artana-evidence-api-service-checks` before phase closeout.
- Run `make service-checks` before final closeout.
- Ask Claude for second-opinion review at the Phase 1, Phase 7, and final
  closeout gates.

### Phase 0: Baseline And Guardrails

Goal: freeze the current safe adapter boundary before plugin migration starts.

Phase 0 is blocking. Do not start Phase 1 until the baseline commands, service
checks, and live-test skip notes are recorded.

- [x] Adapter boundary exists for production callers.
- [x] Concrete adapter is private.
- [x] Candidate context is typed.
- [x] Source helper bypasses are guarded by AST boundary tests.
- [x] Record current focused baseline test commands and results.
- [x] Record current `make artana-evidence-api-service-checks` result.
- [x] Record current `make service-checks` result.
- [x] Add a plan note for any existing skipped live tests so they are not
  confused with regressions.

Acceptance gates:

- Required Decisions Before Phase 1 are resolved and recorded.
- Baseline command results and live-test skip notes are recorded in the
  Verification Log.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py -q`
- `make artana-evidence-api-service-checks`
- `make service-checks`
- `git diff --check`

### Phase 1: Define Plugin Contracts

Goal: define the source-plugin interface without migrating every source yet.

Public schema impact: no.

- [x] Add `services/artana_evidence_api/source_plugins/contracts.py`.
- [x] Define narrow typed plugin protocols:
  - `SourceMetadataPlugin`
  - `SourcePlanningPlugin`
  - `SourceExecutionPlugin`
  - `SourceRecordPlugin`
  - `SourceReviewPlugin`
  - `SourceHandoffPlugin`
  - `EvidenceSourcePlugin`
  - `DirectSearchSourcePlugin`
- [x] Include metadata, query planning, validation, execution,
  normalization, extraction policy, and handoff policy in the contract.
- [x] Define typed execution input/output contracts.
- [x] Add `SourcePluginMetadata`.
- [x] Add `SourceSearchExecutionContext` with `space_id`, `created_by`, and
  store ownership at the orchestration edge; `SourceSearchInput` carries
  optional timeout/limit fields.
- [x] Add `SourceReviewPolicy`.
- [x] Add `SourceHandoffPolicy`.
- [x] Define typed candidate-context contract reuse or bridge to existing
  `SourceCandidateContext`.
- [x] Implement the narrow protocol split chosen in "Required Decisions Before
  Phase 1".
- [x] Add source-plugin architecture tests before migrating real sources.
- [x] Add a regression test that fails when orchestration modules add new
  source-key dispatch maps.
- [x] Add `services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py`.
- [x] Add `services/artana_evidence_api/tests/unit/test_source_plugin_parity.py`.
- [x] Add plugin security tests that deny plugin imports from routers,
  persistence stores, SQLAlchemy models, graph database internals, RLS bypass
  helpers, and source-document persistence internals.
- [x] Add plugin size/shape tests that prevent `source_plugins.py`, oversized
  plugin modules, broad `source_plugins/__init__.py` imports, and side-effect
  registration.
- [x] Add the AST source-map guard before any source migration starts.
  It should detect module-level source-key maps, function-local handler maps,
  `if source_key == "..."`, `match source_key`, and new `_SOURCE_*`,
  `_POLICIES`, or `_LIVE_SOURCE_SEARCH_VALIDATORS` style maps outside plugin
  modules and documented compatibility facades.
- [x] Enforce that migrated plugin keys cannot remain in legacy
  `evidence_selection_source_search.py` handler or validator maps.
- [x] Add plugin contract and architecture tests before deleting any legacy
  central maps.

Acceptance gates:

- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_boundary_contract.py -q`
- `make artana-evidence-api-type-check`
- No production caller switches away from `source_adapters.py` yet.
- `direct_source_search.py` durable store contracts and persistence behavior
  remain outside plugin modules.
- Claude second-opinion review of the contract shape has no unresolved
  blockers.

### Phase 2: Plugin Registry With Pilot Source

Goal: introduce deterministic plugin registration behind the current adapter
boundary with one real source. Do not land an empty registry.

Public schema impact: no, unless the pilot moves public request/response model
imports. If that happens, run the contract check.

Default pilot source: ClinicalTrials.gov. It is the lowest-risk direct source
because it has a simple query payload, clear `nct_id` provider identifier, no
credential gate, and no variant-aware downstream behavior.

Alternative pilot: ClinVar, only if the team wants to prove the hardest
variant-aware path first.

- [x] Add `services/artana_evidence_api/source_plugins/registry.py`.
- [x] Register plugins through an explicit ordered tuple, not import side
  effects or `@register_plugin` decorators.
- [x] Preserve current `direct_search_source_keys()` order exactly.
  - Current direct-search order:
    `pubmed`, `marrvel`, `clinvar`, `drugbank`, `alphafold`, `uniprot`,
    `clinical_trials`, `mgi`, `zfin`.
- [x] Preserve source alias normalization behavior.
  - Registry construction must fail on duplicate aliases.
  - Registry construction must fail when an alias collides with another
    canonical source key.
  - Registry construction must fail on duplicate canonical source keys.
  - Current implementation preserves normalization by reusing
    `normalize_source_key`; duplicate/collision fail-closed checks remain.
- [x] Preserve source capability invariants currently enforced by
  `SourceDefinition`.
- [x] Add registry drift checks equivalent to current adapter contract checks.
- [x] Keep `source_registry.py` compatibility functions until all callers are
  migrated or intentionally kept.
  - Keep `normalize_source_key`.
  - Keep `get_source_definition`.
  - Keep `list_source_definitions`.
  - Keep `direct_search_source_keys`.
  - Keep `research_plan_source_keys`.
  - Keep `default_research_plan_source_preferences`.
  - Keep `unknown_source_preference_keys`.
- [x] Move route-level direct-source branching out of
  `routers/v2_public.py`.
  - Generic create/get source-search routes now dispatch through
    `source_route_plugins.py`, with guard tests preventing source-key branches
    from returning to those generic handlers.
  - Generic source-key route dependencies are built by
    `source_route_dependencies.py`, so `v2_public.py` does not enumerate
    source gateways or discovery services in its route signatures.
  - The separate `source_route_adapters.py` registry has been removed; the
    route plugin registry owns typed route registration plus generic dispatch.
  - Typed direct-source route declarations now live in focused
    `source_route_*.py` modules and are registered through
    `source_route_plugins.py`.
  - `v2_public.py` keeps the public router and source-agnostic workflow
    endpoints; it no longer declares concrete direct-source paths such as
    `/sources/pubmed/searches`.
- [x] Add `services/artana_evidence_api/source_plugins/clinical_trials.py`.
- [x] Move ClinicalTrials.gov metadata into the plugin.
- [x] Move ClinicalTrials.gov query planning into the plugin.
- [x] Move ClinicalTrials.gov live-search validation into the plugin.
- [x] Move ClinicalTrials.gov execution delegation into the plugin.
- [x] Move ClinicalTrials.gov record normalization into the plugin.
- [x] Move ClinicalTrials.gov extraction/review policy into the plugin.
- [x] Move ClinicalTrials.gov handoff policy into the plugin.
- [x] Update `source_adapters.py` to build ClinicalTrials.gov adapter behavior from the
  plugin while other sources still use current central maps.
- [x] Add focused `test_clinical_trials_plugin.py`.
- [x] Add parity tests comparing ClinicalTrials.gov plugin behavior to legacy
  behavior.

Acceptance gates:

- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_registry.py services/artana_evidence_api/tests/unit/test_source_adapter_registry.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_clinical_trials_plugin.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py -k clinical_trials -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py -k clinical_trials -q`
- `make artana-evidence-api-type-check`
- `git diff --check`

### Phase 3: Gateway-Style Source Migration

Goal: migrate the mechanically similar direct-source plugins.

Public schema impact: expected no. If request/response classes move or schema
names change, treat as yes and run OpenAPI/contract checks.

Likely sources:

- [x] AlphaFold
- [x] UniProt
- [x] DrugBank
- [x] MGI and ZFIN as an Alliance-family pair
- [x] ClinVar

For each source:

- [x] Create a source-specific plugin module.
- [x] Move metadata.
- [x] Move query payload planning.
- [x] Move live-search validation.
- [x] Move execution delegation.
- [x] Move record normalization.
- [x] Move provider ID extraction.
- [x] Move variant-aware recommendation.
- [x] Move extraction/review policy.
- [x] Move handoff policy.
- [x] Add or update source-specific plugin tests.
- [x] Remove migrated source entry from the old central maps only after parity
  tests pass.

Suggested order:

1. AlphaFold
2. UniProt
3. DrugBank
4. MGI and ZFIN together
5. ClinVar last

ClinVar should move last among gateway-style sources because variant-aware
recommendations, accession/HGVS detection, and clinical-significance caveats
have more downstream impact.

Shared gateway-source migration notes:

- Keep `DirectSourceSearchStore`, SQLAlchemy persistence, payload envelope
  versioning, routes, handoff service, review queue, proposal staging, and graph
  promotion central.
- Move per-source request/response models only with compatibility imports and
  OpenAPI checks.
- DrugBank has credential and treatment/actionability wording risk.
- MGI and ZFIN should share an Alliance-family helper to avoid copy-paste drift.
  This is implemented in `source_plugins/alliance.py`.

Acceptance gates:

- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_<source>_plugin.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py -k "<source>" -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py -k "<source>" -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_search_handoff.py -q`
- `make artana-evidence-api-contract-check`
- `make artana-evidence-api-type-check`

### Phase 4: PubMed Plugin

Goal: migrate PubMed without breaking its job-based discovery-service pattern.

Public schema impact: expected no, but higher risk because result shaping and
source capture metadata are involved.

- [x] Decide whether PubMed needs a temporary plugin rollout flag or shadow
  parity check.
- [x] Add `services/artana_evidence_api/source_plugins/pubmed.py`.
- [x] Move PubMed metadata and aliases.
- [x] Move PubMed query planning.
- [x] Move PubMed live-search validation.
- [x] Move PubMed discovery-service execution path.
- [x] Move PubMed result shaping.
- [x] Move PubMed record normalization.
- [x] Move PubMed extraction/review policy.
- [x] Move PubMed handoff policy.
- [x] Add focused PubMed plugin tests.
- [x] Add PubMed parity fixtures for query planning, result shaping, normalized
  records, extraction policy, and source capture metadata.
- [x] Preserve completed-vs-incomplete job behavior:
  - completed PubMed job becomes a durable `source_search_runs` record;
  - queued/running/incomplete PubMed job keeps the legacy job response and is
    not saved as a completed direct-source run.
- [x] Preserve public schema names and import paths for:
  - `PubMedSearchRequest`
  - `AdvancedQueryParameters`
  - `DiscoverySearchJob`
  - `RunPubmedSearchRequest`
  - `PubMedSourceSearchResponse`
- [x] Preserve typed v2 PubMed route behavior where the response can be
  `PubMedSourceSearchResponse | DiscoverySearchJob`.
- [x] Preserve generic v2 source-search response behavior separately from the
  typed PubMed route.
- [x] Preserve the distinction between PubMed `total_results` and local
  `record_count`.
- [x] Preserve selected-record handoff identity: selected external ID should be
  the PMID, not the search job ID.
- [x] Preserve `source_capture.external_id` as search/job identity where it
  currently behaves that way.
- [x] Preserve deterministic-vs-live backend selection, optional NCBI API key,
  optional NCBI email/tool values, rate limits, retries, and `Retry-After`
  behavior. This remains covered by PubMed discovery/router tests, not moved
  into the plugin.
- [x] Freeze or deliberately normalize the current `pubdate` versus
  `publication_date` behavior with explicit tests.

Acceptance gates:

- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_pubmed_plugin.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_pubmed_discovery.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_pubmed_router.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py -k pubmed -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py -k pubmed -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_result_capture.py -q`
- `make artana-evidence-api-contract-check`
- `make artana-evidence-api-service-checks`

### Phase 5: MARRVEL Plugin

Goal: migrate the most source-specific logic carefully.

Public schema impact: expected no, but higher risk because panel records,
variant-aware hints, and source capture metadata are involved.

- [x] Decide whether MARRVEL needs a temporary plugin rollout flag or shadow
  parity check.
- [x] Add `services/artana_evidence_api/source_plugins/marrvel.py`.
- [x] Move MARRVEL metadata and aliases.
- [x] Move MARRVEL query planning and panel defaults.
- [x] Move MARRVEL live-search validation.
- [x] Move MARRVEL discovery-service execution path.
- [x] Move MARRVEL panel result shaping.
- [x] Move MARRVEL HGVS/variant derivation logic.
- [x] Move MARRVEL record normalization.
- [x] Move MARRVEL variant-aware recommendation.
- [x] Move MARRVEL extraction/review policy.
- [x] Move MARRVEL handoff policy.
- [x] Add focused MARRVEL plugin tests.
- [x] Add MARRVEL parity fixtures for panel records, HGVS derivation,
  variant-aware hints, normalized records, and source capture metadata.

MARRVEL-specific invariants:

- Do not accidentally tighten the public request contract: `gene_symbol` can be
  combined with `variant_hgvs` or `protein_variant`, but `variant_hgvs` and
  `protein_variant` remain mutually exclusive.
- Preserve the difference between v1 `MarrvelSearchResponse` and v2/direct
  `MarrvelSourceSearchResponse`.
- Preserve public panel literal names.
- Preserve current result-count behavior unless intentionally changed and
  documented.
- Preserve metadata-only panel records where current v2 behavior emits them.
- Preserve the missing `source_capture.external_id` for aggregate MARRVEL
  searches; individual handoffs use `marrvel_record_id`.
- Preserve query-default differences between model playbooks and discovery
  service defaults. This divergence is intentional: model/planner-generated
  MARRVEL searches default to a smaller high-signal panel set
  (`omim`, `clinvar`, `gnomad`, `geno2mp`, `expression`) so evidence-selection
  harness runs stay focused and bounded. Direct user/API MARRVEL searches with
  no `panels` value still ask the discovery service for all supported panels,
  preserving the existing public API behavior and broad exploratory workflow.
- Preserve variant-aware panel classification for ClinVar, Mutalyzer, TransVar,
  gnomAD variant, Geno2MP variant, DGV variant, and DECIPHER variant panels.
- Preserve HGVS fallback order:
  `hgvs_notation`, `hgvs`, `variant`, `cdna_change`, `protein_change`,
  resolved variant, then non-gene query value.

Acceptance gates:

- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_marrvel_plugin.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_marrvel_router.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py -k marrvel -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py -q`
- `make artana-evidence-api-contract-check`
- `make artana-evidence-api-service-checks`

### Phase 6: Non-Direct And Metadata-Only Sources

Goal: implement plugin coverage for sources that create evidence without being
direct-search adapters.

Public schema impact: expected no.

Sources to classify:

- [x] MONDO: authority/grounding source.
- [x] HGNC: authority/grounding source.
- [x] PDF: document-ingestion source.
- [x] text: document-ingestion source.

Contract decision:

- [x] Do not force these into `DirectSearchSourcePlugin`.
- [x] Add `AuthoritySourcePlugin` for MONDO and HGNC.
- [x] Add `DocumentIngestionSourcePlugin` for PDF and text.
- [x] Keep these sources out of `direct_search_source_keys()` and
  `source_adapters()` unless they later gain live direct-search execution.

Evidence path:

- MONDO/HGNC:
  - Normalize identifiers and aliases.
  - Resolve entities to authority references.
  - Attach grounding provenance to extracted evidence.
  - Support later proposal review; do not auto-promote claims.
- PDF/text:
  - Validate user-provided content.
  - Normalize document metadata.
  - Store source documents through existing document persistence flows.
  - Return extraction context for orchestration to feed into extraction/review
    staging; do not call extractors, enqueue reviews, persist documents, or
    bypass review from the plugin.

Implementation checklist:

- [x] Define authority and document-ingestion contracts in
  `source_plugins/contracts.py`.
- [x] Add contract serialization tests for authority grounding and ingestion
  extraction contexts.
- [x] Add `source_plugins/authority/` modules for MONDO and HGNC.
- [x] Add `source_plugins/ingestion/` modules for PDF and text.
- [x] Add an authority/ingestion registry view without mixing these plugins
  into the direct-search registry.
- [x] Update research-plan/source-list code to use the new registry view where
  it needs non-direct source behavior.
- [x] Add focused tests for MONDO/HGNC grounding context behavior.
- [x] Add focused tests for PDF/text ingestion context behavior.
- [x] Confirm document extraction and review gates still own persistence and
  promotion.
- [x] Harden architecture tests so non-direct plugins cannot collapse back into
  flat modules or orchestration source-key maps.
- [x] Promote research-plan source coverage and full metadata parity checks into
  `validate_source_plugin_registry()`.

Acceptance gates:

- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_registry.py services/artana_evidence_api/tests/unit/test_v2_public_routes.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py -q`
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_non_direct_source_plugins.py services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py services/artana_evidence_api/tests/unit/test_source_plugin_parity.py -q`
- `make artana-evidence-api-service-checks`
- `make service-checks`
- Research-plan source lists remain stable.
- Public source listing behavior remains stable.
- Tests document why these are direct-search-disabled but still evidence
  sources.

### Phase 7: Remove Central Source Maps

Goal: make plugins the source of truth.

Public schema impact: no.

- [x] Remove or shrink `_SOURCE_DEFINITIONS`.
- [x] Remove or shrink `_SOURCE_RECORD_POLICIES`.
- [x] Remove or shrink `_SOURCE_QUERY_PLAYBOOKS`.
- [x] Remove or shrink extraction `_POLICIES`.
- [x] Remove live-search validator dispatch maps.
- [x] Remove runner handler maps once plugin execution is authoritative.
- [x] Keep only compatibility facades that are still used by public callers.
- [x] Source-key map and dispatch guard is planned in Phase 1 before migration
  starts.
- [x] Tighten the Phase 1 source-map guard to remove compatibility exceptions
  that are no longer needed.
- [x] Document allowed compatibility facades before enabling the stricter AST
  guard.
- [x] Ask Claude for a second-opinion review before removing the legacy maps.

Current status: Phase 7 is complete. `source_registry.py`,
`source_policies.py`, `evidence_selection_source_playbooks.py`, and
`evidence_selection_extraction_policy.py` remain as compatibility facades, but
source definitions, record normalization, query planning, extraction policy,
and handoff policy are plugin-owned.

Acceptance gates:

- `rg "_SOURCE_.*POLIC|_SOURCE_QUERY|_POLICIES|_LIVE_SOURCE_SEARCH_VALIDATORS" services/artana_evidence_api`
  shows no production source-of-truth maps outside plugin modules, or each
  remaining hit is documented as compatibility-only.
- Architecture size gate passes.
- Source adapter registry tests pass.
- `make artana-evidence-api-service-checks`

### Phase 8: Legacy Test Cleanup

Goal: remove or simplify tests that only existed to protect legacy central maps.
Do not defer plugin contract, architecture, or parity tests to this phase; those
must land before migration and before central-map deletion.

Public schema impact: no.

- [x] Plugin contract tests are planned in Phase 1 so guardrails exist before
  deletion.
- [x] Plugin architecture/source-map tests are planned in Phase 1 so guardrails
  exist before deletion.
- [x] Plugin parity tests are required before each legacy map entry is removed.
- [x] Remove duplicate legacy central-map tests only after plugin tests cover
  the same behavior.
- [x] Keep integration tests for public API behavior, not internal plugin
  implementation details.
- [x] Update source boundary tests to prefer plugin registry boundaries.
- [x] Remove obsolete compatibility-facade exceptions from boundary tests.

Acceptance gates:

- Focused plugin tests pass.
- Existing direct-source route tests pass.
- Evidence-selection runtime tests pass.
- Source-search handoff tests pass.
- Service checks pass.
- `make architecture-size-check`

### Phase 9: Documentation And Rollout

Goal: make the new architecture understandable and safe to maintain.

Public schema impact: no.

- [x] Update this tracker after each phase.
- [x] Add or update source-plugin developer docs.
- [x] Document how to add a new datasource.
- [x] Document how non-direct sources are represented.
- [x] Document compatibility wrappers and planned removal points.
- [x] Ask Claude for second-opinion review before closing the refactor.
- [x] Record final verification commands and results.

Acceptance gates:

- Docs match current code.
- Claude review has no unresolved blockers.
- Final service checks pass.

## Required Verification Commands

Run these after each meaningful phase:

```bash
venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py -q
venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_extraction_policy.py -q
venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py services/artana_evidence_api/tests/unit/test_source_search_handoff.py -q
make artana-evidence-api-lint
make artana-evidence-api-type-check
make artana-evidence-api-boundary-check
make architecture-size-check
git diff --check
```

Run these before merging any phase that changes execution, public schemas, or
source registration:

```bash
make artana-evidence-api-service-checks
make service-checks
```

Run OpenAPI/contract checks whenever request/response models or public schemas
change:

```bash
make artana-evidence-api-contract-check
```

## Completion Definition

The full plugin refactor is complete only when:

- Every direct-search source has one plugin owning its source-specific behavior.
- The adapter boundary builds from plugins, not parallel central maps.
- Live-search execution is plugin-driven.
- Live-search validation is plugin-driven.
- Result shaping is plugin-owned.
- Source metadata and aliases are plugin-owned or explicitly documented as
  registry-owned shared concerns.
- Non-direct evidence sources use the right source contract:
  authority/grounding plugins for ontology and nomenclature sources, and
  document-ingestion plugins for user-provided content.
- Production orchestration modules do not contain per-source behavior maps.
- Public typed direct-source routes are route-plugin registered outside
  `routers/v2_public.py`; the public router does not own source-specific route
  declarations.
- Plugin modules do not bypass PHI encryption, graph RLS, or persistence
  boundaries.
- OpenAPI output has no drift unless an intentional public contract change is
  documented and regenerated.
- Tests are organized around plugin behavior plus public API behavior.
- `make artana-evidence-api-service-checks` passes.
- `make service-checks` passes.
- Claude second-opinion review has no unresolved blockers.

## Verification Log

Use this section to record commands and results as implementation progresses.

Template:

```text
- YYYY-MM-DD: Phase N - short description.
  - Command: `...`
  - Result: passed/failed/skipped.
  - Notes/follow-ups: ...
```

- 2026-04-28: Plan created for item 8 plugin refactor.
  - Command: `git diff --check`
  - Result: passed.
  - Claude second-opinion closeout review: completed. Final concise pass
    returned: "No blockers visible from summary."
  - Claude plan review: completed.
  - Notes/follow-ups: Claude flagged missing file decomposition, non-direct
    source decisions, parity definition, too-late guardrails, security
    invariants, vague gates, and late review checkpoints. Plan was updated to
    address those findings.
- 2026-04-28: Phase 1/2 implementation slice - source plugin contracts,
  explicit plugin registry, and ClinicalTrials.gov pilot plugin.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_clinical_trials_plugin.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py -q`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_registry.py services/artana_evidence_api/tests/unit/test_source_adapter_registry.py -q`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py -k clinical_trials -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py -k clinical_trials -q`
  - Result: passed.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed.
  - Command: `make artana-evidence-api-service-checks`
  - Result: passed before and after Claude follow-up fixes. Live external API
    tests and localhost service checks remained skipped by their normal opt-in
    guards.
  - Claude second-opinion review: completed. Actionable findings addressed by
    routing legacy live-search validation through plugins first, removing
    `clinical_trials` from legacy runner/validator maps, moving
    `EvidenceSelectionSourceSearchError` into plugin contracts, using
    `SourcePluginMetadata`, avoiding import-time plugin-registry validation,
    reducing duplicate ClinicalTrials.gov request validation, and adding a
    guard that migrated plugin keys cannot reappear in legacy source-search
    dispatch maps.
  - Claude second-opinion re-review: completed. Follow-up hardening kept plugin
    registry validation lazy but fail-closed on first use, made registry
    validation consume `SourcePluginMetadata`, enforced canonical source keys in
    source-search runner/plugin execution, and strengthened the migrated-source
    dispatch-map test to inspect AST dictionary keys instead of raw text.
  - Notes/follow-ups: `clinical_trials` now runs through a source plugin behind
    `source_adapters.py`; other sources still use compatibility central maps.
    Remaining Phase 1 hardening includes the broader source-map AST guard and
    duplicate/collision checks for alias registry drift.
- 2026-04-28: Phase 3 implementation slice - AlphaFold plugin migration.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_plugin_helpers.py services/artana_evidence_api/tests/unit/test_alphafold_plugin.py services/artana_evidence_api/tests/unit/test_clinical_trials_plugin.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py services/artana_evidence_api/tests/unit/test_source_plugin_parity.py services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py -q`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_registry.py services/artana_evidence_api/tests/unit/test_source_adapter_registry.py -q`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py -k alphafold -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py -k alphafold -q`
  - Result: passed.
  - Command: `make artana-evidence-api-contract-check`
  - Result: passed.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed.
  - Command: `make artana-evidence-api-service-checks`
  - Result: passed before and after Claude follow-up fixes. Live external API
    tests and localhost service checks remained skipped by their normal opt-in
    guards.
  - Claude second-opinion review: completed. Actionable findings addressed by
    adding plugin-vs-central-registry drift validation, adding generic
    plugin-vs-legacy parity tests for every migrated plugin, adding source-key
    checks for plugin query planning, and extracting shared plugin helpers for
    metadata, normalized extraction payloads, summaries, identifier fields, and
    compact record normalization.
  - Claude second-opinion re-review: completed. No visible high-severity
    blockers. Follow-up tightening added direct helper tests and made
    ClinicalTrials.gov live-search validation use the same helper-enforced
    source-key pattern as AlphaFold.
  - Notes/follow-ups: `alphafold` now runs through a source plugin behind
    `source_adapters.py`; the evidence-selection runner no longer keeps
    AlphaFold in legacy source-key handler or validator maps. Remaining
    gateway-style sources are UniProt, DrugBank, MGI/ZFIN, and ClinVar.
- 2026-04-28: Phases 3-5 implementation slice - all direct-search source
  plugins registered and execution-dispatched through plugins.
  - Subagents:
    - UniProt worker completed `source_plugins/uniprot.py` and
      `test_uniprot_plugin.py`.
    - DrugBank worker completed `source_plugins/drugbank.py` and
      `test_drugbank_plugin.py`.
    - Alliance worker completed `source_plugins/alliance.py`,
      `source_plugins/mgi.py`, `source_plugins/zfin.py`, and
      `test_alliance_plugins.py`.
    - ClinVar worker completed `source_plugins/clinvar.py` and
      `test_clinvar_plugin.py`.
    - PubMed worker completed `source_plugins/pubmed.py` and
      `test_pubmed_plugin.py`.
    - MARRVEL worker completed `source_plugins/marrvel.py` and
      `test_marrvel_plugin.py`.
  - Lead integration: registered PubMed, MARRVEL, ClinVar, DrugBank,
    AlphaFold, UniProt, ClinicalTrials.gov, MGI, and ZFIN in
    `source_plugins/registry.py` in `direct_search_source_keys()` order.
  - Lead integration: reduced `evidence_selection_source_search.py` to a thin
    canonical-key check plus plugin execution dispatch.
  - Lead integration: removed legacy direct-source handler maps and
    live-search validator maps from `evidence_selection_source_search.py`.
  - Lead integration: added execution-scoped plugin construction for PubMed
    and MARRVEL so discovery service factories remain injected rather than
    hidden in the runner.
  - Lead integration: updated generic plugin contract, architecture, parity,
    adapter, and dispatch tests for the full direct-search plugin set.
  - Command: `venv/bin/ruff check services/artana_evidence_api/evidence_selection_source_search.py services/artana_evidence_api/source_plugins services/artana_evidence_api/tests/unit/test_alphafold_plugin.py services/artana_evidence_api/tests/unit/test_clinical_trials_plugin.py services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py services/artana_evidence_api/tests/unit/test_source_plugin_parity.py services/artana_evidence_api/tests/unit/test_uniprot_plugin.py`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_alphafold_plugin.py services/artana_evidence_api/tests/unit/test_clinical_trials_plugin.py services/artana_evidence_api/tests/unit/test_pubmed_plugin.py services/artana_evidence_api/tests/unit/test_marrvel_plugin.py services/artana_evidence_api/tests/unit/test_clinvar_plugin.py services/artana_evidence_api/tests/unit/test_drugbank_plugin.py services/artana_evidence_api/tests/unit/test_uniprot_plugin.py services/artana_evidence_api/tests/unit/test_alliance_plugins.py -q`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py services/artana_evidence_api/tests/unit/test_source_plugin_parity.py -q`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py -k "uniprot or drugbank or mgi or zfin or clinvar or pubmed or marrvel" -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py -k "uniprot or drugbank or mgi or zfin or clinvar or pubmed or marrvel" -q`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py -q`
  - Result: passed.
  - Command: `make artana-evidence-api-contract-check`
  - Result: passed. OpenAPI remained up to date.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed. Ruff, mypy, boundary, OpenAPI, and architecture-size gates
    passed.
  - Command: `make artana-evidence-api-service-checks`
  - Result: passed. Static gates, OpenAPI check, architecture-size gate,
    ephemeral Postgres migrations, and the evidence API pytest suite passed.
    Expected skips remained for opt-in live external API tests and services
    that were not running on localhost.
  - Command: `make service-checks`
  - Result: passed. Graph-service checks, evidence API checks, OpenAPI checks,
    generated TypeScript contract checks, architecture-size checks, and the
    coverage gate passed. Expected live external/API-localhost skips remained.
  - Command: `git diff --check`
  - Result: passed.
  - Claude second-opinion review: completed after two larger local Claude
    review attempts stalled and were stopped cleanly. The final concise Claude
    pass returned: "No blockers visible from summary."
  - Notes/follow-ups: `source_registry.py`, `source_policies.py`,
    `evidence_selection_source_playbooks.py`, and
    `evidence_selection_extraction_policy.py` still exist as compatibility and
    parity sources. Non-direct source classification, stricter source-map AST
    enforcement, and final aggregate `make service-checks` were completed in
    the Phase 6 implementation/hardening closeout.
- 2026-04-28: Phase 6 design slice - non-direct evidence-source contract
  taxonomy.
  - Decision: MONDO and HGNC are authority/grounding sources; they create
    evidence support by grounding entities to normalized IDs, aliases, labels,
    and provenance, but do not directly create claims.
  - Decision: PDF and text are document-ingestion sources; they create
    evidence by validating user-provided content, normalizing document
    metadata, and returning extraction context to orchestration.
  - Code: added `SourceAuthorityReference`, `SourceGroundingContext`,
    `SourceDocumentIngestionContext`, `SourceGroundingInput`,
    `SourceDocumentInput`, `AuthoritySourcePlugin`, and
    `DocumentIngestionSourcePlugin` to
    `services/artana_evidence_api/source_plugins/contracts.py`.
  - Code: authority grounding context explicitly represents `resolved`,
    `ambiguous`, and `not_found` states so MONDO/HGNC misses and ambiguous
    matches are first-class instead of hidden edge cases.
  - Tests: added contract serialization tests for authority grounding and
    document ingestion contexts, including unknown and ambiguous authority
    grounding, in
    `services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py`.
  - Claude second-opinion review: completed. Actionable findings addressed by
    clarifying that ingestion plugins return context but do not dispatch into
    extraction/review, and by adding explicit not-found/ambiguous authority
    grounding states and tests.
  - Claude second-opinion re-review: completed. Final concise pass returned:
    "No blockers visible from summary."
  - Command: `venv/bin/ruff check services/artana_evidence_api/source_plugins/contracts.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py -q`
  - Result: passed.
  - Command: `make artana-evidence-api-type-check`
  - Result: passed.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed. Ruff, mypy, boundary, OpenAPI, and architecture-size gates
    passed.
  - Command: `make service-checks`
  - Result: passed. Graph-service checks, evidence API checks, OpenAPI checks,
    generated TypeScript contract checks, architecture-size checks, and the
    coverage gate passed at 88.09%. Expected live external/API-localhost skips
    remained. Generated `coverage.xml` was restored as unrelated churn.
  - Claude second-opinion review: completed. The review flagged PubMed/MARRVEL
    execution dependency wrapping asymmetry, uneven non-direct plugin tests,
    and missing Phase 6 acceptance-gate docs. These were addressed by
    normalizing `source_plugin_for_execution()` wrapping behavior, adding
    execution-registry and metadata-drift tests, expanding MONDO/HGNC/PDF/text
    behavior tests, and updating Phase 6/Phase 7 plan notes.
  - Claude second-opinion re-review: completed. Final blockers-only pass
    returned: no unresolved blockers.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed. Ruff, mypy, boundary, OpenAPI, and architecture-size gates
    passed.
  - Command: `make artana-evidence-api-service-checks`
  - Result: passed. Static gates, OpenAPI check, architecture-size gate,
    ephemeral Postgres migrations, and the evidence API pytest suite passed.
    Expected skips remained for opt-in live external API tests and services
    that were not running on localhost.
  - Command: `make service-checks`
  - Result: passed. Graph-service checks, evidence API checks, OpenAPI checks,
    generated TypeScript contract checks, architecture-size checks, and the
    coverage gate passed at 88.09%. Expected live external/API-localhost skips
    remained. Generated `coverage.xml` was restored as unrelated churn.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed.
  - Command: `make artana-evidence-api-service-checks`
  - Result: passed. Expected opt-in live external/API-localhost tests remained
    skipped by their normal guards.
  - Command: `make service-checks`
  - Result: passed. Expected opt-in live external/API-localhost tests remained
    skipped by their normal guards; generated `coverage.xml` was restored as
    unrelated churn.
  - Command: `git diff --check`
  - Result: passed.
  - Command: `git diff --check`
  - Result: passed.
  - Notes/follow-ups: concrete MONDO/HGNC and PDF/text plugin modules and a
    non-direct registry view were implemented in the next slice.
- 2026-04-28: Phase 6 implementation slice - non-direct evidence-source
  plugins and registry views.
  - Code: added shared authority support in
    `services/artana_evidence_api/source_plugins/authority/base.py`.
  - Code: added MONDO and HGNC authority plugins in
    `services/artana_evidence_api/source_plugins/authority/mondo.py` and
    `services/artana_evidence_api/source_plugins/authority/hgnc.py`.
  - Code: added shared document-ingestion support in
    `services/artana_evidence_api/source_plugins/ingestion/base.py`.
  - Code: added PDF and text ingestion plugins in
    `services/artana_evidence_api/source_plugins/ingestion/pdf.py` and
    `services/artana_evidence_api/source_plugins/ingestion/text.py`.
  - Code: extended `source_plugins/registry.py` with explicit authority,
    document-ingestion, and all-evidence-source registry views without mixing
    non-direct plugins into the direct-search registry.
  - Code: `research_init_source_results.registry_source_result_keys()` now uses
    `evidence_source_plugin_keys()` so research-plan source summaries are
    plugin-backed while preserving public source order.
  - Tests: added
    `services/artana_evidence_api/tests/unit/test_non_direct_source_plugins.py`
    covering registry separation, source-definition parity, resolved/ambiguous/
    not-found grounding, ingestion metadata normalization, extraction context,
    and content-type validation.
  - Hardening: strengthened `test_source_plugin_architecture.py` so
    non-direct plugins must stay in dedicated packages, plugin modules remain
    size-bounded, production code imports only the plugin registry/contracts
    boundary, and orchestration modules cannot reintroduce source-key dispatch
    maps.
  - Hardening: `validate_source_plugin_registry()` now checks every metadata
    field against the public source definition and fails closed when
    research-plan sources are missing plugin coverage.
  - Command: `venv/bin/ruff check services/artana_evidence_api/source_plugins services/artana_evidence_api/research_init_source_results.py services/artana_evidence_api/tests/unit/test_non_direct_source_plugins.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_non_direct_source_plugins.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py services/artana_evidence_api/tests/unit/test_source_plugin_parity.py services/artana_evidence_api/tests/unit/test_source_registry.py services/artana_evidence_api/tests/unit/test_v2_public_routes.py -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_non_direct_source_plugins.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py services/artana_evidence_api/tests/unit/test_source_registry.py services/artana_evidence_api/tests/unit/test_research_init.py -k "source_registry or source_results or source_preferences or sources" -q`
  - Result: passed.
  - Command: `make artana-evidence-api-type-check`
  - Result: passed.
- 2026-04-28: Phase 7/9 closeout slice - central source-map removal,
  plugin-owned source definitions, PubMed hardening, execution-factory
  cleanup, and final verification.
  - Code: converted `source_registry.py` into a plugin-definition-backed
    compatibility registry while retaining alias normalization and public
    source-list helpers.
  - Code: converted `source_policies.py`,
    `evidence_selection_source_playbooks.py`, and
    `evidence_selection_extraction_policy.py` into plugin-backed compatibility
    facades with no central per-source behavior maps.
  - Code: removed legacy adapter fallback behavior so direct-search adapters
    require registered source plugins.
  - Code: made PubMed normalization preserve `publication_date` from either
    `publication_date` or `pubdate`, with `publication_date` taking priority.
  - Code: replaced PubMed/MARRVEL source-key branches in
    `source_plugins/registry.py` with source-owned execution plugin builders.
  - Docs: recorded the intentional MARRVEL planner-vs-public-search default
    panel split and enumerated the then-remaining route-edge source branches
    as public API schema compatibility only.
  - Hardening: strengthened architecture tests to reject per-source dispatch
    maps and source-key branching in orchestration modules.
  - Command: `venv/bin/ruff check services/artana_evidence_api/source_adapters.py services/artana_evidence_api/source_policies.py services/artana_evidence_api/source_registry.py services/artana_evidence_api/evidence_selection_source_playbooks.py services/artana_evidence_api/evidence_selection_extraction_policy.py services/artana_evidence_api/evidence_selection_source_search.py services/artana_evidence_api/research_init_source_results.py services/artana_evidence_api/source_plugins services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py services/artana_evidence_api/tests/unit/test_source_registry.py services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_plugin_parity.py services/artana_evidence_api/tests/unit/test_pubmed_plugin.py services/artana_evidence_api/tests/unit/test_pubmed_discovery.py`
  - Result: passed.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_plugin_architecture.py services/artana_evidence_api/tests/unit/test_source_registry.py services/artana_evidence_api/tests/unit/test_source_adapter_registry.py services/artana_evidence_api/tests/unit/test_source_plugin_parity.py services/artana_evidence_api/tests/unit/test_source_plugin_contracts.py services/artana_evidence_api/tests/unit/test_source_plugin_helpers.py services/artana_evidence_api/tests/unit/test_non_direct_source_plugins.py services/artana_evidence_api/tests/unit/test_pubmed_plugin.py services/artana_evidence_api/tests/unit/test_pubmed_discovery.py services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py services/artana_evidence_api/tests/unit/test_source_search_handoff.py -q`
  - Result: passed.
  - Command: `make artana-evidence-api-type-check`
  - Result: passed.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed.
  - Command: `make artana-evidence-api-contract-check`
  - Result: passed. Evidence API OpenAPI remained up to date.
  - Command: `make service-checks`
  - Result: passed. Graph-service checks, evidence API static checks,
    OpenAPI/generated TypeScript checks, ephemeral Postgres migrations, test
    suites, and coverage gate passed at 87.44%. Expected opt-in live external
    API and localhost service tests remained skipped by their normal guards.
    Generated `coverage.xml` was restored as unrelated churn.
  - Command: `git diff --check`
  - Result: passed after final docs update.
  - Claude second-opinion review: completed. Claude could not read Python
    source in its environment, but it flagged three review risks from the plan
    and diff summary. The actionable risks were addressed by correcting stale
    plan ownership language, replacing the PubMed/MARRVEL source-key branch
    with source-owned execution builders, running the contract check, and
    documenting `direct_source_search.py` as a public API compatibility surface
    rather than an open behavior-ownership gap.
  - Claude second-opinion re-review: completed. Claude still lacked direct
    Python file access, but flagged four closeout checks. Repo verification
    confirmed the plugin-backed facades have no residual per-source behavior
    maps, the AST architecture guard passes, and OpenAPI has no diff. Follow-up
    docs recorded the intentional MARRVEL planner-vs-public-search default
    split and enumerated the then-remaining `v2_public.py` route-edge source
    branches as public API schema compatibility only.
- 2026-04-28: Route-edge caveat closeout slice.
  - Code: extracted source-specific public route parsing, dependency bridging,
    durable response shaping, and generic route dispatch from
    `routers/v2_public.py` into `source_route_adapters.py` plus focused
    PubMed/MARRVEL route adapter modules.
  - Code: generic `create_source_search` and `get_source_search` now delegate
    through the route adapter registry without source-key branches.
  - Code: fixed PubMed/MARRVEL generic GET cache-hit behavior so stored
    results do not require live discovery-service wiring.
  - Code: moved shared route validation-error formatting into
    `source_route_errors.py`, renamed the MARRVEL result payload helper to
    source-specific wording, and narrowed `source_route_adapters.py.__all__`
    to the generic registry boundary.
  - Code: at this slice, typed per-source v2 routes still remained in
    `v2_public.py` for public API schema and OpenAPI compatibility only. This
    caveat is superseded by the typed route-plugin closeout below.
  - Tests: added route-adapter coverage/drift checks and an AST guard proving
    the generic source-search routes do not branch on source keys.
  - Tests: added module-level adapter behavior tests for unknown adapters,
    stored PubMed/MARRVEL GETs without live discovery services, missing stored
    gateway-source results, and generic payload validation before gateway
    availability.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_route_adapters.py services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py::test_mixed_case_source_keys_route_through_generic_dispatch services/artana_evidence_api/tests/unit/test_pubmed_router.py::test_create_pubmed_search_through_generic_v2_source_route services/artana_evidence_api/tests/unit/test_marrvel_router.py::test_create_marrvel_search_through_generic_v2_source_route services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_source_search_openapi_keeps_typed_routes_and_capture_contract services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_direct_source_route_adapters_cover_registry_sources services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_generic_source_search_routes_do_not_branch_on_source_keys -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Command: `make architecture-size-check`
  - Result: passed after splitting route adapters so the new boundary did not
    become a monolith.
  - Command: `venv/bin/ruff check services/artana_evidence_api/source_route_errors.py services/artana_evidence_api/source_route_adapters.py services/artana_evidence_api/source_route_adapter_contracts.py services/artana_evidence_api/source_route_pubmed.py services/artana_evidence_api/source_route_marrvel.py services/artana_evidence_api/routers/v2_public.py services/artana_evidence_api/tests/unit/test_source_route_adapters.py services/artana_evidence_api/tests/unit/test_v2_public_routes.py`
  - Result: passed.
  - Claude second-opinion review: completed. Actionable findings addressed by
    fixing the stored PubMed/MARRVEL generic GET service-availability
    regression, deduplicating route validation formatting, renaming the
    MARRVEL payload helper, tightening the registry `__all__`, moving typed
    PubMed/MARRVEL imports to focused modules, and adding direct adapter tests.
  - Command: `make artana-evidence-api-type-check`
  - Result: passed.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed. Evidence API OpenAPI remained up to date.
  - Command: `make service-checks`
  - Result: passed. Graph-service checks, evidence API static checks,
    OpenAPI/generated TypeScript checks, architecture size, ephemeral
    Postgres migrations, test suites, and coverage gate passed at 87.44%.
    Expected opt-in live external API and localhost service tests remained
    skipped by their normal guards. Generated `coverage.xml` was restored as
    unrelated churn.
  - Command: `git diff --check`
  - Result: passed after final route-adapter and docs updates.
- 2026-04-28: Typed route-plugin closeout slice.
  - Code: moved concrete typed direct-source route declarations out of
    `routers/v2_public.py` and into focused `source_route_*.py` modules for
    PubMed, MARRVEL, ClinVar, DrugBank, AlphaFold, UniProt,
    ClinicalTrials.gov, MGI, and ZFIN.
  - Code: added `source_route_plugins.py` as the typed public route plugin
    registry and fail-closed drift check against `direct_search_source_keys()`.
  - Code: `v2_public.py` now registers typed source routes through
    `register_direct_source_typed_routes(router)` before the generic
    source-search routes; it no longer declares concrete direct-source paths.
  - Code: moved the remaining ClinVar, ClinicalTrials.gov, UniProt,
    AlphaFold, DrugBank, MGI, and ZFIN generic-route payload behavior out of
    `source_route_adapters.py` and into their focused source route modules.
  - Code: added `source_route_dependencies.py` and a source-keyed
    `DirectSourceRouteDependencies` bag so the route contract and
    `v2_public.py` no longer expose one dependency field per datasource.
  - Code: added `source_route_helpers.py` for shared route-edge validation,
    stored-result lookup, JSON encoding, and gateway-unavailable errors.
  - Code: replaced import-time route-registry drift checks with explicit
    validation functions invoked by app startup and tests.
  - Tests: added route-plugin registration coverage proving every concrete
    typed route comes from the route plugin endpoint map and not from
    `v2_public.py`.
  - Tests: added a source check proving `v2_public.py` does not contain
    concrete direct-source path declarations.
  - Tests: added guards proving `source_route_adapters.py` is registry-only
    and every typed route plugin defines the expected public route metadata.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_every_v2_route_is_covered_by_the_route_contract services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_every_v2_route_is_exposed_in_openapi services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_source_search_openapi_keeps_typed_routes_and_capture_contract services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_typed_direct_source_routes_are_registered_from_route_plugins services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_v2_public_has_no_concrete_direct_source_route_paths -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_route_adapters.py services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py services/artana_evidence_api/tests/unit/test_pubmed_router.py::test_create_pubmed_search_through_generic_v2_source_route services/artana_evidence_api/tests/unit/test_marrvel_router.py::test_create_marrvel_search_through_generic_v2_source_route services/artana_evidence_api/tests/unit/test_v2_public_routes.py -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Claude second-opinion review: completed. Actionable findings addressed by
    moving the remaining per-source payload logic into focused source route
    modules, replacing the per-source-field dependency contract with a
    source-keyed dependency bag, documenting FastAPI route-edge coupling,
    deduplicating request parsing through shared helpers, preserving the
    MARRVEL schema-name subclass with a clearer comment, replacing
    import-time drift checks with explicit validators, and adding route plugin
    metadata/registry-only guard tests.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_route_adapters.py services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_direct_source_route_adapters_cover_registry_sources services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_direct_source_route_adapter_registry_has_no_source_payloads services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_generic_source_search_routes_do_not_branch_on_source_keys services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_typed_direct_source_routes_are_registered_from_route_plugins services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_direct_source_typed_route_plugins_define_expected_public_routes services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_v2_public_has_no_concrete_direct_source_route_paths -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_route_adapters.py services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py services/artana_evidence_api/tests/unit/test_pubmed_router.py::test_create_pubmed_search_through_generic_v2_source_route services/artana_evidence_api/tests/unit/test_marrvel_router.py::test_create_marrvel_search_through_generic_v2_source_route services/artana_evidence_api/tests/unit/test_v2_public_routes.py -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Command: `make architecture-size-check`
  - Result: passed.
  - Command: `make artana-evidence-api-type-check`
  - Result: passed.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed. Evidence API OpenAPI remained up to date.
  - Command: `make service-checks`
  - Result: passed. Graph-service checks, evidence API static checks,
    OpenAPI/generated TypeScript checks, architecture size, ephemeral
    Postgres migrations, test suites, and coverage gate passed at 87.44%.
    Expected opt-in live external API and localhost service tests remained
    skipped by their normal guards. Generated `coverage.xml` was restored as
    unrelated churn.
  - Claude second-opinion re-review: completed. Blockers-only verdict found
    no merge-blocking issues. Non-blocking notes were that registry validation
    is cheap enough to call at startup/use sites, generic source-key requests
    still assemble all route-edge source dependencies, and the source-keyed
    dependency bag intentionally uses `object | None` plus focused-module
    casts to keep the public route contract closed.
  - Command: `git diff --check`
  - Result: passed after final docs update.
- 2026-04-29: Route plugin registry consolidation.
  - Code: removed the separate `source_route_adapters.py` registry.
  - Code: moved generic `/sources/{source_key}/searches` create/get dispatch
    into `source_route_plugins.py`, so one route plugin registry owns typed
    route registration and generic route dispatch.
  - Code: renamed the shared contract module to `source_route_contracts.py`
    and made `DirectSourceRoutePlugin` own typed routes plus generic
    create/get payload handlers.
  - Tests: renamed route adapter tests to route plugin tests and updated guard
    coverage so the plugin registry must cover every direct-search source and
    remain free of source-specific payload behavior.
  - Tests: added dependency-map drift coverage so generic route dependency
    keys must match `direct_source_route_plugin_keys()`.
  - Hardening: normalized MARRVEL stored-result handling to the same explicit
    type-narrowing pattern as PubMed.
  - Docs: updated this tracker and `docs/source_plugins.md` to remove the
    remaining active route-adapter caveat.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_route_plugins.py services/artana_evidence_api/tests/unit/test_direct_source_search_routes.py services/artana_evidence_api/tests/unit/test_pubmed_router.py::test_create_pubmed_search_through_generic_v2_source_route services/artana_evidence_api/tests/unit/test_marrvel_router.py::test_create_marrvel_search_through_generic_v2_source_route services/artana_evidence_api/tests/unit/test_v2_public_routes.py -q`
  - Result: passed with one existing FastAPI deprecation warning.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed. Evidence API OpenAPI remained up to date.
  - Command: `make service-checks`
  - Result: passed. Graph-service checks, evidence API static checks,
    OpenAPI/generated TypeScript checks, architecture size, ephemeral
    Postgres migrations, test suites, and coverage gate passed at 87.44%.
    Expected opt-in live external API and localhost service tests remained
    skipped by their normal guards. Generated `coverage.xml` was restored as
    unrelated churn.
  - Claude second-opinion review: completed. No clear merge blocker was found
    in the supplied context. Actionable feedback addressed by adding
    dependency-map drift coverage and normalizing MARRVEL stored-result type
    narrowing. The review also asked to confirm generic route pre-validation;
    `v2_public.py` calls `_require_direct_search_source(source_key)` before
    plugin dispatch.
  - Claude second-opinion follow-up: completed and verified locally. Generic
    create/get routes already require harness space write/read access and
    pre-validate the source key before plugin dispatch. The real follow-up gap
    was MARRVEL GET fallback durability: rebuilt MARRVEL results are now saved
    into the direct-source search store, matching PubMed fallback semantics.
    The route endpoint expectation map is now returned as an immutable mapping.
    Follow-up regression coverage now asserts immutable endpoint-map behavior,
    durable MARRVEL field preservation, and rebuilt-vs-stored payload parity.
  - Command: `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_route_plugins.py services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_direct_source_route_plugins_cover_registry_sources services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_direct_source_route_plugin_registry_has_no_source_payloads services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_generic_source_search_routes_do_not_branch_on_source_keys services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_typed_direct_source_routes_are_registered_from_route_plugins services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_direct_source_typed_route_plugins_define_expected_public_routes services/artana_evidence_api/tests/unit/test_v2_public_routes.py::test_v2_public_has_no_concrete_direct_source_route_paths -q`
  - Result: passed, 14 tests, with one existing FastAPI deprecation warning.
  - Command: `make artana-evidence-api-static-checks`
  - Result: passed after the Claude follow-up patch. Evidence API OpenAPI
    remained up to date.
  - Command: `make service-checks`
  - Result: passed after the Claude follow-up patch. Coverage gate passed at
    87.44%; expected opt-in live external API and localhost service tests were
    skipped by their normal guards. Generated `coverage.xml` was restored as
    unrelated churn.
  - Command: `git diff --check`
  - Result: passed after final docs update.
