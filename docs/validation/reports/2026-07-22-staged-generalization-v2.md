# Staged Generalization V2

## Decision

`PIVOT_WITH_EVIDENCE`

V2 made one Luna-high call on the exposed comparison canary and stopped before
the remaining cases. The receipt and every budget passed. V1 was not rescored or
modified.

## What Improved

The source-general V2 corrections worked:

- the broader exact trigger `had more comorbidities than` resolved correctly;
- full-sentence event and participant evidence grounded exactly;
- event recovery, comparison, direction, polarity, uncertainty, and statistics
  all passed;
- no contradiction or unsupported scientific claim was introduced.

## Remaining Scientific Failure

Luna labeled the focal `Patients with RA` cohort as `AFFECTED_ENTITY`. The
frozen source-role reference and the prompt role taxonomy require `POPULATION`
for the focal cohort in a population comparison. Luna correctly labeled
`patients without RA` as `COMPARATOR` and `comorbidities` as `OUTCOME`.

This is a participant-role classification failure, not an evidence, trigger,
direction, or comparison failure.

## Provider Evidence

- Response: `resp_0125f93882cd210b006a6126e31f308198996448e634f970ec`
- Input tokens: 1,712
- Output tokens: 1,574
- Total tokens: 3,286
- Latency: 79.992 seconds
- Cost: $0.011156
- Retries and duplicate creation calls: 0

## Final Allowed Improvement Cycle

V3 may change only the source-general comparison-role instruction: comparison
cohorts use `POPULATION` and `COMPARATOR`; `AFFECTED_ENTITY` is reserved for
non-comparative entity state or behavior events. The evaluator and references
remain unchanged. V2 remains review-only and receives no qualification credit.
