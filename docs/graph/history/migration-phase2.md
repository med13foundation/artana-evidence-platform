# Migration Phase 2

**Graph Platform Evolution Plan**

## Purpose

This document records the proposed second phase of graph-service evolution after
the standalone extraction work.

It focuses on the remaining gaps between:

- the current standalone MED13 graph service
- a reusable, domain-neutral graph platform

This plan keeps the existing claim-first scientific model intact while defining
the work needed to:

- remove MED13-specific coupling from the core runtime
- separate generic graph behavior from domain-specific behavior
- improve query scalability with derived read models
- formalize auth, tenancy, contract, and release boundaries
- prove that the service can support multiple domains without core forks

## How To Read This Document

- `Current state` means implemented in the repo today.
- `Target state` means the intended end state for phase 2.
- `Proposed` means design guidance or roadmap work that is not yet implemented.

The current source of truth for the live graph-service contract remains:

- `services/artana_evidence_db/openapi.json`
- `services/artana_evidence_db/routers/`
- `src/web/types/artana-evidence-db.generated.ts`

If this design doc disagrees with those artifacts, treat the generated contract
and route implementation as authoritative for current behavior.

## Implementation Status

As of `2026-03-13`, the implementation tracked by this plan is closed in the
repo and validated through the graph-service, boundary, release, and
cross-domain quality gates.

Use [`migration-phase2-checklist.md`](migration-phase2-checklist.md) as the
implementation ledger for what landed and which validation gates prove it.
This document remains a mixed design-and-state record: it still describes
`Current state`, `Target state`, and `Proposed` architecture to explain the
rationale behind the implemented result.

## Current Implemented Baseline

The graph service already has a strong standalone boundary.

Current state:

- standalone FastAPI service boundary
- generated OpenAPI contract and generated TypeScript client types
- graph-space-scoped auth and access checks
- graph-specific operational workflows and repair scripts
- claim-first data model with canonical projections and reasoning artifacts

### Implemented Knowledge Model

The implemented graph model is:

```text
evidence -> claims -> projections -> canonical graph -> reasoning artifacts
```

More concretely:

```text
claim_evidence
-> relation_claims
-> relation_projection_sources
-> relations
-> reasoning_paths
-> hypothesis claims
```

Core current invariants:

- claims are the authoritative assertion ledger
- canonical relations are projections, not an independent truth source
- every canonical relation must be explainable by support claims
- reasoning paths are derived artifacts, not a second truth store
- hypotheses stay in claim space unless explicitly curated

### Implemented Auth, Tenancy, And Access Model

One of the gaps in the earlier docs set was that productization work was being
discussed without clearly describing the live access model. Phase 2 must keep
this explicit.

Current state:

- `GET /health` is unauthenticated
- all `/v1/...` routes require an authenticated caller
- end-user initiated requests use bearer JWTs
- local and test workflows can use test-auth headers when enabled
- space-scoped reads generally require graph-space membership
- most space-scoped writes require `researcher+`
- curation and review mutations require `curator+`
- `/v1/admin/...` and `/v1/dictionary/...` require `graph_admin`

Current state also includes database-session-aware enforcement:

- the service sets graph-space and graph-admin-aware DB session context
- authorization is enforced at both the service layer and the Postgres-session
  layer when RLS-aware paths are used

This matters because a productized graph platform cannot treat auth as an
afterthought. The access model is part of the product boundary.

### Implemented Operational And Contract Surface

Current state:

- `make graph-readiness`
- `make graph-reasoning-rebuild`
- `make graph-space-sync`
- `make graph-service-openapi`
- `make graph-service-client-types`
- `make graph-service-sync-contracts`
- `make graph-service-checks`

These existing commands already give the service some product-like qualities:

- readiness checks
- repair and rebuild flows
- contract generation
- generated client artifacts
- validation and CI-friendly quality gates

### Current MED13-Specific Coupling

