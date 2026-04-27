# Issues #16 And #17 Evidence Discovery Tracker

Status date: April 27, 2026.

This file is the working progress tracker for:

- [#16 Clarify source boundaries before scaling agentic evidence selection](https://github.com/med13foundation/artana-evidence-platform/issues/16)
- [#17 Build agentic evidence discovery on top of durable source search](https://github.com/med13foundation/artana-evidence-platform/issues/17)

This tracker now records the docs-first pass plus the first implementation
slice for source boundaries and agentic evidence discovery. It does not change
public API contracts, OpenAPI artifacts, migrations, or generated coverage
files.

## Origin / Superseded Plan

The previous long plan described the first-principles product loop:

```text
research space
  -> agent selects relevant source records from a goal and instructions
  -> selected records become source documents and reviewable proposals
  -> human/governance review decides what becomes trusted graph knowledge
```

That direction still stands. The old phase checklist is now superseded because
the checked-out repo already contains much of the evidence-selection baseline.
This tracker keeps the original principle but separates landed implementation
from the remaining work in issues #16 and #17.

## Product Guardrails

These guardrails are still active product requirements, not historical notes:

- The agent is the first relevance filter; the human/governance workflow is the
  trust gate.
- Retrieved records and extracted outputs are candidate evidence, not trusted
  graph knowledge.
- Agentic discovery must not make clinical, diagnostic, regulatory, causal, or
  treatment recommendations.
- A run is not a systematic review unless protocol fields, search accounting,
  exclusion accounting, and human review decisions are captured.
- Evidence outputs must preserve source provenance, stable source identifiers
  or record hashes, selection/skipped/deferred reasons, source family, evidence
  type, uncertainty, and reviewer-facing caveats.
- Live external API checks remain opt-in because they depend on credentials,
  source availability, network behavior, and rate limits.

## Current Live State

These items are backed by files in the current checkout. They should still be
re-verified with service checks before any issue is closed.

- Evidence API owns the goal-driven workflow. Graph persistence and trusted
  graph governance remain outside this tracker in `services/artana_evidence_db`.
- Public evidence-run routes exist through
  `services/artana_evidence_api/routers/v2_public.py` and
  `services/artana_evidence_api/routers/evidence_selection_runs.py`.
- The evidence-selection runtime exists in
  `services/artana_evidence_api/evidence_selection_runtime.py` and queues
  `harness_id="evidence-selection"`.
- Harness registration and worker execution know about `evidence-selection` in
  `services/artana_evidence_api/harness_registry.py`,
  `services/artana_evidence_api/harness_runtime.py`, and
  `services/artana_evidence_api/worker.py`.
- The source-relevance runtime skill exists at
  `services/artana_evidence_api/runtime_skills/orchestration/source_relevance/SKILL.md`.
- Model and deterministic source planning exist through
  `services/artana_evidence_api/evidence_selection_model_planner.py` and
  `services/artana_evidence_api/evidence_selection_source_planning.py`.
- Typed source-query playbooks now live in
  `services/artana_evidence_api/evidence_selection_source_playbooks.py`.
  They define source-specific objective intents, required inputs, query-payload
  builders, interpretation hints, handoff eligibility, and non-goals for all
  direct-search sources.
- Supported live source-search execution exists through
  `services/artana_evidence_api/evidence_selection_source_search.py`, reusing
  existing direct-search gateway behavior rather than introducing parallel
  source clients.
- Source-owned record policies now live in
  `services/artana_evidence_api/source_policies.py`. Handoff provider IDs,
  source families, normalized selected-record payloads, target kind, and
  variant-aware recommendation rules are read through these policies instead
  of growing central handoff maps.
- Durable selected-record handoff exists through
  `services/artana_evidence_api/source_search_handoff.py`.
- Review-gated extraction/proposal behavior is represented in
  `services/artana_evidence_api/evidence_selection_extraction_policy.py` and
  the proposal/review-item staging paths called by the runtime.
- Product and validation docs already describe the evidence-selection harness
  and shadow-review validation in:
  - `docs/architecture/evidence-selection-harness.md`
  - `docs/validation/evidence-selection-validation.md`
  - `docs/validation/evidence-selection-review-template.md`
- Focused tests already exist for the main evidence-selection surfaces:
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py`
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_router.py`
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_model_planner.py`
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py`
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_benchmarks.py`
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_validation.py`
  - `services/artana_evidence_api/tests/unit/test_evidence_selection_extraction_policy.py`
  - `services/artana_evidence_api/tests/unit/test_source_boundary_contract.py`
  - `services/artana_evidence_api/tests/unit/test_source_search_handoff.py`

## Issue #16 Tracker: Source Boundaries

Issue #16 is no longer about inventing the whole harness. It is about making
source responsibilities clearer before more sources are added.

### Done

- Source metadata and capability discovery are centralized in
  `services/artana_evidence_api/source_registry.py`.
- Direct source-search request/response models and durable search storage live
  in `services/artana_evidence_api/direct_source_search.py`.
- Evidence-selection source execution is separated into
  `EvidenceSelectionSourceSearchRunner`, which calls existing direct-search
  services instead of bypassing them.
- Selected-record handoff has a durable service path and tests.
- The architecture docs say the harness coordinates lower-level endpoints and
  does not replace them.
- `services/artana_evidence_api/source_policies.py` owns record-level handoff
  policy for PubMed, MARRVEL, ClinVar, ClinicalTrials.gov, UniProt, AlphaFold,
  DrugBank, MGI, and ZFIN.
- `source_search_handoff.py` now derives durable handoff support from
  `source_record_policies()` and delegates provider-id extraction,
  source-family selection, normalized record payloads, and variant-aware hints
  to the policy layer.
- `SourceDefinition` now rejects `direct_search_enabled=True` unless both
  request and result schema refs are present.
- `test_source_boundary_contract.py` proves policy/registry alignment for all
  direct-search sources and gives focused coverage for a simple source
  (`clinical_trials`) and a variant-aware source (`clinvar`).

### Needs Verification

- Confirm the latest `make artana-evidence-api-service-checks` result on this
  branch before marking #16 implementation slices as fully current.
- Confirm OpenAPI remains stable if future source-boundary docs mention
  public contracts.
- Confirm route tests still cover generic source search, source lookup, and
  handoff compatibility after any doc wording changes.

### Remaining

- Document the source-boundary ownership model explicitly:
  - source registry owns public source metadata and capability flags;
  - direct source search owns typed query execution and durable search capture;
  - evidence-selection planning owns goal-to-query intent conversion;
  - source handoff owns selected-record normalization and source-document
    creation;
  - extraction policy owns review/proposal staging behavior.
- Continue moving future source-specific handoff behavior behind
  source-owned policy helpers instead of central source-key maps.
- Decide whether repeated direct-search execution patterns should be extracted
  into a small helper without changing route shapes or typed response schemas.
- Keep any future refactor incremental. Do not introduce a broad
  `EvidenceSourceAdapter` protocol until the harness/tool contract proves it
  is needed.

### Out Of Scope For #16

- Graph-service schema or governance rewrites.
- Frontend work.
- Removing typed source request/response models.
- Collapsing public source contracts into opaque JSON.

## Issue #17 Tracker: Agentic Evidence Discovery

Issue #17 tracks the agentic layer above durable source search. The current
repo already has a goal-driven evidence-selection baseline, so the remaining
work is to make the discovery contract, validation, and rollout criteria clear.

### Done

- `POST /v2/spaces/{space_id}/evidence-runs` is the documented front door.
- Follow-up runs are documented as the normal iterative path for a living
  research space.
- `planner_mode="model"` and `planner_mode="deterministic"` are represented in
  the evidence-selection route/runtime contract.
- Model source-planner output is validated before it becomes executable source
  searches.
- Source-planning payload builders cover PubMed, MARRVEL, ClinVar,
  ClinicalTrials.gov, UniProt, AlphaFold, DrugBank, MGI, and ZFIN.
- Source-planning payload builders now live behind explicit typed playbooks in
  `evidence_selection_source_playbooks.py`, rather than being implicit adapter
  branches inside the model planner.
- Qualitative relevance labels are emitted in selected/skipped/deferred
  decisions and copied into review-item metadata and the durable
  `evidence_selection_decisions` artifact.
- Live source-search creation now requires explicit `live_network_allowed=true`
  on evidence-selection run and follow-up requests. Runtime validation also
  rejects planner-created live source searches when the flag is false.
- Manual and planner-created live source-search payloads are validated against
  source-specific typed contracts before external source side effects.
- Runtime budgets cap planned live source searches, candidate searches,
  per-search records, per-search timeout, aggregate live source-search phase
  time, and guarded handoff count.
- Model-created source searches have an additional 5-search cap, separate from
  the public 50-search explicit live-search request limit.
- The runtime records selected, skipped, and deferred records as auditable
  evidence-selection output.
- Guarded mode creates review-gated downstream work; it must not promote graph
  facts directly.
- Offline benchmark fixtures exist under
  `services/artana_evidence_api/tests/fixtures/evidence_selection/`, but the
  current inventory is MED13-only and is not production-representative.
- Validation helpers exist for shadow/expert review comparisons.

### Needs Verification

- Run the focused evidence-selection tests and record the exact result in the
  verification log.
- Run `make artana-evidence-api-service-checks` and record the exact result
  in the verification log.
- Confirm the current offline benchmark fixture inventory and whether it covers
  only MED13 or additional disease/gene cases.
- Confirm whether real shadow-mode comparisons with human reviewers have been
  run. If not, keep production-readiness unchecked.
- Confirm the current service behavior for model unavailable, credential
  missing, unsupported source, live-network-disabled, source timeout, and
  duplicate handoff replay cases.

### Remaining

- Keep the agentic discovery docs aligned with the code-level playbook
  registry and qualitative relevance labels.
- Keep budget expectations current as source counts, timeout defaults, or
  model/tool call limits change.
- Document how model-planned source searches are bounded by source allowlists,
  max search count, max records, timeout, live-network opt-in, and review
  controls.
- Connect the validation docs to concrete acceptance criteria:
  precision/recall where benchmark labels exist, duplicate rate, provenance
  completeness, explanation quality, reviewer agreement, and zero
  high-severity overclaiming.
- Keep live external API validation opt-in. Do not make network or credential
  dependent checks normal CI requirements.

### Out Of Scope For #17

- Direct graph promotion from agentic discovery.
- Clinical, diagnostic, regulatory, or causal-truth claims.
- Mandatory live external API tests in normal CI.
- A new frontend.
- A monolithic PR that implements all remaining architecture cleanup at once.

## Close Criteria

#16 closes when the source-boundary ownership model is documented for registry,
direct search, source planning, handoff, and extraction policy, and tests or
contract checks cover one simple source plus one variant-aware source without
changing public route shapes.

#17 closes when the agentic discovery contract is documented end to end,
focused tests and service checks pass, validation gates are tied to benchmark
or reviewer evidence, and production-readiness still requires zero
high-severity overclaiming plus at least three distinct real shadow-mode
research questions with human-review notes.

This implementation slice is ready to stage only after focused tests, service
checks, diff hygiene, and Claude second-opinion review are recorded below.
`coverage.xml` should remain unstaged unless the user explicitly asks to
include generated coverage churn.

## Subagent Orchestration Plan

Use this section to coordinate implementation work without turning #16/#17 into
one monolithic PR.

### Linear Foundation Lane

These steps must happen in order because they define the contract that parallel
workers will build against.

1. Contract/docs owner:
   - Owns `docs/architecture/source-boundaries.md`,
     `docs/architecture/evidence-selection-harness.md`,
     `docs/validation/evidence-selection-validation.md`, and this tracker.
   - Defines source-boundary ownership for registry, direct search, source
     planning, handoff, and extraction policy.
   - Defines the agentic discovery decisions: source selection, query
     formulation, record relevance, and handoff decision.
   - Records current budget defaults and fallback behavior as policy, not as
     hidden implementation trivia.
2. Dispatcher scaffold owner, only if code refactor starts:
   - Owns the smallest source-policy dispatcher shape.
   - Keeps public route shapes and typed source schemas unchanged.
   - Lands before any source-family worker edits handoff behavior.
3. Release criteria owner:
   - Waits until contract docs and validation fixtures settle.
   - Converts benchmark and shadow-review results into close criteria for #17.

### Parallel Group A: Source Boundaries (#16)

Start after the contract/docs owner has named the policy fields.

- Registry/contract worker:
  - Owns `services/artana_evidence_api/source_registry.py`,
    `services/artana_evidence_api/tests/unit/test_source_registry.py`, and a
    future `test_source_boundary_contract.py`.
  - Proves one simple source and one variant-aware source expose the required
    boundary fields.
- Variant-aware handoff worker:
  - Owns a narrow source-policy slice for ClinVar or another variant-aware
    source plus focused calls from
    `services/artana_evidence_api/source_search_handoff.py`.
  - Extends `services/artana_evidence_api/tests/unit/test_source_search_handoff.py`.
- Simple-source handoff worker:
  - Owns a narrow source-policy slice for a simple non-variant source such as
    ClinicalTrials.gov.
  - Proves normalized source-document behavior without touching public route
    contracts.
- Direct-search helper worker:
  - Defer unless duplication becomes the blocking problem.
  - If needed, owns only helper extraction in
    `services/artana_evidence_api/direct_source_search.py` and
    `services/artana_evidence_api/evidence_selection_source_search.py`.
  - Must not alter typed request/response schemas or OpenAPI output.

### Parallel Group B: Agentic Discovery (#17)

Start after the agentic-discovery contract is documented.

- Budget/model worker:
  - Owns model fallback, planned-search caps, per-search timeout,
    max-records-per-search, max-handoff behavior, and how fallback is surfaced
    in source-plan artifacts/results.
  - Keeps budget concerns separate from model-unavailable fallback behavior.
- Runtime edge worker:
  - Owns focused verification for model unavailable, missing credentials,
    unsupported source, source timeout, disallowed source, duplicate handoff
    replay, and no trusted graph write.
  - Extends evidence-selection runtime/router/model-planner tests as needed.
- Validation fixture worker:
  - Owns `services/artana_evidence_api/tests/fixtures/evidence_selection/`,
    `services/artana_evidence_api/tests/unit/test_evidence_selection_benchmarks.py`,
    and validation docs.
  - Expands beyond the current MED13-only fixture before production-readiness
    is claimed.
- Shadow-review worker:
  - Owns reviewer-template examples and comparison-helper usage.
  - Records human-review comparison results when real reviewer data exists.

### Linear QA Lane

Run this lane after worker changes settle. Do not parallelize commands that
rewrite generated artifacts.

1. Verify intended diff:
   - `git status --short`
   - `git diff --name-only`
   - Confirm OpenAPI/type artifacts changed only if the contract changed.
   - Keep `coverage.xml` unstaged or revert it after coverage runs unless the
     user explicitly requests coverage artifact updates.
2. Run focused checks:
   - `make artana-evidence-api-lint`
   - `make artana-evidence-api-type-check`
   - `make artana-evidence-api-boundary-check`
   - `make artana-evidence-api-contract-check`
   - Focused evidence-selection/source-boundary pytest commands.
3. Run issue-close gates:
   - `make artana-evidence-api-service-checks`
   - `make service-checks`
4. Run opt-in live checks only when local services, network access, and
   credentials are intentionally available:
   - `make live-endpoint-contract-check`
   - `make live-external-api-check`
5. Record final evidence in this tracker:
   - command;
   - exit code/result;
   - important warnings/errors;
   - post-run `git status --short`;
   - OpenAPI artifact status;
   - `coverage.xml` decision;
   - Claude second-opinion outcome.

### Subagent Grouping Summary

| Group | Workstream | Parallel? | Must Wait For |
| --- | --- | --- | --- |
| Linear 0 | Contract/docs owner | No | Current tracker |
| A1 | Registry/contract worker | Yes | Linear 0 |
| A2 | Variant-aware handoff worker | Yes | Linear 0, dispatcher if used |
| A3 | Simple-source handoff worker | Yes | Linear 0, dispatcher if used |
| A4 | Direct-search helper worker | Optional | Only if duplication blocks closure |
| B1 | Budget/model worker | Yes | Linear 0 |
| B2 | Runtime edge worker | Yes | Linear 0 |
| B3 | Validation fixture worker | Partly | Linear 0 for labels/criteria |
| B4 | Shadow-review worker | Later | Real reviewer data |
| Linear 1 | Release criteria owner | No | A/B results |
| Linear 2 | QA/release owner | No | All intended changes settled |

## This Docs Pass

### Changes

- [x] Replaced the obsolete long `docs/plan.md` body with a focused #16/#17
  tracker.
- [x] Preserved the original first-principles product loop as a short origin
  note.
- [x] Recorded code-backed current state with paths and test references.
- [x] Separated #16 source-boundary debt from #17 agentic-discovery rollout
  criteria.
- [x] Marked production validation as needing verification instead of claiming
  it is complete.
- [x] Added subagent orchestration groups for parallel and linear workstreams.
- [x] Started implementation with subagents by adding source-boundary
  architecture docs and tightening evidence-selection validation/contract docs.
- [x] Added source-owned record policies for handoff normalization,
  provider-id extraction, source-family metadata, target kind, and
  variant-aware hints.
- [x] Added explicit source-query playbooks for all direct-search sources.
- [x] Added qualitative relevance labels to selection decisions, review-item
  metadata, and durable decision artifacts.
- [x] Added explicit `live_network_allowed` opt-in for live source searches and
  early typed payload validation for manual/planner-created source searches.

### Validation Gates Before Issue Close

- Must pass before #17 close: focused evidence-selection unit tests.
- Must pass before #16/#17 close: `make artana-evidence-api-service-checks`.
- Must pass before a broad release/merge closeout: `make service-checks`.
- Must confirm before staging this docs-only pass: OpenAPI artifacts are
  unchanged.
- Must keep out of this docs-only pass: `coverage.xml` unless explicitly
  requested by the user.

### Remaining

- Keep source-boundary architecture docs updated as future source families add
  policy fields.
- Keep future handoff behavior moving to source-owned policy helpers.
- Expand the validation tracker with the current benchmark fixture inventory.
- Record real shadow-mode human-review comparison results when available.
- Keep `docs/README.md` linked to new architecture docs as they are added.

### Out Of Scope

- Code refactors during this docs-first pass.
- Public API changes during this docs-first pass.
- OpenAPI regeneration during this docs-first pass.
- Graph-service schema or trusted-governance changes.
- Frontend work.

## Open Questions

- #16: Should handoff source-key maps move into source-owned policy helpers, or
  should they stay centralized until another source family is added?
- #16: Is a small direct-search execution helper enough, or is a formal
  `EvidenceSourceAdapter` protocol eventually justified?
- #17: Which qualitative relevance labels are stable enough to document as a
  contract?
- #17: What default budgets should apply to first-pass discovery versus
  follow-up discovery?
- #17: Which validation threshold should be required before moving beyond
  shadow-mode human review?

## Verification Log

Use this section as the append-only log for actual observations on this issue
pair. Planned commands belong in the validation gates above until they are run.

### Documentation-Only Pass

- `gh issue view 16 --repo med13foundation/artana-evidence-platform --json number,title,state,url`
  - Result: issue #16 is open.
- `gh issue view 17 --repo med13foundation/artana-evidence-platform --json number,title,state,url`
  - Result: issue #17 is open.
- `git diff -- docs/plan.md`
  - Result: docs-only tracker replacement reviewed.
- `git diff --check`
  - Result: passed.
- File/path inventory check with `rg`
  - Result: evidence-selection runtime, router, skill, planner, handoff,
    validation, and focused test paths listed above exist in the checkout.
- OpenAPI artifacts
  - Result: no OpenAPI files changed during this docs-only pass.
- `coverage.xml`
  - Result: already modified before this docs pass; do not include it in this
    docs-first change unless explicitly requested.
- Claude second-opinion review
  - Result: completed after the first tracker diff existed; useful feedback was
    folded into product guardrails, close criteria, open questions, and this
    verification log.
- Subagent orchestration review
  - Result: three read-only explorers inspected #16 source boundaries, #17
    agentic discovery/validation, and QA/release sequencing. Their findings
    were folded into the subagent orchestration plan above.
- Implementation start with subagents
  - Result: source-boundary architecture contract added, evidence-selection
    harness contract updated, validation docs clarified, review template
    clarified, and docs index linked to the new source-boundary note.
  - Result: product-facing evidence-run docs kept on `/v2/spaces/{space_id}/evidence-runs`;
    lower-level `/v1/spaces/{space_id}/agents/evidence-selection/runs` routes
    are documented as compatibility/harness-oriented routes.
- Final combined Claude second-opinion review
  - Result: completed after subagent docs landed; follow-up fixes tightened the
    source-policy target-kind wording, direct-search schema-name requirement,
    MED13-only fixture caveat, shadow-mode readiness gate, and `/v2` versus
    `/v1` route language.

### Implementation Pass

- `gh issue view 16 --repo med13foundation/artana-evidence-platform --json number,title,state,body,labels,comments`
  - Result: issue #16 is open; source-boundary acceptance criteria were
    refreshed from the live GitHub issue body.
- `gh issue view 17 --repo med13foundation/artana-evidence-platform --json number,title,state,body,labels,comments`
  - Result: issue #17 is open; agentic-discovery acceptance criteria were
    refreshed from the live GitHub issue body.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_model_planner.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py -q`
  - Result: passed, `32 passed`.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_boundary_contract.py services/artana_evidence_api/tests/unit/test_source_search_handoff.py services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_model_planner.py -q`
  - Result: passed, `51 passed`.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_source_boundary_contract.py services/artana_evidence_api/tests/unit/test_source_registry.py services/artana_evidence_api/tests/unit/test_source_search_handoff.py services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_evidence_selection_model_planner.py services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py services/artana_evidence_api/tests/unit/test_evidence_selection_benchmarks.py -q`
  - Result: passed, `80 passed`.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py services/artana_evidence_api/tests/unit/test_evidence_selection_router.py -q`
  - Result: passed, `33 passed`, with one existing deprecation warning.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_runtime.py -q`
  - Result: passed, `20 passed`, after adding the aggregate source-search
    budget validator.
- `venv/bin/pytest services/artana_evidence_api/tests/unit/test_evidence_selection_plan_validation.py services/artana_evidence_api/tests/unit/test_evidence_selection_router.py services/artana_evidence_api/tests/unit/test_evidence_selection_source_playbooks.py services/artana_evidence_api/tests/unit/test_source_boundary_contract.py -q`
  - Result: passed, `44 passed`, after the Claude second-opinion fixes for
    model search caps, early live-network request validation, MARRVEL
    panel/taxon intent support, empty-object source-policy compaction, and
    focused plan-validation tests.
- `venv/bin/ruff check` on the touched Evidence API runtime, source-policy,
  source-playbook, handoff, router, and focused test files
  - Result: passed.
- `git diff --check`
  - Result: passed.
- `venv/bin/python scripts/export_artana_evidence_api_openapi.py --output services/artana_evidence_api/openapi.json`
  - Result: regenerated `services/artana_evidence_api/openapi.json` after the
    public `live_network_allowed` request-field addition.
- `make artana-evidence-api-service-checks`
  - Result: passed after OpenAPI regeneration and after the final
    plan-validation extraction. Live external API tests remained skipped unless
    their opt-in environment/services are available.
- `make service-checks`
  - Result: passed after the final plan-validation extraction. Graph checks,
    Evidence API checks, OpenAPI contract checks, architecture-size checks, and
    database-backed tests passed. Coverage was 87.63%, above the required 86%.
    Live external API and localhost service checks were skipped by their normal
    opt-in guards.
- OpenAPI artifacts
  - Result: `services/artana_evidence_api/openapi.json` changed intentionally
    because the public Evidence API request contract now includes
    `live_network_allowed`.
- `coverage.xml`
  - Result: generated/rewritten by `make service-checks`; keep it separate from
    the intentional implementation unless the PR policy wants generated
    coverage committed.
- Claude second-opinion review
  - Result: completed after the implementation diff. Claude had truncated diff
    context but flagged actionable risks around OpenAPI freshness,
    live-network opt-in, qualitative labels, source-policy registry parity,
    runtime budgets, architecture file size, and generated coverage churn. The
    code already had or was updated to include OpenAPI regeneration,
    `live_network_allowed`, source-policy/playbook parity tests,
    relevance-label artifact/review metadata tests, aggregate source-search
    budgets, and an extracted plan-validation module to satisfy the size gate.
- Final Claude second-opinion review
  - Result: completed against the staged #16/#17 diff with key implementation
    files included. Follow-up fixes added direct
    `evidence_selection_plan_validation` tests, an explicit 5-search cap for
    model-created searches, early request validation for goal-only model runs
    without live-network opt-in, explicit MARRVEL `taxon_id`/`panels` intent
    support, empty-object source-policy compaction, and required source-policy
    normalizer/variant functions.
