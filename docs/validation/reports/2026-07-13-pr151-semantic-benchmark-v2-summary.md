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
- Reuse the existing expert-study bundle and provenance gate; do not create a
  parallel human-certification mechanism.
- Resolve and hash every declared study source export, reproduce the bundle's
  reviews from those bytes, and verify exact reviewer-roster, run, export
  identity, and packet-manifest bindings.
- Treat the existing gate as necessary but not sufficient for benchmark gold.
  Score eligibility remains unavailable until an external trusted process
  authenticates reviewer identity and independently attests packet sufficiency
  per record, bound to the verified export digests and review run IDs.
- Enumerate packet sufficiency for every record. The three PR150 defects are
  `known_insufficient`; all other immutable v1 snapshots are `unverified`.
- Compute adoption metrics and canary status only from eligible expert labels.
- Make the standalone report builder load the bound prediction artifact and
  recompute its score from the exact evaluation; callers cannot inject a score
  produced from a different or forged evaluation.
- Make benchmark-v2 scoring authoritative in the actual repeated model
  comparison path; v1 scoring remains historical diagnostic output only.
- Keep every excluded record visible and represent no eligible evidence as
  `unavailable` rather than zero or pass.

## Initial Result

The committed v2 fixture has no linked real-shadow-review bundle or external
reviewer/sufficiency attestation. Its report
therefore shows 33 visible records, 0 score-eligible records, 30 pending-expert
records, 3 ambiguous pending-expert records, unavailable adoption metrics, and
an unavailable canary gate. It makes no human/expert or production-readiness
claim.

## Focused Validation

```text
```text
Focused benchmark/comparison/provenance suite: 73 passed
make evidence-selection-semantic-benchmark-v2-check: passed
make artana-evidence-api-lint: passed
make artana-evidence-api-type-check: passed (557 service sources plus strict-import CLIs)
make artana-evidence-api-service-checks: passed
  2,920 collected: 2,893 passed, 27 expected live/environment skips
```
```

Regression coverage includes mismatched pending-evaluation/forged-eligible
report scores, forged and nonexistent real-shadow source exports,
reviewer/source binding drift, model-authored numeric fields, pending-record
score leakage through the real model-comparison path, ambiguous-canary gate
leakage, packet digest drift, explicit known-insufficiency, cross-object metric
forgery, CLI report drift, and honest report wording.

## Human-Only Blocker

An external trusted process must provide authenticated reviewer-identity
attestation bound to the existing study's reviewer roster, review run IDs,
selection-export digest, packet-manifest digest, and independent per-record
packet-sufficiency decisions. The three known-insufficient records require
source-complete v2 packets before that attestation. The repository does not
claim cryptographic human identity, and agent adjudication cannot close this
blocker.
