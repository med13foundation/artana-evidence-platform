# Final Aggregate Gate And Audit Snapshot

Date: 2026-07-03

Branch: `alvaro/evidence-pr0-quality-harness`

## Scope

This snapshot records the end state after the PR-5 through PR-10 implementation
loop:

- Specificity pruning
- CURIE linking and graph entity-candidate propagation
- Evidence-aware scoring
- Trust ladder hard floors
- Reproducible full-text extraction
- CI quality regression gate

## Service Gate

`make service-checks` passed.

- Static checks passed for graph service and Evidence API.
- Architecture size and structure checks passed.
- `relation-feasibility-quality-gate` passed.
- Coverage passed at 86.86% against an 86% minimum.
- Live external API, running-service, and OpenAI-key tests were explicitly
  skipped.

## Final Relation Feasibility Audits

| Audit | Verdict | Precision | Recall | Generic Rate | CURIE Gold Endpoint Rate | Agent Completed | Fallback/Unavailable |
|---|---|---:|---:|---:|---:|---:|---:|
| Strict agent | RED | 0.7500 fallback-only comparison | 0.2400 fallback-only comparison | 0.0000 | 0.0000 | 0/30 | 30/30 |
| Deterministic comparison | RED | 0.7500 | 0.2400 | 0.0000 | 0.0000 | 0/30 | 0/30 |

## Report Hashes

- Strict JSON:
  `32e4c619f22cc9c9cc12090332d148c9dba4b087624184f2418b3e3655337b85`
- Strict Markdown:
  `544097fb4665daa81759242333cd8e0b9e67f7c5e3de1bba712b4e4b7fb7ffb7`
- Deterministic JSON:
  `db43f21c237397462e62c569261e78484effdd9475919c0d2e9a60396ef13f29`
- Deterministic Markdown:
  `8d967de7cb7a70dd74afc0595ddd182a4db4185ee1f4a949df69503e020d4d36`

## Interpretation

The deterministic/fallback path is more specific and better guarded, but it is
not counted as trusted agent evidence. The trusted-agent product goal remains
unproven locally until the agent path completes with model credentials and
recovers CURIE-linked gold endpoints.
