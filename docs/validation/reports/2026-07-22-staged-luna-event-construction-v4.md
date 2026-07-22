# Staged Luna Event Construction V4

## Decision

`INVALID_PROVIDER_EXECUTION`

V4 made exactly one Luna-high inventory call. The provider receipt was rejected
at the output-token budget boundary before custody or scientific scoring. Stage
2 did not run.

## Failure

- Response ID: `resp_0849ac0e3cd34e45006a60f0ecae3c819b82c696cf0d99d705`
- Requested maximum output tokens: 16,000
- Observed output tokens: 18,778
- Input tokens: 836
- Total tokens: 19,614
- Latency: 191.60 seconds
- Cost: $0.113504
- Output-token boundary: `FAIL`
- Total-token, latency, and cost boundaries: `PASS`
- Retries and duplicate creation calls: 0

No scientific metrics were calculated. The rejected output is not reinterpreted
and does not answer whether Luna found the intermediate event.

This is not an isolated deterministic runner defect. The provider exceeded the
same explicit output-token ceiling despite the request carrying that ceiling,
and Source-First V1 previously showed the same provider behavior. The bounded
self-healing rules prohibit further automatic calls for repeated provider
budget violations.
