# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_comparison`
- Run IDs: `tg03-holdout-v2-luna-v11-01, tg03-holdout-v2-luna-v11-02, tg03-holdout-v2-luna-v11-03`
- Model IDs: `openai:gpt-5.6-luna, openai:gpt-5.6-luna, openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11, document_extraction.llm_extraction.v11, document_extraction.llm_extraction.v11`
- Fixture SHA-256: `22fbdf50333811d52e26296e9f1ddd561bfe0f29b0ed7d3771017199552ab956`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `60`
- matched_frame_count: `37`
- strict_completion_rate: `1.0`
- explicit_polarity_concordance_rate: `0.55`
- epistemic_status_concordance_rate: `0.55`
- required_qualifier_completeness_rate: `0.5641025641025641`
- qualifier_concordance_rate: `0.36666666666666664`
- frame_precision: `0.6727272727272727`
- unmatched_output_count: `18`
- unsupported_positive_output_count: `12`
- unsafe_assertive_upgrade_count: `0`
- positive_on_negative_or_null_count: `0`
- agent_authored_quality_score_count: `0`
- source_measurement_without_span_count: `0`
- exact_semantic_frame_stability_rate: `0.2`
- canonical_semantic_frame_stability_rate: `0.2`

## Gates

- polarity: **false** (explicit polarity concordance is 100% across all runs)
- epistemic_status: **false** (explicit epistemic-status concordance is 100% across all runs)
- qualifier_presence: **false** (required qualifier presence is 100% across all runs)
- qualifier_concordance: **false** (all qualifier categories are gold-concordant across all runs)
- unmatched_outputs: **false** (unmatched output frames are zero across all runs)
- unsupported_positive_outputs: **false** (unsupported positive output frames are zero across all runs)
- unsafe_assertive_upgrades: **true** (non-assertive gold claims are never upgraded to ASSERTED)
- positive_on_negative_or_null: **true** (positive output on negative/null cases is zero)
- agent_quality_scores: **true** (agent-authored quality scores are absent)
- no_fallback: **true** (strict reports contain no fallback output)
- measurement_spans: **true** (source measurements all have exact spans)
- stability: **false** (canonical semantic-frame stability is at least 95%)
- strict_completion: **true** (all three strict live runs completed)

## Cases

### holdout_variant_alk_g1202r: ALK resistance variant and population

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=0, polarity=0, qualifiers=0

### holdout_explicit_negative_tmb: Explicit biomarker contradiction

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=0, qualifiers=0

### holdout_null_margin: Null result beyond a prespecified margin

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `3`
- Qualifier-concordant: `2`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=0

### holdout_provisional_zanubrutinib: Provisional treatment signal

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `2`
- Qualifier-concordant: `2`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=0, qualifiers=1
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=1

### holdout_uncertain_talazoparib: Uncertain treatment association

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=1

### holdout_hypothesis_keap1: Mechanistic hypothesis

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=0, polarity=0, qualifiers=0

### holdout_intervention_ctdna: Intervention outside the endpoints

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=0, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=0, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=0

### holdout_comparator_amivantamab: Active comparator

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `2`
- Polarity correct: `2`
- Qualifier-concordant: `0`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=0

### holdout_outcome_enfortumab: Measured clinical endpoint

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=0, polarity=0, qualifiers=0

### holdout_study_adagrasib: Study design qualifier

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `3`
- Qualifier-concordant: `0`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=1, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=0

### holdout_setting_ibrutinib: Treatment setting qualifier

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=1

### holdout_timeframe_milvexian: Timeframe and population qualifier

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=0, polarity=0, qualifiers=0

### holdout_threshold_cabozantinib: Numeric threshold qualifier

- Strict completed: `True`
- Output frames: `0`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=0, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=0, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=0, matched=0, polarity=0, qualifiers=0

### holdout_multi_clause_ret_ntrk: Clause-local sibling claims

- Strict completed: `True`
- Output frames: `6`
- Matched frames: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=2, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=2, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=2, matched=1, polarity=1, qualifiers=1

### holdout_extra_output_capivasertib: Methods and funding output trap

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `3`
- Qualifier-concordant: `3`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=1

### holdout_unresolved_population: Explicitly missing subgroup

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `3`
- Qualifier-concordant: `2`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=0

### holdout_source_measurement_repoterctinib: Literal source measurement

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `3`
- Qualifier-concordant: `1`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=0

### holdout_positive_sotorasib: Positive asserted relation

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `3`
- Polarity correct: `3`
- Qualifier-concordant: `2`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=1, polarity=1, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=1, polarity=1, qualifiers=1
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=1, polarity=1, qualifiers=1

### holdout_population_futibatinib: Population subgroup qualifier

- Strict completed: `True`
- Output frames: `3`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- `tg03-holdout-v2-luna-v11-01`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-02`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
- `tg03-holdout-v2-luna-v11-03`: completed=True, output=1, matched=0, polarity=0, qualifiers=0
