# Engineering Plan

Status date: April 23, 2026.

This plan describes the target direction for the current extracted backend
repo. It intentionally excludes the old monorepo UI, old top-level `src`
runtime package, and deleted SDK package.

## Product Shape

The platform is an evidence-first research backend:

```text
space
  -> evidence
  -> extraction
  -> review
  -> graph
  -> search/chat/discovery
```

The graph is the trusted state. AI workflows may discover and propose, but
review/governance decides what becomes trusted graph knowledge.

## Architecture Principles

- Keep the repo as two backend services: Evidence API and graph service.
- Keep graph internals behind the graph service HTTP/API contract.
- Keep identity low-friction during testing, but route it through
  `IdentityGateway`.
- Treat OpenAPI and generated graph TypeScript contracts as release artifacts.
- Prefer service-local modules over resurrecting the removed top-level `src`
  package.
- Keep direct graph writes for advanced/system workflows; normal researcher
  flows should pass through proposals and review.

## Current Target Topology

```text
client
  -> services/artana_evidence_api
       identity gateway
       documents and extraction
       proposals and review queue
       AI/workflow runtimes
       graph HTTP client
  -> services/artana_evidence_db
       dictionary
       claims and relations
       provenance and observations
       graph views and workflows
```

## Near-Term Plan

1. Keep the two service gates green:
   - `make artana-evidence-api-service-checks`
   - `make graph-service-checks`
2. Test the local identity gateway with internal testers.
3. Finish runtime layering cleanup listed in
   [Pending Boundary Issues](./architecture/pending-boundary-issues.md).
4. Split the largest orchestration modules once behavior is stable.
5. Keep generated OpenAPI and graph TypeScript artifacts synchronized with
   service code.

## Medium-Term Plan

1. Decide whether identity remains local or moves behind a remote
   `IdentityGateway` implementation.
2. Add a frontend or public SDK only when the backend flows are stable enough
   to support external testers.
3. Strengthen deployment smoke checks for both services.
4. Add more boundary rules after helper modules are moved below routers.

## Deferred Work

These are not part of the current backend extraction:

- rebuilding the deleted frontend in this repo;
- restoring `packages/artana_api`;
- restoring the old monorepo `src` package;
- turning identity into a standalone service before tester needs justify it.