The core graph model is close to reusable, but the runtime still carries MED13
and biomedical assumptions.

Current examples:

```text
MED13_DEV_JWT_SECRET
MED13_ENABLE_ENTITY_EMBEDDINGS
MED13_ENABLE_RELATION_SUGGESTIONS
MED13_ENABLE_HYPOTHESIS_GENERATION
MED13_ENABLE_GRAPH_SEARCH_AGENT
```

Current domain-shaped behavior also includes:

```text
biomedical view types
ClinVar defaults
biomedical connectors
repo-local MED13 naming and packaging assumptions
```

## Problem Statement

The graph service is already a real service, but it is not yet a reusable
platform product.

The remaining gaps are:

1. MED13-specific naming and defaults still appear in runtime and feature flags.
2. Biomedical assumptions still leak into routes, views, and connectors.
3. The service still depends on shared MED13 monorepo code rather than a clean
   core package boundary.
4. Querying the claim-first model can become expensive without dedicated read
   models.
5. Product boundaries for auth, versioning, compatibility, generated SDKs, and
   upgrade policy are not yet formalized.
6. The system has not yet proven domain neutrality through multiple active
   domain packs.

### Query Performance Driver

The claim-first architecture introduces deep join paths for common graph reads.

Example path:

```text
relations
-> relation_projection_sources
-> relation_claims
-> claim_participants
-> claim_evidence
```

This join depth is correct for explainability, but it increases latency for
high-volume graph queries and justifies a dedicated read-model strategy.

## Phase 2 Goals

Phase 2 should achieve the following:

1. preserve the claim-first scientific architecture
2. separate graph core from domain-specific behavior
3. neutralize MED13-specific runtime naming
4. define extension points for domain packs
5. add a query/read-model strategy for scale
6. formalize product-grade auth, contract, and release boundaries
7. demonstrate domain neutrality with more than one domain pack

## What Must Not Change

The following invariants are non-negotiable:

```text
claims remain authoritative
canonical relations remain projections
reasoning artifacts remain derived
hypotheses remain claim-space only
projection lineage remains explainable
rebuildability remains mandatory
```

These rules preserve scientific correctness and explainability.

## Target Architecture

The target architecture has three layers:

```text
graph-core
-> domain-pack
-> application
```

### Layer 1: Graph Core

Target state:

- domain-neutral graph runtime
- domain-neutral schema and service abstractions
- neutral auth, tenancy, and policy interfaces
- neutral query and read-model framework
- generated contract and client tooling owned by the product boundary

Graph core responsibilities:

```text
entities
observations
relation_claims
claim_participants
claim_evidence
claim_relations
relations
relation_projection_sources
relation_evidence
reasoning_paths
hypothesis framework
graph traversal
graph search framework
tenancy and access abstractions
dictionary framework
contract generation
```

The core must not contain:

```text
gene-specific views
ClinVar defaults
biomedical connectors
biomedical value assumptions
MED13-branded env names
```

### Graph-Core Stability Contract

Graph-core must remain domain-neutral.

Domain packs may extend behavior through defined interfaces, but they must not:

- change core projection logic
- change claim invariants
- change canonical graph rules
- require graph-core to import domain-pack modules

Graph core may load domain-pack registrations at runtime, but graph core must
never depend on domain-pack code as a compile-time architectural requirement.

### Layer 2: Domain Packs

Target state:

- domain-specific semantics are moved out of the core
- each pack contributes its own entity types, relation types, connectors, view
  definitions, defaults, prompts, and heuristics

Example biomedical pack:

```text
entity types:
  gene
  variant
  phenotype
  pathway
  paper

relation types:
  associated_with
  regulates
  part_of

connectors:
  ClinVar
  PubMed
  gnomAD

views:
  gene
  variant
  phenotype
```

Domain-pack responsibilities may include:

```text
dictionary entries
domain views
connector adapters
default pipelines
reasoning heuristics
pack-specific examples and tests
```

### Layer 3: Applications

