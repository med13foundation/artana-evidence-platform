# Multi-Source And Automated Workflows

Once the basic document and review flow is comfortable, these workflows help
you cover more ground.

## Research Init

Use `research-init` when you already know the research question and source mix.

Good for:

- starting a new topic with several sources
- using PubMed plus structured sources such as MARRVEL or ClinVar
- producing an initial research state and source summary

Endpoint:

- `POST /v1/spaces/{space_id}/research-init`

## Research Bootstrap

Use research bootstrap when you want a first map of a topic.

Good for:

- getting a head start from seed entities
- staging initial graph-write proposals for review
- creating a first research brief

Endpoint:

- `POST /v1/spaces/{space_id}/agents/research-bootstrap/runs`

## Continuous Learning

Use continuous learning when you want the system to refresh a space over time.

Good for:

- checking for new evidence
- creating a limited number of new proposals
- tracking next questions

Endpoint:

- `POST /v1/spaces/{space_id}/agents/continuous-learning/runs`

## Schedules

Schedules save recurring workflow configuration.

Useful endpoints:

- `GET /v1/spaces/{space_id}/schedules`
- `POST /v1/spaces/{space_id}/schedules`
- `PATCH /v1/spaces/{space_id}/schedules/{schedule_id}`
- `POST /v1/spaces/{space_id}/schedules/{schedule_id}/pause`
- `POST /v1/spaces/{space_id}/schedules/{schedule_id}/resume`
- `POST /v1/spaces/{space_id}/schedules/{schedule_id}/run-now`

Use schedules only after you are confident the workflow is producing useful
reviewable output.

## Graph Curation

Graph curation is a more governed path for claim-writing workflows.

Endpoint:

- `POST /v1/spaces/{space_id}/agents/graph-curation/runs`

Good for:

- high-impact claims
- workflows where explicit review and approval checkpoints matter

## Supervisor

Supervisor composes larger workflows, such as bootstrap, briefing chat, and
curation.

Useful endpoints:

- `POST /v1/spaces/{space_id}/agents/supervisor/runs`
- `GET /v1/spaces/{space_id}/agents/supervisor/runs`
- `GET /v1/spaces/{space_id}/agents/supervisor/runs/{run_id}`
- `GET /v1/spaces/{space_id}/agents/supervisor/dashboard`

Supervisor is powerful, but it is not the best first workflow. Learn documents,
review queue, graph explorer, and graph search first.

## Full AI Orchestrator

The full AI orchestrator is the largest deterministic orchestration surface.

Endpoint:

- `POST /v1/spaces/{space_id}/agents/full-ai-orchestrator/runs`

Use it when you need a broad, guarded AI workflow and you understand the review
and transparency surfaces.
