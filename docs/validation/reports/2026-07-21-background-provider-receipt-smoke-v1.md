# Background Provider Receipt Smoke V1

**Decision:** `BACKGROUND_TRANSPORT_VALIDATED`

This was one tiny non-scientific background response. No biomedical source, scientific experiment, graph write, or promotion was used.

## Integrity

- Preregistration: `04259f8fab82755738207189b4d579d339808ee33b20da9e910ac634f6fc9e5d`
- Smoke executions: `1 of 2 allowed`
- Provider creation calls: `1`
- Model-generation calls: `1`
- Polling retrieval requests: `1`
- Confirmation retrieval requests: `1`
- Input-item retrieval requests: `1`
- Provider retries and duplicate creation calls: `0`

## Accounting

- Total tokens: `132`
- Latency seconds: `8.394585250003729`
- Cost USD: `0.0012100000000000001`
- Status history: `['queued', 'completed']`
- Response ID: `resp_0fd479fc75226c82006a600691b668819a87ea2db3dabfcec6`

## Repository Validation

- Focused transport, polling, receipt, smoke, and preregistration tests: passed
- Focused Ruff and strict MyPy: passed
- `make service-checks`: passed once after the live smoke
- Coverage: `87.62%` (required: `86%`)

No scientific provider call was made. Scientific development V4 is frozen
separately and remains unauthorized pending explicit approval.
