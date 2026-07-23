# V11 Exposed Run 2 Interpretation Addendum

The sealed final report says that the run did not validate the complete frozen
scientific contract. That statement refers to the preregistered requirement
that all six exposed cases pass. It must not be interpreted as saying that the
two targeted V11 corrections were untested or unsuccessful.

The comparison canary passed. The uncertainty case returned the exact
participant occurrence `SLC12A3`, not `SLC12A3 gene`, and passed the frozen
grader without V9 regression. The negated-association case used complete,
exact, uniquely resolvable semantic evidence, passed the frozen grader, and
improved V10 `exact_evidence_grounding`. The null-statistics case also passed.

The first scientific failure occurred on `generalization-drug-sensitivity`.
The output replaced the required `sensitivity` core event with an unsupported
association, missed the required core `carcinoma` and `drug` participants, and
added unsupported participant occurrences. Its V9 boolean failures were
unchanged, but `unsupported_claim_count` increased, so the frozen acceptance
policy correctly classified the frontier as
`UNRELATED_SCIENTIFIC_REGRESSION`.

Because execution was fail-fast, `generalization-explicit-nested-cause` was not
called. The terminal therefore does not qualify V11 for fresh-case execution,
even though the SLC12A3 and semantic-grounding repairs were observed.

This addendum changes no result, score, grader, reference, prompt, receipt, or
terminal decision.
