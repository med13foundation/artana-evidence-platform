# PR-23 Low-Value Review Recall

Date: 2026-07-05

Branch: `alvaro/evidence-pr23-low-value-review-recall`

Base branch: `alvaro/evidence-pr22-low-value-review-lane`

Pull request: https://github.com/med13foundation/artana-evidence-platform/pull/106

Commit: PR head commit after packaging

## Goal

PR-23 improves live-agent recall for weak but useful low-value evidence without
letting weak claims become trusted graph evidence. It keeps the deterministic
fallback out of the success path.

## What Changed

- Added `review_status` and `review_reason_codes` to the LLM extraction schema
  so the agent can mark weak claims as review-only.
- Added prompt guidance and examples for hedged, trend-only, may-link,
  possible-biomarker, and correlation-only review evidence.
- Added a second live-agent extraction pass for weak review-only relations.
- Forced every weak-pass candidate into `review_only` by code.
- Dropped weak-pass candidates unless the code-owned review policy detects real
  weak evidence cues in the support sentence.
- Dropped raw unknown relation types from the weak pass before relation-type
  governance resolution.
- Preserved review-only weak generic candidates through specificity pruning
  while normal weak generic candidates remain suppressible.
- Added a primary-prompt rule for `SENSITIZES_TO` constructions such as
  `BRCA1 loss sensitizes triple-negative breast cancer to cisplatin`.
- Bumped the primary extraction prompt version to
  `document_extraction.llm_extraction.v4` and added a weak-review prompt version
  `document_extraction.weak_review_extraction.v1`.

## Validation Commands

Focused regressions:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_uses_agent_review_only_pass \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_drops_invalid_weak_pass_type \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_does_not_downgrade_strong_claims \
  -q
```

Affected tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
  -q
```

Quality gate:

```bash
make relation-feasibility-quality-gate
```

Strict live-agent audit:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr23-low-value-review-recall-run7'
```

Failure attribution:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/2026-07-05-pr23-low-value-review-recall-run7/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr23-low-value-review-recall-run7
```

Full service gate:

```bash
make service-checks
```

## Live-Agent Result

Source artifact:

- `reports/relation_feasibility/2026-07-05-pr23-low-value-review-recall-run7/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr23-low-value-review-recall-run7/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr23-low-value-review-recall-run7/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr23-low-value-review-recall-run7/relation_feasibility_failure_analysis_report.md`

| Metric | PR22 run4 | PR23 run7 | Status |
|---|---:|---:|---|
| Verdict | GREEN | GREEN | Passing |
| Completed-agent precision | 1.0000 | 1.0000 | Passing |
| Completed-agent recall | 0.8800 | 1.0000 | Improved |
| High-value recall | 1.0000 | 1.0000 | Preserved |
| Trusted high-value recall | 0.8500 | 0.8500 | Preserved |
| Low-value review recall | 0.4000 | 1.0000 | Fixed |
| Low-value review CURIE endpoint capture rate | 0.2000 | 1.0000 | Fixed |
| Trusted-eligible CURIE-linked endpoint rate | 1.0000 | 1.0000 | Preserved |
| Verified CURIE match rate | 0.9048 | 1.0000 | Improved |
| Weak-claim trusted leakage count | 0 | 0 | Passing |
| Fallback cases | 0 | 0 | Passing |
| Invalid strict-agent cases | 0 | 0 | Passing |
| Negative-control leakage cases | 0 | 0 | Passing |
| Wrong verified CURIE links | 0 | 0 | Passing |
| Raw unknown candidate relation types | 0 | 0 | Passing |
| Raw unknown inventory relation types | 0 | 0 | Passing |

## Live Loop Notes

- Run1 and run2 stayed safe but missed the three PR23 weak targets; prompt-only
  guidance was not enough.
- Run3 exposed an invalid weak-pass relation type (`CASES`), proving the weak
  pass needed tolerant parsing plus code-owned raw-type rejection.
- Run4 recovered all weak cases but over-downgraded strong candidates because
  weak-pass outputs were too broad.
- Run5 restored precision but still missed the specific `SENSITIZES_TO` case.
- Run6 passed after adding policy-backed weak-pass filtering and a primary
  prompt rule for `X sensitizes disease/cells to drug`, then adversarial review
  found three remaining closeout gaps: mixed-sentence weak cue poisoning,
  structured weak-pass proposal leakage, and fallback-creditable review metrics.
- Run7 passed after adding candidate-argument scoped weak-cue policy, weak-pass
  proposal rejection, and agent-completion requirements for low-value review
  metric credit.

## Final Weak-Case Evidence

The final live run captured all five low-value review cases as review-only:

- `weak_med13_may_link_chd`: `MED13 ASSOCIATED_WITH congenital heart disease`
  with `hedged_language`, `may_link`, `weak_review_agent_pass`.
- `weak_met_correlated_resistance`: `MET amplification ASSOCIATED_WITH
  resistance` with `hedged_language`, `correlated_only`,
  `weak_review_agent_pass`.
- `weak_hrd_possible_biomarker`: `HRD score BIOMARKER_FOR platinum sensitivity`
  with `hedged_language`, `may_link`, `possible_biomarker`,
  `weak_review_agent_pass`.
- `weak_il6_may_regulate_inflammation`: `IL6 REGULATES inflammatory signaling`
  with `hedged_language`, `may_regulate`, `may_link`,
  `weak_review_agent_pass`.
- `weak_akt_trend_survival`: `AKT activation ASSOCIATED_WITH reduced survival`
  with `hedged_language`, `trend_only`, `correlated_only`,
  `weak_review_agent_pass`.

## Remaining Failure Attribution

Final failure attribution reports no missed gold relations.

Final failure attribution reports no false positives.

Remaining CURIE gaps are review-lane or broad endpoint labels:

- `aggressive tumor growth`
- `ERK phosphorylation`
- `response to pembrolizumab`
- `reduced survival`
- `HRD score`
- `platinum sensitivity`
- `inflammatory signaling` with an unverified model hint (`GO:0002526`)
- `resistance`

## Artifact Hashes

| Artifact | SHA-256 |
|---|---|
| relation feasibility JSON | `e08c95ce73c49ea1911c877f20216250781a4745222b82265df3468ce3c4d5ed` |
| relation feasibility Markdown | `2766c06deea7fc78bc514ec934cd5b9a69889243c4cfedd81fe3a64029a5f30f` |
| failure analysis JSON | `380c3b0e25668e93447977e840558cf89f434e26a8fb0b84ca7361ee285760a5` |
| failure analysis Markdown | `3b02408976683117dce478c858f2e945b5d49ec711c3008afd74e767f2e0d6ad` |

## Interpretation

PR-23 fixes the live-agent low-value review recall gap without using
deterministic fallback as success. The system now has a separate weak-review
agent pass, but the code remains the trust boundary: weak-pass outputs are
forced to review-only, raw weak-pass relation types are dropped, and weak-pass
candidates must satisfy the code-owned review policy before they can be kept.
The closeout service gate passed with coverage 87.03% against the 86% gate.

This does not finish trusted-graph readiness. It improves one blocker while
leaving review-lane generic noise, repeated-run proof, endpoint grounding for
broad labels, and graph-side independent promotion enforcement for the remaining
PRs.
