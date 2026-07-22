# Lossless Scientific Event Development Experiment V6

**Decision:** `INVALID_EXPERIMENT`

This is a one-call exposed-development result. It does not qualify the sealed test split, graph writes, or trusted promotion.

## Integrity

- Preregistration: `f022cd940fe8f1c6cbe6eedc0cd0822f4a626200a7db61f8e780745a0bfa2174`
- Provider retries: `0`
- Fallbacks and repairs: `0`
- Graph writes and promotions: `0`
- Sealed test sources accessed: `0`

## Invalidating Failure

- Stage: `RECEIPT_BUDGET`
- Root cause: cost ceiling exceeded

## Provider Record

The terminal provider response was retrieved read-only after V6 had already
stopped. Retrieval did not generate model output and does not make V6 valid.

- Response ID: `resp_0ee48be04b19c62a006a601f224098819a9b4e05f5f053ea0e`
- Provider status: `completed`
- Model: `gpt-5.6-sol`
- Input tokens: `1,794`
- Output tokens: `185,025`
- Reasoning tokens: `12,740`
- Total tokens: `186,819`
- Cost under the frozen pricing formula: `$5.55972`
- Frozen cost ceiling: `$5.00`
- Output topology: `25` reasoning items and `1` final message
- Polling retrieval requests: `43`
- Confirmation retrieval requests: `1`
- Input-item retrieval requests: `1`
- Provider creation calls: `1`
- Duplicate creation calls and retries: `0`

The official GPT-5.6 Sol price is `$5.00` per million input tokens, `$0.50`
per million cached input tokens, and `$30.00` per million output tokens. The
receipt's usage therefore represents a real budget breach, not a comparison or
rounding defect.

## Non-Qualifying Offline Replay

The preserved V6 payload was replayed locally through the exact live parser,
the V6 offset resolver, the lossless event representation, and deterministic
scoring. This diagnostic identifies later blockers without changing V6's
terminal decision.

- Canonical payload SHA-256: `5b9cd67abc6275d446893ff90d67de901198802fdd94a517495631c6e6a0051c`
- Predicted events: `33`
- Gold development events: `30`
- Offset corrections: `16`
- Maximum boundary correction: `2` characters
- Invalid offsets: `0`
- Unresolved references: `0`
- Cycles: `0`
- Complete exact events: `2/30`
- Exact triggers: `21/30`
- Typed arguments: `1/37`
- Nested arguments: `1/12`
- Correct modifiers: `0/2`
- Unsupported or invented exact events: `31`
- Unauthorized semantic mappings: `19`

These numbers are diagnostic only. Scientific metrics remain withheld from the
official V6 result because receipt qualification failed before scoring.

## Conclusion

V6 proves that the multi-item receipt topology and bounded exact-text offset
resolution no longer block structural validation. It remains invalid because
the high-reasoning Sol call exceeded the frozen cost ceiling by `$0.55972`.

More importantly, the preserved answer is scientifically far below the frozen
gate even after structural correction. Repeating the same call with a larger
budget would likely produce a validly measured failure, not solve extraction
quality. The next decision should therefore separate two goals: a new budgeted
run can close experiment-integrity bookkeeping, while improving scientific
quality requires changing the extraction approach and a new preregistered
comparison rather than retrying V6.
