# Agent-First Semantic Relevance Improvement Plan

Date: 2026-07-11

Status: Active; PR 1 merged in GitHub PR `#139`; PR 2 merged in GitHub PR
`#141`; PR 3 is next

Baseline commit: `9f95b2277b0fcb30cd8eb06116af484c841f8319`

## Goal

Make Artana Evidence select useful, specific biomedical evidence through an
agent judgment grounded in the retrieved record, while keeping deterministic
code responsible for validation, provenance, deduplication, budgets, and
fail-closed safety controls.

This plan addresses the live shadow evaluation in which three model-planned
PubMed runs completed without fallback but produced:

- micro precision: `0.2381`
- micro end-to-end recall: `0.3846`
- case ranking ECE: `0.7167`, `0.6000`, and `1.0000`
- all three expert-study entries: failed
- strict batch suite: failed

The immediate product problem is not source planning. The model produced useful
queries and PubMed returned valuable records. The authoritative selector in
`evidence_selection_candidate_screening.py` reduced natural-language criteria
to token overlap and made the final relevance decision.

## Execution Reconciliation After PR 141

This section is authoritative when the original PR numbering below conflicts
with implementation history.

| Actual milestone | State | Merge-visible evidence |
| --- | --- | --- |
| PR 1: freeze the failure corpus | Merged as GitHub PR `#139` | Commit `1b2559aa`; categorical fixtures and reproducible baseline metrics |
| PR 2: agent-first semantic selector and runtime authority | Merged as GitHub PR `#141` | Commit `451e6433`; strict agent path, grounded categorical findings, deterministic decision policy, provenance, and fail-closed behavior |
| PR 3: framework-wide schema registry and numeric-origin guard | Next | Branch `alvaro/evidence-semantic-pr3-schema-registry`; acceptance gates defined below |

PR 2 delivered the most important behavioral change first. The live diagnostic
reported precision `1.0000`, recall `0.9231`, coverage `0.9333`, two explicit
abstentions, invalid-agent selections `0`, semantic fallbacks `0`, and a passed
injection canary. These are strong diagnostic results, not independent expert
proof and not trusted-graph readiness.

PR 2 did not deliver the framework-wide registry originally assigned to it in
the first draft of this plan. PR 3 therefore owns the remaining systemic gap:

- register every model-output schema and every agent-authored category;
- inventory every numeric field by one allowed origin and typed provenance
  envelope;
- quarantine legacy model-authored numeric judgments in an exact-ID debt
  manifest;
- reject direct model-client calls and prose-to-decision parsing outside the
  guarded adapter;
- prove through taint tests that agent-authored numbers cannot influence
  selection, extraction, staging, ranking, evaluation, trusted eligibility, or
  promotion;
- route the fast registry, debt, origin, and boundary checks through CI.

PR 3 must preserve PR 2's live quality and strict no-fallback behavior. It is a
framework enforcement PR, not an opportunity to retune semantic decisions.

## Non-Negotiable Principles

1. Model-planned runs must use an agent for semantic relevance decisions.
2. No deterministic semantic fallback may be credited as agent success.
3. Agent failure, invalid output, missing evidence, or timeout must abstain or
   fail the run according to explicit policy; it must not silently select.
4. Every selection decision must be traceable to criterion-level evidence from
   the retrieved record.
5. Titles alone cannot support a `direct` grounded selection when the criterion
   requires population, intervention, outcome, or study-design evidence.
6. Human-review, AI-review simulation, synthetic fixtures, and production
   evidence must remain distinct provenance classes.
7. Selection quality, ranking quality, relation extraction quality, and trusted
   graph promotion are separate gates.
8. Auto-promotion remains disabled until the final end-to-end gate passes with
   independent expert labels.
9. Agents must not author numeric confidence, probability, relevance, quality,
   priority, or readiness values.
10. Agents emit finite categorical judgments, literal evidence spans, and
    natural-language explanations. Versioned deterministic code alone converts
    those judgments into numeric weights, rankings, and evaluation metrics.
11. A numeric field is allowed only when it uses one origin from the normative
    six-origin taxonomy below: source measurement, retrieval algorithm,
    deterministic policy, calibration model, computed metric, or runtime
    observation. It must satisfy that origin's complete typed provenance
    envelope.
12. An evaluator agent must not score its own output. Independent evaluator
    agents follow the same categorical-output rule and cannot establish expert
    gold evidence.

## Framework-Wide Categorical Judgment Rule

This rule applies to every agent and every evaluation PR in this plan, not only
to evidence selection.

### Agent-authored output: allowed

- finite enum or literal judgments such as `select`, `reject`, `abstain`,
  `supported`, `contradicted`, `unknown`, `primary`, `secondary`, `exact`, and
  `ambiguous`, only when each value has an observable operational definition;
- the criterion or policy identifier being assessed;
- literal source spans and stable source locators;
- a natural-language explanation tied to those spans;
- missing-information, exclusion, safety, and invalid-output categories;
- model ID, prompt version, latency, token use, and cost as observed runtime
  metadata rather than model judgments.

### Agent-authored output: forbidden

- self-reported confidence or probability such as `0.87`;
- numeric relevance, support, quality, utility, priority, or readiness scores;
- unanchored Likert values such as explanation quality `1` through `5`;
- numeric values parsed from model prose;
- a judge-agent score used directly as ground truth or a promotion threshold;
- a numeric field renamed to `weight`, `rank`, or `certainty` while still being
  chosen by the model.
- vague ordinal categories such as `low`, `medium`, `high`, `tentative`,
  `supported`, or `strong` when they merely disguise self-confidence rather
  than encode an observable evidence condition.

