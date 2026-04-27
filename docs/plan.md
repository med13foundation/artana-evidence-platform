# Living Research Space And Agentic Evidence Selection Plan

Status date: April 26, 2026.

Implementation note: the implementation slices are now in place for the
model-planned, review-gated baseline. The
`evidence-selection` harness has public `evidence-runs` routes, workspace
snapshotting, deterministic ranking of durable saved source-search records,
tool-backed structured source-search creation including PubMed and MARRVEL,
guarded source handoff creation,
review-gated proposal/review-item staging, follow-up runs, source-relevance
skill registration, an auditable source-planner seam, per-source live-search
timeouts, executable planner-added source searches, validation comparison
helpers, planner-output validation, strict extraction-policy lookup, guarded
review-store enforcement, model-mediated goal-only source planning, source
query adapters, tests, and user-guide updates. The remaining expansion is real
offline/clinical validation studies.

Current request boundary: evidence runs default to `planner_mode="model"`.
When a query-generation model and API key are configured, a researcher can
submit only a goal/instructions and the planner will create bounded source
searches. `planner_mode="deterministic"` remains available for explicit
manual runs and still requires `source_searches` or `candidate_searches`.
If model planning is unavailable, goal-only requests fail clearly; explicit
source-search requests can fall back to deterministic execution with fallback
metadata recorded in the source-plan artifact. Guarded mode requires at least
one allowed handoff; use shadow mode for screen-only recommendations. Planner
output is validated before source side effects so a model planner cannot
silently add unknown, unsupported, or out-of-envelope sources.

## Goal

Build the next layer of the Evidence API so a researcher can start with a goal,
keep adding ideas over time, and let an Artana harness choose the relevant
source records to extract into reviewable evidence proposals.

The core product idea is:

```text
research space
  -> many research runs over time
  -> agent searches and selects relevant source records
  -> selected records become durable source documents
  -> extraction creates proposals or review items
  -> human/governance review decides what becomes trusted graph knowledge
```

The research space is the long-lived lab notebook. A harness run is one
research pass inside that notebook.

## First Principles

- Research is iterative, not a one-time job.
- The human gives goals, constraints, corrections, and review decisions.
- The agent is the first relevance filter. It should choose useful source
  records from the user goal and instructions.
- The human remains the trust gate. Unreviewed AI output should not become
  trusted graph state.
- Source connectors should stay deterministic. They fetch and normalize source
  data; they do not decide truth.
- Handoff and persistence should stay deterministic and auditable.
- Lower-level source/search/handoff endpoints should remain available for
  debugging and power users, but the main product path should be a goal-driven
  evidence harness.

## Scientific Fit And Guardrails

This loop is scientifically useful only if it is framed as evidence
surveillance and evidence staging, not automatic truth creation.

Good scientific framing:

```text
agent finds and organizes candidate evidence
  -> system records provenance and inclusion/exclusion reasons
  -> extraction creates proposals or review items
  -> humans or governance rules assess quality and certainty
  -> only approved claims become graph knowledge
```

The loop is closest to:

- living evidence surveillance;
- living systematic-review support;
- evidence mapping;
- gene-disease and variant curation support;
- translational research planning;
- hypothesis generation and gap finding;
- knowledge-graph proposal staging.

The loop should support scientific work such as:

- rare-disease evidence maps where information is scattered across literature,
  variant databases, model organisms, protein sources, structure sources, and
  clinical-trial records;
- gene-disease curation where the system gathers candidate evidence for
  review;
- variant interpretation support where source records and papers are collected
  as evidence candidates;
- living literature surveillance where new papers are compared against prior
  review decisions;
- translational research planning where the useful output is "what evidence is
  missing?" as much as "what evidence exists?";
- graph-building workflows where only reviewed proposals become trusted graph
  facts.

The loop should be rejected or downgraded when the user asks it to:

- make clinical treatment decisions;
- make regulatory claims without a protocol, quality assessment, and explicit
  data relevance/reliability review;
- claim causality from association-only evidence;
- call itself a systematic review without predefined inclusion criteria,
  exclusion criteria, search methods, and screening/accounting records;
- turn agent-selected evidence directly into trusted graph facts;
- omit provenance, source identifiers, inclusion/exclusion reasons, or quality
  caveats;
- ignore contradictory evidence or unresolved uncertainty.

Scientific outputs must therefore include:

