# Full AI Orchestrator Rollout Runbook

**Audience:** operators and reviewers widening Full AI Orchestrator usage.

**Scope:** rollout, rollback, and human review for the `research-init`
orchestration modes:

- `deterministic`
- `full_ai_shadow`
- `full_ai_guarded`

This is operator guidance only. It does not change runtime behavior.

## Operating Modes

### `deterministic`

Use this as the rollback target.

Behavior:

- queues the existing deterministic `research-init` runtime
- keeps planner output out of the execution path
- remains the clearing setting when shadow or guarded evidence is incomplete

Choose this mode when:

- a space handles high-value or time-sensitive research
- proof reports are missing, stale, or failing
- guarded readiness is not clean
- operators see compare drift they cannot explain

### `full_ai_shadow`

Use this to observe planner judgment without planner control.

Behavior:

- queues the sibling full orchestrator with `planner_mode=shadow`
- records planner recommendations, timelines, and comparison artifacts
- preserves deterministic execution ownership

Choose this mode when:

- the deterministic path is healthy
- operators want planner-quality evidence before guarded rollout
- current shadow reports pass their automated gates
- there is no need for planner influence yet

### `full_ai_guarded`

Use this as the default research-init shell after proof review.

Behavior:

- queues the sibling full orchestrator with `planner_mode=guarded`
- applies planner influence only through the configured guarded rollout profile
- writes guarded execution, guarded readiness, and proof receipt artifacts
- fails closed for invalid, fallback, disabled, budget-breaking, unverified, or
  policy-disallowed decisions

Current rollout profiles:

- `guarded_source_chase`: default guarded profile; allows planner narrowing of
  enabled live evidence sources, bounded chase candidate subsets, and guarded
  `STOP` only at chase checkpoints. This is the graduated default profile and
  is also selectable per run or per guarded space.
- `guarded_dry_run`: records guarded posture without
  applying guarded actions.
- `guarded_chase_only`: enabled by `ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT=1`;
  allows guarded chase selection, terminal control, and brief generation.
- `guarded_low_risk`: enabled by
  `ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE=guarded_low_risk`; allows the
  broader manual-experiment surface, including prioritized structured-source
  sequence decisions plus chase, terminal-control, and brief-generation
  decisions.

## Preflight

Run preflight from the repo root:

```bash
make full-ai-orchestrator-phase2-eval-fast
make full-ai-orchestrator-guarded-profile-proof
make full-ai-orchestrator-guarded-profile-proof-stop
make full-ai-orchestrator-guarded-graduation-gate
make full-ai-orchestrator-source-chase-graduation-gate
make full-ai-orchestrator-guarded-canary-report
```

Expected report locations:

- shadow evaluation:
  `reports/full_ai_orchestrator_phase2_shadow/<timestamp>/summary.md`
- shadow evaluation JSON:
  `reports/full_ai_orchestrator_phase2_shadow/<timestamp>/summary.json`
- guarded rollout profile proof:
  `reports/full_ai_orchestrator_guarded_rollout/<timestamp>/summary.md`
- guarded rollout profile proof JSON:
  `reports/full_ai_orchestrator_guarded_rollout/<timestamp>/summary.json`
- guarded graduation gate:
  `reports/full_ai_orchestrator_guarded/<timestamp>/summary.md`
- guarded graduation gate JSON:
  `reports/full_ai_orchestrator_guarded/<timestamp>/summary.json`
- source+chase graduation gate:
  `reports/full_ai_orchestrator_guarded/<timestamp>/summary.md`
- source+chase graduation gate JSON:
  `reports/full_ai_orchestrator_guarded/<timestamp>/summary.json`
- guarded source+chase canary report:
  `reports/full_ai_orchestrator_guarded_canary/<timestamp>/summary.md`
- guarded source+chase canary report JSON:
  `reports/full_ai_orchestrator_guarded_canary/<timestamp>/summary.json`

For a slower release review sweep, run:

```bash
make full-ai-orchestrator-guarded-profile-proof-exhaustive
make full-ai-orchestrator-guarded-graduation-gate-exhaustive
make full-ai-orchestrator-source-chase-graduation-gate-exhaustive
make full-ai-orchestrator-guarded-canary-report-exhaustive
```

