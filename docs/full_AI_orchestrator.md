# Full AI Orchestrator Plan

**Status date:** April 18, 2026

## Purpose

This document defines the target architecture for the Full AI Orchestrator:
a governed research-planning agent that coordinates literature, structured
sources, graph reasoning, hypothesis generation, and brief synthesis for a
research space.

The goal is not to let an LLM directly write graph truth. The goal is to let an
AI planner decide what source or reasoning step should run next, while every
fact still flows through deterministic grounding, qualitative assessment,
claim governance, and projection.

## Simple Version

Today the system is smart, but mostly scripted.

It does roughly this:

```text
Run PubMed
Extract entities from PubMed
Run selected structured sources for those terms
Run bootstrap graph reasoning
Run up to two chase rounds
Write a brief
```

The Full AI Orchestrator should do this:

```text
Read the research goal
Inspect current evidence and graph state
Choose the best next source or graph action
Run that action through approved tools
Update durable workspace state
Decide whether to chase another lead or stop
Write a brief explaining findings, gaps, and next questions
```

In short: move from a fixed research recipe to a governed research lead.

## Current Source-Code Status

### What Already Exists

The current codebase now has a real sibling full-orchestrator runtime, a real
shadow planner, a narrow guarded planner pilot, an opt-in bridge from the
normal `research-init` trigger into the full orchestrator, and an owner/admin
space setting for selecting that mode. The missing part is no
longer "a top-level AI decision loop exists at all." The real remaining work is
expanding planner trust safely: broader guarded actions, rollout posture,
operator surfaces, and eventual default adoption.

Latest guarded evaluation status: the live 4-fixture guarded comparison rerun
passed on April 15, 2026 UTC with the cleaner reference report now at
`reports/full_ai_orchestrator_guarded/dual_live_objective_clean_reference_20260415/summary.md`
and
`reports/full_ai_orchestrator_guarded/dual_live_objective_clean_reference_20260415/summary.json`.
That report shows 8 guarded actions applied, 8 verified, 0 verification
failures, 0 pending verifications, 2 expected matches, 2 acceptable
divergences, 0 execution drift, 0 downstream-state drift after matched actions,
and 0 review-needed fixtures across BRCA1, CFTR, MED13, and PCSK9.

After compare-normalization hardening, a smaller BRCA1/CFTR rerun also passed
and made the remaining residual noise more honest instead of less visible. The
current subset report is at
`reports/full_ai_orchestrator_guarded/dual_live_objective_jitter_subset_20260415/summary.md`
and
`reports/full_ai_orchestrator_guarded/dual_live_objective_jitter_subset_20260415/summary.json`.
That rerun shows proposal deltas at `0` for both fixtures, one true
live-source-jitter case on CFTR, and one downstream follow-up-state drift case
on BRCA1 where the only remaining mismatch is an extra pending question about
`PARP inhibitor response`. In simple terms: the guarded planner is still making
the correct stop decision, and the remaining drift is now clearly in
follow-up-question generation rather than in evidence extraction or graph
governance.

Latest supplemental guarded status: the practical live guarded graduation gate
passed on April 17, 2026 UTC. The report is at
`reports/full_ai_orchestrator_guarded/20260417_001904/summary.md`
and
`reports/full_ai_orchestrator_guarded/20260417_001904/summary.json`.
That run shows 8 guarded actions applied, 8 verified, 0 verification failures,
0 pending verifications, 4 guarded terminal-control actions, 4 guarded
chase-checkpoint stops, 4 completed supplemental fixtures, and 0 failed
fixtures. It also proves the evaluation policy now handles one conservative
guarded `STOP` as an accepted safety-first divergence when the planner provides
qualitative rationale, a stop reason, and clean proof receipts. In simple
terms: the guarded planner has live proof for label-filtered chase selection,
bounded stop decisions, and conservative closure without silently treating
safety-first divergence as a failure.

Latest source+chase exhaustive status: the repeated objective plus supplemental
source+chase graduation gate also passed on April 17, 2026 UTC. The report is
at
`reports/full_ai_orchestrator_guarded/20260417_183631/summary.md`
and
`reports/full_ai_orchestrator_guarded/20260417_183631/summary.json`.
That report covers 16 repeated runs, shows clean proof receipts for every
applied guarded source-selection and chase/stop intervention, and confirms the
`guarded_source_chase` profile can exercise real authority without crossing
into reserved, context-only, grounding, or disabled-source surfaces. In simple
terms: the narrow guarded profile now has a strong proof pack; the next job is
to turn that proof into a repeatable operator canary workflow.

Latest real-space canary status: the live real-space canary runner now also has
one clean `guarded_source_chase` pass on April 18, 2026 UTC. The report is at
`reports/full_ai_orchestrator_real_space_canary/20260418_002225/summary.md`
and
`reports/full_ai_orchestrator_real_space_canary/20260418_002225/summary.json`.
That run used an existing supplemental bounded-chase space and shows one
verified source-selection intervention plus one verified guarded `STOP` at the
`after_bootstrap` chase checkpoint, with
`profile_authority_exercised=true`, no invalid outputs, no fallback outputs,
and no source-policy violations. In simple terms: the operator canary workflow
is now real, not just planned.

Latest ordinary low-risk cohort status: a fresh two-space MED13 cohort was
rerun cleanly on April 18, 2026 UTC after the local worker restart-hygiene fix
landed, and it again produced a `hold` verdict rather than a rollback. The
latest report is at
`reports/full_ai_orchestrator_real_space_canary/20260418_060036/summary.md`
and
`reports/full_ai_orchestrator_real_space_canary/20260418_060036/summary.json`.
That rerun covered 6/6 completed live runs across `full_ai_shadow`,
`guarded_dry_run`, and `guarded_source_chase`, with 0 failed runs, 0 timed-out
runs, 0 malformed payloads, 2 verified source interventions, 0 chase/stop
interventions, 0 invalid outputs, 0 fallback outputs, and 0 source-policy
violations. The verdict stayed at `hold` only because no chase/stop authority
was exercised on those ordinary spaces. The earlier clean ordinary cohort at
`reports/full_ai_orchestrator_real_space_canary/20260418_044036/summary.md`
still stands as supporting evidence, but the restart-fixed rerun matters more
because it confirms the clean `hold` was not an artifact of stale local worker
state. In simple terms: on normal low-risk spaces the guarded planner stayed
clean and conservative instead of drifting into `rollback_required`, even after
a fresh local restart.

Latest ordinary source+chase canary status: a three-space ordinary low-risk
cohort passed on April 18, 2026 UTC. The report is at
`reports/full_ai_orchestrator_real_space_canary/20260418_062106/summary.md`
and
`reports/full_ai_orchestrator_real_space_canary/20260418_062106/summary.json`.
That run covered 9/9 completed live runs across `full_ai_shadow`,
`guarded_dry_run`, and `guarded_source_chase`, with 0 failed runs, 0 timed-out
runs, 0 malformed payloads, 3 verified source interventions, 3 chase/stop
interventions, 2 authority-exercised runs, 0 invalid outputs, 0 fallback
outputs, and 0 source-policy violations. Two of the three spaces reached
per-space `pass`; the third stayed as a clean `hold` because it had no
chase/stop opportunity to exercise. In simple terms: the ordinary real-space
canary gap is now closed for the current source+chase milestone, while default
adoption still needs continued low-risk canary accumulation and human review.

Latest active source+chase completion pass: a second three-space active cohort
also passed on April 18, 2026 UTC. The report is at
`reports/full_ai_orchestrator_real_space_canary/20260418_071847/summary.md`
and
`reports/full_ai_orchestrator_real_space_canary/20260418_071847/summary.json`.
That run covered 9/9 completed live runs, with 0 failed runs, 0 timed-out
runs, 0 malformed payloads, 3 verified source interventions, 2 chase/stop
interventions, 1 authority-exercised run, 0 invalid outputs, 0 fallback
outputs, and 0 source-policy violations. Together with the earlier
supplemental reference and the ordinary three-space pass, this gives the
source+chase rollout three clean pass references. In simple terms: the current
operator-proof phase is complete; the remaining work is staged rollout and
continued canary review, not more runner hardening.

Latest rollout-review status: the selected source+chase canary evidence pack
passed on April 18, 2026 UTC. The report is at
`reports/full_ai_orchestrator_rollout_review/20260418_122808/summary.md`
and
`reports/full_ai_orchestrator_rollout_review/20260418_122808/summary.json`.
That review aggregates the supplemental reference, the ordinary three-space
pass, and the active three-space pass. It covers 21 completed live runs, 0
failed runs, 0 timed-out runs, 7 source-selection interventions, 6 chase/stop
interventions, and 4 authority-exercised runs. In simple terms: operators now
have a single review artifact that says the selected evidence pack is clean
enough for cautious `guarded_source_chase` rollout review.

Operator decision status: `guarded_source_chase` is now recorded as
`approved_for_default` in `docs/full_ai_orchestrator_operator_review.md` after
the monitored settings-path canary and default-readiness gate passed. This
approves only the narrow guarded source+chase authority surface and preserves
`deterministic` as the explicit rollback mode.

Latest settings-based small canary status: the first reviewed small canary
passed on April 18, 2026 UTC. The settings-path proof summary is at
`reports/full_ai_orchestrator_settings_canary/20260418_125948/summary.md`,
the standard real-space canary report is at
`reports/full_ai_orchestrator_real_space_canary/20260418_130004/summary.md`,
and the follow-up rollout review is at
`reports/full_ai_orchestrator_rollout_review/20260418_131238/summary.md`.
The settings-path proof covered 3 completed guarded runs with 3
source-selection interventions, 5 chase/stop interventions, 3
authority-exercised runs, and 8 verified proof receipts. The standard
real-space canary covered 9/9 completed runs across `full_ai_shadow`,
`guarded_dry_run`, and `guarded_source_chase`, with 0 failed runs, 0 timed-out
runs, 0 malformed payloads, 0 invalid outputs, 0 fallback outputs, and no
source-policy violations. The follow-up rollout review now aggregates 30
completed live runs with 10 source-selection interventions, 8 chase/stop
interventions, and 5 authority-exercised runs. In simple terms: the first
space-settings canary has passed, but this is still monitored small-canary
evidence, not default adoption.