Agent categories must be atomic and operationally anchored. For example,
`supported` means that a literal cited span directly satisfies the named
criterion; `contradicted` means that a cited span states an incompatible fact;
and `unknown` means neither condition is established. Composite relevance,
support-strength, readiness, and priority bands are deterministic policy
outputs, not agent fields.

### Numeric output: allowed origins

Every allowed numeric value must declare one of these origins:

- `source_measurement`: effect size, p-value, confidence interval, sample size,
  or other number copied and anchored to a source;
- `retrieval_algorithm`: embedding similarity, lexical retrieval score, or
  provider-supplied search rank;
- `deterministic_policy`: a versioned mapping from categorical judgments;
- `calibration_model`: a versioned fitted transformation of a deterministic
  policy output, trained without the evaluated held-out outcomes;
- `computed_metric`: precision, recall, agreement, coverage, error rate,
  or another reproducible calculation;
- `runtime_observation`: latency, token count, provider-reported cost, retry
  count, or another measured execution property.

Raw retrieval and deterministic-policy values are never probabilities. Only a
separate `calibration_model` output may be described as a probability, and only
when a held-out calibration study supports that exact input policy, calibration
algorithm, corpus, and version.

### Required numeric provenance envelopes

Numeric values use origin-specific typed envelopes:

| Origin | Required provenance |
| --- | --- |
| `source_measurement` | Source locator, literal span, field name, unit, extraction method, and source hash |
| `retrieval_algorithm` | Provider/algorithm ID, version, query/input hash, and whether the value affected candidate acquisition |
| `deterministic_policy` | Complete categorical inputs, policy ID/version, mapping version, caps, vetoes, and blocking categories |
| `calibration_model` | Input policy ID/version, calibration algorithm/version, training-set hash, held-out protocol, and calibration status |
| `computed_metric` | Metric specification/version, complete input artifact hashes, denominator, and aggregation scope |
| `runtime_observation` | Runtime/provider source, unit, collection method, and execution ID |

The categorical-input and veto requirements apply to deterministic-policy
values, not to source measurements, retrieval scores, or runtime observations.
No bare numeric field is accepted at an agent, evaluation, study, ranking, or
promotion boundary.

PR 3 must introduce a mandatory registry for every model-output schema. Runtime
invocation rejects unregistered schemas, generic numeric metadata, and numeric
judgment fields. Numeric source measurements use typed origin envelopes rather
than arbitrary scalar dictionaries. Numbers may appear in explanations or
source spans, but parsing prose cannot create or influence a policy score.

All model and agent execution must pass through one guarded adapter that requires
a registered schema ID and validates the returned contract. A boundary/AST check
must reject direct model-client calls, authoritative unstructured output, and
model prose parsed into decision fields outside that adapter.

The registry also owns every agent-authored categorical field and enum value.
Each value requires an observable definition, required evidence/locator shape,
positive example, counterexample, and invalid/unknown behavior. CI rejects an
unregistered category, an enum without these anchors, or a composite ordinal
category presented as an atomic agent finding.

Legacy violations must live in an explicit, shrinking debt manifest with a
stable debt ID, schema and field path, producer, consumers, current influence,
owner PR, quarantine rule, and removal gate. Exact debt IDs must only disappear;
one violation cannot replace another while preserving the count. From PR 3
onward, a legacy numeric field may remain for compatibility only when runtime
tests prove it is quarantined from selection, extraction, staging, ranking,
evaluation, trusted eligibility, and promotion.

### Preliminary numeric-judgment debt ownership

PR 3 must replace this preliminary inventory with a machine-readable complete
scan. These known items already have owners:

| Current surface | Risk | Owner |
| --- | --- | --- |
| `agent_contracts.py::BaseAgentContract.confidence_score` | Shared agent self-confidence enters multiple workflows | PR 3 shared contract quarantine and owning migration |
| `agent_contracts.py::EvidenceItem.relevance` | Agent assigns numeric relevance to its own evidence | PR 3 shared evidence quarantine and owning migration |
| `agent_contracts.py::GraphSearchResultEntry.relevance_score` | Graph-search output can present model-authored relevance as a rank | PR 3 registry and graph-search quarantine; removal in owning migration |
| `agent_contracts.py::EvidenceChainItem.confidence` | Compatibility confidence can obscure whether the model or policy produced it | PR 3 typed provenance envelope and quarantine |
| `agent_contracts.py::GraphSearchContract.confidence_score` | Live graph-search policy can consume a legacy number | PR 3 graph-search quarantine and owning migration |
| `pubmed_relevance.py` confidence instruction | Categorical relevance result still demands a model probability | PR 3 registry and debt quarantine |
| `variant_extraction_contracts.py::confidence_score` and generic scalar values | Extraction output and child observations expose model-authored confidence or untyped numbers | PR 3 quarantine and typed measurement envelope; PR 8A removal |
| `evidence_selection_validation.py::explanation_quality_score` | Subjective `1` through `5` judgment is treated as comparable measurement | PR 4 categorical review rubric |
| Shadow-study `ranking_score` fields | Score origin can be unclear or mixed with reviewer judgment | PR 4 provenance split and PR 5 deterministic ranking policy |

This table is explicitly incomplete until PR 3 generates the registry-backed
manifest. Existing `FactAssessment` and `DecisionConfidenceAssessment`
categorical inputs follow the desired direction: the database or service
computes compatibility weights from enums. PR 3 must still verify that no
model-written legacy number is converted into those categories before the
deterministic policy runs.

## Target Decision Contract

Each candidate should produce a structured judgment similar to:

