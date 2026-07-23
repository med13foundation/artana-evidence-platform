# Staged Generalization V15 Exposed Gate

## Scientific hypothesis

`FOCUS_CLOSURE_AND_ROLE_BEARING_OCCURRENCE_CUSTODY_V1`: build the mandatory event graph from role-bearing occurrences in the focused finding. Outside context may resolve identity or a genuinely implicit or elliptical argument, but cannot add an outside predicate or replace an explicit focus-local occurrence. The frozen V14 participant-denotation rule is applied only after occurrence binding.

No evaluator, event inventory, entity type, mandatory participant or link, root-selection, semantic-axis, evidence-grounding, completeness, or BioNLP-CG projection rule changed.

## Exposed outcomes

- `generalization-comparison-canary`: source-semantic `PASS`, root `PASS`, raw BioNLP-CG `NOT_APPLICABLE`, failure `None`.
- `generalization-drug-sensitivity`: source-semantic `PASS`, root `PASS`, raw BioNLP-CG `PASS`, failure `None`.
- `generalization-uncertainty`: source-semantic `FAIL`, root `FAIL`, raw BioNLP-CG `NOT_APPLICABLE`, failure `UNRELATED_REGRESSION`.

First scientific failure: `UNRELATED_REGRESSION` at `generalization-uncertainty`. Execution stage `None`; diagnostics `{}`.

## Provider custody

Attempted `3`, completed `3`, admitted `3`, rejected `0`, retries `0`, duplicate creations `0`.

- `generalization-comparison-canary`: `ADMITTED_SCIENTIFIC_CUSTODY`, response IDs `['resp_0b925bd38372394c006a629816746c8198950e17903ce30f02']`, usage `{"cached_input_tokens":0,"cost_usd":0.010631,"input_tokens":4175,"latency_seconds":8.486940582995885,"output_tokens":1076,"reasoning_tokens":516,"total_tokens":5251}`.
- `generalization-drug-sensitivity`: `ADMITTED_SCIENTIFIC_CUSTODY`, response IDs `['resp_03e70ee30b77fa39006a62981e4a3c819bb7a8ba273ac7d248']`, usage `{"cached_input_tokens":0,"cost_usd":0.017386,"input_tokens":4162,"latency_seconds":18.575621666997904,"output_tokens":2204,"reasoning_tokens":1552,"total_tokens":6366}`.
- `generalization-uncertainty`: `ADMITTED_SCIENTIFIC_CUSTODY`, response IDs `['resp_0ce65718ea22f429006a629830cb38819baf516b6a07d95700']`, usage `{"cached_input_tokens":0,"cost_usd":0.028437,"input_tokens":4233,"latency_seconds":28.99031350000587,"output_tokens":4034,"reasoning_tokens":3624,"total_tokens":8267}`.

## Cost and stopping budget

Spend `$0.056454000000000004` of `$5.0`; remaining `$4.9435459999999996`; accounting `FULLY_ACCOUNTED`. Tokens, latency, and cost did not affect scientific scoring.

## Qualification state

Fresh cases consumed `0`; untouched `7`; graph writes `0`; trusted promotion `False`. V14 sealed `True`.

## Terminal decision

`V15_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION`
