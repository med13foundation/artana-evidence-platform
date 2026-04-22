# Graph Docs

This folder explains the standalone graph service from different points of view.
The same service is used by different layers of users:

- curious readers who want to understand what the graph service is
- admins and operators who need to run or troubleshoot it
- developers who need to build against it or change it
- maintainers who need exact contract and architecture references

In simple terms, this service is the backend that stores and serves
claim-backed graph knowledge: entities, claims, canonical relations, evidence,
reasoning paths, graph search, read models, and graph-specific operational
workflows.

Current status:

- the graph service is implemented as `graph-core` plus domain packs
- the built-in packs are `biomedical` and `sports`
- `biomedical` remains the primary production pack
- `sports` is the first non-biomedical proof pack used to validate the shared
  pack model

## Choose Your Path

### I want the simple explanation

Read [overview/what-this-service-does.md](overview/what-this-service-does.md).

### I administer or operate the service

Read [admins/admin-guide.md](admins/admin-guide.md).

### I build against the service or change its code

Read [developers/developer-guide.md](developers/developer-guide.md).

### I need exact technical reference

Read [reference/README.md](reference/README.md).

### I need migration history and extraction context

Read [history/README.md](history/README.md).

## What The Service Owns

- the graph HTTP API under `/health` and `/v1/...`
- graph-space-scoped entities, observations, provenance, claims, claim
  relations, canonical relations, graph views, graph documents, reasoning
  paths, search, connection discovery, hypotheses, concepts, and graph-specific
  admin/control-plane operations
- graph-service-local authentication and authorization checks
- graph-space registry and graph-space membership state used by the standalone
  graph runtime
- graph-specific maintenance workflows such as projection readiness audits,
  repairs, participant backfill, reasoning-path rebuilds, and operation-run
  history
- graph-specific deployment and runtime configuration

The platform app no longer owns graph routes. Platform callers use this service
over HTTP.

The service is no longer just a MED13-specific extraction boundary. It now has:

- neutral runtime naming
- explicit pack registration and selection
- graph-core auth and tenancy abstractions
- physical read models and rebuild flows
- release/versioning policy and generated-client ownership
- cross-domain proof across the built-in packs

## Folder Layout

- [overview/](overview/)
  Plain-language docs for understanding what the service does and why it exists.
- [admins/](admins/)
  Admin/operator guides and task-oriented operational documentation.
- [developers/](developers/)
  Developer onboarding, runtime model, contracts, and local workflow guidance.
- [reference/](reference/)
  Exact reference docs: architecture, endpoints, deployment topology, domain
  packs, read models, release policy, examples, use cases, and inventory.
- [history/](history/)
  Historical extraction and migration planning documents.

## Source Of Truth

- `services/artana_evidence_db/openapi.json`
  Generated request/response contract for the running service.
- [reference/endpoints.md](reference/endpoints.md)
  Human-readable route inventory with access expectations.
- `services/artana_evidence_db/routers/`
  Route implementation source.
- [reference/service-inventory.md](reference/service-inventory.md)
  Current runtime/module/caller/tooling inventory.
- `services/artana_evidence_db/artana-evidence-db.generated.ts`
  Generated TypeScript contract for web/admin clients.

If a prose document drifts from the generated contract, treat
`services/artana_evidence_db/openapi.json` as authoritative and update the prose docs.
