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

## Recorded Outcome

- Decision: `STOP_AND_RECALIBRATE`
- Calls made: `1` (`source_frame_typing`)
- Provider response: `resp_0794aff9ec06e3f8006a5d75fe643c81998c7752a5aef321a7`
- Provider receipt: `verified_live`
- Result SHA-256: `3941e4cf6234e8c157dcf1c3fac57d9ba2a5f16688eb1e61e5a4bdf7052780eb`
- Fallbacks, retries, and graph writes: `0`

The run stopped before independent review because Luna used each complete V5
relation anchor as its frame predicate, while the validator silently required
the narrower V5 cue anchor. Two independent adversarial reviewers categorized
the returned frame inventory as scientifically non-lossy and the rejection as a
procedural contract defect. The official V6 result remains unchanged. V7 must
reuse this verified payload, correct the relation-versus-trigger distinction,
and spend only the independent review call that V6 did not reach.
