# Luna Focused Context Experiment

**Decision:** `INVALID_EXPERIMENT`

This exposed-development result is non-qualifying and review-only.

```json
{
  "accounting": {
    "fallbacks": 0,
    "provider_creation_calls": 1,
    "provider_retries": 0,
    "receipts": [
      {
        "estimated_input_tokens": 11268,
        "input_token_estimation_method": "ceil(utf8_bytes/4)",
        "provider_input_bytes": 45071,
        "provider_input_sha256": "7456aea40f0afb662ad06ad09be2b68aa62040461bfe6f2f331fb1cc070c514a",
        "response_id": "resp_0909915ba5830325006a60620dbff88198adf8625d389c717e",
        "stage": "participants",
        "status": "REJECTED_BUDGET",
        "usage": {
          "cached_input_tokens": 0,
          "cost_usd": 1.8716730000000001,
          "input_tokens": 12153,
          "latency_seconds": 148.9371607080102,
          "output_tokens": 309920,
          "reasoning_tokens": 17023,
          "total_tokens": 322073
        }
      }
    ],
    "terminal_violation": "participants: total token ceiling exceeded",
    "total_cost_usd": 1.8716730000000001,
    "total_latency_seconds": 148.9371607080102,
    "total_tokens": 322073
  },
  "baseline_score": null,
  "failure": {
    "boundary": "RECEIPT_BUDGET",
    "diagnostics": {
      "actual_sha256": "7d0ee7aab504fb7e1922617aa2045382f84ea51f162d9db06ab23818a0fe65ee",
      "confirmation_retrieval_requests": 1,
      "differences": [
        {
          "actual_sha256": "7d0ee7aab504fb7e1922617aa2045382f84ea51f162d9db06ab23818a0fe65ee",
          "difference": "VALUE_CHANGED",
          "expected_sha256": "6ce318969619d1c360b6144be09e3d3a22674897c7cbfe995716ed8b7ff7c4cf",
          "path": "$.usage.total_tokens"
        }
      ],
      "duplicate_creation_calls": 0,
      "estimated_input_tokens": 11268,
      "expected_sha256": "6ce318969619d1c360b6144be09e3d3a22674897c7cbfe995716ed8b7ff7c4cf",
      "input_item_retrieval_requests": 1,
      "input_token_estimation_method": "ceil(utf8_bytes/4)",
      "model_generation_calls": 1,
      "observed_usage": {
        "cached_input_tokens": 0,
        "cost_usd": 1.8716730000000001,
        "input_tokens": 12153,
        "latency_seconds": 148.9371607080102,
        "output_tokens": 309920,
        "reasoning_tokens": 17023,
        "total_tokens": 322073
      },
      "polling_retrieval_requests": 28,
      "provider_creation_calls": 1,
      "provider_input_bytes": 45071,
      "provider_input_sha256": "7456aea40f0afb662ad06ad09be2b68aa62040461bfe6f2f331fb1cc070c514a",
      "provider_retries": 0,
      "receipt_status": "REJECTED_BUDGET",
      "response_id": "resp_0909915ba5830325006a60620dbff88198adf8625d389c717e",
      "stage": "participants"
    },
    "root_cause": "total token ceiling exceeded",
    "stage": "participants"
  },
  "final_score": null,
  "mechanical_metrics": null
}
```

## Compact-context result

- V1 participant input: `483,322` bytes.
- V2 participant input: `45,071` bytes.
- Reduction: `438,251` bytes (`90.68%`).
- Deterministic estimate: `11,268` input tokens using `ceil(utf8_bytes/4)`.
- Provider-observed input: `12,153` tokens; cached input: `0`.

## Execution result

- Provider creation calls: `1`.
- Provider retries, fallbacks, and duplicate creation calls: `0`.
- Accepted scientific stages: `0/4`.
- Provider-observed output tokens: `309,920`, including `17,023` reasoning tokens.
- Total tokens: `322,073`, above the frozen `300,000` aggregate ceiling.
- Latency: `148.9371607080102` seconds.
- Calculated cost: `$1.8716730000000001`.
- Receipt status: `REJECTED_BUDGET`.
- Response ID: `resp_0909915ba5830325006a60620dbff88198adf8625d389c717e`.

The compact packaging correction succeeded, but the provider response still exceeded
the frozen experiment budget during the first participant stage. The structured
scientific output was therefore not admitted or scored, and roles, modifiers, and
verification were never called. There are no valid before/after scientific metrics or
wrong-to-correct transitions to report.

This final prompt-and-context experiment remains terminally `INVALID_EXPERIMENT`.
It does not establish that Luna's biomedical reasoning improved or regressed. The next
scientific architecture should use a specialized biomedical event extractor only as a
recall and structure candidate generator, with Luna retaining source-only categorical
adjudication. No further prompt expansion is justified by this experiment.
