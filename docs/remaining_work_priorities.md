# Remaining Work Priorities

Status date: April 30, 2026.

The backend scaffold is in place. The remaining work is about hardening the
boundaries, making testing easier, and preparing for external users without
overbuilding too early.

## P0 - Keep The Extracted Services Shippable

- Keep `make graph-service-checks` passing.
- Keep `make artana-evidence-api-service-checks` passing.
- Keep both generated OpenAPI artifacts current.
- Keep `services/artana_evidence_db/artana-evidence-db.generated.ts` current.
- Do not reintroduce the removed top-level `src` runtime package.
- Keep durable direct source-search and selected-record handoff covered in
  OpenAPI, route tests, and user-facing docs.
- Keep the v2 public API migration moving according to
  [V2 API Migration Plan](./v2_api_migration_plan.md).

## P1 - Finish Evidence API Layering Cleanup

- Move remaining PubMed helper logic out of router modules and below both
  router and runtime code.
- Move PDF enrichment helper logic out of `routers/documents.py`.
- Add a validator rule that blocks production runtime imports from
  `artana_evidence_api.routers.*` after those helper moves land.
- Keep graph mutation paths going through `graph_integration` or graph HTTP
  client surfaces.

## P1 - Test Local Identity With Real Users

- Use `POST /v2/auth/bootstrap` for the first local/admin user.
- Use `POST /v2/auth/testers` for additional internal testers.
- Watch for friction around key rotation, lost keys, space membership, and
  admin operations.
- Decide later whether to implement `RemoteIdentityGateway`; do not add it
  until tester or customer needs make the extra service worthwhile.

## P2 - Continue Packaging Cleanup

- Split `research_init_runtime.py` by source discovery, document preparation,
  extraction staging, replay, and finalization.
- Split `graph_workflow_service.py` by command family.
- Continue reducing root compatibility facades only after
  `architecture_structure_overrides.json` and compatibility tests prove no
  internal or documented caller still needs the old import path.

## P2 - Improve Deployment Confidence

- Keep Cloud Run runtime-config sync scripts aligned with the current env var
  contract.
- Add or refresh staging smoke checks for `/health`, OpenAPI, auth bootstrap or
  tester creation, graph space sync, and one review flow through review items.
- Keep live external API tests opt-in. They depend on network and third-party
  service availability.

## P1 - Move The Public Surface To V2

- Move public docs, examples, and user guides to `/v2` first.
- Move smoke suites, user-flow tests, and helper scripts to `/v2` first.
- Rename v2 request and response fields that still leak `run` or `harness`
  nouns.
- Keep v1 as a compatibility layer only while the v2 cutover finishes.

## P3 - Product Surfaces Outside This Repo

- Decide whether the next public surface is a frontend, a small SDK, or direct
  API onboarding docs.
- Keep that decision outside the current service-boundary cleanup unless it
  directly affects API contracts.
