# Relation Feasibility Generated Summary

## Run Context

- Branch: `alvaro/evidence-pr27-benchmark-v3-doc-proof`
- Commit: `6e67477+pr27-working-tree`
- Command: `scripts/run_relation_feasibility_audit.py --extractor agent --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json --output-dir reports/relation_feasibility/2026-07-06-pr27-v2-run1`
- Model label: `current-agent`
- Fixture path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`

## Artifact Hashes

- `2026-07-06-pr27-v2-relation-feasibility-report.json`: `25ed1ee4bf020bf7f65e8cbe929d2cc11d4abfc55c3f906316d852d152065929`

## Key Metrics

- Verdict: `GREEN`
- case_count: 30
- gold_relation_count: 25
- candidate_count: 25
- completed_agent_candidate_count: 25
- completed_agent_precision_against_gold: 1.0
- completed_agent_recall_against_gold: 1.0
- high_value_recall: 1.0
- trusted_high_value_recall: 0.85
- low_value_review_recall: 1.0
- trusted_eligible_curie_linked_gold_endpoint_rate: 1.0
- candidate_curie_present_rate: 0.84
- verified_curie_match_rate: 1.0
- valuable_candidate_rate: 0.8
- completed_agent_valuable_candidate_rate: 0.8
- generic_relation_rate: 0.12
- raw_unknown_relation_type_count: 0
- raw_unknown_relation_type_surface_count: 0
- model_curie_wrong_count: 0
- wrong_verified_curie_link_count: 0
- fallback_case_count: 0
- invalid_agent_case_count: 0
- negative_control_leakage_count: 0
- weak_claim_trusted_leakage_count: 0

## Blocking Reasons

- none

## Warning Reasons

- none

## Remaining Failures

- none
