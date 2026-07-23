# Staged Generalization V14 Exposed Gate

## Scientific change

`COMPLETE_PARTICIPANT_DENOTATION_V1`: retain the entity-denoting noun head and restrictive identity unless the retained span independently denotes the same participant. No event, role, root, axis, grounding, completeness, or CG rule changed.

## V14-local evaluator correction

At most one independently adjudicated, source-entailed redundant inner causal-agent edge may be normalized in the source lane. It cannot replace a mandatory link. Raw BioNLP-CG projection remains unchanged and review-only.

## Exposed outcomes

- `generalization-comparison-canary`: source `PASS`, root `PASS`, optional edge accepted `0`, raw CG `NOT_APPLICABLE`, failure `None`.
- `generalization-drug-sensitivity`: source `FAIL`, root `PASS`, optional edge accepted `0`, raw CG `FAIL`, failure `UNRELATED_REGRESSION`.

First failure: `UNRELATED_REGRESSION` at `generalization-drug-sensitivity`. Execution stage `None`; root cause `None`; diagnostics `{}`.

## Provider custody

Attempted `2`, completed `2`, admitted `2`, rejected `0`, retries `0`, duplicate creations `0`.

- `generalization-comparison-canary`: `ADMITTED_SCIENTIFIC_CUSTODY`, response IDs `['resp_02eb2181aabaa82d006a62853f217c8199b9cee82a1fadd0f9']`, usage `{"cached_input_tokens":0,"cost_usd":0.010085,"input_tokens":3683,"latency_seconds":8.623367291991599,"output_tokens":1067,"reasoning_tokens":516,"total_tokens":4750}`.
- `generalization-drug-sensitivity`: `ADMITTED_SCIENTIFIC_CUSTODY`, response IDs `['resp_0c79751001b34970006a628546fc90819b96edfcb65ddfec6e']`, usage `{"cached_input_tokens":0,"cost_usd":0.062854,"input_tokens":3670,"latency_seconds":71.88364000000001,"output_tokens":9864,"reasoning_tokens":8545,"total_tokens":13534}`.

## Cost and stopping budget

Spend `$0.07293899999999999` of `$5.0`; remaining `$4.927061`; accounting `FULLY_ACCOUNTED`. Tokens, latency, and cost did not affect scientific scoring.

## Qualification state

Fresh cases consumed `0`; untouched `7`; graph writes `0`; trusted promotion `False`. V13 sealed `True`.

## Terminal decision

`V14_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION`
