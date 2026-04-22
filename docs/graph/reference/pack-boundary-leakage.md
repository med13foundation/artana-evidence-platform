# Pack-Boundary Leakage Findings

Recorded on `2026-03-13`.

This note tracks the current pack-boundary leakage posture after the Phase 7
cross-domain proof work.

## Closed Leakage Areas

- Graph-core no longer imports biomedical modules directly.
- Generic runtime/application code no longer reaches into pack modules from
  deep helper layers; pack resolution is concentrated at explicit runtime
  boundaries.
- View defaults, connector defaults, search behavior, dictionary-loading
  defaults, bootstrap behavior, and relation-suggestion policy are pack-owned.
- The cross-domain gate proves the same shared service boundary works for both
  `biomedical` and `sports` for:
  - dictionary seeding
  - connector default dispatch
  - auth and tenancy checks
  - one-hop neighborhood read-model usage
  - release-contract validation

## Intentional Runtime Coupling

These are explicit runtime-selection boundaries, not leakage:

- `src/graph/pack_registry.py`
  owns built-in pack registration and active-pack resolution
- `src/graph/runtime.py`
  exposes the active pack to runtime/composition code
- `services/artana_evidence_db/app.py`
  bootstraps built-in packs at startup

## Residual Proof Gaps

These are not known boundary violations, but they are still incomplete proof
areas:

- no third pack exists yet
- cross-pack query-index proof currently covers `entity_neighbors`, not every
  read-model surface
- cross-pack auth proof covers the core admin/membership path, not every route
  family

## Current Finding Summary

No active graph-core to domain-pack reverse-import leakage is known after the
current validation gates.

Current residual risk is proof coverage breadth rather than structural boundary
breakage:

- more route families could be exercised under non-biomedical packs
- more read-model surfaces could be exercised under non-biomedical packs
- a second alternate pack would raise confidence that the extension model is
  generic rather than only “biomedical plus one”

## Expected Follow-Up

When a new leakage risk is found, record:

1. the violating file or boundary
2. whether it is graph-core, runtime composition, or service-local leakage
3. whether the fix belongs in graph-core, pack config, or validation tooling
4. the gate that should prevent regression next time
