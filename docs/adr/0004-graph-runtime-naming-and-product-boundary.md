# ADR-0004: Graph Runtime Naming And Product Boundary

**Status**: Accepted
**Date**: 2026-03-13
**Deciders**: MED13 Development Team

## Context

The standalone graph service began as a MED13-shaped extraction of platform
behavior. That left runtime naming, feature flags, and some release-boundary
language tied too closely to the first domain.

At the same time, the graph service now behaves like a product boundary:

- it has a standalone FastAPI service
- it has a generated OpenAPI contract
- it has a generated TypeScript client artifact
- it has explicit release and upgrade policy

We need a stable naming rule that keeps the graph runtime neutral even while
the first production pack remains biomedical.

## Decision

We will treat the standalone graph service as a product boundary with neutral
graph naming.

Rules:

- runtime env vars use `GRAPH_*` names as the primary contract
- product metadata is owned by `src/graph/product_contract.py`
- `/v1` is the HTTP compatibility boundary
- generated OpenAPI and generated TypeScript client artifacts are versioned
  release artifacts
- domain identity is supplied by the active pack, not by hardcoded MED13 naming

This means pack-specific identity such as service name and JWT issuer is
pack-owned runtime metadata, while runtime wiring, release policy, and contract
generation remain graph-owned.

## Consequences

### Positive

- Graph runtime naming is explicit and reusable across domains
- Product-boundary behavior is documented and testable
- Release artifacts have one clear owner
- New packs can change domain identity without forking runtime policy

### Negative

- Legacy MED13-prefixed aliases still need cleanup work until Phase 1 is fully
  closed
- Product boundary maintenance now requires keeping runtime, OpenAPI, client,
  and docs aligned

## Implementation

- Shared runtime/product metadata in
  `src/graph/product_contract.py`
- Shared startup settings in
  `src/graph/core/service_config.py`
- Release-boundary validator in
  `scripts/validate_graph_phase6_release_contract.py`
- Release policy docs in:
  - `docs/graph/reference/release-policy.md`
  - `docs/graph/reference/release-checklist.md`
  - `docs/graph/reference/upgrade-guide.md`
- Release-quality gate:
  `make graph-phase6-release-check`

## References

- `docs/graph/reference/release-policy.md`
- `docs/graph/reference/upgrade-guide.md`
- `docs/graph/history/migration-phase2.md`
