# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-luna-v11-01`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11`
- Fixture SHA-256: `8d1dcf01c51d6aa3e1cb02c54d994a7f9e96c5dc63471129f4ec34baa824ee96`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `20`
- matched_frame_count: `12`
- strict_completion_rate: `0.9473684210526315`
- explicit_polarity_concordance_rate: `0.55`
- epistemic_status_concordance_rate: `0.55`
- required_qualifier_completeness_rate: `0.5384615384615384`
- qualifier_concordance_rate: `0.4`
- frame_precision: `0.6`
- unmatched_output_count: `8`
- unsupported_positive_output_count: `6`
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
- Model-boundary output SHA-256: `7f014c999dae586f95b6159f288b424b7425c10e94e3e08ae2e405d908106136`
- Postprocessed candidate SHA-256: `0a227384a89e5a89e1abf5861927d3097c7fece5f315359d8ae461c6fa152aef`

### holdout_explicit_negative_tmb: Explicit biomarker contradiction

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `ab040321bd0d7082bd76204c32348946c89863791d0a02d902768ffbf8e1bbd6`
- Postprocessed candidate SHA-256: `5d138b857f7e59d09aeb6d01661e440e1f6e3de2b09bbc373ecd698b1b5a7679`

### holdout_null_margin: Null result beyond a prespecified margin

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `7d0cd4d9370f0b5bf03313647976ef5c12be945494785e5b8f13b30b14733874`
- Postprocessed candidate SHA-256: `b9451508726bd5c46c53b308300a302a5abba74d28397da5f78303e5b73464a1`

### holdout_provisional_zanubrutinib: Provisional treatment signal

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `6262a4b292954f496955bd1045aa18b88477d2566bbf9023e25be94aa6ee356b`
- Postprocessed candidate SHA-256: `ae1ed2413e49e21075a14475e3e9a5b6fb0990b897dc669a3d3a773c4be0dbea`

### holdout_uncertain_talazoparib: Uncertain treatment association

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `dba3119bf20af18da6ffe2b3ab71b2c9827603eeccb0bfb6fd60acf35fd0d69b`
- Postprocessed candidate SHA-256: `e5bb257789d2c88a8247d1cb97341aab57b7d47b58ab3c8f8f3075339941dd79`

### holdout_hypothesis_keap1: Mechanistic hypothesis

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `6a8bdfce91faab4cbe62b3dd478f26226ef4c279bbf3cb5426cbbe3978ce3262`
- Postprocessed candidate SHA-256: `9d5a0dffdcc5502adf278763cbc57008fc5627138e9d37019d598e1bda3dccee`

### holdout_intervention_ctdna: Intervention outside the endpoints

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `30c4adf95360bd1afd4345a19ba20757846d72477451d54018edf77a797cb74e`
- Postprocessed candidate SHA-256: `ed2b1a6748d2504eed9c3d1dc16abc26f8271c50340b6c7e750601ed86a0d358`

### holdout_comparator_amivantamab: Active comparator

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `ec9c59a79eedc3c0a431a941d1984ba034cdf982f6aaf92c74647288253f8493`
- Postprocessed candidate SHA-256: `3ef8ca13ea47ab40ea34e0f261d52c0306b098098a52e284d457d9084db62e07`

### holdout_outcome_enfortumab: Measured clinical endpoint

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `d2d0e213858833d4da9c365facee1dbdbf95db9e2632bd6b9e39c565278221cb`
- Postprocessed candidate SHA-256: `d3957ace00a24bfbc01a77e70e25e1a286d870df18c1bcadb52f5a1a0488c3a5`

### holdout_study_adagrasib: Study design qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `d88833be0a215209cefc22cbe1d39bb8c197f56cd068b3d94b6e76ceb6970a14`
- Postprocessed candidate SHA-256: `c9b3c4d176b606f7e9ee1e12289c2eced1941862c6f703536149f70afa533c63`

### holdout_setting_ibrutinib: Treatment setting qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `dacf888808924839c01b7e6ee0e129c3e767d1520be13228638483968063889d`
- Postprocessed candidate SHA-256: `910fcd1fd6626d6ca8b23d66971ef5e1b7bbd3ed6e7f79086f98159610d6c361`

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Strict completed: `True`
- Output frames: `2`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `d0fdf88052de80b42fc4a5961f18d643c4f6273860e35ea9a78721b55c1887a1`
- Postprocessed candidate SHA-256: `d5c4ce928bc7bfdc796bdc4f1f9ddcc8faf585c80a0ea64caf213996ca504577`

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
- Model-boundary output SHA-256: `2f6c92029da22f0679c14da2733c0219f7d72d9b37112c9d8e5ebfc1d116f29e`
- Postprocessed candidate SHA-256: `bb58b4da2d461a2efcd5b7ae700ef238b8ec8bf59eed6f3b1e097bb8afb778c0`

### holdout_extra_output_capivasertib: Methods and funding output trap

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `b45dd0625619ef9fdd4c2ec95bbf99b1a9bf88203fa7f5ede38935633dfb2fb0`
- Postprocessed candidate SHA-256: `c0cbbb06628052bbe23cf928c8b59380e294cb3bce44e0db0b893e33bce8ebbf`

### holdout_unresolved_population: Explicitly missing subgroup

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `7c9f7f07b0d9567c4af8cfe179467f795754c24631030f30083452b066837981`
- Postprocessed candidate SHA-256: `ceafcbaa469f7ecef02417dc2d3edfb229f8a2f34777647a91e77b880872e2c4`

### holdout_source_measurement_repoterctinib: Literal source measurement

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `e87d3ad8bd3de892428392ad2f0350b51944ef1aa35d57d1e6e749b3583de5d4`
- Postprocessed candidate SHA-256: `aaf9312210c706686bf252403a6db3c93010e3553728887cfbc9922df106b524`

### holdout_positive_sotorasib: Positive asserted relation

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `65a65108903f42b02295b71ade238da701487de7675474f53f8e066e491aebdf`
- Postprocessed candidate SHA-256: `8d4bfa63f1a6612afb46b60f10e6bfd22138332cdd6bba7026aaa2025fbff403`

### holdout_population_futibatinib: Population subgroup qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `0c1ce4d5f845abbc63313c8ff894b88274474dbd4c16f1cfb5f1a49ccef28e2c`
- Postprocessed candidate SHA-256: `d0fe4549ff6e47ee26d1ba950799807f221f879885ffa7662cd59d8aa2b7e0c2`
