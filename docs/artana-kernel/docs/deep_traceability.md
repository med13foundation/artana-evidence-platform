# Deep Traceability

Status date: April 23, 2026.

Traceability in this repo is split between Evidence API run records, Artana
kernel state, and graph provenance.

## Evidence API Runtime Trace

Use these endpoints for one run:

- `GET /v1/spaces/{space_id}/runs/{run_id}`
- `GET /v1/spaces/{space_id}/runs/{run_id}/progress`
- `GET /v1/spaces/{space_id}/runs/{run_id}/events`
- `GET /v1/spaces/{space_id}/runs/{run_id}/artifacts`
- `GET /v1/spaces/{space_id}/runs/{run_id}/policy-decisions`
- `GET /v1/spaces/{space_id}/runs/{run_id}/workspace`

Artifacts are the main way to inspect summaries, replay bundles, planner
decisions, source execution summaries, graph snapshots, and generated briefs.

## Artana Kernel Trace

The Artana store captures model/tool execution state for kernel-backed steps.
The Evidence API configures the store in
`services/artana_evidence_api/runtime_support.py`.

## Graph Trace

Trusted graph state carries provenance and evidence through graph-service
records:

- claims;
- claim evidence;
- relation evidence;
- observations;
- provenance;
- graph views and explain endpoints.

The graph service owns those records. Evidence API workflows should link back
to graph state instead of duplicating graph provenance logic.
