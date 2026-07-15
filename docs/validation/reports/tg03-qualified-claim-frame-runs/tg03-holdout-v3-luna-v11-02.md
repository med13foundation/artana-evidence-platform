# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-v3-luna-v11-02`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11`
- Fixture SHA-256: `a5b31c2111a4f2f25017a70c3ce3d33f844e3a939eb918c621ba7e5d9d6d3658`
- Methodology complete: `True`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `17`
- endpoint_source_match_count: `12`
- full_frame_correct_count: `7`
- quality_case_count: `17`
- unresolved_case_count: `2`
- unresolved_expected_frame_count: `3`
- agent_invocation_completion_rate: `1.0`
- strict_usable_extraction_completion_rate: `0.9473684210526315`
- explicit_polarity_concordance_rate: `0.6470588235294118`
- epistemic_status_concordance_rate: `0.6470588235294118`
- required_qualifier_completeness_rate: `0.6363636363636364`
- qualifier_concordance_rate: `0.4117647058823529`
- endpoint_source_match_precision: `0.75`
- full_frame_precision: `0.4375`
- expected_source_measurement_count: `1`
- output_source_measurement_count: `3`
- matched_source_measurement_count: `0`
- source_measurement_precision: `0.0`
- source_measurement_recall: `0.0`
- unmatched_output_count: `4`
- unsupported_positive_output_count: `3`
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
- Model-boundary output SHA-256: `3e72c76c112d42409e8520c54c89d5ea74b26c27afbddf897823f4ea384557d4`
- Postprocessed candidate SHA-256: `7de0dc64e0f35ce4a6bd6dfdc10e41259264cec926c67af0cf92299a41455913`

### holdout_explicit_negative_tmb: Explicit biomarker contradiction

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `f6b548b3eef9a9d6a6351821fc006a8ad53354270b8c43188f4cc102135b808b`
- Postprocessed candidate SHA-256: `b8f8c19ac9021005503a1f19598e37297ce77e69129ed515aaf49239940e538d`

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
- Model-boundary output SHA-256: `870c773986a2a604dc58e162a0400d832cd50c8f27efdfeadfb81f82081d6db8`
- Postprocessed candidate SHA-256: `ed54adf82ef23bd49b2cac15f53b555597fcdc757c41b4f44a4f6c76949a5b81`

### holdout_provisional_zanubrutinib: Provisional treatment signal

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `41c6f692bcc07fb1201bfbe5f89e23ecf68d942ef08750512b3e6d067f63112f`
- Postprocessed candidate SHA-256: `c6d54c54acbc7a0ba374ab352256ed590068213374d64e648334605e1e407d3f`

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
- Model-boundary output SHA-256: `9637110a7741fd9ad26ac0a7406f208a356681774cdf58c47bc260f0192a86dd`
- Postprocessed candidate SHA-256: `473f21f7084f4ed5249d42147d1140cd1e8a3293b0a2abcd6015920d57ae02cf`

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
- Model-boundary output SHA-256: `a7a5039177ffc32fd3a137f65d3f089e8696c1022415943dcce206e7bcc2ceb3`
- Postprocessed candidate SHA-256: `555627f4af04c6f60f2da2b80529461660e8e20c477324008055eaaea53ea41a`

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
- Model-boundary output SHA-256: `1ddd5161ee8b220b22341a66eedb3b185e61f7c78aabb7ecee856a197531ffba`
- Postprocessed candidate SHA-256: `ef9df1a290083dab33b9e111874b11e27fee8019a9a72cdaaf836e9e28f28cc2`

### holdout_comparator_amivantamab: Active comparator

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `40ccaec52f71c2a6d5f25bb689cdc3a6e76e87e505a0fe0ec84e47a69adbb508`
- Postprocessed candidate SHA-256: `1de25da990e771dacded3cfabe64b2867cb2f61f1b35b2adb54c275b83af9730`

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
- Model-boundary output SHA-256: `1f377609da0221ca9dea169302641b7d652d277e98497bf54432ec4007273684`
- Postprocessed candidate SHA-256: `f43d82c8295741795fe4809fed0ba697d6e5b21f07f0f6908bf1de90dfaef1d8`

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
- Model-boundary output SHA-256: `5866ea9305dac4cb0a0037f7fdddfaa99a81b62fb9c751dd56f981400316eaaa`
- Postprocessed candidate SHA-256: `8687b62215e84d2a7c78b59c40883ac20c027ee7d966301f4f158ac6911b9232`

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
- Model-boundary output SHA-256: `c1a433d834c30e540c5279ec9da0f2f85a07d11b04371b0d5b32c5059a96277c`
- Postprocessed candidate SHA-256: `68d385791901f30a51edfd35d9993639c0e83e5ccb713b552684b635e4024e25`

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
- Model-boundary output SHA-256: `8779f1321a40668e234117f1aae729b8497024d843ad9c946a84fb5467703446`
- Postprocessed candidate SHA-256: `ed63b6cb131cb61833e733c5c6b41b60453afd0b9276ed06420f93e5c892e699`

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
- Model-boundary output SHA-256: `d8f3421d094ce88ac1ff8dd616de8a086eeade34980de9021e5e0f48fcc9cf09`
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
- Model-boundary output SHA-256: `04db1b6d407b6aadb30633ddfb8dd2082a6e163f413075893ee3c6b137fe1a4e`
- Postprocessed candidate SHA-256: `cc765217839022ff25b0be6d0845eee31eeb7ee1d6844e0bd8034cd1dabd33d3`

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
- Model-boundary output SHA-256: `3809f0f0e8ffd33d977b0264a12a930b3936d09723de0d26c04725bc61c71172`
- Postprocessed candidate SHA-256: `640b76fb57a64fd66ddb81fb17c73503fd2cac633f277ed6d000fc0916715a11`

### holdout_unresolved_population: Explicitly missing subgroup

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `1e76350a7b56ee33a6176676aebd2638303657fe760af77610939dfeb410224b`
- Postprocessed candidate SHA-256: `92bbc880c8fea14637160b384e071d217d67a5404b46c7aa0a0b48ced8bdd5c6`

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
- Model-boundary output SHA-256: `e583b11390e0381ed7ed0995e04e237e22548ff04285dfbb5ef83fd2fbe79c12`
- Postprocessed candidate SHA-256: `12a9072cd4b0ad821a2ec5dcc4706f3d069da7fad6da133634a0700968cbc5f4`

### holdout_positive_sotorasib: Positive asserted relation

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `40924c9c6872aa9a6e12b027e6389976f060fc3b34cb001269da3e24eb125703`
- Postprocessed candidate SHA-256: `bc7dd714adfc754360bd5f7912a61b7a2fa956d9bfbddd5f25c540dfd1fbaa0b`

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
- Model-boundary output SHA-256: `9ef1a51c2c4e761defad0b44297b56dc881e825d0a89f7e911aada8dad82a721`
- Postprocessed candidate SHA-256: `5ae8e282e22a144a3a52bdb6353f3dd0da1777a6845f69206d0568e66b5cdf4b`

## Unresolved Adjudication

- `holdout_multi_clause_ret_ntrk`: excluded from quality denominators; unresolved frames `holdout_multi_clause_ret_ntrk_02`
- `holdout_population_futibatinib`: excluded from quality denominators; unresolved frames `holdout_population_futibatinib_01`
