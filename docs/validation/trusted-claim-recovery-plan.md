# Trusted Claim Recovery Plan

Created: 2026-07-14

Status: TG-01 through TG-03 are merged. TG-04 now has durable n-ary fixtures,
typed source binding, bounded completeness replay, and finite source-unit
diagnostics through V11. V11 preserved the source meaning but failed workflow
qualification because normalized event identity was not schema-required. V12
is pre-registered on one fresh BioNLP unit with schema-required event identity,
four source-complete acceptable representations, three-agent falsification,
and crash-safe create-once custody. Its live call remains paused until the
final adversarial and repository gates pass. Graph persistence remains paused.

Baseline commit: `884ede20340d7fce7b28994f1bed617b222d2213`

Baseline evaluation:
`docs/validation/reports/2026-07-14-luna-agent-expert-baseline.md`

This is the canonical implementation and progress plan after the July 14 Luna
agent-expert evaluation. It replaces the earlier open-ended trusted-graph
roadmaps as the source of truth for new work. Older plans remain historical
evidence and must not be used to claim current readiness.

## Objective

Move Artana from a useful relation-candidate generator to a system that creates
traceable, qualified, independently verified biomedical claims and only then
projects safe claims into graph relations.

The target flow is:

```text
source document
  -> immutable source identity and exact evidence locator
  -> agent-extracted role-typed clinical assertion
  -> one or more candidate ClaimFrames, or explicit ambiguity
  -> independent agent semantic verification
  -> authoritative entity verification
  -> persisted claim and evidence ledger
  -> deterministic, fail-closed projection decision
  -> optional graph relation
```

The claim ledger is the scientific record. A graph edge is a derived view. A
lossy edge must never replace the qualified claim from which it was derived.

## Honest Finish Lines

This plan distinguishes two finish lines so that agent evaluation is not
misrepresented as human-expert proof:

1. **Agent-verified technical readiness:** source-local claims are traceable,
   qualified, independently agent-verified, authoritatively grounded, stable,
   and protected by fail-closed graph rules. This plan can reach this level.
2. **Human-expert trusted readiness:** independently authenticated biomedical
   experts validate a frozen real-source study. This remains blocked until
   human reviewers are available.

Until product governance explicitly defines otherwise, agent-generated claims
must be capped at `verified_evidence`; they must not be described as
human-validated or clinical truth. The implementation may make the graph
technically ready for trusted promotion without enabling that promotion.

## July 14 Baseline

The following numbers are historical diagnostic counts. The original raw
July 14 bundle is not committed, so they are not independently evaluable and
must not receive current merge credit. The 47-case set was risk-enriched, so
its counts diagnose possible failures and do not estimate whole-corpus
prevalence.

| Measure | Baseline | Interpretation |
|---|---:|---|
| Strict agent completion | 300/300 | Reported completion; must be re-established from committed provider evidence. |
| Credited fallback | 0 | Reported fallback count; not a current safety proof. |
| Invalid agent results | 0 | Reported structured-output count; not independently reproducible. |
| Stable cases across three runs | 88/100 | Suggests a repeatability failure requiring a frozen rerun. |
| Worst-run generic relation rate | 36.76% | Suggests generic output substantially exceeded the planned 5% limit. |
| Worst-run verified CURIE match rate | 75.86% | Suggests entity grounding was below the planned 95% target. |
| Negative-control leakage | 1 | Suggests at least one positive candidate escaped a negative control. |
| Source-reviewed packet sufficiency | 8/47 | Suggests most risk packets lacked self-contained support. |
| Final action `keep` | 1/47 | Suggests most risk cases required revision, rejection, or human routing. |
| Strong provenance | 2/47 | Suggests source identity and locators were usually missing. |
| Generic or overstated outcomes | 13/47 | Suggests binary tuples lost scientifically material context. |

Current decision: **not ready for automatic trusted-graph promotion**.

## Research-Backed Quality Strategy

The implementation strategy for TG-03 through TG-08 is defined in
`docs/validation/reports/2026-07-15-trusted-claim-quality-improvement-research.md`.
Its core conclusion is that unconstrained zero-shot triplet generation is not a
sufficient architecture for trusted biomedical claims.

The remaining PRs therefore use one shared product-quality method:

1. Luna inventories source-local events and classifies typed argument roles
   before proposing one or more frames or explicitly preserving ambiguity.
2. Authoritative biomedical tools supply typed entity candidates, but never
   satisfy semantic trust or receive agent credit.
3. Luna selects a candidate or abstains and emits only closed categories,
   source spans, explanations, and falsification notes.
4. A separate Luna call verifies the complete frame against the cited source
   without extractor rationale or external facts.
5. Deterministic code verifies authority records and computes every numeric
   metric from frozen categorical outputs.
6. Novel findings and hypotheses remain first-class claims in separate
   epistemic lanes; lack of corroboration does not delete them.

Every semantic change is evaluated by paired case transitions on inputs that
were untouched when the experiment was predeclared, not only by aggregate
percentages. A set used to design an intervention becomes a development and
regression set and cannot provide confirmatory merge credit for that
intervention. Paired improvements must exceed
paired regressions, three-run worst-case metrics must improve or meet their
gate, and no safety invariant may regress. Two consecutive product experiments
without a positive paired net change trigger a model/task-ablation review
instead of another prompt-edit loop.

## Scientific Improvement Measurement Protocol

Scientific improvement means that Artana recovers more complete and useful
source-supported claims without creating more unsupported, generic, reversed,
or overconfident claims. Producing more candidates, preserving more JSON
fields, passing more unit tests, or receiving a favorable agent opinion is not
scientific improvement by itself.

### Frozen evaluation design

Before a semantic experiment starts, freeze and hash:

- an untouched confirmatory panel of complete biomedical events;
- source snapshots and exact evidence regions;
- categorical gold labels for event type, trigger, polarity, epistemic status,
  typed participant roles, material qualifiers, and acceptable graph
  projections;
- a categorical `valuable` or `not_valuable` label with an expert-derived
  reason describing the decision or scientific question the claim informs;
- model identifiers, prompts, tool permissions, decoding settings, and run
  count;
- the deterministic scorer version and every matching rule.

The panel must include positive, negative, null, uncertain, hypothesis,
multi-event, multi-sentence, long-context, and novel-but-uncorroborated cases.
Labels come from independent expert-curated corpora or authenticated human
review, never from the implementation under test. A case inspected while
designing a change immediately becomes development data and cannot provide
confirmatory credit for that change.