Applications build product or workflow experiences on top of the graph platform.

Example:

```text
med13-app
```

Application responsibilities:

```text
UI
curation workflows
domain-specific orchestration
research tools
end-user interaction patterns
```

Applications should depend on:

```text
graph-core
+ one or more domain packs
```

## Auth, Tenancy, And Access Product Boundary

One of the missing pieces in the earlier draft was a clear statement of how
auth belongs in the platform design.

### Current State

Current state already enforces:

- authenticated `/v1/...` routes
- graph-space membership checks
- role-based write restrictions
- `graph_admin` control-plane access
- DB session context for graph-aware RLS behavior

### Target State

Target state should preserve the same control model while making it portable.

Graph core should own neutral access abstractions such as:

```text
Principal
Tenant or GraphSpace
Capability or RolePolicy
PolicyDecision
SessionContextWriter
```

Applications should provide:

```text
identity provider integration
JWT issuance and verification policy
role mapping from app identity to graph capabilities
operator provisioning workflows
```

Domain packs may declare additional policy needs, but they must not redefine
core auth semantics.

### Product Requirement

For the graph platform to be reusable, a new application should be able to:

- plug in its own identity provider
- map users into graph tenants or spaces
- use the same capability model and enforcement hooks
- keep contract-level role expectations stable across domains

## Extension Interfaces

Phase 2 should replace implicit coupling with explicit extension points.

Proposed interfaces:

```text
GraphViewProvider
GraphSearchProvider
RelationSuggestionProvider
DomainConnector
DictionaryLoader
DomainPackRegistry
```

The goal is that adding a new domain does not require changing graph-core code
for basic pack registration and execution.

### Extension Lifecycle

Domain packs should be registered during service startup.

Graph core loads:

- dictionary entries
- domain views
- connector adapters
- reasoning heuristics
- pack-owned read-model registrations

Domain packs may extend behavior through the defined interfaces, but they may
not override core data invariants or replace the claim-to-projection model.

## Query And Read-Model Strategy

The claim-first architecture is correct for explainability, but it creates deep
join paths for common reads.

### Long-Term Scaling Pattern

Large claim-backed knowledge systems eventually converge on three permanent
layers:

```text
assertion ledger
-> materialized knowledge graph
-> query indexes
```

The current graph service already has the first two layers.
Phase 2 adds the third.

### Why Read Models Are Needed

Common graph queries often need to walk through:

```text
relations
-> relation_projection_sources
-> relation_claims
-> claim_participants
-> claim_evidence
```

This is a good correctness path, but it is a poor default query path for
high-volume neighborhood and summary reads.

At scale, two things happen:

1. join depth increases
2. query cost grows non-linearly

This is the point where claim-first graph systems usually need a dedicated query
index layer.

### Current Query Layers

Current state:

1. authoritative claim ledger
2. canonical graph projections
3. derived reasoning artifacts

### Target Query Layers

Target state should make the read path explicit:

1. authoritative ledger
2. canonical graph
3. query read models

#### Layer 1: Authoritative Ledger

Current state:

```text
relation_claims
claim_participants
claim_evidence
claim_relations
```

Purpose:

```text
scientific correctness
traceability
auditability
```

This layer is write-optimized.
Routine user-facing queries should rarely hit it directly.

#### Layer 2: Canonical Graph

Current state:

```text
relations
relation_projection_sources
relation_evidence
```

Purpose:

```text
stable graph reads
claim-backed browsing
projection explainability
```

This layer is graph-optimized.
Most graph traversal queries should stop here unless they need deeper evidence
drilldown.

#### Layer 3: Query Read Models

Proposed state:

```text
entity_neighbors
entity_relation_summary
entity_claim_summary
entity_mechanism_paths
entity_evidence_summary
```

Purpose:

```text
fast neighborhood reads
search-oriented summaries
UI-friendly payloads
lower join cost
cache-friendly query surfaces
```

These read models:

