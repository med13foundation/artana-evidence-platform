# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-luna-v11-final-02`
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
- qualifier_concordance_rate: `0.8666666666666667`
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
- Output SHA-256: `b4346aa634d9e0290d4642135dcd880e6b040da508ac553484cb72f40abe85f9`

### disease_subtype: Disease subtype preservation

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `c96fe4ddd500680073a69ed94259c5828738046cb1ddc4fc4dab8ac3741c18e9`

### population: Population qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `49e989576a2a6ec04b126879a09a74697a54794175f8d5ed902ef123a3a58787`

### treatment_line: Treatment line qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `19c788b54116b829ff2510b90008e084b9ebf1cb51f15cc34afc860e24676666`

### assay_cutoff: Assay cutoff and source measurement

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `b29d0a959a0f96092ab53ad02e8dfd028ca0c28af52f8c1bca712672bf8128ba`

### comparator: Comparator preservation

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `36d42aa0381319310d2aed56e642d236dbd093aa6bed33f43cf29d30b9a33720`

### endpoint: Endpoint qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `e8dada24b773ea08c32f471de045d9a7b58745299a1d16efe360312a973b4186`

### timeframe: Timeframe qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `29d0c383d63b2dd6efe590059a0ab0e8a94c7a29a47161a25c686d46fce9dae4`

### explicit_negation: Explicit negative association

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `43878bfb63f5c12ea90d0584e3c00539dfb684e46aa1fc440aca779113cf73ff`

### failed_threshold_null: Failed threshold and null result

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `ac0c3ecc4b6ef032fbfd9e5ce6ba9292f98004a14be9a38977b007873defb5a3`

### provisional_claim: Provisional claim

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `a2b347ab35c59623e8c23dfd77837f29e2f4e9f81e7e11c0e1c5e597f9651b7f`

### novel_hypothesis: Novel hypothesis

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `76388886e4555dbf0a92880520da76f22984b49d8ac30fc4f7f5de698f266a92`

### multi_clause_binding: Multi-clause qualifier binding

- Strict completed: `True`
- Output frames: `2`
- Matched frames: `2`
- Polarity correct: `2`
- Qualifier-concordant: `2`
- Output SHA-256: `09ff38e83d8d82812f1ae74f91da85e276b4af5edf98b89c1b1200e3177ac8bd`
