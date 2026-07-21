# Lossless Scientific Event Development Experiment V3

**Decision:** `INVALID_EXPERIMENT`

This is a one-call exposed-development result. It does not qualify the sealed test split, graph writes, or trusted promotion.

## Integrity

- Preregistration: `a39c08b789f65031617d682aed55a7d9fa0f5d5ceb5929524e2db50bb2388387`
- Provider retries: `0`
- Fallbacks and repairs: `0`
- Graph writes and promotions: `0`
- Sealed test sources accessed: `0`

## Invalidating Failure

- Stage: `PROVIDER_CALL`
- Root cause: APITimeoutError

The one provider creation request timed out before a completed response was
returned. Fail-fast execution stopped before response retrieval, input-item
retrieval, receipt verification, structured-output validation, or scientific
scoring.

## Provider Accounting

- Provider creation calls attempted: `1`
- Provider retries, fallbacks, and alternate models: `0`
- Response retrieval requests: `0`
- Input-item retrieval requests: `0`
- Response ID: `UNVERIFIED_NOT_AVAILABLE`
- Provider model returned: `UNVERIFIED_NOT_AVAILABLE`
- Tokens: `UNVERIFIED_NOT_RECORDED`
- Latency: `UNVERIFIED_NOT_RECORDED`
- Cost: `UNVERIFIED_NOT_RECORDED`
- Raw provider output: `NOT_AVAILABLE`

Unavailable accounting is intentionally not reported as zero.

## Scientific Metrics

Scientific metrics were withheld because no verified provider response or
structurally valid event document existed. Complete-event recovery, trigger
recovery, typed roles, nested references, modifiers, unsupported events,
missing events, offsets, references, cycles, and semantic mappings are all
`NOT_EVALUATED`.

## Conclusion

The deterministic preflight passed, but V3 is not a valid scientific-quality
measurement. This result identifies a provider-call timeout, not evidence that
the model succeeded or failed at scientific event extraction. V3 is terminal:
it was not retried, repaired, reinterpreted, or run on another source.