Latest additional low-risk cohort status: a corrected three-space CFTR cohort
also passed on April 18, 2026 UTC. The report is at
`reports/full_ai_orchestrator_real_space_canary/20260418_144646/summary.md`
and
`reports/full_ai_orchestrator_real_space_canary/20260418_144646/summary.json`.
That run covered 9/9 completed live runs across `full_ai_shadow`,
`guarded_dry_run`, and `guarded_source_chase`, with 0 failed runs, 0 timed-out
runs, 0 malformed payloads, 3 source-selection interventions, 3 chase/stop
interventions, 2 authority-exercised runs, 0 invalid outputs, 0 fallback
outputs, and 0 source-policy violations. The updated rollout review at
`reports/full_ai_orchestrator_rollout_review/20260418_150738/summary.md`
now aggregates 39 completed live runs, 13 source-selection interventions, 11
chase/stop interventions, 7 authority-exercised runs, 9 distinct spaces, and
5 passing spaces. In simple terms: this evidence supported continuing the
small guarded canary and later fed the default-readiness review.

Latest monitored widening status: the two CFTR spaces that had per-space
`pass` were added to the settings-based canary on April 18, 2026 UTC. The
settings-path report is at
`reports/full_ai_orchestrator_settings_canary/20260418_182547/summary.md`
and
`reports/full_ai_orchestrator_settings_canary/20260418_182547/summary.json`.
That check used normal research-init product-path requests with no per-run
orchestration override. It covered 2/2 completed guarded runs, with 0 failed
runs, 0 timed-out runs, 2 source-selection interventions, 3 chase/stop
interventions, 2 authority-exercised runs, 5 verified proof receipts, 0 proof
verification failures, 0 pending proof verifications, 0 invalid outputs, 0
fallback outputs, and no source-policy violations. The clean-hold CFTR space
remained deterministic. In simple terms: the first small widening succeeded,
but the system is still in monitored canary mode, not default mode.

Latest second monitored widening status: the two MED13 ordinary spaces that
had per-space `pass` were also added to the settings-based canary on April 18,
2026 UTC. The settings-path report is at
`reports/full_ai_orchestrator_settings_canary/20260418_184841/summary.md`
and
`reports/full_ai_orchestrator_settings_canary/20260418_184841/summary.json`.
That check used normal research-init product-path requests with no per-run
orchestration override. It covered 2/2 completed guarded runs, with 0 failed
runs, 0 timed-out runs, 2 source-selection interventions, 4 chase/stop
interventions, 2 authority-exercised runs, 6 verified proof receipts, 0 proof
verification failures, 0 pending proof verifications, 0 invalid outputs, 0
fallback outputs, and no source-policy violations. The prior clean-hold space
from the MED13 cohort remained deterministic. In simple terms: the monitored
settings-based canary covered 7 low-risk spaces across BRCA1, PCSK9, CFTR,
and MED13 before the default-readiness gate passed.

Latest default-readiness status: the repeated settings-path gate ran on April
18, 2026 UTC and returned `pass` with
`approved_for_default_discussion`. The report is at
`reports/full_ai_orchestrator_default_readiness/20260418_194423/summary.md`
and
`reports/full_ai_orchestrator_default_readiness/20260418_194423/summary.json`.
The gate reviewed all 7 monitored settings-enabled spaces across 4 selected
settings reports and found 14 clean settings-path runs, 14
authority-exercised clean runs, 14 source-selection interventions, 26
chase/stop interventions, and 40 verified proof receipts, with 0 failed runs,
0 timed-out runs, 0 proof verification failures, 0 pending proof verifications,
0 invalid outputs, and 0 fallback outputs.

Default adoption status: the research-init default has now flipped to
`full_ai_guarded` with `guarded_source_chase`. A request or space setting can
still choose `deterministic` as the scripted rollback path. This is not
autonomous graph ownership: canonical graph writes, graph reasoning ownership,
hypothesis generation ownership, and extraction-policy ownership remain outside
the default planner authority.

Latest guarded rollout-profile proofs: the continue-boundary and stop-boundary
profile proofs passed on April 17, 2026 UTC. The reports are at
`reports/full_ai_orchestrator_guarded_rollout/20260417_011145/summary.md`
and
`reports/full_ai_orchestrator_guarded_rollout/20260417_011544/summary.md`.
Those proofs reuse one deterministic baseline, replay the guarded profiles
counterfactually, and show that `guarded_dry_run` applies no actions,
`guarded_chase_only` allows chase or stop control but no structured-source
steering, `guarded_source_chase` limits authority to source plus chase/stop
decisions, and `guarded_low_risk` allows the broader manual-experiment surface. The
reports now explicitly say that `pending_verification` is expected in this
profile-boundary proof because it is not the post-execution graduation gate. In
simple terms: profile proof tells us the rollout switches route planner
influence correctly; the guarded graduation gate tells us whether applied
planner influence verifies cleanly after execution.

Latest shadow evaluation status: the live 4-fixture shadow comparison rerun
also passed on April 15, 2026 UTC with live deterministic baseline telemetry
attached. The current shadow report shows 12/12 action matches, 12/12 source
matches, 3/3 chase-action matches, 0 invalid outputs, 0 fallback or
unavailable recommendations, qualitative rationale coverage at 100%, planner
total cost `$0.0888`, deterministic baseline cost `$0.3688`, and a
planner-to-baseline cost ratio of `0.24x`, so the `<= 2x baseline` cost gate
passes with real fixture-backed telemetry. See
`reports/full_ai_orchestrator_phase2_shadow/phase2_live_with_baseline_cost_gate/summary.md`
and
`reports/full_ai_orchestrator_phase2_shadow/phase2_live_with_baseline_cost_gate/summary.json`.

Latest repository-wide validation status: `make all` passed on April 17, 2026
UTC with the QA report at
`reports/qa_report_20260417_133718.txt`.

| Area | Current status | Evidence |
| --- | --- | --- |
| Research-init parent runtime | Implemented as the main user-triggered research setup flow. It discovers literature, ingests documents, extracts evidence, bridges observations, optionally calls bootstrap, and consolidates results. | `docs/research_init_architecture.md`, `services/artana_evidence_api/research_init_runtime.py` |
| Full AI orchestrator sibling runtime | Implemented as a separate harness-owned runtime with durable workspace state, action history, result artifacts, planner metadata, and guarded-execution summaries. | `services/artana_evidence_api/full_ai_orchestrator_runtime.py`, `services/artana_evidence_api/harness_runtime.py` |
| Research-init orchestrator adoption bridge | Implemented as the default `research-init` execution shell. Default kickoff now queues the full orchestrator in guarded mode with the `guarded_source_chase` profile; request or space setting `deterministic` routes one run or one space through the baseline scripted runtime. `full_ai_shadow` remains available for observation-only planner review. UI proxy code is outside this extracted checkout. | `services/artana_evidence_api/routers/research_init.py`, `services/artana_evidence_api/types/common.py` |
| Operator rollout control | Implemented as owner/admin space settings in the evidence API. Operators can choose `full_ai_guarded`, `full_ai_shadow`, or explicit rollback mode `deterministic`; guarded spaces can also choose the first-class rollout profile (`guarded_dry_run`, `guarded_chase_only`, `guarded_source_chase`, or `guarded_low_risk`). `full_ai_guarded + guarded_source_chase` is now the default, and `deterministic` is the rollback target. UI settings code is outside this extracted checkout. | `services/artana_evidence_api/routers/spaces.py`, `services/artana_evidence_api/full_ai_orchestrator_runtime.py` |
| Shadow planner | Implemented with `StrongModelAgentHarness`, versioned prompt loading, checkpoint summaries, validation/repair, timeline artifacts, and evaluation support. | `services/artana_evidence_api/full_ai_orchestrator_shadow_planner.py`, `services/artana_evidence_api/phase2_shadow_compare.py` |
| Phase 2 manual evaluation workflow | Implemented and live-validated. The shadow planner can be evaluated against the 4 documented objective fixtures plus supplemental chase-stop, bounded-chase-continue, and label-filtering fixtures, writes JSON plus Markdown reports, and now computes the planner-vs-baseline cost gate from live deterministic baseline telemetry when local compare services are healthy. | `scripts/run_phase2_shadow_eval.py`, `services/artana_evidence_api/tests/unit/test_phase2_shadow_compare.py`, `tests/unit/scripts/test_run_phase2_shadow_eval.py` |
| Guarded planner pilot | Implemented for a narrow set of low-risk decisions, including structured-source narrowing, bounded chase-subset continuation, chase-checkpoint stop control, and guarded brief closure, with verification artifacts. | `services/artana_evidence_api/full_ai_orchestrator_runtime.py`, `services/artana_evidence_api/research_init_runtime.py`, `scripts/run_phase1_guarded_eval.py` |
| Bootstrap child runtime | Implemented as a graph-driven refinement phase with graph connection, hypothesis generation, and claim curation staging. | `docs/research_init_architecture.md`, `services/artana_evidence_api/research_bootstrap_runtime.py` |
| Driven Round 2 | Implemented. PubMed text is scanned for gene-like mentions, and structured enrichment runs on seed terms plus PubMed-discovered terms. | `services/artana_evidence_api/research_init_runtime.py` around `driven_terms_set` and `extract_gene_mentions_from_text` |
| Structured enrichment | Implemented for ClinVar, DrugBank, AlphaFold, MARRVEL, ClinicalTrials.gov, MGI, and ZFIN in the research-init path. | `services/artana_evidence_api/research_init_runtime.py`, `services/artana_evidence_api/research_init_source_enrichment.py` |
| Grounding and normalization sources | Implemented through service-local enrichment and ontology runtime helpers. UniProt and HGNC are reserved source keys in the full-orchestrator planner while MONDO runs as a deferred ontology load. | `services/artana_evidence_api/research_init_source_enrichment.py`, `services/artana_evidence_api/source_enrichment_bridges.py`, `services/artana_evidence_api/mondo_runtime.py`, `services/artana_evidence_api/research_init_runtime.py` |
| Enrichment orchestration metadata | Implemented. The runtime records driven-term counts, PubMed-derived genes, and seed terms in `source_results["enrichment_orchestration"]`. | `services/artana_evidence_api/research_init_runtime.py` |
| Chase rounds | Implemented with a deterministic baseline plus a narrow guarded pilot. The runtime still caps at two chase rounds, derives ordered candidate sets deterministically, and can now accept a planner-selected bounded subset or guarded stop at chase checkpoints. | `services/artana_evidence_api/research_init_runtime.py`, `services/artana_evidence_api/full_ai_orchestrator_runtime.py` |
| Research brief | Implemented. Current flow can produce a theme-organized brief in the evidence API; inbox delivery code is outside this extracted checkout. | `services/artana_evidence_api/research_init_brief.py` |
| Claim governance boundary | Implemented. Agents propose; policy and curation decide. The plan explicitly requires qualitative-first assessments and backend-derived numeric policy weights. | `docs/plan.md`, graph claim/relation services |
| Agent catalog | Implemented agent families include query generation, entity recognition, extraction, graph connection, graph search, content enrichment, mapping judge, and hypothesis generation through service-local runtime modules and graph-service contracts. | `services/artana_evidence_api`, `services/artana_evidence_db` |
| Observability | Existing runtime state, agent run IDs, progress snapshots, result artifacts, and trace helpers provide useful pieces for an orchestrator timeline. | `services/artana_evidence_api/harness_runtime.py`, `services/artana_evidence_api/full_ai_orchestrator_runtime.py` |

