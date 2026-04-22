# Migration Phase 2 Checklist

Progress tracker for [`migration-phase2.md`](migration-phase2.md).

Use this file to track implementation progress without changing the main design
document.

## Repo Snapshot

Snapshot date: `2026-03-13`

Current repo-grounded status after implementation:

- The standalone graph-service boundary is real and documented under
  `services/artana_evidence_db/`, `services/artana_evidence_db/openapi.json`, and
  `src/web/types/artana-evidence-db.generated.ts`.
- Neutral graph/runtime naming and platform-auth naming are implemented in the
  live graph and backend runtime surfaces.
- `src/graph/core/`, `src/graph/domain_biomedical/`, and
  `src/graph/domain_sports/` now provide the graph-core plus domain-pack split,
  with validation gates enforcing the boundary.
- Pack registration, auth, tenancy, read-model, release-boundary, and
  cross-domain proof gates now exist and are wired into repo validation flows.
- Query and reasoning read models now exist as physical derived tables with
  rebuild jobs, benchmarks, and correctness validation.

Completion status assumption:

- Treat Phases 0 through 7 as implemented and validated in the repo.
- Use the remaining notes in this document as evidence links and closure
  context, not as a forward roadmap.

## How To Use

- Check items as work lands.
- Add links to PRs, ADRs, scripts, or benchmark results next to completed items.
- Keep phase completion tied to validation gates, not just code changes.
- Do not mark a phase complete until its validation gate is satisfied.

## Overall Progress

- [x] Phase 0 complete
- [x] Phase 1 complete
- [x] Phase 2 complete
- [x] Phase 3 complete
- [x] Phase 4 complete
- [x] Phase 5 complete
- [x] Phase 6 complete
- [x] Phase 7 complete

## Phase 0: Baseline And Guardrails

