# TG04 Participant Ledger Invalid

Status: `INVALID_RUN`

Scientific qualification: `false`

Advancement: `STOP_BEFORE_SOURCE_REVIEW`

This exposed one-shot experiment tested a participant ledger after flat event roles first merged and then duplicated coordinated participants.

## Validity Controls

- repository commit, fixture, prior runners/results/manifests, and parser artifact sealed;
- adversarial preflight before execution;
- model: `openai:gpt-5.6-sol`, default reasoning behavior;
- provider calls: `1`;
- retries, fallback, replay, graph writes: `0`;
- no benchmark score or automatic scientific gain claim.

Preflight added an experiment-local `REGULATORY_DNA_REGION` type, group-cycle validation, and an explicit untracked-file allowlist before returning `GO`.

## Failure

The provider returned a structured payload, but deterministic validation rejected it with:

```text
unreferenced participants: ['P1']
```

`P1` was the `DR alpha` gene/locus identity. The payload also contained the `proximal promoter` as a regulatory-DNA Site, but the experimental schema supported only group membership edges and event-role edges. It had no participant-to-participant relation capable of connecting the promoter to its gene/locus.

The run therefore stopped before live-receipt adjudication and independent source-only review. No scientific improvement is claimed.

## Diagnostic Observation

The rejected raw payload otherwise had the intended architecture: one collective cis-element Theme, separate `S` and `X2` identities linked by `EXEMPLIFIES`, a regulatory-DNA promoter Site, cell context, and nested CIITA dependency. This is diagnostic only because the run was invalid.

## Root Cause And Next Hypothesis

The participant ledger is still too narrow. Group edges solve collective membership, but biomedical mentions also require source-supported semantic edges such as `PROMOTER_OF`, `PART_OF`, or a deliberate decision to keep the complete promoter phrase as one Site without separately inventorying the locus.

The next protocol must add categorical participant-to-participant semantic edges and retain fail-closed reference integrity. It must be preregistered before another provider call; this invalid output must not be repaired or accepted post hoc.
