# TG-04 V14 Completeness Visible Run: Controlled Stop

## Decision

`STOP_AND_RECALIBRATE`

This run produced no qualified scientific comparison. Arm A failed its frozen
local normalization contract after two of the five authorized calls, so arm C
was never authorized. The result receives zero scientific-improvement credit
and must not be used as trusted graph evidence.

## Custody

- execution commit: `4462b72f70b279675fdda6b70799f2c9125d1cfc`
- issued manifest:
  `00d12f4647f6dfc127e6a1b6650ca45443ae964e240783d20b47eae7bb2cf481`
- model identities:
  - report and policy: `openai:gpt-5.6-luna`
  - provider execution: `openai/gpt-5.6-luna`
  - provider receipt: `gpt-5.6-luna`
- journal:
  `/Users/alvaro/.codex/artana-evidence-experiments/tg04/v14-completeness-4462b72f/experiment.jsonl`
- reservation entry:
  `74ed33a7ea73310a4291d6ccb4795a95f84f81a1e2604d7f6809bad164a7e7ba`
- failed-A entry:
  `ef971a2b8308618ac3711934c287e6b355b576faef864a9ae850f50352fa9059`
- terminal entry:
  `05dc423e4702fbf0887dcdb11aea8158e99314dabd45f73322d640f1760a9600`
- A evidence:
  `a2c04e3fb8ae7ef6fe9dc4f1e6dcde5861a8fd7b844b8c9841db9e9ba308906a`

The journal is terminally sealed. This case must not be retried.

## Calls

| Call | Role | Local result | Provider response |
|---|---|---|---|
| 1 | primary | accepted | `resp_0fbbc1d8a90119a5006a5d4ce18ddc819b9903e543d2d1ed9b` |
| 2 | structure normalization | semantic invalid | `resp_023abbb73ebc5326006a5d4cf954208199b7130fd645489d1f` |

Calls 3 through 5 did not occur. Because A did not complete, provider receipt
retrieval and the A/C comparison did not occur.

## Exact Failure

Deterministic replay of the preserved normalization payload produced:

```text
StructuredModelSemanticError: UNCHANGED mapping altered the source event
```

The agent marked two mappings `UNCHANGED` while changing representation fields:

1. The localization target changed its local event ID, mention anchors, role
   rationales, and inventory rationale.
2. The activation target changed its local event ID, mention anchors, role
   rationale, and inventory rationale.

Those mappings were semantic preservations, but they were not representation
identity. Under the frozen contract they had to be `REFRAME`.

## Scientific Interpretation

The raw normalization payload represented all five source-explicit events:

- the cytoplasmic null result;
- RCC-S suppression of nuclear localization;
- the controlled localization target;
- RCC-S inhibition of activation; and
- the controlled activation target.

This is useful diagnostic evidence that the agent may recover the complete
scientific structure. It is not a qualified result because the procedural
mapping category failed before independent verification and receipt custody.

## Root-Cause Direction

`UNCHANGED` versus `REFRAME` is a deterministic representation comparison, not
a biomedical judgment. The next cycle should stop asking the agent to decide
that procedural label. The agent should return categorical source-to-event
mappings and explanations; deterministic code should derive `UNCHANGED` only
when the complete event representations are identical and `REFRAME` otherwise.

The next visible experiment must use a different preregistered source. This
consumed case may be used only as a visible regression fixture.
