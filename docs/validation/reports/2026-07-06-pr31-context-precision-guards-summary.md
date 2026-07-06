# PR31 Context Precision Guards Summary

## Run Context

- Branch: `alvaro/evidence-pr31-context-precision-guards`
- Base branch: `alvaro/evidence-pr30-trusted-lane-readiness`
- Commit: pending
- Fixture path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Model label: live agent configured by `.env.postgres`

## Goal

Remove repeated trusted-lane false positives by demoting pathway, process, and
cell-context candidates to review-only evidence when they are useful context but
not safe trusted graph evidence.

## Code Changes

- Changed direct target plus broad pathway effect handling so a candidate such
  as `Vemurafenib INHIBITS MAPK signaling` is kept as review-only context when
  the same sentence already contains the trusted direct target relation
  `Vemurafenib TARGETS BRAF V600E`.
- Added a process-effect sibling guard so broad process candidates such as
  `KRAS G12D ACTIVATES pancreatic cancer cell proliferation` are review-only
  when a same-sentence pathway mechanism is the trusted relation target.
- Added a cell-context guard so location/context claims such as
  `JAK-STAT ACTIVATES macrophages` from "activation in macrophages" are
  review-only instead of trusted graph evidence.
- Preserved useful review evidence with explicit review reason codes instead
  of silently treating these candidates as trusted precision failures.

## Artifact Hashes

- `reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run1/relation_feasibility_report.json`:
  `cbe195b3850d850a37a9afd72d1ac7ee883f4a6459312c0e61aa07086d73839b`
- `reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run2/relation_feasibility_report.json`:
  `e439829c6e00453a837fa7a9bc4676356160f8df0f4b295d14a2eb99bc1be956`
- `reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run3/relation_feasibility_report.json`:
  `bd9c73bf9190d8385871e18f1a8d1066e4f43e565087ef0d6b0334090e617c52`
- `reports/relation_feasibility_readiness/2026-07-06-pr31-context-precision-guards-runs1-3/relation_feasibility_readiness_report.json`:
  `f01a97118347ca22312174ecbd972a585c83f71906d86d86ee90580cf74e2159`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr31-context-precision-guards-runs1-3/relation_feasibility_failure_analysis_report.json`:
  `271140f84c94058d783fc191be83b3a8d2801c93d3b602dbb1da3151bc2a462a`

## Validation

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_demotes_pathway_target_sibling

uv run ruff check \
  services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py

make relation-feasibility-quality-gate

make service-checks
```

Strict live-agent runs:

```bash
set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run1

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run2

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run3
```

Aggregate reports:

```bash
uv run python scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run1 \
  --report reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run2 \
  --report reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run3 \
  --output-dir reports/relation_feasibility_readiness/2026-07-06-pr31-context-precision-guards-runs1-3

uv run python scripts/summarize_relation_readiness_failures.py \
  --report run1=reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run1 \
  --report run2=reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run2 \
  --report run3=reports/relation_feasibility/2026-07-06-pr31-context-precision-guards-run3 \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-06-pr31-context-precision-guards-runs1-3
```

## Three-Run Readiness Result

Trusted graph readiness is **READY** for the measured v3 live-agent trusted
lane.

| Metric | Worst | Mean |
|---|---:|---:|
| Trusted candidate precision | 1.0000 | 1.0000 |
| Trusted-eligible high-value recall | 1.0000 | 1.0000 |
| Trusted candidate valuable rate | 1.0000 | 1.0000 |
| Trusted candidate generic relation rate | 0.0000 | 0.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 | 1.0000 |
| Entailment checked rate | 1.0000 | 1.0000 |
| Completed-agent precision | 0.8750 | 0.8938 |
| Completed-agent recall | 0.9333 | 0.9333 |
| All-candidate generic relation rate | 0.2903 | 0.2769 |

Hard failures across runs1-3:

- fallback case count: `0`
- invalid agent case count: `0`
- negative control leakage count: `0`
- raw unknown relation type count: `0`
- raw unknown relation type surface count: `0`
- wrong verified CURIE link count: `0`
- weak claim trusted leakage count: `0`
- review-only gold trusted leakage count: `0`

## Interpretation

PR31 is the first measured slice where the v3 live-agent trusted lane reaches
repeatable trusted graph readiness. The improvement is not from deterministic
fallback and not from hiding failed agent runs:

- all 40 cases completed through the live agent in each run
- fallback stayed at `0`
- trusted candidate precision recovered from the PR30 worst run `0.7778` to
  `1.0000`
- trusted-eligible endpoint recovery recovered from the PR30 worst run `0.8571`
  to `1.0000`
- trusted generic relation rate stayed at `0.0000`

The remaining issues are review/all-candidate burden, not trusted graph
auto-promotion blockers:

- repeated low-value misses remain for weak EGFR response and weak MET
  resistance review evidence
- review-only/all-candidate false positives still include PAH/elevated
  phenylalanine, Vemurafenib/MAPK signaling, and MET/EGFR inhibition
- all-candidate CURIE-linked endpoint rate remains `0.7250` because many
  endpoints are intentionally review-only and not trusted identifiers

## Remaining Work

- Keep PR31 stacked after PR30 because it relies on PR30 trusted-lane readiness
  accounting to prove the difference between trusted auto-promotion and review
  burden.
- Keep the next follow-up focused on review-lane usefulness: recover weak
  EGFR/MET review evidence without allowing weak claims into trusted evidence.
