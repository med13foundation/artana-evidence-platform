# PR27 Benchmark V3 And Generated Proof Docs Summary

Date: 2026-07-06

Branch: `alvaro/evidence-pr27-benchmark-v3-doc-proof`

Run commit: `6e67477+pr27-working-tree`

## Goal

PR27 expands the relation-feasibility benchmark beyond the curated v2 seed and
adds generated Markdown summaries from JSON artifacts so evidence reports can
be reproduced instead of hand-copied.

This PR is a measurement and proof-doc slice. It does not claim final
trusted-graph readiness.

## Implementation

- Added fixture validation rules for duplicate case IDs, missing support
  sentences, incomplete gold relation fields, trusted high-value rows missing
  endpoint CURIEs, negative controls with gold relations, and weak/low-value
  rows missing `value_level`.
- Added topic-specific fixture validation so broad coverage cannot be faked by
  labels alone: long-document cases must be long enough, negated near-miss
  cases must list co-mentioned entities, weak rows must be review-only, and
  trusted high-value rows must require entailment.
- Added `biomedical_relation_goldset_v3.json` with 40 cases:
  - 20 high-value specific relation cases
  - 10 low-value review-only weak or hedged cases
  - 10 negative controls
- Covered oncology drug response, rare disease gene-to-phenotype,
  variant-to-disease risk, pathway regulation, biomarker/treatment response,
  long-document chunking, and adversarial negated near-miss cases.
- Added `generate_relation_feasibility_summary.py`, which writes Markdown
  summaries containing run context, artifact hashes, key metrics, blocking
  reasons, warning reasons, remaining failures, and optional
  failure/readiness artifacts.
- Added the fixture and summary tests to `relation-feasibility-quality-gate`.

## Generated Evidence Artifacts

Tracked v2 seed proof packet:

- `docs/validation/reports/2026-07-06-pr27-v2-relation-feasibility-report.json`
- `docs/validation/reports/2026-07-06-pr27-v2-generated-summary.md`

Tracked v3 expanded proof packet:

- `docs/validation/reports/2026-07-06-pr27-v3-relation-feasibility-report.json`
- `docs/validation/reports/2026-07-06-pr27-v3-failure-analysis-report.json`
- `docs/validation/reports/2026-07-06-pr27-v3-generated-summary.md`

## V2 Seed Result

| Metric | Value |
|---|---:|
| Verdict | GREEN |
| Cases | 30 |
| Completed-agent precision | 1.0000 |
| Completed-agent recall | 1.0000 |
| High-value recall | 1.0000 |
| Trusted high-value recall | 0.8500 |
| Low-value review recall | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 |
| Completed-agent valuable candidate rate | 0.8000 |
| Generic relation rate | 0.1200 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control leakage | 0 |
| Weak-claim trusted leakage | 0 |
| Wrong verified CURIE links | 0 |

## V3 Expanded Result

| Metric | Value |
|---|---:|
| Verdict | RED |
| Cases | 40 |
| Completed-agent precision | 0.7333 |
| Completed-agent recall | 0.7333 |
| High-value recall | 0.7000 |
| Trusted high-value recall | 0.2000 |
| Low-value review recall | 0.8000 |
| Trusted-eligible CURIE endpoint rate | 0.3000 |
| Completed-agent valuable candidate rate | 0.3667 |
| Generic relation rate | 0.3000 |
| Model-only wrong CURIE hints | 9 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control leakage | 0 |
| Weak-claim trusted leakage | 0 |
| Wrong verified CURIE links | 0 |

Blocking reason:

- Too few trusted-eligible CURIE-linked gold endpoints were recovered by
  extraction.

Failure attribution:

- Missed gold relations: 8
- False-positive candidate patterns: 8
- CURIE-gap rows: 28

## Interpretation

The v2 seed benchmark remains green, but the expanded v3 fixture is red. That
means the earlier seed fixture was not enough evidence for trusted-graph
readiness.

The live agent path is still behaving safely on the hard safety invariants:
fallback cases, invalid-agent cases, negative-control leakage, weak-claim
trusted leakage, and wrong verified CURIE links are all zero in v3 run2.

The remaining blockers are quality and specificity blockers:

- high-value biomedical recall is too low on the broader fixture
- trusted high-value recall is far below the readiness target
- trusted-eligible endpoint recovery is far below the readiness target
- generic relation rate is too high
- valuable candidate rate is too low
- several false positives are near-miss specificity errors, such as shortened
  subjects, overly broad disease or tumor objects, and pathway-vs-target
  substitutions

This is useful negative evidence: PR27 raises the benchmark difficulty and
prevents a green v2 seed run from being mistaken for production confidence.

## Validation Commands

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_fixture_validation.py \
  tests/unit/test_generate_relation_feasibility_summary.py \
  tests/unit/test_control_files.py \
  -q
```

```bash
make relation-feasibility-quality-gate
```

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr27-v2-run1'
```

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr27-v3-run2'
```

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/2026-07-06-pr27-v3-run2/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-06-pr27-v3-run2
```

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_generate_relation_feasibility_summary.py::test_pr27_committed_generated_summaries_are_reproducible \
  -q
```

```bash
git diff --check
```

```bash
PATH="$(pwd)/.venv/bin:$PATH" pre-commit run --all-files
```

```bash
make service-checks
```

Final local validation:

- Focused PR27 tests passed: 35 tests.
- `make relation-feasibility-quality-gate` passed: 81 tests.
- `git diff --check` passed.
- `pre-commit run --all-files` passed.
- `make service-checks` passed with coverage 87.03%.
- Adversarial re-review passed after fixing tracked proof docs, generated
  metrics/warnings, and topic-specific fixture validation.

## Remaining Risk

PR27 makes the evaluation stronger, but it intentionally leaves the product
readiness gate red. The next implementation loop should attack the v3 failure
classes directly: broader biomedical relation recall, stricter near-miss
specificity, better verified endpoint linking, and lower generic relation
noise. A stronger model may help, but it must be proven through the PR25
repeatability/model A/B gate without regressing the zero-leakage safety
invariants.
