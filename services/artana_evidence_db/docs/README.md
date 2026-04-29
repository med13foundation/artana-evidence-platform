# Graph API Docs

This folder explains the standalone `artana_evidence_db` service in plain language.

If you are new to the service, read these files in order:

1. [Getting Started](./getting-started.md)
2. [Core Concepts](./concepts.md)
3. [Data Model](./data-model.md)
4. [API Reference](./api-reference.md)

Planning:

- [V2 Reusable Graph Engine Plan](v2-reusable-graph-engine-plan.md)

Useful companion files:

- Service overview: [README.md](../README.md)
- Container definition: [Dockerfile](../Dockerfile)
- Interactive API docs when the service is running: `/docs`
- Raw OpenAPI spec: [openapi.json](../openapi.json)

What this service is:

- A standalone FastAPI service for graph storage, graph reads, graph curation, and graph governance.
- The HTTP boundary around the graph kernel tables such as `entities`, `observations`, `relations`, `relation_claims`, and `provenance`.
- The authority that decides when relation claims have enough evidence to become canonical graph relations.
- The owner of graph-space registry and graph-space membership state used for service-local authorization.
- A service that runs in its own process, with its own container image,
  database configuration, and service-local packaging boundary.

What this service is not:

- It is not the AI orchestration layer. That lives in `services/artana_evidence_api`.
- It is not the platform monolith API.
- It is not a background worker system by itself. Maintenance actions are exposed as explicit admin endpoints.

What this docs set focuses on:

- what runs inside the graph container
- how the graph service is separated from the rest of the platform
- what the main database tables mean
- the simplest mental model for claims, canonical relations, projections, and reasoning paths
- the evidence rule: evidence-required constraints can store draft claims, but cannot promote canonical relations until evidence exists
- the V2 evidence model: current `claim_evidence` and `relation_evidence` rows exist, and V2 makes them more explicit and governed
- every HTTP route exposed by the service
