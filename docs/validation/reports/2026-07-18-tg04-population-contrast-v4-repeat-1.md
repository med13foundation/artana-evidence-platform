# TG04 Population Contrast V4 Repeat 1

## Decision

The fourth hidden-unit qualification did not pass. Repeats 2 and 3 were not run.
The failure is retained as a non-qualifying result and provides no trusted-graph
credit.

## Immutable Evidence

- Foundation commit: `a4143c30`
- Sealed selection commit: `9d55601c`
- Model: `openai:gpt-5.6-luna`
- Run ID: `tg04-population-contrast-v4-2026-07-18`
- Source unit: `source-unit-372b0632f7433058002746584f09b6a55db2fcde52724d1f59104731edb29870`
- Report: `docs/validation/reports/2026-07-18-tg04-population-contrast-v4-repeat-1.json`
- Canonical report-content SHA-256: `5209c8aa2a793af30f577afdec8d92c4164b25e1560d399f74d27cef59a31190`
- Archived file SHA-256: `7214208f09252d8c3ead2bf9ae7bd28368059edc8368107dc08813aa184a6fde`
- Corpus archive SHA-256: `f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f`
- Source SHA-256: `9548ffaadbde4f7f6f4419345ecd93d9f549c04c4c03b0988233610da28eb1cf`
- Expert graph SHA-256: `1420609f10dbb6e2d667acdc6d3d0909a96ccd1572a032ef4986bd1ab4f746ca`
- Projection set SHA-256: `5d725c8feedfaf292cb3753c7c9cd8a557ceb7eeba23538068325f7f4f1f237d`
- Repository tree: `1da1fa67b2bf95b0b5b86070a7f7d38c89300f34`
- Extraction prompt: `tg04.finite_source_unit.extraction.v15`
- Verification prompt: `tg04.finite_source_unit.verification.v14`

## What Passed

- The extractor and independent verifier completed through the live provider.
- Both agents classified the unit as `MIXED_SCIENTIFIC`.
- The extractor returned the resting-cell support result and activated-cell null
  result as separate population-specific events.
- Both candidates were independently judged entailed, complete, structured,
  valid, and eligible by the live verifier. The adversarial post-run review below
  found that this completeness judgment was too permissive.
- Provider receipts were verified live.
- Fallback, invalid output, identity mismatch, rejected claims, and review-only
  claims were all zero.

## Failed Gate

`complete_acceptable_projection_recovered` was false. All other qualification
gates passed.

The model represented the source as two `INCREASE` events. It preserved A3G as
the theme, IFN-alpha treatment as intervention context, and the two populations
as separate contexts. The resting event had `SUPPORT` polarity and the activated
event had `NULL_RESULT` polarity.

The frozen projection set instead required IFN-alpha treatment to be a causal
controller. The phrase "after IFN-alpha treatment" establishes temporal or
experimental context, but it does not by itself establish causation. The model
correctly avoided that unsupported causal upgrade.

The model output was still not a complete structured representation. It dropped
the temporal marker "after" from the typed arguments, and the activated-cell null
event used cue "not" without a typed argument for its inherited "expression of
A3G" process. The source span retained those words, but the graph-facing structure
did not. The independent verifier should have classified that candidate as lossy
or incomplete instead of eligible.

## Root-Cause Correction

The general extraction, verification, and final-framing contracts now distinguish
contextual treatment ordering from source-explicit causation. Directional changes
in an experimental context may use `INCREASE` or `DECREASE` while preserving the
treatment as typed context and the complete temporal phrase as `TIMEFRAME`. An
elliptical null contrast must preserve its inherited tested process as a typed
argument. Final framing rejects a causal relation unless its subject was
categorically inventoried as source-explicit `CAUSE` or `AGENT`.

Regression tests enforce these deterministic structural boundaries and adversarial
temporal-versus-causal minimal pairs without altering the sealed V4 projection set
or awarding post-hoc V4 credit. They do not prove live-agent recovery. A fresh,
pre-registered V5 unit must validate the complete extraction, independent
verification, source binding, and qualification path.

The next hidden unit must be selected only after this correction is committed.
Its deterministic seed is exactly this failed report's SHA-256, and all previously
exposed source documents remain excluded.
