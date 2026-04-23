# Compatibility Matrix

Status date: April 23, 2026.

| Surface | Current Compatibility Rule |
| --- | --- |
| Evidence API OpenAPI | Must match `services/artana_evidence_api/openapi.json`; check with `make artana-evidence-api-contract-check`. |
| Graph OpenAPI | Must match `services/artana_evidence_db/openapi.json`; check with `make graph-service-contract-check`. |
| Graph TypeScript artifact | Must match `services/artana_evidence_db/artana-evidence-db.generated.ts`; checked by `make graph-service-contract-check`. |
| Artana kernel dependency | Pinned in `pyproject.toml` and Evidence API requirements. Runtime code should fail clearly if unavailable. |
| Artana state store | Uses `ARTANA_STATE_URI` or database-derived Postgres URI with `artana,public` search path. |
| Runtime skills | Filesystem `SKILL.md` files are validated at app startup. |
| Identity | Local `IdentityGateway` contract is stable for Evidence API routes; remote extraction is future work. |
