# PR-16 Repeatability Readiness Evidence Snapshot

Date: 2026-07-05

Branch: `alvaro/evidence-pr16-repeatability-readiness`

Base branch: `alvaro/evidence-pr15-governed-proposal-inventory`

## Scope

PR-16 adds a repeatability/readiness gate for relation feasibility reports:

- Aggregate multiple strict live-agent feasibility reports.
- Require a minimum number of repeated strict runs before any trusted-graph
  readiness claim.
- Fail closed on fallback, invalid agent completion, negative-control leakage,
  raw unknown relation surfaces, and wrong verified CURIE links.
- Fail closed on malformed or schema-drifted input reports, including missing
  or non-numeric required metrics.
- Fail closed if any source feasibility audit is already `RED`.
- Evaluate worst-run precision, recall, high-value recall, valuable-candidate
  rate, generic relation rate, verified CURIE recovery, and entailment coverage.
- Keep the default CLI non-destructive for evidence generation, with
  `--fail-on-not-ready` available for hard CI gating.

## Repository Gates

- Failing import regression was reproduced before implementation.
- `tests/unit/test_relation_feasibility_readiness_gate.py` passed.
- Adversarial review found fail-open handling for malformed reports and
  upstream `RED` reports; both now have negative regressions.
- `make relation-feasibility-quality-gate` now includes the readiness tests and
  passed.
- `make artana-evidence-api-lint` passed.
- `make artana-evidence-api-type-check` passed.
- `--fail-on-not-ready` returned exit status `1` for the current NOT READY
  repeatability gate, as expected.
- `make service-checks` passed with coverage at `86.86%`.

## Strict Live-Agent Repeatability Runs

Commands:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr16-repeatability-run1

PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr16-repeatability-run2

PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr16-repeatability-run3
```

| Run | Precision | Recall | High-value recall | Valuable rate | Generic rate | CURIE endpoint rate | Proposal-eligible recall | Fallback | Invalid agent | Negative leakage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| run1 | 0.8095 | 0.6800 | 0.8500 | 0.8095 | 0.0000 | 0.7027 | 0.5000 | 0 | 0 | 0 |
| run2 | 0.7619 | 0.6400 | 0.8000 | 0.7619 | 0.0000 | 0.6486 | 0.5000 | 0 | 0 | 0 |
| run3 | 0.8095 | 0.6800 | 0.8500 | 0.8095 | 0.0000 | 0.7027 | 1.0000 | 0 | 0 | 0 |

## Readiness Gate

Command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-05-pr16-repeatability-run1 \
  --report reports/relation_feasibility/2026-07-05-pr16-repeatability-run2 \
  --report reports/relation_feasibility/2026-07-05-pr16-repeatability-run3 \
  --output-dir reports/relation_feasibility_readiness/2026-07-05-pr16-repeatability-readiness-r2
```

Result: `not_ready`

Blocking reasons:

- Worst-run completed-agent precision is below target.
- Worst-run high-value recall is below target.
- Worst-run CURIE-linked gold endpoint rate is below target.
- 3 source audit reports were RED.

Required metric errors: none.

Hard failure counts:

| Failure | Count |
|---|---:|
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control leakage | 0 |
| Raw unknown candidate relation types | 0 |
| Raw unknown inventory relation-type surfaces | 0 |
| Wrong verified CURIE links | 0 |

Worst metrics:

| Metric | Value |
|---|---:|
| Completed-agent precision | 0.7619 |
| Completed-agent recall | 0.6400 |
| High-value recall | 0.8000 |
| Completed-agent valuable rate | 0.7619 |
| Generic relation rate | 0.0000 |
| CURIE-linked gold endpoint rate | 0.6486 |
| Verified CURIE match rate | 0.6486 |
| Entailment checked rate | 1.0000 |

Mean metrics:

| Metric | Value |
|---|---:|
| Completed-agent precision | 0.7936 |
| Completed-agent recall | 0.6667 |
| High-value recall | 0.8333 |
| Completed-agent valuable rate | 0.7936 |
| Generic relation rate | 0.0000 |
| CURIE-linked gold endpoint rate | 0.6847 |
| Verified CURIE match rate | 0.6847 |
| Entailment checked rate | 1.0000 |

## Artifacts

- Run 1 JSON:
  `reports/relation_feasibility/2026-07-05-pr16-repeatability-run1/relation_feasibility_report.json`
- Run 2 JSON:
  `reports/relation_feasibility/2026-07-05-pr16-repeatability-run2/relation_feasibility_report.json`
- Run 3 JSON:
  `reports/relation_feasibility/2026-07-05-pr16-repeatability-run3/relation_feasibility_report.json`
- Readiness JSON:
  `reports/relation_feasibility_readiness/2026-07-05-pr16-repeatability-readiness-r2/relation_feasibility_readiness_report.json`
- Readiness Markdown:
  `reports/relation_feasibility_readiness/2026-07-05-pr16-repeatability-readiness-r2/relation_feasibility_readiness_report.md`

## Hashes

| Artifact | SHA-256 |
|---|---|
| run1 JSON | `9f68f62e3754886d5d3356b182167d9c7dd9381fc9f32485f1cef8674ab1702a` |
| run2 JSON | `3a02fc86772401818d08df11fcd0322db334e509506132ffc90b31ee7d13fa88` |
| run3 JSON | `e62048277442a23068688a64e8d7a20fb0d50367d37a52b0a1a87cc99d991d28` |
| readiness JSON | `59d0921b80e4161396de0df56458c4e81caf2bec04fab5dfd45bbe714eb0b79d` |
| readiness Markdown | `c8c93114756703c330f82978f654487bca52b37c8dbc0d157cf5f510e561ca75` |

## Interpretation

The current stack is materially better than the original live-agent path:
fallback, invalid-agent cases, negative leakage, raw unknown relation surfaces,
generic relation noise, and unchecked entailment are all controlled in these
three runs.

It is still not trusted-graph ready. The repeated runs show live variance, and
the worst run misses precision, high-value recall, and verified CURIE recovery
targets. Auto-promotion should remain blocked until entity linking and
precision/recall stability clear this repeatability gate.
