# PR-11 Verified CURIE Linking Evidence Snapshot

Date: 2026-07-05

Branch: `alvaro/evidence-pr11-verified-curie-linking`

## Scope

PR-11 tightens entity identity handling for live-agent extraction:

- Add a small verified biomedical entity dictionary for the current benchmark
  surface.
- Treat model-supplied CURIEs as hints only.
- Replace wrong model hints with verified dictionary identifiers when the
  extracted label is known exactly.
- Preserve hint provenance in metadata with `model_hint_curie` and
  `model_hint_status`.
- Add a scorecard blocker for wrong verified CURIE links, so bad verified IDs
  cannot pass the trusted-graph gate.

## Repository Gates

- Focused regression bundle passed:
  `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`,
  `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`,
  `services/artana_evidence_api/tests/unit/test_document_extraction.py`, and
  `tests/unit/test_relation_feasibility_audit.py`.
- `make artana-evidence-api-lint` passed.
- `make artana-evidence-api-type-check` passed.
- `make relation-feasibility-quality-gate` passed.
- `make service-checks` passed, with coverage at 86.86% against an 86% floor.

## Strict Live-Agent Result

Command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  /Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform/.venv/bin/python \
  scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr11-verified-curie-linking-r2
```

| Metric | Value |
|---|---:|
| Verdict | RED |
| Verdict reason | Too few CURIE-linked gold endpoints were recovered by extraction. |
| Cases | 30 |
| Gold relations | 25 |
| Extracted candidates | 29 |
| Agent-completed cases | 30 |
| Agent zero-candidate cases | 8 |
| Negative-control cases | 5 |
| Negative-control empty completions | 5 |
| Negative-control leakage cases | 0 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Completed-agent precision | 0.6897 |
| Completed-agent recall | 0.8000 |
| High-value recall | 0.9000 |
| Low-value recall | 0.4000 |
| Completed-agent valuable rate | 0.5862 |
| Generic relation rate | 0.1379 |
| Pruned generic relation siblings | 3 |
| Governed proposal candidates | 2 |
| Governed proposal gold matches | 1 |
| Governed proposal-eligible gold relations | 2 |
| Governed proposal recall among proposal-eligible gold | 0.5000 |
| Governed proposal matches over all gold relations | 0.0400 |
| Gold CURIE endpoints | 37 |
| Candidate CURIE endpoints | 48 |
| Candidate CURIE present rate | 0.8276 |
| Verified CURIE matches | 29 |
| Verified CURIE match rate | 0.7838 |
| Model CURIE wrong count | 0 |
| Wrong verified CURIE links | 0 |
| Verified CURIE-linked gold endpoint rate | 0.7838 |

## Delta

The prior live-agent remediation snapshot had verified CURIE match rate
`0.0000` and model CURIE wrong count `13`. The first PR-11 live run raised
verified CURIE match rate to `0.3514`. After allowing the verified dictionary to
replace wrong model hints for exact known labels, the second PR-11 live run
raised verified CURIE match rate to `0.7838` while keeping wrong verified CURIE
links at `0`.

## Artifacts

- JSON:
  `reports/relation_feasibility/2026-07-05-pr11-verified-curie-linking-r2/relation_feasibility_report.json`
- Markdown:
  `reports/relation_feasibility/2026-07-05-pr11-verified-curie-linking-r2/relation_feasibility_report.md`

## Hashes

| Artifact | SHA-256 |
|---|---|
| live-agent JSON | `a028031aa69b53357a67f14979208d3b73821d4b145a878aa28a2728592d2285` |
| live-agent Markdown | `0fc05c2c93e38c941b347a3448e7e68171c5084b14343ce0019f56d50ae50578` |

## Interpretation

The live agent path completes without deterministic fallback, and PR-11 removes
the most dangerous identity failure mode: wrong model CURIE hints no longer
become trusted verified identifiers. The system is still not trusted-graph ready
because verified CURIE-linked gold endpoint recovery remains below the `0.95`
target, precision is below the trusted graph target, and valuable candidate rate
is still below target.
