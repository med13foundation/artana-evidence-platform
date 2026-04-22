# Artana Evidence Platform

`artana-evidence-platform` is the extraction target for the Artana evidence
services that currently live inside the monorepo.

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

The current migration focus is no longer "copy the code over." The current
focus is finishing the standalone unwind:

- M2: remove remaining production `src` dependencies from the graph service
- M3: localize or explicitly own the evidence API shared-runtime dependencies

## Tracking Docs

- [Migration Plan](docs/migration-plan.md)
- [Migration Checklist](docs/migration-checklist.md)

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
