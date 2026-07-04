# PR-0 Agent Strict V2 Evidence Snapshot

Date: 2026-07-02

Branch: `alvaro/evidence-pr0-quality-harness`

Command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-02-pr0-agent-strict-v2-fixed
```

Environment note: the local extractor did not have a configured OpenAI API key,
so every agent-mode case used unavailable/fallback diagnostics. The RED verdict
is expected and correct for this environment.

Fixture:

- Path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- SHA-256: `0be3c497378645a69038655818b65dc88af17f029679a3d6590eaa95164fbc70`
- Cases: 30
- Gold relations: 25
- Provenance: `curated_synthetic_seed`

Ignored local artifacts:

- JSON: `reports/relation_feasibility/2026-07-02-pr0-agent-strict-v2-fixed/relation_feasibility_report.json`
- JSON SHA-256: `933d81f9a2648c28480a2507a5de97d28f4cf03076b23a68e7dd27700902116e`
- Markdown: `reports/relation_feasibility/2026-07-02-pr0-agent-strict-v2-fixed/relation_feasibility_report.md`
- Markdown SHA-256: `218182612913a04f8eaff24d73349fea140ec0073e044d99060027132ba55057`

## Metrics

| Metric | Value |
|---|---:|
| Verdict | RED |
| Agent-completed cases | 0 |
| Fallback/unavailable cases | 30 |
| Invalid strict-agent cases | 30 |
| Completed-agent candidates | 0 |
| Completed-agent precision | 0.0000 |
| Completed-agent recall | 0.0000 |
| Completed-agent valuable rate | 0.0000 |
| All candidates | 9 |
| Fallback candidates | 9 |
| Fallback candidates that would look valuable | 6 |
| All-candidate precision | 0.7778 |
| All-candidate recall | 0.2800 |
| All-candidate valuable rate | 0.6667 |
| Generic relation rate | 0.1111 |
| Grounded sentence rate | 1.0000 |
| Gold support sentence alignment rate | 0.7778 |

## Adversarial Findings

- `fallback_only_report`
- `fallback_candidates_look_valuable`
- `substring_grounding_only`
- `generic_relation_rate_high`

Interpretation: PR-0 now makes the quality illusions explicit. Fallback output
is still visible for comparison, but completed-agent quality remains zero until
the actual agent path completes.
