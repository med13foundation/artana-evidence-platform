# Staged Generalization V17 Exposed Gate

## Scientific hypothesis

`INLINE_VERSUS_ANAPHORIC_SCOPE_BOUNDARY_V1`: retain a material inline restriction in the smallest complete participant span; do not decompose that inline text into an optional participant-scope node or link. Preserve V16's separately adjudicated handling of source-grounded anaphoric scope and partitives.

## Exposed outcomes

- `generalization-comparison-canary`: source-semantic `PASS`, V17 scope `True`, raw V16 `True`, raw BioNLP-CG `NOT_APPLICABLE`, failure `None`.
- `generalization-drug-sensitivity`: source-semantic `PASS`, V17 scope `True`, raw V16 `True`, raw BioNLP-CG `PASS`, failure `None`.
- `generalization-uncertainty`: source-semantic `FAIL`, V17 scope `False`, raw V16 `False`, raw BioNLP-CG `NOT_APPLICABLE`, failure `SOURCE_SEMANTICS`.

First scientific failure: `SOURCE_SEMANTICS` at `generalization-uncertainty`. Execution stage `None`; diagnostics `{}`.

## Provider custody

Attempted `3`, completed `3`, admitted `3`, rejected `0`, retries `0`, duplicate creations `0`.

- `generalization-comparison-canary`: `ADMITTED_SCIENTIFIC_CUSTODY`, response IDs `['resp_0ad0d3f92541e60d006a62e69227a08199b20dc9084b25da5f']`, usage `{"cached_input_tokens":0,"cost_usd":0.019902,"input_tokens":4878,"latency_seconds":19.59030808400712,"output_tokens":2504,"reasoning_tokens":1914,"total_tokens":7382}`.
- `generalization-drug-sensitivity`: `ADMITTED_SCIENTIFIC_CUSTODY`, response IDs `['resp_0a7e721d817c86c4006a62e6a51ecc819aba98d6cea8bf2681']`, usage `{"cached_input_tokens":0,"cost_usd":0.024293000000000002,"input_tokens":4865,"latency_seconds":23.495943917005206,"output_tokens":3238,"reasoning_tokens":2588,"total_tokens":8103}`.
- `generalization-uncertainty`: `ADMITTED_SCIENTIFIC_CUSTODY`, response IDs `['resp_07a605b176a537ba006a62e6bc6eb4819b88362b43439f9b6b']`, usage `{"cached_input_tokens":0,"cost_usd":0.015082,"input_tokens":4936,"latency_seconds":11.573403250004048,"output_tokens":1691,"reasoning_tokens":1034,"total_tokens":6627}`.

## Cost and stopping budget

Spend `$0.059276999999999996` of `$5.0`; remaining `$4.940723`; accounting `FULLY_ACCOUNTED`. Tokens, latency, and cost did not affect scientific scoring.

## Qualification state

Fresh cases consumed `0`; untouched `7`; graph writes `0`; trusted promotion `False`. Sealed V16 preserved `True`.

## Terminal decision

`V17_EXPOSED_GATE_FAIL_SOURCE_SEMANTICS`
