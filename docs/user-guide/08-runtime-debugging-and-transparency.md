# Runtime, Debugging, And Transparency

This page is for developers, operators, and power users who need to understand
what happened during a task.

## Queue-First Runtime Behavior

Many task-start endpoints are queue-first.

They may return:

- `201 Created` when the task completes within the inline wait window
- `202 Accepted` when you ask for async behavior or the wait budget expires

To prefer async behavior, send:

```http
Prefer: respond-async
```

## Task Lifecycle

Useful endpoints:

- `POST /v2/spaces/{space_id}/tasks`
- `GET /v2/spaces/{space_id}/tasks`
- `GET /v2/spaces/{space_id}/tasks/{task_id}`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/progress`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/events`
- `POST /v2/spaces/{space_id}/tasks/{task_id}/resume`

Use these when you need to know whether a task is queued, running, completed,
failed, or paused.

## Outputs

Outputs are saved materials from a task.

Useful endpoints:

- `GET /v2/spaces/{space_id}/tasks/{task_id}/outputs`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/outputs/{output_key}`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/working-state`

Examples of outputs:

- research brief
- source inventory
- graph context snapshot
- replay bundle
- workflow summary

## Transparency

Transparency endpoints help answer:

- what was the task allowed to do?
- what did the task actually do?
- did a human later approve or reject anything?

Useful endpoints:

- `GET /v2/spaces/{space_id}/tasks/{task_id}/capabilities`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/decisions`
- `POST /v2/spaces/{space_id}/tasks/{task_id}/planned-actions`

## Approvals

Some workflows pause for approval before continuing.

Useful endpoints:

- `GET /v2/spaces/{space_id}/tasks/{task_id}/approvals`
- `POST /v2/spaces/{space_id}/tasks/{task_id}/approvals/{approval_key}/decision`

Approval body:

```json
{
  "decision": "approved",
  "reason": "Evidence is sufficient"
}
```

Use approvals when a workflow needs permission before applying a gated action.

## Workflow Template Discovery

Workflow templates are the public template objects exposed by the Evidence API.

Useful endpoints:

- `GET /v2/workflow-templates`
- `GET /v2/workflow-templates/{template_id}`

If you are unsure what workflow ids exist, start here.
