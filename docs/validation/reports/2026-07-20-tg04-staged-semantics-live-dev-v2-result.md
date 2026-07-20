# TG04 Staged Semantics Live Development V2 Result

Created: 2026-07-20

Decision: `BOUNDED_LIVE_DEVELOPMENT_FAILED_STOP`

Execution 1 completed six live agent calls and then failed one frozen
deterministic acceptance criterion. Execution 2 was not authorized and was not
run. No prompt, schema, code, source, model setting, or gate was changed after
preregistration. There was no patch or retry inside the experiment.

## Frozen Controls

- Model: `openai:gpt-5.6-sol`
- Reasoning effort: `high`
- Source: exposed development source `pubmed:40289860`
- Source SHA-256:
  `e933d6dbc1e7599e41e093c5ad321131572ccdaddf871c8b610749519fe5ef84`
- Event-scope SHA-256:
  `0f37ff7c0b0f1201f3ee7a849f54d8ba89b7db94276b6d0d8e3411328b4ff66e`
- Corrected-checkpoint tree SHA-256:
  `71cc71c6aa23c0805739efd0d83c64f7958df89ea6df6f134a0d047d56fba73a`
- Frozen V10 tree SHA-256:
  `bb0b66e96646040717b3d7eaea3b062eb3ebe4bf654119aca16e54d7550abc7a`
- Execution repository commit:
  `cdfcd03a5fd0cfcdd7f31ef23882258f757b3fe2`
- Preregistration SHA-256:
  `a782f449f2775d25b4fcfa7f7a98a789728bb9a53e3c442ed2cca041a3fdfffd`
- Execution-lock SHA-256:
  `c5789142b00942b8784b873e6d0dbd7209c9035f2a08c242a75e6ce49028876e`
- Result SHA-256:
  `966341847774d68319b09c86c9d7c39cb899b44faddf61f012d6f52cd121be9f`

## Actual Execution

Every call had one verified-live OpenAI receipt, a unique provider response ID,
and `replayed = false`.

| Stage | Status | Input tokens | Output tokens | Total tokens | Cost USD |
|---|---|---:|---:|---:|---:|
| Core event and local roles | Passed | 1,105 | 712 | 1,817 | 0.026885 |
| Comparison and direction | Passed | 1,155 | 312 | 1,467 | 0.015135 |
| Quantitative measurements | Passed | 1,235 | 456 | 1,691 | 0.019855 |
| Statistical observation and author claim | Passed | 1,090 | 469 | 1,559 | 0.019520 |
| Epistemic status | Passed | 1,163 | 344 | 1,507 | 0.016135 |
| Source-only falsification | Passed | 2,855 | 721 | 3,576 | 0.035905 |
| **Execution 1** | **Failed final gate** | **8,603** | **3,014** | **11,617** | **0.133435** |

- Provider calls: 6
- Verified-live receipts: 6
- Retries: 0
- Fallbacks: 0
- Graph writes: 0
- Untouched sources selected or frozen: 0
- Frozen V10 changes: 0
- Execution 2 calls: 0

## Corrected Boundaries Worked Live

### Event-local role grounding

The role stage received only the two atomic event passages. It returned all six
required participant roles with evidence inside the corresponding event scope:

| Event | Role | Exact local evidence |
|---|---|---|
| A2 | focal population | `Patients with RA` |
| A2 | comparator population | `patients without RA` |
| A2 | outcome | `comorbidities` |
| A5 | focal population | `the RA` |
| A5 | comparator population | `non-RA NSCLC` |
| A5 | outcome | `OS` |

No source-global participant phrase was borrowed.

### Statistical observation versus author claim

For A5, the independent statistical stage returned:

- `log-rank P = 0.08` as `P_VALUE`;
- `hazard ratio 0.92` as `EFFECT_ESTIMATE`;
- `95% confidence interval 0.78-1.09` as `CONFIDENCE_INTERVAL`;
- author claim as `NOT_CLAIMED` with null claim evidence.

It explicitly explained that `no difference` is a comparison result rather
than an explicit significance label. The V1 false-significance failure did not
recur.

## Exact Failure

Failing stage: `execution_1:deterministic_assembly`

Error: `ScientificGateError: A2 comparison semantics are incorrect`

The A2 comparison agent returned the correct scientific categories:

- result state: `OBSERVED_DIFFERENCE`;
- direction: `HIGHER`;
- operator: `GREATER_THAN`.

It anchored those categories to the complete event sentence:

`Patients with RA were more likely to be female and had more comorbidities than patients without RA.`

The frozen V2 gate required the narrower exact span:

`had more comorbidities than`

Therefore the failure is evidence-span granularity, not a wrong comparison or
direction. The full sentence is source-local and entails the same A2 event, but
it does not equal the preregistered string. The frozen criterion was enforced
as written.

## Read-only Assembly Audit

Replaying the stored structured outputs through the frozen deterministic
assembler, without a provider call, produced:

| Metric | Result |
|---|---:|
| Complete events | 2 of 2 |
| Expected semantic stages | 12 |
| Assembled semantic stages | 12 |
| Resolved event-local roles | 6 |
| Unsupported claims | 0 |
| Contradictions | 0 |

- Categorical-stage SHA-256:
  `c0d2a2eda5f83ae09e5e6d876dacc78ca5f0bd3313c4f3a71a6ed62efb35a477`
- Complete-event SHA-256:
  `9524224bfe1e4f5ec6a6dbf3c4860327cfb6ea0e97e5843162d62f791edf2cd2`

This audit does not change the experiment decision. Execution 1 failed one
frozen acceptance criterion, so repeatability remains untested.

## Conclusion

V2 is a failed bounded experiment with a materially positive scientific
result. The two targeted live failures from V1 were corrected, all six stages
completed, and the source-only reviewer supported both complete events. The
remaining observed failure is a deterministic exact-span policy mismatch.

Do not retry or patch V2. Before any separately authorized V3, decide and
preregister whether comparison evidence is accepted by exact literal equality
or by deterministic containment within the same atomic event scope. That is an
evaluation-policy decision; it must not be silently changed after observing
this result.
