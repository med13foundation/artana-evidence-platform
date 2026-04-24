# Real Use Cases

This page shows a few concrete ways someone might use the platform.

Each scenario answers two questions:

- what the user does
- what the tool provides

## Scenario 1: Start A New Gene Research Space

Use this when a researcher wants a fast starting point for a topic such as
`MED13` and does not want to upload documents first.

### What The User Does

1. Create or open a space.
2. Start a research plan with the gene, disease, and source mix.
3. Wait for the initial task to finish.
4. Review the staged findings.

Main endpoints:

- `PUT /v2/spaces/default`
- `POST /v2/spaces/{space_id}/research-plan`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/progress`
- `GET /v2/spaces/{space_id}/review-items`

### What The Tool Provides

The tool creates an initial research state for the topic, pulls evidence from
the chosen sources, and stages reviewable findings.

That usually includes:

- a tracked task
- source results from systems like PubMed or MARRVEL
- review items for human checking
- a starting evidence map the researcher can explore later

In plain terms:

> The user says, "Help me get started on MED13."
> The tool returns a first research package that the user can review and trust
> step by step.

## Scenario 2: Turn A Paper Into Trusted Evidence

Use this when a user already has a paper, note, or PDF and wants the system to
extract structured findings from it.

### What The User Does

1. Upload text or a PDF.
2. Start extraction for that document.
3. Open the review items that came from the document.
4. Promote the strong findings and reject the weak ones.

Main endpoints:

- `POST /v2/spaces/{space_id}/documents/text`
- `POST /v2/spaces/{space_id}/documents/pdf`
- `POST /v2/spaces/{space_id}/documents/{document_id}/extraction`
- `GET /v2/spaces/{space_id}/review-items?document_id=<document_id>`
- `POST /v2/spaces/{space_id}/review-items/{item_id}/decision`

### What The Tool Provides

The tool reads the source, extracts candidate entities, claims, observations,
and evidence, then puts them into a governed review flow.

That gives the user:

- structured findings instead of a raw paper only
- a place to approve or reject each finding
- promoted evidence that becomes part of the evidence map

In plain terms:

> The user gives the tool a paper.
> The tool turns it into reviewable evidence instead of asking the user to read
> and structure everything by hand.

## Scenario 3: Ask Questions About Trusted Evidence

Use this when a user already has reviewed evidence in the space and wants
answers, summaries, or map exploration.

### What The User Does

1. Browse the evidence map to inspect trusted entities and claims.
2. Ask an evidence-search task or send a chat message.
3. Read the answer and, if needed, stage suggested updates for review.

Main endpoints:

- `GET /v2/spaces/{space_id}/evidence-map/entities`
- `GET /v2/spaces/{space_id}/evidence-map/claims`
- `POST /v2/spaces/{space_id}/workflows/evidence-search/tasks`
- `POST /v2/spaces/{space_id}/chat-sessions`
- `POST /v2/spaces/{space_id}/chat-sessions/{session_id}/messages`
- `POST /v2/spaces/{space_id}/chat-sessions/{session_id}/suggested-updates`

### What The Tool Provides

The tool answers questions using the reviewed material already in the space and
can stage possible follow-up updates when it finds something worth adding.

That helps the user:

- inspect trusted evidence directly
- get evidence-backed summaries
- move from "question" to "possible next update" without skipping review

In plain terms:

> The user asks, "What is the strongest evidence linking MED13 to
> cardiomyopathy?"
> The tool answers from the trusted evidence and can prepare suggested updates
> for review if new structured findings should be added.

## Scenario 4: Keep A Topic Fresh Over Time

Use this when a team wants a space to be checked again later instead of doing
everything manually every week.

### What The User Does

1. Choose a workflow that should run again later.
2. Create a schedule.
3. Pause, resume, or start it manually when needed.
4. Review the new findings after each scheduled run.

Main endpoints:

- `POST /v2/spaces/{space_id}/workflows/continuous-review/tasks`
- `GET /v2/spaces/{space_id}/schedules`
- `POST /v2/spaces/{space_id}/schedules`
- `POST /v2/spaces/{space_id}/schedules/{schedule_id}/start-now`
- `GET /v2/spaces/{space_id}/review-items`

### What The Tool Provides

The tool reruns a chosen workflow, tracks the resulting tasks, and stages fresh
review items instead of silently changing trusted graph state.

That gives the team:

- repeatable background refresh
- new candidate findings to review
- a controlled way to keep the evidence map current

In plain terms:

> The user says, "Check this topic again next week."
> The tool does the refresh work, but people still decide what becomes trusted.