- source provenance and stable source identifiers;
- why each record was selected, skipped, or deferred;
- duplicate and already-reviewed evidence handling;
- evidence type and source family;
- uncertainty and limitations;
- contradiction flags where available;
- proposal/review status;
- a clear distinction between "candidate evidence", "reviewed evidence", and
  "trusted graph knowledge".

## What Already Exists

- Research spaces as the container for ongoing work.
- Durable harness runs, run status, events, artifacts, and workspace state.
- Worker execution that maps queued runs to `harness_id` and then to a
  `BaseHarness` wrapper.
- Harness templates for `research-init`, `research-bootstrap`,
  `full-ai-orchestrator`, `graph-chat`, `continuous-learning`, and related
  workflows.
- Runtime skill infrastructure through filesystem-backed `SKILL.md` files,
  skill loading, capability checks, and runtime tool visibility.
- Source registry and direct source search endpoints.
- Durable `source_search_runs` for captured source-search results.
- Durable `source_search_handoffs` for turning selected records into source
  documents.
- Source documents with provenance, source family, normalized record metadata,
  readable extraction text, and raw selected record payloads.
- Variant-aware extraction for supported variant-like documents.
- Proposal and review-item stores.
- Review-gated promotion into trusted graph state.
- Full-AI orchestrator modes: deterministic, shadow, and guarded.

## Missing Product Layer

The missing layer is an agent-controlled evidence selection harness.

Today, the infrastructure can save searches and hand off selected records. The
next harness should decide what to select based on the user's goal, prior
workspace history, source coverage, and review decisions.

Working name:

- `evidence-selection`

Runtime skill:

- `graph_harness.source_relevance`

Its job:

1. Read the active research goal and follow-up instructions.
2. Inspect prior runs, source results, source documents, proposals, review
   items, and graph state.
3. Decide which sources to search or re-search.
4. Generate source-specific search plans.
5. Rank returned records for relevance, novelty, and evidence value.
6. Skip duplicates, off-topic records, weak records, and already-reviewed
   records.
7. Create handoffs only for selected records.
8. Send selected records into extraction/proposal workflows.
9. Save a clear artifact explaining why each record was selected, skipped, or
   deferred.
10. Preserve uncertainty, caveats, and contradiction signals for reviewer
    judgment.

## Target User Experience

The main API should feel like this:

```http
POST /v2/spaces/{space_id}/evidence-runs
```

Example request:

```json
{
  "goal": "Find evidence linking MED13 variants to congenital heart disease.",
  "instructions": "Prioritize human clinical evidence and variant databases.",
  "sources": ["pubmed", "clinvar", "marrvel", "uniprot"],
  "proposal_mode": "review_required"
}
```

Then the user inspects progress and proposals:

```http
GET /v2/spaces/{space_id}/runs/{run_id}
GET /v2/spaces/{space_id}/runs/{run_id}/artifacts
GET /v2/spaces/{space_id}/review-items
```

Follow-up work should build on the same research space:

```http
POST /v2/spaces/{space_id}/evidence-runs/{evidence_run_id}/follow-ups
```

Example follow-up:

```json
{
  "instructions": "Now focus on neurodevelopmental phenotypes and loss-of-function variants."
}
```

The lower-level endpoints stay available as advanced building blocks:

```http
GET  /v2/sources
POST /v2/spaces/{space_id}/sources/{source_key}/searches
GET  /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}
POST /v2/spaces/{space_id}/sources/{source_key}/searches/{search_id}/handoffs
```

These should be documented as advanced/debug APIs, not the normal researcher
front door.

## User Guide Impact

When this plan is implemented, `docs/user-guide` should be reorganized around
the goal-driven evidence run as the default path.

The main user-guide flow should become:

1. Create or open a research space.
2. Start an evidence run with a goal, instructions, source preferences, and
   scientific constraints.
3. Let the harness search, select relevant records, create handoffs, and stage
   extraction outputs.
4. Inspect run progress, artifacts, and evidence-selection explanations.
5. Review proposals and review items.
6. Add follow-up ideas to the same research space.
7. Promote only reviewed evidence into trusted graph knowledge.

The lower-level source endpoints should move to an advanced/debug section:

- source registry inspection;
- direct source search;
- saved source-search retrieval;
- selected-record handoff;
- run events/artifacts/policy-decision inspection.

The guide should make clear that normal researchers do not need to manually
operate every source endpoint or select every source record. They should give
the research goal and review the staged evidence outputs.

## Target Architecture

