# TG-04 Source-Frame Probe V6 Seal

This document independently anchors the one-shot, non-qualifying V6 development
experiment stored outside the repository at
`/Users/alvaro/.codex/artana-evidence-experiments/tg04/source_frame_probe_v6`.

Manifest SHA-256: `d9328c8e1a9878d560a9e1d47f479fb4bbc3b2084efd6ff40007c2ef10e9b30e`

- Frozen Artana code commit: `d204f5e9da02d8b24d13765022bbe8a3f9963db2`
- Model: `openai:gpt-5.6-luna`
- Provider-call limit: `2`
- Retry limit: `0`
- Qualification eligible: `false`

V6 immutably reuses the verified V5 Stage-1 relation inventory and makes no new
candidate-discovery call. Its two-call budget is limited to source-frame typing
and an independent source-only review. The runner requires this committed digest
to match its canonical manifest and permits only the V5 and V6 seal documents as
repository changes after the frozen Artana code commit.

A passing result authorizes only the preregistered untouched two-source pilot. It
does not qualify trusted-graph promotion or authorize a graph write.
