# PR-4 Relation-Type Hardening Evidence Snapshot

Date: 2026-07-03

Branch: `alvaro/evidence-pr0-quality-harness`

Planned branch: `alvaro/evidence-pr4-relation-type-hardening`

Command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-03-pr4-relation-type-hardening-agent-strict
```

Environment note: the local extractor did not complete the LLM/agent path, so
all strict-agent cases used unavailable/fallback diagnostics. The RED verdict
is expected and correct for this environment. PR-4's success condition is that
raw unknown relation types cannot pass as normal extraction or graph-write
relation types without governed review.

Fixture:

- Path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- SHA-256: `0be3c497378645a69038655818b65dc88af17f029679a3d6590eaa95164fbc70`
- Cases: 30
- Gold relations: 25
- Provenance: `curated_synthetic_seed`

Ignored local artifacts:

- JSON: `reports/relation_feasibility/2026-07-03-pr4-relation-type-hardening-agent-strict/relation_feasibility_report.json`
- JSON SHA-256: `e4282496d49616c081e7cd8d0c7574c9ea357bf157bd5da8164c39d1bf7444d5`
- Markdown: `reports/relation_feasibility/2026-07-03-pr4-relation-type-hardening-agent-strict/relation_feasibility_report.md`
- Markdown SHA-256: `50f1c759308013277a09aeaba124aeab78c5fde2e4d085e4b0f62349d8db00d8`

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
| Raw unknown candidate relation type count | 0 |
| Raw unknown candidate relation type rate | 0.0000 |
| Relation type inventory surfaces | 9 |
| Raw unknown inventory relation type count | 0 |
| Raw unknown inventory relation type rate | 0.0000 |
| Grounded sentence rate | 1.0000 |
| Both-arguments-present rate | 1.0000 |
| Entailment checked rate | 1.0000 |
| Entailment supported rate | 1.0000 |

## Focused Validation

- PR-4 focused RED/GREEN tests: 6 passed before adversarial review.
- Post-adversarial raw-type boundary regressions: 7 passed.
- Post-re-review rejected relation, proposal-store, and legacy migration regressions: 28 passed.
- Related extraction, resolver, graph-client unit suites: passed.
- Full graph validation integration file: 38 passed.
- `tests/unit/test_relation_feasibility_audit.py`: 17 passed.
- `ruff check` on touched PR-4 and audit files: passed.
- `make artana-evidence-api-service-checks`: passed after the final proposal-store compatibility fixes.
- `make graph-service-checks`: passed.
- `make service-checks`: passed with captured exit code 0; aggregate coverage was 86.83% against the 86% floor.

## Implementation Evidence

LLM extraction schema now accepts only canonical relation types or the explicit
`PROPOSE_NEW_RELATION_TYPE` sentinel. A new relation proposal must be carried
in `proposed_relation_type` with `new_relation_type_rationale`; placing a raw
new type directly in `relation_type` is rejected.

Structured new relation proposals are skipped by normal candidate creation.
They remain governance signals, not graph-write candidates.

If a malformed or legacy payload bypasses schema validation, resolver decisions
still fail closed: `map_to_existing` and `typo_correction` can rewrite a
candidate, while `requires_review` and `register_new` remove it from the
normal extraction output.

Relation resolver agent failure now returns `requires_review` instead of
`register_new`, so an unavailable agent cannot create or preserve a raw
relation type as if it were approved.

Legacy flat graph gateways without relation validation no longer silently
permit relation writes. Successful promotion tests now expose explicit
validation methods; flat gateways without validation degrade to governed review
or blocked writes instead of implicit persistence.

The feasibility audit now counts candidate-level
`raw_unknown_relation_type_count` and inventory-level
`raw_unknown_relation_type_surface_count`; any surviving raw unknown relation
type on extracted candidates or supplied review/proposal/graph/dictionary
surfaces is a RED-quality issue. Separate boundary regression tests cover
normal proposal drafts, variant-aware proposal drafts, rejected-relation review
items, review-queue conversion, proposal-store persistence, preflight
submission side effects, and graph claim persistence.

## Adversarial Review

External adversarial review initially returned BLOCK. Fixes added after that
review:

- Graph `/claims` now rejects unknown relation types before claim persistence.
- Variant-aware extraction maps `AFFECTS` to `MODULATES` and skips raw
  `EXPLAINS` from normal `candidate_claim` staging.
- `build_document_extraction_drafts` skips raw unknown and
  `PROPOSE_NEW_RELATION_TYPE` candidates defensively.
- Preflight no longer auto-submits relation-type dictionary proposals as a side
  effect of raw unknown graph writes.

External adversarial re-review returned BLOCK for one remaining side door:
supported rejected-relation review items could still carry raw relation types
into nested `candidate_claim` proposal drafts, and the audit metric was
candidate-only.

Fixes added after re-review:

- Rejected relation review items now canonicalize relation types and skip raw
  unknown relation labels before nested proposal-draft creation.
- Proposal persistence now has a shared candidate-claim relation-type guard for
  both in-memory and SQLAlchemy stores.
- Review-queue conversion returns a 409 conflict instead of creating a proposal
  when legacy nested proposal payloads contain raw unknown relation types.
- The feasibility audit can now score relation-type inventory surfaces in
  addition to extracted candidates.
- Legacy proposal payloads using `relation_type`, `proposed_relation`, or the
  old `SUGGESTS` placeholder are migrated to governed `proposed_claim_type`
  values instead of persisting raw relation labels.

External adversarial final re-review: PASS. Reviewer caveat: the strict audit
currently populates candidate relation-type inventory surfaces; proposal,
graph, and dictionary surfaces are covered by boundary tests until a real
live-agent inventory artifact exists.

Built-in adversarial findings:

- `fallback_only_report`
- `fallback_candidates_look_valuable`
- `generic_relation_rate_high`

Interpretation: PR-4 closes the raw relation-type leakage gate, but it does not
prove live agent quality. The agent path still completed 0/30 cases locally,
and generic relation rate is still above the trusted-graph target.
