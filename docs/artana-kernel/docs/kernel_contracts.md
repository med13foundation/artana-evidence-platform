# Kernel Contracts

Status date: April 23, 2026.

The Evidence API uses `artana-kernel` for durable model/tool execution, runtime
state, middleware, replay policy, and structured model steps.

## Current Contract

The service-local integration is responsible for:

- creating an `ArtanaKernel`;
- configuring middleware with safety, quota, capabilities, and PII support;
- using an Artana Postgres store derived from `ARTANA_STATE_URI` or
  `DATABASE_URL`;
- recording model steps with deterministic step keys;
- returning structured Pydantic outputs where model execution is used;
- closing kernel/store resources correctly.

## Runtime Store

`services/artana_evidence_api/runtime_support.py` owns Artana store resolution.
If `ARTANA_STATE_URI` is unset, the service derives it from the configured
database URL and appends `search_path=artana,public`.

Run:

```bash
make init-artana-schema
```

before first local use of the Artana state store.

## Replay Policy

The current code uses explicit replay policies at model-step call sites. The
full AI orchestrator shadow planner uses `fork_on_drift` for planner
checkpointing. Health probes also use deterministic step keys and
`fork_on_drift`.

## Failure Behavior

If `artana-kernel` is unavailable, runtime code should fail clearly rather than
silently pretending model/tool state is durable. Some optional model features
fall back to deterministic extraction when `OPENAI_API_KEY` is not configured.
