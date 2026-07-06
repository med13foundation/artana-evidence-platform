# Relation Feasibility Generated Summary

## Run Context

- Branch: `alvaro/evidence-pr28-v3-specificity-recall`
- Commit: `486108b`
- Command: `zsh -lc set -a; source .env.postgres; set +a; PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 scripts/run_relation_feasibility_audit.py --extractor agent --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json --output-dir reports/relation_feasibility/2026-07-06-pr28-v3-specificity-recall-run6-post-review`
- Model label: `openai:gpt-5.4-mini`
- Fixture path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`

## Artifact Hashes

- `relation_feasibility_report.json`: `b06eca9ef0ad1c24f850899da75d2fa6b6d02259d0b24e3aa73a61eec7e2f86a`
- `relation_feasibility_failure_analysis_report.json`: `2d1e437e7287624fcd7b02c46759d9c332252a5ecb2bedba2b4fb91268c2ec16`

## Key Metrics

- Verdict: `RED`
- case_count: 40
- gold_relation_count: 30
- candidate_count: 27
- completed_agent_candidate_count: 27
- completed_agent_precision_against_gold: 0.8519
- completed_agent_recall_against_gold: 0.7667
- high_value_recall: 0.75
- trusted_high_value_recall: 0.2
- low_value_review_recall: 0.8
- trusted_eligible_curie_linked_gold_endpoint_rate: 0.325
- candidate_curie_present_rate: 0.5741
- verified_curie_match_rate: 0.2833
- valuable_candidate_rate: 0.5185
- completed_agent_valuable_candidate_rate: 0.5185
- generic_relation_rate: 0.2593
- raw_unknown_relation_type_count: 0
- raw_unknown_relation_type_surface_count: 0
- model_curie_wrong_count: 8
- wrong_verified_curie_link_count: 0
- fallback_case_count: 0
- invalid_agent_case_count: 0
- negative_control_leakage_count: 0
- weak_claim_trusted_leakage_count: 0

## Multi-Run Aggregate

Runs `run1` through `run5` were strict v3 live-agent runs before adversarial
review cleanup, using prompt version `document_extraction.llm_extraction.v5`.
`run6-post-review` is the fresh strict v3 live-agent run after the adversarial
fixes, using prompt version `document_extraction.llm_extraction.v6`.

| Run | Verdict | Precision | Recall | High-value recall | Trusted high-value recall | Generic rate | Valuable rate | Trusted endpoint rate | FP | Missed | Fallback | Invalid agent | Safety leaks |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| run1 | RED | 0.7586 | 0.7333 | 0.7000 | 0.2000 | 0.3103 | 0.4138 | 0.3250 | 7 | 8 | 0 | 0 | 0 |
| run2 | RED | 0.7429 | 0.8667 | 0.9000 | 0.2000 | 0.2857 | 0.4000 | 0.3250 | 9 | 4 | 0 | 0 | 0 |
| run3 | RED | 0.8000 | 0.8000 | 0.8000 | 0.2000 | 0.2667 | 0.4667 | 0.3250 | 6 | 6 | 0 | 0 | 0 |
| run4 | RED | 0.9259 | 0.8333 | 0.8500 | 0.2000 | 0.2593 | 0.5185 | 0.3250 | 2 | 5 | 0 | 0 | 0 |
| run5 | RED | 0.8889 | 0.8000 | 0.8000 | 0.2000 | 0.1852 | 0.5185 | 0.3250 | 3 | 6 | 0 | 0 | 0 |
| run6-post-review | RED | 0.8519 | 0.7667 | 0.7500 | 0.2000 | 0.2593 | 0.5185 | 0.3250 | 4 | 7 | 0 | 0 | 0 |

- Best precision/noise run was `run4`: precision 0.9259, false positives 2,
  and high-value recall 0.8500.
- Best recall run was `run2`: recall 0.8667 and high-value recall 0.9000, but
  it had lower precision at 0.7429 and 9 false positives.
- Final post-review evidence is `run6-post-review`: safety remained clean, but
  readiness stayed RED with high-value recall 0.7500, generic rate 0.2593, and
  trusted endpoint rate 0.3250.
- Repeatable omissions remain: BRCA1 plus low-value EGFR/MET were missed across
  all pre-review runs; FBN1 and NTRK were missed in 4 of 5 pre-review runs;
  post-review run6 additionally missed MECP2, PAH, APC, FBN1, BRCA1, EGFR, and
  MET.

## Blocking Reasons

- Too few trusted-eligible CURIE-linked gold endpoints were recovered by extraction.

## Warning Reasons

- Trusted high-value recall is below target.
- Valuable candidate rate is below target.
- Generic relation rate is above target.

## Remaining Failures

- v3_mecp2_associated_with_rett_syndrome: MECP2 pathogenic variants ASSOCIATED_WITH Rett syndrome
- v3_fbn1_associated_with_marfan_syndrome: FBN1 loss-of-function variants ASSOCIATED_WITH Marfan syndrome
- v3_pah_associated_with_phenylketonuria: PAH pathogenic variants ASSOCIATED_WITH phenylketonuria
- v3_brca1_predisposes_hereditary_breast_ovarian_cancer: BRCA1 truncating variants PREDISPOSES_TO hereditary breast and ovarian cancer syndrome
- v3_apc_predisposes_fap: APC pathogenic variants PREDISPOSES_TO familial adenomatous polyposis
- v3_weak_met_correlated_resistance: MET amplification ASSOCIATED_WITH resistance to EGFR inhibition
- v3_weak_egfr_trend_response_erlotinib: EGFR expression ASSOCIATED_WITH erlotinib response
- repeated_missed_gold_relations: v3_apc_predisposes_fap: APC pathogenic variants PREDISPOSES_TO familial adenomatous polyposis
- repeated_missed_gold_relations: v3_brca1_predisposes_hereditary_breast_ovarian_cancer: BRCA1 truncating variants PREDISPOSES_TO hereditary breast and ovarian cancer syndrome
- repeated_missed_gold_relations: v3_fbn1_associated_with_marfan_syndrome: FBN1 loss-of-function variants ASSOCIATED_WITH Marfan syndrome
- repeated_missed_gold_relations: v3_mecp2_associated_with_rett_syndrome: MECP2 pathogenic variants ASSOCIATED_WITH Rett syndrome
- repeated_missed_gold_relations: v3_pah_associated_with_phenylketonuria: PAH pathogenic variants ASSOCIATED_WITH phenylketonuria
- repeated_missed_gold_relations: v3_weak_egfr_trend_response_erlotinib: EGFR expression ASSOCIATED_WITH erlotinib response
- repeated_missed_gold_relations: v3_weak_met_correlated_resistance: MET amplification ASSOCIATED_WITH resistance to EGFR inhibition
- repeated_false_positive_candidates: v3_mecp2_associated_with_rett_syndrome: MECP2 pathogenic variants ASSOCIATED_WITH developmental regression
- repeated_false_positive_candidates: v3_pah_associated_with_phenylketonuria: PAH pathogenic variants ASSOCIATED_WITH elevated phenylalanine
- repeated_false_positive_candidates: v3_vemurafenib_targets_braf_v600e: vemurafenib INHIBITS MAPK signaling
- repeated_false_positive_candidates: v3_weak_met_correlated_resistance: MET amplification ASSOCIATED_WITH EGFR inhibition
- curie_gaps: v3_alectinib_treats_alk_fusion_lung_cancer: unverified_model_hint subject Alectinib -> CHEBI:45783 (model)
- curie_gaps: v3_alectinib_treats_alk_fusion_lung_cancer: missing_curie object ALK fusion-positive lung cancer -> no_curie
- curie_gaps: v3_gla_associated_with_fabry_disease: missing_curie subject GLA variants -> no_curie
- curie_gaps: v3_gla_associated_with_fabry_disease: unverified_model_hint object Fabry disease -> MESH:D050177 (model)
- curie_gaps: v3_il6_regulates_inflammatory_signaling: review_only_endpoint object inflammatory signaling -> no_curie
- curie_gaps: v3_kras_g12d_activates_mapk: missing_curie subject KRAS G12D -> no_curie
- curie_gaps: v3_larotrectinib_treats_ntrk_fusion_tumors: unverified_model_hint subject Larotrectinib -> CHEBI:134227 (model)
- curie_gaps: v3_larotrectinib_treats_ntrk_fusion_tumors: missing_curie object NTRK fusion solid tumors -> no_curie
- curie_gaps: v3_ldlr_predisposes_familial_hypercholesterolemia: unverified_model_hint subject LDLR loss-of-function variants -> HGNC:6547 (model)
- curie_gaps: v3_ldlr_predisposes_familial_hypercholesterolemia: unverified_model_hint object familial hypercholesterolemia -> MONDO:0019005 (model)
