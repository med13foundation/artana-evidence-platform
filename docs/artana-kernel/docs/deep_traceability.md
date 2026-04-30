# Deep Traceability

Status date: April 29, 2026.

Traceability in this repo is split between Evidence API task records, Artana
kernel state, and graph provenance.

## Evidence API Runtime Trace

Use these endpoints for one Evidence API task:

- `GET /v2/spaces/{space_id}/tasks/{task_id}`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/progress`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/events`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/outputs`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/decisions`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/working-state`

Outputs are the main way to inspect summaries, replay bundles, planner
decisions, source execution summaries, graph snapshots, and generated briefs.

## Artana Kernel Trace

The Artana store captures model/tool execution state for kernel-backed steps.
The Evidence API configures the store through
`services/artana_evidence_api/runtime/postgres_store.py`. The old
`services/artana_evidence_api/runtime_support.py` path remains as a
compatibility facade.

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
