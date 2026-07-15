# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-luna-v10-01`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v10`
- Fixture SHA-256: `607dbf3729038bf1bbb767955cdf222f9b88fece7e02cd7eeaf61cc6eaee6de6`
- Gate passed: **false**

## Deterministic Metrics

- expected_frame_count: `15`
- matched_frame_count: `13`
- explicit_polarity_concordance_rate: `0.8666666666666667`
- required_qualifier_completeness_rate: `0.8`
- positive_on_negative_or_null_count: `0`
- agent_authored_quality_score_count: `0`
- source_measurement_without_span_count: `0`

## Gates

- strict_completion: **false** (all strict live cases completed)
- polarity: **false** (explicit polarity concordance is 100%)
- qualifier_presence: **false** (required qualifier presence is 100%)
- positive_on_negative_or_null: **true** (positive output on negative/null cases is zero)
- agent_quality_scores: **true** (agent-authored quality scores are absent)
- no_fallback: **true** (strict reports contain no fallback output)
- measurement_spans: **true** (source measurements all have exact spans)
- stability: **false** (not_evaluated)

## Cases

### variant_egfr_t790m: EGFR T790M variant state

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `1a645855ede53ac6ac4e36d54805fdb9435ac69fdc53c8f16e0f0eb077f18a52`

### variant_brca1_zygosity: BRCA1 loss and zygosity

- Strict completed: `False`
- Output frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Output SHA-256: `096ac3df03946e078dbe269a92a8543208cd3a306619c8121a6cf651f2586842`

### disease_subtype: Disease subtype preservation

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `f8ec933ad0e6a35695fb8d7d34544f5b20465c3c65fbbf8526388ff7ac9baba2`

### population: Population qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `546e7d917f6bfbdb9b99a96aa7d3f827a50f543d471605b6da67fbd0a97989ab`

### treatment_line: Treatment line qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `6623139a6a3244f9326bd8183058b158cd18888da2b787f9bc2e825ceeab6df3`

### assay_cutoff: Assay cutoff and source measurement

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `c0a58525c202ccbbc883c6cab617d8d31037e891cd3ee7d063a29dcf5f4ed328`

### comparator: Comparator preservation

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `6018f2bae69ecccfbe9c38eb1d881f6bd3fc600cf351a9f7675c70eff652e26c`

### endpoint: Endpoint qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `4f65705101ef7daa5f6235c1792e9a6c134c0a0fa7e7f73a5405184c92f6313b`

### timeframe: Timeframe qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `875e314c2c1c63a05deea59e3b7db686fd18e4d04b50abb8bb78d60bf1f074a5`

### explicit_negation: Explicit negative association

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `00f94dc75af0587f21d1448456b570cabb3ef44f5c91ae0f536957aaad297920`

### failed_threshold_null: Failed threshold and null result

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `da25047eb0e4ade1566baf01643296ab0ddf4f9083551cb4ac85f2993042415f`

### provisional_claim: Provisional claim

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `0e8eda00c55e566ad555ee40f4d300e645966d1f0853577cbd984cffd6e03750`

### novel_hypothesis: Novel hypothesis

- Strict completed: `False`
- Output frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Output SHA-256: `096ac3df03946e078dbe269a92a8543208cd3a306619c8121a6cf651f2586842`

### multi_clause_binding: Multi-clause qualifier binding

- Strict completed: `True`
- Output frames: `2`
- Polarity correct: `2`
- Qualifier-concordant: `2`
- Output SHA-256: `ce395739e8ca69750e4c6803749386ccba0cb4663fc25400f8d7d6bc4398e4fc`
