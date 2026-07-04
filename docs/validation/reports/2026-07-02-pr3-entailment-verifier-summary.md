# PR-3 Entailment-Verifier Evidence Snapshot

Date: 2026-07-02

Branch: `alvaro/evidence-pr0-quality-harness`

Planned branch: `alvaro/evidence-pr3-entailment-verifier`

Command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-02-pr3-entailment-verifier-agent-strict
```

Environment note: the local extractor did not have a configured OpenAI API key,
so every agent-mode case used unavailable/fallback diagnostics. The RED verdict
is expected and correct for this environment. PR-3's success condition is not a
higher relation score; it is that each grounded candidate can now be checked
for relation support, contradiction floors are fail-closed, and trusted
eligibility requires entailing support.

Fixture:

- Path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- SHA-256: `0be3c497378645a69038655818b65dc88af17f029679a3d6590eaa95164fbc70`
- Cases: 30
- Gold relations: 25
- Provenance: `curated_synthetic_seed`

Ignored local artifacts:

- JSON: `reports/relation_feasibility/2026-07-02-pr3-entailment-verifier-agent-strict/relation_feasibility_report.json`
- JSON SHA-256: `ff687b274783f712034c6c5f0f0a85f608223a36c223d4da3c2d81a41d4aba2d`
- Markdown: `reports/relation_feasibility/2026-07-02-pr3-entailment-verifier-agent-strict/relation_feasibility_report.md`
- Markdown SHA-256: `391cb4b1297a2d724c94a254eef3ba6df0a5a3424d3657cda1338ce11b964d0c`

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
| Entailment required candidates | 8 |
| Entailment checked count | 8 |
| Entailment supported count | 8 |
| Entailment checked rate | 1.0000 |
| Entailment supported rate | 1.0000 |

## Focused Validation

- `services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py`: 7 passed
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`: 52 passed
- `services/artana_evidence_api/tests/unit/test_proposal_actions.py`: 22 passed
- `tests/unit/test_relation_feasibility_audit.py`: 15 passed
- `services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py`: 8 passed
- Focused graph support hard-floor integration tests: 4 passed
- `ruff check` on touched PR-3 files: passed
- `make graph-service-checks`: passed
- `make artana-evidence-api-service-checks`: passed
- `make service-checks`: passed; total coverage 86.83% against 86%

## Implementation Evidence

Document extraction support now has a fail-closed triple support verifier with
three outcomes:

```python
TripleSupport = Literal["ENTAILS", "NEUTRAL", "CONTRADICTS"]
```

The verifier exposes a model-adapter port but falls back conservatively when no
model is configured. Model exceptions return `NEUTRAL` instead of allowing a
candidate to look trusted. The heuristic verifier is direction-aware for
directional relations: a reversed active sentence such as `EGFR activates
MED13` is `NEUTRAL` for the candidate `MED13 ACTIVATES EGFR`. Passive cues are
kept on the passive path, so `EGFR is activated by MED13` entails `MED13
ACTIVATES EGFR` but not the reversed `EGFR ACTIVATES MED13`.

Document extraction proposals now include `metadata.support_verification` only
after the PR-2 grounding gate passes. Ungrounded candidates omit the key
instead of making a skipped check look like a completed `NEUTRAL` check.

```json
{
  "support": "ENTAILS",
  "rationale": "Sentence contains both endpoints and a relation cue.",
  "model_id": "artana-heuristic-support-v1"
}
```

Contradicted support floors the candidate:

```json
{
  "ranking_score": 0.1,
  "support_verification_floor": "contradiction"
}
```

Candidate extraction trust metadata now also requires
`metadata.support_verification.support == "ENTAILS"` before
`trusted_evidence_eligible` can remain true.

The graph service now enforces the same support floor at the persistence
boundary. AI-authored evidence-requiring claim and canonical relation writes
are rejected unless `metadata.support_verification.support == "ENTAILS"`.
Promotion request metadata is filtered so reviewer-supplied metadata cannot
overwrite verifier-owned `evidence_grounding`, `support_verification`, trust,
or fallback fields before graph validation runs.

The feasibility audit now counts `entailment_required_count`,
`entailment_checked_count`, `entailment_supported_count`,
`entailment_checked_rate`, and `entailment_supported_rate`. A required
candidate is valuable only when support verification returns `ENTAILS`.

## Adversarial Review

Initial verdict: BLOCK.

Blocking findings:

- Role-blind heuristic support could treat reversed active triples as
  `ENTAILS`.
- Ungrounded candidates received `NEUTRAL` support metadata, making skipped
  checks look like completed checks.
- Graph promotion and validation enforced grounding but not entailing support
  at the persistence boundary.
- Passive-direction evidence could still entail the reversed triple.
- Promotion request metadata could overwrite verifier-owned grounding or
  support fields before graph validation.

Fixes:

- Direction-aware support verification plus a reversed-direction regression
  test.
- Support metadata is omitted when structured grounding fails.
- Graph AI evidence validation now requires
  `metadata.support_verification.support == "ENTAILS"` for claim and relation
  writes.
- Passive cue spans can no longer take the active subject-to-cue-to-object
  path.
- Promotion request metadata is filtered so reviewer-supplied values cannot
  replace verifier-owned metadata.

Final verdict: PASS.

Residual non-blocking risk: the verifier remains deterministic and heuristic
unless a model adapter is supplied, so broader semantic nuance remains a later
quality problem. The re-review found no remaining route for unsupported,
co-mentioned, reversed, or request-overridden evidence to become valuable or
trusted under the PR-3 invariants.

## Adversarial Findings

- `fallback_only_report`
- `generic_relation_rate_high`

Interpretation: PR-3 removes the old `entailment_not_checked` gap from the
strict fallback-only report, but it does not prove live agent quality. The
agent path still completed 0/30 cases locally, and generic relation rate is
still above the trusted-graph target.