Do not widen guarded mode when preflight cannot reach live planner access. The
scripts fail early when `OPENAI_API_KEY` is unavailable or planner model
configuration cannot be resolved.

## Current Default

After the April 18, 2026 operator decision, a research-init request with no
override uses `full_ai_guarded` with `guarded_source_chase`.

Current mode meanings:

- no override: guarded source+chase default
- `deterministic`: explicit rollback to the scripted runtime
- `full_ai_shadow`: observation-only planner comparison
- `full_ai_guarded` plus `guarded_dry_run`: proof-only guarded shell
- `full_ai_guarded` plus `guarded_low_risk`: manual experiment only

The default flip does not grant planner-owned graph writes, graph reasoning
ownership, extraction-policy ownership, or hypothesis generation ownership.

## Canary Rollout

The rollout sequence used for graduation was:

`deterministic` -> `full_ai_shadow` -> `full_ai_guarded` with
`guarded_dry_run` -> `full_ai_guarded` with `guarded_source_chase`

1. Start in `deterministic`.

   Confirm the target research space completes a normal `research-init` run and
   produces the expected brief and artifacts.

2. Move one low-risk space to `full_ai_shadow`.

   Use the owner/admin Research Inbox space setting for "Kickoff mode", or a
   request-level orchestration override when running a controlled test. Keep the
   space in shadow until the planner timeline and shadow comparison are
   explainable.

3. Review shadow evidence.

   The latest shadow report should show clean automated gates, no invalid
   planner outputs, no unavailable recommendations, and planner cost within the
   documented gate relative to deterministic baseline telemetry.

4. Move one low-risk space to `full_ai_guarded` with `guarded_dry_run`.

   This confirms guarded artifacts and readiness surfaces without applying
   planner influence.

5. Widen only to a named guarded profile.

   Use `guarded_source_chase` for the next reviewed canary profile. Use
   `guarded_low_risk` only for manual experiments. Do not enable multiple knobs
   as a way to bypass review; the named profile is the operator contract being
   reviewed.

6. Run the canary evidence pack before widening further.

   Use `make full-ai-orchestrator-guarded-canary-report` for the practical
   supplemental pack and
   `make full-ai-orchestrator-guarded-canary-report-exhaustive` for the slower
   repeated all-fixture pack. The canary report must end with verdict `pass`.
   `hold` means review first; `rollback_required` means return to
   `deterministic`.

