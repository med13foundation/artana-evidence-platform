# Staged generalization V5 grader implementation

Date: 2026-07-22

Branch: `alvaro/tg04-source-general-claim-verification`

Scope: exposed development sources only

## Outcome

The source-science grader is implemented, independently reviewed against primary
sources, frozen, replay-tested, preregistered, and proven in one live fail-fast
checkpoint.

The exact scientific terminal is **PIVOT_WITH_EVIDENCE**. Four valid Luna calls
produced verified receipts and custody. Comparison, null statistics, and
negation passed. The uncertainty case then exposed a reproducible source-general
failure, so execution stopped before drug sensitivity and nested causation as
preregistered. The historical V4 result remains immutable and non-creditable.

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
- live V5 result: `d60249165d26778a603f60c91ad8cf676907dfbc63246a49c8506fae0b574f10`

## Live V5 checkpoint

The private worktree credential was loaded without exposing it. The frozen
`openai:gpt-5.6-luna` runner made four creation calls with no retries or
duplicates. Every response completed with `VERIFIED_LIVE` custody and passed
its output-token, total-token, latency, and cost budgets.

Aggregate evidence:

- terminal decision: `PIVOT_WITH_EVIDENCE`;
- passed cases: 3/4 executed, from 6 planned;
- complete-event recovery: 3/4;
- participant-role fidelity: 3/4;
- nested-event structure: 4/4;
- direction, comparison, polarity, statistical fidelity, and exact grounding:
  4/4;
- uncertainty fidelity: 3/4;
- unsupported claims: 2;
- contradictions: 1;
- calls: 4;
- input/output/total tokens: 7,243 / 13,636 / 20,879;
- latency: 457.867 seconds;
- cost: USD 0.089059;
- graph writes: 0;
- qualification credit and trusted promotion: `false`.

The first three cases recovered their required cores without permitted,
ambiguous, or unsupported additions. The uncertainty output instead created a
`VARIANT` participant from the anaphoric phrase `the majority of which`. That
phrase refers back to `947 variants`; it is not itself the source entity. The
output consequently omitted both required participants, `947 variants` and the
`SLC12A3 gene`, and omitted their required links. It also labeled the
uncertainty axis `ASSERTED`, reasoning that the classification statement was
asserted, instead of preserving the explicit classification `uncertain
significance` as `UNCERTAIN`.

This identifies the next architecture/model capability precisely: event-local
participant extraction must resolve anaphoric mentions to exact explicit
antecedents while retaining source context, and the semantic-axis contract must
distinguish assertion of a classification event from the uncertainty conveyed
by the classification value. No grader relaxation can safely correct either
failure. A future cycle should address that source-general capability, not add
case-specific aliases or reinterpret this completed execution.

## Validation

Focused validation passed:

- Ruff over the V5 CLI, grading package, and tests;
- strict mypy over 14 source files;
- 13 focused unit/regression tests, including artifact reproducibility,
  blinding, independent identities, field-level majority, policy drift,
  required-core preservation, forbidden and ambiguous context, immutable V4
  replay, preregistration drift, fail-fast canary behavior, and complete
  recomputation of the live result and receipt/custody chain.

The repository-wide `make service-checks` gate was run exactly once after the
focused state was stable. All emitted lint, type, boundary, OpenAPI, generated
contract, architecture, and completed unit-test checks passed. The aggregate
gate then stopped in `postgres-wait`: PostgreSQL did not become reachable on
`localhost:5432` within 60 seconds, so `coverage-check` and the remaining
database-backed test work did not run. This is an environmental validation
blocker, not a passing full-suite result and not a demonstrated code failure.
The gate was not rerun, preserving the recovered exact-once instruction.

The Docker PostgreSQL container was subsequently recreated without removing its
named volume, restoring the missing host-port publication. The exact
database-backed `coverage-check` test selection was then run against an isolated
migrated database, omitting only the XML writer to preserve the user's existing
dirty `coverage.xml`. It passed at 87.62% coverage against the 86% threshold;
the ephemeral database was dropped cleanly. Thus the previously unexecuted
database-backed work is green, while the historical aggregate command remains
honestly recorded as having stopped at its first PostgreSQL wait.
