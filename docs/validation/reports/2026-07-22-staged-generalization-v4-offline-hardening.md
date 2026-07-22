# Staged Generalization V4 Offline Identity Hardening

## Decision

`OFFLINE_IDENTITY_HARDENING_PASS`

This is a deterministic, non-creditable replay of the two preserved valid V3
provider outputs. V3 remains `PIVOT_WITH_EVIDENCE`; its result, metrics, raw
outputs, and receipts were not edited or rescored in place.

## Root Cause And Correction

V3 used raw substring counts for mention identity. That made the exact mention
`RA` appear ambiguous because the same characters also occur as the suffix of
the separate hyphenated token `non-RA`. The evaluator also required exact
reference-string equality even when the agent returned a uniquely grounded
containing span such as `log-rank P = 0.08` for the frozen `P = 0.08` value.

V4 corrects the owning deterministic boundary:

- exact source offsets are resolved before reference matching;
- alphanumeric, underscore, and hyphen-connected text is treated as one token,
  preventing `RA` from matching inside `non-RA`;
- equal or containing spans are equivalent only when both resolve uniquely in
  the same evidence scope;
- the V4 focal-cohort reference uses the literal source span `RA`, not the
  non-contiguous ellipsis expansion `RA NSCLC`;
- categorical scientific fields remain exact and are never inferred by the
  span-equivalence layer.

## Adversarial Guards

Focused regressions prove that:

- a broad `RA and non-RA NSCLC` span cannot collapse the two cohorts;
- a containing statistical span preserves the exact `P = 0.08` value;
- an absent or changed value such as `P = 0.05` is rejected;
- author interpretation, direction, polarity, uncertainty, types, and roles
  receive no equivalence credit.

## Offline Replay Result

- Cases replayed: 2/2
- Complete-event recovery: 2/2
- Participant-role fidelity: 2/2
- Exact evidence grounding: 2/2
- Statistical fidelity: 2/2
- Unsupported claims: 0
- Contradictions: 0
- Provider calls: 0
- Qualification credit: none
- Graph writes or promotion: 0

The replay result is stored separately at
`docs/validation/results/2026-07-22-staged-generalization-v4-offline-replay.json`.
It establishes that the demonstrated V3 failure family is corrected offline;
it does not establish six-case generalization.
