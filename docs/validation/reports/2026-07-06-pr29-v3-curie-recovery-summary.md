# Relation Feasibility Generated Summary

## Run Context

- Branch: `alvaro/evidence-pr29-v3-curie-recovery`
- Commit: `b37610d`
- Command: `set -a; source .env.postgres; set +a; PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 scripts/run_relation_feasibility_audit.py --extractor agent --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json --output-dir reports/relation_feasibility/2026-07-06-pr29-v3-curie-recovery-run7`
- Model label: `live agent configured by .env.postgres`
- Fixture path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`

## Artifact Hashes

- `relation_feasibility_report.json`: `365bb17a3bdcaaa272815b47fea6995dcf84bd9a6d841ff18085c38826f18672`
- `relation_feasibility_failure_analysis_report.json`: `1d15d06770467c244b0c2b68be0bfe18bb961909a9ef2d74e1858db3737a48c1`

## Key Metrics

- Verdict: `YELLOW`
- case_count: 40
- gold_relation_count: 30
- candidate_count: 31
- completed_agent_candidate_count: 31
- completed_agent_precision_against_gold: 0.9032
- completed_agent_recall_against_gold: 0.9333
- high_value_recall: 1.0
- trusted_high_value_recall: 0.35
- high_value_review_gold_relation_count: 13
- high_value_review_candidate_count: 13
- high_value_review_gold_match_count: 13
- high_value_review_recall: 1.0
- low_value_review_recall: 0.8
- trusted_eligible_curie_linked_gold_endpoint_rate: 1.0
- candidate_curie_present_rate: 0.5645
- verified_curie_match_rate: 0.725
- valuable_candidate_rate: 0.5161
- completed_agent_valuable_candidate_rate: 0.5161
- generic_relation_rate: 0.2903
- raw_unknown_relation_type_count: 0
- raw_unknown_relation_type_surface_count: 0
- model_curie_wrong_count: 2
- wrong_verified_curie_link_count: 0
- fallback_case_count: 0
- invalid_agent_case_count: 0
- negative_control_leakage_count: 0
- weak_claim_trusted_leakage_count: 0

## Blocking Reasons

- none

## Warning Reasons

- Trusted high-value recall is below target.
- Valuable candidate rate is below target.
- Generic relation rate is above target.

## Remaining Failures

- v3_weak_met_correlated_resistance: MET amplification ASSOCIATED_WITH resistance to EGFR inhibition
- v3_weak_egfr_trend_response_erlotinib: EGFR expression ASSOCIATED_WITH erlotinib response
- repeated_missed_gold_relations: v3_weak_egfr_trend_response_erlotinib: EGFR expression ASSOCIATED_WITH erlotinib response
- repeated_missed_gold_relations: v3_weak_met_correlated_resistance: MET amplification ASSOCIATED_WITH resistance to EGFR inhibition
- repeated_false_positive_candidates: v3_pah_associated_with_phenylketonuria: PAH pathogenic variants ASSOCIATED_WITH elevated phenylalanine
- repeated_false_positive_candidates: v3_vemurafenib_targets_braf_v600e: vemurafenib INHIBITS MAPK signaling
- repeated_false_positive_candidates: v3_weak_met_correlated_resistance: MET amplification ASSOCIATED_WITH EGFR inhibition
- curie_gaps: v3_alectinib_treats_alk_fusion_lung_cancer: review_only_endpoint object ALK fusion-positive lung cancer -> no_curie
- curie_gaps: v3_apc_predisposes_fap: review_only_endpoint subject APC pathogenic variants -> no_curie
- curie_gaps: v3_brca1_predisposes_hereditary_breast_ovarian_cancer: review_only_endpoint subject BRCA1 truncating variants -> no_curie
- curie_gaps: v3_fbn1_associated_with_marfan_syndrome: review_only_endpoint subject FBN1 loss-of-function variants -> no_curie
- curie_gaps: v3_gla_associated_with_fabry_disease: review_only_endpoint subject GLA variants -> no_curie
- curie_gaps: v3_il6_regulates_inflammatory_signaling: review_only_endpoint object inflammatory signaling -> no_curie
- curie_gaps: v3_ldlr_predisposes_familial_hypercholesterolemia: review_only_endpoint subject LDLR loss-of-function variants -> no_curie
- curie_gaps: v3_mecp2_associated_with_rett_syndrome: review_only_endpoint subject MECP2 pathogenic variants -> no_curie
- curie_gaps: v3_msi_high_biomarker_checkpoint_response: review_only_endpoint object immune checkpoint inhibitor response -> no_curie
- curie_gaps: v3_osimertinib_treats_egfr_exon19_luad: review_only_endpoint object EGFR exon 19 deletion lung adenocarcinoma -> no_curie
