# Role Alignment Final Report

## Decision

`STOP_OPERATIONAL_BLOCKER`

The checkpoint reached a useful negative operational result, not a scientific
adjudication result. Two separately frozen Luna-high source-review calls violated
their own returned output-token ceilings. The preregistered repeated-budget-
violation stop rule therefore prevented the benchmark-policy and tie-break calls.

All outputs remain review-only. No scientific metrics were calculated from an
invalid receipt, no graph writes occurred, and no promotion was enabled.

## Prior Staged Result

The earlier staged experiment remains unchanged at commit `c0a2f945`:

- Luna recovered decrease, sensitivity, and enhancement as three event nodes.
- It connected the nested event graph and participants without flattening.
- The only public-gold mismatch was vinblastine's role on the sensitivity event.
- The immutable addendum classifies that result as
  `STOP_ROLE_ONTOLOGY_ALIGNMENT_REQUIRED`.

The older staged experiment requested in the attached prompt must not be rerun.

## Policy Finding

The official BioNLP CG paper says:

- `Theme` undergoes an event's primary effect.
- `Cause` is responsible for the event occurring.
- `Participant` is used when the precise role is not stated.

No official task page, task paper, or standalone guideline located in this
checkpoint says that the drug in `sensitivity to <drug>` scientifically causes
the sensitivity. The source phrase therefore supports a cautious meaning such as
`STIMULUS_OR_OBJECT`, not the sentence "vinblastine caused sensitivity."

The complete exposed development corpus nevertheless uses `Cause` for all ten
eligible Simple_chemical arguments on sensitivity/response triggers. This is
strong evidence of a benchmark convention, but it is explicitly labeled
`EVALUATION_ONLY_CORPUS_INFERENCE`, not an official scientific rule.

Primary sources and downloaded hashes are recorded in
`docs/validation/research/2026-07-22-bionlp-cg-role-policy.md`.

## Offline Design Result

The implemented dual-role representation keeps these fields separate:

- `source_semantic_role`
- `benchmark_projection_role`

An evaluation-only projection can therefore represent:

```text
source_semantic_role = STIMULUS_OR_OBJECT
benchmark_projection_role = CAUSE
projection_scope = BIONLP_CG_EVALUATION_ONLY
```

The projection cannot be constructed with graph promotion enabled, cannot
overwrite source meaning, and cannot be verbalized as scientific causation.
Focused fake-provider tests prove this boundary. This is an architecture result,
not proof that the live reviewers agreed.

## Live Executions

### V1

- Response: `resp_05af183fb64707b3006a61152fe43c819b8e2d2296aae9bb58`
- Returned maximum output tokens: 32,000
- Observed output tokens: 70,867
- Observed total tokens: 73,201
- Cost: $0.427536
- Latency: 344.149 seconds
- Decision: `INVALID_PROVIDER_EXECUTION`

### V2

V2 kept the same scientific semantics but used a deterministic seven-case
gold-blind execution panel. The complete ten-case sensitivity corpus profile
remained evaluator-only.

- Response: `resp_07c12f39d5ecf19c006a6117b893f4819babd83b2dcf9e3d08`
- Returned maximum output tokens: 16,000
- Observed output tokens: 18,608
- Observed total tokens: 20,069 against a 20,000 ceiling
- Cost: $0.113109
- Latency: 107.755 seconds
- Decision: `INVALID_PROVIDER_EXECUTION`

### Totals

- Provider creation calls: 2 of 4
- Retries: 0
- Duplicate creation calls: 0
- Input tokens: 3,795
- Output tokens: 89,475
- Total tokens: 93,270
- Cost: $0.540645 of $1.00
- Latency: 451.903 seconds
- Valid source reviews: 0
- Benchmark-policy calls: 0
- Tie-break calls: 0

Both canonical payloads and their hashes were preserved for custody but were not
scientifically interpreted or scored.

## Adversarial And Offline Validation

- Focused role/source-first tests: 21 passed before execution.
- Ruff: passed.
- Focused MyPy: passed.
- Architecture structure guard: passed.
- Two adversarial passes corrected gold leakage, answer laundering, promotion
  bypass, evidence overclaiming, tie-break overwriting, and prospective cost
  accounting before V1.
- Final `make service-checks`: passed once after the terminal result, with
  87.64% coverage against the required 86%.

## Simple Conclusion

The paper says only that the cells have sensitivity **to** vinblastine; it does
not explicitly say vinblastine caused that sensitivity. BioNLP CG appears to call
it `Cause` because that corpus consistently uses `Cause` for the object of
sensitivity or response. Artana now has a safe representation that could retain
the cautious source meaning while exporting the benchmark convention, but this
live checkpoint could not validate the two agent judgments because Luna exceeded
its token ceiling twice.

The earlier staged architecture did solve the missing-intermediate-event and
flattening problem. The remaining role-alignment question is narrowed and its
safe representation exists, but live dual adjudication remains operationally
unproven.