```text
User goal or follow-up instruction
  -> evidence-selection harness run
  -> workspace snapshot
       - prior goals
       - prior searches
       - handoffs
       - source documents
       - proposals
       - review decisions
       - graph state summary
  -> source plan
  -> source searches
  -> agent relevance ranking
  -> selected record handoffs
  -> extraction and normalization
  -> proposals or review items
  -> human/governance review
  -> approved graph updates
```

## Artana Kernel And Harness Boundary

Use Artana Kernel harness machinery for the intelligence layer, but keep the
responsibilities clean.

The `BaseHarness` wrapper should remain a thin execution adapter:

```text
run record
  -> harness_id
  -> worker
  -> BaseHarness wrapper
  -> workflow implementation
```

The actual agent behavior should live in:

- a new runtime skill, `graph_harness.source_relevance`;
- a skill-aware autonomous agent runner;
- deterministic tools for listing sources, reading saved search results,
  creating searches, creating handoffs, reading workspace state, and staging
  proposals.

Do not build a separate one-off planner that bypasses the existing runtime skill
and harness path.

## Implementation Phases

### Phase 1: Product Contract And Naming

Goal: define the public workflow around a living research space.

- [x] Choose the final user-facing name: `evidence-runs`,
  `research-runs`, or another product term.
- [x] Define the first request model with `goal`, `instructions`, source
  preferences, budget, and review mode.
- [x] Add optional scientific protocol fields: inclusion criteria, exclusion
  criteria, population/context, evidence types, and priority outcomes.
- [x] Define the follow-up request model for adding new ideas to an existing
  research space.
- [x] Define response models that return run id, status, selected sources, and
  links to artifacts/review items.
- [x] Decide which existing endpoints become the main path and which become
  advanced/debug.
- [x] Update OpenAPI after the route contract is implemented.

### Phase 2: Workspace Memory And Snapshot

Goal: make each new run aware of previous work in the same research space.

- [x] Build a workspace snapshot service for the evidence-selection harness.
- [x] Include previous goals and follow-up instructions.
- [x] Include prior source documents and handoff-derived source metadata.
- [x] Include source documents and extraction state.
- [x] Include proposals, review items, approvals, rejections, and unresolved
  items.
- [x] Include a compact graph-state summary from approved evidence.
- [x] Add deduplication fingerprints for records, handoffs, and proposals.
- [x] Add tests showing follow-up runs can see previous run state.

### Phase 3: Source Relevance Skill And Tools

Goal: give the harness a controlled way to decide what evidence records matter.

- [x] Add `services/artana_evidence_api/runtime_skills/.../source_relevance/SKILL.md`.
- [x] Define the skill instructions: relevance, novelty, source fit,
  provenance, duplicate avoidance, and review caution.
- [x] Require the skill to separate candidate evidence from reviewed evidence
  and trusted graph knowledge.
- [x] Require inclusion/exclusion reasons for selected, skipped, and deferred
  records.
- [x] Require quality caveats for weak, indirect, conflicting, or
  association-only evidence.
- [x] Add or expose deterministic tools for:
  - [x] listing available source capabilities;
  - [x] creating supported structured source searches;
  - [x] reading saved source-search results;
  - [x] creating selected-record handoffs;
  - [x] reading prior workspace state;
  - [x] staging extraction/proposal work.
- [x] Gate tool access through the existing runtime skill registry.
- [x] Add tests for skill registry validation and allowed tool names.

### Phase 4: Evidence-Selection Harness

Goal: add the actual harness that performs goal-driven source selection.

- [x] Add a harness template for `evidence-selection`.
- [x] Add the runtime wrapper in `harness_runtime.py`.
- [x] Add worker support for the new `harness_id`.
- [x] Implement the deterministic baseline workflow:
  - [x] load workspace snapshot;
  - [x] route source planning through an auditable planner seam;
  - [x] let the planner return executable source searches for the runtime;
  - [x] validate planner-added source searches before execution;
  - [x] enable a model-mediated agent to generate source plans from goal-only
    requests;
  - [x] run supported live structured source searches within budget;
  - [x] time out slow live source searches and complete with auditable errors;
  - [x] rank saved source-search records;
  - [x] create handoffs for selected records;
  - [x] emit artifacts explaining selection and skipped records;
  - [x] emit uncertainty, contradiction, and evidence-quality caveats;
  - [x] hand selected records to review-gated proposal/review-item paths.
- [x] Keep deterministic fallback behavior when model execution is disabled.
- [x] Add unit tests for happy path, budget stop, shadow mode, duplicate
  records, live source-search creation, and review staging.