```json
{
  "recommended_decision": "select | reject | abstain",
  "entity_match": "not_found | ambiguous | exact",
  "population_match": "not_stated | mismatch | partial | exact | not_applicable",
  "reported_study_design": "randomized_trial | cohort | case_control | case_report | review | meta_analysis | preclinical | unclear",
  "criterion_findings": [
    {
      "criterion_id": "population",
      "status": "supported | contradicted | unknown",
      "evidence_locator": "abstract:sentence:3",
      "evidence_text": "",
      "reason": ""
    }
  ],
  "primary_or_secondary": "primary | secondary | unclear",
  "missing_information": [],
  "safety_flags": [],
  "model_id": "",
  "prompt_version": ""
}
```

The values are operationally anchored:

- `supported`: the cited literal span directly establishes the named criterion;
- `contradicted`: the cited literal span establishes an incompatible fact;
- `unknown`: no validated span establishes either outcome;
- `exact`: the record explicitly names the requested entity, population, or
  design without unresolved normalization ambiguity;
- `partial`: the record establishes only a strict subset of the requested
  population;
- `ambiguous` or `unclear`: the record does not permit one supported choice.

The authoritative decision policy must be explicit:

- `select`: every required criterion is supported and no exclusion criterion is
  supported.
- `reject`: at least one required criterion is contradicted or an exclusion is
  supported.
- `abstain`: information is missing, ambiguous, inaccessible, or the model
  response is not valid enough to decide.

The agent recommends a categorical decision but does not convert categories
into a score. Code validates consistency and derives the authoritative decision,
grounding level, composite relevance/support bands, and any ranking weight from
the complete atomic findings. Hard exclusions and unsupported required criteria
remain vetoes regardless of the derived weight.

## Common PR Loop

Every implementation PR from PR 2 onward follows the same loop. PR 1 predates
the registry and is a historical categorical baseline; PR 3 must retrospectively
scan the merged PR 1 and PR 2 artifacts and prove that their agent outputs do
not introduce unregistered numeric judgments before PR 3 can merge.

1. Add RED unit and regression tests from a measured failure.
2. Implement the smallest complete ownership-boundary change.
3. Run focused tests, Evidence API static checks, and service checks.
4. Run two adversarial reviews:
   - semantic/safety reviewer: unsupported selection, prompt injection,
     criterion drift, and fallback leakage;
   - architecture/test reviewer: boundaries, failure handling, observability,
     and missing regressions.
5. Fix every blocking finding and rerun the affected gates.
6. Run the frozen live diagnostic when runtime behavior changes.
7. Publish a merge-visible JSON/Markdown report with exact artifacts and hashes.
8. Merge only when the PR-specific acceptance gate is satisfied.

Every PR report must also include a categorical-judgment conformance section:

- agent-authored numeric judgment fields added: `0`;
- complete registry diff and exact legacy debt IDs removed or remaining;
- category-registry diff proving every new/changed enum is operationally
  anchored with evidence requirements, examples, and counterexamples;
- categorical contract fields exercised by tests;
- deterministic scoring policy IDs and versions changed;
- numeric outputs grouped by allowed origin;
- coverage proof matching every emitted numeric schema/artifact field to exactly
  one typed origin envelope;
- adversarial tests proving an agent-supplied number cannot affect selection,
  extraction, staging, ranking, evaluation, trusted eligibility, or promotion;
- reviewer confirmation that explanations and evidence spans accompany every
  semantic category.

The merge gate fails if a PR introduces a self-score, invokes an unregistered
model-output schema, accepts a numeric judgment through an alias or metadata
dictionary, leaves an emitted numeric field outside the complete origin
inventory, adds an unanchored/composite ordinal agent category, omits required
origin-specific provenance, or uses a judge agent's output as expert gold.

Test success without live behavioral evidence is not sufficient for PRs that
change semantic decisions.

## PR 1: Freeze The Failure Corpus And Measurement Contract

Branch: `alvaro/evidence-semantic-pr1-failure-corpus`

Purpose: Preserve the observed failures before changing selection behavior.

Likely files:

- `scripts/validation/evidence_selection/fixtures/`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_benchmarks.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_candidate_screening.py`
- `docs/validation/reports/`

Implementation:

- Add an offline semantic-selection fixture covering the EGFR, BRCA1, and CFTR
  failures.
- Store PubMed identifiers, titles, paraphrased evidence fields, case criteria,
  expected select/reject/abstain labels, and fixture provenance.
- Label paraphrased records as mechanics/decision-regression evidence. They
  cannot prove literal grounding, source-measurement extraction, or production
  semantic quality because the paraphrase may encode the expected conclusion.
- Include the initial over-filtered EGFR canary.
- Add explicit regression labels for:
  - AURA3 and primary AZD9291 evidence must be selectable.
  - EGFR/afatinib reviews must not satisfy a primary-study request.
  - BRCA-negative PALB2/CHEK2, ATM, RECQL, and thymoma records must not satisfy
    a BRCA1-risk request.
  - F508del randomized and extension studies must be selectable.
  - systematic reviews and no-F508del populations must not satisfy the CFTR
    primary-study request.
  - `Non-human study` must not become a global ban on `study`.
- Add a scorer that reports TP, FP, FN, precision, end-to-end recall,
  abstention rate, and invalid-agent rate without treating abstention as a
  correct selection.
- Mark this corpus `ai_adjudicated_diagnostic`; do not label it expert gold.
- Keep frozen predictions categorical. Numeric baseline metrics must be derived
  by the scorer and never copied from an agent response.

Acceptance:

- The current selector reproduces the baseline failure or worse on the frozen
  corpus.
- Fixture validation rejects duplicate IDs, missing labels, or ambiguous
  provenance.
- Reports distinguish micro, macro, and per-case metrics.
- Reports identify every number as a computed metric and preserve the exact
  categorical decisions used to derive it.
- PR 1 is not used as the sole live quality gate or as literal-grounding proof.
- `make artana-evidence-api-service-checks` passes.

Non-goal: Improve production behavior.

## PR 3 (Next): Enforce The Framework-Wide Categorical Boundary

Branch: `alvaro/evidence-semantic-pr3-schema-registry`

Base: merged PR 2 (`#141`)

