# TG04 Participant Relation Ledger V1

Status: `SCIENTIFIC_PASS_PROCESS_FAIL`

Scientific ledger: `STRICT_SCIENTIFIC_PASS`

Whole-arm qualification: `false`

Advancement: `FIX_ADJUDICATION_GRANULARITY_THEN_EXPAND`

This exposed experiment generalized the participant ledger with categorical `MEMBER_OF`, `EXEMPLIFIES`, `PROMOTER_OF`, and `PART_OF` relations.

## Validity Controls

- fixed repository commit, fixture, parser, prior runner, manifest, result, and report;
- adversarial preflight before execution;
- one default `openai:gpt-5.6-sol` call;
- retries, fallback, replay, graph writes: `0`;
- live receipt: `verified_live`;
- attempt lineage: `pass`;
- no benchmark score or automatic gain decision;
- two independent source-only reviews and one adversarial adjudication.

## Scientific Improvement

The generated ledger correctly preserved:

- one cis-element group as the event Theme;
- separate `S` and `X2` identities through membership edges;
- the cis elements as part of the proximal promoter;
- the promoter-to-`DR alpha` locus relationship;
- group II CID cell context;
- one inner positive transactivation event;
- one outer unsigned CIITA regulation event targeting the inner event;
- zero unsupported mechanisms or claims.

The final adjudicator assigned `STRICT_SCIENTIFIC_PASS`. This is the first exposed CIITA representation in the current loop that avoids both merged participants and duplicated event operands while preserving roles, context, attribution, and nesting.

## Remaining Failure

The whole arm failed on parser-adjudication bookkeeping. Candidate C1 was `DR alpha` typed as `Protein`. Sol returned `ACCEPT` while its rationale and ledger normalized the mention to `GENE_OR_PROTEIN`, which is compatible with a gene/locus reading. Because `ACCEPT` means correct as written, C1 should have been `CORRECT`.

The adjudicator therefore assigned:

- scientific ledger: `STRICT_SCIENTIFIC_PASS`;
- candidate consistency: `INCONSISTENT`;
- whole arm: `SCIENTIFIC_PASS_PROCESS_FAIL`;
- comparison with prior merged and duplicated candidates: `PARTIAL_GAIN`.

## Next Root Cause

Candidate records currently bundle mention span, biomedical type, and event role into one `ACCEPT`, `CORRECT`, or `REJECT` label. A valid span can therefore hide an invalid type or role.

The next external contract must return separate categorical decisions for span validity, type validity, and role validity. After that correction, the participant-relation architecture should be tested on several diverse exposed sources. Untouched qualification remains unauthorized.
