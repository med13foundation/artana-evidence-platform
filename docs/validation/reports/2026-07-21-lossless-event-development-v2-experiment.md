# Lossless Scientific Event Development Experiment V2

**Decision:** `INVALID_EXPERIMENT`

This is a one-call exposed-development result. It does not qualify the sealed test split, graph writes, or trusted promotion.

## Integrity

- Preregistration: `6628957da82913d0be0bfacd4ba1f6d599356f5661216ba595101fd2f14f9db2`
- Provider retries: `0`
- Provider calls attempted: `1`
- Fallbacks and repairs: `0`
- Graph writes and promotions: `0`
- Sealed test sources accessed: `0`

The receipt failed before trustworthy usage accounting could be preserved.
Tokens, latency, and cost are therefore `UNVERIFIED_NOT_RECORDED`, not zero.

## Scientific Metrics

Complete-event, trigger, typed-role, nested-event, modifier, unsupported-event,
offset, reference, and cycle metrics were not computed. Scoring an output whose
provider receipt failed would make this invalid execution look scientifically
interpretable when it is not.

## Invalidating Failure

- Stage: `RECEIPT_OUTPUT`
- Root cause: created and retrieved provider outputs differ