Purpose: Apply the categorical-output rule across every model boundary, add CI
enforcement, and quarantine existing numeric-judgment debt without changing the
merged selector's semantic policy.

Likely files:

- `services/artana_evidence_api/agent_contracts.py`
- `services/artana_evidence_api/runtime/` registry and guarded-adapter modules
- `services/artana_evidence_api/runtime_support.py`
- registered model-output and category manifests
- numeric-origin inventory and numeric-judgment debt manifest
- repository-level registry, boundary, and CI-routing tests
- `scripts/ci/plan_service_checks.py`
- `Makefile`

Implementation:

- Add a repository-level schema guard that rejects agent-authored numeric
  judgment fields, including aliases nested in metadata or generic payloads.
- Register every model-output schema, prompt, producer, and agent-authored enum;
  reject unregistered schemas and arbitrary numeric scalar dictionaries.
- Give every registered category an observable definition, evidence/locator
  requirements, positive example, counterexample, and invalid/unknown behavior.
- Inventory every numeric field in registered schemas and emitted artifacts.
  Require exactly one of the six allowed origins and its complete typed
  provenance envelope.
- Add origin-specific numeric envelope contracts rather than one generic score
  wrapper.
- Inventory current `confidence_score`, evidence `relevance`, subjective quality
  score, and equivalent agent-output fields in a versioned debt manifest. Assign
  each remaining violation a stable ID and owner PR; fail if any new or
  replacement ID appears, even when the total count is unchanged.
- Route production model execution through the registered guarded adapter. Add
  an AST/boundary check against direct model-client calls, authoritative
  unstructured output, and prose parsed into decision fields.
- Quarantine every retained debt field from selection, extraction, staging,
  ranking, evaluation, trusted eligibility, and promotion. Record consumers and
  the owning removal PR rather than hiding compatibility debt.
- Retrospectively scan the merged PR 1 and PR 2 schemas and artifacts.
- Add the fast registry/debt/origin/boundary gate to service-check planning and
  path-routing tests so relevant non-doc changes cannot skip it.

Adversarial tests:

- numeric confidence/relevance hidden in nested metadata or rationale
- prompt attempts to demand a probability or percentage
- unregistered dynamically generated output schema
- arbitrary numeric value hidden in a generic scalar or metadata dictionary
- ordinal confidence laundered as an unanchored category
- one debt ID replaced by a differently named violation
- source measurement missing its literal span, unit, or source hash
- deterministic policy number missing its categorical inputs or vetoes
- retrieval score relabeled as semantic confidence
- direct model-client invocation outside the guarded adapter
- numeric self-score injected at each production model boundary
- explanation text changed while categories remain fixed

Acceptance:

- Every production model-output schema and agent-authored category is present in
  the machine-readable registry.
- Every numeric schema/artifact field has exactly one allowed origin and the
  origin's complete typed provenance envelope, or one stable quarantined debt
  ID with an owning removal PR.
- The CI guard fails when a test-only agent schema adds a judgment float and
  passes for allowed source measurements and computed metrics.
- The category guard fails for an unanchored ordinal enum and passes only after
  every value has observable definitions, evidence requirements, examples, and
  counterexamples.
- A fast database-free registry/debt/origin guard runs for every non-doc PR and
  for changes to registered prompts, schema factories, manifests, and the guard
  itself, including targeted-test-only PRs. CI path-routing tests prove this.
- No production model call bypasses the guarded adapter; a deliberately direct
  test call fails the boundary check.
- Taint tests prove agent-authored numbers cannot influence selection,
  extraction, staging, ranking, evaluation, trusted eligibility, or promotion.
- The merged PR 2 selector retains precision and recall of at least `0.80`, with
  semantic fallback `0` and invalid-agent selections `0`.
- Focused tests, type checks, boundary checks, and adversarial review pass.

Non-goal: Change the merged semantic selector's decision policy or remove every
legacy debt field. PR 3 must quarantine debt and assign each removal to its
owning migration PR.

## PR 2 (Merged As GitHub PR 141): Make Agent Findings Authoritative

Branch: `alvaro/evidence-semantic-pr2-agent-selector`

Base: PR 1

Purpose: Replace lexical semantic selection with agent-authored atomic findings
and one deterministic authoritative decision policy over those findings.

Likely files:

- `services/artana_evidence_api/evidence_selection_runtime.py`
- `services/artana_evidence_api/evidence_selection_candidate_screening.py`
- `services/artana_evidence_api/evidence_selection_result_serialization.py`
- `services/artana_evidence_api/dependencies.py`
- `services/artana_evidence_api/worker.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_router.py`

Implementation:

- Split candidate processing into two responsibilities:
  - deterministic eligibility: schema validity, durable identity, deduplication,
    source policy, budget, and already-captured checks;
  - semantic findings: agent-owned criterion categories, spans, and explanation;
  - authoritative decision: a versioned deterministic policy validates the
    agent's recommendation and derives select/reject/abstain from the complete
    findings.
