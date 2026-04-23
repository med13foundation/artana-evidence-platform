# Graph Service Upgrade Guide

This guide describes the supported upgrade path for operators and dependent
services consuming the standalone graph service.

## Before Upgrading

Run `make graph-service-checks` from the repository root. This validates the
graph service boundary, OpenAPI artifact, generated client artifact, type gate,
and release documentation contract.

Review new `alembic` migrations under the graph service migration tree before
applying them to shared environments.

## Upgrade Steps

1. Deploy the new graph service image.
2. Apply graph-service `alembic` migrations.
3. Confirm `/health` reports the expected service version.
4. Confirm the deployed OpenAPI document matches
   `services/artana_evidence_db/openapi.json`.
5. Roll dependent services only after they are confirmed to consume the HTTP
   contract or generated artifacts.

## Rollback Notes

Roll back application code only after checking whether a migration changed the
database shape. When a migration is not reversible, pause rollout and use a
forward repair migration instead of downgrading production data.
