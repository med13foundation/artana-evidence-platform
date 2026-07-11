# PR-14 Entailment Coverage Hardening Evidence Snapshot

Date: 2026-07-05

Branch: `alvaro/evidence-pr14-entailment-coverage-hardening`

Base branch: `alvaro/evidence-pr13-specificity-noise-reduction`

## Scope

PR-14 makes the relation feasibility scorecard fail closed for required
entailment checks:

- Treat missing source grounding or missing relation arguments as checked
  `NEUTRAL` support instead of unchecked support.
- Preserve the `support_not_entailed` quality flag for those candidates.
- Preserve adversarial warnings for ungrounded evidence sentences after the
  fail-closed entailment change.
- Remove the adversarial `entailment_not_checked` illusion when missing
  arguments are already counted as checked non-entailment.
- Keep fallback/unavailable strict-agent runs ineligible for success.

## Repository Gates

- Failing regression was reproduced before implementation.
- Focused entailment regressions passed.
- Adversarial review found a missing report-level warning for ungrounded
  sentences; a regression and `source_sentence_not_grounded` finding were added.
- `tests/unit/test_relation_feasibility_audit.py` passed.
- `make relation-feasibility-quality-gate` passed.
- `make artana-evidence-api-lint` passed.
- `make artana-evidence-api-type-check` passed.
- `make service-checks` passed with coverage at `86.86%`.

## Strict Live-Agent Result

Command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 \
  scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr14-entailment-coverage-hardening
```

| Metric | PR-13 live | PR-14 live |
|---|---:|---:|
| Verdict | RED | RED |
| Completed-agent precision | 0.8095 | 0.7727 |
| Completed-agent recall | 0.6800 | 0.6800 |
| High-value recall | 0.8500 | 0.8500 |
| Completed-agent valuable rate | 0.8095 | 0.7727 |
| Generic relation rate | 0.0000 | 0.0455 |
| Pruned generic relation siblings | 6 | 5 |
| Quality-filtered candidates | 5 | 5 |
| Candidate CURIE present rate | 0.9048 | 0.8636 |
| Verified CURIE match rate | 0.7027 | 0.7027 |
| Entailment checked rate | 1.0000 | 1.0000 |
| Entailment supported rate | 0.9048 | 0.9091 |
| Fallback cases | 0 | 0 |
| Invalid strict-agent cases | 0 | 0 |
| Negative-control leakage cases | 0 | 0 |
| Governed proposal recall among proposal-eligible gold | 1.0000 | 1.0000 |

## Artifacts

- JSON:
  `reports/relation_feasibility/2026-07-05-pr14-entailment-coverage-hardening/relation_feasibility_report.json`
- Markdown:
  `reports/relation_feasibility/2026-07-05-pr14-entailment-coverage-hardening/relation_feasibility_report.md`

## Hashes

| Artifact | SHA-256 |
|---|---|
| live-agent JSON | `479126236f20a4bba00585e874e9a368ea5c02efa9ec223e4f0870ab481c7edd` |
| live-agent Markdown | `7ef2e3c6db0898d2f99c77c5acd64773d384dda2cd753f65f1bf5fa7716ff012` |

## Interpretation

The strict live-agent path completed without deterministic fallback. PR-14
hardens the scorecard so required entailment can no longer disappear into an
unchecked bucket when grounding or argument evidence is broken.

The PR is still not trusted-graph ready by itself. The current live-agent run
remains RED because verified CURIE-linked endpoint recovery is below target,
and precision is still below the trusted graph construction target.