- For `planner_mode=model`, require the semantic judgment agent after retrieval.
- Remove `_decision_for_record` token overlap as an authoritative decision in
  the model path.
- Preserve an explicitly named deterministic mode only for offline mechanics
  fixtures or caller-supplied deterministic slices; never report it as an agent
  run.
- Fail closed when the semantic agent is unavailable. Do not call the old
  semantic selector as fallback.
- Batch candidates within configured limits and preserve stable candidate IDs.
- Serialize each criterion finding, evidence citation, categorical judgment,
  abstention, model ID, prompt version, agent invocation, and fallback status.
- Derive any operational ranking weight after validation using the versioned
  policy; serialize its `deterministic_policy` origin and policy version
  separately from the agent payload.
- Ensure shadow mode records selected candidates without creating graph writes.
- Add cache keys that include record hash, objective/criteria hash, model ID,
  prompt version, and relevant policy version.

Required regressions:

- model agent unavailable -> 503 before queueing or typed failed run
- model timeout -> no selected result
- invalid model result -> no selected result
- deterministic mode cannot set `agent_invoked=true`
- model mode cannot set a non-null semantic fallback result
- duplicate PubMed records remain deterministic deduplication failures
- all frozen PR 1 cases flow through the semantic agent boundary
- all source-locked cases prove literal-span grounding
- an agent response containing numeric confidence or relevance is invalid and
  cannot select, rank, or promote a candidate
- every legacy numeric field in the selection path is ignored or rejected before
  semantic decision, ordering, staging, or serialization
- modifying an explanation without changing categories cannot silently change
  a derived score

Acceptance:

- Telemetry proves the agent supplied the semantic findings for every eligible
  model-path candidate and that the registered deterministic policy derived
  every authoritative decision. The recommendation is never consumed directly.
- Fallback semantic decision count is `0`.
- Invalid-agent selection count is `0`.
- Source-locked diagnostic precision and recall each reach at least `0.80`; the
  PR 1 paraphrase corpus remains a regression/advisory view.
- No per-case precision or recall is below `0.70`.
- Evidence API service checks and a three-case live diagnostic pass.
- No new debt ID appears; selection-path numeric influence and debt are `0`.

Delivered evidence in GitHub PR `#141`:

- diagnostic precision `1.0000`, recall `0.9231`, and coverage `0.9333`;
- two explicit abstentions, invalid-agent selections `0`, and semantic
  fallbacks `0`;
- prompt-injection canary passed;
- required checks passed and all review threads were resolved before merge.

Stop condition: If two implementation iterations cannot reach the threshold,
do not tune thresholds. Review the decision contract, input evidence, and model
capability before continuing.

## PR 4: Align Shadow-Study And Ranking-Gate Contracts

Branch: `alvaro/evidence-semantic-pr4-shadow-gate-contract`

Base: PR 3. Design may proceed in parallel, but PR 4 must rebase onto the merged
PR 3 registry and guard before review or merge.

Purpose: Ensure the evaluation gate measures artifacts the shadow path can
actually produce.

Likely files:

- `scripts/build_evidence_selection_shadow_review_packet.py`
- `services/artana_evidence_api/evidence_selection/shadow_review_packet.py`
- `services/artana_evidence_api/evidence_selection_validation.py`
- `scripts/run_evidence_selection_expert_study_gate.py`
- `services/artana_evidence_api/evidence_selection/shadow_review_study_batch.py`
- corresponding unit and CLI tests

Implementation:

- Separate two explicit study types:
  - selection relevance study: evaluates selected, rejected, and abstained
    source candidates;
  - downstream review-ranking study: evaluates real proposals and review items
    after extraction/staging.
- A selection-only shadow result must not require `review_item` decisions it
  cannot generate.
- A downstream ranking readiness claim must still require every configured
  source kind and positive/negative outcomes.
- Replace every bare study `ranking_score` with an origin-specific envelope that
  includes producer artifact path/hash, allowed origin, algorithm/policy ID and
  version, and categorical input envelope when the origin is
  `deterministic_policy`.
- Add `ai_reviewer_simulation` as an explicit non-production evidence kind.
- Prevent AI-completed packets from being serialized as `real_shadow_review`.
- Replace subjective explanation-quality integers with atomic findings such as
  `literal_citation_present=yes|no`, `citation_entails_claim=yes|no|unclear`,
  `all_required_criteria_addressed=yes|no`, and
  `unsupported_material_claim_present=yes|no`. Preserve cited spans and reviewer
  explanations; derive any composite explanation-quality category
  deterministically from these findings.
- Require AI reviewer simulations to emit categorical outcomes and cited spans;
  they cannot author ranking scores or grade their own explanations.
- Compute aggregate explanation-quality distributions, agreement, precision,
  and recall deterministically from categorical review decisions.
- Report two aggregate views:
  - raw all-entry diagnostic metrics;
  - passed-entry production metrics.
- Preserve all existing provenance, signatures, collision protection, immutable
  thresholds, and fail-closed publication behavior.

Acceptance:

- A valid selection-only shadow study can pass or fail solely on selection
  criteria without a fabricated `review_item` requirement.
- A downstream ranking study still fails without required source kinds.
- AI simulation can never support production readiness.
- Failed batches show real raw metrics instead of replacing them with zeros.
- No review packet accepts agent-authored numeric quality, confidence,
  relevance, priority, or readiness values.
- No study packet accepts a bare number or an unregistered producer; score
  provenance is complete before PR 5 changes the ranking policy.
- Existing PR 137/138 security and provenance regressions remain green.

Non-goal: Relax quality thresholds.

