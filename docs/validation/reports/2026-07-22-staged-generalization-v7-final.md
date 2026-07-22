# Staged Generalization V7 Final Report

## Terminal decision

`PIVOT_WITH_EVIDENCE`

V7 is a valid, terminal, review-only experiment. It does not qualify scientific
promotion and performed no graph writes. The fail-fast runner stopped after the
first scientific failure, so the three later cases were not called.

## Frozen change

The preregistered change was `FOCUS_GATED_REFERENTIAL_GROUNDING`. V7 kept the V5
panel, strict output schema, `openai:gpt-5.6-luna` model at high reasoning,
three-reviewer frozen grading policy, acceptance thresholds, budgets, and
exactly-once receipt boundary unchanged. It used V6's terminal result as its
hash-pinned pivot basis and did not rescore V6.

The preregistration was committed and pushed before execution at
`6f67d34c62b80e18911797e535deced2581dab5d`.

## Observed result

| Case | Outcome | Important observation |
| --- | --- | --- |
| `generalization-comparison-canary` | Pass | Required comparison, roles, and semantic axes were exact. |
| `generalization-null-statistics` | Pass | V6's over-expansion was repaired: no curve/model participant and no unsupported context remained. |
| `generalization-negated-association` | Fail | Core event, participants, roles, evidence, direction, comparison, uncertainty, and statistics passed; only polarity differed. |

For the failing case, the model returned the correct `ASSOCIATION` event and
`direction = NO_ASSOCIATION`, but used `polarity = NEGATED` for “no longer
associated.” The frozen reference requires `polarity = NULL_RESULT`. That one
axis mismatch produced one contradiction and the terminal pivot.

Aggregate observed metrics at the stop boundary:

- 2 of 3 called cases passed; 3 of 3 had complete core recovery, exact evidence,
  correct roles, nesting, direction, comparison, uncertainty, and statistics.
- Polarity fidelity was 2 of 3.
- Unsupported claims: 0. Ambiguous context: 0. Contradictions: 1.
- Provider calls: 3. Verified receipts: 3. Retries: 0. Duplicate calls: 0.
- Total tokens: 26,433. Total cost: USD 0.125973. Total recorded latency:
  350.77944787499837 seconds.
- Every per-call output-token, total-token, cost, and latency check passed.

The runner did not call `generalization-uncertainty`,
`generalization-drug-sensitivity`, or `generalization-explicit-nested-cause`.
Therefore V7 cannot claim that the original uncertainty failure is repaired.

## Root-cause diagnosis

The focus gate solved the V6 regression without changing or relaxing the grader.
The new stop is an under-specified semantic boundary in the agent instruction,
exposed by model variance: the prompt says to preserve negation but does not
explicitly distinguish grammatical negative wording from an empirical null
result on the polarity axis. V5 happened to map the same finding to
`NULL_RESULT`; V7 mapped its surface negation to `NEGATED` while independently
mapping direction to `NO_ASSOCIATION`.

The first-principles correction is not a grader relaxation. A future,
separately preregistered experiment should define the source-general polarity
taxonomy: an explicitly absent association or effect is `NULL_RESULT`, even when
expressed with negative grammar; `NEGATED` is reserved for direct denial or
non-occurrence that is not an empirical null association/effect. The direction
axis continues to encode `NO_ASSOCIATION` independently.

V7 is the second bounded correction after V5. No V8 call was authorized or made
in this cycle; the terminal evidence is preserved for review before another
scientific change.
