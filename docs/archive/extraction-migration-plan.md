# Migration Plan

Status date: April 23, 2026.

Archived status date: April 30, 2026.

The extraction migration is complete for this checkout. This file is now a
historical status record, not an open migration roadmap.

## Completed Target

The repo now owns:

- `services/artana_evidence_api`
- `services/artana_evidence_db`
- service-focused `scripts/`
- service-focused `tests/`
- service-focused `docs/`
- generated API contract artifacts
- local Postgres and Makefile tooling

The repo no longer contains:

- the temporary top-level `src` package;
- `packages/artana_api`;
- old monorepo frontend/runtime services.

## Current Boundary Goal

The intended steady-state boundary is:

```text
Evidence API
  -> HTTP/generated contract boundary
  -> Graph service
```

The Evidence API should not package graph service internals as its normal
runtime dependency. Identity is local for now, but routed through
`IdentityGateway` so it can move later if needed.

## Migration Milestones

| Milestone | Status |
| --- | --- |
| M0 repo scaffold | Complete |
| M1 bootable baseline import | Complete |
| M2 graph service standalone pass | Complete |
| M3 Evidence API shared-runtime unwind | Complete for removed `src` dependency |
| M4 CI, deploy, docs, and contract alignment | Complete for current services |
| M5 source-of-truth cutover | Complete |
| M6 remove temporary `src` package | Complete |
| M7 restore optional service-local runtimes | Complete |
| M8 local identity boundary | Complete as v1 |

## What Remains

Remaining work is not migration import work. It is architecture hardening:

- finish runtime-to-router helper cleanup;
- reduce large runtime modules;
- decide future identity ownership after internal testing;
- keep service contract and boundary checks green.

See [Remaining Work](../remaining_work_priorities.md).
