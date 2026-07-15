# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_comparison`
- Run IDs: `tg03-holdout-v4-luna-v12-01, tg03-holdout-v4-luna-v12-02, tg03-holdout-v4-luna-v12-03`
- Model IDs: `openai:gpt-5.6-luna, openai:gpt-5.6-luna, openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v12, document_extraction.llm_extraction.v12, document_extraction.llm_extraction.v12`
- Fixture SHA-256: `4dc0c34b8572e879cab1c54d53b8117f9dc296b0522fd7b35ea371f169c8f413`
- Methodology complete: `True`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `51`
- endpoint_source_match_count: `34`
- full_frame_correct_count: `22`
- quality_case_count: `51`
- unresolved_case_count: `6`
- unresolved_expected_frame_count: `9`
- agent_invocation_completion_rate: `1.0`
- strict_usable_extraction_completion_rate: `0.9298245614035088`
- explicit_polarity_concordance_rate: `0.6078431372549019`
- epistemic_status_concordance_rate: `0.6078431372549019`
- required_qualifier_completeness_rate: `0.6060606060606061`
- qualifier_concordance_rate: `0.43137254901960786`
- endpoint_source_match_precision: `0.723404255319149`
- full_frame_precision: `0.46808510638297873`
- expected_source_measurement_count: `12`
- output_source_measurement_count: `8`
- matched_source_measurement_count: `6`
- source_measurement_precision: `0.75`
- source_measurement_recall: `0.5`
- unmatched_output_count: `13`
- unsupported_positive_output_count: `10`
- unsafe_assertive_upgrade_count: `0`
- positive_on_negative_or_null_count: `0`
- agent_authored_quality_score_count: `0`
- source_measurement_without_span_count: `0`
- exact_semantic_frame_stability_rate: `0.17647058823529413`
- canonical_semantic_frame_stability_rate: `0.29411764705882354`

## Gates

- agent_invocation_completion: **true** (all strict cases completed a real agent invocation across all runs)
- strict_usable_extraction_completion: **false** (all strict live cases produced usable extraction across all runs)
- polarity: **false** (explicit polarity concordance is 100% across all runs)
- epistemic_status: **false** (explicit epistemic-status concordance is 100% across all runs)
- qualifier_presence: **false** (required qualifier presence is 100% across all runs)
- qualifier_concordance: **false** (all qualifier categories are gold-concordant across all runs)
- endpoint_source_match_precision: **false** (endpoint/source match precision is 100% across all runs)
- full_frame_precision: **false** (full-frame precision is 100% across all runs)
- source_measurement_precision: **false** (source-measurement precision is 100% across all runs)
- source_measurement_recall: **false** (source-measurement recall is 100% across all runs)
- unmatched_outputs: **false** (unmatched output frames are zero across all runs)
- unsupported_positive_outputs: **false** (unsupported positive output frames are zero across all runs)
- unsafe_assertive_upgrades: **true** (non-assertive gold claims are never upgraded to ASSERTED across all runs)
- positive_on_negative_or_null: **true** (positive output on negative/null cases is zero across all runs)
- agent_quality_scores: **true** (agent-authored quality scores are absent across all runs)
- no_fallback: **true** (strict reports contain no fallback output across all runs)
- measurement_spans: **true** (source measurements all have exact spans across all runs)
- stability: **false** (canonical semantic-frame stability is at least 95%)

## Cases

### holdout_variant_alk_g1202r: ALK resistance variant and population

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-f749d36fa8bc41b5ab476bb365c6548e, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-0abea26fdb18403d960186408dea4c80, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-d01744ee02f94059bb6664e1374cc508, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

### holdout_explicit_negative_tmb: Explicit biomarker contradiction

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-af44918032034093af6060661e6b0ea9, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-df00c29567c04ec6a5b82210467d50c2, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-58c332dcba364c70abfd22eacffe9bce, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=0, qualifiers=0

### holdout_null_margin: Null result beyond a prespecified margin

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `1`
- Polarity correct: `3`
- Qualifier-concordant: `1`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-42019852183e4a3fb83f7bbcae33bb5a, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-4040156e24ca46caa858e34fa800a819, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-1639614249844c0cb48f222b1955ec76, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_provisional_zanubrutinib: Provisional treatment signal

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-707143ffe5764de28175ae590f5141a2, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-f0adc7ae63f540ff94990d45301e11fc, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-a25132c78eb849649157ca50a86a3f10, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_uncertain_talazoparib: Uncertain treatment association

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-122e419da2034182b119a635a9e3df24, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-8f1dd937adff48d9a4a56f6a76bfa1b3, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-8269458a3e9d490fbca6c4d2a93997ee, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_hypothesis_keap1: Mechanistic hypothesis

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-cac639c5061b4505a77c769af302e605, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-1c545da2d05342e2925e22e517c1aecd, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-52e5d435d44a4226b97cf986207f3105, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

