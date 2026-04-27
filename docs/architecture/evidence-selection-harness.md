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

The public route is `POST /v2/spaces/{space_id}/evidence-runs`. Follow-up runs
use `POST /v2/spaces/{space_id}/evidence-runs/{evidence_run_id}/follow-ups`.

Each run uses `planner_mode="model"` by default. When the configured
query-generation model is available, the researcher can provide only a goal and
instructions; the model planner selects a bounded set of supported source
searches and the runtime validates them before any external source call.

Manual runs can set `planner_mode="deterministic"`. Deterministic runs must
provide at least one of:

- `source_searches`: source searches the harness should create and screen;
- `candidate_searches`: durable saved source-search results to screen.

If the model planner is unavailable, goal-only requests fail clearly. Explicit
source-search or candidate-search requests can fall back to deterministic
execution and record the fallback reason in the source-plan artifact.

The harness can create supported live structured source searches, including
PubMed, MARRVEL, ClinVar, ClinicalTrials.gov, UniProt, AlphaFold, DrugBank,
MGI, and ZFIN, subject to each source's gateway availability and API keys.
Each live source search has a per-source timeout so one slow external source
does not block indefinitely. The default is service-defined, and callers can
set `timeout_seconds` on individual `source_searches` when a source is expected
to be faster or slower. Searches currently run sequentially inside a single
evidence run to keep source behavior and shared persistence simple; a future
slice can add parallel execution with a run-level deadline if needed.

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