### Current Completion Boundary

The plan is implemented through the first production-relevant guarded default
slice. The Full AI Orchestrator is now the default research-init shell for the
narrow `guarded_source_chase` authority surface, but it is not a fully
autonomous graph-reasoning system.

Completed enough to rely on:

- deterministic Phase 1 sibling runtime and artifacts
- Phase 2 shadow planner with live fixture evaluation
- narrow guarded planner pilot for low-risk decisions
- guarded source+chase rollout profile with boundary proof
- default research-init adoption bridge for guarded orchestrator runs, with
  `deterministic` still available as rollback
- owner/admin rollout switch for selecting the research orchestration mode
- compact guarded-readiness and guarded-decision receipt summaries in the
  Research Inbox polling API and brief screen
- decision, prompt, model, and verification metadata in run artifacts

Still not complete:

- guarded default authority is limited to source narrowing plus bounded
  chase/stop decisions
- graph reasoning ownership, hypothesis generation ownership, extraction
  policy ownership, and planner-owned canonical writes remain out of scope
- planner does not own full source execution or graph reasoning loops
- richer product surfaces for full planner timelines and verification detail are still
  limited

The next milestone should therefore be post-default monitoring and any future
trust expansion review, not a jump to full planner ownership.

Operator rollout and rollback guidance now lives in
`docs/full_ai_orchestrator_rollout_runbook.md`. Use that runbook when changing
a space between `deterministic`, `full_ai_shadow`, and `full_ai_guarded`,
reviewing guarded proof receipts, widening a canary, or rolling back to the
deterministic baseline.

The current operator decision record lives in
`docs/full_ai_orchestrator_operator_review.md`.

Current rollout implementation:

- `planner_mode=shadow` maps to rollout profile `shadow_only`
- `planner_mode=guarded` defaults to profile `guarded_source_chase`
- per-run request profile overrides the space setting
- the space setting overrides environment configuration
- `ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT=1` preserves the legacy explicit chase
  pilot and maps guarded mode to the narrower `guarded_chase_only` profile
- `guarded_source_chase` is the default guarded profile. It may apply
  planner-ordered or narrowed structured-source selection from enabled live
  evidence sources, bounded chase candidate subsets, and `STOP` only at chase
  checkpoints. It may not control graph reasoning, hypothesis generation, brief
  generation, reserved sources, grounding sources, PDF/text, or disabled
  sources.
- `ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE=guarded_low_risk` enables the
  broader manual-experiment surface, including current low-risk source, chase,
  terminal-control, and brief-generation decisions
- every guarded action should carry `guarded_policy_version`,
  `guarded_rollout_profile`, and a policy-allowed marker in artifacts
- every guarded run should write a compact
  `full_ai_orchestrator_guarded_readiness` artifact. That summary now reports
  applied-strategy counts grouped by governance category
  (`source_selection`, `chase_or_stop`, `brief_generation`), the sorted list of
  `profile_allowed_strategies` for the current rollout profile, and a
  `profile_authority_exercised` flag. For `guarded_source_chase` the flag is
  only true when the run applied both a source-selection and a chase-or-stop
  intervention; for `guarded_low_risk` any category suffices; for
  `guarded_chase_only` a chase-or-stop intervention is enough; for
  `guarded_dry_run` and `shadow_only` the flag is null because those profiles
  cannot apply interventions.
- every guarded decision checkpoint should also write a durable proof receipt:
  `full_ai_orchestrator_guarded_decision_proofs` plus one
  `full_ai_orchestrator_guarded_decision_proof_<id>` artifact per reviewed
  checkpoint

Guarded proof receipts are now the audit boundary for guarded mode. Each proof
records the deterministic target, planner recommendation, rollout profile,
policy version, qualitative-rationale presence, fallback/validation/budget
status, final outcome (`allowed`, `blocked`, or `ignored`), and verification
result when an action was applied. In simple terms: guarded mode must leave a
receipt for both accepted planner influence and rejected planner influence.
The compact guarded-readiness summary is proof-aware as well: blocked or
ignored receipts in a guarded rollout profile prevent the run from being marked
ready for wider rollout even when no guarded action was applied.

Current profile-proof command:

`make full-ai-orchestrator-guarded-profile-proof`

What this proof does:

- runs the focused supplemental continue-boundary smoke fixture
- reuses one deterministic baseline per fixture
- probes `guarded_dry_run`, `guarded_chase_only`, `guarded_source_chase`, and
  `guarded_low_risk`
- verifies dry-run applies no guarded actions
- verifies chase-only cannot apply structured-source steering
- records whether source+chase and low-risk profiles can apply their allowed
  source and/or chase decisions when the planner recommends them
- writes profile summaries and readiness state into the guarded rollout report
- labels itself as `profile_boundary_counterfactual` so reviewers do not confuse
  profile-boundary evidence with post-execution guarded verification

Use `make full-ai-orchestrator-guarded-profile-proof-stop` for the matching
stop-boundary smoke proof.

Use `make full-ai-orchestrator-guarded-profile-proof-exhaustive` when we
explicitly want the slower objective plus supplemental sweep. That command is
useful before graduation review, but it is not the default local proof because
the objective fixtures run the full research-init path and can exceed local
fixture timeouts.

Graduation gate command:

`make full-ai-orchestrator-guarded-graduation-gate`

What this gate proves:

- runs the supplemental guarded evaluation fixtures with the `guarded_low_risk`
  rollout profile
- requires the usual guarded evaluation gates to pass
- requires every fixture to expose guarded decision proof receipts
- requires at least one allowed guarded proof receipt
- requires allowed receipts to be verified, policy-allowed, and tied to an
  applied action
- fails if any proof receipt has a fallback planner recommendation, invalid
  planner output, missing qualitative rationale, budget violation,
  disabled-source violation, pending verification, failed verification, or
  blocked/ignored planner influence
- keeps evaluating after a fixture timeout or runtime error so the report
  explains what failed instead of disappearing at the first broken fixture
- treats a planner `STOP` divergence as an accepted conservative stop only when
  the planner provides a qualitative rationale, a stop reason, and the guarded
  proof receipts remain clean

In simple terms: the profile-proof commands tell us the rollout switches behave
correctly; the graduation gate tells us whether the current proof receipts are
clean enough to justify widening guarded mode.

Use `make full-ai-orchestrator-guarded-graduation-gate-exhaustive` for the
slower objective plus supplemental sweep. The exhaustive command is a release
review tool, not the default local gate, because objective fixtures can run the
full research-init extraction path and exceed local fixture timeouts before any
guarded proof can be judged.

Source+chase graduation gate command:

`make full-ai-orchestrator-source-chase-graduation-gate`

What this gate adds:

- runs the guarded evaluation with `guarded_source_chase`
- requires clean guarded proof receipts
- requires at least one source-selection intervention across the fixture set
- requires at least one chase or chase-checkpoint stop intervention across the
  fixture set
- requires every fixture's per-run guarded readiness summary to report
  `profile_authority_exercised=true`, which for `guarded_source_chase` means
  the run applied both a source-selection and a chase-or-stop intervention.
  This makes the per-run readiness and the gate agree on a single definition
  of "source+chase authority was actually used" instead of relying on
  proof-receipt heuristics alone.
- keeps source/chase as the next reviewed canary target while leaving
  `guarded_low_risk` as a manual-experiment profile

Use `make full-ai-orchestrator-source-chase-graduation-gate-exhaustive` for the
slower repeated objective plus supplemental source+chase release sweep.

Canary report commands:

`make full-ai-orchestrator-guarded-canary-report`

`make full-ai-orchestrator-guarded-canary-report-exhaustive`

Real-space canary commands:

`make full-ai-orchestrator-real-space-canary SPACE_ID=<space-id> OBJECTIVE="..." SEED_TERMS="MED13,BRCA1"`

`make full-ai-orchestrator-real-space-canary SPACE_IDS="<space-a>,<space-b>" OBJECTIVE="..." SEED_TERMS="MED13,BRCA1" REPEAT_COUNT=2 EXPECTED_RUN_COUNT=12`

What the canary report layer adds:

- keeps the existing guarded graduation gates intact
- writes operator-facing canary reports under
  `reports/full_ai_orchestrator_guarded_canary/<timestamp>/`
- reports explicit timeout counts, timed-out fixtures, total runtime, average
  runtime, and granular source-policy violations (`disabled`, `reserved`,
  `context_only`, `grounding`)
- requires the intended run coverage through `expected_run_count`
- produces a final operator verdict of `pass`, `hold`, or `rollback_required`
  from explicit gates only

