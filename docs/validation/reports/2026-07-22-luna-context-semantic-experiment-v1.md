# Luna Focused Context Experiment

**Decision:** `INVALID_EXPERIMENT`

This exposed-development result is non-qualifying and review-only.

```json
{
  "accounting": {
    "fallbacks": 0,
    "provider_creation_calls": 1,
    "provider_retries": 0,
    "receipts": [],
    "terminal_violation": "participants total token ceiling exceeded before receipt admission",
    "total_cost_usd": "UNVERIFIED",
    "total_latency_seconds": "UNVERIFIED",
    "total_tokens": "UNVERIFIED"
  },
  "baseline_score": null,
  "failure": {
    "boundary": "RECEIPT_BUDGET",
    "diagnostics": {
      "actual_sha256": "7482a54b7032de7a7802a28dc4a6f5aebd60e09f656bb49d5702e5a1f6aa50a9",
      "confirmation_retrieval_requests": 1,
      "differences": [
        {
          "actual_sha256": "7482a54b7032de7a7802a28dc4a6f5aebd60e09f656bb49d5702e5a1f6aa50a9",
          "difference": "VALUE_CHANGED",
          "expected_sha256": "6ce318969619d1c360b6144be09e3d3a22674897c7cbfe995716ed8b7ff7c4cf",
          "path": "$.usage.total_tokens"
        }
      ],
      "duplicate_creation_calls": 0,
      "expected_sha256": "6ce318969619d1c360b6144be09e3d3a22674897c7cbfe995716ed8b7ff7c4cf",
      "input_item_retrieval_requests": 1,
      "model_generation_calls": 1,
      "polling_retrieval_requests": 19,
      "provider_creation_calls": 1,
      "provider_retries": 0,
      "response_id": "resp_0899fdc890331ea0006a605966adcc81989ad977f88be5a9a2"
    },
    "root_cause": "total token ceiling exceeded",
    "stage": "participants"
  },
  "final_score": null,
  "mechanical_metrics": null
}
```

## Plain-language conclusion

The deterministic preflight passed, and the provider accepted exactly one Luna/high
creation request. The participant-inventory call then exceeded the frozen total-token
ceiling before its structured output could be admitted. The experiment stopped before
roles, modifiers, or verification, so it produced no valid scientific comparison.

This is an execution-budget failure, not evidence that Luna either improved or failed
the biomedical events. Exact tokens, latency, and cost were not preserved at the failing
boundary and are therefore reported as `UNVERIFIED`, never as zero. No retry, fallback,
untouched source, graph write, or promotion occurred.