Agents may browse authoritative sources when the protocol permits it, but they
return categorical findings, exact spans, explanations, and falsification
notes. They never author precision, recall, confidence, importance, or
readiness numbers. External corroboration is recorded separately and cannot
convert a source-local `insufficient` finding into `entailed`.

### Deterministic metrics

The scorer computes each metric from the frozen labels and immutable agent
artifacts. No weighted overall score is used because an average could hide a
safety failure.

| Measure | Deterministic definition | Scientific question |
|---|---|---|
| Whole-claim precision | exact supported claims / all emitted positive claims | When Artana asserts a complete claim, how often is it right? |
| Whole-claim recall | recovered exact supported claims / all eligible gold claims | How much supported knowledge does Artana recover? |
| Valuable-claim recall | recovered exact `valuable` claims / all eligible gold `valuable` claims | Does it recover claims that inform a real scientific decision? |
| Typed-role fidelity | correctly matched required role and span pairs / all required gold role and span pairs | Did it preserve who or what played each scientific role? |
| Polarity and direction fidelity | exact polarity and direction matches / all emitted matched claims | Did it preserve positive, negative, null, and directional meaning? |
| Unsupported projection rate | positive graph projections outside the frozen acceptable set / all positive projections | Did claim-to-edge conversion invent meaning? |
| Generic projection rate | projections labeled broader than their source claim / all projections | Did the graph discard material context? |
| Negative/null leakage | positive claims emitted for frozen negative or null controls | Does the system create false positive knowledge? |
| Abstention error | eligible gold claims incorrectly abstained / all eligible gold claims | Is fail-closed behavior becoming uselessly conservative? |
| Canonical repeatability | cases with identical categorical semantics in all three runs / all cases | Does the same evidence produce the same meaning? |

A whole claim is an exact match only when event type, polarity, every required
typed participant, material qualifier, and source support agree. Partial
matches are reported diagnostically but never counted as a true positive.
Novel hypotheses are evaluated in their own epistemic lane: correctly
preserved hypotheses earn recovery credit, while projecting them as established
positive relations counts as leakage.

### Paired experiment and gates

Run the current approach and the proposed approach on the same untouched panel
three times. Report every case as `improved`, `unchanged_correct`,
`unchanged_incorrect`, or `regressed`, with the exact categorical difference.
The worst run, not the average run, controls the gate.

Provisional agent-readiness gates are:

- whole-claim precision at least `90%` in every run;
- valuable-claim recall at least `80%` in every run;
- typed-role fidelity and polarity/direction fidelity at least `95%`;
- unsupported and generic positive projection rates at most `5%`;
- negative/null positive leakage `0`;
- credited semantic fallback `0`, invalid agent output `0`, and unauthenticated
  provider output `0`;
- positive paired net change in every run, with no safety regression;
- canonical categorical repeatability at least `95%`.

These gates qualify a review-only agent lane. Automatic trusted promotion still
requires `100%` precision on its prospectively frozen promotion set and an
explicit governance decision. Agent results do not satisfy the human-expert
finish line.

### Task redesign decision

TG-04 tested the same frozen four cases after item-level binding and a strict
two-round completeness loop. Operational completion improved from `1/4` to
`3/4`, but the event-gold qualification case remained
`SEMANTICALLY_INCOMPLETE`, whole-event recall stayed `0/4`, and provider receipt
verification remained `0/27`. The measured result is recorded in
`docs/validation/reports/2026-07-17-tg04-bounded-convergence-pilot.md`.

The open-ended "find every claim" task is now stopped. Do not add another
recovery round, another completeness judge, or a stronger model to that task.
The next controlled experiment must first freeze a finite source-unit event
decision contract. Luna runs that frozen contract once. A predeclared stronger
model may be compared only afterward, against identical units, prompts, tools,
and scoring, so model strength is not confounded with task redesign.

If the finite task still produces no exact whole-event match, stop model-only
extraction and evaluate an expert-seeded or hybrid candidate workflow. Do not
start Graph persistence or add another evaluation layer around a zero-recall
result.

## Non-Negotiable Rules

These rules apply to every PR in this plan.

1. **Agent-first semantics:** biomedical extraction and semantic verification
   are performed by agents. Deterministic fallback may support triage but may
   never receive agent credit or satisfy a semantic trust gate.
2. **Categorical agent output:** agents return closed categories, exact evidence
   spans, explanations, and falsification notes. Agents do not author numeric
   confidence, relevance, precision, recall, calibration, or readiness scores.
3. **Deterministic metrics:** code computes all counts, rates, thresholds, and
   readiness decisions from frozen categorical artifacts.
4. **Source measurements stay source measurements:** an extracted effect size,
   p-value, threshold, dose, or date is allowed only when copied from an exact
   source span and labeled `source_measurement`; it is not model confidence.
5. **Two different questions:** source-local entailment asks whether the cited
   document supports the claim. External corroboration asks whether other
   authoritative sources agree. External research may not repair a packet that
   lacks source-local evidence.
6. **Novel knowledge is preserved:** uncorroborated but plausible findings stay
   as `HYPOTHESIS` or `UNCERTAIN` claims with provenance. They are routed for
   review, not discarded and not projected as established positive relations.
7. **Claim before edge:** null, negated, provisional, and hypothesis statements
   remain first-class claims. A warning flag on an assertive edge is not an
   acceptable substitute.
8. **Authoritative identifiers only:** symbolic placeholders such as
   `ClinVar:BRAF_V600E` cannot count as verified identifiers. Trust requires a
   namespace-specific authoritative record or computed identifier.
9. **Fail closed:** missing source, locator, verifier, authoritative entity,
   qualifier, polarity, or required service response blocks projection.
10. **No threshold weakening:** a PR may improve a metric or strengthen a safety
    invariant. It may not lower a threshold to manufacture green status.
11. **No circular validation:** fixture labels, local dictionaries, and the
    implementation under test cannot independently validate one another.
12. **No infrastructure-only loop:** no new harness work may start unless it is
    required to measure a product field introduced by the same or immediately
    preceding PR.
13. **Provider-authenticated live evidence:** a strict semantic run receives
    merge credit only when every executed OpenAI response can be retrieved by
    its provider response ID and its canonical provider-output hash matches the
    model-boundary record. Self-consistent local JSON is not execution proof.
