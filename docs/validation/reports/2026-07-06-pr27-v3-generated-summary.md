# Relation Feasibility Generated Summary

## Run Context

- Branch: `alvaro/evidence-pr27-benchmark-v3-doc-proof`
- Commit: `6e67477+pr27-working-tree`
- Command: `scripts/run_relation_feasibility_audit.py --extractor agent --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json --output-dir reports/relation_feasibility/2026-07-06-pr27-v3-run2`
- Model label: `current-agent`
- Fixture path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`

## Artifact Hashes

- `2026-07-06-pr27-v3-relation-feasibility-report.json`: `3dd87040d11e615fff6ced0ae45a302c9e74b9a4e3ba1dc98ff9078fec621fc2`
- `2026-07-06-pr27-v3-failure-analysis-report.json`: `eadcd476f2385051eae739375f913b0a02e330c841fcbb0171134185b608871a`

## Key Metrics

- Verdict: `RED`
- case_count: 40
- gold_relation_count: 30
- candidate_count: 30
- completed_agent_candidate_count: 30
- completed_agent_precision_against_gold: 0.7333
- completed_agent_recall_against_gold: 0.7333
- high_value_recall: 0.7
- trusted_high_value_recall: 0.2
- low_value_review_recall: 0.8
- trusted_eligible_curie_linked_gold_endpoint_rate: 0.3
- candidate_curie_present_rate: 0.5833
- verified_curie_match_rate: 0.2667
- valuable_candidate_rate: 0.3667
- completed_agent_valuable_candidate_rate: 0.3667
- generic_relation_rate: 0.3
- raw_unknown_relation_type_count: 0
- raw_unknown_relation_type_surface_count: 0
- model_curie_wrong_count: 9
- wrong_verified_curie_link_count: 0
- fallback_case_count: 0
- invalid_agent_case_count: 0
- negative_control_leakage_count: 0
- weak_claim_trusted_leakage_count: 0

## Blocking Reasons

- Too few trusted-eligible CURIE-linked gold endpoints were recovered by extraction.

## Warning Reasons

- Precision is below trusted graph construction target.
- Trusted high-value recall is below target.
- Valuable candidate rate is below target.
- Generic relation rate is above target.

## Remaining Failures

- v3_osimertinib_treats_egfr_exon19_luad: Osimertinib TREATS EGFR exon 19 deletion lung adenocarcinoma
- v3_larotrectinib_treats_ntrk_fusion_tumors: Larotrectinib TREATS NTRK fusion solid tumors
- v3_fbn1_associated_with_marfan_syndrome: FBN1 loss-of-function variants ASSOCIATED_WITH Marfan syndrome
- v3_ldlr_predisposes_familial_hypercholesterolemia: LDLR loss-of-function variants PREDISPOSES_TO familial hypercholesterolemia
- v3_brca1_predisposes_hereditary_breast_ovarian_cancer: BRCA1 truncating variants PREDISPOSES_TO hereditary breast and ovarian cancer syndrome
- v3_apc_predisposes_fap: APC pathogenic variants PREDISPOSES_TO familial adenomatous polyposis
- v3_weak_met_correlated_resistance: MET amplification ASSOCIATED_WITH resistance to EGFR inhibition
- v3_weak_egfr_trend_response_erlotinib: EGFR expression ASSOCIATED_WITH erlotinib response
- repeated_missed_gold_relations: v3_apc_predisposes_fap: APC pathogenic variants PREDISPOSES_TO familial adenomatous polyposis
- repeated_missed_gold_relations: v3_brca1_predisposes_hereditary_breast_ovarian_cancer: BRCA1 truncating variants PREDISPOSES_TO hereditary breast and ovarian cancer syndrome
- repeated_missed_gold_relations: v3_fbn1_associated_with_marfan_syndrome: FBN1 loss-of-function variants ASSOCIATED_WITH Marfan syndrome
- repeated_missed_gold_relations: v3_larotrectinib_treats_ntrk_fusion_tumors: Larotrectinib TREATS NTRK fusion solid tumors
- repeated_missed_gold_relations: v3_ldlr_predisposes_familial_hypercholesterolemia: LDLR loss-of-function variants PREDISPOSES_TO familial hypercholesterolemia
- repeated_missed_gold_relations: v3_osimertinib_treats_egfr_exon19_luad: Osimertinib TREATS EGFR exon 19 deletion lung adenocarcinoma
- repeated_missed_gold_relations: v3_weak_egfr_trend_response_erlotinib: EGFR expression ASSOCIATED_WITH erlotinib response
- repeated_missed_gold_relations: v3_weak_met_correlated_resistance: MET amplification ASSOCIATED_WITH resistance to EGFR inhibition
- repeated_false_positive_candidates: v3_alectinib_treats_alk_fusion_lung_cancer: Alectinib TREATS central nervous system involvement
- repeated_false_positive_candidates: v3_larotrectinib_treats_ntrk_fusion_tumors: Larotrectinib TREATS solid tumors
- repeated_false_positive_candidates: v3_mecp2_associated_with_rett_syndrome: MECP2 pathogenic variants ASSOCIATED_WITH developmental regression
- repeated_false_positive_candidates: v3_msi_high_biomarker_checkpoint_response: MSI-high status BIOMARKER_FOR colorectal cancer
- repeated_false_positive_candidates: v3_osimertinib_treats_egfr_exon19_luad: osimertinib TREATS EGFR
- repeated_false_positive_candidates: v3_pah_associated_with_phenylketonuria: PAH pathogenic variants ASSOCIATED_WITH elevated phenylalanine
- repeated_false_positive_candidates: v3_vemurafenib_targets_braf_v600e: vemurafenib INHIBITS MAPK signaling
- repeated_false_positive_candidates: v3_weak_met_correlated_resistance: MET amplification ASSOCIATED_WITH EGFR inhibition
- curie_gaps: v3_alectinib_treats_alk_fusion_lung_cancer: unverified_model_hint subject Alectinib -> CHEBI:75086 (model)
- curie_gaps: v3_alectinib_treats_alk_fusion_lung_cancer: missing_curie object ALK fusion-positive lung cancer -> no_curie
- curie_gaps: v3_gla_associated_with_fabry_disease: unverified_model_hint subject GLA variants -> HGNC:4297 (model)
- curie_gaps: v3_gla_associated_with_fabry_disease: unverified_model_hint object Fabry disease -> MONDO:0007739 (model)
- curie_gaps: v3_il6_regulates_inflammatory_signaling: review_only_endpoint object inflammatory signaling -> no_curie
- curie_gaps: v3_kras_g12d_activates_mapk: missing_curie subject KRAS G12D -> no_curie
- curie_gaps: v3_mecp2_associated_with_rett_syndrome: missing_curie subject MECP2 pathogenic variants -> no_curie
- curie_gaps: v3_mecp2_associated_with_rett_syndrome: unverified_model_hint object Rett syndrome -> MESH:C536314 (model)
- curie_gaps: v3_msi_high_biomarker_checkpoint_response: missing_curie subject MSI-high status -> no_curie
- curie_gaps: v3_msi_high_biomarker_checkpoint_response: missing_curie object immune checkpoint inhibitor response -> no_curie