7. Run the real-space canary before discussing wider adoption.

   After fixture canaries are clean, run:

   `make full-ai-orchestrator-real-space-canary SPACE_ID=<space-id> OBJECTIVE="..." SEED_TERMS="MED13,BRCA1"`

   For a low-risk cohort review, run:

   `make full-ai-orchestrator-real-space-canary SPACE_IDS="<space-a>,<space-b>" OBJECTIVE="..." SEED_TERMS="MED13,BRCA1" REPEAT_COUNT=2 EXPECTED_RUN_COUNT=12`

   In local development, the Make target now defaults to test-header auth when
   you do not provide `ARTANA_EVIDENCE_API_KEY` or
   `ARTANA_EVIDENCE_API_BEARER_TOKEN`. That keeps the live canary aimed at the
   orchestrator instead of failing early on local auth setup.

   The live runner queues the same objective through:

   - `full_ai_shadow`
   - `full_ai_guarded` with `guarded_dry_run`
   - `full_ai_guarded` with `guarded_source_chase`

   It writes reports under
   `reports/full_ai_orchestrator_real_space_canary/<timestamp>/`. The report
   must end with verdict `pass`. `hold` means coverage or exercised-authority
   evidence is still insufficient. `rollback_required` means the live canary
   produced a failure, malformed payload, timeout, invalid/fallback planner
   output, missing proof receipt, or source-policy violation and the space
   should return to `deterministic`.

   The report now also includes a per-space rollout summary and a cohort
   status. Treat `single_space_reference_only` as useful but not enough for a
   wider adoption review. Treat `multi_space_partial` as acceptable only when
   the cohort verdict is `pass`, all automated gates are clean, and multiple
   ordinary spaces exercise source+chase authority. Continue accumulating
   ordinary low-risk canaries before any default-adoption decision.

   Current passing reference:

   - `reports/full_ai_orchestrator_real_space_canary/20260418_002225/summary.md`

   Current passing ordinary-cohort reference:

   - `reports/full_ai_orchestrator_real_space_canary/20260418_062106/summary.md`

   Current passing active-cohort completion reference:

   - `reports/full_ai_orchestrator_real_space_canary/20260418_071847/summary.md`

   Current passing settings-enabled small-canary reference:

   - `reports/full_ai_orchestrator_real_space_canary/20260418_130004/summary.md`

   Current settings-path proof summary for the same small canary:

   - `reports/full_ai_orchestrator_settings_canary/20260418_125948/summary.md`

   Current passing additional CFTR low-risk cohort:

   - `reports/full_ai_orchestrator_real_space_canary/20260418_144646/summary.md`

   Current settings-enabled CFTR widening:

   - `reports/full_ai_orchestrator_settings_canary/20260418_182547/summary.md`

   Current settings-enabled MED13 widening:

   - `reports/full_ai_orchestrator_settings_canary/20260418_184841/summary.md`

   The single-space reference came from an existing supplemental bounded-chase
   space and exercised both a verified source-selection intervention and a
   verified guarded `STOP` at the `after_bootstrap` chase checkpoint. The
   ordinary cohort then showed 9/9 completed runs, 0 failures, 0 timeouts, 3
   source interventions, 3 chase/stop interventions, and 2
   authority-exercised spaces. The active completion cohort showed another 9/9
   completed runs, 0 failures, 0 timeouts, 3 source interventions, 2
   chase/stop interventions, and 1 authority-exercised space. Treat these
   reports as the current operator-proof references. The settings-enabled
   small canary then showed the actual space-setting path can run cleanly: the
   settings-path proof summary had 3 completed guarded runs, 3 source
   interventions, 5 chase/stop interventions, 3 authority-exercised runs, and
   8 verified proof receipts; the standard real-space canary runner had 9/9
   completed runs with 0 failures, 0 timeouts, 0 malformed payloads, 3 source
   interventions, 2 chase/stop interventions, and 1 authority-exercised run.
   The additional corrected CFTR cohort had another 9/9 completed runs with 0
   failures, 0 timeouts, 0 malformed payloads, 3 source interventions, 3
   chase/stop interventions, and 2 authority-exercised runs.
   The two CFTR spaces that had per-space `pass` were then widened into
   settings-based canary mode and checked through the normal research-init
   product path. That settings-enabled CFTR widening had 2/2 completed runs, 0
   failures, 0 timeouts, 2 source interventions, 3 chase/stop interventions, 2
   authority-exercised runs, and 5 verified proof receipts. The CFTR
   clean-hold space stayed deterministic.
   The two MED13 spaces that had per-space `pass` were also widened into
   settings-based canary mode and checked through the normal research-init
   product path. That settings-enabled MED13 widening had 2/2 completed runs,
   0 failures, 0 timeouts, 2 source interventions, 4 chase/stop interventions,
   2 authority-exercised runs, and 6 verified proof receipts. The MED13
   clean-hold space stayed deterministic.
   For more ordinary low-risk spaces, a verdict of `hold` can still be
   legitimate when no live chase opportunity materializes in the guarded run.

   Before discussing default adoption, run a second normal product-path cycle
   across the monitored settings-enabled spaces:

   `make full-ai-orchestrator-settings-canary-cycle SPACE_IDS="366b8d14-f704-4e42-a40e-be21b1b8869b,1cc6396d-e852-4aae-bb93-c32e89707bcc,2f6e1da1-45f1-4048-b223-b5e7a0a5d1b6,487badd9-4897-4f3e-9b3e-d481da5fafcf,d2147b2f-87ca-4f3b-9526-a9e41a0a9ea2,ebbca89d-6a29-4ea5-ace6-a7de3cc62221,44295e6d-2f35-4a42-9de1-1a5fba6b07be" OBJECTIVE="Run the second settings-path guarded source+chase readiness cycle across the monitored low-risk spaces, prioritizing enabled live evidence sources and stopping when chase candidates look weak or repetitive." SEED_TERMS="BRCA1,olaparib,PCSK9,LDL cholesterol,CFTR,cystic fibrosis,MED13,congenital heart disease" EXPECTED_RUN_COUNT=7`

   Then run the default-readiness gate over all selected settings-path canary
   reports:

   `make full-ai-orchestrator-default-readiness-gate SETTINGS_REPORTS="reports/full_ai_orchestrator_settings_canary/20260418_125948/summary.json,reports/full_ai_orchestrator_settings_canary/20260418_182547/summary.json,reports/full_ai_orchestrator_settings_canary/20260418_184841/summary.json,reports/full_ai_orchestrator_settings_canary/20260418_191638/summary.json" MONITORED_SPACE_IDS="366b8d14-f704-4e42-a40e-be21b1b8869b,1cc6396d-e852-4aae-bb93-c32e89707bcc,2f6e1da1-45f1-4048-b223-b5e7a0a5d1b6,487badd9-4897-4f3e-9b3e-d481da5fafcf,d2147b2f-87ca-4f3b-9526-a9e41a0a9ea2,ebbca89d-6a29-4ea5-ace6-a7de3cc62221,44295e6d-2f35-4a42-9de1-1a5fba6b07be" OPERATOR_DECISION=approved_for_default_discussion`

   The default-readiness gate writes reports under
   `reports/full_ai_orchestrator_default_readiness/<timestamp>/`. It exits
   non-zero for both `hold` and `rollback_required`; that is intentional
   because only a `pass` means the selected evidence is ready for default
   discussion. The current passing gate is:

   - `reports/full_ai_orchestrator_default_readiness/20260418_194423/summary.md`

   It returned `pass` with clean evidence: 7 monitored spaces, 14 clean
   settings-path runs, 14 authority-exercised clean runs, 0 failed runs, 0
   timed-out runs, 0 invalid/fallback outputs, and 0 proof verification
   failures. This opened default-adoption discussion and supported the later
   operator default decision.

   After selecting the reports that should count toward a rollout review, run:

   `make full-ai-orchestrator-rollout-review CANARY_REPORTS="reports/full_ai_orchestrator_real_space_canary/20260418_002225/summary.json,reports/full_ai_orchestrator_real_space_canary/20260418_062106/summary.json,reports/full_ai_orchestrator_real_space_canary/20260418_071847/summary.json,reports/full_ai_orchestrator_real_space_canary/20260418_130004/summary.json,reports/full_ai_orchestrator_real_space_canary/20260418_144646/summary.json"`

   The rollout review writes a single operator summary under
   `reports/full_ai_orchestrator_rollout_review/<timestamp>/`. It fails on
   rollback reports, malformed evidence, failed/timed-out runs, invalid or
   fallback planner outputs, budget violations, source-policy violations, or
   insufficient pass/intervention coverage. The current selected evidence pack
   is:

   - `reports/full_ai_orchestrator_rollout_review/20260418_122808/summary.md`

   Current follow-up review including the settings-enabled small canary:

   - `reports/full_ai_orchestrator_rollout_review/20260418_131238/summary.md`

   Current follow-up review including the additional CFTR cohort:

   - `reports/full_ai_orchestrator_rollout_review/20260418_150738/summary.md`

   Record the human/operator decision in
   `docs/full_ai_orchestrator_operator_review.md` before changing default
   behavior. The current approved decision is `approved_for_default` only for
   `full_ai_guarded + guarded_source_chase`.

