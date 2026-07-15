# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-v2-luna-v11-03`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11`
- Fixture SHA-256: `22fbdf50333811d52e26296e9f1ddd561bfe0f29b0ed7d3771017199552ab956`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `20`
- matched_frame_count: `13`
- strict_completion_rate: `0.9473684210526315`
- explicit_polarity_concordance_rate: `0.6`
- epistemic_status_concordance_rate: `0.6`
- required_qualifier_completeness_rate: `0.6153846153846154`
- qualifier_concordance_rate: `0.3`
- frame_precision: `0.6842105263157895`
- unmatched_output_count: `6`
- unsupported_positive_output_count: `4`
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
- Model-boundary output SHA-256: `7bd10a128de7fc3578c6f9caa9340c3e0bb4c6584cdd08961dd2bfd73dcd4eb1`
- Postprocessed candidate SHA-256: `8b895923ca53f5f46100cf40b103669c86ce508b23cbc6506491b63ba2a99054`

### holdout_explicit_negative_tmb: Explicit biomarker contradiction

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `7ab26cab4dc24c54e3e5463eb530f83f985378a3815453c702a97e273e39b57f`
- Postprocessed candidate SHA-256: `14b70507deb68318c6cbeff773fb27d24280310f566eee6007ea6574b36dc839`

### holdout_null_margin: Null result beyond a prespecified margin

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `f1625a492c0632ebb2c82376a76adae724117372efd231ad9ddaf4327ca7a2b9`
- Postprocessed candidate SHA-256: `125346ea0fd9b15e125e0612bb3e83848c7719e6769eb40964a6b8a942afa5fb`

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
- Model-boundary output SHA-256: `e0f6af35d752ee2cf059b6daa1faa4c5055f7ca46b145e89320cafd176114c27`
- Postprocessed candidate SHA-256: `ac229de28967509dc0455e5193fdb1434387785a2248fd3b4d9fa460430127bc`

### holdout_hypothesis_keap1: Mechanistic hypothesis

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `68584aad3a7d5ce012c067f9e951688a26de5fe089db3975c1a6dde32ab53e27`
- Postprocessed candidate SHA-256: `c75b5b96f62e9f84c4ac3cbc61fa5ebdaa45a2f1993474b98552df622aa055ea`

### holdout_intervention_ctdna: Intervention outside the endpoints

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `7880a42fbf910b465b18962adf87bb5bbeb18b6ce6e0cce1efae602ff0813517`
- Postprocessed candidate SHA-256: `29c4258cfef4d1508b1dbcfbdf10bda35bcad3980b13863c7c94e91612539357`

### holdout_comparator_amivantamab: Active comparator

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `4b413f48d0c5878a2ed4f459608f8760efc62956a2eebfa83a69d50386c5bb25`
- Postprocessed candidate SHA-256: `6b9d5dce4010cd36d3c89becb5ba53fec02f746d499af42ffc282ccd391a7cfb`

### holdout_outcome_enfortumab: Measured clinical endpoint

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `67e47373293f893647e5a3ffd00881e1356cd9f221077c054f1705d0d7699b6c`
- Postprocessed candidate SHA-256: `f823de84c74580c83375487abcb7da055e4812469a54fc0f529f424fd2c7cbfa`

### holdout_study_adagrasib: Study design qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `6773579965ae7920ba835b60f52c5d6f0e4098dcb369042c3ca8d9ce8e718d1b`
- Postprocessed candidate SHA-256: `85ad11917bf641871cb6933e466146709dd6663f1b9c7dd4b35da82478a48ab7`

### holdout_setting_ibrutinib: Treatment setting qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `bd372718487542c0e582ffc0794150ad0c39fb2795eb779e45462bc2c148b120`
- Postprocessed candidate SHA-256: `e6b38fa10a6affc6ada8148875447dd56db91ae3deb3403e3b4598bd5b80c48b`

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `2390d8b15f10bedca12f057d2be1011fc3bd25a3f98d477f5deeaf25f1c57040`
- Postprocessed candidate SHA-256: `39821e1868829f74d2234a1dcc9f63cfc8ae8444e0759d5c8eb3d94bb46e21e8`

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
- Model-boundary output SHA-256: `3467a3415e1ff189ede64fa74197da220560045cf0ef95d7599d334a7d1bb633`
- Postprocessed candidate SHA-256: `389a0db1fcc265241081642bffba6c9663b9804457a8e107277105b50186d7cc`

### holdout_extra_output_capivasertib: Methods and funding output trap

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `52b6278cd5a996afa08125658a8aced2f81c90b65dc78d05813c35dfcbe4f729`
- Postprocessed candidate SHA-256: `bbac4a89cca5792657e05ac7a6e4843dce5608d08be6677f8fbe80d983e7a543`

### holdout_unresolved_population: Explicitly missing subgroup

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `5615803f0599da9207b8c6b0b690126b75ee56ded09f37170676f5299285931d`
- Postprocessed candidate SHA-256: `147b7d5afe1ea409f3f2a95a8383b08330b7e12683de5ec9f331e09ed29767f5`

### holdout_source_measurement_repoterctinib: Literal source measurement

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `37739ed5d1a0ff048001f564cee61ca58331bd5052ff02b52576ba667ef0bdbe`
- Postprocessed candidate SHA-256: `c275c834c23ac22ab5a4068acad72e644a2022bcbe347c0e91078d69cbf38cbb`

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
- Model-boundary output SHA-256: `597ff8199ceaed9695d3935bb3a5d93684199480724672b4d004c56c07910c27`
- Postprocessed candidate SHA-256: `759972598de1799eadce8917b84f7ea49a3a99a21d24976eecb539c81ac4db73`
