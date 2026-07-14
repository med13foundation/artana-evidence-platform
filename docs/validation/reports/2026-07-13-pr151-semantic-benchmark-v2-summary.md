# PR151 Semantic Benchmark V2 Validation Summary

Date: 2026-07-13

Branch: `alvaro/evidence-pr151-expert-benchmark-v2`

Base: merged PR150 commit `3d8e23e588206a4ef1cc46c1628fcbd0fa808da4`

## Root Cause

PR150 demonstrated that the v1 AI-adjudicated fixture was not a valid model
adoption gold set. `brca1:pmid:30191368` had a defective expected label, while
two canaries omitted facts needed to decide the requested population and study
fit. Prompt pressure would only encourage models to reproduce defective labels.

## Integrity Design

- Preserve v1 fixture and snapshot bytes as historical AI diagnostic evidence.
- Keep AI adjudication categorical with rationale and literal bounded evidence
  spans; reject expert provenance and numeric self-scores in that contract.
- Reuse the existing expert-study bundle and provenance gate as the only future
  human-review authority.
- Derive score eligibility only after the existing gate passes, the source
  manifest binds the benchmark packet manifest, the review inventory exactly
  matches the case, and record-level citations resolve into packet text.
- Compute adoption metrics and canary status only from eligible expert labels.
- Keep every excluded record visible and represent no eligible evidence as
  `unavailable` rather than zero or pass.

## Initial Result

The committed v2 fixture has no linked real-shadow-review bundle. Its report
therefore shows 33 visible records, 0 score-eligible records, 30 pending-expert
records, 3 ambiguous pending-expert records, unavailable adoption metrics, and
an unavailable canary gate. It makes no human/expert or production-readiness
claim.

## Focused Validation

```text
59 passed
Ruff: passed
mypy benchmark_v2 package: passed (6 source files)
mypy validation CLI: passed (1 source file)
make artana-evidence-api-service-checks: passed (Postgres-backed)
```

Regression coverage includes forged expert provenance, model-authored numeric
fields, pending-record score leakage, ambiguous-canary gate leakage, packet
digest drift, AI-simulation bundle rejection, record-level source sufficiency,
CLI report drift, and honest report wording.

## Human-Only Blocker

Genuine human reviewers must complete the bounded benchmark cases through the
existing real-shadow-review study bundle/provenance gate. The three ambiguous
records also require richer bounded packets. Agent adjudication remains AI
diagnostic and cannot close this blocker.
