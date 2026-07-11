# PR-22 Low-Value Review Lane And Trusted Verdict Split

Date: 2026-07-05

Branch: `alvaro/evidence-pr22-low-value-review-lane`

Base branch: `alvaro/evidence-pr21-verified-grounding-closure`

Commit: pending local packaging

## Goal

PR-22 separates trusted-eligible endpoint recovery from low-value review evidence
so weak or hedged claims can be measured without blocking trusted high-value
promotion or leaking into trusted graph evidence.

## What Changed

- Added review-only candidate status and reason codes to extracted relation
  contracts and relation feasibility models.
- Added `review_only_candidate_policy.py` for hedged language such as trend-only,
  possible biomarker, may-regulate, and correlation-only claims.
- Preserved uncertain but useful weak claims as `review_only` instead of either
  dropping them or marking them trusted.
- Carried `review_only` status and reason codes into document proposal metadata,
  added a `review_only_candidate` trust-floor failure, and protected review
  metadata from promotion-request overrides.
- Added endpoint metric splits:
  - `trusted_eligible_curie_linked_gold_endpoint_rate`
  - `low_value_review_curie_endpoint_capture_rate`
  - `weak_claim_trusted_leakage_count`
- Updated single-run verdict logic to block on trusted-eligible endpoint recovery,
  not all-gold endpoint recovery.
- Kept all-gold endpoint recovery as a diagnostic metric.
- Refactored relation feasibility scoring/readiness helpers so the new gates are
  owned by smaller focused functions.

## Validation Commands

Focused regression:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_audit.py::test_verdict_uses_trusted_eligible_endpoint_rate_not_all_gold_rate \
  -q
```

Affected tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_proposal_actions.py \
  tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  -q
```

Quality gate and lint:

```bash
make relation-feasibility-quality-gate

uv run --python python3.13 --with ruff ruff check \
  scripts/run_relation_feasibility_audit.py \
  scripts/validation/relation_feasibility/models.py \
  scripts/validation/relation_feasibility/readiness.py \
  scripts/validation/relation_feasibility/reporting.py \
  scripts/validation/relation_feasibility/runner.py \
  scripts/validation/relation_feasibility/scoring.py \
  scripts/validation/relation_feasibility/summary_scoring.py \
  scripts/validation/relation_feasibility/trusted_metric_rules.py \
  scripts/validation/relation_feasibility/endpoint_metrics.py \
  services/artana_evidence_api/document_extraction_contracts.py \
  services/artana_evidence_api/document_extraction_drafts.py \
  services/artana_evidence_api/document_extraction_support/trust_ladder.py \
  services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py \
  services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py \
  services/artana_evidence_api/document_extraction_support/review_policy/review_only_candidate_policy.py \
  services/artana_evidence_api/proposal_actions.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_proposal_actions.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
  tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_readiness_gate.py

git diff --check

make service-checks
```

Strict live-agent audit:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run4'
```

Failure attribution:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr22-low-value-review-lane-run4
```

## Live-Agent Result

Source artifact:

- `reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_failure_analysis_report.md`

| Metric | PR22 run4 value | Status |
|---|---:|---|
| Verdict | GREEN | Passing single-run gate |
| Blocking reasons | 0 | Passing |
| Warning reasons | 0 | Passing |
| Completed-agent precision | 1.0000 | Passing |
| Completed-agent recall | 0.8800 | Passing |
| Completed-agent valuable rate | 0.9091 | Passing |
| High-value recall | 1.0000 | Passing |
| Trusted high-value recall | 0.8500 | Passing, no margin |
| Trusted-eligible CURIE-linked gold endpoint rate | 1.0000 | Passing |
| All-gold CURIE-linked endpoint rate | 0.9048 | Diagnostic only |
| Low-value review recall | 0.4000 | Needs PR23 |
| Low-value review CURIE endpoint capture rate | 0.2000 | Needs PR23/PR24 |
| Weak-claim trusted leakage count | 0 | Passing |
| Fallback cases | 0 | Passing |
| Invalid strict-agent cases | 0 | Passing |
| Negative-control leakage cases | 0 | Passing |
| Wrong verified CURIE links | 0 | Passing |
| False positives | 0 | Passing |

## Remaining Failure Attribution

Missed low-value review relations:

- `weak_akt_trend_survival`: `AKT activation ASSOCIATED_WITH reduced survival`
- `weak_med13_may_link_chd`: `MED13 ASSOCIATED_WITH congenital heart disease`
- `weak_met_correlated_resistance`: `MET amplification ASSOCIATED_WITH resistance`

Remaining CURIE gaps:

- `aggressive tumor growth`
- `ERK phosphorylation`
- `response to pembrolizumab`
- `HRD score`
- `platinum sensitivity`
- `inflammatory signaling`

## Artifact Hashes

| Artifact | SHA-256 |
|---|---|
| relation feasibility JSON | `632cfb250048a3c55427cad8552139f715372139c59bb0686211d8059fdf7496` |
| relation feasibility Markdown | `8350468d014406a4d97ca05953151ead06c21184b8edcf11f7cf3eba7c8014ed` |
| failure analysis JSON | `b115a04be14b6bcac55c1b579ae6b877a855a83ef9238612187e67f5de34ddec` |
| failure analysis Markdown | `eb4e3b85c10f70a20b2c68874e13ed26d72a93cc7a8806f8a8ae9a79566a47f9` |

## Final Validation Notes

- Focused RED/GREEN regressions were added for review-only trust blocking,
  proposal draft metadata propagation, and promotion metadata override
  protection.
- `make service-checks` passed on 2026-07-05/2026-07-06 UTC, including static
  checks, contract checks, architecture checks, migrations, DB-backed tests, and
  coverage at 87.03% against the 86% gate.
- Final adversarial review found no remaining PR22 API-lane trust blocker. It
  confirmed graph-service independent review-only rejection is still a follow-up
  PR26 requirement.

## Interpretation

PR-22 fixes the trusted-lane measurement contract. The strict live-agent path
now has a GREEN single-run verdict because trusted-eligible endpoint recovery is
complete on this fixture, while weak low-value evidence is measured separately
and the production proposal path now blocks review-only candidates from the
trusted tier with verifier-owned metadata.

This is not final trusted-graph readiness. The next lanes still need to improve
low-value review recall, document endpoint grounding decisions, prove
repeatability across at least three strict live-agent runs, and verify graph-side
promotion enforcement.
