# Staged Generalization V9 Final Report

## Terminal decision

`PIVOT_WITH_EVIDENCE`

V9 is a valid, terminal, review-only experiment. It does not qualify scientific
promotion and performed no graph writes. The fail-fast runner stopped at the
first scientific failure, leaving the final nested-causation case uncalled.

## Frozen change

The sole preregistered scientific change was
`CLASSIFICATION_ARGUMENT_BOUNDARY`. V9 added source-general rules that:

- link the classified entity as `AFFECTED_ENTITY`;
- link an explicitly named entity that restricts the classified entity's
  identity or scope as `CONTEXTUAL_PARTICIPANT`; and
- keep the classification label or value in the event trigger and semantic
  axes instead of duplicating it as `OUTCOME`, unless it independently
  participates in another event.

The role-field contract was versioned, but the JSON output shape did not
change. V9 retained V8's source-general polarity taxonomy.

V9 kept the V5 panel, case order, `openai:gpt-5.6-luna` model at high reasoning,
three-reviewer frozen grading policy, acceptance thresholds, budgets, and
exactly-once receipt boundary unchanged. It used V8's terminal artifacts as its
hash-pinned pivot basis and did not rescore V8.

The preregistration was committed and pushed before execution at
`13106a214afc0882e7382032f167e4b909e2d065`.

## Observed result

| Case | Outcome | Important observation |
| --- | --- | --- |
| `generalization-comparison-canary` | Pass | Required comparison, roles, and semantic axes remained exact. |
| `generalization-null-statistics` | Pass | Null-result polarity and focus-gated grounding remained stable. |
| `generalization-negated-association` | Pass | The repaired source-general polarity distinction remained stable. |
| `generalization-uncertainty` | Pass | V9 repaired the V8 classification boundary: `947 variants` was the affected entity, `SLC12A3 gene` was the contextual participant, and no classification value was duplicated as an outcome. |
| `generalization-drug-sensitivity` | Fail | The extraction disagreed with the frozen reference, and the current exact-span resolver also made the required drug mention impossible to ground unambiguously. |

Aggregate observed metrics at the stop boundary:

- 4 of 5 called cases passed.
- Complete event recovery and participant-role fidelity: 4 of 5.
- Direction, comparison, polarity, uncertainty, statistics, and exact evidence
  grounding: 4 of 5.
- Nested event structure: 5 of 5.
- Unsupported claims: 5. Ambiguous context: 0. Contradictions: 1.
- Provider calls: 5. Verified receipt triplets: 5. Retries: 0. Duplicate
  calls: 0.
- Total tokens: 36,306. Total cost: USD 0.152476. Total recorded latency:
  142.057457668001 seconds.
- Every per-call output-token, total-token, cost, and latency check passed.

The runner did not call `generalization-explicit-nested-cause`.

## Drug-sensitivity semantic mismatch

The V9 extraction represented `sensitivity` as an `ASSOCIATION`, linked
`carcinoma patients` as `POPULATION/AFFECTED_ENTITY`, linked `5-FU` as
`SIMPLE_CHEMICAL/STIMULUS_OR_OBJECT`, and set direction to `OBSERVED`.

The frozen reference instead requires:

- a `REGULATION` event;
- `carcinoma` as `CANCER/AFFECTED_ENTITY`;
- `5-FU` as `SIMPLE_CHEMICAL/STIMULUS_OR_OBJECT`; and
- direction `NOT_APPLICABLE`.

These event-type, entity-type, exact participant, and direction differences are
real reference disagreements. They must remain visible even after the span
resolver is corrected.

## Deterministic evaluator defect

The same case also exposes an independent evaluator defect. The prompt requires
each `exact_evidence` value to contain the complete exact source sentence. That
sentence is:

> Thymidylate synthase (TS) and dihydropyrimidine dehydrogenase (DPD) are
> 5-fluorouracil (5-FU) metabolizing enzymes and are involved in the sensitivity
> of carcinoma patients to 5-FU.

The frozen reference accepts only `5-FU` as the required drug text, but the
complete evidence sentence contains `5-FU` twice. The current
`resolve_in_context` contract delegates to `resolve_unique_span` and rejects a
child string that occurs more than once inside its evidence sentence.
Consequently, even a reference-shaped answer with the mandated full sentence
cannot bind the required drug mention. This is a deterministic grader/span
identity impossibility, not evidence that the scientific acceptance threshold
should be relaxed.

V9 remains terminal and its frozen result must not be mutated or rescored. The
semantic mismatches above also remain failures; correcting occurrence identity
would remove only the impossible grounding condition.

## Required next step

Do not start another model-prompt experiment yet. First, build and qualify a
separately versioned, occurrence-aware span identity contract offline. It must:

1. bind an exact child span by explicit occurrence or source offsets rather than
   assuming its surface text is unique within a sentence;
2. reject missing, out-of-evidence, or mismatched offsets fail-closed;
3. add regression tests for repeated identical mentions, unique mentions, and
   every frozen panel case; and
4. preserve the existing reference labels and scientific thresholds.

Only after that evaluator contract is independently frozen should a new
preregistered experiment be considered. No additional provider call was
authorized or made after the terminal V9 stop.