```text
denormalize the graph
precompute join paths
store summary metrics
```

Important clarification:

- these read models are proposed, not current repo tables
- they must be rebuildable from the authoritative stores
- they must never become a second truth source
- phase 2 may implement only a minimal subset of read models based on observed
  query bottlenecks rather than creating every possible summary table up front

### Read-Model Ownership

Read models belong to graph-core because they are part of the platform query
surface.

Graph core may own generic read models such as:

```text
entity_neighbors
entity_relation_summary
entity_claim_summary
```

Domain packs may contribute pack-specific read models such as:

```text
gene_phenotype_summary
team_player_connection_summary
```

Even when a domain pack contributes a read model, the rebuild framework,
materialization rules, and truth-source boundaries remain owned by graph-core.

### Query Flow

Target query order:

```text
query read model
-> canonical graph
-> claim ledger
```

Typical UI or API reads should hit read models first.
Explainability and evidence drilldown should resolve through projection lineage
and then back to claims and evidence.

After scaling improvements, the effective query stack becomes:

```text
applications
-> read models
-> canonical graph
-> claim ledger
```

Most queries should never need to touch the authoritative ledger directly.

### Example Query Before Indexes

Without query indexes, a typical graph question can require several joins:

```sql
SELECT ...
FROM relations r
JOIN relation_projection_sources p ON p.relation_id = r.id
JOIN relation_claims c ON c.id = p.claim_id
JOIN claim_participants cp ON cp.claim_id = c.id
JOIN claim_evidence e ON e.claim_id = c.id
WHERE r.source_entity_id = 'MED13';
```

This shape is correct for provenance, but expensive for high-volume reads.

### Example Read Model

Example proposed table:

```text
entity_neighbors
```

Example shape:

```text
entity_id
neighbor_entity_id
relation_type
support_count
confidence
last_updated
```

Example query:

```sql
SELECT * FROM entity_neighbors
WHERE entity_id = 'MED13';
```

This avoids repeated deep joins into claim tables for routine neighborhood reads.

### Example Query After Indexes

With read models, the same access pattern becomes:

```sql
SELECT *
FROM entity_neighbors
WHERE entity_id = 'MED13';
```

One indexed table replaces a multi-join traversal.

### Mechanism Indexes

Mechanism reasoning is one of the system's differentiators, so it should be
indexed explicitly rather than treated as a side effect.

Example proposed table:

```text
entity_mechanism_paths
```

Example row shape:

```text
start_entity
end_entity
path_length
confidence
path_signature
last_updated
```

Example:

```text
start_entity: MED13
end_entity: speech_delay
path_length: 3
confidence: 0.74
path_signature:
MED13 -> mediator_complex -> transcription -> neurodevelopment
```

This makes reasoning-path reads fast without weakening the claim-first model.

### Operational Rebuild Model

Current state already includes:

- `make graph-readiness`
- `make graph-reasoning-rebuild`

Target state should add read-model rebuild support only after read models
actually exist.

Proposed future command:

```text
graph-read-model-rebuild
```

That command should be documented as future work until the underlying tables and
rebuild jobs are implemented.

Read models may be updated by:

- projection materialization events
- claim triage updates
- ingestion batches
- scheduled rebuild operations

Event-driven refresh is the preferred steady-state model.
Full rebuilds remain necessary for recovery, backfill, and repair.

### Event-Driven Integration

The current service is already close to this pattern because it has:

```text
claim ledger
projection materialization
reasoning-path rebuild
readiness checks
```

Phase 2 mainly adds:

```text
query read models
event-driven index updates
```

One natural integration point is the projection materialization flow.

For example, after `KernelRelationProjectionMaterializationService` updates the
canonical graph, it could trigger proposed index updaters such as:

```text
EntityNeighborIndexUpdater
EntityMechanismIndexUpdater
EntityClaimSummaryUpdater
```

These names are illustrative, but the pattern is the important part:
projection and claim events should update read models incrementally instead of
recomputing the entire query surface on every change.