8. Hold the canary until proof receipts are clean.

   The space should produce `full_ai_orchestrator_guarded_readiness` and
   `full_ai_orchestrator_guarded_decision_proofs`. For applied guarded actions,
   proof receipts must be allowed, policy-allowed, verified, and tied to an
   applied action.

9. Expand gradually.

   Prefer one space, then a small cohort of low-risk spaces, then broader
   adoption. Stop expansion immediately on blocked readiness, missing receipts,
   repeated fixture failures, unexplained drift, or model/rate-limit instability.

## Proof And Report Artifacts

Review both generated reports and per-run artifacts.

Generated proof reports:

- `reports/full_ai_orchestrator_phase2_shadow/<timestamp>/summary.md`
- `reports/full_ai_orchestrator_phase2_shadow/<timestamp>/summary.json`
- `reports/full_ai_orchestrator_guarded_rollout/<timestamp>/summary.md`
- `reports/full_ai_orchestrator_guarded_rollout/<timestamp>/summary.json`
- `reports/full_ai_orchestrator_guarded/<timestamp>/summary.md`
- `reports/full_ai_orchestrator_guarded/<timestamp>/summary.json`
- `reports/full_ai_orchestrator_guarded_canary/<timestamp>/summary.md`
- `reports/full_ai_orchestrator_guarded_canary/<timestamp>/summary.json`
- `reports/full_ai_orchestrator_real_space_canary/<timestamp>/summary.md`
- `reports/full_ai_orchestrator_real_space_canary/<timestamp>/summary.json`
- `reports/full_ai_orchestrator_rollout_review/<timestamp>/summary.md`
- `reports/full_ai_orchestrator_rollout_review/<timestamp>/summary.json`

