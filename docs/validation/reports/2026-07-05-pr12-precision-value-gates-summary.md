# PR-12 Precision And Valuable Candidate Evidence Snapshot

Date: 2026-07-05

Branch: `alvaro/evidence-pr12-precision-value-gates`

Base branch: `alvaro/evidence-pr11-verified-curie-linking`

## Scope

PR-12 adds an agent-output quality filter for relation candidates:

- Keep governed relation proposals in review for PR-15.
- Remove canonical candidates whose evidence sentence is uncertain.
- Remove canonical candidates whose evidence sentence is missing a relation
  endpoint.
- Remove canonical candidates whose sentence does not entail the candidate
  relation.
- Add support-verifier coverage for symbolic variant labels and relation types
  such as `BIOMARKER_FOR`, `SENSITIZES_TO`, `PREDISPOSES_TO`, and
  `DOWNSTREAM_OF`.
- Report `quality_filtered_candidate_count` in diagnostics, audit JSON,
  Markdown, and CLI output.

## Repository Gates

- Focused regression bundle passed:
  `services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py`,
  `services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py`,
  `services/artana_evidence_api/tests/unit/test_document_extraction.py`,
  `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`,
  and `tests/unit/test_relation_feasibility_audit.py`.
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
  --output-dir reports/relation_feasibility/2026-07-05-pr12-precision-value-gates
```

| Metric | PR-11 live | PR-12 live |
|---|---:|---:|
| Verdict | RED | RED |
| Completed-agent precision | 0.6897 | 0.7500 |
| Completed-agent recall | 0.8000 | 0.7200 |
| High-value recall | 0.9000 | 0.9000 |
| Low-value recall | 0.4000 | 0.0000 |
| Completed-agent valuable rate | 0.5862 | 0.7500 |
| Generic relation rate | 0.1379 | 0.1250 |
| Pruned generic relation siblings | 3 | 3 |
| Quality-filtered candidates | 0 | 8 |
| Candidate CURIE present rate | 0.8276 | 0.8750 |
| Verified CURIE match rate | 0.7838 | 0.7568 |
| Model CURIE wrong count | 0 | 0 |
| Wrong verified CURIE links | 0 | 0 |
| Fallback cases | 0 | 0 |
| Invalid strict-agent cases | 0 | 0 |
| Negative-control leakage cases | 0 | 0 |

## Artifacts

- JSON:
  `reports/relation_feasibility/2026-07-05-pr12-precision-value-gates/relation_feasibility_report.json`
- Markdown:
  `reports/relation_feasibility/2026-07-05-pr12-precision-value-gates/relation_feasibility_report.md`

## Hashes

| Artifact | SHA-256 |
|---|---|
| live-agent JSON | `e94798292607eb47d7f3282566f557156669dd22732bb46c8d92654291a46f02` |
| live-agent Markdown | `0eb782e5249ff8dcb966592a0411d3944c55b228653b0e1b4dd86b5a40a0dc71` |

## Interpretation

The live agent path still completes without deterministic fallback. PR-12
raises completed-agent precision from `0.6897` to `0.7500` and completed-agent
valuable rate from `0.5862` to `0.7500`, passing the valuable-rate target for
this slice.

The PR is not trusted-graph ready. It intentionally removes low-confidence
`may`/weak claims, so low-value recall drops to `0.0000`. Global recall drops to
`0.7200`, and verified CURIE match rate dips from `0.7838` to `0.7568` because
the current CURIE denominator still counts low-value gold endpoints. Remaining
precision issues are mostly generic sibling relations and governed relation
proposal recall, which belong to PR-13 and PR-15.