### Performance Characteristics

This pattern is common in large ledger-backed, event-sourced, and graph-heavy
systems because:

```text
joins disappear
aggregations are precomputed
paths are indexed
```

In practice, teams often see order-of-magnitude improvements in graph query
latency after introducing query indexes. For this system, `10-50x` is a
reasonable design target for the affected workloads, not a guaranteed outcome.

### Non-Negotiable Direction Of Truth

Read models must never become a source of truth.

The invariant remains:

```text
claims -> projections -> read models
```

Never:

```text
read models -> graph updates
```

## Current State Versus Proposed State

To avoid confusion, phase 2 should explicitly distinguish what exists today from
what is still design work.

| Area | Current state | Target state |
| --- | --- | --- |
| Standalone API | Implemented | Preserve |
| Claim-first ledger | Implemented | Preserve |
| Canonical projections | Implemented | Preserve |
| Reasoning-path rebuilds | Implemented | Preserve and harden |
| Query read models | Not implemented as dedicated tables | Add rebuildable derived read tables |
| MED13 env naming | Present | Replace with neutral naming |
| Biomedical defaults in runtime | Present | Move into domain packs |
| Core/package separation | Partial | Split graph-core from domain packs and applications |
| Auth and RLS behavior | Implemented in service | Formalize as portable product boundary |
| Generated contract and TS types | Implemented | Add release and compatibility policy |
| Multi-domain proof | Not demonstrated | Validate with multiple domain packs |

## Packaging, Versioning, And Compatibility

Another missing gap in the earlier draft was product policy around releases and
client compatibility.

### Current State

Current state already provides:

- generated OpenAPI
- generated TypeScript client types
- contract-check commands in the repo

### Target State

A productized graph platform should add:

- semantic versioning for the public HTTP API
- a deprecation policy for breaking route or schema changes
- release notes for contract changes
- upgrade docs for operators and application teams
- generated SDK ownership and publish process
- compatibility testing between runtime and generated clients

### Product Rules

Recommended rules:

1. OpenAPI is the release contract.
2. Generated clients are versioned artifacts, not ad hoc build outputs.
3. Breaking API changes require an intentional version bump and migration notes.
4. Deprecations must be called out before removal.
5. Contract checks run in CI before release.

## Domain-Neutrality Proof Plan

The platform should not claim domain neutrality only because the abstractions
look generic. It should prove it through working domain packs.

### Minimum Proof

Phase 2 should validate at least three application shapes:

1. biomedical research
2. sports analytics
3. policy or enterprise knowledge

### Success Criteria

Domain neutrality is credible only if:

- graph-core code does not need domain forks
- domain packs provide the schema, connectors, and defaults
- the same auth and tenancy model works unchanged
- the same contract-generation and release process works unchanged
- the same query-layer strategy works across domains

### Test Matrix

Phase 2 should define a validation matrix covering:

- pack registration
- dictionary loading
- connector dispatch
- graph search behavior
- graph view behavior
- authorization expectations
- generated contract stability
- rebuild and readiness operations

## Future Scaling Risks

These are not phase-2 blockers, but they should shape the design.

### Claim Explosion

Automated ingestion can create very large numbers of claims for one entity pair
or one evidence family.

Likely future needs:

- claim clustering
- claim aggregation
- confidence scoring

### Reasoning Path Explosion

Reasoning paths can grow combinatorially as more intermediate entities and claim
chains become available.

Likely future needs:

- path scoring
- path pruning
- path ranking

### Domain-Pack Boundary Leakage

Domain packs can accidentally reintroduce coupling if generic services begin to
depend on pack-local assumptions.

Guardrail:

```text
graph core must never depend on domain-pack modules
```

This rule should be enforced in code organization, dependency direction, and
review.

## Implementation Plan

Phase 2 should be executed as a sequence of independently shippable phases.

Implementation principles:

