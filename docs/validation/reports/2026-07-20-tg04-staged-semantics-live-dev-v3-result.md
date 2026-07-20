# TG04 Staged Semantics Live Development V3 Result

Created: 2026-07-20

Decision: `BOUNDED_LIVE_DEVELOPMENT_PASSED`

V3 changed only the A2 evidence-span acceptance rule. It retained V2's exposed
source, model, reasoning effort, staged prompts, schemas, token ceilings,
scientific criteria, and conditional two-execution topology. Both executions
passed without a prompt, code, model, source, or gate change between them.

This is a bounded exposed-development pass. It is not an untouched-source or
broad scientific-qualification result.

## Frozen Controls

- Model: `openai:gpt-5.6-sol`
- Reasoning effort: `high`
- Source: exposed development source `pubmed:40289860`
- Source SHA-256:
  `e933d6dbc1e7599e41e093c5ad321131572ccdaddf871c8b610749519fe5ef84`
- Event-scope SHA-256:
  `0f37ff7c0b0f1201f3ee7a849f54d8ba89b7db94276b6d0d8e3411328b4ff66e`
- Frozen V2 code tree SHA-256:
  `cdaad7672181ddb791c5859cfefbc374766324f5130de48d1c0bc9de1ccfdee6`
- Frozen V2 prompts SHA-256:
  `4089cc618d969c81dd30ae4b2fad089b22b8a27b2e591928902d1459ef76c6f3`
- Frozen V10 tree SHA-256:
  `bb0b66e96646040717b3d7eaea3b062eb3ebe4bf654119aca16e54d7550abc7a`
- Corrected-checkpoint tree SHA-256:
  `71cc71c6aa23c0805739efd0d83c64f7958df89ea6df6f134a0d047d56fba73a`
- Execution repository commit:
  `7cf9b01c9966af3db778bdc0bcacd78222a9d88f`
- Preregistration SHA-256:
  `5145d7afc9bbd7b0d379134425eca258b43613332f81ae8dd16ae52309cb8964`
- Execution-lock SHA-256:
  `ad6735cbf58e1e4516beedef966794c0dc0b6e942caec19d8a597643d13b0766`
- Result SHA-256:
  `91d85ef3e7a775049d4274e5581a3b29e9941dcfbd3ff1d738c6e127945a314b`
- Internal canonical report SHA-256:
  `7614576b520cf295cba3d35402e6548632669cd2550fe8998b9c977e52d08b32`

## Single Policy Change

V2 required A2 comparison evidence to equal this literal string:

`had more comorbidities than`

V3 accepts a returned evidence interval only when deterministic checks prove:

1. the returned text resolves to exact source character offsets;
2. the required cue resolves to exact source character offsets;
3. both intervals belong to the same `A2` atomic event scope;
4. the returned evidence interval contains the required cue interval; and
5. the returned interval does not overlap a predeclared contradictory interval.

The validator compares offsets and scope identity only. It does not infer
comparison direction, polarity, contradiction, or any biomedical meaning.

## Offline Evidence

Before freezing V3:

- the full A2 event sentence containing the cue passed;
- abstract-wide evidence failed;
- A5 evidence submitted for A2 failed;
- A2 evidence missing the required cue failed;
- evidence overlapping a caller-declared contradictory interval failed;
- V2's staged prompt file remained byte-identical;
- strict Ruff and mypy passed;
- 115 combined scientific regression tests passed; and
- `make service-checks` passed at 87.48% coverage.

## Live Execution

| Execution | Calls | Tokens | Cost USD | Events | Stages | Local roles | Unsupported | Contradictions |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 6 | 11,328 | 0.124815 | 2/2 | 12/12 | 6/6 | 0 | 0 |
| 2 | 6 | 11,203 | 0.121915 | 2/2 | 12/12 | 6/6 | 0 | 0 |
| **Total** | **12** | **22,531** | **0.246730** |  |  |  |  |  |

All 12 calls had:

- one verified-live provider receipt;
- a unique provider response ID;
- `replayed = false`;
- no retry; and
- per-call and per-execution token usage below the frozen ceilings.

There were zero fallbacks, graph writes, untouched-source operations, and
frozen V10 changes.

## Scientific Result

Both executions preserved A2 as:

- result state: `OBSERVED_DIFFERENCE`;
- direction: `HIGHER`;
- operator: `GREATER_THAN`; and
- returned evidence: the complete local event sentence containing
  `had more comorbidities than`.

Both executions preserved A5 as:

- `log-rank P = 0.08` -> `P_VALUE`;
- `hazard ratio 0.92` -> `EFFECT_ESTIMATE`;
- `95% confidence interval 0.78-1.09` -> `CONFIDENCE_INTERVAL`; and
- author claim -> `NOT_CLAIMED` with no author-claim evidence.

Both executions also preserved all six event-local participant anchors and
received `ENTAILED / COMPLETE_FOR_ASSERTION` source-only reviews.

## Repeatability

- Categorical-stage match: `true`
- Complete-event match: `true`
- Shared categorical-stage SHA-256:
  `c0d2a2eda5f83ae09e5e6d876dacc78ca5f0bd3313c4f3a71a6ed62efb35a477`
- Shared complete-event SHA-256:
  `9524224bfe1e4f5ec6a6dbf3c4860327cfb6ea0e97e5843162d62f791edf2cd2`

Free-text explanations varied slightly, as permitted. Scientific categories,
exact evidence, roles, offsets, measurements, epistemic status, and review
outcomes were identical under the deterministic signatures.

## Conclusion

V3 proves that event-local interval containment removes V2's false rejection
without weakening scientific or provenance gates on this exposed source. The
two prior live failure families remain corrected, and the complete staged event
was repeatable across two independent executions.

The result does not establish generalization to unseen literature. Any next
experiment should remain separately preregistered and should test this frozen
architecture on a new development or untouched source only with explicit
authorization.
