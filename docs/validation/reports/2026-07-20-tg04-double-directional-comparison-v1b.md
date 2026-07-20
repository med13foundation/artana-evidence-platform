# TG04 Double Directional Comparison V1B

Status: `COMPARISON_CONTENT_PASS_ROLE_CONTRACT_FAIL`

Scientific qualification: `false`

Advancement: `ADD_SIDE_TYPED_COMPARISON_EVIDENCE_AND_EXPLICIT_ROLES`

## Execution

- already-exposed BioNLP development source;
- model: `openai:gpt-5.6-sol` with provider-default reasoning effort;
- the initial execution was sealed after an authentication rejection and produced no model output;
- one separately preregistered replacement call;
- retries, fallback, replay, and graph writes: `0`;
- replacement receipt: `verified_live`;
- V4 adversarial contract tests: `10 passed`;
- no benchmark score and no trusted-graph promotion.

## Scientific Result

Sol recovered both source-supported comparisons:

1. CD25 expression is lower in TGF-beta-treated cells than in activated T cells.
2. CD25 expression is still lower in cells cultured with TGF-beta and IL-4 than in cells treated with TGF-beta alone.

It correctly resolved `which was even more pronounced` to the preceding CD25 down-regulation, retained all three cell contexts, separated TGF-beta and IL-4, and invented no mechanism or additional comparison.

Two source-only reviewers agreed that source understanding was correct, comparison coverage was complete, and both comparison frames were valid. Independent adjudication classified comparison content as `PASS` and unsupported claims as `ABSENT`.

## Why The Complete Ledger Failed

The V4 validator rejected the output before normal completion because it required the intervention to appear directly on the comparison evidence event. The output instead represented TGF-beta through a separate source-supported treatment-context event. V4 also cannot distinguish a legitimate right-side baseline event from a right comparator incorrectly copied onto a left-side event.

Independent adjudication found two role-vocabulary mismatches:

- `CAUSE` is too strong for the treatment agent in `TGF-beta-treated cells`; the relation is supported but needs `TREATMENT_AGENT` or `EXPOSURE`.
- `CONTEXT` is too weak for the event-to-event meaning of `which was even more pronounced`; the relation is supported but needs an anaphoric or comparison-basis role.

The complete ledger therefore remains `FAIL` despite correct comparison content.

## Root Cause And Next Test

The remaining failure is no longer missing biomedical understanding. The contract conflates three different structures:

- left-side evidence versus right-side baseline evidence;
- treatment/exposure relations versus biological causation;
- anaphoric intensification versus generic context.

The next exposed experiment must add side-typed comparison evidence and explicit non-causal treatment plus comparison-basis roles. Deterministic validation should test each side separately. The source-specific comparison count remains a preregistered review criterion, not reusable ontology truth.

No untouched run is authorized until the full ledger, not only its comparison frames, passes source-only review.