Reference:
[`migration-phase2.md#phase-0-baseline-and-guardrails`](migration-phase2.md#phase-0-baseline-and-guardrails)

Scope and deliverables:

- [x] Current route contract is recorded
- [x] Generated client outputs are captured
- [x] Current auth and access expectations are documented
- [x] Representative graph-read benchmarks exist
- [x] Dependency boundaries are documented
- [x] Core versus domain-pack validation approach is defined
- [x] OpenAPI baseline snapshot exists
- [x] TypeScript client baseline exists
- [x] Benchmark set covers graph reads and evidence drilldown
- [x] Dependency-boundary rules are written
- [x] ADRs exist for naming, packaging, and read-model ownership

Validation gate:

- [x] `make graph-service-checks` passes
- [x] Benchmark suite produces repeatable numbers
- [x] Boundary-validation script exists or is clearly scoped
- [x] Current auth and role expectations are reviewed

Notes:

- Baseline contract artifact exists at `services/artana_evidence_db/openapi.json`.
- Generated TS client baseline exists at `src/web/types/artana-evidence-db.generated.ts`.
- Current auth/access expectations are documented in
  `docs/graph/developers/developer-guide.md`,
  `docs/graph/reference/endpoints.md`, and the service routers/dependencies.
- Existing boundary enforcement is service-boundary-focused via
  `scripts/validate_graph_service_boundary.py`; phase 0 still needs an explicit
  rule set for future `graph-core` versus domain-pack imports.
- Phase-2 boundary validation now exists at
  `scripts/validate_graph_phase2_boundary.py`.
- Graph benchmark artifacts now exist under
  `docs/graph/reference/read-model-benchmarks.md`.
- ADRs now exist for the remaining Phase 0 decisions:
  `docs/adr/0004-graph-runtime-naming-and-product-boundary.md`,
  `docs/adr/0005-graph-core-and-domain-pack-packaging.md`, and
  `docs/adr/0006-graph-read-model-ownership-and-truth-boundaries.md`.
- Current auth and role expectations were re-reviewed through the Phase 7
  cross-domain gate, which now proves graph-admin claim enforcement, membership
  checks, and role hierarchy across both built-in packs.

## Phase 1: Runtime Neutralization

Reference:
[`migration-phase2.md#phase-1-runtime-neutralization`](migration-phase2.md#phase-1-runtime-neutralization)

Scope and deliverables:

- [x] MED13-prefixed graph env names are replaced with neutral graph names
- [x] Graph runtime naming is isolated from MED13 application naming
- [x] Domain defaults are moved out of generic runtime config
- [x] Temporary compatibility aliases are minimized
- [x] Neutral graph runtime env contract is documented
- [x] Config docs and deploy references are updated
- [x] Alias policy and removal intent are documented
- [x] Runtime configuration and auth startup tests exist

Validation gate:

- [x] Graph service boots with neutral env names only
- [x] Any temporary aliases are documented with removal intent
- [x] No new MED13-specific graph env vars were introduced
- [x] Contract generation still passes unchanged
- [x] Client generation still passes unchanged

Notes:

- Neutral runtime envs already exist for the standalone service:
  `GRAPH_DATABASE_URL`, `GRAPH_SERVICE_*`, `GRAPH_DB_*`, and
  `GRAPH_JWT_SECRET`.
- Shared graph-core runtime env resolution now exists in
  `src/graph/core/runtime_env.py` and is consumed by both the standalone
  service config and the platform graph-service client runtime.
- Shared graph-service startup config now exists in
  `src/graph/core/service_config.py`; `services/artana_evidence_db/config.py` is now a
  thin compatibility wrapper.
- Pack-provided runtime identity defaults now resolve through the active pack,
  including the default graph service name and JWT issuer.
- Neutral graph feature-flag names now exist as the only supported graph
  runtime contract:
  `GRAPH_ENABLE_ENTITY_EMBEDDINGS`,
  `GRAPH_ENABLE_RELATION_SUGGESTIONS`,
  `GRAPH_ENABLE_HYPOTHESIS_GENERATION`, and
  `GRAPH_ENABLE_SEARCH_AGENT`.
- Graph runtime code, graph-facing docs, and graph deployment tooling now use
  neutral `GRAPH_*` names only; the removed alias set is recorded at
  `docs/graph/reference/runtime-alias-policy.md`.
- Phase-1 alias validation now exists at
  `scripts/validate_graph_phase1_alias_policy.py` and
  `make graph-phase1-alias-check`.
- Runtime/auth startup coverage exists in
  `tests/unit/graph/test_runtime_env.py`,
  `tests/unit/graph/test_service_config.py`,
  `tests/unit/services/artana_evidence_db/test_config.py`, and
  `tests/unit/services/artana_evidence_db/test_auth.py`.
- Contract and generated client validation now pass unchanged through
  `make graph-service-contract-check`.
- Shared platform auth wiring has also been neutralized beyond the standalone
  graph runtime: backend JWT and test-auth env resolution now flows through
  `src/infrastructure/security/runtime_env.py` using `AUTH_JWT_SECRET`,
  `AUTH_ALLOW_TEST_AUTH_HEADERS`, and `AUTH_BYPASS_JWT_FOR_TESTS`, with deploy
  wiring updated in `scripts/deploy/sync_cloud_run_runtime_config.sh` and
  `scripts/deploy/rollout_staging_queued_workers.sh`.

## Phase 2: Core And Domain-Pack Separation

Reference:
[`migration-phase2.md#phase-2-core-and-domain-pack-separation`](migration-phase2.md#phase-2-core-and-domain-pack-separation)

Scope and deliverables:

- [x] Graph-core module boundary is defined
- [x] Biomedical domain-pack boundary is defined
- [x] Biomedical view defaults are moved out of graph-core
- [x] Connector defaults are moved out of graph-core
- [x] Pack-local heuristics are moved out of graph-core
- [x] MED13 application wiring sits on top of the biomedical pack
- [x] Graph-core package or module boundary exists
- [x] Biomedical pack package or module boundary exists
- [x] Import-direction rules enforce core independence
- [x] Biomedical defaults and pack registrations are migrated

Validation gate:

- [x] Graph-core has no compile-time dependency on biomedical modules
- [x] Biomedical behavior loads through the pack boundary
- [x] MED13 functionality still works through the biomedical pack
- [x] Architecture validation blocks reverse imports from core to domain packs

Notes:

- Module boundaries now exist at `src/graph/core/` and
  `src/graph/domain_biomedical/`.
- The current runtime still has some remaining biomedical-shaped behavior in
  shared modules under `src/`, but the major Phase-2 seams now resolve through
  `src/graph/core`, `src/graph/domain_biomedical`, and shared graph runtime
  builders instead of service-local forks.
- Existing boundary validation now has two layers:
  `scripts/validate_graph_service_boundary.py` for standalone-service
  ownership, and `scripts/validate_graph_phase2_boundary.py` for future
  `graph-core` independence from the biomedical pack.
- Remaining Phase-2 work is concentrated in the remaining MED13 application
  wiring seams and in proving end-to-end MED13 application behavior entirely
  through the biomedical pack.
- Biomedical graph-view defaults now resolve through
  `src/graph/domain_biomedical/view_config.py` and are injected into the
  graph-view service instead of being hardcoded in the generic router/support
  layer.
- A minimal pack object now exists at `src/graph/core/domain_pack.py`, with the
  biomedical implementation wired through `src/graph/domain_biomedical/pack.py`
  and consumed by service dependencies for graph-view config resolution.
- Active pack selection now resolves through `src/graph/pack_registry.py`, so
  service/runtime modules no longer choose the biomedical pack directly.
- Builtin dictionary domain contexts now resolve through the active pack in
  `src/graph/domain_biomedical/dictionary_domain_contexts.py` instead of
  hardcoded biomedical text inside the generic graph governance repositories.
- Pack-owned source-type domain-context defaults now resolve through
  `src/graph/core/domain_context.py`, so graph ingestion and dictionary
  services no longer depend on biomedical `pubmed`/`clinvar` mappings baked
  into generic runtime helpers.
- Entity-recognition bootstrap content now resolves through the active pack,
  including bootstrap entity types, baseline PubMed graph types, and bootstrap
  relation definitions, instead of living only in shared helper constants.
- Source-type bootstrap selection for publication baselines is now pack-owned
  as well, so the shared bootstrap helper no longer special-cases `pubmed`
  directly.
- Publication-baseline synonym source labels and description text now come from
  the pack bootstrap config as well, rather than shared helper literals.
- The bootstrap contract itself is now publication-neutral in graph-core; the
  shared helper and pack API no longer expose `pubmed_baseline_*` naming.
- Relation auto-promotion env resolution now has a shared graph-core contract,
  with neutral `GRAPH_RELATION_AUTOPROMOTE_*` names as the only supported
  runtime contract.
- Relation auto-promotion policy types and parsing helpers now live in
  `src/graph/core/relation_autopromotion_policy.py`, so kernel repositories
  consume graph-core policy instead of owning that runtime contract.
- Relation auto-promotion default thresholds now resolve from the active pack,
  so graph-core provides the policy engine while the pack owns baseline
  promotion defaults.
- Relation repository construction in graph runtime/service composition now
  injects the resolved auto-promotion policy through
  `build_relation_repository(...)`, so the main graph service paths no longer
  depend on repository-local pack/env discovery.
- Graph-connection source-type defaults now resolve through the active pack in
  `src/graph/core/graph_connection_prompt.py`, so the standalone router,
  shared service, and HTTP client no longer hardcode `clinvar` as a generic
  connector default.
- The graph-connection service and Artana adapter now receive their
  graph-connection prompt config from service/runtime composition, so that
  slice no longer resolves the active pack implicitly from inside shared
  service or adapter code.
- The entity-recognition Artana adapter now receives its prompt and payload
  config from dependency-injection/service composition, so that live runtime
  path no longer resolves the active pack implicitly from inside the shared
  adapter itself.
- The extraction Artana adapter and its live prompt/payload helper path now
  receive extraction prompt and payload config from dependency-injection/service
  composition, so that live extraction runtime no longer resolves the active
  pack implicitly from inside shared adapter or payload-helper code.
- The live entity-recognition bootstrap helper path now reads bootstrap
  behavior from `EntityRecognitionServiceDependencies` instead of resolving the
  active pack internally from shared application helper code.
- The entity-recognition and extraction fallback helper modules now take
  explicit fallback config objects, so those helper-only paths no longer touch
  the global pack registry directly.
- The live dictionary repository builder path now injects builtin domain
  contexts from composition into both graph governance and shared runtime
  repositories, so MED13 runtime no longer depends on deep repository-method
  pack lookup for that domain-context seeding path.
- The shared graph-governance builders now also require builtin domain
  contexts explicitly, so standalone service/runtime composition injects
  dictionary seeding config at the builder edge instead of letting governance
  code fall back to the global pack registry.
- `SqlAlchemyKernelRelationRepository` now requires an explicit
  `auto_promotion_policy`, removing the remaining repository-local fallback and
  forcing runtime and test callers to compose relation policy deliberately.
- `SqlAlchemyGraphQueryRepository` now receives an explicit relation
  repository through shared builders, so graph query paths no longer create
  relation-policy-aware repositories internally.
- The standalone service no longer carries forked governance persistence
  implementations for dictionary and concept storage; the service-facing
  modules now act as compatibility re-exports over the shared
  `src/infrastructure/graph_governance` layer.
- Orphaned service-local dictionary persistence helper files have been removed,
  so `services/artana_evidence_db` no longer carries dead copies of dictionary search or
  repository mixin internals that are owned by `src/infrastructure/graph_governance`.
- Entity-recognition fallback field heuristics now resolve through the active
  graph pack, so shared LLM adapter fallback code no longer hardcodes
  biomedical `clinvar` and `pubmed` source-field mappings internally.
- Extraction fallback relation defaults and claim-text field ordering now
  resolve through the active graph pack, so shared extraction adapter fallback
  code no longer hardcodes the biomedical relation triple or text-field order.
- Entity-recognition compact raw-record shaping now resolves through the active
  graph pack as well, so shared adapter code no longer hardcodes the
  `pubmed`/`clinvar` payload field allowlists used for prompt compaction.
- Entity-recognition supported-source dispatch and system-prompt selection now
  resolve through the active graph pack, so the shared adapter no longer
  hardcodes the biomedical `pubmed` versus `clinvar` prompt split internally.
- Extraction supported-source dispatch and system-prompt selection now resolve
  through the active graph pack as well, so shared extraction adapter code no
  longer hardcodes the biomedical `pubmed` versus `clinvar` prompt split.
- Graph-connection supported-source dispatch and system-prompt selection now
  resolve through the active graph pack too, so the shared graph-connection
  adapter no longer hardcodes the biomedical `pubmed` versus `clinvar` prompt split.
- Extraction compact raw-record shaping now resolves through the active graph
  pack as well, including PubMed chunk-mode field selection, so shared
  extraction payload helpers no longer hardcode `pubmed`/`clinvar` allowlists.
- A focused pack-proof validation gate now exists as
  `make graph-phase2-biomedical-pack-check`, which runs representative
  pack-resolution, service-default, governance, DI, and standalone HTTP-boundary
  coverage under `GRAPH_DOMAIN_PACK=biomedical`.
- Platform-side application service factories now resolve the active graph pack
  through one shared helper and reuse it across live entity-recognition and
  extraction agent/service wiring, narrowing the remaining MED13 application
  wiring work to top-level service composition and graph-core runtime defaults.
- Graph-core domain-context resolution is now pack-policy-driven rather than
  pack-registry-driven: `src/graph/core/domain_context.py` requires an explicit
  `domain_context_policy`, and the current application/ingestion callers pass
  the active pack policy in from outside graph-core.
- Graph-core relation auto-promotion policy resolution is now default-driven
  rather than pack-registry-driven: `AutoPromotionPolicy.from_environment(...)`
  requires explicit `RelationAutopromotionDefaults`, and graph runtime
  composition supplies the active pack defaults.
- A shared `src/graph/runtime.py` helper module now owns active-pack-derived
  runtime helpers for the current codebase, and the application/ingestion
  callers that need domain-context policy or auto-promotion defaults now route
  through that helper instead of importing the pack registry directly.
- The standalone graph service composition/dependency layer now also routes
  active-pack resolution through `src/graph/runtime.py`, leaving direct
  `resolve_graph_domain_pack()` usage limited to startup/runtime helpers rather
  than everyday service composition code.
- Startup configuration now follows the same runtime-helper path, so direct
  pack-registry resolution is confined to `src/graph/runtime.py` and
  `src/graph/pack_registry.py` rather than service, application, or graph-core
  behavior modules.

## Phase 3: Extension And Access Platformization

Reference:
[`migration-phase2.md#phase-3-extension-and-access-platformization`](migration-phase2.md#phase-3-extension-and-access-platformization)

Scope and deliverables:

- [x] Extension interfaces for views are defined
- [x] Extension interfaces for search are defined
- [x] Extension interfaces for relation suggestions are defined
- [x] Extension interfaces for connectors are defined
- [x] Extension interfaces for dictionary loading are defined
- [x] Extension interfaces for pack registration are defined
- [x] Startup pack registration flow is defined
- [x] Graph-core auth abstractions are defined
- [x] Graph-core tenancy abstractions are defined
- [x] Application integration contract for JWT, roles, and tenant membership exists
- [x] Domain-pack registration lifecycle is documented

Validation gate:

- [x] Graph service can start with pack registration through explicit interfaces
- [x] Auth and tenancy abstractions remain domain-neutral
- [x] Service and RLS-aware behavior still produce the same authorization results
- [x] No pack overrides core invariants or projection logic

Notes:
- Pack-registration contracts now exist in `src/graph/core/pack_registration.py`
  and the current runtime uses an explicit in-memory registry implementation.
- The standalone graph service now bootstraps default domain packs during app
  startup in `services/artana_evidence_db/app.py` instead of relying only on implicit
  registry construction.
- Minimal graph-core access abstractions now exist in
  `src/graph/core/access.py`, and the standalone graph service membership
  checks map the current caller and membership role onto those neutral access
  decisions without changing the existing RLS/session behavior.
- Minimal graph-core tenancy abstractions now exist in
  `src/graph/core/tenancy.py`, and the standalone graph service now maps JWT
  callers, graph-space membership, and RLS session settings through explicit
  adapter helpers in `services/artana_evidence_db/auth.py` and
  `services/artana_evidence_db/database.py`.
- Focused unit and integration coverage now exercises the explicit auth and
  tenancy mapping path, including graph-space membership checks and graph-admin
  route enforcement, without changing the observed authorization outcomes.
- Graph view semantics now expose an explicit extension contract via
  `src/graph/core/view_config.py::GraphViewExtension`, and the standalone graph
  service graph-view wiring now depends on that interface instead of the
  concrete biomedical config type.
- Graph search semantics now expose an explicit extension contract via
  `src/graph/core/search_extension.py`, and the standalone graph-search adapter
  now receives pack-owned search prompt/step configuration from the active
  domain pack instead of hardcoding that contract internally.
- Relation-suggestion semantics now expose an explicit extension contract via
  `src/graph/core/relation_suggestion_extension.py`, and the constrained
  relation-suggestion service now receives pack-owned candidate retrieval policy
  from the active domain pack instead of hardcoding that runtime policy in the
  service body.
- Dictionary loading semantics now expose an explicit extension contract via
  `src/graph/core/dictionary_loading_extension.py`, and the shared governance
  builders now receive pack-owned dictionary loading configuration instead of
  accepting only loose builtin-domain-context tuples.
- Connector semantics now expose an explicit extension contract via
  `src/graph/core/graph_connection_prompt.py::GraphConnectorExtension`, and the
  live graph-connection runtime now reads connector step-key and prompt
  dispatch behavior from that interface instead of hardcoding those rules in
  the adapter body.
- Pack registration, startup bootstrap, active-pack resolution, and runtime
  consumption are now documented in
  `docs/graph/reference/domain-pack-lifecycle.md`.
- An explicit invariant validator now exists at
  `scripts/validate_graph_phase3_invariants.py`, covering both forbidden
  pack/runtime imports inside projection/reasoning invariant owners and the
  absence of projection/invariant override fields on `GraphDomainPack`.

-

## Phase 4: Query Index Foundation

Reference:
[`migration-phase2.md#phase-4-query-index-foundation`](migration-phase2.md#phase-4-query-index-foundation)

Scope and deliverables:

- [x] Generic read-model framework exists in graph-core
- [x] Incremental index updates attach to projection events
- [x] Incremental index updates attach to claim events
- [x] First bottleneck-driven read models are implemented
- [x] Full rebuild path exists for repair and backfill
- [x] Read-model schema and ownership rules are documented
- [x] Rebuild job for query indexes exists
- [x] Benchmark comparison exists for before and after index introduction

Initial read models:

- [x] `entity_relation_summary`
- [x] `entity_claim_summary`
- [x] `entity_neighbors`

Validation gate:

- [x] New read models are derived only from authoritative stores
- [x] Event-driven updates keep indexes fresh for target workflows
- [x] Full rebuild restores indexes correctly from source truth
- [x] Selected workloads show better benchmarked query latency

Notes:

- Graph-core read-model contracts now exist in `src/graph/core/read_model.py`,
  including the baseline generic catalog for `entity_neighbors`,
  `entity_relation_summary`, and `entity_claim_summary`.
- Ownership and authoritative-source rules are documented in
  `docs/graph/reference/read-model-ownership.md`.
- Validation for the Phase 4 foundation now exists in
  `scripts/validate_graph_phase4_read_models.py` with a matching
  `make graph-phase4-read-model-check` target and architecture test coverage.
- Claim-ledger and projection mutation owners now emit explicit
  `GraphReadModelUpdate` intents through an injected dispatcher from
  `KernelRelationClaimService` and
  `KernelRelationProjectionMaterializationService`.
- The current runtime adapter is now a projector-backed dispatcher that keeps
  `entity_neighbors`, `entity_relation_summary`, and `entity_claim_summary`
  refreshed from live claim and projection updates.
- Physical read-model tables, rebuild projectors, Alembic migrations, and
  rebuild scripts now exist for `entity_neighbors`,
  `entity_relation_summary`, and `entity_claim_summary`; benchmark artifacts
  now exist as well.
- Focused benchmark coverage now exists in
  `tests/performance/test_graph_query_performance.py`, with a dedicated
  `make graph-read-model-benchmark` target and a recorded benchmark artifact in
  `docs/graph/reference/read-model-benchmarks.md`.

## Phase 5: Reasoning Index Hardening

Reference:
[`migration-phase2.md#phase-5-reasoning-index-hardening`](migration-phase2.md#phase-5-reasoning-index-hardening)

Scope and deliverables:

- [x] Mechanism-oriented read models are added
- [x] Invalidation rules for reasoning indexes are defined
- [x] Rebuild behavior for reasoning indexes is defined
- [x] Reasoning paths remain derived from grounded claim structures
- [x] Advanced ranking and pruning remain deferred unless justified by metrics
- [x] Reasoning index schema exists
- [x] Invalidation hooks tie to claim and projection changes
- [x] Rebuild workflow for mechanism indexes exists
- [x] Mechanism-query benchmarks and correctness checks exist

Initial reasoning indexes:

- [x] `entity_mechanism_paths`

Validation gate:

- [x] Mechanism indexes are rebuildable
- [x] Reasoning reads are materially faster for supported workflows
- [x] No reasoning index becomes a truth source
- [x] Hypothesis generation still depends on claim-backed reasoning inputs

Notes:

- `entity_mechanism_paths` now exists as a physical graph-core reasoning index in
  `src/models/database/kernel/read_models.py` with projector ownership in
  `src/application/services/kernel/kernel_entity_mechanism_paths_projector.py`
  and migration `014_entity_mechanism_paths`.
- `KernelReasoningPathService` now owns reasoning-index freshness at the real
  reasoning boundary: space rebuilds trigger a full mechanism-index rebuild,
  and claim / claim-relation staleness flows dispatch `CLAIM_CHANGE` and
  `PROJECTION_CHANGE` invalidation updates for the affected mechanism rows.
- Hypothesis-generation seed reads now use the compact mechanism index through
  `KernelReasoningPathService.list_mechanism_candidates(...)` instead of
  fanout through `list_paths(...)` + `get_path(...)` for each path candidate.
- `make graph-reasoning-index-benchmark` now records the first Phase 5
  reasoning comparison. On March 13, 2026, the isolated-Postgres benchmark
  measured `313.92 ms` legacy seed reads versus `5.93 ms` indexed reads for
  `entity_mechanism_paths`, a `52.92x` speedup.

## Phase 6: Product Boundary Hardening

Reference:
[`migration-phase2.md#phase-6-product-boundary-hardening`](migration-phase2.md#phase-6-product-boundary-hardening)

Scope and deliverables:

- [x] API versioning policy is defined
- [x] Deprecation policy is defined
- [x] Generated-client ownership is defined
- [x] Generated-client release process is defined
- [x] Runtime-to-client compatibility expectations are defined
- [x] Operator upgrade workflow is documented
- [x] Release checklist exists
- [x] Upgrade guide exists

Validation gate:

- [x] OpenAPI remains the release contract
- [x] Contract checks run before release
- [x] Generated clients are treated as versioned artifacts
- [x] Breaking changes require explicit release intent and migration notes

Notes:

- Shared graph-service product metadata now lives in
  `src/graph/product_contract.py`, so runtime versioning, OpenAPI ownership,
  health metadata, and release-artifact paths resolve through one graph-core
  contract.
- Phase-6 release validation now exists at
  `scripts/validate_graph_phase6_release_contract.py` and is wired into
  `make graph-phase6-release-check`.
- Release-boundary docs now exist at
  `docs/graph/reference/release-policy.md`,
  `docs/graph/reference/release-checklist.md`, and
  `docs/graph/reference/upgrade-guide.md`.
- `make graph-service-checks` now includes the Phase-6 release validator, so
  graph-service contract freshness, generated-client ownership, and release
  docs are enforced together with lint, typing, and service tests.

## Phase 7: Cross-Domain Proof

Reference:
[`migration-phase2.md#phase-7-cross-domain-proof`](migration-phase2.md#phase-7-cross-domain-proof)

Scope and deliverables:

- [x] Biomedical remains the primary production pack
- [x] At least one non-biomedical pack is implemented
- [x] Shared extension model is validated across packs
- [x] Shared auth model is validated across packs
- [x] Shared contract-generation model is validated across packs
- [x] Shared query-index model is validated across packs
- [x] Cross-domain validation matrix results are recorded
- [x] Shared graph-core examples across domains are documented
- [x] Pack-boundary leakage findings are documented

Candidate non-biomedical packs:

- Sports analytics
- Policy or enterprise knowledge

Validation gate:

- [x] Non-biomedical pack runs without core forks
- [x] Auth and tenancy model works unchanged
- [x] Contract-generation and release workflow works unchanged
- [x] Query-index framework supports both domains without special-casing core logic

Notes:

- A forward-only sports pack now exists at `src/graph/domain_sports/pack.py`.
- Built-in pack registration now includes both `biomedical` and `sports`, while
  the default active pack remains `biomedical`.
- Focused pack and runtime tests now prove `GRAPH_DOMAIN_PACK=sports` resolves
  through the same registry and startup-config path used by the biomedical pack.
- The standalone graph-service integration suite now includes a sports-pack
  HTTP-boundary proof covering dictionary domain-context seeding for
  `competition` and connector default dispatch with `source_type=match_report`.
- Cross-domain proof now has an explicit gate at
  `make graph-phase7-cross-domain-check`, with static validation in
  `scripts/validate_graph_phase7_cross_domain.py` and recorded results in
  `docs/graph/reference/cross-domain-validation-matrix.md`.
- The same cross-domain gate now covers graph-admin claim enforcement and
  tenant membership / role hierarchy for both `biomedical` and `sports`.
- The cross-domain gate now also covers the shared `entity_neighbors`
  read-model path, proving the one-hop neighborhood index works unchanged
  across both built-in packs.
- Shared graph-core examples are now documented in
  `docs/graph/reference/cross-domain-examples.md`.
- Current pack-boundary closure status and residual proof gaps are documented
  in `docs/graph/reference/pack-boundary-leakage.md`.

## Cross-Phase Workstreams

### Workstream A: Architecture And Packaging

- [x] Core/module split is tracked
- [x] Dependency validation is tracked
- [x] Pack lifecycle is tracked

### Workstream B: Auth And Access

- [x] Portable auth abstractions are tracked
- [x] Application identity integration is tracked
- [x] RLS-aware behavior validation is tracked

### Workstream C: Query Performance

- [x] Benchmark design is tracked
- [x] Read-model implementation is tracked
- [x] Event-driven updates are tracked
- [x] Rebuild workflows are tracked

### Workstream D: Product Boundary

- [x] OpenAPI ownership is tracked
- [x] Client generation is tracked
- [x] Versioning is tracked
- [x] Release and upgrade policy is tracked

### Workstream E: Domain Proof

- [x] Biomedical-pack stabilization is tracked
- [x] Non-biomedical-pack implementation is tracked
- [x] Cross-domain validation matrix is tracked

## Final Exit Criteria

Reference:
[`migration-phase2.md#exit-criteria`](migration-phase2.md#exit-criteria)

- [x] Graph-core runs without biomedical modules in its dependency chain
- [x] Neutral graph naming replaces MED13-specific runtime naming
- [x] Domain-specific defaults are removed from graph-core
- [x] Biomedical behavior loads through explicit extension points
- [x] The MED13 application uses the biomedical pack without core changes
- [x] Read-model strategy is implemented or clearly deferred with no ambiguity
- [x] Auth, tenancy, and RLS behavior are documented as part of the product boundary
- [x] API versioning, deprecation, and generated-client policy are documented
- [x] At least one non-biomedical domain pack proves the architecture without core forks

## Closure Note

This checklist is now materially complete for the scope defined in
`migration-phase2.md`.

Remaining follow-on work, if pursued, belongs to a new post-phase-2 roadmap
rather than this tracker. Examples include:

1. Add a second non-biomedical pack beyond `sports`.
2. Extend cross-pack read-model proof beyond the currently benchmarked paths.
3. Broaden cross-pack auth and tenancy proof across additional route families.
