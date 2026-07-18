# TG04 V7 Selection Preflight

## Decision

V7 stopped before any model call. The selected source is genuinely hidden, but
the sealed BioNLP graph is not a complete inventory of the scientific claims in
the source unit.

## What Passed

- The seed is the exact SHA-256 of the immutable V6 preflight JSON.
- All six remaining negated-result candidates were scanned against Git-indexed
  repository blobs before ranking.
- No candidate source was already exposed in tracked repository content.
- The selected unit was revealed only after deterministic ranking.

## What Failed

The expert graph covers the negated phosphorylation claim:

`NIK cannot phosphorylate IkappaB-alpha directly.`

The same source unit also contains a directional comparison that is absent from
the local corpus events:

`Mutated NIK inhibited stimulus-induced kappaB-dependent transcription more effectively than mutated IKK-alpha or -beta.`

Graph closure over the events present in the corpus is therefore insufficient:
it proves annotation consistency, not complete scientific-claim coverage.

## Next Calibration

Before selecting V8, independently adjudicate source/gold completeness for all
remaining hidden candidates. Freeze the admissible candidate identities and
rationales, then apply the chained deterministic rank only within that set.
This remains blind to Artana and Luna outputs while avoiding repeated selection
of corpus records whose gold annotations are scientifically incomplete.