In simple terms: the graduation gate proves the planner stayed inside the
source+chase boundary; the canary report packages that proof into something an
operator can review quickly before widening a real space.

The next rollout sequence is now explicit:

1. fixture canaries pass
2. real-space canary passes
3. only then discuss widening or any default-adoption decision

The live real-space canary runner writes reports under
`reports/full_ai_orchestrator_real_space_canary/<timestamp>/` and exercises the
actual `/v1/spaces/{space_id}/research-init` route with per-run overrides for:

- `full_ai_shadow`
- `full_ai_guarded` + `guarded_dry_run`
- `full_ai_guarded` + `guarded_source_chase`

It does not mutate space settings, broaden planner authority, or change the
deterministic rollback path.

The real-space report now also summarizes the cohort, not just the raw runs.
It records a per-space rollout summary and a cohort status so operators can
tell the difference between:

- one passing supplemental reference space,
- a mixed low-risk cohort where some spaces still legitimately land on `hold`,
- and a clean multi-space cohort that is ready for rollout review.

The current passing real-space reference is
`reports/full_ai_orchestrator_real_space_canary/20260418_002225/summary.md`.
That pass came from an existing supplemental bounded-chase space, which makes
it a good operator proof target because it exercises both source steering and a
verified guarded chase-checkpoint `STOP`. Ordinary low-risk spaces can still
land on `hold` when no live chase opportunity materializes, so the next rollout
step is repeated clean canaries on more typical spaces rather than a default
flip.

### Code Evidence Snapshot

The implementation is now split across three layers:

- the existing deterministic `research-init` runtime,
- the sibling full orchestrator runtime that records the planning surface
  durably,
- and the shadow/guarded planner layer that can recommend or narrowly govern a
  subset of actions.

Concrete evidence:

- `services/artana_evidence_api/research_init_runtime.py:911-935` creates the
  queued `research-init` harness run, seeds the artifact store, and patches
  workspace state.
- `services/artana_evidence_api/full_ai_orchestrator_runtime.py` defines the
  sibling `full-ai-orchestrator` harness runtime, result contract, action
  registry, durable artifact keys, shadow planner timeline, and guarded
  execution summaries.
- `services/artana_evidence_api/full_ai_orchestrator_shadow_planner.py` uses
  `StrongModelAgentHarness`, loads a versioned planner prompt, builds bounded
  workspace summaries, validates planner output, and records planner metadata
  including model and prompt version.
- `services/artana_evidence_api/phase2_shadow_compare.py` compares planner
  recommendations to the deterministic next action across the checkpoint
  timeline and powers the Phase 2 evaluation workflow.
- `scripts/run_phase2_shadow_eval.py` provides the manual Phase 2 fixture
  runner for BRCA1, MED13, CFTR, and PCSK9, plus supplemental chase-stop,
  bounded-chase-continue, and label-filtering fixtures used to score both
  chase-control directions and verify filtered chase-candidate reporting.
- `scripts/run_phase1_guarded_eval.py` provides the guarded comparison runner
  for low-risk planner interventions and writes JSON plus Markdown reports. It
  now supports `--fixture-set objective|supplemental|all` so guarded evaluation
  can explicitly target the chase-focused supplemental scenarios instead of
  only the four broad objective fixtures.
- `services/artana_evidence_api/research_init_runtime.py:1710-1745` implements
  driven Round 2 by extracting gene-like mentions from PubMed candidates and
  selecting structured enrichment sources from source preferences.
- `services/artana_evidence_api/research_init_runtime.py:2034-2045` writes
  `source_results["enrichment_orchestration"]`, which is useful metadata but not
  yet a durable decision ledger.
- `services/artana_evidence_api/research_init_runtime.py:2466-2495` queues and
  executes `research_bootstrap` as the graph-driven child phase after entities
  exist.
- `services/artana_evidence_api/research_init_runtime.py:1247-1325` implements
  chase-round source selection by looking at recent graph entity labels,
  filtering out previous seeds, taking at most 10 new terms, and running
  enabled structured sources.
- `services/artana_evidence_api/research_init_runtime.py:2566-2605` caps chase
  rounds at two and stops early when fewer than `_MIN_CHASE_ENTITIES` new terms
  are found.
- `services/artana_evidence_api/routers/research_init.py:61-72` shows the
  current default source posture: PubMed, MARRVEL, ClinVar, MONDO, PDF, and
  text on by default; DrugBank, AlphaFold, UniProt, and HGNC off by default.
- `services/artana_evidence_api/research_init_runtime.py:1978-2259` is the
  actual active structured-enrichment block in Phase 1 today. It executes
  ClinVar, DrugBank, AlphaFold, ClinicalTrials.gov, MGI, ZFIN, and MARRVEL.
- `services/artana_evidence_api/research_init_runtime.py:2864-2869` marks
  UniProt and HGNC as deferred in the current deterministic flow rather than
  running them as first-class research actions.
- `services/artana_evidence_api/research_init_runtime.py:2869-2992` runs MONDO
  as a deferred ontology load, which is real source-backed work but not the
  same kind of evidence-gathering step as PubMed or ClinVar.
- `docs/research_init_architecture.md:5-22` documents the current parent flow:
  PubMed discovery, document ingestion, entity extraction, observation bridge,
  bootstrap, and result consolidation.
- `docs/research_init_architecture.md:42-55` documents bootstrap as the
  graph-driven child phase for graph connection, hypothesis generation, claim
  curation staging, and brief output.
- `docs/plan.md:390-423` keeps the current plan baseline at one initial round
  plus up to two chase rounds, with early stop if fewer than 3 new relevant
  entities are found.

### What Is Not Yet Implemented

The orchestrator still is not "finished" because the remaining gaps are the
hard ones:

- Source ordering is still mostly deterministic outside the guarded pilot.
- The planner can recommend actions broadly in shadow mode, but it does not yet
  own most real execution.
- Chase rounds now have partial planner integration for candidate surfacing,
  shadow comparison, and guarded bounded-subset or stop decisions, but live
  coverage is still thin and the deterministic runtime remains the execution
  owner.
- Guarded execution is intentionally narrow and not yet the default operating
  mode.
- The sibling runtime can now be selected by research-init, but it is not yet
  the default production planning shell.
- UI and product surfaces for planner timelines, policy posture, and rollout
  controls are still limited. The inbox research brief now shows applied
  guarded strategies, rollout profile, intervention counts by category, and a
  profile-authority signal, but richer decision-proof detail and timeline
  controls still need to follow.

So the current codebase has moved well past "orchestrator deferred" and into
"orchestrator partially implemented, with trust expansion and default adoption
still remaining."

From first principles, the best next step is no longer more shadow-planner
instrumentation. The next real frontier is guarded trust expansion: let the
planner govern a slightly broader low-risk slice, especially chase-subset
selection and other bounded continuation/stop decisions, then verify those
guarded actions repeatedly on live-style fixture runs before widening the
surface again.

### Phase 1 Source Capability Matrix

Phase 1 preserves the current deterministic runtime. That means source toggles
exist in one place, but the sources do not all behave the same way yet.

| Source | Phase 1 runtime status | Phase 2 planning posture |
| --- | --- | --- |
| PubMed | Active research action | Planner-usable source action |
| PDF | Active document input path | Planner-aware existing evidence/input |
| Text | Active document input path | Planner-aware existing evidence/input |
| ClinVar | Active structured enrichment | Planner-usable source action |
| DrugBank | Active structured enrichment | Planner-usable source action |
| AlphaFold | Active structured enrichment | Planner-usable source action |
| ClinicalTrials.gov | Active structured enrichment | Planner-usable source action |
| MGI | Active structured enrichment | Planner-usable source action |
| ZFIN | Active structured enrichment | Planner-usable source action |
| MARRVEL | Active structured enrichment | Planner-usable source action |
| MONDO | Active deferred ontology/background load | Planner-usable grounding or ontology action |
| UniProt | Present in source preferences and `source_results`, but not executed as a first-class research-init enrichment action | Add only as an explicit grounding or protein-context action |
| HGNC | Present in source preferences and `source_results`, but not executed as a first-class research-init enrichment action | Add only as an explicit grounding or nomenclature action |

This distinction matters for Phase 2. The planner should not be told that every
enabled source key already corresponds to a mature evidence-gathering action.
For Phase 2, the action registry should include all available sources, but the
registry must label them correctly:

- **Evidence-gathering actions:** PubMed, ClinVar, DrugBank, AlphaFold,
  ClinicalTrials.gov, MGI, ZFIN, MARRVEL
- **User-supplied evidence inputs:** PDF, text
- **Grounding or ontology actions:** MONDO
- **Future grounding and protein-context actions once wrapped explicitly:** UniProt,
  HGNC

Phase 2 should therefore include every currently available source in the plan,
but it should not pretend that UniProt and HGNC are already equivalent to
ClinVar or PubMed in the live orchestrator loop.

Planner-facing workspace summaries now normalize enabled sources into four
canonical buckets:

- `live_evidence` for real evidence-gathering sources the planner can reason
  about as active discovery targets
- `context_only` for existing PDF or text inputs that should not be treated like
  live evidence sources
- `grounding` for ontology or normalization context such as MONDO
- `reserved` for sources that are known to the system but are not yet first-class
  planner actions

That taxonomy is the planner surface the shadow reports and evaluation artifacts
should read from.

## Target Outcome

The Full AI Orchestrator should become the top-level research planning runtime
for a space.

It should:

1. Accept a research objective, seed entities, enabled source set, and governance settings.
2. Build and maintain durable workspace state.
3. Decide which action to run next from an allowlisted action registry.
4. Execute source, graph, and reasoning actions through idempotent tools.
5. Track why each action was selected.
6. Use qualitative-first assessment for relevance and evidence quality.
7. Stop when evidence is sufficient, budgets are reached, or no useful new leads appear.
8. Produce a research brief that explains findings by theme, not just by source.
9. Never bypass graph governance or write canonical truth directly.

## Why Use Artana-Kernel

