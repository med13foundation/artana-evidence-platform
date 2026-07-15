# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-luna-v10-02`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v10`
- Fixture SHA-256: `607dbf3729038bf1bbb767955cdf222f9b88fece7e02cd7eeaf61cc6eaee6de6`
- Gate passed: **false**

## Deterministic Metrics

- expected_frame_count: `15`
- matched_frame_count: `12`
- explicit_polarity_concordance_rate: `0.8`
- required_qualifier_completeness_rate: `0.7`
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
- Output SHA-256: `76f5e50555253f1436add6ed14518732628c1621495e759c852726e36fb6484f`

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
- Output SHA-256: `c313c35af3d07fd04fa586d7df5877a5db9c767ff55a89ddc166cec253846c6d`

### population: Population qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `b0f6f89a08c7951e70c0fbf1cc13371e0038a7588113babec42074a96fa55bff`

### treatment_line: Treatment line qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `adf3b77989460321b6671acd096039af0afbfd664f51df8884c3832b6c55b5ab`

### assay_cutoff: Assay cutoff and source measurement

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `3b20ef0d2886eefd9f9cbf5218a31c4505624d4be5a9621a50d4c02f158a175f`

### comparator: Comparator preservation

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `e6814464b87043e8cfaa59e22368b96de9e00084075096d00b9b79965b6e1ebb`

### endpoint: Endpoint qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `21f3d075bacb6ea1dbfbe7a14f68dbf8ed397d526b75f256aba08b9b66004ef2`

### timeframe: Timeframe qualifier

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `ea8f9aac4b6421f92632e1dbba2bce98acf347ac3e5bc4a64c43225707785442`

### explicit_negation: Explicit negative association

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `5e1fcb4e953019f5fc1326b569e2956ac9425d8b14a49314cdfcca497a648fd6`

### failed_threshold_null: Failed threshold and null result

- Strict completed: `False`
- Output frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Output SHA-256: `096ac3df03946e078dbe269a92a8543208cd3a306619c8121a6cf651f2586842`

### provisional_claim: Provisional claim

- Strict completed: `True`
- Output frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `e32c36b784eea504cb4faaae1b73da1b833a86c700cfe2fbbc8151195f7f1b56`

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
- Output SHA-256: `74b9d70958af5b9404db27faac088e3b2909f05315dea1a534d754f3656a9a05`
