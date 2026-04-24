# Core Concepts

These are the main words you will see across the API.

## Space

A space is your research space.

For MED13, you might create one space called `MED13 Workspace`. It keeps the
topic, permissions, evidence, graph context, and research state together.

Useful endpoints:

- `POST /v2/spaces`
- `PUT /v2/spaces/default`
- `GET /v2/spaces/{space_id}/research-state`

## Evidence Item

An evidence item is source material the system can reason from.

Examples:

- text note
- PDF
- paper abstract
- structured source result from PubMed, MARRVEL, ClinVar, or another enabled
  source

Useful endpoints:

- `POST /v2/spaces/{space_id}/documents/text`
- `POST /v2/spaces/{space_id}/documents/pdf`
- `POST /v2/spaces/{space_id}/sources/pubmed/searches`
- `POST /v2/spaces/{space_id}/sources/marrvel/searches`

## Task

A task is one job the system performs.

Examples:

- extract findings from one document
- run a multi-source research-plan workflow
- answer a graph-search question
- run continuous learning

Useful endpoints:

- `GET /v2/spaces/{space_id}/tasks`
- `GET /v2/spaces/{space_id}/tasks/{task_id}`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/events`

## Proposed Update

A proposed update is a suggested fact that needs review.

Think of it as the system saying: "This may be worth adding to the graph, but a
human should check it first."

Useful endpoints:

- `GET /v2/spaces/{space_id}/proposed-updates`
- `GET /v2/spaces/{space_id}/review-items`

## Review Item

The review items list is the main human decision surface.

It can include:

- proposals to promote or reject
- review-only follow-up items
- approvals for paused runs

This is the gate between AI suggestion and trusted graph knowledge.

Useful endpoints:

- `GET /v2/spaces/{space_id}/review-items`
- `POST /v2/spaces/{space_id}/review-items/{item_id}/decision`

## Graph

The graph is the trusted evidence map.

Approved entities, claims, relationships, and evidence live here. Normal users
should usually add to it by reviewing and promoting proposals, not by direct
low-level writes.

Useful endpoints:

- `GET /v2/spaces/{space_id}/evidence-map/entities`
- `GET /v2/spaces/{space_id}/evidence-map/claims`
- `GET /v2/spaces/{space_id}/evidence-map/claims/{claim_id}/evidence`

## Output

An output is saved material produced by a task.

Examples:

- research brief
- source inventory
- graph snapshot
- progress summary

Useful endpoints:

- `GET /v2/spaces/{space_id}/tasks/{task_id}/outputs`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/outputs/{output_key}`