Durable guarded artifacts:

- `full_ai_orchestrator_guarded_execution`
- `full_ai_orchestrator_guarded_readiness`
- `full_ai_orchestrator_guarded_decision_proofs`
- `full_ai_orchestrator_guarded_decision_proof_<id>`

Useful supporting artifacts:

- `full_ai_orchestrator_decision_history`
- `full_ai_orchestrator_shadow_planner_timeline`
- `full_ai_orchestrator_shadow_planner_comparison`
- `full_ai_orchestrator_source_execution_summary`
- `full_ai_orchestrator_chase_rounds`
- `full_ai_orchestrator_brief_metadata`

The profile-proof reports are boundary proofs. They reuse a deterministic
baseline and replay guarded profiles counterfactually, so pending verification
can be expected there. The graduation gate is the post-execution proof. Use the
graduation gate to decide whether applied guarded influence is ready to widen.

## Readiness Review Rubric

Approve widening only when all of these are true:

- The target mode and profile are explicit.
- The latest shadow report passes automated gates.
- The relevant profile proof shows the expected profile boundary:
  `guarded_dry_run` applies no actions, `guarded_chase_only` does not apply
  structured-source steering, `guarded_source_chase` limits authority to
  enabled live evidence source selection plus chase/stop decisions, and
  `guarded_low_risk` stays within its manual-experiment eligibility surface.
- The guarded graduation gate passes.
- For `guarded_source_chase`, the source+chase graduation gate also passes.
- For `guarded_source_chase`, the canary report verdict is `pass`.
- `summary.json` shows no fixture errors.
- `summary.json` shows no timed-out fixtures.
- `summary.json` shows no verification failures and no pending verifications.
- At least one guarded action was applied in the graduation gate.
- For `guarded_source_chase`, at least one source-selection intervention and
  one chase-or-stop intervention are observed across the fixture set.
- Guarded proof summaries and reviewable proof receipts are present.
- At least one allowed proof receipt exists.
- No proof receipt is blocked or ignored for the profile being widened.
- Allowed proof receipts are verified, policy-allowed, and tied to applied
  actions.
- No proof receipt shows fallback recommendation, invalid planner output,
  budget violation, disabled-source violation, reserved-source violation,
  context-only violation, grounding violation, or missing qualitative rationale.
- Compare drift is either absent or classified as expected live-source jitter,
  guarded narrowing, expected follow-on drift, or another documented acceptable
  divergence.
- A human reviewer can explain the planner's qualitative rationale in plain
  language.

Hold rollout when any item is false or ambiguous.

## Rollback

Rollback target is always `deterministic`.

Immediate rollback triggers:

- `full_ai_orchestrator_guarded_readiness.status` is
  `blocked_guarded_decision_proofs`
- any allowed guarded receipt is not verified
- any proof receipt has `decision_outcome=blocked` or `decision_outcome=ignored`
  during a widening canary
- planner output is invalid, unavailable, or repaired through fallback
- a guarded action violates budget, disabled-source, or policy boundaries
- the canary report verdict is `rollback_required`
- compare drift is classified as execution drift or needs review
- reports fail to write, disappear, or cannot be tied to the run under review
- rate limits make planner behavior intermittent

Rollback steps:

1. Set the affected space's "Kickoff mode" to `deterministic`.
2. Remove guarded rollout environment overrides from the affected deployment:
   `ARTANA_ENABLE_GUARDED_CHASE_ROLLOUT` and
   `ARTANA_FULL_AI_ORCHESTRATOR_GUARDED_PROFILE`.
3. Restart or redeploy the affected service process so environment changes take
   effect.
4. Run one deterministic research-init smoke run for the affected space.
5. Preserve the failed guarded or canary report directory and run artifacts for
   review.
