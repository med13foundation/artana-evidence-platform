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

- Added a request-local semantic attempt recorder as the sole execution-ID
  owner. It registers execution order and per-batch retry number before runtime
  setup can fail. Batch identity now fingerprints the complete governed context:
  objective, instructions, criteria, population, evidence types, outcomes,
  source/search identity, record indices, and record content.
- Added typed local-validation failures for record coverage, evidence
  references, and service run identity. A completed terminal response can now
  be represented as locally rejected without changing the Artana outcome.
- Replaced terminal-only normalization with one immutable telemetry record per
  semantic attempt. Missing terminal events remain explicit attempts with
  `telemetry_collection/model_terminal_event_missing`.
- Added a separately hashed attempted-execution manifest for every model run.
  Replay requires exact equality with the normalized ledger and rejects omitted,
  inserted, duplicated, non-contiguous, or per-batch-discontiguous attempts even
  when an attacker recomputes the ledger's inner digest.
- Bumped the frozen protocol to v4 and report envelope to v5. Adoption policy
  `1.3.0` allows zero failed, locally rejected, abandoned, or unobserved
  candidate attempts.
- Each terminal is joined to its referenced `MODEL_REQUESTED` event. Request
  event ID/hash/sequence, run, cycle, model, and step must agree with the
  terminal and frozen semantic attempt. The collector counts every request
  event in the execution and rejects extra/orphan cycles instead of filtering
  them away.
- Added typed Artana outcome classification. Pydantic terminal failures map to
  `output_schema_validation/schema_contract_rejected`; abandonment is distinct,
  and inconsistent outcome/category pairs are rejected.
- Removed all service-side token-pricing cost reconstruction. Token and cost
  values are copied only from Artana terminal fields and use
  `artana_model_terminal` provenance. Missing values carry typed unavailable
  reasons. Dimension-specific schema-exception reasons identify token usage and
  cost usage independently; timeouts and abandonment use generic
  terminal-missing usage reasons.
- Expanded the attempt digest to cover execution/batch association, terminal
  event identity/hash, failure stage/cause, usage values, and provenance.
  Aggregates and availability status are recomputed from the locked attempts.
- Added separate deterministic counts and rendering for confirmed failures,
  local rejections, abandonment, and telemetry-unavailable attempts.
- Moved attempt aggregation, digest, ordering, and availability policy out of
  `contracts.py` into the focused `repeatability.runtime` package. Manifest and
  ledger ordering now use one shared typed structural validator.
- Telemetry completeness is evaluated before retry reliability, so missing or
  unobserved candidate telemetry is always inconclusive.
- Kept agent outputs categorical, deterministic scoring unchanged, registered
  schema checks intact, frozen model identity intact, and source-lock/bundle
  verification unchanged.

## Validation

Focused semantic and repeatability unit/regression suite:

```text
113 passed
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
Evidence API mypy: no issues in 557 source files
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

- Attempt omission or insertion is rejected against the separately hashed
  attempted-execution manifest after inner digest and aggregate recomputation.
- Duplicate execution IDs, global sequence gaps, and per-batch numbering gaps
  are rejected during ledger validation.
- Request/terminal ID, hash, run, cycle, model, and step mismatches are rejected.
- An otherwise valid linked pair plus an orphan request event is rejected.
- Mixed schema-failure usage retains the available dimension and assigns a
  token-specific or cost-specific unavailable reason only to the missing one.
- Changing batch identity, governed-context digest, failure stage/cause, request
  identity, or unavailable-usage reason without recomputing the attempt digest
  is rejected.
- Forging token, cost, latency, provenance, or unavailable-reason aggregates is
  rejected even when the envelope remains structurally valid.
- The comparison renderer lists all non-completed attempts and keeps confirmed
  failure counts separate from telemetry-unavailable counts.

## Remaining Upstream Limitation

Artana's current adapter does not attach response usage to Pydantic validation
exceptions. Once that bare exception reaches the kernel, the original provider
usage is unavailable to this service. PR152 reserves typed, dimension-specific
token/cost usage-loss reasons for this proven path and never estimates the
missing values. Artana/LiteLLM provider retries
also remain one terminal model cycle rather than separately queryable provider
sub-attempts.

This limitation affects resource accounting completeness only. It does not
weaken schema validation or permit failed output adoption: the model comparison
continues to fail closed.
