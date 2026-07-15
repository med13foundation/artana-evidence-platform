# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-v3-luna-v11-01`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11`
- Fixture SHA-256: `a5b31c2111a4f2f25017a70c3ce3d33f844e3a939eb918c621ba7e5d9d6d3658`
- Methodology complete: `True`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `17`
- endpoint_source_match_count: `13`
- full_frame_correct_count: `8`
- quality_case_count: `17`
- unresolved_case_count: `2`
- unresolved_expected_frame_count: `3`
- agent_invocation_completion_rate: `1.0`
- strict_usable_extraction_completion_rate: `0.9473684210526315`
- explicit_polarity_concordance_rate: `0.7058823529411765`
- epistemic_status_concordance_rate: `0.7058823529411765`
- required_qualifier_completeness_rate: `0.7272727272727273`
- qualifier_concordance_rate: `0.5294117647058824`
- endpoint_source_match_precision: `0.8125`
- full_frame_precision: `0.5`
- expected_source_measurement_count: `1`
- output_source_measurement_count: `3`
- matched_source_measurement_count: `0`
- source_measurement_precision: `0.0`
- source_measurement_recall: `0.0`
- unmatched_output_count: `3`
- unsupported_positive_output_count: `2`
- unsafe_assertive_upgrade_count: `0`
- positive_on_negative_or_null_count: `0`
- agent_authored_quality_score_count: `0`
- source_measurement_without_span_count: `0`

## Gates

- agent_invocation_completion: **true** (all strict cases completed a real agent invocation)
- strict_usable_extraction_completion: **false** (all strict live cases produced usable extraction)
- polarity: **false** (explicit polarity concordance is 100%)
- epistemic_status: **false** (explicit epistemic-status concordance is 100%)
- qualifier_presence: **false** (required qualifier presence is 100%)
- qualifier_concordance: **false** (all qualifier categories are gold-concordant)
- endpoint_source_match_precision: **false** (endpoint/source match precision is 100%)
- full_frame_precision: **false** (full-frame precision is 100%)
- source_measurement_precision: **false** (source-measurement precision is 100%)
- source_measurement_recall: **false** (source-measurement recall is 100%)
- unmatched_outputs: **false** (unmatched output frames are zero)
- unsupported_positive_outputs: **false** (unsupported positive output frames are zero)
- unsafe_assertive_upgrades: **true** (non-assertive gold claims are never upgraded to ASSERTED)
- positive_on_negative_or_null: **true** (positive output on negative/null cases is zero)
- agent_quality_scores: **true** (agent-authored quality scores are absent)
- no_fallback: **true** (strict reports contain no fallback output)
- measurement_spans: **true** (source measurements all have exact spans)
- stability: **false** (not_evaluated)

## Cases

### holdout_variant_alk_g1202r: ALK resistance variant and population

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `9e0cdd1dfe9cb7f4198b32265fe09982c3f92cc06bc7d3abfc071c033b795539`
- Postprocessed candidate SHA-256: `740c59a0aa86154d61a0d2507c77a5b502cf96d97bbf6c562a938c715908d875`

### holdout_explicit_negative_tmb: Explicit biomarker contradiction

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `f32494ec48988f940404906647898658c8a6bd215efd73e2d89d05da04355520`
- Postprocessed candidate SHA-256: `88a3b668fceb163afc3518bf29339f11c27b8cf7b330051a1ee2b8c20b002911`

### holdout_null_margin: Null result beyond a prespecified margin

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `6d5e5bf9c079583dae36ad1776d790ce58d415203a4b499253b87d0eaafcb640`
- Postprocessed candidate SHA-256: `68c29fc7c1408dfc1c104a353f096192869ab97195a999dcbb2c808050785d7f`

### holdout_provisional_zanubrutinib: Provisional treatment signal

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `49b7649f3d8944cca9ba6e03f08e130d289c072cbb0f635fc697153799e0ed22`
- Postprocessed candidate SHA-256: `022154bac44ec39e54afdeab952a90f286d7cdd3210d9e24c837ea806dae6737`

### holdout_uncertain_talazoparib: Uncertain treatment association

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `705ddbe6048bf4b8fb08417e69119d3b9af8b7853c498ab637332bd83418bb76`
- Postprocessed candidate SHA-256: `107bca098e8cdae26dc5034df7096704c8a6ba49738e56703fd397321a8b7fdb`

### holdout_hypothesis_keap1: Mechanistic hypothesis

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `0260cf085d5a61ab80333ecde56d817d7a01d8af0a9ff9b8ee48a599a0872762`
- Postprocessed candidate SHA-256: `ee3452f39e5f64bd08f53ea9f2986e2390245f629a3baf4b5cee30b6d1b18a3a`

