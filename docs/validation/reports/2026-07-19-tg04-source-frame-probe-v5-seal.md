# TG-04 Source-Frame Probe V5 Seal

This document independently anchors the one-shot, non-qualifying V5 development
experiment stored outside the repository at
`/Users/alvaro/.codex/artana-evidence-experiments/tg04/source_frame_probe_v5`.

Manifest SHA-256: `fb9877710fd0bebf751f3d02b4b8cd21a83fae686c8ab53a317af9766e87c4aa`

- Frozen Artana code commit: `d204f5e9da02d8b24d13765022bbe8a3f9963db2`
- Model: `openai:gpt-5.6-luna`
- Provider-call limit: `3`
- Retry limit: `0`
- Qualification eligible: `false`

The V5 runner requires this committed digest to match its canonical manifest and
requires this document to be the only repository change after the frozen Artana
code commit. A passing result authorizes only the preregistered untouched pilot;
it does not qualify trusted-graph promotion.

## Recorded Outcome

- Decision: `STOP_AND_RECALIBRATE`
- Calls made: `1` (`relation_phrase_inventory`)
- Provider response: `resp_0bb9dd00b4043e05006a5d70071138819b970202c85db1ec79`
- Provider receipt: `verified_live`
- Result SHA-256: `9861647c93f8a4af77b471d0dec439fa7cf7e0c715999bd4b664d347df0f46cf`
- Fallbacks, retries, and graph writes: `0`

The exact-anchor remediation succeeded and recovered all three dimer candidates
with separate molecular members. The run stopped before Stage 2 because Luna
retained `two new kappa B-specific complexes` as shared scope instead of emitting
the preregistered separate generic candidate. Two independent post-run source-only
adjudicators categorized that representation as scientifically non-lossy and the
rigid candidate count as a false rejection. The official V5 decision remains
unchanged; V6 must reuse the verified Stage-1 payload and test only frame typing
plus independent review.
