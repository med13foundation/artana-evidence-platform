# Artana Evidence Platform

`artana-evidence-platform` is the extraction target for the Artana evidence
services that currently live inside the monorepo.

As of April 23, 2026, this repository is the source of truth for:

- `services/artana_evidence_db`
- `services/artana_evidence_api`

Staging deployments for both services now run from this repository's GitHub
Actions workflows.

The initial scope is:

- `services/artana_evidence_db`: standalone governed graph service
- `services/artana_evidence_api`: AI evidence and orchestration service
- temporary shared runtime code currently imported from `src/`
- optional later move of `packages/artana_api`

This repository started in planning-and-tracking mode so the migration could be
executed deliberately rather than as an ad hoc folder copy.

## Current Status

As of April 22, 2026, the first bootable baseline import is in place in this
repository.

Imported and verified in the extracted repo:

- `services/artana_evidence_db`
- `services/artana_evidence_api`
- temporary shared runtime code from `src/`
- service-relevant `scripts/`, `docs/`, `tests/`, and `packages/artana_api`
- root extracted-repo tooling such as `Makefile`, `pytest.ini`,
  `.dockerignore`, and local Postgres helpers

The migration cutover is complete:

- M2: graph service standalone unwind complete
- M3: evidence API direct production `src` imports eliminated
- M4: CI, deploy workflows, and deploy/runtime docs complete
- M5: cutover complete, staging verified, monorepo copies deprecated

## Tracking Docs

- [Migration Plan](docs/migration-plan.md)
- [Migration Checklist](docs/migration-checklist.md)
- [Extracted Services Deploy Runbook](docs/deployment/extracted-services-runbook.md)

## Intended First-Cut Boundaries

Included in the first extraction cut:

- `services/artana_evidence_db`
- `services/artana_evidence_api`
- `src/` as a temporary shared runtime package
- selected `scripts/`, `docs/`, and test assets needed to keep service gates green

Explicitly out of scope for the first cut unless requirements change:

- `services/research_inbox`
- `services/research_inbox_runtime`
- legacy `src/web`
- unrelated monorepo services and infrastructure

## Goal

Get the graph service and evidence API into a dedicated repository with a
working local/dev/test/deploy loop first, then progressively unwind the
remaining monorepo shared-runtime dependencies.

## Verified Baseline

The following checks have already been run successfully from this repository:

- `make graph-service-checks`
- `make artana-evidence-api-service-checks`
- `make run-graph-service`
- `make run-artana-evidence-api-service`
- Docker runtime builds for both service images