- preserve claim-first invariants in every phase
- ship one architectural boundary change at a time
- keep the live HTTP contract stable unless a phase explicitly version-bumps it
- add benchmarks and validation gates before adding scaling complexity
- prefer feature-gated rollout for new read models and new pack-loading paths
- do not let future read models or domain packs weaken explainability

### Phase 0: Baseline And Guardrails

Objective:
Establish the measurement, validation, and safety rails needed to refactor the
service without drifting from the live product boundary.

Scope:

- record current route contract and generated client outputs
- capture current auth and access expectations
- benchmark representative graph reads
- document dependency boundaries that must not be broken
- define architectural validation checks for core versus domain-pack imports

Deliverables:

- frozen OpenAPI snapshot for phase-start comparison
- generated TypeScript client baseline
- baseline query benchmark set for graph reads and evidence drilldown
- dependency-boundary rules for graph-core versus domain-pack code
- implementation ADRs for naming, packaging, and read-model ownership

Validation gate:

- `make graph-service-checks` passes
- benchmark suite exists and produces repeatable numbers
- boundary-validation script exists or is clearly scoped
- current auth and role expectations are documented and reviewed

### Phase 1: Runtime Neutralization

Objective:
Remove MED13-branded runtime assumptions from the graph-service boundary without
changing the scientific model.

Scope:

- replace MED13-prefixed graph env names with neutral graph names
- isolate graph runtime naming from MED13 application naming
- move domain defaults out of generic runtime config
- keep compatibility aliases only where operationally necessary

Deliverables:

- neutral graph runtime env contract
- updated config docs and deploy references
- explicit compatibility policy for any temporary aliases
- tests covering both required runtime configuration and auth startup behavior

Validation gate:

- graph service boots with neutral env names only
- any temporary aliases are documented with removal intent
- no new MED13-specific graph env vars are introduced
- contract and client generation still pass unchanged

### Phase 2: Core And Domain-Pack Separation

Objective:
Create a real architectural split between graph-core and biomedical behavior.

Scope:

- define the graph-core module boundary
- define the biomedical domain-pack boundary
- move biomedical view defaults, connector defaults, and pack-local heuristics
  out of graph-core
- keep MED13 application wiring on top of the biomedical pack

Target module shape:

```text
graph-core
graph-domain-biomedical
med13-app
```

Deliverables:

- graph-core package or module boundary
- biomedical pack package or module boundary
- import-direction rules enforcing core independence
- migrated biomedical defaults and pack registrations

Validation gate:

- graph-core has no compile-time dependency on biomedical modules
- biomedical behavior loads through the pack boundary
- MED13-specific functionality still works through the biomedical pack
- architecture validation blocks reverse imports from core to domain packs

### Phase 3: Extension And Access Platformization

Objective:
Formalize the extension lifecycle and portable product boundary.

Scope:

- define extension interfaces for views, search, relation suggestions,
  connectors, dictionary loading, and pack registration
- define startup pack registration flow
- formalize portable auth, tenancy, and policy abstractions
- make application identity integration explicit

Deliverables:

- stable extension interface definitions
- domain-pack registration lifecycle documentation
- graph-core auth and tenancy abstractions
- application integration contract for JWT, role mapping, and tenant membership

Validation gate:

- graph service can start with pack registration through explicit interfaces
- auth and tenancy abstractions remain domain-neutral
- service and RLS-aware behavior still produce the same authorization results
- no pack overrides core invariants or projection logic

### Phase 4: Query Index Foundation

Objective:
Add the first production-grade query indexes and update pipeline.

Scope:

- implement the generic read-model framework in graph-core
- attach incremental index updates to projection and claim events
- add a minimal first set of read models for proven bottlenecks
- keep full rebuild capability for repair and backfill

Initial read models:

```text
entity_neighbors
entity_relation_summary
entity_claim_summary
```

Deliverables:

- read-model schema and ownership rules
- event-driven update hooks from claim and projection changes
- rebuild job for query indexes
- benchmark comparisons before and after index introduction

