# PR-25 Repeatability And Model A/B Harness

Date: 2026-07-06

Branch: `alvaro/evidence-pr25-repeatability-model-ab`

Base branch: `alvaro/evidence-pr24-grounding-decision-table`

Commit: see PR head commit

## Goal

PR-25 adds the harness needed to prove repeatability and evaluate a stronger
model with evidence. The candidate model must not win by improving recall while
introducing fallback, invalid agent output, wrong verified CURIE links, weak
claim trusted leakage, or trusted-endpoint regression.

## What Changed

- Added an artifact-only model comparison module:
  `scripts/validation/relation_feasibility/model_comparison.py`.
- Added `scripts/run_relation_model_comparison.py`, a thin wrapper that can:
  - compare already-written current/candidate report artifacts, or
  - run repeated strict live-agent audits into per-model run directories.
- Made run mode fail closed unless `ARTANA_STRONGER_MODEL_CANDIDATE` is set.
- Reused the readiness gate as the source of adoption truth:
  worst-run metrics, hard-failure counts, source RED reports, and required metric
  errors.
- Extended failure-analysis model comparison rows with trusted-lane, low-value
  review, entailment, and hard-failure totals.
- Added model-comparison tests to `make relation-feasibility-quality-gate`.

## Validation

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_model_comparison.py \
  tests/unit/test_relation_feasibility_failure_analysis.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  -q
```

Result: passed, 23 tests.

```bash
make relation-feasibility-quality-gate
```

Result: passed, 74 tests.

```bash
uv run --python python3.13 --with ruff ruff check \
  scripts/run_relation_model_comparison.py \
  scripts/validation/relation_feasibility/model_comparison.py \
  scripts/validation/relation_feasibility/failure_analysis.py \
  tests/unit/test_relation_feasibility_model_comparison.py \
  tests/unit/test_relation_feasibility_failure_analysis.py
```

Result: all checks passed.

Fail-closed candidate-env check:

```bash
bash -lc 'set -a; source .env.postgres >/dev/null 2>&1 || true; \
  unset ARTANA_STRONGER_MODEL_CANDIDATE; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_model_comparison.py \
  --current-model-label current \
  --candidate-model-label candidate \
  --runs-per-model 3 \
  --run-audits \
  --output-dir reports/relation_model_comparison/2026-07-06-pr25-missing-candidate-check'
```

Result: exited nonzero with
`ARTANA_STRONGER_MODEL_CANDIDATE must be set when --run-audits is used`.

## Pending Live Evidence

`.env.postgres` currently sets
`ARTANA_AI_EVIDENCE_EXTRACTION_MODEL=openai:gpt-5.4-mini`, but does not set
`ARTANA_STRONGER_MODEL_CANDIDATE`.

After choosing an approved candidate model, run:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_model_comparison.py \
  --current-model-label current \
  --candidate-model-label candidate \
  --runs-per-model 3 \
  --run-audits \
  --output-dir reports/relation_model_comparison/2026-07-06-pr25-model-comparison'
```

The comparison report can recommend the candidate only if:

- the candidate readiness gate is ready on worst-run metrics,
- fallback, invalid-agent, negative leakage, raw unknown relation type, wrong
  verified CURIE, and weak-claim trusted leakage counts are all zero,
- trusted-eligible endpoint recovery does not regress versus the current model.

## Interpretation

PR-25 is not yet a live stronger-model result. It is the measurement and
adoption harness. The live A/B decision remains pending until
`ARTANA_STRONGER_MODEL_CANDIDATE` is configured and the six strict runs complete.
