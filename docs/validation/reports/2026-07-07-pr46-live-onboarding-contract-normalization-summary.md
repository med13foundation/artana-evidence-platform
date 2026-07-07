# PR46 Live Onboarding Contract Normalization Summary

## Run Context

- Branch: `alvaro/evidence-pr46-live-onboarding-contract-normalization`
- Base branch: `alvaro/evidence-pr45-expert-source-export-writer`
- Scope: Evidence API onboarding-agent contract robustness

## Goal

Close the live-key aggregate gate blocker found during PR45 validation without
mixing the fix into the PR45 source-export writer slice.

## Root Cause

`make service-checks` runs real onboarding-agent integration tests when
`.env.postgres` provides an OpenAI API key. During PR45 validation, the model
returned an otherwise usable onboarding contract whose redundant
`pending_question_count` did not match the `pending_questions` list. The nested
`OnboardingStatePatch` validator rejected the payload before the runtime could
persist the onboarding turn.

The root problem was that the contract treated a model-authored derived count as
authoritative. The count should be derived from the normalized pending-question
list before nested validation, while still rejecting genuinely inconsistent
message states such as `review_needed` with open pending questions.

## Code Changes

- Normalized every `OnboardingAssistantContract` dict payload before nested
  state-patch validation.
- Derived `state_patch.pending_question_count` from normalized
  `state_patch.pending_questions` when the pending-question list is absent,
  empty, or a valid list of strings.
- Preserved the existing conversion of `plan_ready` outputs with top-level open
  questions into `clarification_request`.
- Rejected malformed pending-question payloads instead of filtering invalid
  items away.
- Kept fail-closed validation for `review_needed`/`plan_ready` outputs that
  retain valid pending questions without a top-level conservative downgrade.

## Validation

RED tests observed:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_research_onboarding_runtime.py \
  -q \
  -k "derives_clarification_pending_question_count or derives_plan_ready_pending_question_count"
```

Initial result: two failures, both from
`pending_question_count must match pending_questions length`.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_research_onboarding_runtime.py \
  services/artana_evidence_api/tests/unit/test_research_onboarding_agent_runtime.py \
  services/artana_evidence_api/tests/unit/test_output_schema_registry.py \
  -q
```

Result: `28 passed`.

```bash
set -a; source .env.postgres; set +a; \
uv run python scripts/run_isolated_postgres_tests.py \
  services/artana_evidence_api/tests/integration/test_research_onboarding_agent_runtime.py \
  -q -s
```

Result: passed against isolated Postgres.

```bash
uv run ruff check \
  services/artana_evidence_api/agent_contracts.py \
  services/artana_evidence_api/tests/unit/test_research_onboarding_runtime.py
```

Result: passed.

```bash
make artana-evidence-api-type-check
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed.

```bash
make service-checks
```

Result: passed with coverage `87.03%`.

## Interpretation

PR46 closes the immediate live-agent contract drift that blocked the aggregate
gate under a configured OpenAI key. It does not make onboarding content quality
claims; it only makes the contract boundary robust to a redundant count field
that should never override the actual pending-question list.