Validation gate:

- new read models are derived only from authoritative stores
- event-driven updates keep indexes fresh for target workflows
- full rebuild restores indexes correctly from source truth
- benchmarked query latency improves for selected workloads

### Phase 5: Reasoning Index Hardening

Objective:
Make reasoning and mechanism queries scale without weakening scientific
traceability.

Scope:

- add mechanism-oriented read models
- define invalidation and rebuild behavior for reasoning indexes
- keep reasoning paths explicitly derived from grounded claim structures
- defer advanced ranking and pruning unless metrics justify them

Initial reasoning indexes:

```text
entity_mechanism_paths
```

Deliverables:

- reasoning index schema
- invalidation rules tied to claim and projection changes
- rebuild workflow for mechanism indexes
- mechanism-query benchmarks and correctness checks

Validation gate:

- mechanism indexes are rebuildable
- reasoning reads are materially faster for supported workflows
- no reasoning index becomes a truth source
- hypothesis generation still depends on claim-backed reasoning inputs

### Phase 6: Product Boundary Hardening

Objective:
Make the graph service behave like a versioned product boundary rather than a
repo-local subsystem.

Scope:

- formalize API versioning and deprecation rules
- define generated-client ownership and release process
- add compatibility expectations between runtime and generated clients
- document operator upgrade workflow

Deliverables:

- versioning policy
- deprecation policy
- generated SDK or client publication plan
- release checklist and upgrade guide

Validation gate:

- OpenAPI remains the release contract
- contract checks run before release
- generated clients are treated as versioned artifacts
- breaking changes require explicit release intent and migration notes

### Phase 7: Cross-Domain Proof

Objective:
Prove that the architecture is actually domain-neutral.

Scope:

- keep biomedical as the primary production pack
- implement at least one non-biomedical pack
- validate the same extension, auth, contract, and query model across packs

Candidate non-biomedical packs:

```text
sports analytics
policy or enterprise knowledge
```

Deliverables:

- one working non-biomedical domain pack
- cross-domain validation matrix results
- examples showing shared graph-core behavior across domains
- documented lessons from any pack-boundary leakage found during implementation

Validation gate:

- non-biomedical pack runs without core forks
- auth and tenancy model works unchanged
- contract-generation and release workflow works unchanged
- query-index framework supports both domains without special-casing core logic

## Phase Dependencies

Recommended dependency order:

```text
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6 -> Phase 7
```

Critical dependency notes:

- do not build query indexes before core/package boundaries are stable enough to
  own them
- do not claim productization before versioning and compatibility policy exist
- do not claim domain neutrality before a second pack runs without core forks
- do not optimize reasoning indexes before the generic query-index layer exists

## Workstreams Across Phases

Some workstreams cut across multiple phases and should be tracked explicitly.

### Workstream A: Architecture And Packaging

- core/module split
- dependency validation
- pack lifecycle

### Workstream B: Auth And Access

- portable auth abstractions
- application identity integration
- RLS-aware behavior validation

### Workstream C: Query Performance

- benchmark design
- read-model implementation
- event-driven updates
- rebuild workflows

### Workstream D: Product Boundary

- OpenAPI ownership
- client generation
- versioning
- release and upgrade policy

### Workstream E: Domain Proof

- biomedical-pack stabilization
- non-biomedical-pack implementation
- cross-domain validation matrix

## Robustness Requirements

The implementation plan is only successful if it is operationally robust.

Every phase should include:

- unit coverage for new core logic
- integration coverage for route and data-path changes
- contract checks against generated OpenAPI and generated clients
- migration or rebuild rehearsals for any new derived stores
- benchmark comparison for performance-sensitive phases
- rollback or disablement strategy for new optional read models

## Architecture Overview Diagram

This diagram shows the target structure after graph-core and domain-pack
separation.

