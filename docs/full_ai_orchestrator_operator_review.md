# Full AI Orchestrator Operator Review

**Status date:** April 18, 2026

## Decision

`guarded_source_chase` is **approved_for_small_canary**,
**approved_for_default_discussion**, and **approved_for_default**.

The deterministic research-init runtime remains the explicit rollback path.

This review approves only the narrow guarded profile that may apply enabled
live-evidence source narrowing, bounded chase candidate subsets, and guarded
`STOP` at chase checkpoints. It does not approve `guarded_low_risk`, planner
graph reasoning ownership, extraction policy ownership, hypothesis generation
ownership, or canonical graph writes.

## Evidence Pack

Selected rollout review:

- `reports/full_ai_orchestrator_rollout_review/20260418_122808/summary.md`
- `reports/full_ai_orchestrator_rollout_review/20260418_122808/summary.json`
- Follow-up review after the settings-based canary:
  `reports/full_ai_orchestrator_rollout_review/20260418_131238/summary.md`
- Follow-up review JSON:
  `reports/full_ai_orchestrator_rollout_review/20260418_131238/summary.json`
- Follow-up review after the additional CFTR cohort:
  `reports/full_ai_orchestrator_rollout_review/20260418_150738/summary.md`
- Follow-up CFTR review JSON:
  `reports/full_ai_orchestrator_rollout_review/20260418_150738/summary.json`

Selected real-space evidence:

- Supplemental reference:
  `reports/full_ai_orchestrator_real_space_canary/20260418_002225/summary.md`
- Ordinary three-space cohort:
  `reports/full_ai_orchestrator_real_space_canary/20260418_062106/summary.md`
- Active three-space cohort:
  `reports/full_ai_orchestrator_real_space_canary/20260418_071847/summary.md`
- Settings-enabled small canary:
  `reports/full_ai_orchestrator_real_space_canary/20260418_130004/summary.md`
- Settings-enabled small canary JSON:
  `reports/full_ai_orchestrator_real_space_canary/20260418_130004/summary.json`
- Settings-path stabilized proof summary:
  `reports/full_ai_orchestrator_settings_canary/20260418_125948/summary.md`
- Settings-path stabilized proof summary JSON:
  `reports/full_ai_orchestrator_settings_canary/20260418_125948/summary.json`
- Additional CFTR three-space cohort:
  `reports/full_ai_orchestrator_real_space_canary/20260418_144646/summary.md`
- Additional CFTR three-space cohort JSON:
  `reports/full_ai_orchestrator_real_space_canary/20260418_144646/summary.json`
- Settings-enabled CFTR widening:
  `reports/full_ai_orchestrator_settings_canary/20260418_182547/summary.md`
- Settings-enabled CFTR widening JSON:
  `reports/full_ai_orchestrator_settings_canary/20260418_182547/summary.json`
- Settings-enabled MED13 widening:
  `reports/full_ai_orchestrator_settings_canary/20260418_184841/summary.md`
- Settings-enabled MED13 widening JSON:
  `reports/full_ai_orchestrator_settings_canary/20260418_184841/summary.json`
- Second settings-path cycle across all seven monitored spaces:
  `reports/full_ai_orchestrator_settings_canary/20260418_191638/summary.md`
- Second settings-path cycle JSON:
  `reports/full_ai_orchestrator_settings_canary/20260418_191638/summary.json`

The selected rollout review passed with 21 completed live runs, 0 failed runs,
0 timed-out runs, 7 source-selection interventions, 6 chase/stop
interventions, and 4 authority-exercised runs.

The follow-up rollout review passed with 30 completed live runs, 0 failed runs,
0 timed-out runs, 10 source-selection interventions, 8 chase/stop
interventions, and 5 authority-exercised runs.

The latest follow-up rollout review, including the additional CFTR cohort,
passed with 39 completed live runs, 0 failed runs, 0 timed-out runs, 13
source-selection interventions, 11 chase/stop interventions, 7
authority-exercised runs, 9 distinct spaces, and 5 passing spaces.

The settings-enabled CFTR widening passed with 2 completed live runs, 0 failed
runs, 0 timed-out runs, 2 source-selection interventions, 3 chase/stop
interventions, 2 authority-exercised runs, 5 verified proof receipts, 0 proof
verification failures, and 0 pending proof verifications.

The settings-enabled MED13 widening passed with 2 completed live runs, 0 failed
runs, 0 timed-out runs, 2 source-selection interventions, 4 chase/stop
interventions, 2 authority-exercised runs, 6 verified proof receipts, 0 proof
verification failures, and 0 pending proof verifications.

The second settings-path cycle passed across all 7 monitored spaces with 7
completed live runs, 0 failed runs, 0 timed-out runs, 7 source-selection
interventions, 14 chase/stop interventions, 7 authority-exercised runs, 21
verified proof receipts, 0 proof verification failures, and 0 pending proof
verifications.

