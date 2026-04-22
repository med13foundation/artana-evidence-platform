# Graph Reference Docs

This folder contains the exact technical reference material for the standalone
graph service.

Use these files when you need precision rather than onboarding.

## Files

- [architecture.md](architecture.md)
  The graph model, authoritative stores, projection rules, read architecture,
  invariants, and compatibility notes.
- [endpoints.md](endpoints.md)
  The complete current HTTP route inventory with access expectations.
- [domain-pack-lifecycle.md](domain-pack-lifecycle.md)
  How built-in packs are registered, selected, and consumed by runtime code.
- [deployment-topology.md](deployment-topology.md)
  Runtime and deployment topology, required environment contract, promotion
  validation, and dedicated-database migration guidance.
- [read-model-ownership.md](read-model-ownership.md)
  Ownership and truth-boundary rules for graph read models.
- [read-model-benchmarks.md](read-model-benchmarks.md)
  Recorded benchmark results for the generic and reasoning read-model layers.
- [release-policy.md](release-policy.md)
  API versioning, generated-client ownership, and breaking-change policy.
- [release-checklist.md](release-checklist.md)
  Operator and maintainer release steps for the graph service.
- [upgrade-guide.md](upgrade-guide.md)
  Upgrade expectations for callers and operators.
- [cross-domain-validation-matrix.md](cross-domain-validation-matrix.md)
  Recorded proof that shared graph-core behavior works across built-in packs.
- [cross-domain-examples.md](cross-domain-examples.md)
  Side-by-side examples of the same graph-core contracts across domains.
- [pack-boundary-leakage.md](pack-boundary-leakage.md)
  Current status of pack-boundary closure and residual proof gaps.
- [use-cases.md](use-cases.md)
  Primary user and system workflows over the graph.
- [examples.md](examples.md)
  Concrete examples of claims, projections, graph documents, reasoning paths,
  and hypotheses.
- [service-inventory.md](service-inventory.md)
  The active runtime/module/caller/tooling inventory for the standalone graph
  service.

## Recommended Reading Order

1. [endpoints.md](endpoints.md)
2. [architecture.md](architecture.md)
3. [domain-pack-lifecycle.md](domain-pack-lifecycle.md)
4. [read-model-ownership.md](read-model-ownership.md)
5. [release-policy.md](release-policy.md)
6. [use-cases.md](use-cases.md)
7. [examples.md](examples.md)
8. [deployment-topology.md](deployment-topology.md)
9. [service-inventory.md](service-inventory.md)
