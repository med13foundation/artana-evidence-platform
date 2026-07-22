# Lossless Scientific Event Development Experiment V4

**Decision:** `INVALID_EXPERIMENT`

This is a one-call exposed-development result. It does not qualify the sealed test split, graph writes, or trusted promotion.

## Integrity

- Preregistration: `023768cdc0d4523c58d160073c76bc5dc36ee2cc00bcc441147caee53c5c994c`
- Frozen state: `d3e0031abfbcb56b6b9cde0b9a0e66875c47b668f1f9aae2dc44662eb2fecc51`
- Selected exposed source: `PMID-16428936`
- Selected source SHA-256: `00da32aa63d3aa0f48d3c02f806e8db9ca2cd10bda0357280674a188a04523ab`
- External authorization was applied without changing the immutable V4 file.
- Provider creation calls: `1`
- Provider retries: `0`
- Duplicate creation calls: `0`
- Fallbacks and repairs: `0`
- Graph writes and promotions: `0`
- Sealed test sources accessed: `0`

## Provider Execution

- Response ID: `resp_0dc68e743f3173d3006a600bc344a0819a99e4da5c2142e67b`
- Requested and validated model: `gpt-5.6-sol`
- Acknowledgement: valid response ID received within the frozen 30-second gate
- Terminal state: `completed` before receipt topology validation
- Polling retrieval requests: `58`
- Confirmation retrieval requests: `1`
- Input-item retrieval requests: `1`
- Exact status history: unavailable because the invalid receipt artifact did not serialize it
- Tokens, latency, and cost: unavailable because strict receipt validation failed before verified accounting was serialized; these values are not reported as zero

## Invalidating Failure

- Stage: `RECEIPT_OUTPUT_TOPOLOGY`
- Root cause: multiple reasoning items are unsupported
- The canonical structured payload passed discovery and creation-versus-retrieval equality before this failure.
- Completed and confirmation output hashes were both `b5b2280a9c7653dbf08aff783bbff7ce8dc6ba5e3fc224246049a7fe1aaf42df`.
- The failing topology rule accepts at most one provider `reasoning` item. This high-reasoning response contained multiple reasoning items.

## Scientific Result

Scientific schema assembly, offset validation, reference validation, and scoring
were not reached. Complete-event recovery, trigger recovery, role fidelity,
nested-event recovery, modifier fidelity, missing events, and unsupported events
are therefore **withheld**, not zero.

## Conclusion

The asynchronous transport solved the original untraceable synchronous timeout:
one provider response was acknowledged, polled, and completed without duplicate
creation. V4 is nevertheless invalid because the receipt topology contract does
not support a legitimate multi-item reasoning envelope. This experiment cannot
say whether the model's scientific extraction was good or bad.
