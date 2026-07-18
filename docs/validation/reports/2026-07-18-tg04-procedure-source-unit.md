# TG-04 Procedure Source-Unit Experiment

Date: 2026-07-18

## Decision

**PROCEED TO ONE KNOWN EXPERT EVENT.** The isolated procedure-recognition gate
passed on its first and only authorized run. The extractor and blinded verifier
independently classified the previously disputed electroporation sentence as
`PROCEDURE`. Neither agent treated it as a scientific event.

This result resolves the specific event-eligibility asymmetry exposed by the
earlier finite source-unit pilot. It does not measure scientific event
reconstruction, discovery value, graph quality, or readiness for persistence.

## Frozen Experiment

- Harness commit: `4935a8cc`
- Model: `openai:gpt-5.6-luna`
- Run ID: `tg04-procedure-source-unit-luna-01`
- Agent calls: exactly `2`
- Extraction calls: `1`
- Blinded verification calls: `1`
- Biomedical fallback: `0`
- Artifact:
  `/tmp/artana-tg04/procedure-source-unit-2026-07-18/luna-r1.json`
- Artifact SHA-256:
  `1edea7a836ad766724ac402d9375ad616d94d5a1051c1030f1a8b8b418168116`
- Embedded report SHA-256:
  `f739d25d9a0ac4ad74b066ddd7a0e32c63ef5355e8cfe5662fe0ff59daf7363e`

The embedded digest was recomputed after removing `report_sha256` and matched
exactly. The output path was create-once and no replacement run was made.

## Source Unit

The unit was pre-registered from the true-negative BioNLP methods control. It
was selected by case ID, sentence index, opaque unit ID, and input hash.

- Unit ID:
  `source-unit-063ab2e2ce044fe71c9f700805f4ed61be4a66879bd9aa3d50e7a683c2ee3af1`
- Input SHA-256:
  `19f72827611fa17d2b45c457ed6b632a1f549a9e44c3bb58387dc8d86dbdf47d`
- Source range: `118-359`

The sentence describes adding reporter vectors to CD4+ T cells and
electroporating them with a specified Nucleofector program. In the previous
pilot, the extractor excluded it while the verifier incorrectly reported a
missing biomedical event.

## Agent Results

The extraction agent returned:

- eligibility category: `PROCEDURE`
- extraction decision: `NO_EVENT`
- scientific candidates: `0`
- binding rejections: `0`

Its explanation identified vector addition, cell resuspension, and
electroporation as experimental setup without a biological result or proposed
mechanism.

The blinded verification agent returned:

- eligibility category: `PROCEDURE`
- coverage decision: `NO_EVENT_CONFIRMED`
- candidate decisions: `0`

Its independent explanation likewise identified sample preparation and
intervention application without a biological result or proposed mechanism.

## Deterministic Gate

Every pre-registered requirement passed:

- both agent executions completed;
- both agents specifically returned `PROCEDURE`;
- the independent categories agreed;
- no scientific candidate was extracted;
- the verifier confirmed no scientific event;
- binding rejections, invalid outputs, and fallback were zero;
- one provider response belonged to extraction and one to verification;
- the two provider response IDs were distinct;
- both provider receipts verified live.

The CLI is fail-closed: it returns a nonzero exit status whenever any gate
requirement fails.

## What Improved

The earlier pilot gave extraction and verification different definitions of a
scientific event. The revised contract makes both agents return the same closed
eligibility category before event and coverage decisions. Deterministic code
rejects category-decision contradictions, cross-agent disagreement, generic
`NO_EVENT` agreement, abstention carrying entailed evidence, missing lineage,
or an unverified receipt.

This is meaningful progress in event eligibility and false-positive control.
It is not yet evidence that Artana can reconstruct a complete expert event.

## Next Isolated Step

After this PR merges, run exactly one frozen source unit containing one known
expert event. Use the same extraction and blinded verification roles. Require:

- both agents to return the same relation-eligible scientific category;
- an exact source-bound trigger and all material typed participants;
- exact event type, polarity, epistemic status, and nested structure;
- zero binding rejection, invalid output, fallback, and uncertainty escalation;
- one distinct provider receipt per role, both verified live.

Stop if any condition fails. Do not run the unannotated discovery unit until
the one expert-event reconstruction passes.

## Validation

- `45` focused finite-unit and provider-receipt tests passed.
- Ruff and mypy passed on all changed files.
- `make service-checks` passed with `87.47%` coverage.
- Commit and push hooks remained enabled.
- An independent adversarial review found and drove closure of category
  disagreement, abstention leakage, generic `NO_EVENT` false pass, disconnected
  gate, role-lineage, exact-call-count, and CLI-exit-status weaknesses before
  the live run.
