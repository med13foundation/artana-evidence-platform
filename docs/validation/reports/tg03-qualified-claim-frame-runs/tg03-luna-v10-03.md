# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-luna-v10-03`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v10`
- Fixture SHA-256: `607dbf3729038bf1bbb767955cdf222f9b88fece7e02cd7eeaf61cc6eaee6de6`
- Gate passed: **false**

## Deterministic Metrics

- expected_frame_count: `15`
- matched_frame_count: `12`
- explicit_polarity_concordance_rate: `0.8`
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
- Output SHA-256: `6268276ed7efee039f09cd0274fcbc1cb5eeb61d0523ba71d9def7a83383b1f8`

### variant_brca1_zygosity: BRCA1 loss and zygosity

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Output SHA-256: `74d338d9ae31dfb9b22bb710b2197086788a51c553e628e5aa2580bc53e8c941`

### disease_subtype: Disease subtype preservation

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `fcbe76c1d6e8c1bf38f236fec87bac4b71049138fccb796d0c5bd564a11db6c5`

### population: Population qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `ed1dac9e3ffcc51893efa0a798fd812cfe77622d00caa1aca58b623606620e27`

### treatment_line: Treatment line qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `48e9dcd32897e167e2179f5b8c1d280515e6a25fb7cfd6de4be7627b1c7cd390`

### assay_cutoff: Assay cutoff and source measurement

- Strict completed: `False`
- Output frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Output SHA-256: `096ac3df03946e078dbe269a92a8543208cd3a306619c8121a6cf651f2586842`

### comparator: Comparator preservation

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `4eea7bbd8e892f5816b010e76223fcaf2774db76fd48864259cc5aa48091bf88`

### endpoint: Endpoint qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `eb266a7320e317bc401c67f219f8369ebb6fcc2c68900b1f8d04550258af5cf6`

### timeframe: Timeframe qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `534fe6e8018f9a201a1d6ebcc3731e91c4196da09fd84afea53eb9d4589b9206`

### explicit_negation: Explicit negative association

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `c8ee8a26243bd2cb63645b28f0a845ad9eb7be111adb12669bfc0d1f66db3f29`

### failed_threshold_null: Failed threshold and null result

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `326bb0d3cf1b4a918d5eefd781fda956a6778e274273a62f17d123e56ccfa22a`

### provisional_claim: Provisional claim

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `e70ec4fa181773067b073525f7dba32abd2c3ae5b09da3e647d1a601b8638833`

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
- Output SHA-256: `217072418f87a6cd96ee1a0837e2c5c29a8072d39fdf257954d6f1933aab84be`
