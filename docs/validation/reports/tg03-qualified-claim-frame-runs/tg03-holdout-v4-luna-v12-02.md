# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-v4-luna-v12-02`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v12`
- Fixture SHA-256: `4dc0c34b8572e879cab1c54d53b8117f9dc296b0522fd7b35ea371f169c8f413`
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
- expected_source_measurement_count: `4`
- output_source_measurement_count: `3`
- matched_source_measurement_count: `2`
- source_measurement_precision: `0.6666666666666666`
- source_measurement_recall: `0.5`
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
- Model-boundary output SHA-256: `5fa5285725fb38330ecb98fb2f6add19a1419e870c591b006b2a8927de1f001b`
- Postprocessed candidate SHA-256: `b189745da0f9197963912dce2677177e11756a0f0a84d87de1269ffd9d2d7b8b`

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
- Model-boundary output SHA-256: `c423606279a98e8b4954c45be8e186280120b59fb214e62702c5d9b3c11d033e`
- Postprocessed candidate SHA-256: `6722daf74d2bc5776ec362fc50f470a9926e9efd2d1912c768d5c3ac4f198d3a`

### holdout_null_margin: Null result beyond a prespecified margin

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `2105f33303a062a05753ec3363e31f3e059b280539ddca2147f2ed532bdfaed0`
- Postprocessed candidate SHA-256: `543242b03a6d7d4dd9ee2cd67aed4aff31480122bb1eec751043a895b7c2e976`

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
- Model-boundary output SHA-256: `135cda120ed564dd3c82d3ff0577fa227b11f45e6212f4e914ec0b95fbb91b9d`
- Postprocessed candidate SHA-256: `398b549d3eec526daab4b87699dd617779360f370ac7944f206332b9e6cd7ff9`

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
- Model-boundary output SHA-256: `cba2afb610e44858e2a6d3f314aad299b6b0b9c9d7c547c702db76433bf86f71`
- Postprocessed candidate SHA-256: `284c83cb5827b5a799a347ef4579e3c2001ec3f04c1839d11de60cc630128eb5`

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
- Model-boundary output SHA-256: `f35b454b95dc7b96eb6e1dac618521dc4b5acd117d16ed33e9895830a1114769`
- Postprocessed candidate SHA-256: `7cb1872d9b71c81dda475c61958fa60da3e77834a592b90c17c4d86f87234c15`

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
- Model-boundary output SHA-256: `99aae6e3473ca8bfd8683ffd7431a0723c6039a27b30e1c6560d4a0b12e808d7`
- Postprocessed candidate SHA-256: `eb8b826895a6941c99f41240f3057a93c32c9dff25032114ab9ae0e487e51814`

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
- Model-boundary output SHA-256: `611f011cca15a1b4e3f58ec5ae454f6583e246446d1f9a346d3b9f0ea7dfb7d4`
- Postprocessed candidate SHA-256: `c06ed845b2076f7cf41036d5e95b20c3a0afab89693981a5bdab8841c3bdf954`

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
- Model-boundary output SHA-256: `fcfbcbddb9eb0cf7662da76f80eade60c5e1083413fb20805687a91e9178e190`
- Postprocessed candidate SHA-256: `207232c4a19d0f420dde923d22687c8e7a544cf43a2664a63edd76a28157099f`

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
- Model-boundary output SHA-256: `03e84f0a6bdd4731bac4a39d3c4bdae9f7e2a64aa8ca9054add044df19626c04`
- Postprocessed candidate SHA-256: `eab98ce727c0703f82660b44d0fca8d9035c0093a488d0516d34964b0552f891`

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
- Model-boundary output SHA-256: `c790ea5388f60a54b685c5573faab1b71cda659a04551ccc3d1845edd95273be`
- Postprocessed candidate SHA-256: `211c61eb94ddb19b101ad3daca72e95063f4af614fa83db6a303824c897e0437`

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `d08fcf0007b3dbcf7fe03ff750ec115747c5000c962d72e6588b32d8267d201a`
- Postprocessed candidate SHA-256: `f2d4b7645633c210f5f93fc8529ae93bb59dad671ffdf28403b19bb39098f58c`

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
- Model-boundary output SHA-256: `d2f8110fe41e80148e98146d0a27b1c5afbc3f97a8e7380d241a370d50b87652`
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
- Model-boundary output SHA-256: `492ba9e065f9a351a592a0396ef413c9e83e1281ac5ec989f09884f4aeb2d2f6`
- Postprocessed candidate SHA-256: `6c7c8721dfc86dee6be7c8bd82129f9648211c39a8c13dc7a2e5556639eee68a`

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
- Model-boundary output SHA-256: `214b83bc15799eb4f1573d236c29827adbb1b9e20a5f329adf820d7114094c28`
- Postprocessed candidate SHA-256: `76d8449c640850a17b5f637011917105aac29ab79d8b17e5a723bc6b0a7face2`

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
- Model-boundary output SHA-256: `73f1c81586bc5193f88c42b96776900da785cd0490f82055ce7fb8298fc83205`
- Postprocessed candidate SHA-256: `9fca28e19a5f5a405324894dd6bf907bdb92f991c85bac357a33a47f386c9b27`

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
- Model-boundary output SHA-256: `3cdfffd1b52315660326bf4ed72d2afd326878c853a384598792f03a38119247`
- Postprocessed candidate SHA-256: `155387c821b559068b2c462e4fec1f33f4cacf59c6f419b59a31129f4e4fc5b6`

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
- Model-boundary output SHA-256: `74fe61f9fae4989307858f65970bc1a91f1fae0f3e3692f5092fdca1f3bc8750`
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
- Model-boundary output SHA-256: `4bc9ce8f7a7e580b6f201412554233422e0190633831d7d7f9117a762d4b3739`
- Postprocessed candidate SHA-256: `96246311f52833798af1bd493a96e0c19ecb509398a5ec71b05cf66120f34264`

## Unresolved Adjudication

- `holdout_multi_clause_ret_ntrk`: excluded from quality denominators; unresolved frames `holdout_multi_clause_ret_ntrk_02`
- `holdout_population_futibatinib`: excluded from quality denominators; unresolved frames `holdout_population_futibatinib_01`
