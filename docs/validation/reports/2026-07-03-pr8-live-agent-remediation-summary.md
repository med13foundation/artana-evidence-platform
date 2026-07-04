# PR-8 Live Agent Remediation Evidence Snapshot

Date: 2026-07-03

Branch: `alvaro/evidence-pr0-quality-harness`

## Scope

This snapshot records the combined PR2-PR8 remediation pass after the strict
agent scorecard fix:

- tiered high-value versus low-value recall
- prompt/schema/taxonomy alignment
- governed new relation proposal scoring
- specificity and argument-fidelity guardrails
- model versus verified CURIE metric split
- migration cleanup for duplicate active proposal fingerprints
- adversarial fixes for adapter provenance, negative-control leakage metrics,
  proposal denominator clarity, model-CURIE trust floors, governed relation-type
  review staging, sentence-scoped specificity pruning, and promoted-proposal
  migration safety
- refreshed strict live-agent feasibility run

## Repository Gates

- `make setup-postgres` passed and applied migration
  `024_unique_active_proposal_fingerprints`.
- `make service-checks` passed after the final adversarial-fix pass, with
  coverage at 87.03% against an 86% floor.

## Strict Live-Agent Result

Command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-03-pr8-live-agent-remediation
```

| Metric | Value |
|---|---:|
| Verdict | RED |
| Verdict reason | Too few CURIE-linked gold endpoints were recovered by extraction. |
| Cases | 30 |
| Gold relations | 25 |
| Extracted candidates | 29 |
| Agent-completed cases | 30 |
| Agent zero-candidate cases | 8 |
| Negative-control cases | 5 |
| Negative-control empty completions | 5 |
| Negative-control leakage cases | 0 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Completed-agent precision | 0.6552 |
| Completed-agent recall | 0.7600 |
| High-value recall | 0.8500 |
| Low-value recall | 0.4000 |
| Completed-agent valuable rate | 0.5517 |
| Generic relation rate | 0.1379 |
| Pruned generic relation siblings | 3 |
| Governed proposal candidates | 2 |
| Governed proposal gold matches | 1 |
| Governed proposal-eligible gold relations | 2 |
| Governed proposal recall among proposal-eligible gold | 0.5000 |
| Governed proposal matches over all gold relations | 0.0400 |
| Candidate CURIE present rate | 0.5690 |
| Verified CURIE match rate | 0.0000 |
| Model CURIE wrong count | 13 |
| Verified CURIE-linked gold endpoint rate | 0.0000 |

## Artifacts

- JSON:
  `reports/relation_feasibility/2026-07-03-pr8-live-agent-remediation/relation_feasibility_report.json`
- Markdown:
  `reports/relation_feasibility/2026-07-03-pr8-live-agent-remediation/relation_feasibility_report.md`

## Hashes

| Artifact | SHA-256 |
|---|---|
| live-agent JSON | `8cf78159b7e4e05123b3f99b80b75041a2ef3cc9bcc71c96c1de1c20ffa8d915` |
| live-agent Markdown | `dd4c2f3ee9e59ceaf3bab17d89d2811e10e412c2556e6a463c9fd54355a6fa29` |

## Interpretation

The live agent path now completes across the benchmark without deterministic
fallback. That is a major validity improvement over the prior fallback-only
strict runs. The rerun also shows live-agent variance, so the exact precision
and recall should be interpreted as a current sample, not a stable production
SLO yet.

The system is still not trusted-graph ready. The strongest remaining blockers
are verified CURIE recovery at 0.0000, 13 wrong model CURIE hints, precision
below 0.80, valuable candidate rate below 0.70, and one missed governed
proposal-eligible relation. High-value recall is 0.8500, which means the agent
is finding many important relations, but it is still not specific and verified
enough to promote without review.
