## Full AI Orchestrator Live Compare Issues

This note captures the April 12-13, 2026 live side-by-side comparisons between:

- baseline `research-init`
- Phase 2 `full-ai-orchestrator`

using the same objective and source toggles against the local stack.

### Confirmed mismatches

1. PubMed parity drift
- Baseline completed with `documents_ingested=5`.
- Orchestrator completed with `documents_ingested=4`.
- The per-query PubMed summary also diverged, which means the two runs did not preserve the same initial evidence selection.

2. Proposal-count drift
- Baseline completed with `proposal_count=125`.
- Orchestrator completed with `proposal_count=121`.

3. Bootstrap drift
- Baseline bootstrap summary reported `proposal_count=125`, `linked_proposal_count=117`, `bootstrap_generated_proposal_count=8`.
- Orchestrator bootstrap summary reported `proposal_count=121`, `linked_proposal_count=121`, `bootstrap_generated_proposal_count=0`.

4. Chase-round drift
- Chase round 1 and 2 produced different term sets between baseline and orchestrator.
- These differences are downstream of the initial evidence mismatch and should not be treated as independent planner issues until PubMed parity is fixed.

5. Planner comparison drift
- The shadow planner timeline completed, but most checkpoints diverged from deterministic next actions.
- Some checkpoints were invalidated by planner output validation, including numeric-style ranking and non-live action selection.

6. Runtime noise seen only in the orchestrator run
- LLM extraction timeout with regex fallback
- entity embedding refresh timeout
- bootstrap candidate embedding refresh deadlock

### First fix landed

The full orchestrator route now captures and persists a PubMed replay bundle before worker execution, and the runtime reloads that bundle when executing the run.

Why this matters:

- it makes the orchestrator's first evidence step replayable
- it aligns the run with the Phase 1 requirement for deterministic baseline artifacts
- it removes one source of drift caused by recomputing PubMed discovery/selection during queued execution

### April 13 rerun after replay-bundle route fix

Fresh live runs:

- baseline `research-init` run `e403fa59-7f2f-4fad-ab16-7cd24cd8ac33`
- Phase 2 `full-ai-orchestrator` run `663cdef8-bb2f-4325-9985-a177f3e79a93`

What improved:

1. The orchestrator route definitely persisted and consumed the replay artifact.
- Workspace snapshot included `pubmed_replay_bundle_key=full_ai_orchestrator_pubmed_replay_bundle`.
- Artifact list included `full_ai_orchestrator_pubmed_replay_bundle`.
- The orchestrator PubMed summary exactly matched the replay bundle's query totals:
  - `"MED13 congenital heart disease"` -> `7`
  - `"MED13"` -> `168`
  - `"congenital heart disease"` -> `211394`

What still drifted:

1. PubMed selection drift still exists in public-route comparison.
- Baseline completed with `source_results.pubmed.documents_selected=2` and `documents_ingested=2`.
- Orchestrator completed with `source_results.pubmed.documents_selected=3` and `documents_ingested=3`.
- This means the replay artifact path is active, but the two public routes are still not consuming the exact same selected document set.

2. Structured-source output drift is still large.
- Baseline source summaries:
  - `alphafold.records_processed=2`
  - `clinical_trials.records_processed=30`
  - `marrvel.records_processed=298`
- Orchestrator source summaries:
  - `alphafold.records_processed=3`
  - `clinical_trials.records_processed=26`
  - `marrvel.records_processed=1824`
- These are downstream of the different PubMed document set and different driven-term extraction.

3. Proposal/bootstrap drift remains significant.
- Baseline completed with `proposal_count=125`.
- Orchestrator completed with `proposal_count=96`.
- Baseline bootstrap summary:
  - `proposal_count=125`
  - `linked_proposal_count=123`
  - `bootstrap_generated_proposal_count=2`
- Orchestrator bootstrap summary:
  - `proposal_count=96`
  - `linked_proposal_count=96`
  - `bootstrap_generated_proposal_count=0`

4. Chase-round drift remains significant.
- Baseline chase round 1 created `1` document and chase round 2 created `1` document.
- Orchestrator chase round 1 created `0` documents and chase round 2 created `3` documents.
- The new term sets diverged strongly, so planner-quality evaluation is still confounded by baseline drift.

5. Error profile drift worsened in the orchestrator run.
- Baseline errors:
  - `LLM found no extractable relations (text_length=508)`
- Orchestrator errors:
  - `LLM found no extractable relations (text_length=470)`
  - `LLM found no extractable relations (text_length=438)`
  - `LLM found no extractable relations (text_length=439)`
  - `LLM found no extractable relations (text_length=1818)`

