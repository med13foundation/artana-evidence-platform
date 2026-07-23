# Staged Generalization V13 Exposed Gate

## 1. Adjudicated root cause

`COMPOSITIONAL_FOCUS_ROOT_AMBIGUITY`.

## 2. Scientific change

`COMPOSITIONAL_FOCUS_ROOT_SELECTION`; inventory, links, semantic fields, and the frozen grader were not relaxed. V12 drug source metrics were reused unchanged; V13's versioned decision policy makes the review-only CG metric nonblocking.

## 3. Nested source-semantic lane

Nested source lane: `FAIL`.

## 4. Exact BioNLP-CG projection lane

Nested benchmark projection: `FAIL` over `EXACT_CG_ROOT_DEPENDENCY_CHAIN`. Full-focus CG measurement: `NOT_MEASURED_UNREPRESENTABLE`. The official additional focus event is E28 `Infection`; V9 cannot represent `INFECTION`, `CELL`, or `ORGANISM`. This lane is review-only and cannot fail source-scientific qualification.

## 5. Exposed case outcomes and first frontier

- `generalization-comparison-canary`: source-scientific pass `True`, root selection `PASS`, completeness `COMPLETE`, source `PASS`, review-only benchmark projection `NOT_APPLICABLE` (`NOT_APPLICABLE`), full-focus CG `NOT_APPLICABLE`, failure `None`.
- `generalization-drug-sensitivity`: source-scientific pass `True`, root selection `PASS`, completeness `COMPLETE`, source `PASS`, review-only benchmark projection `PASS` (`DRUG_FOCUS_EVENT`), full-focus CG `NOT_APPLICABLE`, failure `None`.
- `generalization-explicit-nested-cause`: source-scientific pass `False`, root selection `PASS`, completeness `COMPLETE`, source `FAIL`, review-only benchmark projection `FAIL` (`EXACT_CG_ROOT_DEPENDENCY_CHAIN`), full-focus CG `NOT_MEASURED_UNREPRESENTABLE`, failure `SOURCE_SEMANTICS`.

First scientific failure: `SOURCE_SEMANTICS` at `generalization-explicit-nested-cause`. Execution failure stage: `None`; root cause: `None`; diagnostics: `{}`.

## 6. Evaluator and frozen grader

Provider-called `3` of `6` cases; scientifically evaluated `3`; called but unevaluated `[]`; admitted evaluations persisted: `True`.

## 7. Exactly-once provider evidence

Attempted `3`, completed `3`, admitted `3`, rejected `0`, unaccounted `0`; retries `0`, duplicate creations `0`, receipts valid `True`.

## 8. Usage, latency, and spend

Input `10161`, cached input `0`, output `10854`, reasoning `8530`, total `21015`, latency `82.33526566700311`, spend `$0.07528499999999999`; observed accounted spend `$0.07528499999999999`; accounting `FULLY_ACCOUNTED`.

- `generalization-comparison-canary`: status `ADMITTED_SCIENTIFIC_CUSTODY`, failure stage `None`, response IDs `['resp_0875074a6a3f8507006a62731cf75081988cc392798a295b16']`, usage `{"cached_input_tokens":0,"cost_usd":0.011300000000000001,"input_tokens":3392,"latency_seconds":10.304679249995388,"output_tokens":1318,"reasoning_tokens":764,"total_tokens":4710}`.
- `generalization-drug-sensitivity`: status `ADMITTED_SCIENTIFIC_CUSTODY`, failure stage `None`, response IDs `['resp_0b27f927fe225e28006a6273265f24819a8011b8e9b705f323']`, usage `{"cached_input_tokens":0,"cost_usd":0.019585,"input_tokens":3379,"latency_seconds":22.110360542006674,"output_tokens":2701,"reasoning_tokens":2070,"total_tokens":6080}`.
- `generalization-explicit-nested-cause`: status `ADMITTED_SCIENTIFIC_CUSTODY`, failure stage `None`, response IDs `['resp_081e85d75ba8b839006a62733c673c8199a0ed8c3d2b485af7']`, usage `{"cached_input_tokens":0,"cost_usd":0.044399999999999995,"input_tokens":3390,"latency_seconds":49.92022587500105,"output_tokens":6835,"reasoning_tokens":5696,"total_tokens":10225}`.

## 9. Operational budget

Limit `$5.0`; remaining `$4.924715`; exhausted `False`. Token count, answer length, latency, and cost did not affect scientific scoring.

## 10. Historical sealing

V12 remains sealed and diagnostic-only with zero retroactive credit: `True`.

## 11. Fresh-case accounting

Fresh cases consumed `0`; untouched fresh cases `7`; fresh qualification `PENDING_INDEPENDENT_REVIEW`; automatic draft generated `False`.

## 12. Graph and promotion state

Graph writes `0`; trusted promotion `False`.

## 13. Terminal decision

`V13_EXPOSED_GATE_FAIL_SOURCE_SEMANTICS`
