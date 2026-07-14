# Semantic Model Comparison Protocol

- Evaluated commit: `71460f596b7efa19cf74a5e1d76710a7a75a3ab8`
- Trusted mainline ref: `origin/main`
- Trusted mainline commit: `d23b1dea194d7fc6f116de84738fdf720c536a71`
- Required integrated mainline commit: `d23b1dea194d7fc6f116de84738fdf720c536a71`
- Current model: `openai:gpt-5.4-mini`
- Candidate model: `openai:gpt-5.6-luna`
- Runs per model: `3`
- Fixture SHA-256: `a77e9db72d823c9bff8974afe6b2eaa74e423fb1de37ececa519bfa59b146a69`
- Baseline SHA-256: `e9867148d9a5ff2eb874ee597b7982147ce76c7684f284cab4c10f0a8f8ba295`
- Repository source files: `5`
- Source lock SHA-256: `c1c6a65c05570c44e6a4cd8a3abf27b36e7d28223e29c4a2f6036596635282f6`
- Evidence provenance: **AI-adjudicated diagnostic**
- Production readiness claim: **NO**

## Frozen Repository Sources

- `baseline_predictions`: `scripts/validation/evidence_selection/fixtures/semantic_relevance_live_baseline_predictions_v1.json` (`93844ba87ca9985da90b635de831cd0c5fc86c801cd63544bf9a5835de7f1b2f`)
- `sanitized_source_snapshot`: `scripts/validation/evidence_selection/fixtures/source_artifacts/brca1_risk_penetrance.json` (`7254d4cd0f74fb92e67d1caf1f545c2ff6bf471774047212ab1de344808baeb7`)
- `sanitized_source_snapshot`: `scripts/validation/evidence_selection/fixtures/source_artifacts/cftr_f508del_eti_response.json` (`b8fdf86290b33f4d7b9ae29cada157952f43d6eb0d1ec6527d84ca82c3f33477`)
- `sanitized_source_snapshot`: `scripts/validation/evidence_selection/fixtures/source_artifacts/egfr_exclusion_token_canary.json` (`a935301454764c1c54b8ccb2cb857ffd73d24d6f206f6ef5fb914ca57d354d32`)
- `sanitized_source_snapshot`: `scripts/validation/evidence_selection/fixtures/source_artifacts/egfr_t790m_primary_evidence.json` (`eb757ece0f13815d41e9dc0d0122de0293971f0309d423d1a23d3f14c26b4abe`)

## Deterministic Adoption Policy

- Policy: `evidence_selection.semantic_model_adoption@1.2.0`
- Minimum worst-run precision: `0.8000`
- Minimum worst-run recall: `0.8000`
- Minimum per-case precision: `0.7000`
- Minimum per-case recall: `0.7000`
- Minimum worst-run coverage: `0.8000`
- Minimum per-case coverage: `0.7000`
- Variance-only model adoption: **FORBIDDEN**
- Record-level instability allowed: `0`
- Agent-authored confidence or numeric model preference: **FORBIDDEN**
- Absolute maximum candidate resource ratio: `10.00`
