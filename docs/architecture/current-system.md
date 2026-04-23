# Current System

Status date: April 23, 2026.

This repo is the extracted backend for the Artana evidence platform. It contains
two service packages plus service-focused scripts, tests, migrations, docs, and
generated API artifacts.

## What Is In This Checkout

```text
services/
  artana_evidence_api/   Evidence API and workflow runtime
  artana_evidence_db/    Graph service and graph-owned persistence/API
scripts/                 contract export, boundary checks, deploy helpers
tests/                   e2e tests for extracted service behavior
docs/                    current repo docs
```

There is no top-level `src/` package, no frontend app, and no
`packages/artana_api` SDK in this checkout.

## Service Responsibilities

| Service | Owns | Does Not Own |
| --- | --- | --- |
| Evidence API | local identity gateway, API keys, spaces, documents, proposal/review flow, research-init, chat, AI runs, workflow artifacts | graph schema ownership, dictionary ownership, canonical graph persistence |
| Graph service | graph schema, dictionary, claims, relations, observations, provenance, graph views, domain packs, graph workflows, admin space sync | end-user API keys, document upload UX, research-init orchestration |

The Evidence API talks to the graph service through HTTP/client contracts. It
should not package or import graph implementation internals for normal runtime
behavior.

## Local Runtime

The default local loop is:

```bash
make install-dev
make run-all
```

`make run-all` starts:

- local Postgres;
- graph service on `http://127.0.0.1:8090`;
- Evidence API on `http://127.0.0.1:8091`.

The local Makefile uses one `DATABASE_URL` by default, but each service has its
own Alembic tree and service-owned schema expectations.

## Public Contracts

Generated artifacts are part of the repo contract:

- `services/artana_evidence_api/openapi.json`
- `services/artana_evidence_db/openapi.json`
- `services/artana_evidence_db/artana-evidence-db.generated.ts`

Regenerate or check them with:

```bash
make artana-evidence-api-contract-check
make graph-service-contract-check
```

## Main Evidence Workflow

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

## Quality Gates

Use these before merging service changes:

```bash
make graph-service-checks
make artana-evidence-api-service-checks
```

Focused boundary checks:

```bash
make graph-service-boundary-check
make artana-evidence-api-boundary-check
```