```text
                    ┌──────────────────────────────┐
                    │         Applications         │
                    │                              │
                    │  MED13 app / other apps      │
                    │  UI / pipelines / agents     │
                    └───────────────▲──────────────┘
                                    │
                                    │ Graph API
                                    │
                    ┌───────────────┴──────────────┐
                    │        Graph Service         │
                    │      product boundary        │
                    │                              │
                    │  auth / API / search / ops   │
                    └───────────────▲──────────────┘
                                    │
                 ┌──────────────────┴──────────────────┐
                 │                                     │
      ┌──────────▼──────────┐               ┌──────────▼──────────┐
      │      Graph Core     │               │     Domain Pack     │
      │   domain-neutral    │               │  biomedical, etc.   │
      │                     │               │                     │
      │ claims ledger       │               │ entity types        │
      │ canonical graph     │               │ relation types      │
      │ read-model engine   │               │ views               │
      │ reasoning framework │               │ connectors          │
      │ tenancy interfaces  │               │ prompts/defaults    │
      └──────────▲──────────┘               └──────────▲──────────┘
                 │                                     │
                 └──────────────────┬──────────────────┘
                                    │
                              ┌─────▼─────┐
                              │ Postgres  │
                              │ ledger    │
                              │ graph     │
                              │ read mods │
                              └───────────┘
```

## Claim Lifecycle

The claim lifecycle remains the core mental model and must survive phase 2
unchanged.

```text
Source evidence
-> relation_claims
-> claim triage
-> projection materialization
-> canonical relations
-> reasoning_paths
-> hypothesis claims
```

### Lifecycle Stages

1. Evidence ingestion
   Evidence enters through ingestion pipelines, extraction flows, or manual
   curation.
2. Claim creation
   Evidence is interpreted into `relation_claims` with structured participants
   and evidence rows.
3. Claim triage
   Claims become eligible for projection only when they meet curation and
   persistability requirements.
4. Projection materialization
   Support claims create or update canonical `relations` and
   `relation_projection_sources`.
5. Canonical graph reads
   The graph exposes claim-backed edges for browsing, search, and traversal.
6. Reasoning path generation
   Derived mechanism chains are rebuilt from grounded claim structures.
7. Hypothesis generation
   Reviewable hypothesis claims are created in claim space without auto-promoting
   to canonical truth.

### Lifecycle Guarantees

```text
no canonical relation without support claims
every canonical relation has projection lineage
reasoning artifacts are rebuildable
hypotheses do not automatically become canonical relations
```

## Exit Criteria

Phase 2 should be considered complete only when all of the following are true:

1. graph-core runs without biomedical modules in its dependency chain
2. neutral graph naming replaces MED13-specific runtime naming
3. domain-specific defaults are removed from graph-core
4. biomedical behavior loads through explicit extension points
5. the MED13 application uses the biomedical pack without core changes
6. read-model strategy is implemented or clearly deferred with no ambiguity
7. auth, tenancy, and RLS behavior are documented as part of the product
   boundary
8. API versioning, deprecation, and generated-client policy are documented
9. at least one non-biomedical domain pack proves the architecture without core
   forks

## Summary

Phase 2 is not a rewrite of the graph model. It is a boundary-hardening and
productization step.

The system should be understood as a scientific reasoning platform, not merely a
generic graph product. Its distinguishing feature is the claim-ledger model and
the explainable path from evidence to projections to reasoning artifacts.

The service should evolve from:

```text
standalone MED13-first graph service
```

to:

```text
graph platform
+ domain packs
+ application-specific products
```

without changing the core scientific model:

```text
evidence
-> claims
-> projections
-> canonical graph
-> reasoning artifacts
```

If phase 2 succeeds, the system keeps its explainable claim-first architecture
while gaining:

- cleaner product boundaries
- portable auth and tenancy semantics
- clearer release and compatibility rules
- faster query paths
- credible domain neutrality

The added query-index layer should allow the architecture to scale to very large
claim volumes without giving up traceability or rebuildability.