## PR 5: Derive Ranking Deterministically And Calibrate The Policy

Branch: `alvaro/evidence-semantic-pr5-ranking-calibration`

Base: PR 3 and PR 4

Purpose: Remove model-authored scores from ranking and calibrate only the
versioned deterministic mapping from categorical judgments to outcomes.

Likely files:

- `services/artana_evidence_api/evidence_selection/semantic_judgment.py`
- `services/artana_evidence_api/evidence_selection_result_serialization.py`
- `services/artana_evidence_api/evidence_selection_validation.py`
- `services/artana_evidence_api/ranking.py`
- calibration tests and report scripts

Implementation:

- Delete or quarantine raw model confidence and numeric relevance from the
  evaluation and ranking inputs. Do not preserve them as advisory signals.
- Define separate fields for categorical agent judgment, deterministic
  operational ranking weight, and an optional calibrated probability. Do not
  overload one `ranking_score`.
- Require every ranking weight to include `score_origin=deterministic_policy`,
  policy ID, policy version, and the categorical input envelope.
- Keep calibrated probability unavailable until the exact deterministic policy
  has enough independent adjudicated training samples plus a disjoint held-out
  evaluation partition. PR 5 implements the fitter and validation machinery but
  leaves production calibration unavailable; PR 7 supplies predeclared expert
  partitions. Its numeric origin is `calibration_model`, with the complete
  calibration envelope defined above.
- Add abstention-aware calibration metrics and reliability bins.
- Version calibration artifacts by model, prompt, objective schema, and corpus.
- Also version by categorical schema and deterministic scoring policy.
- Reject stale calibration when any versioned dependency changes.
- Add saturation, monotonicity, non-finite, and adversarial distribution tests.
- Do not fit or approve production calibration from the three-case AI corpus.
- Retain retrieval-algorithm similarity separately with
  `score_origin=retrieval_algorithm`; never relabel it as semantic confidence.
- Retrieval scores may acquire candidates and order pre-judgment retrieval work,
  but cannot enter semantic select/reject, post-judgment ranking, trusted
  eligibility, or promotion policy. Multi-origin scores are forbidden; each
  displayed number retains its own envelope.

Acceptance:

- An agent cannot emit or override any numeric rank, probability, or confidence.
- A deterministic weight of `1.0` cannot arise merely from lexical overlap.
- No retrieval or lexical score of any value influences semantic outcome or
  post-judgment priority.
- Missing calibration is explicit and blocks a production ranking claim.
- On the frozen diagnostic, ECE is reported honestly and does not use labels as
  an input to the score being evaluated.
- Adoption of a calibration model requires predeclared, research-question-level
  disjoint training and held-out sets with frozen hashes.
- Calibration predicts adjudicated categorical outcomes from pre-gold
  deterministic weights; it never rebuilds a score from gold labels or
  post-hoc verifier results.

## PR 6: Repeatability And Model A/B Proof

Branch: `alvaro/evidence-semantic-pr6-live-repeatability`

Base: PR 3, PR 4, and PR 5

Purpose: Prove the new selector works repeatedly and determine whether a
stronger model adds value.

Implementation:

- Run the source-locked three-case diagnostic three times with the default
  model; run the PR 1 paraphrase corpus as a separate advisory regression.
- Run the same nine-case matrix with one stronger candidate model.
- Use identical source records when comparing semantic judgment models so query
  variance does not hide selection variance.
- Also run an end-to-end comparison with fresh searches as an advisory test.
- Record worst-run, mean, and variance for precision, recall, abstention,
  invalid-agent rate, latency, cost, and calibration.
- Compare categorical decision distributions and criterion-level disagreement;
  do not ask either model for numeric confidence or use self-scores in model
  selection.
- Require zero semantic fallback and zero invalid-agent selections.
- Publish immutable artifacts and hashes.

Model adoption gate:

- worst-run precision `>= 0.80`
- worst-run recall `>= 0.80`
- no case below `0.70` precision or recall
- invalid-agent selection count `0`
- semantic fallback count `0`
- no provenance or integrity failures
- stronger model adopted only if it materially improves worst-run quality or
  reduces variance enough to justify cost and latency
- model adoption uses deterministically computed outcome metrics, not either
  model's stated certainty

Stop condition: If neither model passes, return to PR 2/3 design. Do not proceed
to human study by weakening thresholds.

## PR 7: Independent Expert Pilot

Branch: `alvaro/evidence-semantic-pr7-expert-pilot`

Base: PR 6

Purpose: Replace AI diagnostic labels with credible independent evidence.

Study design:

- at least 20 distinct research questions and 200 candidate records when a
  calibrated probability is part of the readiness claim
- predeclare at least 12 calibration-training questions and 8 final held-out
  evaluation questions; partition by research question, never by record
- freeze and hash both partitions before first-pass review; no question, record,
  reviewer decision, or derived feature may cross partitions
- if these sample requirements are not met, calibrated probability remains
  unavailable and ECE remains advisory rather than blocking readiness
- at least two qualified independent reviewers per case
- reviewers blinded to model score and harness decision during first-pass label
- explicit inclusion/exclusion rubric established before review
- reviewers use anchored categorical dimensions and explanations rather than
  subjective numeric relevance, confidence, or explanation-quality ratings
- disagreement adjudicated by a third reviewer or documented consensus process
- inter-rater agreement reported before adjudication
- agreement and all aggregate study metrics are computed deterministically from
  the categorical labels
- no reviewer is the implementation agent

Acceptance:

