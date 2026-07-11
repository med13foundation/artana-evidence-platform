# PR-24 Grounding Decision Table

Date: 2026-07-06

Branch: `alvaro/evidence-pr24-grounding-decision-table`

Base branch: `alvaro/evidence-pr23-low-value-review-recall`

Commit: see PR head commit

## Goal

PR-24 makes the remaining endpoint-grounding gaps explicit policy decisions.
Broad, composite, event-like, treatment-response, score, prognosis, and generic
resistance labels must not become trusted identifiers just because a model
suggested a plausible CURIE.

## What Changed

- Added explicit review-only decision metadata to `ReviewOnlyEntityRecord`.
- Expanded the local grounding decision table for all remaining PR23 gap labels:
  `aggressive tumor growth`, `ERK phosphorylation`, `response to pembrolizumab`,
  `HRD score`, `platinum sensitivity`, `inflammatory signaling`,
  `reduced survival`, and `resistance`.
- Added link metadata for review-only endpoint abstentions:
  `grounding_curation_status`, `grounding_reason_code`, and
  `trusted_identifier_allowed`.
- Updated failure attribution so curated review-only endpoints appear as
  `review_only_endpoint` with the grounding decision, not as accidental missing
  CURIEs or trusted model hints.
- Made review-only grounding decisions take precedence over verified aliases so
  composite labels such as `resistance to gefitinib` cannot become trusted drug
  identifiers through an alias collision.
- Added a guarded primary LLM output schema so raw relation types from the live
  agent, such as `CASES`, reach the code-owned resolver/drop path instead of
  crashing schema validation before safeguards run.

## Validation Commands

Focused RED/GREEN tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py::test_review_only_dictionary_has_explicit_decisions_for_pr24_endpoint_gaps \
  services/artana_evidence_api/tests/unit/test_entity_curie_linking.py::test_review_only_grounding_metadata_explains_policy_decision \
  tests/unit/test_relation_feasibility_failure_analysis.py::test_failure_analysis_reports_review_only_grounding_decision \
  -q
```

Affected grounding and attribution suites:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
  services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
  tests/unit/test_relation_feasibility_failure_analysis.py \
  -q
```

Relation feasibility quality gate:

```bash
make relation-feasibility-quality-gate
```

Initial strict live-agent audit:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-06-pr24-grounding-decision-table-run1'
```

Final strict live-agent audit after adversarial fixes:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-06-pr24-grounding-decision-table-run3'
```

Final failure attribution:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/2026-07-06-pr24-grounding-decision-table-run3/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-06-pr24-grounding-decision-table-run3
```

## Live-Agent Result

Source artifacts:

- `reports/relation_feasibility/2026-07-06-pr24-grounding-decision-table-run3/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-06-pr24-grounding-decision-table-run3/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr24-grounding-decision-table-run3/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr24-grounding-decision-table-run3/relation_feasibility_failure_analysis_report.md`

| Metric | PR24 run3 |
|---|---:|
| Verdict | GREEN |
| Completed-agent precision | 0.9615 |
| Completed-agent recall | 1.0000 |
| Completed-agent valuable rate | 0.7692 |
| High-value recall | 1.0000 |
| Trusted high-value recall | 0.8500 |
| Low-value review recall | 1.0000 |
| Trusted-eligible CURIE-linked endpoint rate | 1.0000 |
| Verified CURIE match rate | 1.0000 |
| Weak-claim trusted leakage count | 0 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Wrong verified CURIE links | 0 |
| Missed gold relations | 0 |
| False positives | 1 review-only candidate |
| Generic relation rate | 0.1154 |

## Endpoint Decisions

Final failure attribution reports no missed gold relations. It reports one false
positive, `cisplatin TREATS platinum-sensitive tumors`; the candidate is
`review_only`, has no trusted object CURIE, and carries `context_dependent` plus
`subset_relation` reasons. All eight remaining endpoint gaps are intentional
review-only grounding decisions:

| Label | Decision | Reason |
|---|---|---|
| `aggressive tumor growth` | review-only | `composite_event_label` |
| `ERK phosphorylation` | review-only | `broad_process_label` |
| `response to pembrolizumab` | review-only | `composite_treatment_response_label` |
| `reduced survival` | review-only | `prognosis_outcome_label` |
| `HRD score` | review-only | `biomarker_score_label` |
| `platinum sensitivity` | review-only | `drug_response_phenotype_label` |
| `inflammatory signaling` | review-only | `broad_process_label` |
| `resistance` | review-only | `generic_resistance_label` |

Each row has `trusted_identifier_allowed=False`.

## Artifact Hashes

| Artifact | SHA-256 |
|---|---|
| relation feasibility JSON | `c27caea9764d72d046f0de047d1812bc2dadbbcb27cc2c9ac5317eafd266b79d` |
| relation feasibility Markdown | `8b2d8ab8f6fee81206bd864f035997e71a07f10bdba1f53ff9328fa2e3f13b8f` |
| failure analysis JSON | `459bab353528067abf897d2fbbfa16f674eb7ad17f5f75cc0d39c5696c2372d2` |
| failure analysis Markdown | `b410e9ded43c8ea634a981368fd629daaf5e7b78e910602087d3c576f3076e87` |

## Interpretation

PR-24 does not claim final trusted-graph readiness. It closes the endpoint
grounding decision-table gap by making unsafe labels explicit review-only
abstentions while preserving the live-agent trusted-lane metrics. It also fixes
the live primary-pass raw-relation crash exposed by run2. The remaining
trusted-readiness work is repeatability, generic and review-lane noise,
graph-side promotion enforcement, and broader benchmark proof.
