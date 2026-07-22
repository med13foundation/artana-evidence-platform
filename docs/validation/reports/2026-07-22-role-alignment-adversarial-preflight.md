# Role Alignment Adversarial Preflight

Date: 2026-07-22

## Scope

Two independent adversarial passes reviewed the offline role-alignment design
before preregistration or provider execution. The review targeted gold leakage,
causal overstatement, benchmark-answer laundering, evidence laundering,
deterministic semantic inference, promotion bypass, and same-model provenance.

## Findings And Corrections

1. The first panel selected only sensitivity examples whose public role was
   `Cause`. The builder now selects the complete exposed eligible set regardless
   of gold role. All ten eligible cases happen to be `Cause`; that result is
   measured after selection and labeled corpus inference, not policy.
2. The original explicit-causation control was semantically weak. It was
   replaced by a deterministic control whose source says the participant was
   "responsible" for the event.
3. Exact span grounding was easy to overstate as semantic proof. The metric now
   explicitly reports that it proves custody only; role meaning remains
   agent-owned.
4. Tie-break output could overwrite the two original reviews. It now validates
   disagreement only and preserves both original decisions unchanged.
5. Review-only and graph-promotion flags were constructor-controlled. They are
   now immutable non-init fields, with a regression test proving callers cannot
   opt into promotion.
6. A benchmark reviewer could launder corpus behavior as official policy. Agent
   inputs now contain official rules only. Corpus convention is computed from
   the complete exposed panel by deterministic evaluation and is explicitly
   scoped to BioNLP CG evaluation.
7. The tie-break prompt still mentioned the corpus convention. That reference
   was removed; unresolved official-policy cases must return `ABSTAIN`.
8. Prospective global cost enforcement initially considered only completed
   calls. It now reserves the maximum cost of the next call before launch.
9. Provider-boundary failure accounting could lose an acknowledged call. Invalid
   results now preserve the reserved attempt and acknowledged response ID and
   state honestly when failed-call usage is unverified.
10. Same-family fresh calls could be described too strongly. Every result states
    `same_model_family_independent_calls=true` and
    `model_independent_review=false`.

## Residual Limits

- The two primary reviewers and optional tie-break use the same Luna model
  family. Fresh calls reduce shared-answer exposure but are not model-independent.
- No standalone official CG annotation manual was found. A repeated corpus
  convention may support benchmark interoperability, but cannot be presented as
  an official scientific definition.
- The projection is diagnostic and review-only. It cannot enter graph promotion
  or rewrite the source-semantic role.

## Preflight Decision

The focused design is ready to freeze after tests, Ruff, MyPy, and the
architecture guard pass. No provider call was made during either adversarial
pass.
