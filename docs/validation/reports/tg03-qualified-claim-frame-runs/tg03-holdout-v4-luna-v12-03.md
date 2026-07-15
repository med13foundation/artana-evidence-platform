# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-v4-luna-v12-03`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v12`
- Fixture SHA-256: `4dc0c34b8572e879cab1c54d53b8117f9dc296b0522fd7b35ea371f169c8f413`
- Methodology complete: `True`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `17`
- endpoint_source_match_count: `10`
- full_frame_correct_count: `7`
- quality_case_count: `17`
- unresolved_case_count: `2`
- unresolved_expected_frame_count: `3`
- agent_invocation_completion_rate: `1.0`
- strict_usable_extraction_completion_rate: `0.8947368421052632`
- explicit_polarity_concordance_rate: `0.5294117647058824`
- epistemic_status_concordance_rate: `0.5294117647058824`
- required_qualifier_completeness_rate: `0.5454545454545454`
- qualifier_concordance_rate: `0.4117647058823529`
- endpoint_source_match_precision: `0.6666666666666666`
- full_frame_precision: `0.4666666666666667`
- expected_source_measurement_count: `4`
- output_source_measurement_count: `2`
- matched_source_measurement_count: `2`
- source_measurement_precision: `1.0`
- source_measurement_recall: `0.5`
- unmatched_output_count: `5`
- unsupported_positive_output_count: `4`
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
- source_measurement_precision: **true** (source-measurement precision is 100%)
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
- Model-boundary output SHA-256: `6c15dde67a761287ee34e79674ab2da064300fe2b95164a9d3e5389850a16611`
- Postprocessed candidate SHA-256: `0a9b828ccf9dd0f08d5ffbe136229a3ad7850068ab265630b3a166e79ebc5cd4`

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
- Model-boundary output SHA-256: `3043c1d62e7c85ff5ad35e2a31a194c42a920ef35da1abdca92d77b4ca41a5ea`
- Postprocessed candidate SHA-256: `ea378d5f14a1446847727b56ac2adc07a056dabae6d83a74f4d6f5bffba3f058`

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
- Model-boundary output SHA-256: `ba062080fb2ee2b27c65b6832d5f1d5dcb9f0d51f5a93ff1b83009c9847b9f48`
- Postprocessed candidate SHA-256: `f2b9abedd0d20e0ec37139e01b1665b7d1d4b5a3e3c4f1d1cf540a966ff71099`

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
- Model-boundary output SHA-256: `3c1f16dfc3baf48ece2a5638cc66e85c41a9633fcefc05cc3482d31b5b1c442a`
- Postprocessed candidate SHA-256: `ef4a1fae54bb3808ef17a9ee5ab5cc6a9e6b280ce56b1e4d71faa6e55320bda6`

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
- Model-boundary output SHA-256: `244847f99604661ff195a019f7edca3a66923bb7217ba031c43979f541130f04`
- Postprocessed candidate SHA-256: `46451aa58ce2276db688a2deb55f569fedb088a26be6d26cb96cc353fb55f579`

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
- Model-boundary output SHA-256: `2ef3313f755d4db832acfd2127428dce0c34b02767195d27f704865db15c0020`
- Postprocessed candidate SHA-256: `7843def6dc6b0c288a4bb823c9eb0bd09a23e623597e4f32ce50f627fe0d9bd5`

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
- Model-boundary output SHA-256: `e0fb9d75cc3ca2620673db603896ac2bbd21dcd6eb0e42b421d997032e4acc31`
- Postprocessed candidate SHA-256: `947eae569c0ea7d55443275bdfa7d5fdde40e3537b59fe5b9b1233e97435e09a`

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
- Model-boundary output SHA-256: `a8bcc7cf44eb5d5a99360ca85be7cb29478bd300ad14db08e9f498b450d599e4`
- Postprocessed candidate SHA-256: `f9419c8be5df199ecc83e035d8eb67660a75bb062ed22e2a0f363ba09849c43d`

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
- Model-boundary output SHA-256: `5024051593a4729f5f7f1b59cab420332ad3289f6013156ab2bac4bd01c78b03`
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
- Model-boundary output SHA-256: `cb1f8ff16b0add4af39a41860488179d6ed098c40470d1cc0976fd2bfba583ca`
- Postprocessed candidate SHA-256: `6408e91e781af0fd1c605f94243d347546baa64a8ea4aef748a400ef114aa6fe`

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
- Model-boundary output SHA-256: `17741c671c4b20bf74802225137027bd85202384c05da83620f2fc576f097f17`
- Postprocessed candidate SHA-256: `81d7215abe9f2da415cdb08601cca5f7f0c8c5e5d7592e048c15af3f16e669eb`

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `False`
- Output frames: `0`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `15a6292dc78ec4db50b22aee643c1ca5b31e6b0d4c8908dc1f7a455be7f1d88a`
- Postprocessed candidate SHA-256: `096ac3df03946e078dbe269a92a8543208cd3a306619c8121a6cf651f2586842`

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
- Model-boundary output SHA-256: `8d37456d217d4c408617488223df217c84d05dccf19c01e1164bee81d3cfb161`
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
- Model-boundary output SHA-256: `6f2c887fe0f7bc13f22f0eae518b163b93da4f8e7e3ac5e194e1ace3830c68a9`
- Postprocessed candidate SHA-256: `4cc3f86fe7f754aa8e4a9c20de4cf72d84658972029aada320c8bf6e9d69e884`

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
- Model-boundary output SHA-256: `ad42ad933bb3739c747ed8114316a3de44352ac698a8fdbb5285e2d2ea697a5c`
- Postprocessed candidate SHA-256: `4ef08f199e3b03873858be2bfef3e1f02a1a07760e539a6b3c89c552ae5131c1`

### holdout_unresolved_population: Explicitly missing subgroup

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `6ded2b23e484bff3e60b83342b0761e1fde3e288946c4d0d4dce7d7c84d0917a`
- Postprocessed candidate SHA-256: `712aaff61f29272142bd5b2be0a8b4bee52ee363fa6d71ae8e95511e3b486b23`

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
- Model-boundary output SHA-256: `ada661491ec638b49d11b4da5bd960b60c7e86d3a7ab4cb7ac6a80209baa647e`
- Postprocessed candidate SHA-256: `0600af3aa8c19454dfea218eb17339026db0530b56c332c341ddfd3fcd6a4620`

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
- Model-boundary output SHA-256: `bed50faf034309e18acfe482675c5099d4723a460e0b3b17566bc3636e504eae`
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
- Model-boundary output SHA-256: `bf7d64fa28de4cb87c45931abc76d5f9702018fe4655e2a477abac442779cfc4`
- Postprocessed candidate SHA-256: `fd8bb10120aff5073f484c38b9b901943442a053b0e1710e26e948cfc3e8a586`

## Unresolved Adjudication

- `holdout_multi_clause_ret_ntrk`: excluded from quality denominators; unresolved frames `holdout_multi_clause_ret_ntrk_02`
- `holdout_population_futibatinib`: excluded from quality denominators; unresolved frames `holdout_population_futibatinib_01`
