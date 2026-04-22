# ADR-0005: Graph-Core And Domain-Pack Packaging

**Status**: Accepted
**Date**: 2026-03-13
**Deciders**: MED13 Development Team

## Context

The graph platform needed a packaging model that separates reusable graph
behavior from domain-specific defaults, prompts, heuristics, and vocabulary.

Before the packaging split, biomedical assumptions were mixed into shared
runtime, service composition, and adapter code. That made it hard to prove the
graph runtime was domain-neutral.

We now have at least two built-in packs, so packaging must reflect the actual
runtime architecture rather than the original MED13 extraction shape.

## Decision

We will package the graph platform as:

- `src/graph/core`
  for domain-neutral graph contracts and shared runtime foundations
- `src/graph/domain_<name>`
  for pack-owned defaults, prompts, heuristics, and domain identity
- `src/graph/pack_registry.py`
  for built-in pack registration and active-pack resolution
- `src/graph/runtime.py`
  for explicit runtime access to the active pack

`GraphDomainPack` is the unit of registration and the only approved pack-owned
surface consumed by generic runtime/composition code.

Graph-core must not import domain-pack modules directly.

## Consequences

### Positive

- Domain-specific behavior has one explicit ownership boundary
- New packs can be added without graph-core forks
- Runtime consumers can depend on pack contracts instead of direct pack imports
- Boundary validation becomes automatable

### Negative

- Pack config growth must be managed carefully so `GraphDomainPack` does not
  become a dumping ground for unrelated runtime concerns
- Built-in pack registration remains static and in-process for now

## Implementation

- Graph-core contracts in `src/graph/core/`
- Built-in packs in:
  - `src/graph/domain_biomedical/`
  - `src/graph/domain_sports/`
- Registry/bootstrap flow in:
  - `src/graph/core/pack_registration.py`
  - `src/graph/pack_registry.py`
  - `services/artana_evidence_db/app.py`
- Boundary validation:
  `scripts/validate_graph_phase2_boundary.py`
- Cross-domain proof gate:
  `make graph-phase7-cross-domain-check`

## References

- `docs/graph/reference/domain-pack-lifecycle.md`
- `docs/graph/reference/cross-domain-validation-matrix.md`
- `docs/graph/reference/pack-boundary-leakage.md`
