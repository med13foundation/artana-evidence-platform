# Evidence Selection Harness

The evidence-selection harness is the goal-driven front door for research
spaces. It does not replace the lower-level source endpoints; it coordinates
them.

## Product Shape

A research space is a living workspace, not a one-time job. A user can start
with a goal, let the harness search and select candidate source records, review
the staged outputs, and later add follow-up instructions in the same space.

The loop is:

```text
goal or follow-up instruction
  -> source searches or saved source-search results
  -> harness relevance selection
  -> source handoffs
  -> review-gated proposals and review items
  -> human approval before trusted graph promotion
  -> later follow-up in the same space
```

## Service Boundary

This harness lives in `services/artana_evidence_api` because it is workflow and
orchestration behavior. It reads and writes Evidence API state: runs,
documents, proposals, review items, durable source-search results, and source
handoffs.

It does not write approved graph facts directly. Trusted graph state remains
owned by `services/artana_evidence_db` and is reached through review and graph
service contracts.

## Current Runtime Contract

The product-facing public route is `POST /v2/spaces/{space_id}/evidence-runs`.
Follow-up runs use
`POST /v2/spaces/{space_id}/evidence-runs/{evidence_run_id}/follow-ups`.
The lower-level evidence-selection router still exists for harness-oriented
compatibility, but product docs should keep steering normal users to the
`/v2` front door.

The agentic-discovery contract has four bounded decisions:

- source selection: choose which allowed direct-search sources should be used;
- query formulation: turn the goal and instructions into normalized
  source-specific query payloads;
- record relevance: select, skip, or defer source-search records against the
  goal and reviewer criteria, whether the records came from searches created in
  this run or from existing durable search results;
- handoff decision: decide which selected records should become guarded source
  handoffs, proposals, and review items.

These are planning and triage decisions. They do not create approved graph
facts.

Each run uses `planner_mode="model"` by default. When the configured
query-generation model is available, the researcher can provide only a goal and
instructions plus `live_network_allowed=true`; the model planner selects a
bounded set of supported source searches and the runtime validates them before
any external source call. Goal-only model-planned runs without live-network
opt-in fail at request validation instead of queueing work that cannot execute.

Manual runs can set `planner_mode="deterministic"`. Deterministic runs must
provide at least one of:

- `source_searches`: source searches the harness should create and screen;
- `candidate_searches`: durable saved source-search results to screen.

If the model planner is unavailable, goal-only requests fail clearly. Explicit
source-search or candidate-search requests can fall back to deterministic
execution and record the fallback reason in the source-plan artifact.

## Budget And Fallback Policy

Current discovery is bounded by these policy defaults and validation limits:

- planning mode: `planner_mode="model"` can convert a goal into executable
  searches when a query-generation model and API key are configured;
  `planner_mode="deterministic"` screens explicit `source_searches` or
  `candidate_searches`;
- explicit-work fallback: if `planner_mode="model"` is requested but the model
  planner is unavailable, runs with explicit `source_searches` or
  `candidate_searches` fall back to deterministic planning and record the
  model-unavailable reason;
- model-unavailable failure: if no explicit source work is supplied and the
  model planner is unavailable, the request fails instead of inventing a search
  plan;
- live-network opt-in: `live_network_allowed=false` is the default. A run can
  screen saved `candidate_searches` without live-network access, but any run
  that creates live source searches, including goal-only model-planned runs,
  must explicitly set `live_network_allowed=true`;
- max planned searches: model-created searches are capped at 5 per run;
- max live searches: the public request accepts up to 50 explicit live source
  searches, and the runtime rejects planner output above that aggregate live
  search budget;
- max records per search: the request default is 3, with a validation range of
  1 to 100; model-requested record limits are capped by the run's
  `max_records_per_search`, and explicit planner output above that run limit is
  rejected before source execution;
- max handoffs: the request default is 20. Shadow mode can use 0 to 200, while
  guarded mode requires at least 1 handoff slot and accepts up to 200;
- per-search timeout: live source searches default to 120 seconds and planner
  output cannot exceed 120 seconds;
- candidate-evidence-only guardrail: selected records are staged as candidate
  evidence for review. The result explicitly records
  `approved_graph_facts_created: 0`.

The model planner output is validated for live-network opt-in, allowed source
keys, direct-search support, non-empty query payloads, record limits, search
count limits, and timeout limits before any external source call runs.

The harness can create supported live structured source searches, including
PubMed, MARRVEL, ClinVar, ClinicalTrials.gov, UniProt, AlphaFold, DrugBank,
MGI, and ZFIN, subject to each source's gateway availability and API keys.
Each live source search has a per-source timeout so one slow external source
does not block indefinitely. The default is service-defined, and callers can
set `timeout_seconds` on individual `source_searches` when a source is expected
to be faster or slower. Searches currently run sequentially inside a single
evidence run to keep source behavior and shared persistence simple. With the
current model-created search cap and default timeout, a worst-case source-search
phase can approach 10 minutes before model and persistence overhead; callers
should use async execution for broad or slow source mixes. A future slice can
add parallel execution with a run-level deadline if needed.

## Review Gate

Selected records are candidate evidence, not trusted evidence. Guarded mode can
create source handoffs, documents, proposals, and review items. It must not
promote facts into the trusted graph automatically.

Shadow mode records recommendations and reasons without creating handoffs.

## Scientific Boundaries

The harness is useful for evidence triage, hypothesis exploration, source
coverage, and keeping a research topic fresh. It is not, by itself:

- clinical advice;
- a diagnostic system;
- automatic regulatory-grade evidence;
- proof of causality;
- a systematic review unless the workflow also captures protocol fields,
  search accounting, exclusion accounting, and human review decisions.

Those boundaries should stay visible in product docs, artifacts, and reviewer
surfaces.

## Source Planning

The current implementation routes source planning through a dedicated planner
contract and records planner metadata in the source-plan artifact. The model
planner asks the configured Artana query-generation model for normalized search
intent, then service-local source adapters convert that intent into executable
payloads for PubMed, MARRVEL, ClinVar, ClinicalTrials.gov, UniProt, AlphaFold,
DrugBank, MGI, and ZFIN.

The planner remains behind budget, source allowlist, record-limit, timeout,
and review controls. It chooses what to search and what appears relevant; it
does not decide scientific truth or write approved graph facts.
