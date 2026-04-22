# What This Service Does

This document explains the graph service in plain language.

## Short Version

The graph service is the backend that turns source records and curation input
into connected, explainable graph knowledge.

Instead of only storing isolated rows such as "this paper mentioned X", it lets
the system store and query:

- entities
  the things in the graph, such as genes, variants, phenotypes, papers, and
  claims
- claims
  statements extracted or entered about those things
- canonical relations
  the stable graph edges that are allowed to appear in default graph views
- evidence and provenance
  why a claim or relation exists and where it came from
- reasoning paths and graph search
  reusable paths and search results over the graph

## Why It Exists

MED13 needs more than document storage. It needs a way to answer questions like:

- what connects this gene to this phenotype?
- which claims support or refute this relation?
- what evidence explains this graph edge?
- what mechanism path leads from A to B?
- what graph state is safe to show as canonical truth versus still-open claim
  space?

This service exists to answer those questions through one graph-specific API and
runtime instead of spreading graph logic across the main platform.

## What It Owns

The graph service owns:

- graph APIs for entities, claims, relations, graph views, graph documents,
  graph search, graph connections, reasoning paths, hypotheses, concepts, and
  dictionary governance
- graph-specific admin/control-plane APIs for graph spaces, memberships,
  readiness audits, repairs, rebuilds, and run history
- graph-service-local authz rules for graph spaces and graph admins
- graph-owned runtime metadata such as `graph_spaces`,
  `graph_space_memberships`, and `graph_operation_runs`

The graph service does not own:

- general platform membership and organization business rules
- the full MED13 admin UI
- the public website
- generic platform APIs outside the graph boundary

## How It Works In Simple Terms

1. Data comes in from ingestion, extraction, or manual curation.
2. The service stores claims, participants, and evidence about that data.
3. Resolved support claims can materialize canonical relations.
4. Canonical graph reads return stable, explainable edges by default.
5. Claim-space reads still preserve disagreement, uncertainty, and hypotheses.
6. Search, graph views, and reasoning-path reads use those explainable graph
   stores to answer user questions.

The key idea is:

- claims are the detailed ledger
- canonical relations are the stable graph projection
- evidence and provenance explain both

## What Different People Use It For

### Researchers and Curators

- browse the graph
- inspect claims and evidence
- review or resolve claim state
- inspect domain views such as gene, variant, phenotype, paper, and claim
- generate or record hypotheses

### Admins and Operators

- keep graph spaces and memberships in sync
- run readiness audits and repairs
- rebuild reasoning paths
- inspect operation-run history
- manage graph-specific dictionary governance

### Developers

- call the graph service over HTTP
- use the generated OpenAPI and TypeScript contracts
- add or change graph-service routes and runtime code
- validate graph boundaries and graph-specific deploy/runtime contracts

## Is It MED13-Specific?

The surrounding application is still MED13-first, but the graph service itself
now implements a pack-driven graph platform.

Current state:

- graph-core owns the claim-first model, auth/tenancy abstractions, read-model
  framework, release contract, and runtime helpers
- domain packs supply domain-shaped behavior such as view types, prompts,
  dictionary seeding, connector defaults, and heuristics
- the built-in packs are `biomedical` and `sports`
- `biomedical` remains the primary production pack
- `sports` proves that the same runtime, auth, contract, and read-model
  framework work without core forks

The examples in these docs remain mostly biomedical because MED13 is still the
main product context, but the implemented service is no longer only a
biomedical runtime.

## What To Read Next

- If you operate the service: [../admins/admin-guide.md](../admins/admin-guide.md)
- If you develop against it: [../developers/developer-guide.md](../developers/developer-guide.md)
- If you need exact API routes: [../reference/endpoints.md](../reference/endpoints.md)
- If you need the graph model and invariants: [../reference/architecture.md](../reference/architecture.md)
- If you need to understand the pack model: [../reference/domain-pack-lifecycle.md](../reference/domain-pack-lifecycle.md)
