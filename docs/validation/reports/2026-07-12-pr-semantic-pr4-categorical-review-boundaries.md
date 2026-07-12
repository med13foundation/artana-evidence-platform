# PR 4 Categorical Review Boundaries

## Goal

Remove the three PR 4 agent-output debts without replacing them with hidden
model-authored scores:

- `AON-PROP-001`: numeric proposal-review locator.
- `AOC-SHADOW-001`: composite expected-value band.
- `AOC-SHADOW-002`: composite risk band.

Agents remain responsible for semantic assessment. Deterministic code owns
identity mapping, exact coverage, value/risk derivation, approval policy, and
guarded-action enforcement.

## Implemented Boundaries

Proposal review now gives the agent content-bound opaque `draft_ref` values.
The result is accepted only when every expected reference appears exactly
once. Reordered results map safely; duplicates, omissions, and unknown
references reject the complete model result instead of partially applying it.

The shadow planner now emits atomic `benefit_findings` and `risk_findings`.
Each finding has a closed categorical kind and a nonblank evidence statement.
The model schema no longer contains `expected_value_band`, `risk_level`, or
`requires_approval`. Deterministic policy derives those compatibility fields,
vetoes non-control actions with high risk, and prevents guarded execution of
non-control actions unless risk is explicitly low and approval is explicitly
not required.

Proposal-review provider and outer timeouts now use the selected model's
registered timeout. This replaces the five-second hard stop that forced the
real judge path into heuristic fallback.

## Measured Progress

The canonical registry report records:

| Measure | Before PR 4 | After PR 4 |
| --- | ---: | ---: |
| Registered numeric model-output paths | 16 | 15 |
| Active debt IDs | 18 | 15 |
| Unquarantined debt IDs | 17 | 14 |

All three PR 4 debt IDs were removed. The remaining 14 unquarantined IDs are
owned by the variant-extraction and graph migrations.

## Adversarial Loop

The adversarial pass tested duplicate, missing, unknown, and permuted proposal
references; contradictory and whitespace-only findings; legacy composite
fields; high-risk action bypass; approval-required guarded execution; and
content changes under otherwise stable draft identity.

It found and fixed four concrete gaps:

1. Guarded execution ignored a deterministically derived approval requirement.
2. Finding and proposal rationales could be whitespace-only.
3. Opaque references were not bound to the complete draft content.
4. A hardcoded five-second proposal-review timeout forced the live agent into
   fallback even when the registered model allowed a longer execution window.

Two independent Claude review attempts were stopped after bounded windows
without returning findings. They are not counted as review passes or as
evidence of correctness.

## Live Agent Evidence

The live shadow planner completed with `openai:gpt-5-mini`:

- planner status: `completed`
- fallback used: `false`
- validation error: none
- action: `QUERY_PUBMED`
- benefit finding: `closes_evidence_gap`
- risk finding: `no_material_risk`
- deterministic compatibility result: value `high`, risk `low`, approval
  `false`

The live proposal-review judge completed with `openai:gpt-5-mini` after the
timeout fix:

- review status: `completed`
- fallback used: `false`
- review method: `llm_judge_v1`
- factual support: `strong`
- goal relevance: `direct`
- priority: `prioritize`

These calls prove the changed live contracts can complete. They are contract
smoke tests, not an independent expert-quality study.

## Validation

- Focused proposal, extraction, shadow-planner, guarded-runtime, replay, and
  registry suites pass.
- `make artana-evidence-api-static-checks` passes, including 518-source mypy,
  OpenAPI, boundary, registry, semantic-baseline, architecture-size, and
  architecture-structure gates.
- `make artana-evidence-api-service-checks` passes to 100% against an isolated
  migrated PostgreSQL database.
- The canonical agent-output registry report is current and its deterministic
  check passes.

## Remaining Limit

This PR improves decision integrity but does not establish trusted-graph
readiness. The remaining variant and graph output debts must reach zero, and
independent expert evaluation must still establish semantic precision and
recall on representative cases.
