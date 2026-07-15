# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-luna-v11-final-03`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11`
- Fixture SHA-256: `c2ad0198a24ad94aff2401fbcea41a284e731b86375bd1aaba0b146b17dbba1e`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `15`
- matched_frame_count: `15`
- strict_completion_rate: `1.0`
- explicit_polarity_concordance_rate: `1.0`
- epistemic_status_concordance_rate: `1.0`
- required_qualifier_completeness_rate: `1.0`
- qualifier_concordance_rate: `0.9333333333333333`
- positive_on_negative_or_null_count: `0`
- agent_authored_quality_score_count: `0`
- source_measurement_without_span_count: `0`

## Gates

- strict_completion: **true** (all strict live cases completed)
- polarity: **true** (explicit polarity concordance is 100%)
- qualifier_presence: **true** (required qualifier presence is 100%)
- positive_on_negative_or_null: **true** (positive output on negative/null cases is zero)
- agent_quality_scores: **true** (agent-authored quality scores are absent)
- no_fallback: **true** (strict reports contain no fallback output)
- measurement_spans: **true** (source measurements all have exact spans)
- stability: **false** (not_evaluated)

## Cases

### variant_egfr_t790m: EGFR T790M variant state

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `752bcba598801d8347e14c42c5f0e61d3340fab5233fa339628235a7a691a8c4`

### variant_brca1_zygosity: BRCA1 loss and zygosity

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `de855aeca92aec8cd29732c5807836a46ea73e8a5c428b52154f138d033b2396`

### disease_subtype: Disease subtype preservation

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `40d59e3e505e965ef8508c36d3353e9194228e8b89f86646780e47c588768f2b`

### population: Population qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `d58242339e38b126122dd7814f01d16702e078ec3d2c013f4ce93796ae47d6ea`

### treatment_line: Treatment line qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `8dfe3a87cf21a9991ee976a24814bd2e9fa0e7a4b309a4a0d153bfbf2d408310`

### assay_cutoff: Assay cutoff and source measurement

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `53aa4e379c2ce64ef0762a2c1d234705f0a6e19ebe30c5c699808de1e85d1838`

### comparator: Comparator preservation

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `fc6683fbcc9b2c02a529ab5d54d39b052306c5e60ae781ddc7e4e06f8ebfa31a`

### endpoint: Endpoint qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `91bffeb384b7c9e8789772e5396565b4f36cff8d7ee74330fea1471fbcf477aa`

### timeframe: Timeframe qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `ad5fd977d389afe5255d74dfa23de9f6c2de01fc7dd777ca1b1510f9e289330e`

### explicit_negation: Explicit negative association

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `2ad74ca50f7134a796287de2b36f331dbdf170de416b7d652aeaf9bdca812807`

### failed_threshold_null: Failed threshold and null result

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `b5f42273ac084f2e13cea79b07ffcd78b87204af6e0c455f895d8ac2e6c0748b`

### provisional_claim: Provisional claim

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `43903520f4f4d261cfb419ab2ca07c35a836b1561e52904ddf8c8d282e405f6e`

### novel_hypothesis: Novel hypothesis

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `2dbc4c62ce135c17ba00fe4326b144b2f20b31729a8880ccfa12f1fbb91a8af9`

### multi_clause_binding: Multi-clause qualifier binding

- Strict completed: `True`
- Output frames: `2`
- Matched frames: `2`
- Polarity correct: `2`
- Qualifier-concordant: `2`
- Output SHA-256: `aa9ac5241c97bea3f3f57c6c39be829cec5147766811525bbc6ef120cd6cb7af`
