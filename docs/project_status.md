# Project Status

Status date: April 26, 2026.

## Summary

`artana-evidence-platform` is now an extracted two-service backend repo. The
current checkout is not the old monorepo and not a frontend workspace.

Implemented now:

- standalone graph service package: `services/artana_evidence_db`;
- standalone Evidence API package: `services/artana_evidence_api`;
- local Postgres setup and migrations for both services;
- generated OpenAPI artifacts for both services;
- generated TypeScript graph contract artifact;
- boundary validators for graph and Evidence API service separation;
- local identity gateway for low-friction tester access;
- document upload, extraction, proposals, review queue, runs, artifacts,
  research-init, chat, graph-search, continuous-learning, supervisor, and full
  AI orchestrator endpoints in the Evidence API;
- source registry, durable direct source-search capture, and idempotent
  selected-record handoff for PubMed, MARRVEL, ClinVar, ClinicalTrials.gov,
  UniProt, AlphaFold, DrugBank, MGI, and ZFIN;
- dictionary, claims, relations, observations, provenance, graph views,
  reasoning paths, workflows, domain packs, and admin space-sync endpoints in
  the graph service.

Not present in this checkout:

- `services/research_inbox`;
- `services/research_inbox_runtime`;
- `services/frontdoor`;
- the old top-level `src/` runtime package;
- `packages/artana_api`;
- a production UI.

## Current Service Topology

```text
tester or client
  -> Evidence API (:8091 local)
     -> Graph service HTTP contract (:8090 local)
        -> graph-owned Postgres schema
```

For local development, `make run-all` starts Postgres and both services.

## Evidence API Status

The Evidence API is the user-facing backend service in this repo. It owns:

- auth/API-key endpoints under `/v1/auth`;
- local tester onboarding through `POST /v1/auth/testers`;
- research spaces and membership endpoints under `/v1/spaces`;
- document upload/extraction endpoints;
- proposal and review-queue endpoints;
- run lifecycle, artifacts, progress, policy, approvals, and workspace
  inspection;
- research-init and research-bootstrap workflows;
- source capability, direct-search, durable search retrieval, and selected
  source-result handoff endpoints;
- graph explorer and graph search workflow surfaces;
- full AI orchestrator, supervisor, continuous-learning, graph-curation,
  graph-connection, hypothesis, and mechanism-discovery runs.

Identity and tenancy are local for now, but the gateway contract is in place so
future remote identity extraction does not require rewriting all routes.

## Graph Service Status

The graph service is the graph-owned backend. It owns:

- dictionary and dictionary proposal APIs;
- graph entities, relations, observations, claims, claim evidence, and claim
  participants;
- provenance and explainability records;
- graph views, graph documents, neighborhood/subgraph/export endpoints;
- concepts and concept proposals;
- hypotheses and reasoning paths;
- graph workflows and AI-full-mode governance records;
- domain-pack seed and repair operations;
- admin space registry, membership sync, and projection maintenance endpoints.

The graph service release contract is guarded by OpenAPI, generated TypeScript
types, release docs, and `make graph-service-checks`.

## Current Boundaries

The current boundary rules are:

- Evidence API calls graph behavior over HTTP/client contracts.
- Graph service does not own end-user API keys.
- User/API-key/space/membership decisions in the Evidence API pass through
  `IdentityGateway`.
- Generated OpenAPI artifacts must match runtime code.
- The removed top-level `src/` package must not return as a runtime dependency.

## Known Gaps

The main remaining gaps are architecture hardening, not missing core service
scaffold:

- final decision on local identity ownership versus a future remote identity
  service;
- remaining runtime-to-router helper imports in research-init;
- very large orchestration modules that should be split after behavior is
  stable;
- no frontend or SDK package in this checkout;
- external live-source checks remain opt-in because they depend on network and
  external API availability.

Direct source-search handoff is implemented in the Evidence API and remains
review-gated. It creates extraction inputs or durable source documents from
captured source results, but it does not write trusted graph facts directly.

See [Pending Boundary Issues](./architecture/pending-boundary-issues.md) and
[Remaining Work](./remaining_work_priorities.md).
