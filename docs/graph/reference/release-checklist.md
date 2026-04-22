# Graph Service Release Checklist

Use this checklist for any standalone graph-service release candidate.

## Contract

- Confirm the product version and `/v1` contract intent in
  [release-policy.md](/Users/alvaro1/Documents/med13/foundation/resource_library/docs/graph/reference/release-policy.md).
- Run `make graph-service-sync-contracts`.
- Run `make graph-service-contract-check`.
- Verify the committed OpenAPI artifact changed only when intended:
  [openapi.json](/Users/alvaro1/Documents/med13/foundation/resource_library/services/artana_evidence_db/openapi.json)
- Verify the generated TypeScript client changed only when intended:
  [artana-evidence-db.generated.ts](/Users/alvaro1/Documents/med13/foundation/resource_library/services/artana_evidence_db/artana-evidence-db.generated.ts)

## Runtime

- Run `make graph-service-checks`.
- Run `make graph-phase6-release-check`.
- Confirm health returns the expected runtime version from `/health`.

## Release Notes

- Record additive versus breaking contract changes.
- If any `/v1` behavior changed incompatibly, include explicit migration notes.
- Link the operator steps in
  [upgrade-guide.md](/Users/alvaro1/Documents/med13/foundation/resource_library/docs/graph/reference/upgrade-guide.md).

## Deployment

- Apply graph-service migrations before or with runtime rollout.
- Roll out the graph-service runtime and verify `GRAPH_DATABASE_URL` and related runtime config.
- Re-run the post-deploy health and contract smoke checks.
