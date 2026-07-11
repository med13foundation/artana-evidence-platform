# PR-13 Specificity Noise Reduction Evidence Snapshot

Date: 2026-07-05

Branch: `alvaro/evidence-pr13-specificity-noise-reduction`

Base branch: `alvaro/evidence-pr12-precision-value-gates`

## Scope

PR-13 removes generic relation tail clauses when a stronger same-subject
relation exists in the same evidence sentence:

- Suppress `ASSOCIATED_WITH` candidates that trail a specific canonical sibling
  in the same sentence.
- Suppress `ASSOCIATED_WITH` candidates that trail a governed relation-type
  proposal in the same sentence.
- Preserve generic associations from different sentences.
- Keep governed relation proposals staged for review instead of dropping them.

## Repository Gates

- Focused pruning tests passed.
- Focused affected bundle passed:
  `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`,
  `services/artana_evidence_api/tests/unit/test_document_extraction.py`, and
  `tests/unit/test_relation_feasibility_audit.py`.
- `make artana-evidence-api-lint` passed.
- `make artana-evidence-api-type-check` passed.
- `make relation-feasibility-quality-gate` passed.

## Strict Live-Agent Result

Command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 \
  scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr13-specificity-noise-reduction-r2
```

| Metric | PR-12 live | PR-13 live |
|---|---:|---:|
| Verdict | RED | RED |
| Completed-agent precision | 0.7500 | 0.8095 |
| Completed-agent recall | 0.7200 | 0.6800 |
| High-value recall | 0.9000 | 0.8500 |
| Completed-agent valuable rate | 0.7500 | 0.8095 |
| Generic relation rate | 0.1250 | 0.0000 |
| Pruned generic relation siblings | 3 | 6 |
| Quality-filtered candidates | 8 | 5 |
| Candidate CURIE present rate | 0.8750 | 0.9048 |
| Verified CURIE match rate | 0.7568 | 0.7027 |
| Model CURIE wrong count | 0 | 0 |
| Fallback cases | 0 | 0 |
| Invalid strict-agent cases | 0 | 0 |
| Negative-control leakage cases | 0 | 0 |
| Governed proposal recall among proposal-eligible gold | 0.5000 | 1.0000 |

## Artifacts

- JSON:
  `reports/relation_feasibility/2026-07-05-pr13-specificity-noise-reduction-r2/relation_feasibility_report.json`
- Markdown:
  `reports/relation_feasibility/2026-07-05-pr13-specificity-noise-reduction-r2/relation_feasibility_report.md`

## Hashes

| Artifact | SHA-256 |
|---|---|
| live-agent JSON | `3d309bc3076561e8417d8992cbfa392fb3370ba8283cef9a53af3655df542620` |
| live-agent Markdown | `77218b16fe170bf8b5995a2599c52a218516b7a0a776c60ce18d8df5b2e890a5` |

## Interpretation

The live agent path still completes without deterministic fallback. PR-13
reaches the generic-noise target: generic relation rate is `0.0000`, while
precision and valuable-candidate rate both rise above `0.8000`.

The PR is still not trusted-graph ready. Recall and verified CURIE-linked gold
endpoint recovery remain below target, and the live run shows expected variance
in high-value recall. The remaining work belongs to PR-14 entailment coverage
and PR-15 governed proposal handling / entity-linking recovery.
