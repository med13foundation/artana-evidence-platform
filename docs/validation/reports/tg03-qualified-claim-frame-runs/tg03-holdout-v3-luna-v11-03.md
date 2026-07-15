# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-v3-luna-v11-03`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11`
- Fixture SHA-256: `a5b31c2111a4f2f25017a70c3ce3d33f844e3a939eb918c621ba7e5d9d6d3658`
- Methodology complete: `True`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `17`
- endpoint_source_match_count: `11`
- full_frame_correct_count: `6`
- quality_case_count: `17`
- unresolved_case_count: `2`
- unresolved_expected_frame_count: `3`
- agent_invocation_completion_rate: `1.0`
- strict_usable_extraction_completion_rate: `0.9473684210526315`
- explicit_polarity_concordance_rate: `0.5294117647058824`
- epistemic_status_concordance_rate: `0.5294117647058824`
- required_qualifier_completeness_rate: `0.5454545454545454`
- qualifier_concordance_rate: `0.4117647058823529`
- endpoint_source_match_precision: `0.6875`
- full_frame_precision: `0.375`
- expected_source_measurement_count: `1`
- output_source_measurement_count: `3`
- matched_source_measurement_count: `0`
- source_measurement_precision: `0.0`
- source_measurement_recall: `0.0`
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
- Model-boundary output SHA-256: `5cd3b849ce2085c0d4e8e44f9f657dd6687ea7a10e90561519d162dbf879c755`
- Postprocessed candidate SHA-256: `0b06b9ea397aef70e84d6114e41d8953b62d254d12320c4b50ab5e7f63ad5618`

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
- Model-boundary output SHA-256: `3432121c20b7045085c6aba1b000327002f61b748c238eff78b5e664d989c105`
- Postprocessed candidate SHA-256: `767d7b8bb4b080622efe2b8c935843413deb77470fdb83c4bccecd83a13f22aa`

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
- Model-boundary output SHA-256: `548d8138723c586eab3088de663f554b5f303d4501ef34a168e219cadb7aceea`
- Postprocessed candidate SHA-256: `714eb0c747bd7ae282d192f39f1b24808d1967ae7a4856846f0107227d93f2b4`

### holdout_provisional_zanubrutinib: Provisional treatment signal

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `1`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `4d2e2db919e9562287ca9eba62be915567359d850ca8ae2a2a8230d2c9e82e24`
- Postprocessed candidate SHA-256: `7eea39316055abad7b21dfa5c182aa3986064f410936adf0d2ba221f23088209`

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
- Model-boundary output SHA-256: `08e62d0cc497a78c92df0a60429b35d2f71ed95ed0f6a2d4a74283d1a28535e9`
- Postprocessed candidate SHA-256: `157ac3fbcc275e96517977112c8fed583b72018b0f4ee0b52c5463e833edf4c9`

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
- Model-boundary output SHA-256: `2893d7268183953279eedcf259429776124c7143b8e27eb96347c66ce769615b`
- Postprocessed candidate SHA-256: `043800a2f2bacf378f8d7ba85c727b1606acd4524eeb2adc481d757ba696e879`

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
- Model-boundary output SHA-256: `2e7a62b4241de2a56926a1c7e904777c820c15e94f8d0e184ebebd5c7f45353f`
- Postprocessed candidate SHA-256: `5c8c3fd9176febe4fb6223207aa729ba11c3455debc9437ae217f5bf446beb68`

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
- Model-boundary output SHA-256: `d481109f3510737cb3849fa6a82519c3b13fe89da49f510d17525decdca61f0c`
- Postprocessed candidate SHA-256: `dff28abac6c2d7c8962c650c20d73449a4fee4208adad60d53cbe145e3f61b93`

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
- Model-boundary output SHA-256: `104022db2402a30b8b787ae0d83de24f62721760152aef3627cdbe36767d1da0`
- Postprocessed candidate SHA-256: `c736401ca3fefe66f008fef743b74ad9358465a7abe5b28edf98cb18c63acd71`

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
- Model-boundary output SHA-256: `e996e5cc1f4e8c5d61e33e8fdea956466290d4c9a14bfbd49979839553a14aac`
- Postprocessed candidate SHA-256: `bb5e0e60eed2a447735ea74734454999282816b9e57de7fd6ed55833fadf5d52`

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
- Model-boundary output SHA-256: `81acf415c2c87e80bda62c105a7cb89c251b738bdcac1dadbc45dab2cfa0b7b1`
- Postprocessed candidate SHA-256: `6ad444c5f0f82a438b225d1d923ee6988ce31ba002b238cfa3601589da1ba1cf`

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
- Model-boundary output SHA-256: `f164bb969272ff7a7b041130e9beec5fbd7e658394ac68c19d01121fcf80686d`
- Postprocessed candidate SHA-256: `f4090644f69fc3f9d9c6dea3fbaf7bb5a0e925d2001507dcf3b29ff8f7530aff`

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
- Model-boundary output SHA-256: `6937f044c98092fb1387494b3e2f8f02b4e2360d51654570742c3fe15dcd1fdb`
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
- Model-boundary output SHA-256: `a109f439738674fe98d8685843bb9e4060a77eb0270472a18ee627507be0d4b8`
- Postprocessed candidate SHA-256: `bda53ace843f7fa8b91b1210443bdef026c370decfe0f0e41a0fed4c6e3abf61`

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
- Model-boundary output SHA-256: `6ab57eda4ccfde1cf91cbe20eba181c525b43354c34daf265c4c52cef7cc6d79`
- Postprocessed candidate SHA-256: `19f295558bd4207347709d892afdd151ae97aa18dcbbe37e847c2f82c0f9f3d3`

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
- Model-boundary output SHA-256: `cd4399e6e60540669860ee16c81e5bc535b06254259c406a70de4c09a216a95f`
- Postprocessed candidate SHA-256: `e0ca20e1001044e7b3e0728576db1a0b335fe1a7e0a9c8b294e11ee67eb3f562`

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
- Model-boundary output SHA-256: `d5306d0b2f095f50e8068c030bac1934a5ab48fc061197028586c3cf5c3ab1ce`
- Postprocessed candidate SHA-256: `54fa242c2f1cc6bfd44c672aaa80abb8a25151049f9c64dbc51e6170fe43f950`

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
- Model-boundary output SHA-256: `67340aafbb65e6635ed507a775399879739a313d0a9b6d7d2aedc103f6cffbb8`
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
- Model-boundary output SHA-256: `2e6c53d600d79beb77f43762c4ea083a761c87b668c890e1905447e828a9727c`
- Postprocessed candidate SHA-256: `24ccf039f86b8a6b2b8bbbf8d83c81e4aa1f348f714b3a36cdf4f696ee2a3a3a`

## Unresolved Adjudication

- `holdout_multi_clause_ret_ntrk`: excluded from quality denominators; unresolved frames `holdout_multi_clause_ret_ntrk_02`
- `holdout_population_futibatinib`: excluded from quality denominators; unresolved frames `holdout_population_futibatinib_01`
