# TG-04 V9 Live Scientific Result

Date: 2026-07-18

Decision: `STOP_AND_RECALIBRATE_NESTED_EVENT_EXTRACTION`

This report records the first finalized live execution of the pre-registered V9
BioNLP source unit. It is a negative scientific qualification result, not an
execution failure and not evidence that the extracted scientific core was
empty.

## Receipt

- model: `openai/gpt-5.6-luna`;
- run: `tg04-v9-live-20260718`, repeat `1`;
- report: `/private/tmp/artana-tg04/v9/repeat-1.json`;
- report SHA-256:
  `59107ff0d23bf9543b23df2add9885d0bab4c7dd0c38ffbd18e030734cc2c897`;
- reservation: finalized with `gate_passed=false`;
- primary extraction attempts: `1`;
- independent weak-review attempts: `1`;
- verified provider receipts: `2`;
- invalid agent outputs: `0`;
- deterministic fallback outputs: `0`.

The finalized report still passes deterministic V9 replay after the V10 policy
changes. V9 prompt identity remains frozen at extraction `v20` and verification
`v19`.

## Deterministic Result

Luna returned six candidates. The verifier categorized all six as entailed and
projection-eligible. Deterministic linking recovered three unambiguous
outer-to-controlled-target links with no orphan target or unresolved reference.

The qualification gate nevertheless failed because:

- no complete acceptable projection was recovered;
- no unique representation family was recovered;
- all six verifier-trusted candidates remained unmatched.

These failures correctly prevent graph promotion. They do not distinguish a
scientific error from a valid representation missing in the frozen projection,
so each miss was adjudicated separately.

## Candidate Adjudication

The categories are categorical findings, not model-generated scores.

| Candidate | Scientific core | Primary failure | Adjudication |
| --- | --- | --- | --- |
| IL-2 restores proliferative response | Source-explicit positive regulation and controlled target are preserved | Treatment, Rel-/- variant, and T-cell population are bundled into one population context; direct antecedent `Exogenous IL-2` was also absent from the frozen relative-clause alternatives | `GRAPH_INCOMPLETE`, with a `SOURCE_VALID_EQUIVALENT` cause representation |
| Controlled proliferative response | Source explicitly names the controlled process | Population is encoded only as context and treatment plus variant roles are absent | `GRAPH_INCOMPLETE` |
| IL-2 restores IL-5, TNF-alpha, and IFN-gamma production | Positive controller, grouped process target, comparator, and event link are preserved | Material treatment, variant, and population context is bundled rather than independently typed | `GRAPH_INCOMPLETE` |
| Controlled IL-5/TNF-alpha/IFN-gamma production | All three themes are retained | `production` is typed `OTHER_EXPLICIT` instead of `EXPRESSION`; scoped context is absent | `ONTOLOGY_WRONG` |
| IL-2 does not restore IL-3/GM-CSF expression to normal levels | Null polarity, comparator, grouped process, and controlled-event link are preserved | The relation cue is not minimal and material context is bundled | `GRAPH_INCOMPLETE`, with a source-valid null-result core |
| Controlled IL-3/GM-CSF expression | `EXPRESSION` and both themes are retained | Treatment, variant, and population context scoped by the source is absent | `GRAPH_INCOMPLETE` |

No candidate was adjudicated `UNSUPPORTED`. That is scientifically encouraging,
but none is complete enough for trusted graph promotion.

## Adversarial Review

An independent Claude Sonnet source-only review classified the overall zero
match as `BOTH`: genuine extraction defects and benchmark over-specificity. Two
reviewer conclusions were narrowed after checking the frozen projection:

- grouped supported cytokine targets are explicitly accepted, so grouping does
  not make the outer supported-restoration candidate ontology-wrong;
- the null-result core is source-valid, but bundled context still makes its
  graph representation incomplete under the declared trust contract.

The accepted adversarial finding is therefore not that the matcher should
accept bundled text. It is that source-valid antecedent and cue alternatives
must be explicitly adjudicated before execution, while typed role loss remains
fail-closed.

## Implemented Remediation

The next contract change addresses only failures demonstrated by V9:

1. Production inventory and completeness prompts now require independent typed
   treatment, variant, and population arguments when a compound phrase carries
   all three roles.
2. Controlled targets retain context scoped to them; an outer copy is not a
   substitute.
3. Production of named gene or protein products maps to `EXPRESSION` unless the
   source explicitly names another closed event type.
4. Relation cues use the shortest source-explicit relation phrase and material
   negation, leaving participants and thresholds in typed arguments.
5. V10 finite-unit prompts are versioned separately from V9, preserving
   immutable replay.
6. Sealed projections may list exact, source-verbatim trigger alternatives.
   Unlisted cues still receive no credit, and duplicate or non-verbatim
   alternatives fail validation.

## V10 Stop/Go Boundary

V9 repeat `2` is not authorized. V10 may consume one fresh hidden unit only
after all of the following are true:

- V9 replay remains byte-identity canonical;
- visible tests prove accepted and rejected cue alternatives;
- the selected V10 gold lists every source-valid representation before model
  execution;
- adversarial review finds no false-positive path;
- repository service, type, boundary, schema, and coverage gates pass;
- the worktree is clean and the reservation is committed before provider use.

A V10 pass requires complete source-supported event recovery, exact nested-link
topology, zero unsupported trusted claims, zero unresolved extra claims, zero
fallback, and verified provider lineage. Additional source-valid discoveries
remain review-only rather than being silently counted as benchmark failures or
trusted-graph successes.
