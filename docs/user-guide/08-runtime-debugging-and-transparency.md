# Runtime, Debugging, And Transparency

This page is for developers, operators, and power users who need to understand
what happened during a run.

## Queue-First Runtime Behavior

Many run-start endpoints are queue-first.

They may return:

- `201 Created` when the run completes within the inline wait window
- `202 Accepted` when you ask for async behavior or the wait budget expires

To prefer async behavior, send:

```http
Prefer: respond-async
```

## Run Lifecycle

Useful endpoints:

- `POST /v1/spaces/{space_id}/runs`
- `GET /v1/spaces/{space_id}/runs`
- `GET /v1/spaces/{space_id}/runs/{run_id}`
- `GET /v1/spaces/{space_id}/runs/{run_id}/progress`
- `GET /v1/spaces/{space_id}/runs/{run_id}/events`
- `POST /v1/spaces/{space_id}/runs/{run_id}/resume`

Use these when you need to know whether a run is queued, running, completed,
failed, or paused.

## Artifacts

Artifacts are saved outputs from a run.

Useful endpoints:

- `GET /v1/spaces/{space_id}/runs/{run_id}/artifacts`
- `GET /v1/spaces/{space_id}/runs/{run_id}/artifacts/{artifact_key}`
- `GET /v1/spaces/{space_id}/runs/{run_id}/workspace`

Examples of artifacts:

- research brief
- source inventory
- graph context snapshot
- replay bundle
- workflow summary

## Transparency

Transparency endpoints help answer:

- what was the run allowed to do?
- what did the run actually do?
- did a human later approve or reject anything?

Useful endpoints:

- `GET /v1/spaces/{space_id}/runs/{run_id}/capabilities`
- `GET /v1/spaces/{space_id}/runs/{run_id}/policy-decisions`
- `POST /v1/spaces/{space_id}/runs/{run_id}/intent`

## Approvals

Some workflows pause for approval before continuing.

Useful endpoints:

- `GET /v1/spaces/{space_id}/runs/{run_id}/approvals`
- `POST /v1/spaces/{space_id}/runs/{run_id}/approvals/{approval_key}`

Approval body:

```json
{
  "decision": "approved",
  "reason": "Evidence is sufficient"
}
```

Use approvals when a workflow needs permission before applying a gated action.

## Harness Discovery

Harnesses are workflow templates.

Useful endpoints:

- `GET /v1/harnesses`
- `GET /v1/harnesses/{harness_id}`

If you are unsure what workflow ids exist, start here.