### holdout_intervention_ctdna: Intervention outside the endpoints

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `2`
- Polarity correct: `3`
- Qualifier-concordant: `2`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-07ecc9ce78b6450f98f1640c0ead7bcd, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-0493b7d7d4db4a1b8f73413719a46e58, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-4cf815b468ec41b9a5a168487f0f88e7, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_comparator_amivantamab: Active comparator

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `2`
- Full frames correct: `0`
- Polarity correct: `2`
- Qualifier-concordant: `0`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-b2fe69dee8a548598a09c1567c3e1546, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-477b3b83415245a9a8b6a28e42491fb1, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-4d5bbddc58f6401cb1d7803f48861ae7, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

### holdout_outcome_enfortumab: Measured clinical endpoint

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-cc096af7cbe04e3ab69978864c85cd1c, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-9ca12cbf12e54708b88c7781d29d24fa, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-4491509f447e48568d5622b426b74352, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

### holdout_study_adagrasib: Study design qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `0`
- Polarity correct: `3`
- Qualifier-concordant: `0`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-192cc913d4fb4979b90fef39c3c79054, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-d21844dd10574b4fa8095615329a242c, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-423cf1b748b748d7b0432ff4755793eb, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0

### holdout_setting_ibrutinib: Treatment setting qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-b208383ba73246c88d8feddc02e179c1, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-31b5c60ab430480a8d8a8a8ca16c962b, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-ee6801ddac3d4471929c38334d41886e, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `False`
- Output frames: `2`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-26ba46d043494c0f880328a83d6e1112, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-95d8dfbeed8a4fbb971197924d1834fa, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-eb0932e7e13d4ba68adffb91fa94193f, agent_completed=True, strict_usable=False, output=0, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

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
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-5f7c93619572427998d702c27dbea5bf, agent_completed=True, strict_usable=False, output=0, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-5b091dbdd44840789ad55ad98be9e769, agent_completed=True, strict_usable=False, output=0, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-82078413091443e89c9b4ccf50884218, agent_completed=True, strict_usable=False, output=0, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

### holdout_multi_clause_ret_ntrk: Clause-local sibling claims

- Adjudication: `unresolved`
- Included in quality metrics: `False`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `6`
- Endpoint/source matches: `3`
- Full frames correct: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-838d33ed00854ab1ad2b8e124b050028, agent_completed=True, strict_usable=True, output=2, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-1d539e92cec34c33b827964733236a4e, agent_completed=True, strict_usable=True, output=2, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-48f09eaabb1e48f3a7d225545da1acfd, agent_completed=True, strict_usable=True, output=2, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_extra_output_capivasertib: Methods and funding output trap

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-9b245b2d31df4401bdc1c424e97f7821, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-d87938cd2d10427b8b6931a05e41344e, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-1681ff066f5a458d9109f33b8cfea5c9, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_unresolved_population: Explicitly missing subgroup

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `2`
- Full frames correct: `2`
- Polarity correct: `2`
- Qualifier-concordant: `2`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-317e99ca24e04166a33a099d412646ba, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-18dcf88b866346c89e44b568ce27e5dc, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-d3ca2f59d4d14c9188ab8999c316590e, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

### holdout_source_measurement_repoterctinib: Literal source measurement

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-5c8c205098564bbaa31b346e199b7e89, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-6d25178318544249994b0a9a2888a03b, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-f4cb70487ccf491998e4f2acadfb34bf, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_positive_sotorasib: Positive asserted relation

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `2`
- Polarity correct: `3`
- Qualifier-concordant: `2`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-7a497aa157104e6a8a0de24d05401906, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-bca04e8feef04e3a937d7862224e5757, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-fa6836618a33488c80d360308be3b07b, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0

### holdout_population_futibatinib: Population subgroup qualifier

- Adjudication: `unresolved`
- Included in quality metrics: `False`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `0`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v4-luna-v12-01`: invocation=tg03-invocation-7968f66195c04a79a3c4580223970af5, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-02`: invocation=tg03-invocation-2fbdd1fe6aed45b9a8428e4b297d4b87, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v4-luna-v12-03`: invocation=tg03-invocation-d18cbbe7e1094f60ae53f05dc75735e6, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

## Unresolved Adjudication

- `holdout_multi_clause_ret_ntrk`: excluded from quality denominators; unresolved frames `holdout_multi_clause_ret_ntrk_02`
- `holdout_population_futibatinib`: excluded from quality denominators; unresolved frames `holdout_population_futibatinib_01`
