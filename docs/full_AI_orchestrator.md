# Full AI Orchestrator

Status date: April 30, 2026.

The full AI orchestrator is the Evidence API's broadest research workflow. It
wraps research-plan with planner checkpoints, guarded decisions, outputs, and
operator-controllable rollout modes.

Public endpoint:

- `POST /v2/spaces/{space_id}/workflows/full-research/tasks`

Primary files:

- `services/artana_evidence_api/routers/full_ai_orchestrator_runs.py`
- `services/artana_evidence_api/full_ai_orchestrator/execute.py`
- `services/artana_evidence_api/full_ai_orchestrator/queue.py`
- `services/artana_evidence_api/full_ai_orchestrator/response.py`
- `services/artana_evidence_api/full_ai_orchestrator_contracts.py`
- `services/artana_evidence_api/full_ai_orchestrator/shadow_planner/`

Compatibility imports:

- `services/artana_evidence_api/full_ai_orchestrator_runtime.py`
- `services/artana_evidence_api/full_ai_orchestrator_shadow_planner.py`
- other root `full_ai_orchestrator_*.py` files

Those root files are kept as thin compatibility facades so older imports and
tests continue to work. New implementation work should use the package paths.

## Current Behavior

The orchestrator can:

- create a durable task;
- execute research-plan style source discovery and extraction;
- use planner checkpoints in shadow or guarded modes;
- record action history and decision outputs;
- preserve replay bundles and source execution summaries;
- expose progress, events, outputs, decisions, and working state through the
  shared task APIs.

## Modes

The current code supports deterministic and AI-assisted rollout modes through
space settings and request/runtime options:

- `deterministic`: baseline behavior and rollback target;
- `full_ai_shadow`: planner recommends but does not control live actions;
- `full_ai_guarded`: bounded planner decisions can affect selected low-risk
  actions under guardrails.

Guarded behavior is intentionally narrow. The orchestrator should not bypass
the review gate or graph governance boundary.

## Trust Boundary

The orchestrator can suggest, chase, summarize, and stage work. It should not
turn unreviewed AI output into trusted graph state. Promotion remains governed
by proposal/review flows and graph service policy.

## Operator Surfaces

Use these runtime endpoints to inspect behavior:

- `GET /v2/spaces/{space_id}/tasks/{task_id}`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/progress`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/events`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/outputs`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/decisions`
- `GET /v2/spaces/{space_id}/tasks/{task_id}/working-state`

The old long-form canary reports are not kept in `docs/`. New rollout evidence
should live under ignored `reports/` output and be summarized in PRs.

## Package Layout

The implementation is now grouped by responsibility:

```text
full_ai_orchestrator/
  execute.py              main run execution
  queue.py                task queue entrypoint
  response.py             API response assembly
  action_registry.py      allowed orchestrator actions
  workspace_support.py    workspace/result helpers
  progress/               progress observer and state
  guarded/                guarded rollout, readiness, policy, verification
  shadow/                 shadow summaries, decisions, timelines
  shadow_planner/         planner prompts, validation, runtime, telemetry
```

## Known Architecture Debt

The full-AI package split is complete enough that the old root runtime module
is no longer a monolith. Remaining debt is mostly compatibility cleanup:

- keep root `full_ai_orchestrator_*.py` facades only while old imports need
  them;
- prefer package-path imports for new code;
- remove compatibility facades only after the control file and tests prove no
  internal or documented caller still needs the old path.
