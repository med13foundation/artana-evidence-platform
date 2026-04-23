# Strong Model Harnesses

Status date: April 23, 2026.

The main strong-model user in this repo is the full AI orchestrator shadow and
guarded planner path.

Primary file:

- `services/artana_evidence_api/full_ai_orchestrator_shadow_planner.py`

## Current Use

The planner builds checkpoint summaries, routes them through Artana model
execution, validates structured outputs, and falls back when model execution is
unavailable or invalid.

Guarded planner output is bounded. It can recommend or select from allowed
actions at specific checkpoints, but it must not bypass review or graph
governance.

## Model Configuration

Model capability defaults and health checks live in:

- `services/artana_evidence_api/runtime_support.py`

Without `OPENAI_API_KEY`, model health reports degraded or unknown and optional
model-backed steps use deterministic fallback where the runtime supports it.
