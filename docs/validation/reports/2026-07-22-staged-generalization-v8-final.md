# Staged Generalization V8 Final Report

## Terminal decision

`PIVOT_WITH_EVIDENCE`

V8 is a valid, terminal, review-only experiment. It does not qualify scientific
promotion and performed no graph writes. The fail-fast runner stopped at the
first scientific failure, leaving the final two cases uncalled.

## Frozen change

The sole preregistered scientific change was
`SOURCE_GENERAL_POLARITY_TAXONOMY`. V8 added source-general definitions for
`AFFIRMED`, `NEGATED`, and `NULL_RESULT` to both the prompt and a versioned
polarity-field description. The JSON output shape did not change.

V8 kept the V5 panel, case order, `openai:gpt-5.6-luna` model at high reasoning,
three-reviewer frozen grading policy, acceptance thresholds, budgets, and
exactly-once receipt boundary unchanged. It used V7's terminal result as its
hash-pinned pivot basis and did not rescore V7.

The preregistration was committed and pushed before execution at
`577b9c3e8e5e9bea7358c6c1754af0a9f009e427`.

## Observed result

| Case | Outcome | Important observation |
| --- | --- | --- |
| `generalization-comparison-canary` | Pass | Required comparison, roles, and semantic axes were exact. |
| `generalization-null-statistics` | Pass | Focus-gated grounding continued to avoid V6's context over-expansion. |
| `generalization-negated-association` | Pass | V7's polarity error was repaired: the analytic absence of association was `NULL_RESULT`. |
| `generalization-uncertainty` | Fail | Antecedent grounding and uncertainty were repaired, but the participant frame remained incomplete and over-specified. |

For the failing case, V8 correctly grounded the referring expression to the
variant set, used `947 variants` as the affected entity, and classified the
scientific status as `uncertainty = UNCERTAIN`. It nevertheless:

- omitted the required `SLC12A3 gene` locus participant and its contextual link;
- added `uncertain significance` as an `OUTCOME` participant even though that
  classification value was already represented by the event and uncertainty
  axis.

The frozen grader therefore recorded a missing core participant/link and one
unsupported participant/link pair. No semantic-axis contradiction occurred.

Aggregate observed metrics at the stop boundary:

- 3 of 4 called cases passed.
- Polarity fidelity: 4 of 4. Uncertainty fidelity: 4 of 4.
- Exact evidence, direction, comparison, nesting, and statistics: 4 of 4.
- Complete core recovery and participant-role fidelity: 3 of 4.
- Unsupported claims: 2. Ambiguous context: 0. Contradictions: 0.
- Provider calls: 4. Verified receipts: 4. Retries: 0. Duplicate calls: 0.
- Total tokens: 29,620. Total cost: USD 0.129865. Total recorded latency:
  143.7437858329995 seconds.
- Every per-call output-token, total-token, cost, and latency check passed.

The runner did not call `generalization-drug-sensitivity` or
`generalization-explicit-nested-cause`.

## Root-cause diagnosis

V8 accomplished its intended change: the polarity distinction became stable
enough to pass the V7 failure, without changing the grader. It also demonstrated
that the V7 uncertainty and anaphora guidance now produces the correct
antecedent and uncertainty axis.

The remaining blocker is the classification argument boundary. The agent does
not consistently distinguish between:

1. an entity that defines the identity of the classified set, such as an
   explicitly stated locus; and
2. the classification value itself, which belongs in the classification event
   and semantic axes rather than being duplicated as an outcome participant.

A future separately preregistered experiment should address that single
source-general boundary. It should require explicit restrictive context that
defines the classified entity set and prohibit duplicating a classification
value as an `OUTCOME` participant unless it independently participates in
another event. The grader, panel, polarity taxonomy, and uncertainty rule should
remain unchanged.

No additional provider call was authorized or made after the terminal V8 stop.
