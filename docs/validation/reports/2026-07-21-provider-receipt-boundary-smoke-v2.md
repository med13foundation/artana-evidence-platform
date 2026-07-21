# Provider Receipt Boundary Smoke V2

**Decision:** `RECEIPT_BOUNDARY_FAILED`

This was one non-scientific categorical provider call. It did not access biomedical sources, run the scientific experiment, write to the graph, or enable promotion.

## Custody

- Preregistration: `66c636677be212a9d4c64288f6f353058ede1d5bc5f70d89bee7da1998a532b7`
- Response ID: `UNVERIFIED`
- Provider creation calls: `1`
- Response retrieval requests: `0`
- Input-item custody retrieval requests: `0`
- Provider retries and fallbacks: `0`
- Biomedical sources accessed: `0`

## Failure

- Stage: `CREATION_SCHEMA`
- Domain: `TRANSPORT_METADATA`
- Root cause: creation response schema differs

The provider creation envelope returned an explicit top-level response-format
`description: null` that was absent from the frozen request-shaped format. The
difference is transport metadata. It does not change the strict JSON Schema,
expected category, expected explanation, model identity, or scientific content.
It was not allowlisted, so the boundary failed closed as preregistered.

The stop occurred before response retrieval, input-item retrieval, payload
comparison, and usage validation. Tokens, latency, and cost are therefore
`UNVERIFIED_NOT_RECORDED`, not zero.

### Redacted Diagnostics

```json
{
  "actual_schema_sha256": "f8bf8a3eb6d5797317c2c6b64027871c0fd87bf81162b7fe1fd34654b6d5a81e",
  "differences": [
    {
      "allowlisted": false,
      "creation_sha256": "03fd13e6a949d36ab7b4121c577068dde29655577ba3237e39e8ae1b938fdaca",
      "difference": "ADDED_ON_RETRIEVAL",
      "path": "$.description",
      "rationale": null,
      "retrieval_sha256": "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"
    }
  ],
  "expected_schema_sha256": "c7000a28e1f1165907a2f5914a71d41904cdc85cb76f018bad78c725dfcb0f38",
  "input_item_retrieval_requests": 0,
  "provider_calls": 1,
  "response_retrieval_requests": 0
}
```

## Validation Evidence

- Frozen executable commit: `de78524bee4a06bb0ec6d29ed8530a27dddd6e92`
- Focused receipt and preflight tests: `33 passed`
- Focused Ruff and strict MyPy: passed
- `make service-checks`: passed once after the executable correction
- Repository coverage: `87.62%`
- Scientific-development preregistration created: `no`

No scientific preregistration was created because the receipt boundary was not
live-validated. V2 is terminal and cannot be patched, retried, or reinterpreted.
