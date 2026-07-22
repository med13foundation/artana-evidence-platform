# Staged Luna Event Construction V3

## Decision

`INVALID_PROVIDER_EXECUTION`

V3 made exactly one inventory call. Stage 2 did not run. The response was
acknowledged and the verified receipt plus canonical typed payload were safely
preserved in the atomic custody bundle before the defect occurred.

## Root Cause

Custody readback used Python structural equality. JSON serialization correctly
converted receipt tuples to arrays, so the readback contained lists. Although
the canonical JSON content was equivalent, tuple-versus-list equality failed
and raised `CustodyPersistenceError`.

This is an isolated deterministic custody comparison defect. V3 remains
immutable and receives no scientific interpretation or benchmark score.

## Accounting

- Response ID: `resp_0318bce8f23c6172006a60f02ae04881998ef9903dab5b0548`
- Input tokens: 836
- Output tokens: 2,821
- Total tokens: 3,657
- Latency: 17.66 seconds
- Cost: $0.017762
- Provider retries: 0
- Stage 2 calls: 0

The correction for V4 is limited to comparing canonical JSON hashes after
readback and adding tuple-bearing receipt regression coverage. Prompts, schemas,
source, model, scientific gates, and anchor rules remain unchanged.
