# PR35 Benchmark V4 100-Case Proof Summary

## Run Context

- Branch: `alvaro/evidence-pr35-benchmark-v4-100-case-proof`
- Base branch: `alvaro/evidence-pr34-live-model-ab-proof`
- Fixture path:
  `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json`

## Goal

Make the Definition-of-Green scale requirement executable. The tracker says the
initiative is green only when the gold set has at least 100 labeled documents
and CI enforces the quality invariants. PR35 closes the benchmark-size gap by
adding a v4 fixture and a regression test that fails when the fixture is too
small or too narrow.

## Code And Data Changes

- Added `biomedical_relation_goldset_v4.json`.
- Kept the 40-case v3 fixture as the regression seed.
- Added 60 labeled synthetic cases covering:
  - high-value specific relation extraction,
  - low-value review-only evidence,
  - hard negative controls,
  - long-document chunk-local extraction,
  - adversarial negated near-misses.
- Added diversity guards so the fixture cannot reach 100 cases by padding
  duplicate relation signatures or by adding broad pathway/process and broad
  gene-predisposition rows as trusted v4 gold.
- Added a v4 fixture-validation regression test requiring:
  - at least 100 cases,
  - at least 50 high-value specific cases,
  - at least 25 low-value review cases,
  - at least 25 negative controls,
  - at least 5 long-document cases,
  - at least 5 adversarial negated near-miss cases.

## Fixture Coverage

| Metric | Value |
|---|---:|
| Validator issue count | 0 |
| Total cases | 100 |
| Strong-specific cases | 50 |
| Weak review-only cases | 25 |
| Negative controls | 25 |
| High-value specific cases | 50 |
| True low-value review gold cases | 25 |
| Any review-only gold cases | 62 |
| Gold relation signatures | 75 |
| Unique gold relation signatures | 74 |
| Repeated gold relation signatures | 1 |
| Long-document topic cases | 8 |
| Adversarial negated near-miss cases | 6 |

Topic distribution:

| Topic | Cases |
|---|---:|
| oncology_drug_response | 31 |
| pathway_regulation | 30 |
| rare_disease_gene_phenotype | 23 |
| biomarker_treatment_response | 19 |
| variant_disease_risk | 18 |
| negative_control | 25 |
| low_value_review | 25 |
| long_document_chunking | 8 |
| adversarial_negated_near_miss | 6 |

## RED/GREEN Proof

Focused fixture validation:

```bash
uv run pytest tests/unit/test_relation_feasibility_fixture_validation.py -q
```

RED result before the v4 fixture was added:

- `test_v4_fixture_reaches_definition_of_green_scale` failed with
  `FileNotFoundError` for
  `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json`.

GREEN result after adding the fixture:

- `7 passed`

Fixture coverage command:

```bash
uv run python - <<'PY'
from pathlib import Path
from scripts.validation.relation_feasibility.fixture_checks import fixture_coverage

coverage = fixture_coverage(
    Path(
        "scripts/validation/relation_feasibility/fixtures/"
        "biomedical_relation_goldset_v4.json"
    )
)
print(coverage)
PY
```

Result:

- `issue_count=0`
- `case_count=100`
- `gold_relation_signature_count=75`
- `unique_gold_relation_signature_count=74`
- `repeated_gold_relation_signature_count=1`
- `high_value_specific_case_count=50`
- `true_low_value_review_case_count=25`
- `low_value_review_case_count=62` for the broader review-only-or-low
  compatibility counter
- `negative_control_case_count=25`

Adversarial review fixes:

- Added `true_low_value_review_case_count` so high-value review-only rows cannot
  satisfy the true low-value coverage requirement.
- Added relation-signature diversity metrics and a v4 assertion allowing only
  the inherited v3 IL6 strong/weak contrast to repeat.
- Changed new broad pathway/process and broad HGNC gene-predisposition v4 rows
  to review-only gold, and rewrote duplicate drug/variant rows into distinct
  molecular-subtype or response-review cases.

## Final Local Validation

Touched-file lint:

```bash
uv run ruff check \
  scripts/validation/relation_feasibility/fixture_checks/validation.py \
  tests/unit/test_relation_feasibility_fixture_validation.py
```

Result: passed.

Relation-feasibility quality gate:

```bash
make relation-feasibility-quality-gate
```

Result: passed.

Aggregate service gate:

```bash
make service-checks
```

Result: passed with coverage `87.03%`.

Adversarial re-review:

- Result: PASS.
- Prior blockers fixed: true low-value counting, duplicate-signature padding,
  broad v4 trusted pathway/process rows, and broad v4 trusted HGNC
  gene-predisposition rows.

## Interpretation

PR35 does not claim final trusted-graph readiness. It raises the evidence bar:
the system now has a 100-case fixture and a test that prevents the Definition of
Green from being satisfied by a small benchmark.

The next required proof is to run the strict live-agent readiness loop against
the v4 fixture before claiming trusted-graph readiness.
