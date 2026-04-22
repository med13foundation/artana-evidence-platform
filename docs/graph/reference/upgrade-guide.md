# Graph Service Upgrade Guide

This guide covers operator-side upgrades for the standalone graph service.

## 1. Review The Release Boundary

- Read the intended contract and compatibility rules in
  [release-policy.md](/Users/alvaro1/Documents/med13/foundation/resource_library/docs/graph/reference/release-policy.md).
- Review whether the release is additive or breaking for `/v1`.
- If the release includes breaking intent, read the migration notes before rollout.

## 2. Refresh And Verify Artifacts

- Regenerate release artifacts with `make graph-service-sync-contracts`.
- Verify contract freshness with `make graph-service-contract-check`.
- Confirm the generated OpenAPI and TypeScript artifacts are committed with the runtime change.

## 3. Validate The Candidate

- Run `make graph-service-checks`.
- Run `make graph-phase6-release-check`.
- If the release touches graph query or reasoning indexes, run the relevant benchmark or rebuild checks as part of rollout prep.

## 4. Apply Database Changes

- Ensure Postgres connectivity is ready for the graph service.
- Apply graph migrations with the graph-service Alembic flow. The release path
  assumes `alembic`-managed schema upgrades, for example:

```bash
python -m services.artana_evidence_db.manage upgrade head
```

- If the release introduces new derived tables or indexes, rebuild them as required by the release notes.

## 5. Roll Out Runtime

- Deploy the graph-service runtime with the intended image and runtime config.
- Verify the graph-service URL, JWT secret, and database settings are correct for the target environment.

## 6. Smoke Test Post-Upgrade

- Check `/health` and confirm the expected runtime version.
- Run a minimal graph-service contract smoke check against the deployed service.
- Confirm the admin and graph-space routes required by the release are operational.

## 7. Communicate Breaking Changes

- If `/v1` changed incompatibly, distribute the explicit migration notes.
- Ensure dependent callers update against the generated TypeScript client from the same release line.
