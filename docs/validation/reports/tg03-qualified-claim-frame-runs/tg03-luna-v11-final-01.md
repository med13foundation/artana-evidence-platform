# TG-03 ClaimFrame Feasibility Audit

- Report type: `claim_frame_feasibility_run`
- Run IDs: `tg03-luna-v11-final-01`
- Model IDs: `openai:gpt-5.6-luna`
- Prompt versions: `document_extraction.llm_extraction.v11`
- Fixture SHA-256: `c2ad0198a24ad94aff2401fbcea41a284e731b86375bd1aaba0b146b17dbba1e`
- Gate passed: **false**

## Decision

**TG-03 merge gate: FAIL. Trusted projection remains blocked.**

## Deterministic Metrics

- expected_frame_count: `15`
- matched_frame_count: `14`
- strict_completion_rate: `0.9285714285714286`
- explicit_polarity_concordance_rate: `0.9333333333333333`
- epistemic_status_concordance_rate: `0.9333333333333333`
- required_qualifier_completeness_rate: `0.9`
- qualifier_concordance_rate: `0.8666666666666667`
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
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `4aff543fa68287f7afc4ca4b343fdddb24887eba4d9467f1ebdf72e269d6a591`

### variant_brca1_zygosity: BRCA1 loss and zygosity

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `3fc3a6d0fcceb5f9a788a52e0fb994675190ae8112515f518e036dc9dec279b4`

### disease_subtype: Disease subtype preservation

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `abb8aacacf1d84b841137b4cdcd8d89454147d6ed35dda6cc35ac7b53b919a91`

### population: Population qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `0a467fd27a974a69251fd86ed683cc23951849e026c45219900bc60827a299c6`

### treatment_line: Treatment line qualifier

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `0da99db948c88573ba6dc702bb0906fde78f2fe064315155526f744afe0c203e`

### assay_cutoff: Assay cutoff and source measurement

- Strict completed: `False`
- Output frames: `0`
- Matched frames: `0`
- Polarity correct: `0`
- Qualifier-concordant: `0`
- Output SHA-256: `096ac3df03946e078dbe269a92a8543208cd3a306619c8121a6cf651f2586842`

### comparator: Comparator preservation

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `ad521196dc75f57d2daa7892b61801d14ed23f00d2be15c21a61c5ce23e934e4`

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
- Output SHA-256: `4acbffc9730dfb7fc069156c6a52c01500d5a2f2455b7d5c94fabf9508fe54d9`

### explicit_negation: Explicit negative association

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `dfccb4f9d132bf4af4021e3f1157fba194079247235d777e9674dd3b1348d0d4`

### failed_threshold_null: Failed threshold and null result

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `2b47b0a50842d8d811e3aa876a03f0f36b914931cba261fea088e46081d6205d`

### provisional_claim: Provisional claim

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `1`
- Output SHA-256: `52d245e0936b310d2524130fe45206c144c6dc2f07825c8765d4dfd04b8256b7`

### novel_hypothesis: Novel hypothesis

- Strict completed: `True`
- Output frames: `1`
- Matched frames: `1`
- Polarity correct: `1`
- Qualifier-concordant: `0`
- Output SHA-256: `cdff949ab6bc11caf79b7de3a11f7b696e150779a375863942f9142775d4fdc5`

### multi_clause_binding: Multi-clause qualifier binding

- Strict completed: `True`
- Output frames: `2`
- Matched frames: `2`
- Polarity correct: `2`
- Qualifier-concordant: `2`
- Output SHA-256: `672d9c63c418a49914f071c872977e2caf5d48cfe728f8feed77aa06d391f6f6`
