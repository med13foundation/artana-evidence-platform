# Full AI Orchestrator Milestone 3 Review

**Review date:** April 13, 2026  
**Reviewed report:** `reports/full_ai_orchestrator_phase2_shadow/20260414_044654/summary.md`

## Purpose

This note records the current Milestone 3 shadow-planner review outcome after:

- the fixture-alignment fixes,
- the live Phase 2 evaluation rerun,
- the source-selection improvement pass,
- the closure-readiness and stage-guard pass,
- and the planner-cost instrumentation that now derives planner cost from
  observed token usage plus configured model pricing when the provider path
  reports zero-dollar placeholders.

It answers one question:

**Are we ready to move from Milestone 3 shadow mode to Milestone 4 guarded
planner execution?**

## Current Automated Outcome

The latest shadow evaluation is clean on the automated safety gates and now
shows the intended value-demonstration surface:

- 4 fixtures
- 8 runs
- 13 checkpoints
- 11 / 13 action matches
- 12 / 13 source matches
- 1 source-improvement candidate
- 2 closure-improvement candidates
- 0 disabled-source violations
- 0 budget violations
- 0 invalid outputs
- 0 fallback recommendations
- 0 unavailable recommendations
- 100% qualitative-rationale coverage

The report now correctly shows:

- planner cost telemetry: `available`
- deterministic baseline cost telemetry: `available`
- planner total cost: `$0.1131`
- deterministic baseline cost: `$0.3495`
- planner cost gate: `PASS` (`0.32x` baseline)

## Human Review Observations

### 1. Rationale quality is acceptable

Across BRCA1, CFTR, MED13, and PCSK9, the planner rationales are coherent and
grounded in workspace state. They refer to:

- whether PubMed evidence exists yet,
- which structured sources are still pending,
- whether chase rounds were skipped for threshold reasons,
- whether the run is at a terminal stop point.

This satisfies the "qualitative assessment first" expectation for shadow mode.

### 2. Safety posture is good

The planner is not suggesting disabled sources, not exceeding budgets, and not
escaping the live action menu. The new stage guards also prevent two specific
failure modes that showed up during live evaluation:

- skipping PubMed ingest while literature grounding is still pending, and
- replacing the terminal `STOP` checkpoint with `GENERATE_BRIEF`.

In practice, it is behaving like a disciplined reader of the workspace summary
rather than an improvising agent.

### 3. The planner now shows plausible improvement in 3 of 4 fixtures

This is the key review result.

Milestone 3 in `docs/full_AI_orchestrator.md` asks for human review that the
planner shows fewer irrelevant source choices or better closure judgment than
the deterministic flow in at least 3 of 4 fixtures.

The refreshed official fixture set now surfaces exactly that:

- **BRCA1:** after PubMed ingest/extract, the planner keeps the same action
  class (`RUN_STRUCTURED_ENRICHMENT`) but prefers `drugbank` over the
  deterministic `clinvar` path because the objective is explicitly about PARP
  inhibitor response and the workspace routing hints rank drug-mechanism
  evidence first.
- **CFTR:** after the first chase round, the planner recommends
  `GENERATE_BRIEF` instead of opening another chase round because the workspace
  shows the chase threshold was already missed and no structured follow-up is
  pending.
- **MED13:** after the first chase round, the planner again recommends
  `GENERATE_BRIEF` because grounded evidence is already present and the
  workspace shows no pending questions, evidence gaps, contradictions, or
  errors.

Those are not random mismatches. They are the two exact classes of improvement
the comparison harness was designed to recognize:

- objective-shaped source selection, and
- conservative closure instead of another low-yield chase round.

That gives us a much better answer than simple parity. The planner is still
bounded by the deterministic runtime, but the shadow report now demonstrates
where the planner's judgment could be useful once guarded execution is allowed.

## Graduation Decision

**Decision: Milestone 3 now meets its technical graduation bar.**

What is true today:

- shadow mode is safe,
- comparison reporting is credible,
- fixture expectations are aligned with runtime behavior,
- planner-cost reporting is honest and computed,
- and the official evaluation now demonstrates planner-value candidates in
  3 of 4 fixtures.

What still remains before production guarded rollout:

- a maintainer product judgment that these three candidate improvements are
  good enough to justify Milestone 4,
- and then a narrow guarded-execution PR that keeps the action menu small and
  rollback easy.

## Recommended Next PR

The next orchestrator PR should move to **Milestone 4 guarded execution for a
small action set**, not more fixture work.

Recommended target:

### Milestone 4 guarded planner pilot

Allow the planner to choose only low-risk actions while the deterministic
runtime and governance layers keep ownership of the real work.

Concrete goals:

- keep PubMed grounding and final governance deterministic;
- allow guarded planner choices only for:
  - structured-source selection,
  - conservative closure (`GENERATE_BRIEF`),
  - `STOP`,
  - and `ESCALATE_TO_HUMAN`;
- preserve all current validation, disabled-source checks, budget checks, and
  rollback posture;
- keep the shadow comparison artifacts so guarded runs can still be audited
  against the deterministic baseline.

## Bottom Line

Milestone 3 is now in a healthy state technically:

- safe,
- reproducible,
- honestly reported,
- and able to show planner-value candidates in the official evaluation set.

The next step is no longer more measurement repair. The next step is a narrow
guarded-execution pilot that turns the proven low-risk planner judgments into
real, reviewable behavior without giving up deterministic rollback.