The first default-readiness gate returned `hold`, which was the expected
conservative result before repeated settings-path evidence. The second
default-readiness gate returned `pass` after the repeated settings-path cycle
and explicit `approved_for_default_discussion` operator decision.

- Default-readiness report:
  `reports/full_ai_orchestrator_default_readiness/20260418_190658/summary.md`
- Default-readiness JSON:
  `reports/full_ai_orchestrator_default_readiness/20260418_190658/summary.json`
- Passing default-readiness report:
  `reports/full_ai_orchestrator_default_readiness/20260418_194423/summary.md`
- Passing default-readiness JSON:
  `reports/full_ai_orchestrator_default_readiness/20260418_194423/summary.json`

## Review Checklist

| Check | Status |
| --- | --- |
| No failed, timed-out, or malformed runs in selected evidence | pass |
| No invalid or fallback planner outputs counted as success | pass |
| No disabled, reserved, context-only, or grounding source violations | pass |
| Guarded proof receipts present and verified for applied actions | pass |
| Source-selection interventions observed | pass |
| Chase/stop interventions observed | pass |
| Deterministic rollback path confirmed | pass |
| Default-readiness gate passed | pass |
| Default adoption approved for `guarded_source_chase` | pass |

## Small Canary Scope

The active settings-based canary is limited to these low-risk spaces:

- `366b8d14-f704-4e42-a40e-be21b1b8869b`
  (`brca1-olaparib-guarded-canary-a`)
- `1cc6396d-e852-4aae-bb93-c32e89707bcc`
  (`brca1-olaparib-guarded-canary-b`)
- `2f6e1da1-45f1-4048-b223-b5e7a0a5d1b6`
  (`pcsk9-ordinary-guarded-canary-a`)
- `487badd9-4897-4f3e-9b3e-d481da5fafcf`
  (`cftr-ordinary-guarded-canary-b`)
- `d2147b2f-87ca-4f3b-9526-a9e41a0a9ea2`
  (`cftr-ordinary-guarded-canary-c`)
- `ebbca89d-6a29-4ea5-ace6-a7de3cc62221`
  (`med13-ordinary-guarded-canary-a`)
- `44295e6d-2f35-4a42-9de1-1a5fba6b07be`
  (`med13-ordinary-guarded-canary-b`)

The clean-hold spaces remain deterministic:

- `031c2a64-433f-485b-ab06-f4ab5c0d3066`
  (`cftr-ordinary-guarded-canary-a`)
- `d97b106f-4892-4f4d-aac2-aaa73112aec9`
  (`phase2-live-timeline-validation`)

Canary settings:

- `research_orchestration_mode = full_ai_guarded`
- `full_ai_guarded_rollout_profile = guarded_source_chase`

After the default flip, new spaces and kickoff requests use
`full_ai_guarded + guarded_source_chase` unless a request or space explicitly
selects `deterministic` as rollback. Broader authority still requires a
separate review.

## Rollback Triggers

Return an affected space to deterministic mode if any of these occur:

- any failed run
- any timeout
- any malformed guarded payload
- any invalid or fallback planner output
- any disabled, reserved, context-only, or grounding source violation
- missing or unverified guarded proof receipts
- unexpected brief, proposal, or downstream-state drift

Rollback setting:

- `research_orchestration_mode = deterministic`
- remove `full_ai_guarded_rollout_profile`

## Canary Result

The small settings-based canary passed on April 18, 2026.

Settings-path proof result:

- report: `reports/full_ai_orchestrator_settings_canary/20260418_125948/summary.md`
- verdict: `pass`
- completed runs: `3`
- failed runs: `0`
- source-selection interventions: `3`
- chase/stop interventions: `5`
- authority-exercised runs: `3`
- verified proof receipts: `8`
- proof verification failures: `0`
- pending proof verifications: `0`

Runs:

- `brca1-olaparib-guarded-canary-a`:
  `4aaa7cca-5c87-4066-9c54-f1ac48c03cc4`, completed,
  readiness `ready_verified`, profile source `space_setting`
- `brca1-olaparib-guarded-canary-b`:
  `801eaa0d-7c5d-4a83-a9a3-097da89f5c84`, completed,
  readiness `ready_verified`, profile source `space_setting`
- `pcsk9-ordinary-guarded-canary-a`:
  `80574046-fc93-4fe8-a713-5f411f745628`, completed,
  readiness `ready_verified`, profile source `space_setting`

The standard real-space canary runner also passed against the same three
spaces:

