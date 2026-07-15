# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-v2-luna-v11-02`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11`
- Fixture SHA-256: `22fbdf50333811d52e26296e9f1ddd561bfe0f29b0ed7d3771017199552ab956`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `20`
- matched_frame_count: `13`
- strict_completion_rate: `0.8947368421052632`
- explicit_polarity_concordance_rate: `0.6`
- epistemic_status_concordance_rate: `0.6`
- required_qualifier_completeness_rate: `0.6153846153846154`
- qualifier_concordance_rate: `0.4`
- frame_precision: `0.7222222222222222`
- unmatched_output_count: `5`
- unsupported_positive_output_count: `3`
- unsafe_assertive_upgrade_count: `0`
- positive_on_negative_or_null_count: `0`
- agent_authored_quality_score_count: `0`
- source_measurement_without_span_count: `0`

## Gates

- strict_completion: **false** (all strict live cases completed)
- polarity: **false** (explicit polarity concordance is 100%)
- epistemic_status: **false** (explicit epistemic-status concordance is 100%)
- qualifier_presence: **false** (required qualifier presence is 100%)
- qualifier_concordance: **false** (all qualifier categories are gold-concordant)
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

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `bce37d93d0c2aca52906003d18886eea388f7e67b45e0e2ed61193e9745272d9`
- Postprocessed candidate SHA-256: `89ba001833fa7a5e873cf051a331760b0d0c511af2730d502bf4817a24ce6d5c`

### holdout_explicit_negative_tmb: Explicit biomarker contradiction

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `85f10537b5f3af7c014ec54f5f9939d78ae48144b5434c143bac15e5f84ce8e3`
- Postprocessed candidate SHA-256: `22c7a37527ac9d0c0c576de36f92a39be3517c6279224365ed847868a6199fc9`

### holdout_null_margin: Null result beyond a prespecified margin

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `84423a673b083fcb28efb1acf96b4ecab5df798a094e0f4f19bd2a955f746748`
- Postprocessed candidate SHA-256: `4a1acdcbb708fd64e90625ae98319dbed79561915d3750a6a9ac1bd378386ddd`

### holdout_provisional_zanubrutinib: Provisional treatment signal

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `babe98449718a3590a212ed75b014a398ee8be000efe909b33cc334012735e9f`
- Postprocessed candidate SHA-256: `e65dd81534704f46a7f79227240b02a8f3c590ccc51ff2f121cc5490898b0afd`

### holdout_uncertain_talazoparib: Uncertain treatment association

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `c147eb93f8ced01b2a866a8d79f8f740964da08c4b1152c8b4a0ecfc736ae579`
- Postprocessed candidate SHA-256: `924327f7cd2d25ccb6b8495854b22cd7dead69542a0c69ec90f7c91ea906aeda`

### holdout_hypothesis_keap1: Mechanistic hypothesis

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `bba2d9608028d328440859719bed283ea7e8cf507e5b153ada12d91ac95236dc`
- Postprocessed candidate SHA-256: `c51ce4d1a5e632fa49b52578ad430cc61eac767f149d910807434b036c91ccfe`

### holdout_intervention_ctdna: Intervention outside the endpoints

- Strict completed: `False`
- Output frames: `0`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `93120b1837679b46c9e61d17d3b2e900cf91d45ccd98dd49db05663be1ff6605`
- Postprocessed candidate SHA-256: `096ac3df03946e078dbe269a92a8543208cd3a306619c8121a6cf651f2586842`

### holdout_comparator_amivantamab: Active comparator

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `304dda96d24fcd5c361b12083037102c86150d51af6115bdf4aab00ca56c6049`
- Postprocessed candidate SHA-256: `f6bf1d6f72cb7c92f0f30ee02df1ea03ed04f2dfe0bf4d87c771cb08ac9f2ef1`

### holdout_outcome_enfortumab: Measured clinical endpoint

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `435f65015dfdd4b21981a240c1d7e6b7f4221fb5db6a13c18bdadae5f2ddac6b`
- Postprocessed candidate SHA-256: `f43d82c8295741795fe4809fed0ba697d6e5b21f07f0f6908bf1de90dfaef1d8`

### holdout_study_adagrasib: Study design qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `c4828d8c5285cdd460e4b735bb1b9990a2dbb9a90d1f2a04924c6083aa0377d9`
- Postprocessed candidate SHA-256: `7b49e135f8b7da46552c562741db527a26d6530469f5a8961381e3fdd7e941e1`

### holdout_setting_ibrutinib: Treatment setting qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `8d9d4c85a30abb5d3b96f1877fe3c26ba86e8c00b758a57e1a30a04c8e6baa0f`
- Postprocessed candidate SHA-256: `9c765bab5b3b084538e951f36a8e0ea3d57bcf6020b537e8ed1a587a6b6a642e`

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `b9c357e4ddbfd17ca21df90e2396e100af8c4a5f4f95ab1bd2a8ccd371a42e1e`
- Postprocessed candidate SHA-256: `36e2d8a177d7be2a9d3a9f425a9d56f9c78cf2a9f6fc93ecc4dcc66b3c638392`

### holdout_threshold_cabozantinib: Numeric threshold qualifier

- Strict completed: `False`
- Output frames: `0`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `93120b1837679b46c9e61d17d3b2e900cf91d45ccd98dd49db05663be1ff6605`
- Postprocessed candidate SHA-256: `096ac3df03946e078dbe269a92a8543208cd3a306619c8121a6cf651f2586842`

### holdout_multi_clause_ret_ntrk: Clause-local sibling claims

- Strict completed: `True`
- Output frames: `2`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `2f8c01e7aabedb5cb8d004d0c39b81bf1280f11ee46f2e9c81cfc6833ddfbb84`
- Postprocessed candidate SHA-256: `d2ed7fd19dc194ca6b050b1bd42360874cd51751c05bbd89eb36e1acaa580457`

### holdout_extra_output_capivasertib: Methods and funding output trap

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `ca53daed0ee20bbfc3c4bfaa2a7b9435a9134602cc6c76ff439aecd0c4be19f0`
- Postprocessed candidate SHA-256: `65b7b942c256e3a2d64c2e2b2cd1f4baa66454aa04b0d22d6ceb4360b56f0e9e`

### holdout_unresolved_population: Explicitly missing subgroup

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `3375949811201be2717c977ccf500529de276db178b2070a00d3dee1c34b2713`
- Postprocessed candidate SHA-256: `44ff461ceb241d83d68b1b84fd376e3e8fa7e5aff2514a5f3d4a77e1f120126c`

### holdout_source_measurement_repoterctinib: Literal source measurement

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `1cd9be233b9e8787ef2af9055a14fb20511cf3cabaa951c7a571b47a6363ae8e`
- Postprocessed candidate SHA-256: `0f1a4bd50cd217717f1eb002d08fad447f39de305512ac8f4c53cabd0479ace7`

### holdout_positive_sotorasib: Positive asserted relation

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `447d248aee44f992b3a70c860ec2679da552d609bede340bb000d5e8003e8848`
- Postprocessed candidate SHA-256: `2cd7abbf3c1a727d956076ecf61094baf78c907c98e3690ee7a4330ac1d0f5e0`

### holdout_population_futibatinib: Population subgroup qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `9033cb5c86a3e4f4a876fb72ac4b7888aef0edc810f5cffb6764516eddf2621f`
- Postprocessed candidate SHA-256: `59ef058ebd99a6d4a0b76e84480176d160805259634f306ee9103dee02abd545`
