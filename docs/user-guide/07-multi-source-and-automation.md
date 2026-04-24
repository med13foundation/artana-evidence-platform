# Multi-Source And Automated Workflows

Once the basic document and review flow is comfortable, these workflows help
you cover more ground.

## Research Plan

Use `research-plan` when you already know the research question and source mix.

Good for:

- starting a new topic with several sources
- using PubMed plus structured sources such as MARRVEL or ClinVar
- producing an initial research state and source summary

Endpoint:

- `POST /v2/spaces/{space_id}/research-plan`

## Topic Setup

Use topic setup when you want a first map of a topic.

Good for:

- getting a head start from seed entities
- staging initial proposed updates for review
- creating a first research brief

Endpoint:

- `POST /v2/spaces/{space_id}/workflows/topic-setup/tasks`

## Continuous Learning

Use continuous learning when you want the system to refresh a space over time.

Good for:

- checking for new evidence
- creating a limited number of new proposals
- tracking next questions

Endpoint:

- `POST /v2/spaces/{space_id}/workflows/continuous-review/tasks`

## Schedules

Schedules save recurring workflow configuration.

Useful endpoints:

- `GET /v2/spaces/{space_id}/schedules`
- `POST /v2/spaces/{space_id}/schedules`
- `PATCH /v2/spaces/{space_id}/schedules/{schedule_id}`
- `POST /v2/spaces/{space_id}/schedules/{schedule_id}/pause`
- `POST /v2/spaces/{space_id}/schedules/{schedule_id}/resume`
- `POST /v2/spaces/{space_id}/schedules/{schedule_id}/start-now`

Use schedules only after you are confident the workflow is producing useful
reviewable output.

## Evidence Curation

Evidence curation is a more governed path for claim-writing workflows.

Endpoint:

- `POST /v2/spaces/{space_id}/workflows/evidence-curation/tasks`

Good for:

- high-impact claims
- workflows where explicit review and approval checkpoints matter

## Full Research

Full research composes larger workflows, such as topic setup, briefing chat, and
curation.

Useful endpoints:

- `POST /v2/spaces/{space_id}/workflows/full-research/tasks`
- `GET /v2/spaces/{space_id}/workflows/full-research/tasks`
- `GET /v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}`
- `GET /v2/spaces/{space_id}/workflows/full-research/dashboard`

Full research is powerful, but it is not the best first workflow. Learn documents,
review items, the evidence map, and evidence search first.

## Autopilot

Autopilot is the broadest guarded AI workflow surface.

Endpoint:

- `POST /v2/spaces/{space_id}/workflows/autopilot/tasks`

Use it when you need a broad, guarded AI workflow and you understand the review
and transparency surfaces.
