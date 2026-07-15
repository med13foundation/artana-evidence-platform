# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-holdout-v2-luna-v11-01`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11`
- Fixture SHA-256: `22fbdf50333811d52e26296e9f1ddd561bfe0f29b0ed7d3771017199552ab956`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `20`
- matched_frame_count: `11`
- strict_completion_rate: `0.8947368421052632`
- explicit_polarity_concordance_rate: `0.45`
- epistemic_status_concordance_rate: `0.45`
- required_qualifier_completeness_rate: `0.46153846153846156`
- qualifier_concordance_rate: `0.4`
- frame_precision: `0.6111111111111112`
- unmatched_output_count: `7`
- unsupported_positive_output_count: `5`
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
- Model-boundary output SHA-256: `cd0513e851151e8fcd93fad06df16b903f326dd824110c855de1f3cf315f7341`
- Postprocessed candidate SHA-256: `0549fb43392b9086c77a39793022e5ad5616146fbfff1810315316425f2e78a3`

### holdout_explicit_negative_tmb: Explicit biomarker contradiction

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `b330ce6c71e840b706882d658205b0c95f1afbf0e5b2961f4c6fe7782182bce5`
- Postprocessed candidate SHA-256: `ad22f60123ff862f8a49e96d10c6ebc6c585e762ac8c120dfec5c47bdf13febe`

### holdout_null_margin: Null result beyond a prespecified margin

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `4e9b95ff74c137488e2e4210585b9c48c9acafcfb9e4bbb129b6af4433571ccd`
- Postprocessed candidate SHA-256: `2998c65ffa01470c2f232d4bb14ff95f484a256c6c5ac57521ec448a2c13e95d`

### holdout_provisional_zanubrutinib: Provisional treatment signal

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `0`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `21253cb31e65521aead3b4494c59f5f9a8a332583a5c8eab4dbdfbaa65cfacb8`
- Postprocessed candidate SHA-256: `e9b4821d8d7fe53cea89d92452244d99d102db448e534a371afd1887e3ecbf2a`

### holdout_uncertain_talazoparib: Uncertain treatment association

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `43951ceffbbc6eb8a3eb3c10ae7b1b95eefd9a2215d2d7d65bae74f928c83dba`
- Postprocessed candidate SHA-256: `2f8edbb7ba76628f4a6f71767284b936873bdcc1f330a0f1e9e9ab3de14cdd2c`

### holdout_hypothesis_keap1: Mechanistic hypothesis

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `50ab4abe568c05db75cdc16f17b6edf98c657e688e5f843f07d1649efc925f3a`
- Postprocessed candidate SHA-256: `3c8052617b7706f32ad5c23bdf5ce0518f5bf01bc10615e31eb55ff26aada0c7`

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
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `4d57ece7151a2c03922d64c8b71d51152cf5f9c7e24731dda2bf7acd6dc3cfa1`
- Postprocessed candidate SHA-256: `208ca8600ef7b3677a15a0529a89278ee09a523fd9f28fe2a8e31e471784c37d`

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
- Model-boundary output SHA-256: `bf9acef07d40f560aaeaf5fa4fa293b2110d614c92f029124db0dfb276215ffa`
- Postprocessed candidate SHA-256: `cd86ce76b95fa353e030f5471198f6a3d169e3fde83264c86149e1b9a37b1e7b`

### holdout_setting_ibrutinib: Treatment setting qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `ba5b70659a7ae36503dd5c99538170306f313275cc6adf7d000bbe428b237c2f`
- Postprocessed candidate SHA-256: `d97c44ed38782ddde37b240d2c1f456450292f23f75d72b1b67873e775248c82`

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `fa46edb4071edbea62c733a66770b8efd725739bd699226f80f60da6502eacd3`
- Postprocessed candidate SHA-256: `c6a08fd483a417618dd34570dd51b4ae2d3376bdb2b93308e35caffb22bc8a68`

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
- Model-boundary output SHA-256: `7d728355fc33d53bf9da3ec47b8aea269a7418560c417935f7166b156eee54eb`
- Postprocessed candidate SHA-256: `6596543694f8ce249258d14f6b63a2fb1957a1744530a25ba5371f9c6373301b`

### holdout_extra_output_capivasertib: Methods and funding output trap

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `c638cff734601527d2c0b00662e0b8edd01e363902df18edfbc573bfecf615d8`
- Postprocessed candidate SHA-256: `0ab1b376bf7cd0bfeceba855f5cb13a7923b124b520ed982a9ce9f96bececd5b`

### holdout_unresolved_population: Explicitly missing subgroup

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `78db676127a1b2d23891a7bfc78428f9617e50c3fdaf12d4660f55492a61dc99`
- Postprocessed candidate SHA-256: `9e4873e9ea45ede2c302b1b96525414d6d014bfa1b216e17a0a19eb421a8088c`

### holdout_source_measurement_repoterctinib: Literal source measurement

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Model-boundary output SHA-256: `c2a8bc4556367fe26b9649a126929ff79e745b025b405b7c79033d793b0772b7`
- Postprocessed candidate SHA-256: `712e297673e2e66d3fa694ab130a8ebcdac84c6eb18d3d625c9eef3038f37680`

### holdout_positive_sotorasib: Positive asserted relation

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `51ace1588eb32d43c63cd7108b26fbe848a77e3bcef7d85e4010826cd2ca67b5`
- Postprocessed candidate SHA-256: `3ccf81f6f1b8f8abf0d834c7a5b8c1d24bda34a55e0cd37064ca2e7b3b7bbc17`

### holdout_population_futibatinib: Population subgroup qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Model-boundary output SHA-256: `30f6da01efb58360fa16c22c4e105d3568e5d40127cf694230e81ade289d8f9e`
- Postprocessed candidate SHA-256: `38c7a7cf592b7f2ffd02c7c76c9a170e718f1d4d07dcdc788a6660db7f8b17e0`
