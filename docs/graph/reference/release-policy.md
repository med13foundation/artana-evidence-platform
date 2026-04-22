# Graph Service Release Policy

## Versioning Policy

The standalone graph service has two version surfaces:

- Runtime/product version: `0.1.0`
- HTTP contract prefix: `/v1`

Rules:

- The runtime version is semantic version metadata for the standalone product.
- The HTTP contract prefix is the compatibility boundary for callers.
- Additive, backward-compatible changes may ship inside `/v1`.
- Breaking HTTP contract changes must not silently land inside `/v1`.
- Any intentional breaking contract change requires explicit release intent,
  updated migration notes, regenerated artifacts, and an upgrade guide update.

## Deprecation Policy

Deprecation is explicit.

Rules:

- New endpoints or fields may be added without deprecating existing ones.
- Deprecated endpoints or fields must be called out in release notes before
  removal.
- Removals from `/v1` require explicit migration notes and upgrade guidance.
- Internal refactors that do not change the OpenAPI contract do not count as
  product deprecations.

## Generated Client Ownership

The release contract is owned by this repository.

Authoritative artifacts:

- OpenAPI release contract: [openapi.json](/Users/alvaro1/Documents/med13/foundation/resource_library/services/artana_evidence_db/openapi.json)
- Generated TypeScript client contract:
  [artana-evidence-db.generated.ts](/Users/alvaro1/Documents/med13/foundation/resource_library/services/artana_evidence_db/artana-evidence-db.generated.ts)

Generation sources:

- OpenAPI export: `scripts/export_graph_openapi.py`
- TypeScript generation: `scripts/generate_ts_types.py --module src.type_definitions.graph_service_contracts`

Ownership rules:

- OpenAPI is the primary release contract.
- Generated client artifacts are versioned release artifacts, not disposable local files.
- Release candidates must update both artifacts together via `make graph-service-sync-contracts`.
- Release validation must fail if either artifact is stale via `make graph-service-contract-check`.

## Generated Client Release Process

Before a release:

1. Regenerate artifacts with `make graph-service-sync-contracts`.
2. Validate freshness with `make graph-service-contract-check`.
3. Run the broader service gate with `make graph-service-checks`.
4. Record any breaking change intent and migration notes in the release summary.

## Compatibility Expectations

Compatibility rules for runtime and generated clients:

- Runtime and generated clients are expected to come from the same release line.
- The generated TypeScript contract is only guaranteed to match the OpenAPI artifact committed with the same runtime release.
- If `/v1` changes in a breaking way, callers must be given explicit migration notes before rollout.
- Operator upgrades must treat schema migrations, runtime rollout, and regenerated client artifacts as one coordinated release boundary.