- adjudicated precision `>= 0.80`
- adjudicated recall `>= 0.80`
- no high-severity overclaims
- acceptable agreement target defined before collection and met
- production ranking ECE `<= 0.05` only on a held-out expert set
- calibration is fit only on the predeclared training partition and evaluated
  once on the untouched held-out partition; tuning after held-out access creates
  a new model version and requires a new held-out set
- every artifact passes provenance and signature gates
- no reviewer or evaluator-agent numeric judgment enters the gold label or
  promotion decision

This PR may update evidence reports and thresholds justified by the predeclared
study protocol. It must not tune the selector on the held-out evaluation set.

## PR 8A: Migrate Extraction To Categorical Findings

Branch: `alvaro/evidence-semantic-pr8a-categorical-extraction`

Base: PR 7

Purpose: Remove model-authored numeric judgment from document/variant extraction
before attempting trusted-relation proof.

Implementation:

- Replace extraction-level confidence fields and generic numeric scalar
  judgments with registered atomic categories, literal spans, source
  measurements in typed envelopes, and explanations.
- Separate copied scientific numbers from semantic judgments; require locator,
  span, field, unit, extraction method, and source hash for every copied number.
- Remove numeric-to-category adapters from extraction and reject unregistered
  dynamic schemas or arbitrary scalar dictionaries.
- Derive any extraction priority or compatibility weight through a versioned
  deterministic policy after categorical validation.
- Migrate compatibility consumers before removing the owned debt IDs. After PR
  8A, compatibility serializers contain no legacy bare judgment number; they may
  expose categorical fields or allowed numeric values only through complete
  origin-specific envelopes. If a consumer still requires the legacy number,
  PR 8A cannot claim debt removal or merge.

Acceptance:

- extraction agent-authored numeric judgment debt IDs are removed
- source measurements pass typed provenance validation
- unsupported, ambiguous, and missing-span findings abstain or route to review
- taint tests prove legacy numbers cannot affect candidate omission, extraction
  output, proposal creation, or staging
- focused, service, boundary, registry, and adversarial gates pass

## PR 8B: Migrate Relation, Linking, And Entailment Findings

Branch: `alvaro/evidence-semantic-pr8b-categorical-relations`

Base: PR 8A

Purpose: Remove model-authored numeric judgment from relation normalization,
entity linking, entailment, specificity, and promotion inputs.

Implementation:

- Require relation, entailment, entity-link, specificity, and evidence-strength
  agents to emit registered atomic categories, cited spans, and explanations.
- Remove remaining relation/link numeric-judgment schemas and legacy
  numeric-to-category adapters.
- Derive relation ordering, review priority, and eligibility from versioned
  deterministic policies. Hard safety failures are categorical vetoes, not low
  numeric penalties.
- Keep raw unknown entities and relation types out of trusted promotion.

Acceptance:

- relation/link/entailment agent-authored numeric judgment debt IDs are removed
- wrong verified CURIE links, fallback trusted relations, invalid-agent trusted
  relations, and negative/weak-evidence leakage remain `0`
- taint tests prove no legacy number affects normalization, linking, entailment,
  specificity, trusted eligibility, staging order, or promotion
- focused, service, graph-boundary, registry, and adversarial gates pass

## PR 9: End-To-End Trusted Relation Proof

Branch: `alvaro/evidence-semantic-pr9-trusted-relation-proof`

Base: PR 8B

Purpose: Prove that better source selection and already-categorical extraction
create valuable, specific graph relations rather than merely relevant papers.

Implementation:

- Carry expert-approved records through document creation, categorical agent
  extraction, relation normalization, CURIE linking, sentence anchoring,
  entailment checks, proposal staging, and human promotion.
- Track source-selection errors separately from extraction, linking, relation
  type, qualifier, and promotion-policy errors.
- Require each trusted relation to include a direct supporting span containing
  or normalization-linking both arguments.
- Require canonical relation type or explicit human-reviewed exception.
- Produce a graph-readiness report over the expert pilot set.

Acceptance:

- trusted-tier precision `1.00`
- trusted high-value recall meets the existing readiness threshold
- wrong verified CURIE links `0`
- fallback trusted relations `0`
- invalid-agent trusted relations `0`
- negative and weak-evidence leakage `0`
- generic relation used when a supported specific sibling exists `0`
- every trusted relation has provenance, sentence anchor, both arguments,
  entailment status, categorical inputs, deterministic policy version, and
  promotion audit trail
- end-to-end taint tests prove no model-authored number influenced extraction,
  candidate omission, proposal creation, staging order, relation normalization,
  trusted eligibility, or promotion

Only PR 9 can recommend enabling a narrowly scoped auto-promotion policy. The
default remains human promotion.

## PR-By-PR Categorical Conformance Matrix

