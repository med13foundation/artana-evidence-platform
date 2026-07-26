# TG-04 Known Expert-Event Source-Unit Experiment

Date: 2026-07-18

## Decision

**STOP AND RECALIBRATE.** The first authorized run reconstructed one
source-grounded scientific finding and passed every execution, provenance, and
receipt check. It did not exactly reconstruct the sealed expert-corpus event,
so the deterministic gate correctly blocked the unannotated discovery unit and
any persistence work.

This is not a provider, fallback, or evidence-grounding failure. It is a
representation-alignment failure between Artana's source-faithful claim frame
and the BioNLP corpus event projection.

## Frozen Experiment

- Harness commit: `d9108953`
- Model: `openai:gpt-5.6-luna`
- Run ID: `tg04-known-expert-unit-luna-01`
- Agent calls: exactly `2`
- Extraction calls: `1`
- Blinded verification calls: `1`
- Biomedical fallback: `0`
- Artifact:
  `/tmp/artana-tg04/known-expert-unit-2026-07-18/luna-r1.json`
- Artifact SHA-256:
  `865a4eadab94021d57e7446b7f8ce96125aa29b7b3d6df6ed92f267f6a36f775`
- Embedded report SHA-256:
  `adc7d5fa2aac69464f72c8e7f62327d8696838373f67b7682a9200af037031dc`

The artifact was written create-once. Its embedded digest was recomputed after
removing `report_sha256` and matched exactly. No replacement run was made.

## Source Unit And Sealed Gold

The source unit is the asserted result sentence, `109` characters long:

> **Restricted corpus text, not republished here.** The unit is
> `bionlp-ge-2011:PMC-1134658-06-Results-05` at `char:555-664` of the
> normalized corpus document, SHA-256
> `193eb99d4d17d23d990650553f3189dc7523392e2c119dad6895528d475a8065`.
> A reader holding a licensed copy of the corpus can recover and verify it
> exactly. See
> [`RESTRICTED_CORPORA.md`](../../../scripts/validation/RESTRICTED_CORPORA.md);
> rehydrate with `python3 scripts/fetch_bionlp_ge_corpus.py`.

- Case: `bionlp-ge-2011:PMC-1134658-06-Results-05`
- Expert event: `PMC-1134658-06-Results-05:E9`
- Unit ID:
  `source-unit-e14e44064324af2f721a3d02d2caf44c00218a0ab6c4afc58e9bace413c9d46c`
- Input SHA-256:
  `14aec6614afd9d47d4cbafe7298b0e6b77b7a3d324048635d3fb98f463b9a0fd`

The model saw only the source unit. The expert event was loaded only after both
agent calls for deterministic comparison.

## What The Agents Did Correctly

Both the extraction agent and independent verifier returned `FINDING`. The
extractor produced exactly one candidate; the verifier marked it `ENTAILED`
with local evidence spans and `CANDIDATES_COMPLETE` coverage. Both provider
receipts verified live, with one distinct response per role.

The candidate preserved the source's direction, observed status, target
(`Id1 mRNA`), magnitude, and treated-cell context. Binding rejection, invalid
agent output, fallback, unidentified provider attempts, and epistemic
escalation were all zero.

## Why The Strict Gate Failed

The sealed corpus event is a `POSITIVE_REGULATION` event with:

- trigger: `upregulation`;
- `CAUSE`: `BMP-6`;
- `THEME`: `Id1`.

Luna instead produced an `INCREASE` event with:

- trigger: `four-fold upregulation`;
- `THEME`: `Id1 mRNA`;
- `CONTEXT`: `BMP-6-treated B cells`.

The output is source-anchored and plausibly useful, but its event type, trigger
boundary, argument roles, and participant surface differ from the sealed
projection. Whole-event precision and recall are therefore both `0/1`. The
gate requires `1/1`, so `exactly_one_complete_expert_event` is false.

This demonstrates the distinction we need to preserve: a source-valid claim is
not automatically an exact match to a particular corpus ontology projection.
Changing the gold, weakening exact matching, or prompting the model toward the
known event would turn the experiment into a self-fulfilling pass.

## Next Step: Recalibration Before Discovery

Do not run the unannotated discovery unit. First create a small, independent
adjudication protocol for representation equivalence:

1. Keep the raw expert event immutable.
2. Record a separate, categorical adjudication for whether a source-faithful
   Artana claim is an acceptable alternate representation, a partial claim, or
   a contradiction.
3. Require an independent agent reviewer to provide cited reasons for that
   category; deterministic code records the category and computes all rates.
4. Run the same one-unit result only after the protocol and its negative tests
   are frozen. It must not treat an alternate representation as an exact
   expert-event match.

Only a pre-registered accepted-equivalence result can justify moving to one
unannotated discovery unit. Even then, graph persistence remains prohibited.

## Validation

- `49` focused finite-unit and provider-receipt tests passed before the live
  run.
- Ruff and Python compilation passed on every changed file.
- Shared-environment mypy passed for `612` evidence API source files.
- Commit hooks ran and passed graph/evidence lint and type checks.
- The worktree-local `make service-checks` target could not start because its
  local virtualenv is missing Ruff; this was an environment limitation, not a
  passing full-gate result.
- An adversarial second-opinion pass found no actionable false-pass or
  gold-leakage issue in the harness.
