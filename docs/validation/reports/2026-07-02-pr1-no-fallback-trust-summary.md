# PR-1 No-Fallback-Trust Evidence Snapshot

Date: 2026-07-02

Branch: `alvaro/evidence-pr0-quality-harness`

Command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-02-pr1-no-fallback-trust-agent-strict-r6
```

Environment note: the local extractor did not have a configured OpenAI API key,
so every agent-mode case used unavailable/fallback diagnostics. The RED verdict
is expected and correct for this environment. PR-1's success condition is not a
higher relation score; it is that fallback/unavailable output cannot be labeled
as trusted evidence.

Fixture:

- Path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- SHA-256: `0be3c497378645a69038655818b65dc88af17f029679a3d6590eaa95164fbc70`
- Cases: 30
- Gold relations: 25
- Provenance: `curated_synthetic_seed`

Ignored local artifacts:

- JSON: `reports/relation_feasibility/2026-07-02-pr1-no-fallback-trust-agent-strict-r6/relation_feasibility_report.json`
- JSON SHA-256: `933d81f9a2648c28480a2507a5de97d28f4cf03076b23a68e7dd27700902116e`
- Markdown: `reports/relation_feasibility/2026-07-02-pr1-no-fallback-trust-agent-strict-r6/relation_feasibility_report.md`
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

## Implementation Evidence

PR-1 adds one trust rule across candidate extraction surfaces:

`trusted_evidence_eligible = agent_extraction_completed and not fallback_output_used`

Covered surfaces:

- default document extraction diagnostics and proposal drafts
- document extraction router response proposals
- variant-aware proposal drafts
- variant-aware review item drafts and nested proposal payloads
- review-item-to-proposal conversion
- research-init persisted fallback drafts
- mixed agent plus unmatched deterministic signal fallback

## Adversarial Findings

- `fallback_only_report`
- `fallback_candidates_look_valuable`
- `substring_grounding_only`
- `generic_relation_rate_high`

Interpretation: PR-1 makes fallback provenance explicit at the proposal/review
boundary. Fallback candidates may remain visible for triage and comparison, but
they are ineligible for trusted evidence until a completed agent extraction path
produces them without deterministic fallback.
