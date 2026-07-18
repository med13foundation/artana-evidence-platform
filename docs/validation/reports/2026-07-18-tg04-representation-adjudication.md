# TG-04 Representation Adjudication

Date: 2026-07-18

## Decision

**PROCEED TO ONE UNANNOTATED DISCOVERY UNIT.** The one authorized independent
adjudication classified the source-bound Artana event as an
`ACCEPTABLE_ALTERNATE` representation of the sealed BioNLP event. Every
pre-registered semantic, lineage, receipt, and fail-closed requirement passed.

This result does not change the original exact benchmark score, which remains
`0/1`. It is agent-adjudicated diagnostic evidence, not human-expert proof of
scientific readiness, and it does not authorize graph persistence.

## Frozen Inputs

- Harness commit: `90847d46`
- Model: `openai:gpt-5.6-luna`
- Run ID: `tg04-representation-adjudication-luna-01`
- Agent calls: exactly `1`
- Biomedical fallback: `0`
- Prior artifact SHA-256:
  `865a4eadab94021d57e7446b7f8ce96125aa29b7b3d6df6ed92f267f6a36f775`
- Prior embedded report SHA-256:
  `adc7d5fa2aac69464f72c8e7f62327d8696838373f67b7682a9200af037031dc`
- Adjudication artifact:
  `/tmp/artana-tg04/representation-adjudication-2026-07-18/luna-r1.json`
- Adjudication artifact SHA-256:
  `1d15e7b05248daf6ad10f6a647be4820e7303dcd724caee2a84f5da9da734f68`
- Adjudication embedded report SHA-256:
  `1e775d4ea0b203a6c69fa4b218ff7ff3d1512ea7b031617eff4d46f1c10d2f43`

Both embedded digests were independently recomputed. The prior artifact was
hash-pinned before the adjudicator ran. The adjudication output was written to
a create-once path and was not replaced or rerun.

## Categorical Result

Both expert and candidate representations were judged `ENTAILED` by the frozen
source. The six required comparison axes were:

- trigger: `COMPATIBLE_REFINEMENT`;
- direction: `PRESERVED`;
- participants: `COMPATIBLE_REFINEMENT`;
- causal role: `COMPATIBLE_REFINEMENT`;
- polarity: `PRESERVED`;
- epistemic status: `PRESERVED`.

The adjudicator treated `four-fold upregulation` as a more specific trigger and
`Id1 mRNA` as the source-explicit measurement of `Id1`. It also addressed the
hardest disagreement: the candidate stores `BMP-6-treated B cells` as context,
while the expert event stores `BMP-6` as `CAUSE`. The adjudicator concluded that
the treated-cell phrase retains the BMP-6 relation rather than demoting it to
incidental context.

The falsification condition was concrete: the equivalence would fail if BMP-6
were merely mentioned separately and the source did not link it to the observed
upregulation.

## What The Gate Proves

The gate proves that one independent agent, using only the source and two
frozen representations, found the mismatch to be a scientifically compatible
alternate frame. The result has exact source coverage, one accepted provider
attempt, one verified live receipt, no invalid output, and no fallback.

The gate does not prove that all alternate frames are valid, that Luna can find
novel valuable claims, or that an agent adjudicator matches human experts. It
also does not relabel the BioNLP event or count this candidate as an exact
benchmark match.

## Next Isolated Step

After this PR merges, select exactly one frozen source unit whose possible
scientific event is hidden from the discovery agent and is not included in the
known-event comparison prompt. Run one extraction agent and one independent
source verifier. Then use a separate source-and-literature review agent to
categorize the discovered claim as supported, contradicted, already known,
potentially novel, or unresolved, with exact citations.

Stop if the discovery is generic, partial, unsupported, receipt-less, or not
independently reproducible. Even a successful discovery remains review-only and
cannot be persisted to the trusted graph.

## Validation

- `56` focused representation, finite-unit, and provider-receipt tests passed.
- Ruff passed on every changed file.
- Mypy passed for `612` Evidence API modules.
- Commit hooks passed graph/evidence lint and type checks.
- `make service-checks` passed, including fresh PostgreSQL migrations and the
  full service suite, at `87.47%` measured coverage.
- An independent Claude adversarial review returned no actionable false-pass,
  gold-replacement, receipt, or verifier-leakage findings.
