# Artana Evidence Platform

`artana-evidence-platform` is the extraction target for the Artana evidence
services that currently live inside the monorepo.

The initial scope is:

- `services/artana_evidence_db`: standalone governed graph service
- `services/artana_evidence_api`: AI evidence and orchestration service
- temporary shared runtime code currently imported from `src/`
- optional later move of `packages/artana_api`

This repository starts in planning-and-tracking mode so the migration can be
executed deliberately rather than as an ad hoc folder copy.

## Current Status

As of April 22, 2026, this repository is being prepared as the new home for the
extracted services. The code has not been imported yet. The first tracked goal
is to land a bootable baseline import with clear acceptance gates.

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
