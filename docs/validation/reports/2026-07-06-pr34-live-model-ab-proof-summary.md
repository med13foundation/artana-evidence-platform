# PR34 Live Model A/B Proof Summary

## Run Context

- Branch: `alvaro/evidence-pr34-live-model-ab-proof`
- Base branch: `alvaro/evidence-pr33-review-burden-pruning`
- Commit: PR branch head
- Fixture path:
  `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Current model: `openai:gpt-5.4-mini`
- Candidate model: `openai:gpt-5`

## Goal

Close the pending stronger-model question with live evidence instead of model
intuition. A candidate model can be recommended only when it completes the same
repeatability gate as the current model, has zero hard safety failures, and does
not regress trusted endpoint recovery.

## Code Changes

- Added `--cases` to `scripts/run_relation_model_comparison.py` so repeated
  model A/B audits can pin the same benchmark fixture used by trusted-readiness
  runs.
- Made run-mode model comparison fail closed when a live audit subprocess exits
  nonzero. The CLI now writes a comparison report with `KEEP_CURRENT`,
  `audit_failures`, blocking reasons, and safety failures instead of crashing
  without an artifact.
- Added Markdown rendering for audit failures so reviewers do not need to open
  JSON to see why a candidate model was rejected.

## Artifact Hashes

- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/relation_model_comparison_report.json`:
  `ba9e7fffcf24dce3cf730933f4d1a27aac7c56f17e9e33b9b1a85d388b5c968b`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/runs/current/run1/relation_feasibility_report.json`:
  `552f0bf5f7dbab09075a3fc74a91811d00f4b4debd45f807f0c4490eaa6d4070`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/runs/current/run2/relation_feasibility_report.json`:
  `16f09f98b6c208b6fd3d539f90e7c79f62c49da1c161d1f01aa8f651854bcf97`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/runs/current/run3/relation_feasibility_report.json`:
  `5ba655a0873072403e3344c2936b68b87430161a3b694e14ddebbce2f488e972`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/runs/candidate/run1/relation_feasibility_report.json`:
  `cdad70287950b4db7c2f4e58e2d960637a6696801d3c00d5344b302f050bccf8`

## Validation

RED/GREEN regression for fixture pinning:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_model_comparison.py::test_model_comparison_cli_passes_cases_to_repeated_audit_runs \
  -q
```

Result:

- before implementation: failed because `--cases` was not recognized
- after implementation: passed

RED/GREEN regression for failed candidate audit reporting:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_model_comparison.py::test_model_comparison_cli_writes_fail_closed_report_for_failed_candidate_run \
  -q
```

Result:

- before implementation: failed with escaped `CalledProcessError`
- after implementation: passed and wrote `audit_failures`

Symmetric current-model failure regression:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_model_comparison.py::test_model_comparison_cli_writes_fail_closed_report_for_failed_current_run \
  -q
```

Result: passed after adversarial review.

Focused model-comparison suite:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_model_comparison.py \
  -q
```

Result: `13 passed`

Quality gate:

```bash
make relation-feasibility-quality-gate
```

Result: passed.

Full service gate:

```bash
make service-checks
```

Result: passed with coverage `87.03%` against the `86%` floor.

Live model A/B command:

```bash
set -a; source .env.postgres; \
export ARTANA_STRONGER_MODEL_CANDIDATE=openai:gpt-5; set +a; \
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_model_comparison.py \
  --current-model-label openai:gpt-5.4-mini \
  --candidate-model-label openai:gpt-5 \
  --runs-per-model 3 \
  --run-audits \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof
```

Result:

- current model completed three strict v3 live-agent runs
- candidate model completed one strict v3 live-agent run
- candidate model run2 failed preflight with `LiteLLM timed out after 1 attempts`
- comparison report decision: `KEEP_CURRENT`

## Model Comparison Result

| Model | Completed runs | Decision status |
|---|---:|---|
| `openai:gpt-5.4-mini` | 3/3 | READY current baseline |
| `openai:gpt-5` | 1/3 | Not adoptable |

Current model worst-run readiness:

| Metric | Worst |
|---|---:|
| Trusted graph readiness | READY |
| Completed-agent precision | 1.0000 |
| Completed-agent recall | 1.0000 |
| Completed-agent valuable candidate rate | 0.5333 |
| High-value recall | 1.0000 |
| Trusted candidate precision | 1.0000 |
| Trusted candidate valuable rate | 1.0000 |
| Trusted candidate generic rate | 0.0000 |
| Trusted-eligible high-value recall | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 |
| Entailment checked rate | 1.0000 |
| Verified CURIE match rate | 0.7250 |

Current model hard failures across runs1-3:

- fallback case count: `0`
- invalid agent case count: `0`
- negative control leakage count: `0`
- raw unknown relation type count: `0`
- raw unknown relation type surface count: `0`
- wrong verified CURIE link count: `0`
- weak claim trusted leakage count: `0`
- review-only gold trusted leakage count: `0`

Candidate completed run1:

| Metric | Value |
|---|---:|
| Verdict | GREEN |
| Completed-agent precision | 1.0000 |
| Completed-agent recall | 0.9667 |
| Completed-agent valuable candidate rate | 0.5172 |
| High-value recall | 0.9500 |
| Trusted candidate precision | 1.0000 |
| Trusted-eligible high-value recall | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 |
| Fallback cases | 0 |
| Invalid agent cases | 0 |
| Wrong verified CURIE links | 0 |

Fail-closed comparison decision:

- adopted model label: `null`
- blocking reasons:
  - `candidate audit run failed.`
  - `candidate report count must match --runs-per-model; expected 3, got 1.`
- safety failures:
  - `candidate run2 exited 2`

## Interpretation

PR34 answers the stronger-model question for the current trusted-readiness
stack: do not switch the default extraction model to `openai:gpt-5` from this
evidence.

The current configured model is already repeatably READY on the v3 trusted
lane. The stronger candidate did not complete the three-run gate reliably, and
its single completed run had lower completed-agent recall, high-value recall,
and valuable candidate rate than the current model.

The useful follow-up is not to rely on a stronger model as a shortcut. Future
model work should first add explicit latency/cost fields and then retry a
candidate only if it can pass the same three-run gate without preflight
timeouts or safety regressions.

Adversarial review found no blockers. It identified two improvements, both
applied here: symmetric failed-current-run coverage and softer wording around
candidate latency because explicit latency/cost fields are not yet recorded.
