# Pending Boundary Issues

This note tracks architecture issues that are real but larger than a narrow
release-gate patch.

## Evidence API Data Ownership

Status: partially addressed.

The evidence API is operationally separated from the graph service, but it still
uses service-local ORM mappings for identity and tenancy tables that were
originally shared platform tables:

- `services/artana_evidence_api/models/user.py`
- `services/artana_evidence_api/models/research_space.py`
- `services/artana_evidence_api/models/discovery.py`

Two immediate cleanups have landed:

- PostgreSQL startup no longer creates auth tables opportunistically;
  production-like schemas should be managed by Alembic migrations, not app
  startup DDL.
- Identity and tenancy operations now go through the local identity gateway
  documented in [local-identity-boundary.md](./local-identity-boundary.md).

Target state:

- Keep the Evidence API on `IdentityGateway`, not direct identity-table writes.
- Rename the schema helpers and comments away from "shared platform" if these
  tables remain owned by the Evidence API during testing.
- When growth requires it, replace `LocalIdentityGateway` with a remote
  identity/tenancy adapter and keep Evidence API workflow code unchanged.

Until remote extraction or final local ownership is decided, this is a clean
local boundary but not yet a fully autonomous identity service.

## Runtime To Router Imports

Status: partially addressed.

The full AI orchestrator no longer imports the private
`research_init_runtime._build_source_results` helper. Source-result construction
now lives below both runtimes in
`services/artana_evidence_api/research_init_source_results.py`.

Remaining runtime-to-router imports still exist in
`services/artana_evidence_api/research_init_runtime.py`. The largest ones are
PubMed candidate selection helpers and PDF enrichment helpers currently owned by
router modules.

Target state:

- Move PubMed query building, candidate models, relevance selection, and scope
  refinement helpers into a service module below both router and worker code.
- Move PDF enrichment workflow helpers below `routers/documents.py` so the
  worker can enrich PDFs without importing router internals.
- Add a boundary validator rule that fails production runtime imports from
  `artana_evidence_api.routers.*` after those moves are complete.

## Large Runtime Modules

Status: open.

The biggest orchestration modules remain large:

- `services/artana_evidence_api/research_init_runtime.py`
- `services/artana_evidence_api/full_ai_orchestrator_runtime.py`
- `services/artana_evidence_db/graph_workflow_service.py`

Target state:

- Split research-init into source discovery, replay, document preparation,
  extraction staging, and state finalization modules.
- Split full AI orchestration into planner, action executor, guarded policy, and
  artifact writer modules.
- Split graph workflow service by command family once the current checks are
  stable.
