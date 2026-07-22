# Staged generalization V5 grader implementation

Date: 2026-07-22

Branch: `alvaro/tg04-source-general-claim-verification`

Scope: exposed development sources only

## Outcome

The source-science grader is implemented, independently reviewed against primary
sources, frozen, replay-tested, and preregistered. It is ready for its one-shot
V5 live checkpoint.

The scientific terminal remains **PIVOT_WITH_EVIDENCE**. The historical V4
result is immutable, and its non-creditable replay through the new grader still
fails. No V5 provider call was made because `OPENAI_API_KEY` is absent from the
task environment. There are no V5 attempts, receipts, or raw outputs to
reinterpret.

## Root cause addressed

The legacy grader treated the minimal core inventory as a closed equality
contract. A source-faithful extraction could therefore fail merely for adding
valid, explicit statistical or mechanistic context. Relaxing the grader without
an independently frozen boundary would create the opposite problem: unsupported
or neighboring claims could receive credit.

V5 replaces that false choice with two deterministic lanes:

1. Required core remains exact and cannot be replaced by optional context.
2. Additional context receives credit only when independent, blinded source
   review froze its entity type, exact span aliases, event linkage, role, and
   classification before provider execution.

Unlisted additions are unsupported. Ambiguous additions are review-only and
block a pass. Benchmark projection remains separate, evaluation-only,
review-only, non-creditable, and forbidden from graph promotion.

## Independent Internet review

Three independent source graders received only the blinded source packet,
review schema, primary-source manifest, and grading instructions. They did not
receive production output, frozen core references, or benchmark labels.

The frozen policy binds the three review artifacts by SHA-256 and resolves each
candidate by two-of-three majority. Presence, classification, and event-role
linkage are voted independently; an unresolved field stops the freeze. The only
field returned for blinded tiebreak was the excluded baseline-dexamethasone
population. It resolved to `AMBIGUOUS_REVIEW_ONLY` with
`CONTEXTUAL_PARTICIPANT`, because the current role schema cannot express
exclusion without implying cohort inclusion.

The final policy contains:

- 5 permitted contextual participants;
- 2 ambiguous review-only participants;
- 16 forbidden participants;
- 1 reviewed candidate excluded because it duplicates required core.

Notable decisions:

- `log-rank P = 0.08`, `hazard ratio 0.92`, and its confidence interval are
  permitted measurements of the null comparison;
- `Kaplan-Meier survival curves` and `adjusted models` are analysis
  representations, not additional graph participants;
- TS and DPD are permitted context for the drug-sensitivity event;
- the excluded dexamethasone subgroup and HCMV region 1/2 protein refinement
  remain review-only;
- neighboring demographic, medication, variant, phenotype, and experimental
  population mentions are forbidden for the focused events.

Primary evidence custody uses NCBI PubMed EFetch payloads for PMID 40289860,
42454948, 21965773, and 7966592. Their URLs, retrieval timestamps, byte counts,
and payload hashes are frozen in the evidence manifest.

## Immutable V4 replay

The V4 replay is diagnostic only:

- decision: `OFFLINE_DUAL_LANE_GRADER_FAIL`;
- historical result changed: `false`;
- qualification credit: `false`;
- provider calls: `0`;
- graph writes: `0`.

The V4 comparison canary passes. The V4 null-statistics output still fails with
four unsupported node/link claims: `NSCLC` was not independently accepted as a
separate participant, and `Kaplan-Meier survival curves` was independently
classified as forbidden. This disproves the provisional hypothesis that all
four V4 additions were valid context.

## Frozen execution boundary

The V5 preregistration freezes the exposed panel, prompt, output schema,
provider format, source and provider-input hashes, grading artifacts, policy,
V4 replay, benchmark custody, code, model settings, budgets, case order, and
acceptance rules.

- model: `openai:gpt-5.6-luna`
- reasoning: `high`
- calls: at most 6, one creation call per case, zero retries
- per-call ceilings: 20,000 output tokens, 24,000 total tokens, 900 seconds,
  USD 0.15
- global cost ceiling: USD 0.90
- canary first; stop on invalid custody, budget failure, or scientific failure
- graph writes and trusted promotion: forbidden

Artifact hashes:

- policy: `7d045ccca6398ca10d3dfc3b8136fa871c9b118bfc05ed19d43daa905e518649`
- preregistration: `1b145ed37ce004a6811c84c3bb92837f129b73af0f2dbae2d68d18dea414fd2e`
- immutable V4 replay: `78a25c46696cbd7a7cd4b96ffba8f6048ec930352988663ed284c6f62e749236`

## Validation

Focused validation passed:

- Ruff over the V5 CLI, grading package, and tests;
- strict mypy over 14 source files;
- 12 focused unit/regression tests, including artifact reproducibility,
  blinding, independent identities, field-level majority, policy drift,
  required-core preservation, forbidden and ambiguous context, immutable V4
  replay, preregistration drift, and fail-fast canary behavior.

The repository-wide `make service-checks` gate was run exactly once after the
focused state was stable. All emitted lint, type, boundary, OpenAPI, generated
contract, architecture, and completed unit-test checks passed. The aggregate
gate then stopped in `postgres-wait`: PostgreSQL did not become reachable on
`localhost:5432` within 60 seconds, so `coverage-check` and the remaining
database-backed test work did not run. This is an environmental validation
blocker, not a passing full-suite result and not a demonstrated code failure.
The gate was not rerun, preserving the recovered exact-once instruction.

## Live checkpoint blocker

The live command is intentionally not run with Codex or a substitute model.
Doing so would violate the frozen `openai:gpt-5.6-luna` provider and receipt
contract. Once `OPENAI_API_KEY` is available in the task environment, the
preregistered command is:

```bash
.venv/bin/python scripts/run_staged_generalization_v5.py execute
```

Until that call produces valid custody and scientific metrics, V5 is not
qualification evidence and the correct terminal decision remains
`PIVOT_WITH_EVIDENCE`.
