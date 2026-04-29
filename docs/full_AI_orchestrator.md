# Full AI Orchestrator

Status date: April 29, 2026.

The full AI orchestrator is the Evidence API's broadest research workflow. It
wraps research-plan with planner checkpoints, guarded decisions, outputs, and
operator-controllable rollout modes.

Public endpoint:

- `POST /v2/spaces/{space_id}/workflows/full-research/tasks`

Primary files:

- `services/artana_evidence_api/routers/full_ai_orchestrator_runs.py`
- `services/artana_evidence_api/full_ai_orchestrator_runtime.py`
- `services/artana_evidence_api/full_ai_orchestrator_contracts.py`
- `services/artana_evidence_api/full_ai_orchestrator_shadow_planner.py`

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

## Known Architecture Debt

`full_ai_orchestrator_runtime.py` is still too large. Split it after the
current behavior is stable:

- planner checkpoint assembly;
- guarded action execution;
- runtime policy;
- artifact writing;
- source execution summaries.
