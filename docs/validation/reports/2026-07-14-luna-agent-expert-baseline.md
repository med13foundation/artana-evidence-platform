# July 14 Luna Agent-Expert Baseline

Created: 2026-07-14

Versioned: 2026-07-16

Status: historical diagnostic baseline; not confirmatory readiness evidence

## Purpose

This record preserves the July 14 diagnostic counts used to prioritize the
Trusted Claim Recovery Plan. The original report was written below the ignored
top-level `reports/` directory and was not committed. It is therefore not
available in a fresh checkout and cannot receive immutable-run,
provider-authentication, or scientific-readiness credit.

The counts remain useful as explicit root-cause observations. Later PRs must
replace them with prospectively frozen, hash-addressed artifacts rather than
silently treating this reconstruction as equivalent to the missing raw run.

## Recorded Counts

The 100-case relation set was run three times. The separate 47-case review set
was deliberately risk-enriched and does not estimate prevalence.

| Measure | Recorded result | Denominator |
|---|---:|---:|
| Strict agent completion | 300 | 300 attempts |
| Credited deterministic fallback | 0 | 300 attempts |
| Invalid structured agent results | 0 | 300 attempts |
| Stable cases across three runs | 88 | 100 cases |
| Worst-run generic relation rate | 36.76% | worst of three 100-case runs |
| Worst-run verified CURIE match rate | 75.86% | worst of three 100-case runs |
| Negative-control leakage | 1 | frozen negative controls |
| Source-reviewed packet sufficiency | 8 | 47 review cases |
| Final reviewer action `keep` | 1 | 47 review cases |
| Strong source provenance | 2 | 47 review cases |
| Generic or overstated outcomes | 13 | 47 review cases |

Recorded decision: **not ready for automatic trusted-graph promotion**.

## Provenance Boundary

The missing original report prevents an independent reviewer from checking its
case-level outputs, provider response IDs, prompt and fixture hashes, or exact
metric implementation. Consequently:

- these values may establish failure hypotheses but not a merge-quality delta;
- they may not satisfy a scientific precision, recall, or readiness gate;
- they may not be used as a frozen baseline for model comparison;
- any later report must link raw categorical outputs and deterministic scoring;
- any semantic provider call receiving credit must include retrievable provider
  response IDs and matching canonical output hashes.

## Committed Supporting Evidence

The following earlier committed artifacts support narrower execution and
fallback observations. They do not reconstruct the missing 47-case review
packet or independently validate every count above.

| Artifact | SHA-256 |
|---|---|
| `docs/validation/reports/semantic-model-comparisons/2026-07-13-pr6-gpt-5.6-luna-v3/semantic_model_comparison_manifest.json` | `601b430bc34fe368a1656abdb1594b730188ccbd9bf2a89a94232212164be7a8` |
| `docs/validation/reports/semantic-model-comparisons/2026-07-13-pr6-gpt-5.6-luna-v3/semantic_model_comparison_report.json` | `f159482dd5cab13c32b04487df5ff66808439309abfe166012a06fddc708763b` |
| `docs/validation/codex-agent-expert-evaluation-protocol.md` | `07b9885622f4469769f9a84576db99f721ae0dc38bfa79da45b6828f91614713` |

## Replacement Requirement

The next scientific experiment must freeze its source snapshots, complete
n-ary gold labels, prompts, model settings, categorical outputs, provider
receipts, and deterministic scorer before execution. Its worst-run metrics and
paired case transitions replace this historical baseline for scientific
decisions.
