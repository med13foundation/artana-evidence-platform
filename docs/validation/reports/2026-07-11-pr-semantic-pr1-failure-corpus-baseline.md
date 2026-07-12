# Evidence Selection Semantic Diagnostic Baseline

- Benchmark: `2026-07-11-agent-first-semantic-relevance-baseline`
- Fixture provenance: **AI-adjudicated diagnostic**
- Production readiness claim: **NO**
- Baseline commit: `9f95b2277b0fcb30cd8eb06116af484c841f8319`
- Baseline model: `openai:gpt-5.4-mini`
- Fixture SHA-256: `a77e9db72d823c9bff8974afe6b2eaa74e423fb1de37ececa519bfa59b146a69`
- Prediction artifact SHA-256: `93844ba87ca9985da90b635de831cd0c5fc86c801cd63544bf9a5835de7f1b2f`

Expected labels are AI-adjudicated diagnostics, and predictions are manually transcribed from live shadow results. This is not independent human-expert evidence.

## Case Results

| Case | Role | Records | TP | FP | FN | TN | Precision | Expected + | End-to-end recall | Abstain | Invalid |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EGFR T790M primary evidence | primary | 8 | 1 | 5 | 2 | 0 | 0.1667 | 3 | 0.3333 | 0 | 0 |
| BRCA1 risk and penetrance | primary | 15 | 4 | 8 | 2 | 1 | 0.3333 | 6 | 0.6667 | 0 | 0 |
| CFTR F508del ETI response | primary | 7 | 0 | 3 | 4 | 0 | 0.0000 | 4 | 0.0000 | 0 | 0 |
| EGFR exclusion-token canary | canary | 3 | 0 | 0 | 3 | 0 | 0.0000 | 3 | 0.0000 | 0 | 0 |

## Source Artifacts

| Case | Role | Source run | Sanitized snapshot | Snapshot SHA-256 | Upstream SHA-256 |
| --- | --- | --- | --- | --- | --- |
| egfr_t790m_primary_evidence | primary | `ed628a98-3eb0-4a98-8beb-0b94614c2641` | `scripts/validation/evidence_selection/fixtures/source_artifacts/egfr_t790m_primary_evidence.json` | `eb757ece0f13815d41e9dc0d0122de0293971f0309d423d1a23d3f14c26b4abe` | `213fa9ef8a2c46379d665391ea9064259522d64fd2a57717dc28c407296129b3` |
| brca1_risk_penetrance | primary | `a8361ae7-7bb3-4122-85e7-37b207f11d04` | `scripts/validation/evidence_selection/fixtures/source_artifacts/brca1_risk_penetrance.json` | `7254d4cd0f74fb92e67d1caf1f545c2ff6bf471774047212ab1de344808baeb7` | `8f0dcdb076ebb0985be4177908d110017876463c170a2d26aed5e82e3612ffd9` |
| cftr_f508del_eti_response | primary | `ea0ae3b8-df5e-4875-81b7-83a9cfe77328` | `scripts/validation/evidence_selection/fixtures/source_artifacts/cftr_f508del_eti_response.json` | `b8fdf86290b33f4d7b9ae29cada157952f43d6eb0d1ec6527d84ca82c3f33477` | `0b6901128ee361c6e67ec5e5631cef6e537a8ae41d818d3979e60a784ef128b9` |
| egfr_exclusion_token_canary | canary | `d2cb282f-5b38-4f43-a0b0-aa20cae266d2` | `scripts/validation/evidence_selection/fixtures/source_artifacts/egfr_exclusion_token_canary.json` | `a935301454764c1c54b8ccb2cb857ffd73d24d6f206f6ef5fb914ca57d354d32` | `e071c01c86179eab249e8569eaf40ae22a095932b642516be8e1b018ccf0de43` |

## Aggregate Results

### Primary-only micro aggregate (30 records)

- Precision: `0.2381`
- End-to-end recall: `0.3846`
- Decision accuracy: `0.2000`
- Decision coverage: `1.0000`
- Abstention rate: `0.0000`
- Invalid-agent rate: `0.0000`

### Primary-only macro aggregate (unweighted mean across 3 cases)

- Precision: `0.1667`
- End-to-end recall: `0.3333`
- Decision accuracy: `0.1528`
- Decision coverage: `1.0000`
- Abstention rate: `0.0000`
- Invalid-agent rate: `0.0000`

Canary cases are shown above but excluded from both aggregates. Precision is reported as 0 when a case has no predicted selections.

## Interpretation

The baseline is intentionally RED. PR 1 freezes the failure and measurement contract; it does not change production selection behavior.
