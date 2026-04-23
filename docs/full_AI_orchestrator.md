# Full AI Orchestrator

Status date: April 23, 2026.

The full AI orchestrator is the Evidence API's broadest research workflow. It
wraps research-init with planner checkpoints, guarded decisions, artifacts, and
operator-controllable rollout modes.

Endpoint:

- `POST /v1/spaces/{space_id}/agents/full-ai-orchestrator/runs`

Primary files:

- `services/artana_evidence_api/routers/full_ai_orchestrator_runs.py`
- `services/artana_evidence_api/full_ai_orchestrator_runtime.py`
- `services/artana_evidence_api/full_ai_orchestrator_contracts.py`
- `services/artana_evidence_api/full_ai_orchestrator_shadow_planner.py`

## Current Behavior

The orchestrator can:

- create a durable run;
- execute research-init style source discovery and extraction;
- use planner checkpoints in shadow or guarded modes;
- record action history and decision artifacts;
- preserve replay bundles and source execution summaries;
- expose progress, events, artifacts, policy decisions, and workspace state
  through the shared run APIs.

## Modes

The current code supports deterministic and AI-assisted rollout modes through
space settings and request/runtime options:

- `deterministic`: baseline behavior and rollback target;
- `full_ai_shadow`: planner recommends but does not control live actions;
- `full_ai_guarded`: bounded planner decisions can affect selected low-risk
  actions under guardrails.

Guarded behavior is intentionally narrow. The orchestrator should not bypass
the review queue or graph governance boundary.

## Trust Boundary

The orchestrator can suggest, chase, summarize, and stage work. It should not
turn unreviewed AI output into trusted graph state. Promotion remains governed
by proposal/review flows and graph service policy.

## Operator Surfaces

Use these runtime endpoints to inspect behavior:

- `GET /v1/spaces/{space_id}/runs/{run_id}`
- `GET /v1/spaces/{space_id}/runs/{run_id}/progress`
- `GET /v1/spaces/{space_id}/runs/{run_id}/events`
- `GET /v1/spaces/{space_id}/runs/{run_id}/artifacts`
- `GET /v1/spaces/{space_id}/runs/{run_id}/policy-decisions`
- `GET /v1/spaces/{space_id}/runs/{run_id}/workspace`

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
