# PR-2 Grounding-Gate Evidence Snapshot

Date: 2026-07-02

Branch: `alvaro/evidence-pr0-quality-harness`

Command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-02-pr2-grounding-gate-agent-strict
```

Environment note: the local extractor did not have a configured OpenAI API key,
so every agent-mode case used unavailable/fallback diagnostics. The RED verdict
is expected and correct for this environment. PR-2's success condition is not a
higher relation score; it is that relation evidence now has measurable sentence
anchoring plus subject/object presence, and AI-authored claims fail closed when
that grounding metadata is missing or incomplete.

Fixture:

- Path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- SHA-256: `0be3c497378645a69038655818b65dc88af17f029679a3d6590eaa95164fbc70`
- Cases: 30
- Gold relations: 25
- Provenance: `curated_synthetic_seed`

Ignored local artifacts:

- JSON: `reports/relation_feasibility/2026-07-02-pr2-grounding-gate-agent-strict/relation_feasibility_report.json`
- JSON SHA-256: `bd066d60be48549ceae59982e4baa166e8731a82537d73acf8c2d9761b568d62`
- Markdown: `reports/relation_feasibility/2026-07-02-pr2-grounding-gate-agent-strict/relation_feasibility_report.md`
- Markdown SHA-256: `6ae759e7233930372268551d0d61ad4b1ccc6a6c0446d5d80f57c2c088754c12`

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
| Both-arguments-present count | 9 |
| Both-arguments-present rate | 1.0000 |
| Gold support sentence alignment rate | 0.7778 |

## Implementation Evidence

Document extraction proposals now include `metadata.evidence_grounding`:

```json
{
  "anchor_start": 0,
  "anchor_end": 43,
  "match_kind": "exact",
  "score": 1.0,
  "subject_present": true,
  "object_present": true,
  "grounded": true
}
```

The feasibility audit now counts `both_arguments_present_count` and
`both_arguments_present_rate`; a candidate is valuable only when its evidence
sentence is anchored and both relation endpoints are present in that sentence.

The graph service now rejects AI-authored claims that require evidence unless
`metadata.evidence_grounding` has `grounded=true`, `subject_present=true`, and
`object_present=true`. The claim creation route returns HTTP 400 for that
AI-authored `insufficient_evidence` validation result instead of persisting the
claim.

The same hard floor now applies to canonical relation creation. `POST
/relations` validates AI-authored relation-create requests after ordinary
triple validation and before it creates the resolved claim or materializes the
canonical relation. A regression test covers an `artana_generated` relation
request with `object_present=false` and expects HTTP 400.

## Adversarial Review

Initial verdict: BLOCK.

Blocking finding: canonical relation promotion bypassed the PR-2 AI grounding
floor because `POST /relations` validated ordinary evidence presence but did
not require `metadata.evidence_grounding` before persistence.

Fix: the shared AI evidence validator now accepts both claim-create and
relation-create requests. `POST /relations` calls
`validate_ai_authored_relation_request` after triple validation and before
claim/relation persistence.

Final verdict: PASS.

Non-blocking risk: direct `POST /relations` writes still depend on AI markers
because `KernelRelationCreateRequest` has no `agent_run_id` or `ai_provenance`
field. Proposal promotion sets `evidence_sentence_source=artana_generated`, so
the bypass found by the reviewer is covered.

## Adversarial Findings

- `fallback_only_report`
- `fallback_candidates_look_valuable`
- `entailment_not_checked`
- `generic_relation_rate_high`

Interpretation: PR-2 closes the most basic grounding hole by requiring an
anchored evidence sentence with both endpoints present. It still does not prove
live agent quality because all strict-agent cases were fallback/unavailable,
and it still does not verify relation entailment. PR-3 should add the
fail-closed entailment verifier.