### Phase 5: Iterative Follow-Up Runs

Goal: let a researcher keep building the same space over time.

- [x] Add the follow-up endpoint or command.
- [x] Link follow-up runs to a parent run and the same research space.
- [x] Store follow-up instructions as durable run input.
- [x] Make the harness compare new instructions with previous work.
- [x] Prevent repeated handoffs for already captured source records.
- [x] Let the harness explicitly re-search a source with new search keys.
- [x] Add tests for follow-up runs that expand, narrow, and correct the prior
  research direction.

### Phase 6: Extraction And Proposal Integration

Goal: selected records should become reviewable evidence outputs, not just saved
documents.

- [x] Route variant-like selected records through variant-review proposal
  staging.
- [x] Route saved PubMed/literature records through literature-review proposal
  staging.
- [x] Define source-specific extraction policy for UniProt, AlphaFold,
  DrugBank, ClinicalTrials.gov, MGI, and ZFIN.
- [x] Stage source-specific proposals and normalized reviewer payloads for
  non-variant sources.
- [x] Fail loudly when a selected source has no extraction policy.
- [x] Require a review-item store in guarded mode instead of silently using an
  in-memory fallback.
- [x] Add live PubMed and MARRVEL source-search creation to the evidence-run
  runner.
- [x] Stage source documents only; do not directly promote graph facts.
- [x] Stage proposals and review items only; do not directly promote graph
  facts.
- [x] Preserve source-search id, selected record id/hash, and
  source capture metadata on proposals.
- [x] Preserve evidence type, source family, uncertainty, and reviewer-facing
  limitations on proposals.
- [x] Add regression tests proving graph promotion remains review-gated.

### Phase 7: Documentation, QA, And Rollout

Goal: make the new path the clear product front door while preserving advanced
APIs.

- [x] Update user guide docs to teach goal-driven evidence runs first.
- [x] Reorder `docs/user-guide` so the first workflow is space -> evidence run
  -> review proposals -> follow up.
- [x] Move direct source-search/handoff docs into an advanced/debug section.
- [x] Add examples for iterative follow-up runs in the same research space.
- [x] Add science-side warnings: not clinical advice, not automatic regulatory
  evidence, not causal truth, and not a systematic review unless protocol fields
  and accounting are used.
- [x] Update architecture docs to describe research space as a living workspace.
- [x] Add API migration notes if route aliases are introduced.
- [x] Run focused unit and route tests.
- [x] Run Evidence API service checks.
- [x] Run full repo checks before merge when code changes are complete.
- [x] Use Claude second-opinion before final closeout.

## Validation And Testing Strategy

Validation must prove more than "the agent produced plausible text." It must
prove that the harness finds useful evidence, skips weak or irrelevant records,
preserves provenance, avoids duplicates, and keeps humans in control.

### Engineering Tests

- [x] Unit-test workspace snapshot construction.
- [x] Unit-test source planning with deterministic model/tool fakes.
- [x] Unit-test record ranking, selection, skip reasons, and deferred reasons.
- [x] Unit-test duplicate detection across prior searches, handoffs, proposals,
  and review decisions.
- [x] Unit-test handoff creation from selected records.
- [x] Unit-test source failure handling and partial-run behavior.
- [x] Route-test starting a goal-driven evidence run.
- [x] Route-test follow-up runs in the same research space.
- [x] Integration-test worker execution for the new harness.
- [x] Regression-test that graph promotion never happens without review.

### Fixture Benchmarks

Create offline benchmark fixtures so the harness can be tested without live
external APIs:

```text
services/artana_evidence_api/tests/fixtures/evidence_selection/
  med13_congenital_heart_disease/
    source_results.json
    expected_selected.json
    expected_skipped.json
    expected_proposals.json
  brca1_breast_cancer/
  cftr_cystic_fibrosis/
  mecp2_rett_syndrome/
  tp53_li_fraumeni/
```

Each benchmark should define:

- research goal and instructions;
- available source-search results;
- records expected to be selected;
- records expected to be skipped;
- known duplicates;
- known weak/indirect evidence;
- known contradictory or uncertain evidence;
- expected proposal/review-item shape.

Track metrics:

- recall of important records;
- precision of selected records;
- duplicate rate;
- provenance completeness;
- quality of selected/skipped/deferred reasons;
- reviewer agreement;
- high-severity overclaim count.

### Shadow And Guarded Rollout

Start with shadow mode:

