# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-v4-luna-v12-01`
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
- full_frame_correct_count: `8`
- quality_case_count: `17`
- unresolved_case_count: `2`
- unresolved_expected_frame_count: `3`
- agent_invocation_completion_rate: `1.0`
- strict_usable_extraction_completion_rate: `0.9473684210526315`
- explicit_polarity_concordance_rate: `0.6470588235294118`
- epistemic_status_concordance_rate: `0.6470588235294118`
- required_qualifier_completeness_rate: `0.6363636363636364`
- qualifier_concordance_rate: `0.47058823529411764`
- endpoint_source_match_precision: `0.75`
- full_frame_precision: `0.5`
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
- Model-boundary output SHA-256: `c32787ffba851f75614e6d99ebf3d539afc4497f813bb61c1a8cf636ccdc4712`
- Postprocessed candidate SHA-256: `282d6e4c531685d46e56186013bc6b56f43b2a8b79da58d3d78c4b9bdb0bdd31`

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
- Model-boundary output SHA-256: `2b22d456f40099783b5e54b07bcfac2aa068a0ec4978a97fcf8e4246da4ed89f`
- Postprocessed candidate SHA-256: `0eff137afea887eae1d30f320da0a6929c156887aebf31385430aecb3b5dc17e`

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
- Model-boundary output SHA-256: `26a8e3acd15aae6479406e974a33fdcf82e5ba270ec23e6cb8f284356a95c982`
- Postprocessed candidate SHA-256: `cae424f0c199091edc3a5bc2b5abc0e7315a64c6bddc680afcc2072852f744bf`

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
- Model-boundary output SHA-256: `35fcd9ff5dac8b662e4c104b73ccf9260aaf9f02efd0b69ce8720c8099c95a20`
- Postprocessed candidate SHA-256: `9435d51ee9af24527da2c171d0a64b3bb82da0fd8f0af614deebe5cbfafd37b1`

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
- Model-boundary output SHA-256: `3ec08e283b4da91cc4dc615dc4c91443f524c7cc5580e7c19aee15466e72cc54`
- Postprocessed candidate SHA-256: `fa1a1fe07df43b93327b0321959d47e4002cd7ab5eb577d92e22baadfc033545`

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
- Model-boundary output SHA-256: `7a730c71b67b293d2e1e34b0dbbf53ac493a06b725fa2c92f67c5fd88868933f`
- Postprocessed candidate SHA-256: `dc888d79a7e2fa084fc4e53d7f66d73025a4f573a7bc7f7f7544fabcc7bf8f90`

### holdout_intervention_ctdna: Intervention outside the endpoints

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `69f6675c989542d2d589bb8a7d0416038af54caf0ac83eb39db84ebf6aac7340`
- Postprocessed candidate SHA-256: `c2013775ef3f830746d7d6bbcfcc48dcb3043a1307f5b7f666968729d674eecc`

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
- Model-boundary output SHA-256: `a252b183500ac0eb9ae8fe713fcd2629d64b3a5b86f535a71e779981e6cb4c7a`
- Postprocessed candidate SHA-256: `c8fde83b7837cfe174a12c2d10ec2c6fa8e2ef968a3b8ca41a7f7f0f8ff43b07`

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
- Model-boundary output SHA-256: `d24b761d21b891ad8968bf6bb9fa6788e62b968436af2c258953ccd12ba279ab`
- Postprocessed candidate SHA-256: `ee48a9298f99c07d14f2ff3f5679ee430c00b5b3d84fcd35297e078636f523d0`

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
- Model-boundary output SHA-256: `8766dfdb23284b4d137946e6282674899066cafff0f115277ff189c7237daff1`
- Postprocessed candidate SHA-256: `a76293b0939ddf9edbeea892284701dfca72126d51647f2eb9a2cd7b33ecbeb4`

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
- Model-boundary output SHA-256: `0b9616a75984491006197983f5fa63196240b5b1d490242bc3067968c3920162`
- Postprocessed candidate SHA-256: `2541b42d516bc839241997f1a95c9420f2be1197228b997e39c786006f5a8c3d`

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
- Model-boundary output SHA-256: `80fa5409d866847938d63556230674760791342f0699a86ed4a69230bebcf700`
- Postprocessed candidate SHA-256: `8035c65d5254f36e9fc7bf45e533606a37e5dcc7e6f7c7550e6acc934726e075`

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
- Model-boundary output SHA-256: `84cf9e6f34c060676176bc86da89aff6f3f9081353e7bc01343ed648d0fd2c8f`
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
- Model-boundary output SHA-256: `c756f0bc0fe2a891f0726160e9ab15fa2a019a9b391478cfc9290c8c1bbde7f8`
- Postprocessed candidate SHA-256: `df958c6880bda14e71d3e6d615ee55c7c8389adbf4697748bdc7804da922160b`

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
- Model-boundary output SHA-256: `b031458334476972ebd6ab1530977653141ec4134755d09a5b9fbb4c6173fb08`
- Postprocessed candidate SHA-256: `3d29e01eb562113c3ee92917cd602742cdbb610e2141fbfddacd15cfd2161742`

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
- Model-boundary output SHA-256: `9283174218f15421b313e874ea9066ebb1db43695fa51764eaf2eb0da7025249`
- Postprocessed candidate SHA-256: `794da7348c3dd68f1f59c3e9c7cc3485cc2c200bb0476564b0d464c625a529ad`

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
- Model-boundary output SHA-256: `906013fd796ba2025fde33d1329d79f6e37fa699f6ebaf03d72d626bdfa8bd5b`
- Postprocessed candidate SHA-256: `b21b9f6f054679b7d949a4128a1e34a830adc260619dea25e6b6926efbf8c5ca`

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
- Model-boundary output SHA-256: `9b06e6ee8be3d67bde516be71a969675736a39513b8f9404525885eb52bf9955`
- Postprocessed candidate SHA-256: `2e304c14a21dc6000c066c087e57d01c667f3f6c8afc5988a141a41ef7a7cc57`

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
- Model-boundary output SHA-256: `c39aa9084bc14dd4f9ccdc7f0629b3fea60649f8b124c5d2690b9cb05499660c`
- Postprocessed candidate SHA-256: `6df826be6aba4548746d39757e28f950f1efc1e7a3114d7713ca5189418264cd`

## Unresolved Adjudication

- `holdout_multi_clause_ret_ntrk`: excluded from quality denominators; unresolved frames `holdout_multi_clause_ret_ntrk_02`
- `holdout_population_futibatinib`: excluded from quality denominators; unresolved frames `holdout_population_futibatinib_01`