- report: `reports/full_ai_orchestrator_real_space_canary/20260418_130004/summary.md`
- requested runs: `9`
- completed runs: `9`
- failed runs: `0`
- timed-out runs: `0`
- malformed runs: `0`
- invalid outputs: `0`
- fallback outputs: `0`
- source-selection interventions: `3`
- chase/stop interventions: `2`
- authority-exercised runs: `1`
- cohort status: `multi_space_partial`

The follow-up rollout review including this small canary passed:

- report: `reports/full_ai_orchestrator_rollout_review/20260418_131238/summary.md`
- selected reports: `4`
- completed runs: `30`
- failed runs: `0`
- timed-out runs: `0`
- source-selection interventions: `10`
- chase/stop interventions: `8`
- authority-exercised runs: `5`
- distinct spaces: `6`
- rollout verdict: `pass`

An additional low-risk CFTR cohort was collected after the small canary:

- report: `reports/full_ai_orchestrator_real_space_canary/20260418_144646/summary.md`
- requested runs: `9`
- completed runs: `9`
- failed runs: `0`
- timed-out runs: `0`
- malformed runs: `0`
- invalid outputs: `0`
- fallback outputs: `0`
- source-selection interventions: `3`
- chase/stop interventions: `3`
- authority-exercised runs: `2`
- cohort status: `multi_space_partial`

The rollout review including the CFTR cohort also passed:

- report: `reports/full_ai_orchestrator_rollout_review/20260418_150738/summary.md`
- selected reports: `5`
- completed runs: `39`
- failed runs: `0`
- timed-out runs: `0`
- source-selection interventions: `13`
- chase/stop interventions: `11`
- authority-exercised runs: `7`
- distinct spaces: `9`
- passing spaces: `5`
- rollout verdict: `pass`

The two CFTR spaces that had per-space pass were then promoted into the
settings-based canary and checked through the normal research-init product
path:

- report: `reports/full_ai_orchestrator_settings_canary/20260418_182547/summary.md`
- completed runs: `2`
- failed runs: `0`
- timed-out runs: `0`
- source-selection interventions: `2`
- chase/stop interventions: `3`
- authority-exercised runs: `2`
- verified proof receipts: `5`
- proof verification failures: `0`
- pending proof verifications: `0`
- invalid outputs: `0`
- fallback outputs: `0`
- source-policy violations: `0`
- verdict: `pass`

Settings-path CFTR runs:

- `cftr-ordinary-guarded-canary-b`:
  `744c295c-5cdf-494f-b1c9-f666f6b0e019`, completed,
  readiness `ready_verified`, profile source `space_setting`
- `cftr-ordinary-guarded-canary-c`:
  `44dc1a4b-cad9-4e67-a74c-9da34dd4c9b4`, completed,
  readiness `ready_verified`, profile source `space_setting`

The two MED13 spaces that had per-space pass were then promoted into the
settings-based canary and checked through the normal research-init product
path:

- report: `reports/full_ai_orchestrator_settings_canary/20260418_184841/summary.md`
- completed runs: `2`
- failed runs: `0`
- timed-out runs: `0`
- source-selection interventions: `2`
- chase/stop interventions: `4`
- authority-exercised runs: `2`
- verified proof receipts: `6`
- proof verification failures: `0`
- pending proof verifications: `0`
- invalid outputs: `0`
- fallback outputs: `0`
- source-policy violations: `0`
- verdict: `pass`

Settings-path MED13 runs:

- `med13-ordinary-guarded-canary-a`:
  `836002cb-8a16-4170-a3ec-9bc7f70a8876`, completed,
  readiness `ready_verified`, profile source `space_setting`
- `med13-ordinary-guarded-canary-b`:
  `fe093c41-ad1a-4355-9284-40035e124b4d`, completed,
  readiness `ready_verified`, profile source `space_setting`

Decision after canary: keep the seven named spaces in
`full_ai_guarded + guarded_source_chase` and use their evidence as the
settings-path proof pack for default adoption. The default flip is approved
only for this same narrow source+chase profile.

## Default Readiness

Current default-readiness verdict: `pass`.

The latest gate is:

- `reports/full_ai_orchestrator_default_readiness/20260418_194423/summary.md`

Gate summary:

- selected settings reports: `4`
- monitored spaces: `7`
- spaces with clean evidence: `7`
- clean settings-path runs: `14`
- authority-exercised clean runs: `14`
- source-selection interventions: `14`
- chase/stop interventions: `26`
- verified proof receipts: `40`
- failed runs: `0`
- timed-out runs: `0`
- proof verification failures: `0`
- pending proof verifications: `0`
- invalid outputs: `0`
- fallback outputs: `0`

The gate passed with `approved_for_default_discussion`, and the operator
decision now approves the default flip for `full_ai_guarded` with
`guarded_source_chase`. This does not approve `guarded_low_risk`, planner-owned
graph reasoning, extraction-policy ownership, hypothesis generation ownership,
or autonomous canonical graph writes.