14. **No contaminated-holdout credit:** the historical TG-03 v4/v2 holdout was
    inspected while designing inventory-first extraction. It remains useful for
    regression and runtime smoke tests, but it cannot independently prove that
    TG-03 improved product quality. Confirmatory agent-readiness requires a
    prospectively frozen external set whose labels and case selection were not
    derived from production outputs.

## Progress Tracking

GitHub assigns the final PR number when a branch is opened. Keep the stable
`TG-0x` identifier in commit messages, reports, and this tracker so the plan
does not need to be renumbered.

Allowed status values are `not_started`, `in_progress`, `evidence_pending`,
`ready_for_review`, `merged`, and `blocked`.

| Plan ID | GitHub PR | Suggested branch | Depends on | Status | Primary proof |
|---|---:|---|---|---|---|
| TG-01 | [#158](https://github.com/med13foundation/artana-evidence-platform/pull/158) | `alvaro/trusted-claims-tg01-truthful-safety` | None | merged | Existing unsafe evidence cannot become trusted. Evidence: `docs/validation/reports/2026-07-14-tg01-truthful-safety.md`. |
| TG-02 | [#159](https://github.com/med13foundation/artana-evidence-platform/pull/159) | `alvaro/trusted-claims-tg02-source-provenance` | TG-01 | merged | Every eligible claim has authoritative source identity and an exact locator. Evidence: `docs/validation/reports/2026-07-15-tg02-source-provenance.md`. |
| TG-03 | [#160](https://github.com/med13foundation/artana-evidence-platform/pull/160) | `alvaro/trusted-claims-tg03-claim-frame` | TG-02 | merged | Runtime and safety proof is complete: the strict Luna path completed with three provider-bound calls, fallback 0, graph writes 0, and both adversarial re-reviews clear. Scientific-quality proof failed on the first clean case with 0% endpoint/full-frame precision and recall, so the remaining 18 development cases were not run. This PR merged only as a truthful safety and architecture improvement. Evidence: `docs/validation/reports/2026-07-14-tg03-qualified-claim-frame.md`. |
| TG-04 | [#161](https://github.com/med13foundation/artana-evidence-platform/pull/161), [#162](https://github.com/med13foundation/artana-evidence-platform/pull/162)-[#167](https://github.com/med13foundation/artana-evidence-platform/pull/167) | `alvaro/trusted-claims-tg04-claim-persistence` | TG-03 | blocked | Typed n-ary fixtures, source binding, provider lineage, and bounded replay are durable. The bounded Luna pilot improved operational completion to `3/4`, but the gold case remained incomplete and whole-event recall was `0/4`. Open-ended completeness and Graph persistence are stopped pending a finite source-unit event task. Evidence: `docs/validation/reports/2026-07-17-tg04-bounded-convergence-pilot.md`. |
| TG-05 | TBD | `alvaro/trusted-claims-tg05-agent-verifier` | TG-04 | not_started | Independent agent verification replaces heuristic semantic trust. |
| TG-06 | TBD | `alvaro/trusted-claims-tg06-authoritative-grounding` | TG-04 | not_started | Every promotion-eligible entity resolves to an authoritative identifier. |
| TG-07 | TBD | `alvaro/trusted-claims-tg07-safe-projection` | TG-05, TG-06 | not_started | Only complete supported claims project to positive graph relations. |
| TG-08 | TBD | `alvaro/trusted-claims-tg08-real-source-proof` | TG-07 | not_started | Repeated real-source runs satisfy every agent-readiness gate. |

Dependency graph:

```text
TG-01 -> TG-02 -> TG-03 -> TG-04
                              |-> TG-05 -|
                              |-> TG-06 -|-> TG-07 -> TG-08
```

TG-05 and TG-06 may run in parallel after TG-04. The other PRs are ordered
because they change a shared contract or depend on evidence produced earlier.

## Standard PR Loop

Every PR follows this loop and records each result in its evidence report.

- [ ] Freeze the parent commit, input cases, prompts, model identifier, and
      baseline artifact hashes before implementation.
- [ ] State one falsifiable hypothesis and name the root cause being changed.
- [ ] Review existing unit, integration, contract, and end-to-end tests.
- [ ] Add failing unit and regression tests for the identified failure.
- [ ] Add at least one adversarial test that attempts unsafe promotion.
- [ ] Implement one responsibility at the service that owns it.
- [ ] Run focused tests and the changed service's lint, type, boundary, and
      contract checks.
- [ ] Run Postgres-backed integration tests when persistence or an API contract
      changes.
- [ ] Run the strict live-agent path with `openai:gpt-5.6-luna`; fallback stays
      disabled and cannot receive credit.
- [ ] Run three identical live passes when the PR changes extraction,
      verification, grounding, or projection semantics.
- [ ] Freeze outputs before independent agent review.
- [ ] Request an adversarial reviewer that did not implement the PR. The review
      must cite files, cases, or artifact evidence; a generic approval is not
      review evidence.
- [ ] Fix valid findings, rerun affected validation, and record unresolved risk.
- [ ] Run `git diff --check` and `make service-checks` without skipping hooks.
- [ ] Publish a deterministic before/after report under
      `docs/validation/reports/` and link raw immutable artifacts.
- [ ] Merge only when the PR-specific gate and the global merge gate pass.

## Global Merge Gate

A PR is not merge-ready until all applicable statements are true:

- its hypothesis is supported or it demonstrably strengthens a fail-closed
  invariant;
- focused unit and regression tests pass;
- relevant integration, migration, and generated contract tests pass;
- the relevant service gate and `make service-checks` pass;
- strict agent completion is 100%, credited fallback is 0, and invalid agent
  output is 0 for live-semantic PRs;
- every executed provider response is independently retrievable and its
  canonical output hash matches the model-attempt record;
- no new negative, null-result, contradiction, or hypothesis leakage appears;
- agent outputs remain categorical and all numeric metrics are deterministic;
- the evidence summary contains exact commands, commit, model, case hashes,
  artifact paths, metric denominators, and before/after results;
- an independent adversarial review has no unresolved high-severity finding;
- documentation names remaining blockers and does not claim human expertise;
- GitHub has no unresolved actionable review thread, required checks are green,
  the branch is conflict-free, and required approval is present.

## Validation Command Matrix

Use the repository's existing targets. Focused pytest commands belong in each
PR evidence report because the exact test files may change during
implementation.

Evidence API changes:

```bash
make artana-evidence-api-lint
make artana-evidence-api-type-check
make artana-evidence-api-boundary-check
make artana-evidence-api-contract-check
make artana-evidence-api-test
make artana-evidence-api-service-checks
```

Graph DB changes:

```bash
make graph-service-lint
make graph-service-type-check
make graph-service-boundary-check
make graph-service-contract-check
make graph-service-test
make graph-service-checks
```

Cross-service, migration, or generated-contract changes:

```bash
make setup-postgres
make artana-evidence-api-service-checks
make graph-service-checks
make service-checks
```

Strict live-agent regression template:

```bash
set -a
source .env.postgres
set +a
export ARTANA_AI_EVIDENCE_EXTRACTION_MODEL=openai:gpt-5.6-luna
RUN_DIR=docs/validation/reports/relation_feasibility/<date>-<plan-id>-run-01
test ! -e "$RUN_DIR"
uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir "$RUN_DIR"
```

For semantic PRs, repeat into `run-02` and `run-03`, then evaluate worst-run
results with the existing readiness gate. The no-clobber preflight is mandatory
for every run ID; a pre-existing run directory invalidates the command rather
than authorizing replacement. Do not overwrite a prior run or retry only failed
cases. Store the exact command, environment-name allowlist, model,
prompt/configuration hashes, and output hashes in the evidence report. Never
record secret values. The run preflight and manifest must both prove that the
configured and retrieved provider model is exactly `openai:gpt-5.6-luna`; a
runtime-default substitution invalidates the run.

## TG-01: Truthful Safety Floor

**Hypothesis:** current candidates can satisfy the `trusted` tier using
heuristic semantic support and symbolic variant identifiers. Blocking those
paths will remove false trust even if the trusted count temporarily falls to
zero. Authoritative source identity and exact locators remain TG-02's separate
responsibility.

**Root cause:** trust checks validate a result shape, not the authority that
produced it. `_heuristic_support` can return `ENTAILS`; `trust_ladder.py` accepts
that category without requiring an independent agent verifier; and the verified
dictionary contains symbolic ClinVar-like values also used by fixtures.

**Primary files:**

- `services/artana_evidence_api/document_extraction_support/evidence_support_verifier.py`
- `services/artana_evidence_api/document_extraction_support/trust_ladder.py`
- `services/artana_evidence_api/document_extraction_support/entity_grounding/verified_dictionary.py`
- `services/artana_evidence_db/validation/claim_ai_evidence_validation.py`
- `services/artana_evidence_db/validation/trusted_evidence_floor.py`

**Implementation scope:**

- Make semantic verification origin explicit and closed: `agent`, `heuristic`,
  or `unavailable`.
- Prevent `heuristic` and `unavailable` results from satisfying trusted or
  verified semantic floors.
- Reject symbolic ClinVar placeholders as verified identifiers. Quarantine
  affected dictionary entries and fixtures instead of silently rewriting them.
- Keep heuristic support available only as clearly labeled triage metadata.

**Required tests:**

- Unit: a heuristic `ENTAILS` result remains an agent candidate and cannot be
  trusted.
- Unit: missing verification origin fails closed.
- Unit: symbolic ClinVar values cannot set `trusted_identifier=true`.
- Regression: forged metadata cannot bypass Graph DB trust enforcement.
- Integration: the old proposal write path cannot create a trusted claim from
  heuristic semantic support.
- Adversarial: mutate each trust metadata field independently and prove none can
  create a trusted result.

**Merge gate:**

- heuristic-supported trusted count: `0`;
- symbolic-placeholder verified count: `0`;
- fallback and invalid-agent counts: `0`;
- Graph DB independently rejects every forged case;
- any reduction in trusted-candidate count is reported as truthful quarantine,
  not as a quality regression.

**Evidence report:**
`docs/validation/reports/<date>-tg01-truthful-safety.md`

## TG-02: Authoritative Source Provenance And Exact Locators

**Hypothesis:** a claim cannot be independently checked because the current
packet often identifies an internal proposal rather than the actual publication
or registry record and exact source location.

**Root cause:** source identity, retrieval version, and evidence location are
not one required end-to-end contract from ingestion through Graph DB.

**Primary files:**

- `services/artana_evidence_api/source_document_models.py`
- `services/artana_evidence_api/source_document_extraction_service.py`
- `services/artana_evidence_api/document_extraction_contracts.py`
- `services/artana_evidence_api/proposal_actions.py`
- `services/artana_evidence_api/types/graph_contracts.py`
- `services/artana_evidence_db/provenance_model.py`
- `services/artana_evidence_db/claim_evidence_models.py`

**Implementation scope:**

- Add a typed source identity with source kind, authoritative identifier, URL,
  retrieved timestamp, version when available, and immutable content hash.
- Add an exact evidence locator with section, paragraph or sentence identity,
  character offsets, exact quote, and quote hash. Page/table/figure locators are
  required when the source format supplies them.
- Preserve PMID, PMCID, DOI, ClinicalTrials.gov NCT ID, ClinVar accession, and
  publisher record identity without flattening them into an internal proposal
  ID.
- Carry source and locator data through extraction, proposal review, graph
  client requests, claim evidence, and provenance storage.
- Refuse promotion when the quote does not match the hashed source snapshot.

**Required tests:**

- Unit: locator offsets recover the exact quote from the source snapshot.
- Property/regression: Unicode, repeated sentences, section boundaries, and
  long-document chunks do not shift the locator.
- Unit: source version or content changes invalidate the quote hash.
- Contract: Evidence API and Graph DB schemas expose the same required source
  fields.
- Migration: old rows remain readable but are explicitly ineligible until
  provenance is repaired.
- Integration: a real PubMed/PMC fixture round-trips source identity and locator
  through both services.
- Adversarial: external corroboration cannot substitute for a missing local
  locator.

**Merge gate:**

- promotion-eligible claims with authoritative source identity: `100%`;
- promotion-eligible claims with a valid exact locator: `100%`;
- quote/source hash mismatches accepted: `0`;
- internal-only references counted as authoritative provenance: `0`;
- provenance survives API serialization and database round-trip without loss.

**Evidence report:**
`docs/validation/reports/<date>-tg02-source-provenance.md`

## TG-03: Qualified ClaimFrame Agent Extraction

**Hypothesis:** most generic and overstated relations come from collapsing a
scientific statement directly into `subject - predicate - object` before
polarity, biological state, study context, and qualifiers are preserved.

**Root cause:** the extraction contract is too small for the information needed
to distinguish a broad assertion from a conditional observation, null result,
or hypothesis.

**Primary files:**

- `services/artana_evidence_api/document_extraction_contracts.py`
- `services/artana_evidence_api/document_extraction_prompting.py`
- `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- new focused modules under
  `services/artana_evidence_api/document_extraction_support/claim_frames/`

**Implementation scope:**

- Introduce a typed `ClaimFrame` with source locator, subject, predicate,
  object, polarity, epistemic status, biological or variant state, population,
  intervention, comparator, outcome, study design, treatment setting,
  timeframe, threshold, and extracted source measurements.
- Use closed categorical values for polarity and epistemic status.
- Require every material qualifier present in the cited sentence or local
  context to be represented or explicitly marked `not_applicable` or
  `unresolved`.
- Store exact agent evidence spans and a natural-language extraction rationale.
- Do not ask the extraction agent for confidence or any numeric quality score.
- Extract source-native numbers only with an exact span and
  `origin=source_measurement`.
- Emit null, negative, provisional, and novel statements as claims with honest
  semantics instead of assertive edges plus review flags.
- Inventory every source-local claim before framing and frame one inventory
  item per model call so sibling predicates cannot compete for one output slot.
- Initially require the inventory agent to categorize binary endpoint direction
  as `A_SUBJECT_B_OBJECT`, `B_SUBJECT_A_OBJECT`, or `UNRESOLVED`. The clean Luna
  smoke demonstrated that this representation is still lossy when a sentence
  supports multiple role-compatible frames. That result is the input to TG-04,
  not a quality success for TG-03.

**Required tests:**

- Unit: variant state such as `EGFR T790M`, `BRCA1 loss`, and zygosity is not
  reduced to the bare gene.
- Unit: disease subtype, population, treatment line, assay cutoff, comparator,
  endpoint, and timeframe are preserved.
- Unit: explicit negation and failed thresholds produce `REFUTE`, `UNCERTAIN`,
  or null-result semantics, never a positive support frame.
- Unit: hypotheses remain `HYPOTHESIS` even when external corroboration is
  absent.
- Regression: long and multi-clause sentences bind qualifiers to the correct
  subject, predicate, and object.
- Regression: reversing subject and object is rejected even when both endpoint
  spans remain source-bound.
- Schema: unknown categories fail validation rather than becoming free text.
- Live agent: one strict Luna smoke run over the historical development set to
  prove the production path and provider receipt chain. Three-run confirmatory
  quality proof moves to TG-08 because this set informed the TG-03 design.
- Adversarial: attempt to strip each qualifier while retaining the broad triple.

**Merge gate:**

- frozen cases with correct explicit polarity: `100%` diagnostic concordance;
- required qualifier presence on promotion-eligible frames: `100%`;
- positive frames emitted from explicit negative/null cases: `0`;
- agent-authored quality scores: `0`;
- source measurements without exact source spans: `0`;
- provider responses that are incomplete, hidden-context, relabelled, or
  omitted before scoring receive credit: `0`;
- reversed directional frames accepted: `0`;
- canonical semantic-frame stability on the eventual confirmatory three-run
  set: at least `95%`, with
  exact serialized-frame stability reported separately. Canonical stability
  may ignore harmless source-span boundary or case differences only when the
  frame remains source-bound and every gold categorical semantic field agrees.

**Evidence report:**
`docs/validation/reports/<date>-tg03-qualified-claim-frame.md`

## TG-04: Lossless Claim Persistence And Graph Contract

**Hypothesis:** preserving typed event arguments and explicit ambiguity before
choosing graph endpoints will prevent the early semantic loss observed in the
TG-03 live smoke, and the result can be stored without conversion to a triple.

**Root cause:** the current inventory forces one untyped binary endpoint pair
from a source statement that may contain an intervention, condition,
population, variant, outcome, and several defensible projections. Framing then
receives a shortened span and cannot recover discarded roles. The subsequent
proposal action also uses a narrow claim-create contract that bypasses existing
Graph DB participant, qualifier, evidence, and projection capabilities.

**Primary files:**

- `services/artana_evidence_api/types/graph_contracts.py`
- `services/artana_evidence_api/graph_client.py`
- `services/artana_evidence_api/proposal_actions.py`
- `services/artana_evidence_db/graph_api_schemas/kernel_relation_schemas.py`
- `services/artana_evidence_db/relation_claim_models.py`
- `services/artana_evidence_db/claim_participant_models.py`
- `services/artana_evidence_db/claim_evidence_models.py`
- `services/artana_evidence_db/graph_domain_qualifiers.py`
- relevant forward-only migrations and generated API contracts

**Implementation scope:**

TG-04 has a scientific restart gate before persistence work:

- keep the untouched, set-valued n-ary event panel and categorical gold frozen;
- replace open-ended inventory completeness with a finite source-unit contract;
- require extraction agents to return `EXPLICIT_EVENT`, `NO_EVENT`, or
  `ABSTAIN`, with exact trigger and argument spans;
- require a separate source-only verifier agent to return `ENTAILED`,
  `CONTRADICTED`, `INSUFFICIENT`, or `ABSTAIN`, with exact evidence and a
  falsification explanation;
- compute every metric and readiness decision deterministically;
- run the same four-case Luna diagnostic once, then consider a stronger-model
  arm only against the unchanged finite task;
- publish case transitions, metrics, provider receipts, replay evidence, and
  artifact hashes;
- resume persistence only when scientific and provider-custody gates pass.

Until that gate passes, Graph schema, migration, and persistence changes remain
paused. Preserving six roles on one diagnostic case is an information-retention
result, not evidence of better scientific precision or recall.

After the scientific restart gate passes:

- Replace the binary inventory handoff with a role-typed assertion containing
  `INTERVENTION`, `CONDITION`, `POPULATION`, `VARIANT`, `OUTCOME`, `COMPARATOR`,
  `TIMEFRAME`, and `STUDY_DESIGN` participants as applicable, each bound to an
  exact source span.
- Preserve the complete source sentence or bounded source region through
  framing; a shortened surface clause may be an anchor but not the sole input.
- Return categorical `SINGLE_FRAME`, `MULTIPLE_VALID_FRAMES`, `AMBIGUOUS`, or
  `ABSTAIN`. Preserve every supported candidate frame instead of silently
  selecting one.
- Add a claim-create request that carries the complete role-typed assertion,
  candidate frames, and ambiguity decision.
- Persist claim polarity, participants and roles, qualifier values, source
  measurements, evidence locators, extraction run identity, prompt/model
  identity, and agent rationale.
- Make the claim ledger the first write. Do not create or promote a canonical
  relation as a side effect of receiving an incomplete claim.
- Include polarity, material qualifiers, entity state, and source identity in
  idempotency and claim fingerprints.
- Route old triple-only records to explicit migration/review status. Do not
  invent missing qualifiers during migration.
- Regenerate OpenAPI and TypeScript artifacts when contracts change.

**Required tests:**

- Unit: the ALK G1202R smoke sentence preserves intervention, disease,
  population, variant, and outcome roles before any endpoint selection.
- Unit: multiple defensible projections produce `MULTIPLE_VALID_FRAMES` and
  survive without one being silently dropped.
- Contract: complete role-typed assertions serialize identically across both
  service schemas.
- Integration: Evidence API writes a claim, participants, qualifiers, evidence,
  and provenance to Postgres-backed Graph DB.
- Round-trip: every material role, ClaimFrame, ambiguity, and evidence field
  reads back unchanged.
- Idempotency: identical claims deduplicate; claims with different polarity,
  source, variant state, population, or endpoint remain distinct.
- Migration: legacy incomplete triples stay readable and promotion-ineligible.
- Failure injection: partial persistence rolls back rather than leaving a claim
  or edge with missing evidence.
- End-to-end: no direct legacy proposal path bypasses claim persistence.

**Merge gate:**

- untouched n-ary panel, labels, scorer, prompts, and model configuration are
  frozen and hash-addressed before execution;
- every deterministic scientific metric and paired case transition is
  published for all three runs;
- the proposed approach clears every provisional agent-readiness gate in the
  Scientific Improvement Measurement Protocol;
- if the gate fails, TG-04 remains a documented controlled stop and persistence
  does not resume;
- assertion roles, candidate frames, or ClaimFrame fields lost in round-trip:
  `0`;
- source-supported ambiguous alternatives silently collapsed: `0`;
- partial write artifacts after injected failure: `0`;
- incomplete legacy claims auto-promoted: `0`;
- direct trusted-edge writes from the extraction proposal path: `0`;
- graph and evidence service contract checks pass with generated artifacts
  current.

**Latest evidence report:**
`docs/validation/reports/2026-07-17-tg04-bounded-convergence-pilot.md`

## TG-05: Independent Agent Semantic Verifier

**Hypothesis:** the extracting agent's rationale and deterministic text cues are
not independent evidence that the complete qualified claim is entailed by the
cited source.

**Root cause:** semantic support currently has a heuristic fallback that can
return `ENTAILS`, and the trust ladder checks the category without proving an
independent agent evaluated polarity and qualifiers.

**Primary files:**

- new focused verifier modules under
  `services/artana_evidence_api/document_extraction_support/agent_verification/`
- `services/artana_evidence_api/document_extraction_support/evidence_support_verifier.py`
- `services/artana_evidence_api/document_extraction_support/trust_ladder.py`
- guarded agent runtime and replay/cache-key modules

**Agent output contract:**

- `support_status`: `entails`, `contradicts`, `insufficient`, or `abstain`;
- `argument_grounding`: `both`, `partial`, or `none`;
- `qualifier_fidelity`: `complete`, `incomplete`, `contradicted`, or
  `not_applicable`;
- `polarity_fidelity`: `correct`, `incorrect`, or `uncertain`;
- exact supporting and contradicting spans;
- explanation and falsification note;
- no numeric confidence or readiness score.

**Implementation scope:**

- Run a distinct verification call after extraction using the cited source
  snapshot, exact locator, and complete ClaimFrame.
- Prevent the verifier from seeing extractor confidence, fixture labels, or
  downstream trust status.
- Record verifier model, prompt version, input hash, output hash, and run ID.
- Fail closed on timeout, invalid category, missing span, or unavailable agent.
- Keep deterministic cues as diagnostics only; they may detect obvious format
  failures but cannot produce semantic trust.
- Deterministically map categorical verifier findings to eligibility.

**Required tests:**

- Unit: every category maps to the intended fail-closed policy.
- Unit: entailed broad triple plus missing qualifier is not eligible.
- Unit: correct entities with wrong direction or polarity are rejected.
- Unit: verifier timeout, malformed output, or cache mismatch blocks trust.
- Regression: deterministic heuristic `ENTAILS` never substitutes for the agent.
- Cache: model, prompt, ClaimFrame, source, or locator changes invalidate replay.
- Live agent: three Luna verifier passes over positives, negatives, nulls,
  hypotheses, multi-clause claims, and qualifier traps.
- Adversarial: a separate agent attempts to approve claims using outside facts
  not present in the cited source.

**Merge gate:**

- promotion-eligible claims with independent agent verification: `100%`;
- heuristic semantic results counted as agent verification: `0`;
- qualifier-incomplete or polarity-wrong claims eligible: `0`;
- malformed/unavailable verifier results eligible: `0`;
- categorical verifier stability across three identical runs: at least `95%`;
- all numeric verifier metrics are computed deterministically.

**Evidence report:**
`docs/validation/reports/<date>-tg05-agent-verifier.md`

## TG-06: Authoritative Entity And Variant Grounding

**Hypothesis:** a correct statement is unsafe to connect when the system cannot
prove which gene, variant, disease, drug, process, or phenotype each mention
means.

**Root cause:** model hints, local aliases, symbolic variant labels, and fixture
expectations are mixed with authoritative verification.

**Primary files:**

- `services/artana_evidence_api/document_extraction_support/entity_grounding/`
- `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- graph dictionary governance and entity validation modules
- frozen authoritative-source fixtures under the relevant test trees

**Implementation scope:**

- Define an allowlist of entity kinds and authoritative namespaces.
- Use authoritative identifiers appropriate to each type, including numeric
  ClinVar Variation IDs or accessions and GA4GH VRS computed identifiers for
  variants where applicable.
- Separate the agent's candidate resolution from deterministic authority
  verification. The agent returns a candidate, category, explanation, and
  evidence; code verifies identifier syntax, type, record existence, and
  source/version provenance.
- Represent allele, zygosity, copy-number state, loss/gain, fusion, expression,
  and protein consequence separately from the bare gene.
- Return `verified`, `ambiguous`, `unresolved`, or `invalid`; do not force a
  nearest match.
- Preserve ambiguous and unresolved novel claims for review while blocking
  relation projection.

**Required tests:**

- Unit: symbolic ClinVar placeholders are invalid as authoritative IDs.
- Unit: bare-gene grounding cannot replace a material variant or state.
- Unit: namespace and entity type must agree.
- Unit: ambiguous aliases abstain instead of choosing the first match.
- Snapshot: authoritative record version and content hash are retained.
- Integration: authoritative-source adapters fail closed on unavailable,
  mismatched, retired, or redirected records.
- Regression: the benchmark cannot use the same local dictionary entry as both
  expected truth and independent verification.
- Live agent: three runs over genes, variants, diseases, drugs, processes,
  phenotypes, and deliberately ambiguous mentions.
- Adversarial: attempt identifier spoofing, namespace confusion, paralog
  substitution, and bare-gene collapse.

**Merge gate:**

- wrong authoritative links among eligible claims: `0`;
- promotion-eligible endpoints with verified authority records: `100%`;
- symbolic-placeholder verified identifiers: `0`;
- material variant/state collapsed to a bare gene: `0`;
- frozen diagnostic verified-CURIE match rate: at least `95%`;
- unresolved novel claims preserved for review: `100%`.

**Evidence report:**
`docs/validation/reports/<date>-tg06-authoritative-grounding.md`

## TG-07: Safe Claim-To-Relation Projection

**Hypothesis:** a graph relation is safe only when its complete source claim is
supported, authoritatively grounded, representable without qualifier loss, and
still linked to its evidence.

**Root cause:** projection and trust have been treated as metadata on relation
candidates instead of as a deterministic policy over persisted qualified
claims.

**Primary files:**

- `services/artana_evidence_db/claim_projection_readiness_service.py`
- `services/artana_evidence_db/claim_projection_readiness_support.py`
- `services/artana_evidence_db/relation_projection_invariant_service.py`
- `services/artana_evidence_db/relation_projection_materialization_service.py`
- `services/artana_evidence_db/relation_projection_source_service.py`
- `services/artana_evidence_db/relation_autopromotion_policy.py`

**Implementation scope:**

- Compute projection eligibility deterministically from persisted claim facts.
- Require authoritative source and locator, independent agent entailment,
  verified participants, canonical predicate, explicit polarity, and complete
  representable qualifiers.
- Project only supported positive claims into positive canonical relations.
- Keep `REFUTE`, `UNCERTAIN`, `HYPOTHESIS`, null-result, unresolved, and
  qualifier-incomplete records queryable in the claim ledger without positive
  projection.
- Preserve a reversible pointer from every relation to its source claims,
  evidence locators, verifier artifacts, and authority records.
- Include material qualifiers in projection fingerprints so scoped claims do
  not collapse into a broad edge.
- Invalidate or rematerialize projections when a source, claim, entity,
  verifier result, correction, or retraction changes.

**Required tests:**

- Unit decision table for every missing or failing prerequisite.
- Unit: negative, null, uncertain, and hypothesis claims create no positive
  canonical edge.
- Unit: qualifier loss blocks projection rather than broadening the claim.
- Unit: contradictory claims coexist in the ledger without becoming one
  misleading edge.
- Integration: complete claim projects exactly once and remains traceable.
- Idempotency/concurrency: retries and races do not duplicate relations.
- Invalidation: correction, retraction, or verifier reversal withdraws the
  derived projection while retaining audit history.
- End-to-end: neither Evidence API nor direct Graph API callers can bypass the
  projection policy.
- Adversarial: forged trust metadata, direct route calls, partial claims, and
  stale verifier artifacts all fail.

**Merge gate:**

- positive projections from negative/null/uncertain/hypothesis claims: `0`;
- projections with missing source, locator, verifier, or authoritative entity:
  `0`;
- projections that drop a material qualifier: `0`;
- projected relations without reversible claim/evidence lineage: `0`;
- duplicate projections under retry or concurrency: `0`;
- Graph DB rejects all policy bypass attempts independently of Evidence API.

**Evidence report:**
`docs/validation/reports/<date>-tg07-safe-projection.md`

## TG-08: Frozen Real-Source Proof And Release Decision

**Hypothesis:** after the product contract is repaired, Artana will create
specific, traceable, stable, independently verified claims from real biomedical
sources rather than only performing well against repository-authored fixtures.

**Root cause addressed:** previous scorecards relied heavily on synthetic or
repository-authored cases and measured broad triple concordance. They did not
prove source-local fidelity of the complete claim.

**Study set:**

- at least 60 real, immutable source documents;
- balanced coverage of strong direct findings, explicit negatives and nulls,
  variants and biological state, population and treatment qualifiers,
  provisional or novel hypotheses, and long or contradictory documents;
- topic coverage across oncology, rare disease, cardiology, pharmacogenomics,
  molecular mechanisms, and clinical trials;
- no test case may be created from the same dictionary record used to verify
  its expected entity mapping;
- source snapshots, case-selection rules, hashes, prompts, and metric semantics
  are frozen before the first run.

**Execution:**

- Run the complete agent path three times with `openai:gpt-5.6-luna` and no
  deterministic semantic fallback.
- Freeze each run before review.
- Run independent packet-only and source-enriched agent reviewers using the
  categorical contract in
  `docs/validation/codex-agent-expert-evaluation-protocol.md`.
- Allow source-enriched agents to browse authoritative sources, but keep
  source-local sufficiency separate from external-world corroboration.
- Run fresh adversarial agents against every proposed keep decision, negative
  control, novel hypothesis, unstable claim, and high-impact disagreement.
- Compute every metric deterministically from frozen categorical findings.
- Publish raw artifacts, hashes, source ledger, disagreements, adjudication,
  metric protocol, deterministic scorecard, and plain-language report.

**Agent-readiness gates:**

| Gate | Target |
|---|---:|
| Agent completion | 100% in every run |
| Credited fallback | 0 |
| Invalid agent output | 0 |
| Authoritative source identity and exact locator | 100% of eligible claims |
| Independent agent semantic verification | 100% of eligible claims |
| Heuristic semantic verification receiving agent credit | 0 |
| Authoritatively verified entities | 100% of eligible claim endpoints |
| Wrong authoritative entity links | 0 |
| Positive projection from negative/null/hypothesis claims | 0 |
| Material qualifier loss in projected relations | 0 |
| Strong provenance in reviewed eligible packets | 100% |
| Source-local packet sufficiency | at least 90% diagnostic rate |
| Generic or overstated reviewed claims | at most 5% diagnostic rate |
| Exact semantic stability across three runs | at least 95% |
| High-severity unsupported auto-projections | 0 |
| Novel hypotheses preserved or explicitly routed | 100% |

The packet sufficiency, specificity, and stability rates are internal
agent-diagnostic measures until human experts review the frozen study. They may
authorize the `verified_evidence` lane, not a claim of human-expert precision.

**Merge and release gate:**

- all earlier PR evidence is linked and hash-verifiable;
- every agent-readiness gate above passes without threshold changes;
- independent adversarial review has no unresolved high-severity issue;
- three repeated runs pass on worst-run metrics, not only means;
- the report clearly separates technical readiness, diagnostic agent findings,
  and absent human-expert validation;
- if any hard gate fails, the decision remains `not_ready` and the report names
  the exact failing cases. Do not start another broad PR loop automatically.

**Evidence report:**
`docs/validation/reports/<date>-tg08-real-source-readiness.md`

## Evidence Summary Template

Every PR must create one report using this shape:

```markdown
# TG-0X Evidence Summary

- GitHub PR:
- Branch:
- Commit:
- Parent commit:
- Hypothesis:
- Root cause:
- Implementation responsibility:
- Frozen input manifest and hash:
- Model and normalized execution model:
- Prompt/configuration hashes:

## Before And After

| Gate | Baseline | Current | Target | Denominator | Result |
|---|---:|---:|---:|---:|---|

## Validation

- Focused unit/regression tests:
- Integration/migration/contract tests:
- Service checks:
- Strict live-agent runs:
- Artifact hashes:
- Independent reviewer:
- Adversarial findings and resolutions:

## Decision

- Merge gate: pass/fail
- Safety invariants strengthened:
- Product quality improved:
- Remaining blockers:
- Human-expert evidence present: yes/no
```

## Final Readiness Matrix

Do not collapse progress into one weighted score. A high average can hide a
single unsafe failure. Track each dimension independently.

| Dimension | Baseline | Required end state | Owning PR | Current evidence | Status |
|---|---|---|---|---|---|
| Agent execution | Historical note: 300/300, fallback 0 | Establish 100%, fallback 0 from committed provider evidence | All | Original July 14 raw report missing; TG-03 has a smaller provider-bound smoke run | not_evaluable |
| Truthful trust | Heuristic and symbolic-authority gaps found | No non-agent semantic trust or fake authority | TG-01 | `docs/validation/reports/2026-07-14-tg01-truthful-safety.md` | merged |
| Source traceability | 2/47 strong provenance | 100% eligible claims strong | TG-02 | Implementation and safety gates merged; the experimental evidence remains non-evaluable under the durable-artifact protocol. See `docs/validation/reports/2026-07-15-tg02-source-provenance.md`. | merged |
| Claim extraction runtime safety | No inventory-first provider path | Strict agent path is auditable, fallback-free, and quarantined | TG-03 | Clean Luna smoke completed with fallback 0 and graph writes 0; both adversarial re-reviews are clear. See `docs/validation/reports/2026-07-14-tg03-qualified-claim-frame.md`. | merged |
| Claim completeness | 13/47 generic/overstated outcomes | Complete typed roles, polarity, state, qualifiers, and honest ambiguity | TG-04 | A development run reported better role preservation, but its artifacts were ephemeral and its candidate projections remained scientifically ambiguous. The controlled stop is recorded in `docs/validation/reports/2026-07-15-tg04-typed-assertion-checkpoint.md`. | blocked |
| Lossless persistence | Triple-oriented write path | Zero assertion-role, candidate-frame, ambiguity, or evidence field loss | TG-04 | Persistence was intentionally not implemented because claim completeness and durable scientific proof did not pass. | blocked |
| Semantic verification | Heuristic can return `ENTAILS` | Independent categorical agent verifier | TG-05 | Pending | not_started |
| Entity grounding | 75.86% worst-run diagnostic rate | At least 95%, wrong links 0 | TG-06 | Pending | not_started |
| Safe projection | Review flags can accompany assertive tuples | Zero unsafe or lossy positive edges | TG-07 | Pending | not_started |
| Real-source proof | 8/47 sufficient risk packets | All TG-08 gates on 60+ real sources | TG-08 | Pending | not_started |
| Human-expert proof | None | Authenticated independent expert study | Future governance | Not available | blocked |

## Stop And Reassess Rules

Stop the implementation sequence and perform a root-cause review when any of
the following occurs:

- two consecutive PRs add validation machinery without improving a product
  field or strengthening a safety invariant;
- the same failure class remains unchanged after two attempted product fixes;
- a PR needs to lower a threshold or relabel an output to appear successful;
- live-agent completion, fallback, invalid-output, negative-control, or wrong-ID
  safety regresses;
- packet sufficiency or qualifier fidelity does not materially improve after
  TG-03 and TG-04;
- the implementation starts using external corroboration to excuse missing
  source-local evidence;
- a new broad benchmark is proposed before the current frozen failures are
  closed;
- agent evaluation is presented as human-expert precision.

At a stop point, publish a short decision record with: observed failure, root
cause hypothesis, evidence for and against it, whether to revise the approach,
and the smallest next experiment. Do not continue the PR sequence by inertia.

## Good Stopping Points

- **After TG-01:** the system is more truthful but may have zero trusted claims.
  This is a safe operational stop.
- **At the TG-04 controlled stop:** Artana preserves richer assertion data in
  runtime proposals, but has no validated lossless claim ledger or automatic
  projection. Resume persistence only after durable n-ary scientific evidence
  passes the checkpoint.
- **After TG-07:** the product path is technically complete; automatic trusted
  promotion may remain disabled while real-source proof runs.
- **After TG-08:** decide whether to enable the agent-verified lane, repeat a
  narrowly targeted failure experiment, or wait for human experts. Do not open
  another general excellence loop without a newly observed root cause.
