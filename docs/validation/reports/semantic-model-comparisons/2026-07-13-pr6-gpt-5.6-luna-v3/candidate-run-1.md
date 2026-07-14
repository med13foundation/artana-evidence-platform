# PR 2 Agent-First Semantic Selector Evaluation

- Evaluated commit: `71460f596b7efa19cf74a5e1d76710a7a75a3ab8`
- Model: `openai:gpt-5.6-luna`
- Baseline report SHA-256: `e9867148d9a5ff2eb874ee597b7982147ce76c7684f284cab4c10f0a8f8ba295`
- Fixture provenance: **AI-adjudicated diagnostic**
- Production readiness claim: **NO**
- Quality gate: **PASS**
- Canary gate: **PASS**
- Deterministic semantic fallbacks: `0`

## Improvement

| Metric | PR 1 baseline | PR 2 live agent | Required |
| --- | ---: | ---: | ---: |
| Precision | 0.2381 | 1.0000 | 0.8000 |
| End-to-end recall | 0.3846 | 1.0000 | 0.8000 |

## Case Results

| Case | Role | TP | FP | FN | TN | Precision | Recall | Abstain | Invalid |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EGFR T790M primary evidence | primary | 3 | 0 | 0 | 5 | 1.0000 | 1.0000 | 0 | 0 |
| BRCA1 risk and penetrance | primary | 6 | 0 | 0 | 9 | 1.0000 | 1.0000 | 0 | 0 |
| CFTR F508del ETI response | primary | 4 | 0 | 0 | 3 | 1.0000 | 1.0000 | 0 | 0 |
| EGFR exclusion-token canary | canary | 3 | 0 | 0 | 0 | 1.0000 | 1.0000 | 0 | 0 |

This diagnostic demonstrates improvement on the frozen PR 1 cases. It is not an independent expert study and does not by itself establish production or trusted-graph readiness.
