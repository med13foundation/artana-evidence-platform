# PR152 Failed Model-Attempt Telemetry Validation

Date: 2026-07-13

Branch: `alvaro/evidence-pr152-failed-attempt-telemetry`

Base: merged PR150 commit `3d8e23e588206a4ef1cc46c1628fcbd0fa808da4`

## Root Cause

The PR150 repeatability run produced three schema-invalid model responses. The
exact execution path was:

1. `step_helpers.run_single_step_with_policy` called Artana's
   `SingleStepModelClient.step` with the registered semantic output schema.
2. Artana's `LiteLLMAdapter` received the provider response and extracted usage
   before calling `output_schema.model_validate_json`.
3. Pydantic rejected the output. The adapter re-raised a bare
   `ValidationError`, without attaching the already extracted response usage.
4. Artana's model cycle observed no `ModelResult`, then persisted a failed
   `model_terminal` event with latency, `error_category=internal`,
   `error_class=ValidationError`, and no token/cost values.
5. The semantic diagnostic correctly caught the failure and emitted only
   categorical `invalid_agent` decisions. PR150's telemetry consumer retained
   outcome and latency but omitted failure fields and batch association, and it
   could derive absent cost from token pricing in other partial cases.

The first-principles fix is to join service-owned attempt identity with the
immutable Artana event ledger, preserve categorical failure facts, and make
missing provider usage an explicit fact rather than a value to reconstruct.

## Implementation

- Added a request-local semantic attempt recorder. It registers execution ID,
  deterministic batch SHA-256 identity, execution order, per-batch retry
  number, step key, source/search identity, and opaque record references before
  runtime setup can fail.
- Added typed local-validation failures for record coverage, evidence
  references, and service run identity. A completed terminal response can now
  be represented as locally rejected without changing the Artana outcome.
- Replaced terminal-only normalization with one immutable telemetry record per
  semantic attempt. Missing terminal events remain explicit attempts with
  `telemetry_collection/model_terminal_event_missing`.
- Bumped the changed comparison report envelope from v3 to v4 while retaining
  the unchanged frozen comparison protocol at v3, so old evidence is not
  silently reinterpreted under the new attempt schema.
- Added typed Artana failure classification. Pydantic terminal failures map to
  `output_schema_validation/schema_contract_rejected`; provider and runtime
  categories remain categorical.
- Removed all service-side token-pricing cost reconstruction. Token and cost
  values are copied only from Artana terminal fields and use
  `artana_model_terminal` provenance. Missing values carry typed unavailable
  reasons, including `artana_exception_did_not_preserve_provider_usage`.
- Expanded the attempt digest to cover execution/batch association, terminal
  event identity/hash, failure stage/cause, usage values, and provenance.
  Aggregates and availability status are recomputed from the locked attempts.
- Added deterministic summary counts and failed-attempt Markdown rendering.
  Model adoption remains inconclusive when runtime telemetry is incomplete.
- Kept agent outputs categorical, deterministic scoring unchanged, registered
  schema checks intact, frozen model identity intact, and source-lock/bundle
  verification unchanged.

## Validation

Focused semantic and repeatability unit/regression suite:

```text
84 passed
```

Isolated-Postgres Artana failure-path integration:

```text
2 passed
```

The integration test drives the real service helper, Artana single-step client,
kernel model cycle, Postgres event store, and telemetry consumer with a genuine
Pydantic rejection. A second Postgres test verifies exact complete usage
copying.

Static validation completed before the aggregate service gate:

```text
Focused Ruff: all checks passed
Evidence API mypy: no issues in 553 source files
Strict script mypy checks: all passed
```

Service-gate results:

- `make artana-evidence-api-service-checks`: passed, including lint, mypy,
  boundary, contract, agent-output, baseline, architecture, and the full
  migrated isolated-Postgres Evidence API suite.
- `make service-checks`: passed. Graph and Evidence API checks, generated
  contracts, migrated test suites, and the coverage gate passed at `87.43%`
  against the required `86%`.

## Tamper And Rendering Coverage

- Changing batch identity, failure stage, failure cause, or unavailable-usage
  reason without recomputing the attempt digest is rejected.
- Forging token, cost, latency, provenance, or unavailable-reason aggregates is
  rejected even when the envelope remains structurally valid.
- The comparison renderer lists failed and locally rejected attempts with
  execution ID, batch ID, status, typed stage/cause, and explicit token/cost
  availability.

## Remaining Upstream Limitation

Artana's current adapter does not attach response usage to Pydantic validation
exceptions. Once that bare exception reaches the kernel, the original provider
usage is unavailable to this service. PR152 exposes the limitation with a typed
reason and never estimates the missing values. Artana/LiteLLM provider retries
also remain one terminal model cycle rather than separately queryable provider
sub-attempts.

This limitation affects resource accounting completeness only. It does not
weaken schema validation or permit failed output adoption: the model comparison
continues to fail closed.
