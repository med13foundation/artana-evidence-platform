# Artana Evidence Platform - AGENTS.md

Guidance for coding agents working in this independent backend repo.

## Project Shape

This repository contains two Python backend services:

- `services/artana_evidence_api`: the evidence workflow API. It owns research spaces, document ingestion, PubMed/MARRVEL discovery, review queues, proposals, graph chat/search orchestration, guarded AI runs, and user-facing workflow state.
- `services/artana_evidence_db`: the graph/evidence service. It owns graph entities, relations, observations, provenance, relation evidence, dictionary governance, validation, and graph service API contracts.

The services are intentionally separated. Keep orchestration and user workflow concerns in `services/artana_evidence_api`; keep graph persistence, dictionary governance, and graph validation concerns in `services/artana_evidence_db`.

There is no active frontend package in this repository. Do not add UI work here unless explicitly asked; this repo is for backend services, contracts, scripts, tests, docs, and migrations.

## Working Rules

- Keep changes scoped to the requested service and files.
- Do not revert edits made by other people in the working tree.
- Prefer existing service patterns over new abstractions.
- Use forward-only implementation for new repository work unless compatibility is explicitly requested.
- Write relevant tests after code changes. First check whether tests already exist and whether they are current and robust, then add focused unit, regression, integration, or service tests as appropriate.
- Avoid `Any` in new Python code. Use concrete types, protocols, dataclasses, Pydantic models, or service-local typed contracts.
- Never commit PHI, secrets, API keys, or real patient data.
- Keep generated OpenAPI/type artifacts current when changing service contracts.

## Service Boundaries

### Evidence API

Use `services/artana_evidence_api` for:

- FastAPI application and routers
- research spaces and authentication
- evidence/document ingestion workflows
- review queue, approvals, proposals, schedules, artifacts, and run registries
- agent runtime orchestration and guarded/full AI modes
- graph client integration against the graph service
- service-local Alembic migrations and tests

Common checks:

```bash
make artana-evidence-api-lint
make artana-evidence-api-type-check
make artana-evidence-api-boundary-check
make artana-evidence-api-contract-check
make artana-evidence-api-test
make artana-evidence-api-service-checks
```

### Graph Service

Use `services/artana_evidence_db` for:

- graph entities, relations, observations, provenance, and evidence
- dictionary models, repositories, management services, and governance
- relation validation and auto-promotion rules
- graph API routers and service contracts
- service-local Alembic migrations and tests

Common checks:

```bash
make graph-service-lint
make graph-service-type-check
make graph-service-boundary-check
make graph-service-contract-check
make graph-service-test
make graph-service-checks
```

## Local Development

Set up the environment:

```bash
make venv
make install-dev
```

Start local infrastructure and migrations:

```bash
make setup-postgres
```

Run both services:

```bash
make run-all
```

Default local ports:

- graph service: `8090`
- evidence API: `8091`

## Database And Contracts

- Graph service migrations live under `services/artana_evidence_db/alembic/versions`.
- Evidence API migrations live under `services/artana_evidence_api/alembic/versions`.
- Graph OpenAPI output lives at `services/artana_evidence_db/openapi.json`.
- Evidence API OpenAPI output lives at `services/artana_evidence_api/openapi.json`.
- Graph TypeScript service contracts live at `services/artana_evidence_db/artana-evidence-db.generated.ts`.

When API schemas change, run the matching contract generation/check target and include resulting artifact updates if the target expects them.

## Security Invariants

- Graph-service JWT signing must use `GRAPH_JWT_SECRET` in deployed environments. Do not rely on the development fallback outside local/dev use.
- Graph PostgreSQL access uses RLS session context from `services/artana_evidence_db/database.py`; do not bypass `app.current_user_id`, `app.has_phi_access`, or `app.bypass_rls` without an explicit system/migration reason.
- PHI-sensitive graph identifiers flow through `services/artana_evidence_db/phi_encryption_support.py` and repository encryption paths when PHI encryption is enabled.
- Audit and governance ledgers in the graph service are product data. Do not remove audit fields, mutation records, or decision envelopes as cleanup unless the migration and tests prove replacement behavior.

## Testing Expectations

- Add narrow regression tests for bug fixes.
- Add unit tests for pure service/domain behavior.
- Add integration tests for API endpoints, repositories, migrations, or cross-service contract behavior.
- Keep tests in the relevant service test tree when they exercise one service:
  - `services/artana_evidence_api/tests/unit`
  - `services/artana_evidence_api/tests/integration`
  - `services/artana_evidence_db/tests/unit`
  - `services/artana_evidence_db/tests/integration`
- Use root `tests/unit` for repository-level control files, packaging rules, migration contracts, or cross-service checks.

## QA Report

`scripts/run_qa_report.sh` is the repository-level QA wrapper. It should call only targets that exist in this repo's `Makefile`, especially the aggregate service gate:

```bash
make service-checks
```

Do not add removed external or frontend targets to the QA report script.
