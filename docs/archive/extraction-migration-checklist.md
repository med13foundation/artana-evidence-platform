# Migration Checklist

Status date: April 23, 2026.

Archived status date: April 30, 2026.

Legend:

- `[x]` complete
- `[-]` intentionally deferred

## Extraction Status

- [x] Extract `services/artana_evidence_db`.
- [x] Extract `services/artana_evidence_api`.
- [x] Add root Makefile targets for both services.
- [x] Add local Postgres setup and migration targets.
- [x] Generate graph service OpenAPI.
- [x] Generate Evidence API OpenAPI.
- [x] Generate graph TypeScript contract artifact.
- [x] Add graph service boundary validator.
- [x] Add Evidence API boundary validator.
- [x] Add graph service check target.
- [x] Add Evidence API service check target.
- [x] Add deploy workflows for both services.
- [x] Remove top-level temporary `src` package.
- [x] Remove `packages/artana_api` from this checkout.
- [x] Update packaging/type/check paths so service gates no longer depend on
  removed monorepo paths.
- [x] Add local identity gateway boundary for users, API keys, spaces, and
  membership checks.

## Current Required Gates

Run these before merging service changes:

```bash
make graph-service-checks
make artana-evidence-api-service-checks
```

Focused contract/boundary gates:

```bash
make graph-service-contract-check
make artana-evidence-api-contract-check
make graph-service-boundary-check
make artana-evidence-api-boundary-check
make graph-phase6-release-check
```

## Deferred Outside This Migration

- [-] Build or restore a frontend in this repo.
- [-] Restore a Python SDK in this repo.
- [-] Extract identity into a separate deployed service.
- [-] Split the largest runtime modules.

Those are product or architecture hardening decisions, not blockers for the
completed extraction.