6. Do not re-enable guarded mode until a new preflight, canary review, and
   readiness review pass.

## Troubleshooting

### Missing Proof Receipts

Symptoms:

- `full_ai_orchestrator_guarded_decision_proofs` is missing.
- `guarded_decision_proofs_key` is absent from the workspace summary.
- the graduation gate fails `proof_summaries_present` or
  `reviewable_proofs_present`.

Operator response:

- Confirm the run actually used `full_ai_guarded`, not `deterministic` or
  `full_ai_shadow`.
- Confirm the report is a guarded graduation gate report, not only a rollout
  profile proof.
- Check the run's `full_ai_orchestrator_guarded_execution` artifact. If no
  guarded checkpoint was reviewed, keep the space in dry-run or shadow until a
  reviewable checkpoint appears.
- Roll back to `deterministic` for any widening canary where receipts are
  expected but missing.
- For canary runs, also require
  `reports/full_ai_orchestrator_guarded_canary/<timestamp>/summary.json`.

### Blocked Decisions

Symptoms:

- readiness status is `blocked_guarded_decision_proofs`
- proof receipts contain `decision_outcome=blocked`
- the graduation gate fails `no_blocked_or_ignored_proofs`

Operator response:

- Treat the block as a successful fail-closed event, not as permission to widen.
- Read the receipt's `outcome_reason`, `guarded_strategy`, rollout profile, and
  policy version.
- If the block is due to a rollout profile boundary, either keep the narrower
  profile or run the appropriate profile proof before widening.
- If the block is due to invalid output, fallback, budget, disabled source,
  reserved/context-only/grounding selection, or missing rationale, keep the
  space in `deterministic` or `full_ai_shadow` until the planner or policy
  issue is fixed.

### Artifact Failures

Symptoms:

- reports are not written under `reports/full_ai_orchestrator_*`
- `summary.md` exists but `summary.json` is missing
- workspace artifacts are missing from a completed run
- the runner exits before printing `Summary JSON:` and `Summary Markdown:`

Operator response:

- Re-run the relevant proof command and capture the terminal error.
- Check for graph sync errors. If the error mentions signature verification,
  restart backend and graph service with matching `AUTH_JWT_SECRET` and
  `GRAPH_JWT_SECRET`.
- Check local disk permissions and available space for the `reports/` tree.
- Treat missing artifacts as a rollback condition for guarded canaries.
- For canary runs, require both the guarded graduation report and the canary
  report under `reports/full_ai_orchestrator_guarded_canary/`.

### Compare Drift

Symptoms:

- report summary has execution drift, downstream-state drift, guarded-narrowing
  drift, live-source jitter, or review-needed drift
- fixture rows show mismatches even though guarded actions verified

Operator response:

- Accept only drift classes the report marks as expected or acceptable.
- Investigate `execution_drift` and `needs_review` before any widening.
- For `live_source_jitter`, confirm the mismatch is limited to rerunning live
  sources in separate spaces.
- For `downstream_state_drift`, confirm evidence counts and matched planner
  decisions still align, and that drift is limited to follow-up state such as
  pending-question wording or summary fields.
- For `guarded_narrowing_drift`, confirm the drift follows the intentionally
  narrowed guarded source path.

### Rate Limits Or Planner Access

Symptoms:

- preflight fails with missing planner access
- shadow report has unavailable recommendations
- guarded runs intermittently miss planner checkpoints
- proof commands fail with provider rate-limit errors

Operator response:

- Confirm `OPENAI_API_KEY` is configured in the environment running the proof or
  service.
- Confirm the model registry can resolve the planner capability used by the
  runner.
- Re-run with the fast shadow command only after provider access stabilizes:
  `make full-ai-orchestrator-phase2-eval-fast`.
- Do not widen guarded mode while planner access is intermittent. Keep the space
  in `deterministic` or `full_ai_shadow`.

## Operator Notes

- The profile-proof commands prove rollout switches. The graduation gate proves
  applied guarded decisions.
- `deterministic` is not a degraded mode. It is the trusted baseline and the
  clearing target.
- A blocked guarded decision is a safety signal. Widen only after the block is
  understood and a fresh proof passes.
- Keep report directories intact during review. They are the audit trail for why
  a mode was widened or rolled back.
