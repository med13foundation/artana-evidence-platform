# Staged Generalization V10 Exposed Run

## 1. Historical V9 reproducibility

V9 reproduces at its pinned commit. Current receipt code is isolated by the versioned provenance artifact and is not authorized to rewrite or rescore V9.

## 2. Exposed/public case outcomes

- `generalization-comparison-canary`: grader `True`, V10 gate `True`, failure `None`.
- `generalization-null-statistics`: grader `True`, V10 gate `True`, failure `None`.
- `generalization-negated-association`: grader `False`, V10 gate `False`, failure `UNRELATED_SCIENTIFIC_REGRESSION`.

## 3. SLC12A3 actual-call correction

`False`

## 4. Preserved and regressed V9 fields

- Preserved: `['comparison_fidelity', 'complete_event_recovery', 'direction_fidelity', 'exact_evidence_grounding', 'nested_event_structure', 'participant_role_fidelity', 'polarity_fidelity', 'required_core_complete', 'statistical_fidelity', 'uncertainty_fidelity']`
- Improved: `[]`
- Regressed: `['exact_evidence_grounding']`
- Count regressions: `[]`

## 5. Boundary versus unrelated failures

First failure classification: `UNRELATED_SCIENTIFIC_REGRESSION`.

## 6. Provider execution and budget

`{'provider_calls': 3, 'provider_retries': 0, 'duplicate_creation_calls': 0, 'input_tokens': 8184, 'cached_input_tokens': 0, 'output_tokens': 23765, 'reasoning_tokens': 5511, 'total_tokens': 31949, 'latency_seconds': 103.08140020699648, 'cost_usd': 0.15077400000000002, 'remaining_cost_usd': 4.849226}`

## 7. Optional consumed-case diagnostic

`SKIPPED_PUBLIC_GATE_FAILED`

## 8. Fresh-case accounting

Fresh cases consumed: `0`. Remaining preserved: `7`.

## 9. Graph and promotion state

Graph writes: `0`. Trusted promotion: `False`.

## 10. Terminal decision

`V10_EXPOSED_GATE_FAIL_MODEL_CORRECTION_REQUIRED`
