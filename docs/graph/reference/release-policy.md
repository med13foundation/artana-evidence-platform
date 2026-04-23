# Graph Service Release Policy

This policy defines the standalone graph service release boundary for
`services/artana_evidence_db`. The graph service is consumed over HTTP and by
generated contract artifacts, not by importing its Python internals from other
services.

## Versioning Policy

The graph service version is owned by
`services/artana_evidence_db/product_contract.py`. Runtime metadata, `/health`,
and the generated OpenAPI artifact must report the same version before a release
can proceed.

The public HTTP API is versioned by the `/v1` prefix. Breaking API changes must
land behind a new major API prefix or be delayed until a coordinated migration
window.

## Deprecation Policy

Deprecated endpoints, fields, or enum values must remain documented until their
removal release. A deprecation note should name the replacement path, the first
release where the old surface is deprecated, and the earliest release where it
may be removed.

## Generated Client Ownership

The graph service owns its OpenAPI artifact and generated TypeScript client:

- `services/artana_evidence_db/openapi.json`
- `services/artana_evidence_db/artana-evidence-db.generated.ts`

Regenerate these artifacts with the service contract tooling whenever the public
API changes. Downstream services may consume these generated artifacts, but they
must not package the graph service implementation as their runtime dependency.

## Compatibility Expectations

Every release must preserve the HTTP-only service boundary:

- All public graph paths stay under `/v1`, except `/health` and OpenAPI docs.
- Generated artifacts match the runtime product contract.
- Alembic migrations are forward-only and reviewed before deployment.
- `make graph-service-checks` passes before the release is promoted.