- [x] The harness recommends source searches and selected records.
- [x] It does not create handoffs automatically.
- [x] Add a validation helper and review template to compare harness selections
  with human selections.
- [x] Record false positives, false negatives, duplicate suggestions, and
  explanation quality in validation reports/templates.
- [ ] Run real shadow-mode comparisons with human reviewers.

Move to guarded mode only after shadow-mode results are acceptable:

- [x] Allow handoff creation under budget and source limits.
- [x] Keep all extraction outputs review-gated.
- [x] Require complete provenance and selection reasons.
- [x] Emit artifacts for selected, skipped, and deferred records.
- [x] Stop or downgrade when sources fail, evidence is too weak, or the request
  asks for clinical/regulatory/causal conclusions.

### Scientific Review

Use small expert-review studies before calling the harness production-ready:

- [ ] Give the same goal and source result set to the harness and to a human
  reviewer.
- [ ] Compare selected records and skipped records.
- [ ] Have reviewers score relevance, completeness, novelty, provenance,
  uncertainty handling, and overclaiming.
- [ ] Track whether the harness saves review time without lowering evidence
  quality.
- [ ] Update benchmark fixtures from expert feedback.

### Production Readiness Gates

Before production rollout:

- [x] Direct graph promotion without review is impossible.
- [x] Provenance completeness is effectively 100%.
- [x] Every selected record has a reason.
- [x] Every skipped/deferred record that affects the evidence picture has a
  reason.
- [x] Duplicate handoffs/proposals are prevented or explicitly linked.
- [ ] High-severity overclaiming is zero in benchmark and shadow-mode review.
- [x] Source failures are graceful and auditable.
- [x] Live external API tests remain opt-in but have documented local commands.

## Acceptance Criteria

- A user can start from a high-level research goal without manually choosing
  every source endpoint and search result.
- A user can add follow-up ideas to the same research space without starting
  over.
- A user can provide scientific constraints such as inclusion criteria,
  exclusion criteria, evidence type preferences, and priority outcomes.
- The harness reads previous results and avoids unnecessary duplicate work.
- The harness selects relevant source records and creates handoffs
  automatically.
- Every selected record has an auditable reason and provenance trail.
- Skipped and deferred records have auditable reasons when they affect the
  evidence picture.
- The system makes uncertainty, contradictions, and evidence quality caveats
  visible to reviewers.
- Extraction creates proposals or review items, not trusted graph facts.
- Human/governance review remains the promotion gate.
- Lower-level source/search/handoff endpoints remain available for advanced
  usage.
- API docs and `docs/user-guide` make the goal-driven harness the front door.
- User-guide examples teach follow-up runs as normal research behavior.
- Product docs explicitly say this is not an automatic clinical, regulatory, or
  causal-truth engine.

## Open Design Questions

- Should the public product name be `evidence-runs`, `research-runs`, or
  `research-sessions`?
- Should follow-up instructions attach to a previous run, directly to the
  research space, or both?
- How much autonomy should the first version have: select from already-saved
  source results only, or also launch new searches?
- What budget limits should apply per source and per run?
- Should skipped records be stored as first-class decisions, or only summarized
  in artifacts?
- Which non-variant sources get full source-specific extraction first?
- Should evidence quality use a simple internal scale first, or align early
  with external review conventions such as GRADE-style certainty language?
- Which output, if any, should support PRISMA-style search and selection
  accounting for formal review workflows?

## Progress Checklist

- [x] Product contract chosen.
- [x] Public route plan finalized.
- [x] Workspace snapshot service implemented.
- [x] Source relevance runtime skill added.
- [x] Evidence-selection harness template registered.
- [x] Worker can execute the new harness.
- [x] Harness can create supported structured source searches.
- [x] Harness can rank and select saved source records.
- [x] Harness can create durable handoffs.
- [x] Harness can trigger extraction/proposal staging.
- [x] Follow-up runs reuse previous space state.
- [x] Duplicate captured source records are avoided.
- [x] Selected, skipped, and deferred records carry reasons.
- [x] Evidence caveats and uncertainty are visible in outputs.
- [x] Review gate is preserved.
- [x] User guide front door updated.
- [x] Advanced/debug source endpoint docs separated.
- [x] Follow-up run guide added.
- [x] Scientific guardrails documented for users.
- [x] OpenAPI updated.
- [x] Offline benchmark fixtures added.
- [x] Shadow-mode validation artifacts supported.
- [x] Guarded rollout gates defined.
- [x] Expert-review validation process documented.
- [x] Tests and service checks pass.