The orchestrator should use Artana-kernel because this is exactly the shape of
work the kernel is meant to support: durable, long-running, model-driven
orchestration with replay-safe tools and explicit governance.

Relevant Artana-kernel capabilities from `docs/artana-kernel/docs`:

- **Strong model harnesses:** `StrongModelHarness`, `StrongModelAgentHarness`,
  workspace state, artifacts, verification gates, acceptance gates, pause/resume,
  and approval workflows.
- **Research-shaped harness template:** the kernel docs describe a research
  harness posture focused on question, graph, evidence count, contradictions,
  literature, graph, and scoring tools.
- **Durable tools and idempotency:** tools can receive `ToolExecutionContext`;
  mutating tools should be registered as side-effect tools and use idempotency
  keys for safe retries.
- **Replay and stable step keys:** explicit `step_key` usage allows deterministic
  replay and drift handling across loops.
- **Traceability:** lifecycle events, `trace::state_transition`, `trace::round`,
  `trace::cost`, `agent_model_step`, `agent_verify_step`, `agent_tool_step`, and
  parent step keys can give us a durable "why did the orchestrator do this?"
  timeline.
- **Capability guards and progressive skills:** source tools can be exposed only
  when a source is enabled for the space and when the orchestrator has activated
  the relevant runtime skill.
- **Approval workflows:** higher-risk actions can pause for human approval while
  lower-risk read actions can run automatically.

Important boundary: Artana-kernel should coordinate planning and tool execution.
It should not replace the existing graph governance layer.

### Kernel Build Options

Artana-kernel gives us several valid ways to build this orchestrator. In simple
terms:

#### Option 1: `StrongModelHarness`

This is the thin durable shell.

We write the orchestration loop ourselves and use the kernel for:

- workspace state
- artifacts
- replay
- stable `step_key` handling
- safe tool execution
- trace summaries

Best for:

- Milestone 1 decision logging
- Milestone 2 action registry
- early production-safe rollout where behavior should remain mostly scripted

Tradeoff:

- more orchestration code lives in our service
- less native agent behavior

#### Option 2: `StrongModelAgentHarness`

This is the bounded autonomous shell.

The kernel runs an `AutonomousAgent` loop with workspace context, allowed
tools, acceptance gates, verification, and artifact persistence.

Best for:

- Milestone 3 shadow planner
- Milestone 4 guarded planner
- Milestone 5 planner-led chase rounds
- the final "AI research lead" behavior

Tradeoff:

- stronger dependence on tool contracts and acceptance gates
- more of the loop becomes model-led instead of hand-authored

#### Option 3: domain template such as `ResearchHarness`

This is a research-shaped wrapper around the same core harness machinery.

Best for:

- later cleanup once the orchestrator workspace and tool posture are stable
- making the runtime read like a research workflow instead of a generic harness

Tradeoff:

- not necessary for the first implementation
- does not remove the need for our own graph/governance contracts

#### Option 4: `SupervisorHarness`

This is an orchestrator-of-orchestrators.

One top-level supervisor can delegate to child harnesses such as:

- planner child
- structured enrichment child
- bootstrap child
- brief-generation child

Best for:

- later scaling if the orchestrator becomes a true multi-agent system
- separating complex child responsibilities cleanly

Tradeoff:

- too much complexity for the first release
- harder debugging and rollout

#### Option 5: raw `AutonomousAgent` without a harness

This is the option to avoid as the primary production architecture.

It is useful for short-running or exploratory agent work, but it is not the
right shell for a long-running governed research orchestrator that needs durable
workspace state, replay, traceability, approval workflows, and side-effect
control.

### Recommended Kernel Path

The best fit for this project is a phased kernel path, not a single harness
choice from day one.

**Phase A: `StrongModelHarness` first**

Use the thin durable shell for Milestones 1-2.

Reason:

- we need traceability before autonomy
- we need safe tool wrappers before planner freedom
- we want the current deterministic runtime behavior to remain easy to compare

What Phase A gives us that Phase B reuses directly:

- **Durable workspace state:** the same state object later fed into
  `StrongModelAgentHarness` already exists, is serialized, and is stable.
- **Decision contract and artifact history:** Phase B does not invent a new
  decision shape; it writes planner decisions into the same decision ledger.
- **Allowlisted action registry:** the planner will only be allowed to choose
  from tools that Phase A already wrapped, typed, and tested.
- **Stable provenance and replay keys:** `step_key` naming, run summaries, and
  artifact conventions are already established before model-led planning starts.
- **Source safety checks:** capability guards, idempotency inputs, and
  side-effect boundaries already exist before the planner gets autonomy.
- **A deterministic baseline:** shadow mode in Phase B can compare planner
  choices against a known-good reference run instead of against hand-wavy
  expectations.

In plain terms: Phase A builds the rails that Phase B drives on. Without that
work, the first agent-led version would have to invent its state model, tool
contracts, provenance model, and comparison baseline all at once.

**Phase B: `StrongModelAgentHarness` next**

Use the bounded autonomous shell for Milestones 3-5.

Reason:

- this is where the planner starts choosing actions
- acceptance gates and verifier loops start to matter
- the runtime becomes a real orchestrator instead of a scripted wrapper

**Phase C: optional `ResearchHarness` or `SupervisorHarness` later**

Only add a domain template or supervisor layer if the orchestrator becomes
large enough that those abstractions clearly improve clarity, testing, or
scaling. They are not required for the first safe release.

### Model Selection Strategy

Artana-kernel does not magically choose the model on its own. The service
chooses the model first, then passes that resolved model ID into the kernel.

That is the pattern already used in this repo:

- `services/artana_evidence_api/runtime_support.py:72-180` defines
  `ModelCapability`, `ArtanaModelRegistry`, capability-based defaults, and
  override validation.
- `services/artana_evidence_api/artana.toml:12-17` configures the current
  capability defaults and whether runtime model overrides are allowed.
- `services/artana_evidence_api/graph_search_runtime.py:251-263`,
  `services/artana_evidence_api/pubmed_relevance.py:163-175`, and
  `services/artana_evidence_api/research_onboarding_agent_runtime.py:262-276`
  show the common runtime pattern: use a request override only if overrides are
  enabled and the model supports the required capability; otherwise fall back to
  the configured default for that capability.

As of the current codebase, the registry defaults are:

- `default_query_generation = "openai:gpt-5.4-mini"`
- `default_evidence_extraction = "openai:gpt-5.4-mini"`
- `default_curation = "openai:gpt-5.4-mini"`
- `default_judge = "openai:gpt-5.4-mini"`

and:

- `allow_runtime_model_overrides = false`

So today the platform is configured to prefer a registry-defined default model,
not free-form per-request model selection.

#### What the orchestrator should do

The Full AI Orchestrator should follow the same service-owned selection pattern.

It should not:

- hardcode vendor/model names into orchestrator logic
- let arbitrary callers choose any model by request payload
- overload unrelated capabilities in a way that hides planner costs and quality

It should:

- resolve models through the service-local registry
- validate that the chosen model supports the intended orchestrator role
- record the resolved model ID in run metadata and decision artifacts
- keep request-time model overrides disabled by default

#### Recommended orchestrator model roles

Once the planner is introduced, the orchestrator should select models by role:

- `planner_model_id`: primary planning and tool-selection model
- `verifier_model_id`: lower-cost validation or critique model
- `brief_model_id`: narrative-capable synthesis model

For Milestones 1-2, no dedicated planner model is required because the runtime
is still deterministic. For Milestones 3-5, these roles become explicit.

#### Recommended registry evolution

The cleanest approach is to extend the registry with orchestrator-specific
capabilities instead of pretending the planner is just another query generator.

Preferred future capabilities:

- `ORCHESTRATION_PLANNER`
- `ORCHESTRATION_VERIFIER`
- `ORCHESTRATION_BRIEF`

That gives us clean defaults, cleaner observability, and clearer cost tracking.
If we do not add new capabilities immediately, the temporary fallback should be:

- planner -> `QUERY_GENERATION`
- verifier -> `JUDGE`
- brief -> `EVIDENCE_EXTRACTION` or a dedicated brief config field

but that should be treated as transitional, not the final design.

#### Override policy

The orchestrator should keep the same safety posture as the rest of the service:

- config and environment decide defaults
- runtime request overrides stay off by default
- temporary override enablement should be used only for testing or controlled
  rollout

This matters because model choice affects cost, latency, reasoning quality, and
trace replay behavior. It is a governance decision, not just a convenience
parameter.

### Kernel Integration Mapping

The end-state orchestrator is agent-led, but the implementation path should be
phased:

- Milestones 1-2: `StrongModelHarness`
- Milestones 3-5: `StrongModelAgentHarness`
- Later optional layering: `ResearchHarness` or `SupervisorHarness`

Integration mapping:

| Orchestrator concept | Kernel concept |
| --- | --- |
| Workspace state | Harness workspace artifact (JSON, versioned per round) |
| Decision history | Harness artifact collection (append-only) |
| Deterministic decision logging | `StrongModelHarness` artifacts plus trace summaries |
| Planner step | `agent_model_step` with structured output contract once `StrongModelAgentHarness` is introduced |
| Verifier step | `agent_verify_step` after tool execution once the planner is model-led |
| Action execution | `run_tool(...)` / `agent_tool_step` with registered side-effect tools |
| Round boundary | `trace::round` lifecycle event |
| Cost tracking | `trace::cost` lifecycle event |
| Decision provenance | `step_key` with deterministic naming: `decision-{round}-{action_type}` |

Workspace state serialization should use the kernel's artifact store directly.
The `OrchestratorDecision` contract should be a Pydantic model that serializes
to a kernel artifact without transformation. Do not build a parallel artifact
layer.

The kernel docs live at `docs/artana-kernel/docs`. Before implementing
Milestone 1, verify that the kernel's artifact store supports the proposed
workspace state shape, including nested lists and dicts. If it does not, file
a kernel enhancement before proceeding.

## Requirements

### Functional Requirements

#### Orchestrator Workspace State

The orchestrator needs a durable workspace shape, likely stored as Artana-kernel
artifacts plus mirrored run metadata for product observability.

