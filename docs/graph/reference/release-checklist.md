# Graph Service Release Checklist

Use this checklist before promoting a new standalone graph service build.

- Confirm the service version in `services/artana_evidence_db/product_contract.py`
  matches `/health` and the OpenAPI `info.version`.
- Regenerate and review `services/artana_evidence_db/openapi.json`.
- Regenerate and review the generated TypeScript client artifact at
  `services/artana_evidence_db/artana-evidence-db.generated.ts`.
- Review Alembic migrations for forward-only behavior and tenant-safe data
  access.
- Run `make graph-service-checks`.
- Confirm no downstream service imports or packages graph implementation modules
  instead of using the HTTP contract artifacts.
- Record any breaking or deprecated behavior in this reference directory before
  deployment.
