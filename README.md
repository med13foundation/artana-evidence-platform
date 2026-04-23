# Artana Evidence Platform

Status date: April 23, 2026.

`artana-evidence-platform` is the extracted backend repo for the Artana
evidence services.

This checkout currently contains:

- `services/artana_evidence_api`: Evidence API, local identity gateway,
  documents, proposals, review queue, research-init, chat, and AI workflow
  runtimes.
- `services/artana_evidence_db`: governed graph service, dictionary, claims,
  relations, observations, provenance, graph views, workflows, and graph admin
  sync.

This checkout does not contain:

- a frontend app;
- the old top-level `src` runtime package;
- `packages/artana_api`;
- unrelated monorepo services.

## Start Locally

```bash
make install-dev
make run-all
```

`make run-all` starts local Postgres, the graph service on
`http://127.0.0.1:8090`, and the Evidence API on `http://127.0.0.1:8091`.

## Docs

- [Docs Index](docs/README.md)
- [Current System](docs/architecture/current-system.md)
- [User Guide](docs/user-guide/README.md)
- [Project Status](docs/project_status.md)
- [Engineering Plan](docs/plan.md)
- [Remaining Work](docs/remaining_work_priorities.md)

## Main Workflow

```text
Create or get a space
  -> add or discover evidence
  -> extract reviewable proposals
  -> review or reject proposals
  -> promote trusted items into the graph
  -> explore, ask, and repeat
```

The review queue is the trust gate. AI workflows can search, extract, and stage
work, but promoted graph state should flow through review/governance.

## Service Gates

Run these before merging backend changes:

```bash
make graph-service-checks
make artana-evidence-api-service-checks
```

Useful focused checks:

```bash
make graph-service-contract-check
make artana-evidence-api-contract-check
make graph-service-boundary-check
make artana-evidence-api-boundary-check
make graph-phase6-release-check
```

## Generated Contracts

- `services/artana_evidence_api/openapi.json`
- `services/artana_evidence_db/openapi.json`
- `services/artana_evidence_db/artana-evidence-db.generated.ts`

Regenerate graph artifacts with:

```bash
make graph-service-sync-contracts
```

Regenerate Evidence API OpenAPI with:

```bash
make artana-evidence-api-openapi
```