6. Planner timeline is present, but still not yet a trustworthy comparison signal.
- The orchestrator completed with `checkpoint_count=9`.
- Shadow planner evaluation reported:
  - `action_matches=5`
  - `source_matches=7`
  - `invalid_recommendations=3`
  - `planner_failures=3`
- Until deterministic Phase 1 parity is tighter, planner divergence is hard to interpret.

7. The live compare script still has a result-fetch race.
- During the rerun, the compare script attempted to fetch `full_ai_orchestrator_result` immediately after terminal status and got a `404`.
- A follow-up fetch showed the artifact existed.
- So this is a script timing bug, not an orchestrator persistence failure.

### Next fixes

1. Make the live comparison truly apples-to-apples by ensuring both compared runs share one PubMed replay bundle, instead of only the orchestrator route doing so.
2. Once PubMed selection parity is fixed, re-check driven terms, structured-source counts, bootstrap totals, and chase-round outputs.
3. After deterministic parity is stable, tighten the shadow-planner validation and comparison metrics.

### April 12 rerun after document `step_key` fingerprint fix

Targeted deterministic compare command:

- `PYTHONPATH=/Users/alvaro/Documents/Code/monorepo/services ... python -m artana_evidence_api.manage compare-phase1`
- `--pubmed-backend deterministic`
- sources: `pubmed,marrvel,clinvar,pdf,text,alphafold,clinical_trials`
- `mondo=false` for this parity check so the run measures orchestrator parity instead of waiting on ontology loading

Fresh compare runs:

- baseline `research-init` run `f498eb78-96b9-467b-915b-2582fa2f0b68`
- Phase 2 `full-ai-orchestrator` run `6c383d42-2553-44b0-8683-5c87993fac0c`

What matched:

1. High-signal workspace summary matched end-to-end.
- `documents_ingested=10`
- `proposal_count=202`
- `driven_terms=["MED13"]`
- identical pending questions
- identical bootstrap totals:
  - `proposal_count=202`
  - `linked_proposal_count=202`
  - `bootstrap_generated_proposal_count=0`

2. Source summaries matched.
- `clinvar.records_processed=20`
- `alphafold.records_processed=1`
- `clinical_trials.records_processed=2`
- `marrvel.records_processed=1194`
- PubMed summary matched with `documents_selected=10` and `documents_ingested=10`

3. The deterministic compare no longer reported the earlier proposal/bootstrap drift.
- This is the strongest evidence so far that the document-scoped `step_key` fingerprinting fixed the cross-document extraction/review replay bleed that had been inflating or mutating downstream proposal counts.

What still remains open:

1. Full live service comparison still has a MONDO tail problem.
- The baseline public-route run can sit in `phase="deferred_mondo"` at roughly `95%` progress for a long time.
- The code labels this step as deferred/background, but the runtime still executes the ontology load inline before final completion and brief generation.
- That means the live route compare can still time out before a terminal status even though deterministic parity is now clean when MONDO is excluded.

Current interpretation:

- Core Phase 1 deterministic parity for the main research pipeline is now in much better shape.
- The remaining live-compare blocker is no longer the earlier extraction/proposal drift; it is the long inline MONDO completion tail on the public-route path.

### April 13 fix: MONDO tail made truly deferred

What changed in code:

- `research_init_runtime.py` no longer awaits MONDO ingestion inline before marking the run completed.
- When MONDO is enabled, the main run now:
  - marks `source_results["mondo"]["status"] = "background"`
  - completes the primary research-init run
  - launches a deferred MONDO loader that patches the workspace and primary result artifact after ontology loading finishes
- `research_init_brief.py` now renders a background-loading MONDO message instead of falsely saying that zero terms were loaded.

Regression coverage:

- `tests/unit/test_research_init.py`
  - verifies the run completes first
  - verifies MONDO starts in `background`
  - verifies the deferred patch later moves it to `completed`
- `tests/e2e/test_research_init_pipeline_e2e.py`
  - verifies the full stubbed pipeline follows the same handoff
- `tests/unit/test_research_init_brief.py`
  - verifies the brief text explains background MONDO loading correctly

Proof compare after the fix:

- baseline run `058993d5-454b-44d8-9144-e103be60eda7`
- orchestrator run `47c81c54-195e-4353-80b4-a79a5abad3f3`
- command kept `mondo=true`
- compare returned successfully instead of timing out in `deferred_mondo`

Observed result:

- `baseline_mondo_status = "background"`
- `orchestrator_mondo_status = "background"`
- compare mismatches: `[]`

Interpretation:

- The MONDO tail no longer blocks the parity check.
- With the earlier document `step_key` fix plus the deferred MONDO change, the deterministic Phase 1 compare now returns cleanly even when MONDO stays enabled.