| PR | Agent emits | Deterministic code computes | Forbidden in this PR | Merge evidence |
| --- | --- | --- | --- | --- |
| 1 | Frozen `select/reject/abstain/invalid` decisions and reasons | TP, FP, FN, TN, precision, end-to-end recall, coverage | Agent-written baseline metrics | Prediction artifact plus reproducible report; PR 3 retrospective registry scan |
| 2 | Live atomic candidate findings, spans, explanations, recommendation | Authoritative decision, candidate order, outcome metrics, runtime counters | Direct use of recommendation, agent rank overrides, numeric fallback | Live trace proving finding authority, policy recomputation, and fallback `0` |
| 3 | Operationally anchored categories, evidence spans, explanations, abstention reason | Registry validation, origin coverage, debt diff, deterministic policy outputs | Confidence, disguised ordinal confidence, probability, relevance score, hidden numeric metadata | Mandatory schema registry, exact-ID debt manifest, source-locked corpus, adversarial contract tests |
| 4 | Reviewer categories, decisions, cited findings, notes | Agreement, precision, recall, category distributions | Explanation-quality integer or AI readiness score | Completed packet plus provenance-class checks |
| 5 | No new agent judgment; consumes validated categories | Versioned ranking weight, calibration, ECE, reliability bins | Raw model confidence or gold-derived score | Mapping artifact, held-out protocol, score-origin audit |
| 6 | Repeated categorical judgments from each model | Worst, mean, variance, disagreement, cost, latency | Model self-score used for adoption | Immutable repeated-run matrix |
| 7 | Expert categorical labels, spans, explanations | Agreement and adjudicated outcome metrics | Numeric reviewer confidence or implementation-agent gold | Blinded protocol and adjudicated expert artifacts |
| 8A | Extraction categories, copied measurements with spans, explanations | Extraction priority and compatibility weights | Extraction confidence, generic numeric scalars, numeric-to-category adapters | Debt-ID removal, measurement provenance, taint tests |
| 8B | Relation/link/entailment atomic categories with supporting spans | Relation order, review priority, eligibility vetoes | Relation/link confidence or legacy numeric influence | Debt-ID removal, graph-boundary and taint tests |
| 9 | No new scoring judgment; consumes the categorical pipeline | Trusted eligibility, promotion vetoes, graph-readiness metrics | Any model-authored number in the end-to-end path | Expert-set audit trail with all policy versions |

For every row, the PR author must attach a machine-readable numeric-origin
inventory generated by comparing all registered schemas and emitted artifacts,
not by sampling. CI fails when any numeric field lacks exactly one typed origin
envelope or when any registered model-output schema is absent from the scan.
Adversarial reviewers must trace every numeric report field to its complete
input artifacts and algorithm/policy, inject numeric self-scores through each
changed agent boundary, and test known legacy debt IDs for decision influence.
The complete coverage report and injection results are merge evidence.

## Dependency And Parallelization

```text
PR 1 Failure corpus --> PR 2 Runtime selector --> PR 3 Registry + CI guard
                                                   |--> PR 4 Study contract
                                                   |          |
                                                   v          v
                                                   PR 5 Calibration
                                                          |
                                                          v
                                                     PR 6 Live A/B
                                                          |
                                                          v
                                                     PR 7 Expert pilot
                                                          |
                                                          v
                                                PR 8A Extraction migration
                                                          |
                                                          v
                                             PR 8B Relation/link migration
                                                          |
                                                          v
                                                  PR 9 Trusted proof
```

Recommended lanes:

- Lane A: PR 1, PR 2, PR 3
- Lane B: PR 4 development may start after PR 1, but review and merge require
  PR 3 plus a rebase onto its registry and CI guard
- Lane C: prepare PR 6 automation while PR 3-5 are under review, without
  generating readiness claims before their merge
- Lane D: inventory and design PR 8A/8B while PR 6/7 run; implementation and
  merge follow PR 7 so expert artifacts exercise the categorical migrations

PR 5 must integrate the final PR 3 decision fields and PR 4 study contracts.
PR 6 must run from the integrated mainline, not from independently green branch
results. PR 9 cannot begin until PR 8A and PR 8B remove their owned debt IDs.

## Progress Scorecard

Update this table from merge-visible artifacts after every PR.

| Metric | Baseline | Merged PR 2 | PR 3 target | PR 6 target | PR 7 target | PR 9 target |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Selection precision | 0.2381 | 1.0000 diagnostic | preserve >=0.80 | worst >=0.80 | >=0.80 | tracked |
| Selection recall | 0.3846 | 0.9231 diagnostic | preserve >=0.80 | worst >=0.80 | >=0.80 | tracked |
| Selection coverage | not measured | 0.9333 diagnostic | preserve/measured | stable | measured | measured |
| Semantic fallback count | deterministic selector authoritative | 0 | 0 | 0 | 0 | 0 |
| Invalid-agent selections | not measured | 0 | 0 | 0 | 0 | 0 |
| Agent-authored numeric judgments in evaluated path | inventory required | selector rejects them | 0 unquarantined | 0 | 0 | 0 |
| Numeric outputs with allowed origin and version | partial | selector-local | 100% registry coverage | 100% | 100% | 100% |
| Abstention count/rate | not measured | 2 / measured | measured | stable | measured | measured |
| Ranking ECE | 0.6000-1.0000 across three cases | not a readiness claim | advisory | honest/held-out | <=0.05 | tracked |
| Independent expert cases | 0 | 0 | 0 | 0 | >=10 questions | expert pilot set |
| Trusted relation precision | not established | not claimed | not claimed | not claimed | not claimed | 1.00 |

## Program Stop Rules

Stop implementation and reassess when any of these occurs:

- two consecutive PR iterations improve test infrastructure but not frozen live
  diagnostic quality;
- a proposed fix weakens provenance, signatures, or production thresholds;
- deterministic semantic fallback reappears under another name;
- AI simulation is presented as independent human evidence;
- an agent-authored number influences selection, ranking, quality evaluation,
  extraction, candidate omission, proposal creation, staging, calibration,
  trusted eligibility, or promotion;
- a numeric field lacks exactly one allowed origin and that origin's complete
  typed provenance envelope;
- a PR adds, substitutes, or leaves unquarantined a numeric-judgment debt ID, or
  bypasses the registry/origin CI guard;
- the stronger model changes cost without improving worst-run quality;
- source selection improves but end-to-end relation quality does not.

The program is complete only when independent experts validate source selection
and the approved sources produce specific, fully grounded trusted relations.
