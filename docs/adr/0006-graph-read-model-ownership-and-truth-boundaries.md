# ADR-0006: Graph Read-Model Ownership And Truth Boundaries

**Status**: Accepted
**Date**: 2026-03-13
**Deciders**: MED13 Development Team

## Context

The graph platform needs read models for query performance, but the graph data
model is claim-first and explainability-driven.

That creates a risk: if read models are treated as truth-bearing stores, the
system can drift away from its core invariants:

- claims are authoritative
- canonical relations are projections
- reasoning artifacts are derived outputs

We need an explicit ownership rule for read models that preserves those truth
boundaries while still allowing query acceleration.

## Decision

We will treat graph read models as graph-core-owned derived query surfaces.

Rules:

- read models are never truth sources
- read models must be rebuildable from authoritative stores
- generic read-model framework and core model names belong to graph-core
- domain packs may influence the graph through pack-owned defaults and
  vocabulary, but they do not own core read-model framework invariants
- projection lineage and claim ledger remain authoritative for explainability

The initial graph-core read-model catalog is:

- `entity_neighbors`
- `entity_relation_summary`
- `entity_claim_summary`
- `entity_mechanism_paths`

## Consequences

### Positive

- Query acceleration does not weaken claim-first correctness
- Read-model rebuild and invalidation rules stay centralized
- Cross-pack query behavior can be validated against one shared framework
- Projection and reasoning invariants remain protected from pack overrides

### Negative

- Every new read model now needs explicit ownership and rebuild semantics
- Pack-specific read-model expansion must be justified carefully to avoid
  leaking domain assumptions into graph-core

## Implementation

- Graph-core read-model contract in
  `src/graph/core/read_model.py`
- Physical read-model tables in
  `src/models/database/kernel/read_models.py`
- Ownership validation in
  `scripts/validate_graph_phase4_read_models.py`
- Cross-pack proof for the shared one-hop neighborhood path in
  `make graph-phase7-cross-domain-check`

## References

- `docs/graph/reference/read-model-ownership.md`
- `docs/graph/reference/read-model-benchmarks.md`
- `docs/graph/reference/cross-domain-validation-matrix.md`
