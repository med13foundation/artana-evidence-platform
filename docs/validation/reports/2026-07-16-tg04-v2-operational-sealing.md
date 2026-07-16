# TG-04 v2 Operational Sealing

## Purpose

This change makes the frozen 40-case TG-04 run observable when a
representability-stress case cannot be source-bound after the production
inventory schema retry. It does not change scientific scoring, qualification
thresholds, model selection, graph projection, or persistence readiness.

## Categorical Outcomes

Each case has one deterministically checked outcome:

- `BOUND_OUTPUT`: the complete accepted inventory is nonempty and exactly
  matches the scored prediction.
- `NO_OUTPUT`: the complete accepted inventory is empty and exactly matches an
  abstaining prediction.
- `UNBINDABLE_OUTPUT`: a representability-stress case ends in one of the
  allowlisted provider-backed inventory failure prefixes below.

The evaluator derives `BOUND_OUTPUT` and `NO_OUTPUT` from accepted raw
inventory. It does not trust the report label.

## Sealable Failure Prefixes

Only these one-chunk inventory prefixes can continue as descriptive
`UNBINDABLE_OUTPUT`:

1. Primary inventory is schema- or semantic-invalid, followed by a failed
   schema retry of the same kind.
2. Primary inventory returns an accepted empty list, its schema retry is
   explicitly skipped, and the zero-candidate retry plus its schema retry are
   both schema- or semantic-invalid.

Every executed attempt must retain a canonical OpenAI response ID, provider
output hash, raw payload and payload hash, prompt hash, kernel run ID, source
hash, input hash, evidence-unit hash, and output-schema identity. The evaluator
reconstructs canonical production prompts and live-verifies all receipts.

Invocation, authentication, provider-identity, repository-drift, malformed
custody, completeness-stage, recovery-stage, and unexpected-topology failures
still abort without a sealed report.

## Qualification Boundary

`UNBINDABLE_OUTPUT` is accepted only for frozen
`REPRESENTABILITY_STRESS` cases. It is excluded from scientific quality and
repeatability metrics. An unbindable qualification case is rejected.

The existing qualification invariant remains strict: even a repaired
qualification output fails the operational gate when it contains a schema- or
semantic-invalid attempt. Fallback, unidentified provider attempts, incomplete
case coverage, duplicate case coverage, and unverified receipts also fail the
gate.

## Validation

- Focused n-ary runner, operational, evaluator, and production inventory tests:
  passed.
- Evidence API strict MyPy gate: passed.
- Validation-module MyPy with service source resolution: passed.
- `make service-checks`: passed.
- Independent adversarial design review: qualification-invalid preservation,
  outcome derivation, provider custody, and canonical-prefix requirements were
  incorporated before final validation.

## Next Stop/Go Step

After this change is reviewed and merged, run one separately identified Luna
operational pass over all 40 frozen cases. Continue to the three-Luna plus
three-Sol scientific matrix only if the operational artifact covers all 40
cases, has zero qualification invalid/unbindable outcomes, zero fallback,
zero unidentified provider attempts, and live-verified provider receipts.

Persistence remains blocked regardless of operational success. It can be
reconsidered only after the unchanged scientific gates qualify a model and the
held-out confirmation stage succeeds.