Minimum fields:

- `space_id`
- `run_id`
- `objective`
- `seed_terms`
- `seed_entity_ids`
- `enabled_sources`
- `governance_mode`
- `current_round`
- `discovered_entities`
- `new_entities_by_round`
- `source_results`
- `claim_counts`
- `proposal_counts`
- `open_questions`
- `evidence_gaps`
- `contradictions`
- `budget_state`
- `decision_history`
- `brief_outline`

#### Orchestrator Decision Contract

Every planner decision must be structured. No free-form "I will go research
more" blobs.

The contract has two tiers:

**Core fields (required from Milestone 1, always present):**

```text
decision_id
round_number
action_type
action_input
source_key
evidence_basis
stop_reason
```

**Planner fields (Optional, populated from Milestone 3 onward):**

```text
expected_value_band
qualitative_rationale
risk_level
requires_approval
budget_estimate
fallback_reason
```

In Milestone 1 (deterministic decision logging), planner fields are `None`.
The Pydantic model should use `Optional[str] = None` for planner fields so
that Milestone 1 records are clean, not padded with placeholder values.

Action types are split into two categories:

**Source actions** (tool calls through the action registry):

- `QUERY_PUBMED`
- `RUN_STRUCTURED_ENRICHMENT`
- `RUN_GRAPH_CONNECTION`
- `RUN_HYPOTHESIS_GENERATION`
- `RUN_GRAPH_SEARCH`
- `SEARCH_DISCONFIRMING` (reserved for later milestones; first implementation
  should be a read-only contradiction-focused evidence search, not a new
  mutating source path)
- `GENERATE_BRIEF`

**Control-flow decisions** (state transitions, not tool calls):

- `STOP`
- `ESCALATE_TO_HUMAN`

Source actions go through the action registry and tool execution. Control-flow
decisions are state transitions handled by the orchestrator loop directly.

Later source actions can include ontology refreshes, whole-space gap discovery,
review-priority tuning, and active-learning tasks.

#### Action Registry

The orchestrator should not call arbitrary code. It should choose from an
allowlisted action registry.

Initial actions should wrap existing code:

- PubMed discovery from `research_init_runtime`
- PDF workset ingestion and review from the existing document path
- Text workset ingestion and review from the existing document path
- ClinVar enrichment from `research_init_source_enrichment.py`
- DrugBank enrichment from `research_init_source_enrichment.py`
- AlphaFold enrichment from `research_init_source_enrichment.py`
- MARRVEL enrichment from `research_init_source_enrichment.py`
- ClinicalTrials.gov, MGI, and ZFIN enrichment helpers
- Deferred MONDO ontology load as a grounding action
- Graph connection runner
- Hypothesis generation service
- Claim curation staging
- Brief generation

The initial Phase 2 registry should also reserve named actions for UniProt and
HGNC, but only after they are wrapped as explicit orchestrator actions with
clear semantics. Until then, they should be described in the plan as
**available grounding services**, not as already-live Phase 1 research actions.

Each action wrapper should declare:

- input schema
- output schema
- source family
- read or write behavior
- side-effect level
- idempotency key inputs
- timeout
- rate limit
- budget estimate
- space setting key for capability check (e.g., `sources.clinvar`)
- whether approval is required

**Capability guards read from space settings as the single source of truth.**
The action registry does not maintain a separate enabled/disabled state. The
`required capability` field is a reference to the space source-preference key
(e.g., `sources.get("clinvar", True)`). This prevents two systems checking the
same thing.

#### Planner Loop

The target loop should look like this:

```text
1. Load workspace state
2. Summarize current evidence and gaps
3. Planner proposes next action
4. Policy gate validates action against allowed sources, budget, risk, and governance
5. Execute the action through an idempotent tool
6. Normalize action output into workspace state
7. Verifier checks whether output supports the decision rationale
8. Continue or stop
9. Generate final brief and run summary
```

#### Planner Prompt Strategy

The planner is an LLM call. Its prompt and output format determine the
orchestrator's behavior.

**State serialization:** The planner receives a summary of workspace state, not
the full state. As the workspace grows (50+ entities, 20+ source results by
round 3), the full state exceeds practical context budgets. The summarization
strategy:

- Always include: objective, seed terms, current round, budget remaining,
  decision history (action_type + source_key + stop_reason for each)
- Include by reference: entity count, source result count, claim/proposal counts
- Include selectively: top-N most relevant new entities (by round), top evidence
  gaps, active contradictions
- Never include: full entity lists, raw source result payloads, full claim text

Target prompt size: under 4,000 tokens for the workspace summary portion.

**Output format:** The planner produces structured decisions using tool use
(function calling). The tool definition matches the `OrchestratorDecision`
contract. This gives reliable field extraction without JSON parsing heuristics.

**Model selection:**

- Planner step: a higher-reasoning structured-output model
- Verifier step: a lower-cost validation model
- Brief generation: a narrative-capable summarization model

Exact provider and model names belong in deployment config, not in this design
doc. They should be resolved through the service-local Artana model registry as
described in the Model Selection Strategy section above.

**Latency budget:** Planning overhead is expected to be materially higher than
the current deterministic flow. Shadow mode (Milestone 3) should measure
whether that extra latency is justified by better source selection and better
stopping behavior before any guarded rollout.

