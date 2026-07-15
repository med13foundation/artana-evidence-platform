# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_comparison`
- Run IDs: `tg03-holdout-v3-luna-v11-01, tg03-holdout-v3-luna-v11-02, tg03-holdout-v3-luna-v11-03`
- Model IDs: `openai:gpt-5.6-luna, openai:gpt-5.6-luna, openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11, document_extraction.llm_extraction.v11, document_extraction.llm_extraction.v11`
- Fixture SHA-256: `a5b31c2111a4f2f25017a70c3ce3d33f844e3a939eb918c621ba7e5d9d6d3658`
- Methodology complete: `True`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `51`
- endpoint_source_match_count: `36`
- full_frame_correct_count: `21`
- quality_case_count: `51`
- unresolved_case_count: `6`
- unresolved_expected_frame_count: `9`
- agent_invocation_completion_rate: `1.0`
- strict_usable_extraction_completion_rate: `0.9473684210526315`
- explicit_polarity_concordance_rate: `0.6274509803921569`
- epistemic_status_concordance_rate: `0.6274509803921569`
- required_qualifier_completeness_rate: `0.6363636363636364`
- qualifier_concordance_rate: `0.45098039215686275`
- endpoint_source_match_precision: `0.75`
- full_frame_precision: `0.4375`
- expected_source_measurement_count: `3`
- output_source_measurement_count: `9`
- matched_source_measurement_count: `0`
- source_measurement_precision: `0.0`
- source_measurement_recall: `0.0`
- unmatched_output_count: `12`
- unsupported_positive_output_count: `9`
- unsafe_assertive_upgrade_count: `0`
- positive_on_negative_or_null_count: `0`
- agent_authored_quality_score_count: `0`
- source_measurement_without_span_count: `0`
- exact_semantic_frame_stability_rate: `0.11764705882352941`
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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-4af3ebc492ac4de7bab9d59a23742c9b, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-909213f94df04cd888393a9d4eebc019, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-7bf619493c144b14bb38cb067ae498f0, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

### holdout_explicit_negative_tmb: Explicit biomarker contradiction

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `0`
- Polarity correct: `0`
- Qualifier-concordant: `1`
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-e77909f6a4e041a294948ac96f31ff15, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=0, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-400a5a34fa3d459cb545110c9413283a, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-c3fe40e315914642ba49e69e9ccc9f3a, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=0, qualifiers=0

### holdout_null_margin: Null result beyond a prespecified margin

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-049af64fd98b4b06b0c2c058341fb47d, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-28fc413c586342a69854358edb6ebabc, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-2a4af194d5f04b0f9b1e4ac73747051f, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_provisional_zanubrutinib: Provisional treatment signal

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `1`
- Polarity correct: `2`
- Qualifier-concordant: `2`
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-70f361d77b4a4e07b5b120dfa1b38feb, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-a22343818eb54b9db90c2535746afafc, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-7ce8e86ab9294378b47f1f3d73d9233d, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=0, qualifiers=1

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-01427c5108c44ce793edb72fdd8c17f9, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-78493ee5febd4604b3e11caac9b1f89d, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-7414878e25e048e7b6ae5b2876571695, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-3d71b81477f04f0c9aff3a4459d6c95d, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-bc7b4d6f76604cc6a39a776bda0834aa, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-0871e9b943ff4f9d8132ac7d749740aa, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

### holdout_intervention_ctdna: Intervention outside the endpoints

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `0`
- Polarity correct: `3`
- Qualifier-concordant: `0`
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-44596c17bf454d41b0efc5182e4c0f48, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-e81c7d5694f84e9baf08ec3f1c3c23ec, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-1bae3355c6624e06b3cf129cfeebe9d9, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0

### holdout_comparator_amivantamab: Active comparator

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `1`
- Full frames correct: `0`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-2ae473b99ebc4bb8b7f49a6ac048cc80, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-c03f8746a4bc458791b88addd345086d, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-e016aeded2474045accefe5dbab93eed, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-afbf8a4179084b85b77337c49cdfa290, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-4b1044a71e954a999450d1ef6a263aa5, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-531f6812475c45cca0b69fb544e79856, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-0d4cebecf27347ff9531a2e82d3d6aa1, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-ec29d461a6f44f4ab3b483de4dcc0e4f, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-cfbe434c741347fdbac830ff27b8f370, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-dd55cbc654464cd59f50cc7d970395ae, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-a170bd14ff1648188af27c0465a48403, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-2ea8e804c53749bd8de3aef363767550, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `2`
- Full frames correct: `2`
- Polarity correct: `2`
- Qualifier-concordant: `2`
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-e3a7c2f2a28a4b1eb927f97e4a3658cf, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-0f615cac931b4535b7dbb177ab68a196, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-c2bb89974a704f5b939e1eed4ab14962, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-703ec90d87e648f29a0458210c24df6a, agent_completed=True, strict_usable=False, output=0, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-4cd3fd84c4c64f1980df5db9187e701c, agent_completed=True, strict_usable=False, output=0, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-8dba62e0402043cdb07ec13ea00c6ecf, agent_completed=True, strict_usable=False, output=0, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-a22c77f8674f484db77dd4917a8109a3, agent_completed=True, strict_usable=True, output=2, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-1cf04d3c8dc24d0fa3cedbe5254c1c22, agent_completed=True, strict_usable=True, output=2, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-cfaf330b3b0f4c1daffc01dd417ca9a2, agent_completed=True, strict_usable=True, output=2, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-a8c008cc1a0f41119ec0218b4a9c004f, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-d2a0a77282724fc8af3daf522c758e14, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-6b790b66c71e48278501aa864c283ea9, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

### holdout_unresolved_population: Explicitly missing subgroup

- Adjudication: `adjudicated`
- Included in quality metrics: `True`
- Agent invocation completed: `True`
- Strict usable extraction completed: `True`
- Output frames: `3`
- Endpoint/source matches: `3`
- Full frames correct: `1`
- Polarity correct: `3`
- Qualifier-concordant: `1`
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-256def6e914d4940ba83062f922cc4a3, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-049759989b064a65a044291ad8ccdf49, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-ea2412ffe36a4a36858d5821d09e0f3b, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-75332e45f82848409a4f02d087e7b84e, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-0785113985fb459cbe6f7fe872f984c7, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-d964aab2263d43c899a3f27c394060ba, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-2ef29832062942c7951219b4fb01828d, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-24aae264104f43169729b514bbfb8c71, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=0, polarity=1, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-43535abfe54b41eb8c0b0bbeb514137e, agent_completed=True, strict_usable=True, output=1, endpoint_source=1, full_frame=1, polarity=1, qualifiers=1

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
- `tg03-holdout-v3-luna-v11-01`: invocation=tg03-invocation-176db4ea514c497f8f81ab42544e8997, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-02`: invocation=tg03-invocation-77000d35e1584ae490a3cae943a4c210, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0
- `tg03-holdout-v3-luna-v11-03`: invocation=tg03-invocation-0ba440f9100943a6af7f577ebb9b6937, agent_completed=True, strict_usable=True, output=1, endpoint_source=0, full_frame=0, polarity=0, qualifiers=0

## Unresolved Adjudication

- `holdout_multi_clause_ret_ntrk`: excluded from quality denominators; unresolved frames `holdout_multi_clause_ret_ntrk_02`
- `holdout_population_futibatinib`: excluded from quality denominators; unresolved frames `holdout_population_futibatinib_01`