### holdout_intervention_ctdna: Intervention outside the endpoints

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `204d12d4538871aa13a73d8d34c1286f781d1756c0c76d364106e94426afb6e9`
- Postprocessed candidate SHA-256: `1da48191284611b060d44348aca343daf7237011b7cacbb2a9e701d7af90cb30`

### holdout_comparator_amivantamab: Active comparator

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `62d38652b8a93bb4135d6807b47dc88c6cbea800c9fab019782d481383d855b0`
- Postprocessed candidate SHA-256: `eb4c07788c03f7dbd5c577fb1980be1e2f30cce061a1f9106bb2c8e4cb25a33e`

### holdout_outcome_enfortumab: Measured clinical endpoint

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `6216ffde259be97a49bf342f07324a766cdd208a99d82b63de405197d7acdd38`
- Postprocessed candidate SHA-256: `884279e010e1fe1c4d229c6598163d822bfb859d1ef8e7483ae5000ef61150eb`

### holdout_study_adagrasib: Study design qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `b9ad2f192a49789b554b350e4b2e794be213de86ab79bc6bfca5316ad78d3252`
- Postprocessed candidate SHA-256: `850a25e8f0b7e522e44743e20fb97adbcfc42400d4aabb52ac5afa73c08ff963`

### holdout_setting_ibrutinib: Treatment setting qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `978f6d898eb276c51082a1ce00ab5cd16eef661a199a9994547478a953213fb3`
- Postprocessed candidate SHA-256: `998e5727c1c69a6c3867b37622c6745a7962dff9daf4238f7277eee2817eeecb`

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `b46096dd0ec0dcd959478dfba878cf9e87042c28c80e302303e0c2aa55bd6811`
- Postprocessed candidate SHA-256: `92604390f166071ba0875ddf1452b656f9e28d5b0d9ddc453d56abf8528f6474`

### holdout_threshold_cabozantinib: Numeric threshold qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `False`
- Output frames: `0`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `07ebf697e25f1d0fd5f61cb10c0894ee337c1df7d65ea91e78df0b28f0e5d503`
- Postprocessed candidate SHA-256: `096ac3df03946e078dbe269a92a8543208cd3a306619c8121a6cf651f2586842`

### holdout_multi_clause_ret_ntrk: Clause-local sibling claims

- Adjudication: `unresolved`
- Included in quality metrics: `False`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `2`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `0390d0cea070d67260e785b89ed858c5219957f77de69b5013b674812fe7ef48`
- Postprocessed candidate SHA-256: `583a81bab1691ed60c9ab816b5dd26c2619928b303b1c00e55ce1d8dbe42b929`

### holdout_extra_output_capivasertib: Methods and funding output trap

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `70fc47d327f435c6bb18576caaee8e752ee631aa3e6671575582785df8ce5840`
- Postprocessed candidate SHA-256: `37586a65e8a562b2c51bd3c89da6a117a3c3d20cf67ea1c88ac0802c36cbbc04`

### holdout_unresolved_population: Explicitly missing subgroup

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `029010a43c78324676467a8e8fc0daf6ef2367cdce41b9b59cdbeb4fea15582f`
- Postprocessed candidate SHA-256: `b65a451807ed40127711c1ab6294a26c325e148f2a7308bf48a1514af3afb776`

### holdout_source_measurement_repoterctinib: Literal source measurement

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `463b6f5ea8fb746686629307e65a408a9fc54e211293cb2c195c66ce42201ae9`
- Postprocessed candidate SHA-256: `7cd576a87fb2c10729082ac968e9731bf32c99e51279ad6c8ca3b97281fe7b1a`

### holdout_positive_sotorasib: Positive asserted relation

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `8a9bd9e8d7ed439114b5d3144b945ce0604f65814233710ccddbfe650cb4c09c`
- Postprocessed candidate SHA-256: `8d4bfa63f1a6612afb46b60f10e6bfd22138332cdd6bba7026aaa2025fbff403`

### holdout_population_futibatinib: Population subgroup qualifier

- Adjudication: `unresolved`
- Included in quality metrics: `False`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `2e4811f343b84a763204030698f0409e031f83728a8dec10eec40d7e49400fcb`
- Postprocessed candidate SHA-256: `a2d841b455542d9d538002e2e2af614d3225ab97917de00118f4cee7cc5007de`

## Unresolved Adjudication

- `holdout_multi_clause_ret_ntrk`: excluded from quality denominators; unresolved frames `holdout_multi_clause_ret_ntrk_02`
- `holdout_population_futibatinib`: excluded from quality denominators; unresolved frames `holdout_population_futibatinib_01`