**Batch decisions:** Where possible, the planner should decide on multiple
related actions in a single call (e.g., "which structured sources should run
for these new entities?" rather than one call per source). This reduces round
trips.

**Prompt versioning:** Planner prompts live in version-controlled prompt files
(not inline strings). Each decision record includes a `prompt_version` field
(git hash of the prompt file at execution time). This enables prompt-to-outcome
tracing.

#### Stop Rules

The orchestrator has two levels of stop conditions.

**Hard limits (planner cannot exceed):**

- max discovery rounds reached. For the first release, keep the current plan
  baseline: one initial round plus up to two chase rounds (3 total rounds).
  Any expansion beyond that is later experimental work and should be
  feature-flagged.
- max source calls reached (configured limit)
- max cost reached (configured limit)
- proposal count exceeds curator capacity threshold (configurable)
- user approval required and not granted

**Soft defaults (planner may improve upon):**

The current deterministic flow uses a fixed recipe: PubMed foundation, one
structured enrichment round, up to two chase rounds, no unlimited source
fan-out. These are the starting defaults, not constraints. The planner's
primary value is making smarter decisions about:

- Which sources to query (skip irrelevant ones, prioritize high-value ones)
- When to stop chasing (relevance assessment, not just entity count threshold)
- Whether to run a disconfirming search (seek contradicting evidence)
- How to order sources based on the research objective type

The planner is explicitly allowed to deviate from the deterministic recipe
within hard limits. If it discovers that DrugBank is unlikely to help for a
pure-genetics objective, it should skip DrugBank and record why.

#### Output Requirements

The orchestrator must produce:

- durable decision log
- source execution summary
- evidence summary by theme
- generated proposals and claims through existing governed paths
- open questions
- contradictions and fragile evidence where available
- research brief
- machine-readable run summary for UI and observability

### Governance Requirements

The orchestrator must follow the platform rule:

```text
AI proposes. Governance decides. Canonical graph truth is never written directly by the planner.
```

Specific requirements:

- No direct canonical relation writes from planner actions.
- All relation truth goes through claim/proposal/curation paths.
- Fact-producing agents must emit qualitative assessments first.
- Numeric scores used for ranking or promotion must be backend-derived.
- Computational hypotheses cannot self-promote.
- Human-in-loop mode remains the default.
- FULL_AUTO, when enabled, still uses existing policy thresholds and relation constraints.
- Every action must carry provenance: source, run ID, decision ID, and input snapshot.

### Safety Requirements

- Use Artana-kernel side-effect tools for mutating actions.
- Use idempotency keys for each source/action pair.
- Use capability guards so disabled sources cannot be called.
- Require approval for expensive, broad, or high-risk actions.
- Support shadow mode where the planner recommends actions but does not execute
  mutating actions.
- Enforce per-run budget limits.
- Enforce per-source rate limits.
- Preserve RLS and tenant isolation.
- Do not include PHI in prompts unless the space and user are explicitly allowed.

### Observability Requirements

The product must be able to answer:

- What did the orchestrator know at each step?
- Why did it choose this source?
- What action did it run?
- What did the action return?
- Did the verifier agree with the action result?
- How much did the run cost?
- Which generated facts entered governance?
- Which facts were rejected or escalated?
- Why did the orchestrator stop?

Minimum telemetry:

- `orchestrator.started`
- `orchestrator.decision.proposed`
- `orchestrator.decision.approved`
- `orchestrator.decision.rejected`
- `orchestrator.action.started`
- `orchestrator.action.completed`
- `orchestrator.action.failed`
- `orchestrator.verifier.completed`
- `orchestrator.round.completed`
- `orchestrator.stopped`
- `orchestrator.brief.generated`

## Recommended Architecture

### Runtime Shape

The orchestrator is a **sibling runtime** to `research_init_runtime.py`, not
nested inside it. This avoids adding planner logic to an already 2600+ line
module and naturally produces the action isolation that Milestones 2-4 need.

The orchestrator imports and calls existing helpers from
`research_init_runtime.py` and `research_init_source_enrichment.py` as tools,
but owns its own planning loop, workspace state, and decision history.

```text
Research Inbox
  -> artana_evidence_api orchestrator route
    -> FullAIOrchestratorService (sibling to research_init_runtime)
      -> Artana-kernel shell
        -> Milestones 1-2: StrongModelHarness
          -> deterministic decision recording
          -> safe action wrappers
          -> workspace artifact update
        -> Milestones 3-5: StrongModelAgentHarness
          -> Planner model step
          -> Policy/acceptance gate
          -> Allowlisted action tool (calls existing helpers)
          -> Verifier model step
          -> Workspace artifact update
      -> Existing research_init helpers (as imported tools)
      -> Existing graph governance paths
```

### Suggested Modules

```text
services/artana_evidence_api/
  full_ai_orchestrator_runtime.py
  full_ai_orchestrator_contracts.py
  full_ai_orchestrator_tools.py
  full_ai_orchestrator_policy.py
  routers/full_ai_orchestrator_runs.py

services/artana_evidence_api/tests/unit/
  test_full_ai_orchestrator_policy.py
  test_full_ai_orchestrator_contracts.py
  test_full_ai_orchestrator_runtime.py
```

This is a starting shape, not a mandate. The implementation should follow the
service-local boundaries that already exist in `services/artana_evidence_api`.

### Data Model

Start with Artana-kernel artifacts and existing run summaries. Add SQL tables
only when product queries require them.

Likely first persistent shape:

- Artana-kernel run artifacts for workspace snapshots.
- Pipeline/run summaries for timeline and traceability.
- Harness document/source metadata for source execution.
- Claim/proposal metadata with `orchestrator_decision_id`.

Possible later table:

```text
research_orchestrator_decisions
  id
  space_id
  run_id
  round_number
  action_type
  action_input
  source_key
  rationale
  evidence_basis
  status
  tool_run_id
  started_at
  completed_at
  error
  metadata_payload
```

Do not add this table until we know dashboard/query needs require SQL-level
access. Artana-kernel artifacts may be enough for the first release.

## Best Strategy

### Strategy Principle

Do not replace the whole research-init flow at once.

Build a governed shell first, then move decisions into it gradually.

### Milestone 1: Decision Ledger Around Current Flow

**Implementation status:** largely implemented

Add explicit decision records around the existing deterministic flow.

No AI planner yet.

Kernel posture: `StrongModelHarness`

This milestone is useful even without a planner because it produces assets the
agent-led phase will consume unchanged:

- a stable workspace snapshot shape
- a stable decision schema
- stable run summaries and artifact keys
- a deterministic trace of which source actions happened and why
- a baseline run that later shadow-mode planner runs can be compared against

Deliverables:

- `OrchestratorDecision` contract.
- Decision history artifact.
- Decision IDs attached to source results.
- Decision IDs attached to generated proposals/claims where practical.
- Tests proving every source action has a decision record.

Why first: this creates traceability before autonomy.

### Milestone 2: Action Registry Wrapping Existing Helpers

**Implementation status:** largely implemented

Wrap existing source and graph steps as typed orchestrator actions.

Kernel posture: `StrongModelHarness`

This milestone is the bridge into the agent phase. Its outputs are reused
directly by `StrongModelAgentHarness`:

- the planner's tool menu is the Phase A action registry
- planner safety gates rely on the same capability checks and idempotency keys
- planner verification uses the same normalized action outputs
- guarded execution later reuses the same wrappers instead of introducing a
  second set of tool contracts

Deliverables:

- Allowlisted action registry.
- Input/output schemas.
- Idempotency keys.
- Source capability checks.
- Dry-run or shadow execution mode.
- Tests proving disabled sources cannot be called.

Why second: the planner should only choose from safe tools.

### Milestone 3: Shadow-Mode AI Planner

**Implementation status:** implemented and live-evaluated

Run an Artana-kernel harness that recommends the next action, but keep the
deterministic runtime in control.

Kernel posture: `StrongModelAgentHarness`

Deliverables:

- Planner prompt and output contract.
- Workspace state summary.
- Planner recommendations stored as artifacts.
- Comparison report: planner recommendation vs deterministic action.
- Manual evaluation runner: `make full-ai-orchestrator-phase2-eval`, which writes
  JSON plus Markdown reports under `reports/full_ai_orchestrator_phase2_shadow/`.
- No mutating planner actions.

**Shadow mode success criteria (graduation gate for Milestone 4):**

- Minimum 8 shadow runs across the 4 documented objective fixtures (BRCA1,
  MED13, CFTR, PCSK9), 2 per fixture. Supplemental chase-selection and
  label-filtering fixtures can add coverage for exact chase-subset scoring and
  filtered-candidate reporting, but they do not replace the 4 objective
  fixtures.
- Human review of comparison reports: planner selects fewer irrelevant sources
  than deterministic flow in at least 3 of 4 fixtures.
- Planner never proposes a disabled source or exceeds budget in any run.
- Planner rationale fields are coherent and reference workspace state (human
  spot-check, not automated).
- Planner cost per run is within 2x of the deterministic flow's total LLM cost
  (extraction + brief, excluding planner overhead baseline).

Current evaluation note:

- The planner is now a real `StrongModelAgentHarness` integration, not a
  one-shot helper. It writes checkpoint recommendations, comparison artifacts,
  planner metadata, and evaluation summaries.
- The report enforces the automated safety gates above, including invalid
  output, fallback, disabled-source, budget, rationale-presence, and
  planner-cost handling.
- The shadow planner workspace summary exposes a conservative
  `synthesis_readiness` signal so both the planner and the evaluation harness
  can recognize closure-ready checkpoints without inventing numeric confidence.
- The evaluation report distinguishes objective-shaped
  `source_improvement_candidate` checkpoints from conservative
  `closure_improvement_candidate` checkpoints.
- The April 15, 2026 live rerun completed with deterministic baseline telemetry
  attached across the 4 objective fixtures, so the planner-vs-baseline cost
  gate is now computed from real compare runs instead of remaining `n/a`.
- The latest live report passed with 12/12 action matches, 12/12 source
  matches, 3/3 chase-action matches, 0 invalid outputs, 0 fallback or
  unavailable recommendations, planner total cost `$0.0888`, deterministic
  baseline cost `$0.3688`, and a planner-to-baseline ratio of `0.24x`.
- Graduation to Milestone 4 still depends on human review of the fixture
  reports and a deliberate rollout decision, not just automated safety parity.

If these criteria are not met, iterate on the planner prompt before proceeding
to Milestone 4.

Why third: this lets us evaluate quality without graph pollution.

### Milestone 4: Guarded AI Planner for Low-Risk Decisions

**Implementation status:** partially implemented as a narrow pilot

Let the planner choose from a small action set:

- run structured enrichment for one source
- skip a source with rationale
- stop
- escalate

Keep PubMed foundation and final governance deterministic.

Kernel posture: `StrongModelAgentHarness`

Deliverables:

- Acceptance gate for planner actions.
- Verifier step after action execution.
- Budget limits.
- Source call limits.
- Regression tests for invalid planner outputs.

Current guarded scope:

- narrow structured-source selection or deferral
- guarded chase-checkpoint stop control
- guarded bounded chase-subset continuation
- guarded brief-generation stop decisions
- verification and summary artifacts for guarded actions
- per-checkpoint guarded decision proof artifacts for allowed and blocked
  planner influence
- manual guarded comparison reports that distinguish expected narrowing from
  accepted conservative stops, real drift, live-source jitter, and downstream
  follow-up-state drift

This milestone is therefore no longer purely prospective. What remains is
expanding the guarded surface carefully and proving it repeatedly on live-style
comparisons.

Why fourth: it introduces autonomy where failure is contained.

### Milestone 5: Replace Deterministic Chase Rounds

**Implementation status:** implemented for guarded source+chase default mode

Move chase-round entity selection into the planner.

Kernel posture: `StrongModelAgentHarness`

Deliverables:

- Relevance assessment contract for new entities.
- Top-N selected entities with rationale.
- Stop if relevance or evidence quality is low.
- Tests proving noisy entities are not chased.

Current status:

- typed chase candidates and chase selections exist in the orchestrator
  contracts and workspace summaries
- chase checkpoints are exposed to the shadow planner at `after_bootstrap` and
  `after_chase_round_1`
- planner outputs for chase checkpoints are validated against the candidate set
  and can recommend either a bounded subset or `STOP`
- guarded mode can already apply and verify a planner-selected chase subset
  without changing deterministic fallback semantics
- comparison and reporting code already track chase-selection overlap and exact
  match metrics
- the live supplemental guarded rerun passed on April 16, 2026 UTC with exact
  chase-selection matches in both chase-focused fixtures and no verification
  failures

What remains:

- continued post-default monitoring on ordinary low-risk spaces
- any future authority expansion beyond source+chase must get its own proof and
  operator decision

Current rollout posture:

- guarded chase is enabled by default only inside the graduated
  `guarded_source_chase` profile
- use `deterministic` to bypass the guarded planner and return to the scripted
  runtime
- run and workspace summaries now record `guarded_chase_rollout_enabled` so
  guarded reports show whether chase steering was actually allowed for that run
- the manual guarded evaluation summary also prints the rollout state as
  `Guarded chase rollout: enabled|disabled`

Latest proof command:

`make full-ai-orchestrator-guarded-rollout-proof`

Latest proof report:

`reports/full_ai_orchestrator_guarded_rollout/<timestamp>/summary.md`

What this proof does:

- runs one real deterministic baseline
- replays the guarded orchestrator twice from that same baseline
- keeps guarded chase rollout off for the first replay
- turns guarded chase rollout on for the second replay
- proves the boundary by showing zero guarded chase actions when off and
  non-zero guarded chase actions when on

Why fifth: chase rounds are where the planner can add the most value.

### Milestone 6: Full Orchestrator Runtime

**Implementation status:** default guarded source+chase adoption is implemented

After shadow, guarded, real-space canary, settings-path canary, and
default-readiness gates passed, the orchestrator became the default
research-init planning shell for the narrow `guarded_source_chase` profile.

Kernel posture: keep `StrongModelAgentHarness`; consider `ResearchHarness` or
`SupervisorHarness` only if the runtime has grown enough to justify the extra
abstraction.

Deliverables:

- Orchestrator route or research-init integration flag.
- UI timeline of decisions and actions.
- Cost and source-call summaries.
- Production rollout flag.
- Runbook and rollback path.

At the time of this status update, the sibling runtime, planner timeline,
guarded execution summaries, and guarded default shell are real. What is not
done is broadening planner authority into graph reasoning, extraction policy,
hypothesis generation, or planner-owned canonical graph writes.

### Rollback Mechanism

The orchestrator is a sibling runtime, so rollback is natural: the existing
`research_init_runtime` remains unchanged and can be called directly.

Switching mechanism:

- Space-level setting: `research_orchestration_mode` with values
  `full_ai_guarded` (default), `full_ai_shadow`, and `deterministic`. This is
  editable by the space owner or an admin in Research Inbox space settings.
- Per-run override: the `POST /v1/spaces/{space_id}/research-init` trigger
  accepts an optional `orchestration_mode` parameter that overrides the space
  setting for one run.
- In-flight safety: changing the space setting does not affect running
  orchestrator runs. A run uses the mode selected at start time.
- `full_ai_guarded` queues the full orchestrator with `planner_mode=guarded`
  and default profile `guarded_source_chase`.
- `full_ai_shadow` queues the full orchestrator with `planner_mode=shadow`.
- `deterministic` calls `research_init_runtime` directly as the rollback path.
- A future autonomous/full mode is intentionally not exposed yet.

### Concurrency Model

The orchestrator shares the existing pipeline worker pool. It does not create
its own concurrency model.

- Orchestrator runs claim a worker slot like any other pipeline job.
- Initial rollout should use conservative concurrency and increase only after
  shadow and guarded telemetry show acceptable run duration, rate-limit
  behavior, and artifact-store load.
- Source API rate limits should be enforced from a shared runtime limiter, not
  from per-run local counters.
- If a source is rate-limited, the action fails with a retriable error. The
  planner can choose a different source or wait.
- Exact worker counts are deployment defaults, not architecture requirements.

### Objective-Shaped Routing

This is a later optimization, not a first-release requirement.

For the first orchestrator release, keep the current plan baseline intact:
literature-first discovery with PubMed as the foundational search step, then
structured enrichment, then chase rounds. Objective classification can still be
recorded for observability and shadow evaluation, but it should not silently
rewrite the baseline plan in v1.

The planner's primary value is adapting source ordering to the research
objective. Different objectives have different optimal starting points:

- **Literature-first** (default): research question in natural language. Start
  with PubMed, then structured enrichment from findings.
- **Variant-first**: seed entities are variants or genes. Start with ClinVar and
  AlphaFold for variant context, then PubMed for mechanism literature.
- **Drug-first**: seed entities are drugs. Start with DrugBank for targets, then
  PubMed for mechanism literature around those targets.
- **Disease-first**: seed entities are diseases. Start with MONDO for ontology
  context, then PubMed for associated genes, then structured enrichment.
- **Phenotype-first**: seed entities are phenotypes. Start with HPO for ontology
  context, then look for gene-phenotype associations.

In later guarded and full modes, the planner can classify the objective type
from seed entities and objective text, then use the appropriate routing
template as a starting point. Within each template, the planner can still skip
irrelevant sources or reorder based on findings.

This is NOT fully autonomous free-form planning. It is objective-aware source
routing within a governed framework. The planner adapts a template, not invents
a strategy.

## First Coding PR Recommendation

The first coding PR should not add an autonomous planner.

Recommended first PR:

**"Add orchestrator decision contracts and decision logging around current
research-init source actions."**

This PR should not change source behavior and should not introduce autonomous
planning. It should make the current deterministic behavior observable in the
same shape the future AI planner will use.

Scope:

- Add `ResearchOrchestratorDecision` Pydantic contract.
- Add a small decision recorder helper.
- Record deterministic decisions for:
  - PubMed foundation search
  - driven structured enrichment
  - bootstrap run
  - chase rounds
  - stop condition
- Attach decision IDs to `source_results["enrichment_orchestration"]`.
- Add tests proving:
  - every source execution has a decision record
  - stop decisions record a reason
  - no decision record can claim direct canonical graph writes

This gives us the audit spine. The AI planner can arrive later without changing
the observability contract.

## Testing Strategy

### Unit Tests

- Decision contract validation (core fields required, planner fields Optional).
- Planner contract validation (structured output matches tool definition).
- Action registry rejects unknown action types.
- Capability guard rejects disabled source calls via space settings lookup.
- Budget policy rejects over-budget plans.
- Stop-rule evaluation (hard limits and soft defaults).
- Qualitative assessment is required before derived numeric ranking.
- Workspace state round-trip: serialize the proposed workspace state to a
  kernel artifact, deserialize, assert equality (UUIDs, nested lists, dicts
  preserved).
- Source action vs control-flow action type separation.

### Phase A Harness Tests

These tests explain why the initial `StrongModelHarness` phase is worth doing.
They should pass before any agent-led planning is introduced.

- A deterministic research-init-shaped run writes the expected workspace
  artifact after each major step.
- Each deterministic source action appends exactly one decision artifact with a
  stable schema.
- Re-running the same deterministic action with the same replay and idempotency
  inputs does not duplicate artifacts or side effects.
- Decision artifacts and workspace state use stable `step_key` conventions so
  later planner runs can compare against them.
- Bootstrap handoff preserves orchestrator provenance (`run_id`,
  `decision_id`, source/action metadata).
- The Phase A action registry can be loaded independently of any planner and
  exposes only allowlisted actions.
- Capability guards reject disabled sources before any tool execution begins.
- The normalized action outputs are sufficient to build a planner workspace
  summary later without re-reading raw source payloads.

### Integration Tests

- Research-init run produces decision history.
- Existing deterministic path still runs unchanged.
- Structured enrichment action wrappers call existing helpers.
- Bootstrap action wrapper stages claims through existing governance.
- Shadow planner writes recommendations but performs no mutating actions.
- Decision IDs survive bootstrap handoff (research_init to research_bootstrap).

### Regression Tests

- Planner cannot write canonical relations directly.
- Planner cannot call a source disabled in the space preferences.
- Planner cannot exceed max rounds (hard limit).
- Re-running a tool with the same idempotency key does not duplicate source docs,
  proposals, claims, or graph observations.
- Planner output missing rationale is rejected.
- Planner output with numeric confidence but no qualitative assessment is rejected.
- Computational hypotheses remain excluded from auto-promotion.

### Verifier Tests

- Verifier rejects clearly bad action result (e.g., ClinVar returns zero results
  for a known pathogenic variant gene).
- Verifier passes clearly good result (source returned relevant data matching the
  decision rationale).
- Verifier handles partial success (some results, some errors) with appropriate
  pass/flag behavior.

### Evaluation Harness

Use fixtures for known research objectives:

- BRCA1 and PARP inhibitors (literature-first objective)
- MED13 and congenital heart disease (gene-first objective)
- CFTR and cystic fibrosis (disease-first objective)
- PCSK9 and lipid metabolism (drug-repurposing objective)

Each fixture should include a snapshot workspace state at multiple rounds to
serve as eval test inputs.

**Planner eval tests (regression safety net for prompt changes):**

- Given BRCA1 workspace at round 1 (no prior evidence), planner chooses a
  source action (not STOP).
- Given MED13 workspace at round 3 (sufficient evidence), planner chooses STOP
  or GENERATE_BRIEF.
- Planner output always includes non-empty qualitative_rationale that references
  workspace state.
- Planner does not over-query: with sufficient evidence and budget at 50%,
  stops within budget.
- When objective-shaped routing is enabled, planner can prioritize
  variant-first objectives toward ClinVar/AlphaFold without violating rollout
  guardrails.
- When contradiction-search actions are enabled, planner can propose a
  contradiction-seeking read action when strong support exists.

Compare:

- deterministic current flow
- shadow planner recommendations
- guarded planner actions

Metrics:

- useful sources selected
- irrelevant source calls avoided
- source cost
- generated claim/proposal count
- cross-source links discovered
- contradictions/gaps surfaced
- disconfirming searches triggered
- curator acceptance rate
- brief usefulness score
- proposal volume per run (curator capacity check)

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Planner over-queries sources | Budget limits, source-call caps, stop rules |
| Planner chases noisy entities | relevance assessment, verifier step, max entity count |
| Planner bypasses governance | action registry excludes direct canonical writes |
| Prompt drift changes behavior | Artana-kernel replay, stable step keys, shadow comparison, prompt versioning |
| Source API costs/rate limits | per-source capability metadata, shared rate-limit counters |
| Hard-to-debug decisions | durable decision ledger and trace summaries |
| Graph pollution | shadow mode first, human-in-loop default, governance enforcement |
| Huge rewrite risk | incremental milestones, keep current deterministic path as fallback |
| Confirmation bias (only supporting evidence) | contradiction-seeking read action, planner prompted to seek contradicting evidence |
| Proposal volume overwhelms curators | proposal count in stop rules, configurable curator capacity threshold |
| Added latency from planner calls | model-tier strategy, batch decisions, shadow-mode latency measurement |

## Open Questions

- ~~Should the first orchestrator run live inside `research_init_runtime`, or
  should it be a sibling runtime?~~ **Resolved: sibling runtime.** See Runtime
  Shape section.
- Should Artana-kernel artifacts be the primary decision store, or should we add
  SQL decision tables immediately?
- What is the minimum UI needed for "why did it do this?"
- Which sources are safe for autonomous use by default?
- What run budget should be the default for research spaces?
- ~~Should ontology loading be part of the orchestrator, or treated as a
  space-level prerequisite outside the research run?~~ **Likely resolved:
  ontology loading is a platform-level operation, not a per-research-run
  action.** Ontologies are versioned platform assets. The orchestrator assumes
  they are already loaded.
- Should the orchestrator choose extraction prompts/policies, or only source
  actions?
- How should source queries be audited for privacy when the research objective
  contains sensitive terms? (Source queries can leak research intent to external
  APIs.)

## Non-Goals For The First Release

- No autonomous canonical graph writes.
- No whole-space all-pairs gap discovery.
- No unlimited recursive research loops.
- No PHI-aware patient-data integration.
- No replacement of existing claim governance.
- No removal of deterministic research-init until shadow and guarded modes prove
  quality and safety.

## Success Definition

The Full AI Orchestrator is successful when:

- Researchers see a clear decision timeline.
- The system explains why each source was queried.
- The graph gains more useful cross-source evidence than the deterministic flow.
- Irrelevant source calls decrease.
- Curators trust the generated proposals more, not less.
- Every generated claim remains governed.
- Runs are replayable, observable, and bounded by policy.

The first visible product win should be a brief that says not just "we queried
these sources," but "we chased this specific lead because these earlier findings
made it relevant."
