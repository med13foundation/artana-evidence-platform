# Staged Generalization V11 Exposed Run 2

## 1. Operational root cause and transport

Run 1 classification: `PROVIDER_QUEUE_STALL`. Run 2 transport: `DIRECT_OPENAI_FOREGROUND_RESPONSES`.

## 2. Report-generation correction

Invalid reports now preserve the preregistered scientific context. Correction artifact: `70441b474ffbcd96a7d48c0862a835ea4445bb82d2b73dc26e12efd2b51154da`.

## 3. Preserved scientific contract

Preregistered root cause: `SEMANTIC_EVIDENCE_PROMPT_CONTRACT_GAP`. Frozen V11 change: `UNIQUE_COMPLETE_SEMANTIC_EVIDENCE_GROUNDING`. The run did not scientifically validate either the preregistered root-cause hypothesis or the frozen V11 change.

## 4. Exposed/public case outcomes

- `generalization-comparison-canary`: grader `True`, V11 run-2 gate `True`, failure `None`.
- `generalization-uncertainty`: grader `True`, V11 run-2 gate `True`, failure `None`.
- `generalization-negated-association`: grader `True`, V11 run-2 gate `True`, failure `None`.
- `generalization-null-statistics`: grader `True`, V11 run-2 gate `True`, failure `None`.
- `generalization-drug-sensitivity`: grader `False`, V11 run-2 gate `False`, failure `UNRELATED_SCIENTIFIC_REGRESSION`.

## 5. SLC12A3 boundary

Corrected to the exact occurrence: `True`.

## 6. Semantic grounding

All admitted semantic evidence unique: `True`. Negated complete sentence observed: `True`.

## 7. V9 and V10 regressions

`{'v9_regressed_fields': [], 'v9_count_regressions': ['unsupported_claim_count'], 'v10_regressed_fields': [], 'v10_count_regressions': []}`

## 8. Provider execution and cumulative budget

`{'provider_calls': 8, 'transport_qualification_provider_calls': 3, 'scientific_provider_calls': 5, 'provider_retries': 0, 'duplicate_creation_calls': 0, 'input_tokens': 18471, 'cached_input_tokens': 2710, 'output_tokens': 12609, 'reasoning_tokens': 8524, 'total_tokens': 31080, 'latency_seconds': 111.61969845898025, 'cost_usd': 0.09168600000000002, 'remaining_cost_usd': 4.908314}`

## 9. Fresh-case accounting

Fresh cases consumed: `0`. Untouched fresh cases preserved: `7`.

## 10. Graph and promotion state

Graph writes: `0`. Trusted promotion: `False`.

## 11. Execution validity and frontier

Failure stage: `None`. Failed case: `generalization-drug-sensitivity`. First scientific failure: `UNRELATED_SCIENTIFIC_REGRESSION`.

## 12. Terminal decision

`V11_EXPOSED_RUN_V2_FAIL_UNRELATED_REGRESSION`
