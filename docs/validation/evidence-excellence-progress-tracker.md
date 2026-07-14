# Artana Evidence Excellence Progress Tracker

Created: 2026-07-02

This is the living tracker for raising Artana Evidence from "useful relation
candidate extraction" to a high-confidence, agent-driven, evidence-grounded
trusted graph system.

Next trusted-readiness PR plans:

- PR11-PR16 foundation plan:
  `docs/validation/trusted-graph-readiness-pr-plan.md`
- PR17+ recovery plan for the remaining trusted-graph blockers:
  `docs/validation/trusted-graph-readiness-recovery-plan.md`
- Finding-by-finding remediation plan for the PR-17 failure attribution output:
  `docs/validation/trusted-graph-finding-remediation-plan.md`
- Root-cause blocker plan for the latest PR19 trusted-readiness blockers:
  `docs/validation/trusted-graph-readiness-blocker-resolution-plan.md`
- Robust finding-by-finding PR21+ execution plan:
  `docs/validation/trusted-graph-readiness-robust-findings-plan.md`
- Current post-PR21 finding closure plan:
  `docs/validation/trusted-graph-readiness-post-pr21-findings-plan.md`
- Current post-PR22 remediation plan:
  `docs/validation/trusted-graph-readiness-post-pr22-remediation-plan.md`

The tracker is updated after each PR with metrics, report links, tests, and
review evidence. A phase is not done because code merged. A phase is done when
the evidence below proves the quality gate moved in the right direction.

## Operating Rules

- Agent success and deterministic fallback success are tracked separately.
- Deterministic fallback output never counts as trusted evidence quality.
- Every PR must add or tighten at least one measurable gate.
- Every PR must include focused tests for the changed behavior.
- Every PR must attach a report artifact or explicit evidence note.
- Trust improvements must fail closed. Missing verifier, unavailable agent, or
  unknown dictionary state should queue or reject, not silently promote.
- Graph persistence and dictionary governance stay in
  `services/artana_evidence_db`.
- Evidence workflow orchestration, document extraction, review, and agent
  evaluation stay in `services/artana_evidence_api`.

## North Star

A trusted relation should follow this path:

```text
agent-generated
  -> evidence-anchored
  -> subject and object linked
  -> relation type canonical or reviewed
  -> triple support verified
  -> score calibrated
  -> trust tier audited
```

Fallback extraction may remain useful for triage or degraded local operation,
but fallback output must not be counted as agent quality and must not enter a
trusted tier without the same verification gates.

## Current Baseline

Baseline date: 2026-07-01

Evidence:

- Strict agent report:
  `reports/relation_feasibility/2026-07-02-pr0-agent-strict-v2-fixed/relation_feasibility_report.md`
- Merge-visible report snapshot:
  `docs/validation/reports/2026-07-02-pr0-agent-strict-v2-summary.md`
- Deterministic comparison report:
  `reports/relation_feasibility/2026-07-01-deterministic-comparison/relation_feasibility_report.md`
- Audit script:
  `scripts/run_relation_feasibility_audit.py`
- Audit package:
  `scripts/validation/relation_feasibility/`
- Implementation plan:
  `docs/superpowers/plans/2026-07-02-evidence-excellence-implementation.md`

| Metric | Strict agent baseline | Deterministic comparison | Notes |
|---|---:|---:|---|
| Cases | 30 | 6 | PR-0 adds a 30-case synthetic seed fixture; still not production representative. |
| Gold relations | 25 | 4 | PR-0 v2 labels include CURIE/support metadata. |
| Agent-completed cases | 0 | 0 | Strict agent blocked locally by missing `OPENAI_API_KEY`. |
| Fallback or unavailable cases | 30 | 0 | Strict agent mode correctly flags fallback/unavailable as invalid. |
| Invalid strict-agent cases | 30 | 0 | Current strict verdict is RED. |
| Candidate precision | 0.7778 | 0.6667 | Strict-agent local run is fallback-only and invalid for product quality. |
| Candidate recall | 0.2800 | 0.5000 | Strict-agent local run is fallback-only and invalid for product quality. |
| Generic relation rate | 0.1111 | 0.3333 | Still above the trusted-graph target of <= 0.05. |
| Completed-agent valuable rate | 0.0000 | n/a | Completed-agent quality stays zero while all agent cases are unavailable/fallback. |
| All-candidate valuable rate | 0.6667 | 0.6667 | Comparison-only; not trusted evidence. |
| Grounded sentence rate | 1.0000 | 1.0000 | Current check is substring-only, not args-present or entailment. |
| Verdict | RED | YELLOW | Deterministic YELLOW is comparison only. |

## Excellence Scorecard

| Gate | Baseline | Target | Current | Evidence | Status |
|---|---:|---:|---:|---|---|
| Agent completion rate | 0/6 | 100% | 30/30 | 2026-07-03 PR8 live-agent remediation report | Live path completes |
| Fallback trusted count | Not gated | 0 | 0 across PR-1 route, review-item, research-init, variant, and signal-enrichment tests | PR-1 fallback trust gate and adversarial PASS | Ready for review |
| Negative-control leakage | 0 in starter fixture | 0 | 5/5 negative-control empty completions; 0 leakage cases; 0 fallback cases | 2026-07-03 PR8 live-agent remediation report | Passing |
| Evidence anchor rate | substring-only 1.0000 | >= 0.98 | 1.0000 live-agent grounded sentence rate | 2026-07-03 PR8 live-agent remediation report | Passing |
| Both-args-present rate | Not measured | >= 0.95 | 0.9655 live-agent rate | 2026-07-03 PR8 live-agent remediation report | Passing |
| Entailment checked rate | 0% | 100% | 0.9630 live-agent rate | 2026-07-03 PR8 live-agent remediation report | Needs unchecked-case cleanup |
| Relation over-generalization | 0.3333 generic rate | <= 0.05 | 0.1379 live-agent generic rate | 2026-07-03 PR8 live-agent remediation report | Needs cleanup |
| Kept raw relation types | Possible on resolver failure | 0 | 0/30 candidates and 0/30 inventory surfaces | 2026-07-03 PR8 live-agent remediation report | Passing |
| CURIE-linked gold entities | 0% in extraction path | >= 0.95 | 0.0000 verified CURIE match rate; 0.5690 candidate CURIE present rate; 13 wrong model CURIE hints | 2026-07-03 PR8 live-agent remediation report | Strict gate RED |
| Auto-created junk nodes | Possible unresolved fallthrough | 0 | Entity-candidate creation requires linked CURIE payloads in PR-6; graph junk-node count not separately audited | PR-6 tests | Ready for review; add graph-count audit later |
| Score calibration ECE | Uncalibrated | < 0.05 | Trusted candidate support-calibration ECE 0.0000 worst/mean; all-candidate support-calibration ECE 0.0732 worst, 0.0671 mean; production review-ranking ECE is now measured from decided workspace review outcomes | PR-37 v4 calibration readiness gate; PR-38 workspace review-ranking calibration | Trusted lane gated; production thresholding needs expert/shadow review set |
| Trusted-tier precision | Not gold-gated | 1.00 | 1.00 on focused hard-floor adversarial suite; live gold run completes but remains RED because verified CURIE match is 0.0000 | PR-8 plus live-agent remediation report | Ready for review |
| Reproducible extraction | text clipped, temp unset | deterministic and cache-safe | Full-text chunking plus prompt-version/model-aware replay keys | PR-9 blind-spot and key-collision tests | Ready for review |
| CI quality gate | Not present | blocking | `relation-feasibility-quality-gate` runs in `service-checks` and CI repo-control jobs | PR-10 planner/control tests and final `make service-checks` | Ready for review |

## Phase And PR Tracker

Status values:

- Not started
- In progress
- Evidence pending
- Ready for review
- Merged
- Blocked

| Phase | PR | Branch | Status | Goal | Primary gate | Evidence |
|---|---|---|---|---|---|---|
| 0 | PR-0 | `alvaro/evidence-pr0-quality-harness` | Ready for review | Expand the starter audit into an attachment-style gold harness. | Strict agent reports are valid and reproducible. | 30-case v2 fixture, completed-agent metrics, adversarial report section, merge-visible evidence snapshot, and adversarial PASS exist. |
| 0 | PR-1 | `alvaro/evidence-pr1-no-fallback-trust` | Ready for review | Ensure fallback output cannot be confused with agent success or trusted evidence. | Fallback trusted count is 0. | Focused RED/GREEN tests, Evidence API service gate, strict audit r6, merge-visible evidence snapshot, and adversarial PASS; implemented as a stacked slice in the current worktree until PR-0 is split/committed. |
| 1 | PR-2 | `alvaro/evidence-pr2-grounding-gate` | Ready for review | Add sentence anchoring and both-arguments-present checks. | Args-present rate >= 0.95 on gold. | Sentence anchor and args-present tests, graph AI hard-floor tests for claims and canonical relations, API service gate, graph service gate, aggregate service-checks, strict audit snapshot, adversarial BLOCK fixed, and re-review PASS. |
| 1 | PR-3 | `alvaro/evidence-pr3-entailment-verifier` | Ready for review | Add fail-closed support verification for each triple. | Entailment checked rate is 100%. | Support verifier tests, document extraction trust-floor tests, graph support hard-floor tests, promotion metadata-override tests, relation feasibility audit tests, touched-file lint, graph/API/aggregate service gates, strict audit snapshot, adversarial BLOCK fixes, and final re-review PASS. |
| 2 | PR-4 | `alvaro/evidence-pr4-relation-type-hardening` | Ready for review | Enum-constrain extraction and fail closed on resolver failures. | Kept raw relation types are 0. | Focused RED/GREEN tests, relation feasibility raw-unknown and inventory metrics, API/graph/aggregate service gates, strict audit snapshot, and external adversarial PASS. |
| 2 | PR-5 | `alvaro/evidence-pr5-specificity-pruning` | Ready for review | Suppress redundant generic siblings and probe generic relations. | Over-generalization <= 0.05. | Specificity-pruning tests, weak generic-correlation suppression, generic-rate audit metric 0.0000, API service gate, aggregate service-checks, strict-agent fallback-as-failure snapshot, and adversarial PASS. |
| 3 | PR-6 | `alvaro/evidence-pr6-curie-entity-linking` | Implemented locally; strict gate RED | Link entities to CURIEs or abstain and queue. | CURIE-linked gold entities >= 0.95. | LLM CURIE schema, normalization/abstention helper, verified-linker-only graph identifiers, model-CURIE hints kept metadata-only, CURIE endpoint audit metric, focused RED/GREEN tests, and live-agent remediation report. Live verified CURIE match rate remains 0.0000 with 13 wrong model CURIE hints. |
| 4 | PR-7 | `alvaro/evidence-pr7-evidence-aware-scoring` | Ready for review | Make ranking evidence-aware and calibrated. | Specific grounded claims outrank generic claims. | Evidence-aware ranking components, focused RED/GREEN ranking tests, score split 0.9220 vs 0.7220 for identical review labels, and API service gate. |
| 5 | PR-8 | `alvaro/evidence-pr8-trust-ladder-hard-floors` | Ready for review | Add trust ladder and hard floors config cannot weaken. | Trusted-tier precision is 1.00. | Trust ladder metadata, verified-linker-only CURIE trust floors, graph-side trusted-claim rejection, verifier-owned promotion metadata protection, focused RED/GREEN adversarial tests, service gates, and live-agent remediation report. Live run completes; trusted graph readiness remains blocked by verified CURIE recovery and precision/valuable-rate warnings. |
| 6 | PR-9 | `alvaro/evidence-pr9-reproducible-fulltext-extraction` | Ready for review | Pin model behavior, fix cache keys, and chunk full documents. | No 4000-character blind spot. | Full-text sentence-aware chunking, prompt-version/model-aware replay keys, chunk telemetry in diagnostics, RED/GREEN blind-spot and key-collision tests, architecture-size split, touched-file lint, focused extraction suite, and API service gate. |
| 6 | PR-10 | `alvaro/evidence-pr10-ci-quality-gate` | Ready for review | Make quality regression visible in CI. | Regression fails CI. | Relation-feasibility quality gate in `service-checks`, CI planner routing for audit-methodology changes, repo-control workflows run audit tests, RED/GREEN planner/control tests, direct quality-gate pass, repo-control bundle pass, and docs path hygiene cleanup. |
| 7 | PR-17 | `alvaro/evidence-pr17-readiness-failure-attribution` | Local checkpoint committed | Explain every PR16 readiness blocker before changing extraction or promotion policy. | Repeated misses, false positives, CURIE gaps, proposal capture, and model labels are reportable. | Failure-analysis module, CLI, focused RED/GREEN tests, PR16 three-run baseline analysis, service-checks pass, and merge-visible PR17 evidence snapshot. |
| 8 | PR-19 | `alvaro/evidence-pr19-high-value-relation-recovery` | Implemented locally; strict gate RED | Make high-value drug-resistance relations canonical instead of proposal noise. | High-value recall >= 0.8500 with raw unknown relation surfaces 0. | `CONFERS_RESISTANCE_TO` API taxonomy, graph dictionary seed, graph constraints, safe typo proposal repair, verifier cues, benchmark shape update, focused RED/GREEN tests, relation-feasibility gate, and strict live run. Live run reaches precision 0.9048 and high-value recall 0.9500, but trusted graph readiness remains blocked by verified CURIE endpoint rate 0.8108. |
| 9 | PR-20 | `alvaro/evidence-pr20-qualifier-precision-adjudication` | Implemented locally; adversarial review fixes applied; strict gate RED | Preserve biomedical qualifiers and remove context false positives from trusted evidence. | Completed-agent precision >= 0.8000 and high-value recall >= 0.8500 without broad subject substitutions. | Dropped-modifier tests, expanded modifier adversarial tests, clause-local and comma-and modifier regressions, context-shadowing and review-only trust tests, low-value review accounting, relation-feasibility gate, strict live run4 with completed-agent precision 0.9500 and high-value recall 0.9500. Trusted high-value recall is now stricter at 0.5500; trusted graph readiness remains blocked by verified CURIE endpoint rate 0.8108. |
| 10 | PR-21 | `alvaro/evidence-pr21-verified-grounding-closure` | Implemented locally; adversarial blockers fixed; strict gate RED | Improve verified grounding and review-only abstention without trusting raw model hints. | Trusted high-value recall >= 0.8500 and wrong verified CURIE links remain 0. | Grounding dictionary split, verified process labels, review-only broad/composite labels, verified-linker spoof regression, safe relation-alias scoring, missed-gold CURIE attribution, focused tests, relation-feasibility gate, strict live run3 with precision 1.0000, high-value recall 1.0000, trusted high-value recall 0.8500, verified endpoint rate 0.8810, false positives 0, fallback 0. Overall readiness remains RED. |
| 11 | PR-22 | `alvaro/evidence-pr22-low-value-review-lane` | Implemented locally; strict single-run GREEN; repeatability pending | Split trusted-eligible endpoint recovery from low-value review evidence. | Trusted-eligible CURIE-linked endpoint rate >= 0.9500 and weak-claim trusted leakage remains 0. | Review-only candidate policy, review status propagation, `review_only_candidate` trust floor, promotion metadata protection, trusted/review endpoint metric split, single-run verdict contract fix, scoring/readiness helper refactor, focused tests, direct touched-file ruff, relation-feasibility gate, strict live run4 with verdict GREEN, precision 1.0000, high-value recall 1.0000, trusted endpoint rate 1.0000, weak leakage 0, fallback 0. Low-value review recall remains 0.4000 and final readiness still needs repeated runs. |
| 12 | PR-23 | `alvaro/evidence-pr23-low-value-review-recall` | Draft PR #106 open; GitHub CI clean | Recover weak-but-useful low-value review evidence through the live agent path without deterministic fallback. | Low-value review recall >= 0.8000 and weak-claim trusted leakage remains 0. | Weak-review agent pass, weak-pass prompt/schema versioning, code-forced review-only metadata, policy-backed weak-pass keep filter, candidate-argument scoped weak-cue policy, raw weak-pass relation-type/proposal drop, review-only pruning preservation, fallback-gated review metrics, sensitization prompt repair, focused RED/GREEN tests, relation-feasibility gate, strict live run7 with verdict GREEN, precision 1.0000, low-value review recall 1.0000, high-value recall 1.0000, trusted endpoint rate 1.0000, false positives 0, missed gold 0, weak leakage 0, fallback 0, invalid agent 0, `make service-checks` with coverage 87.03%, and PR #106 GitHub checks passing. Repeatability remains pending. |
| 13 | PR-24 | `alvaro/evidence-pr24-grounding-decision-table` | Implemented locally; final gates pending | Give every remaining endpoint gap a safe verified or review-only grounding decision without trusting model hints. | All remaining CURIE gaps have explicit review-only decision metadata and wrong verified CURIE links remain 0. | Review-only grounding decision metadata, eight-label endpoint policy table, review-only-before-verified collision handling, link metadata for `grounding_reason_code`, failure-analysis `review_only_endpoint` rows, guarded primary LLM schema for raw relation-type cleanup, focused RED/GREEN tests, relation-feasibility gate, and strict live run3 with verdict GREEN, precision 0.9615, recall 1.0000, trusted endpoint rate 1.0000, verified CURIE match rate 1.0000, one review-only false positive, missed gold 0, fallback 0, invalid agent 0, wrong verified CURIE links 0. Repeatability and generic relation rate 0.1154 remain follow-up work. |
| 14 | PR-25 | `alvaro/evidence-pr25-repeatability-model-ab` | In progress; harness implemented, live A/B pending | Prove repeatability and evaluate whether a stronger model improves trusted readiness without safety regressions. | Candidate model can be recommended only from worst-run readiness, zero safety failures, and no trusted-endpoint regression. | Artifact-only model-comparison module, repeated-run wrapper with `ARTANA_STRONGER_MODEL_CANDIDATE` fail-closed guard, readiness-backed adoption decision, failure-analysis trust-lane model metrics, focused RED/GREEN tests, and updated `relation-feasibility-quality-gate`. Live six-run A/B remains pending because `ARTANA_STRONGER_MODEL_CANDIDATE` is not configured in `.env.postgres`. |
| 15 | PR-26 | `alvaro/evidence-pr26-graph-promotion-fail-closed` | Implemented locally; final gates pass | Make Graph DB independently reject unsafe trusted AI evidence even if a caller labels it trusted. | Graph validation rejects fallback, incomplete-agent, review-only, weak-reason, model-only endpoint, unlinked endpoint, non-ENTAILS, malformed floor metadata, and failed trust-floor promotion attempts. | Graph-owned review-lane floor, verified endpoint marker floor, malformed metadata fail-closed checks, `/claims` trusted-floor rejection, claim and direct relation regression tests, RED unit/integration/adversarial proof, focused 71-test graph validation pass, changed-file Ruff pass, post-adversarial `make graph-service-checks` pass, and post-adversarial `make service-checks` pass with coverage 87.03%. Summary: `docs/validation/reports/2026-07-06-pr26-graph-promotion-fail-closed-summary.md`. |
| 16 | PR-27 | `alvaro/evidence-pr27-benchmark-v3-doc-proof` | Implemented locally; final gates pass | Expand benchmark breadth and make proof summaries generated from JSON artifacts. | v3 fixture validation passes and generated summaries expose reproducible metrics, blockers, warning reasons, artifact hashes, and remaining failures from tracked JSON. | 40-case v3 fixture, fixture validator, generated summary CLI, tracked PR27 proof JSON/Markdown, quality-gate tests, v2 GREEN run, v3 RED run2, v3 failure attribution, adversarial re-review PASS, pre-commit pass, and `make service-checks` pass with coverage 87.03%. V3 proves current agent path is safe on hard negatives but not trusted-graph ready: precision 0.7333, trusted high-value recall 0.2000, trusted endpoint rate 0.3000, generic rate 0.3000, model-only wrong CURIE hints 9, fallback 0, invalid agent 0, negative leakage 0, weak trusted leakage 0, wrong verified links 0. Summary: `docs/validation/reports/2026-07-06-pr27-benchmark-v3-doc-proof-summary.md`. |
| 17 | PR-28 | `alvaro/evidence-pr28-v3-specificity-recall` | Implemented locally; post-adversarial strict gate RED | Improve v3 live-agent specificity and high-value recall without crediting deterministic fallback. | Precision/noise must improve while fallback, invalid-agent, negative leakage, weak trusted leakage, and wrong verified links stay at 0. | Specific biomedical label preservation, prompt v6 subtype reminder, tumor-agnostic fusion object repair for `harboring` and `with` surfaces, variant-class dropped-subject rejection, treatment/context-tail rejection, shared argument aliases, `predispose` support cue coverage, sibling-required context filtering, review-only retention for single suspicious context candidates, focused RED/GREEN tests, relation-feasibility quality gate, five pre-review strict v3 live-agent runs, and one post-review strict v3 live-agent run. Best precision/noise run was run4: precision 0.9259, recall 0.8333, high-value recall 0.8500, false positives 2, fallback 0, invalid agent 0. Best recall run was run2: recall 0.8667 and high-value recall 0.9000, but precision 0.7429 with 9 false positives. Final post-review run6 stayed RED: precision 0.8519, recall 0.7667, high-value recall 0.7500, generic rate 0.2593, valuable rate 0.5185, trusted endpoint rate 0.3250, false positives 4, fallback 0, invalid agent 0. Remaining blockers: trusted CURIE recovery, repeatability, generic/valuable thresholds, and repeatable omissions including BRCA1, EGFR, MET, FBN1, NTRK, plus post-review misses for MECP2/PAH/APC. Summary: `docs/validation/reports/2026-07-06-pr28-v3-specificity-recall-summary.md`. |
| 18 | PR-29 | `alvaro/evidence-pr29-v3-curie-recovery` | Implemented locally; post-adversarial strict gate YELLOW | Recover v3 verified CURIE endpoints and high-value rare-disease associations through the live-agent path without accepting broad or fake exact IDs. | Trusted-eligible CURIE-linked endpoint rate >= 0.9500 with fallback, invalid-agent, weak trusted leakage, negative leakage, and wrong verified CURIE links all at 0. | Corrected false/broad v3 CURIE curation, demoted gene-state/composite/molecular-subtype labels to review-only, propagated review-only endpoint grounding into candidate trust metadata, added NTRK live-surface relation aliasing, added fixture-policy validation so trusted gold cannot use review-only endpoints or review-status typos, added explicit high-value review-only metrics, prompt v7 rare-disease association examples, focused RED/GREEN tests, relation-feasibility quality gate, and strict live run7. Run7: YELLOW, precision 0.9032, recall 0.9333, high-value recall 1.0000, high-value review-only recall 1.0000, trusted high-value recall 0.3500, trusted endpoint rate 1.0000, verified CURIE match rate 0.7250, model wrong hints 2, wrong verified links 0, fallback 0, invalid agent 0, negative leakage 0, weak trusted leakage 0. Remaining warnings: trusted high-value recall, valuable candidate rate 0.5161, and generic relation rate 0.2903. Summary: `docs/validation/reports/2026-07-06-pr29-v3-curie-recovery-summary.md`. |
| 19 | PR-30 | `alvaro/evidence-pr30-trusted-lane-readiness` | Draft PR #113 open; three-run readiness not_ready | Separate trusted graph readiness from review-only/all-candidate triage so the gate measures auto-promotion safety without hiding review burden. | Readiness thresholds use trusted candidate precision, trusted-eligible high-value recall, trusted candidate valuable rate, trusted candidate generic rate, trusted-eligible CURIE endpoint rate, and review-only gold trusted leakage. | Added trusted-eligible high-value and trusted-candidate metrics, centralized trusted graph candidate eligibility so context relations cannot inflate readiness, made review-only gold trusted leakage a hard failure, rewired single-run verdict warnings and repeatability thresholds to the trusted lane, split Markdown reporting by trusted/review/all-candidate lanes, kept all-candidate metrics visible for triage, updated model comparison/failure attribution/adversarial wording, added RED/GREEN tests for review-only high-value/generic/context/leakage candidates, ran focused tests, failure-analysis tests, touched-file Ruff, `make relation-feasibility-quality-gate`, `make service-checks`, and strict v3 live runs5-7. Three-run readiness remains not_ready with blockers: one RED source audit, worst trusted candidate precision 0.7778, and worst trusted endpoint rate 0.8571. Trusted candidate generic rate is 0.0000 and hard failures are all 0, including review-only gold trusted leakage 0. Remaining issues: run5 missed `Larotrectinib TREATS NTRK fusion solid tumors`; runs6-7 had trusted precision misses including recurring `Vemurafenib INHIBITS MAPK signaling`. Summary: `docs/validation/reports/2026-07-06-pr30-trusted-lane-readiness-summary.md`. |
| 20 | PR-31 | `alvaro/evidence-pr31-context-precision-guards` | Draft PR #114 open; three-run readiness READY; GitHub checks clean | Demote pathway, process, and cell-context candidates from trusted auto-promotion when they are useful review context but not curated trusted graph evidence. | Three strict v3 live-agent runs report trusted graph readiness ready with worst trusted precision, trusted high-value recall, trusted valuable rate, trusted endpoint recovery, and entailment checked rate all at 1.0000. | Added RED/GREEN quality-filter tests for Vemurafenib/MAPK pathway shadowing, KRAS/proliferation process shadowing, and JAK-STAT/macrophage cell-context activation; added fake-LLM extraction regression proving review-only metadata survives the agent path; ran focused tests, touched-file Ruff, `make relation-feasibility-quality-gate`, strict v3 live runs1-3, readiness aggregate READY, and failure analysis. Hard failures are all 0: fallback, invalid agent, negative leakage, raw unknown relation/surface, wrong verified CURIE links, weak trusted leakage, and review-only gold trusted leakage. Remaining work is review-lane usefulness, not trusted auto-promotion: weak EGFR/MET review misses and all-candidate review burden remain. Summary: `docs/validation/reports/2026-07-06-pr31-context-precision-guards-summary.md`. |
| 21 | PR-32 | `alvaro/evidence-pr32-weak-review-recovery` | Implemented locally; post-adversarial three-run readiness READY; final gates pass | Recover weak EGFR trend-response and MET correlated-resistance evidence as review-only candidates while preserving trusted-lane safety. | Low-value review recall is 1.0000 across three strict v3 live-agent runs, weak trusted leakage remains 0, and trusted readiness remains READY. | Added weak-review prompt examples, weak-pass prompt reinforcement, `trended with` detection, trend-response relation repair, correlated-resistance object repair, post-repair duplicate merging, and schema recovery for canonical relations with spurious proposal fields. Adversarial review then tightened schema recovery to reject unknown/conflicting proposals, clear stale object CURIE metadata after object repair, and scope repair cues to the candidate claim; re-review then closed bare-`and` claim-boundary leakage. Focused tests pass (`55 passed`), touched-file Ruff passes, `make relation-feasibility-quality-gate` passes, `make service-checks` passes with coverage 87.03%, strict live runs12-14 are GREEN with low-value review recall 1.0000, fallback 0, invalid agent 0, weak trusted leakage 0, and readiness aggregate READY. Summary: `docs/validation/reports/2026-07-06-pr32-weak-review-recovery-summary.md`. |
| 22 | PR-33 | `alvaro/evidence-pr33-review-burden-pruning` | Implemented locally; final gates pass; three-run readiness READY | Remove repeated review-burden false positives and recover rare zero-candidate/schema-invalid agent responses without deterministic fallback. | Trusted readiness remains READY, hard safety failures stay 0, and missed gold and repeated false positives are 0 across three post-adversarial strict v3 live-agent runs. | Added companion phenotype, pathway/process, downstream context, cell-context, and binding-site sibling pruning; added agent-only zero-candidate and schema-repair retries with retry-specific prompts and distinct replay keys; adversarial review and service-gate failures fixed invalid-sibling shadowing, raw-but-unusable retry suppression, schema-retry ordering, weak-pass candidate loss, partial zero-retry cue coverage, unknown-only candidate retry suppression, and over-broad pruning; focused tests pass (`80 passed`), quality-filter suite passes (`47 passed`), touched-file Ruff passes, `make relation-feasibility-quality-gate` passes, `make service-checks` passes with coverage `87.03%`, and strict post-adversarial3 live runs1-3 aggregate to READY with worst completed-agent precision 1.0000, worst recall 1.0000, worst high-value recall 1.0000, trusted precision 1.0000, trusted valuable rate 1.0000, trusted endpoint rate 1.0000, missed gold 0, false positives 0, fallback 0, invalid agent 0, negative leakage 0, weak trusted leakage 0, and wrong verified CURIE links 0. Summary: `docs/validation/reports/2026-07-06-pr33-review-burden-pruning-summary.md`. |
| 23 | PR-34 | `alvaro/evidence-pr34-live-model-ab-proof` | Implemented locally; live A/B proof complete; final gates pass | Close the stronger-model question with a fail-closed live model comparison on the v3 benchmark. | Candidate model adoption requires three completed runs, zero hard safety failures, and no trusted endpoint regression. | Added fixture pinning to `scripts/run_relation_model_comparison.py`, made failed audit subprocesses produce a `KEEP_CURRENT` report with `audit_failures`, and added Markdown audit-failure rendering. Current `openai:gpt-5.4-mini` completed 3/3 strict v3 live runs with trusted readiness READY and hard failures 0; candidate `openai:gpt-5` completed only 1/3 runs and failed run2 preflight with a LiteLLM timeout, so the comparison decision is KEEP_CURRENT. Focused model-comparison tests pass (`13 passed`), `make relation-feasibility-quality-gate` passes, `make service-checks` passes with coverage `87.03%`, and adversarial review found no blockers after symmetric failed-current-run coverage and doc wording cleanup. Summary: `docs/validation/reports/2026-07-06-pr34-live-model-ab-proof-summary.md`. |
| 24 | PR-35 | `alvaro/evidence-pr35-benchmark-v4-100-case-proof` | Implemented locally; final local gates pass; adversarial re-review PASS | Make the Definition-of-Green benchmark scale requirement executable with a 100-case v4 fixture. | CI fails if the trusted-readiness benchmark fixture is below 100 cases, lacks balanced high-value/true-low-value/negative/long-document/near-miss coverage, pads scale with duplicate relation signatures, or adds new broad v4 pathway/gene rows as trusted gold. | Added `biomedical_relation_goldset_v4.json` by preserving the 40-case v3 seed and adding 60 labeled synthetic cases: 50 strong-specific, 25 weak review-only, and 25 negative-control cases overall. Added v4 validation coverage requiring at least 100 cases, 50 high-value specific cases, 25 true low-value review cases, 25 negative controls, at least five long-document cases, at least five adversarial negated near-misses, at least 74 unique gold relation signatures, and at most one repeated signature for the inherited v3 IL6 strong/weak contrast. RED test failed on the missing v4 fixture; adversarial review then found the low-value count mixed high-value review-only rows and that some v4 rows duplicated v3 or used broad trusted endpoints, so PR35 added `true_low_value_review_case_count`, signature-diversity counters, and a v4 trusted-context guard. GREEN focused fixture validation passes (`7 passed`) with validator issue count 0, touched-file Ruff passes, `make relation-feasibility-quality-gate` passes, `make service-checks` passes with coverage `87.03%`, and final adversarial re-review reports PASS. Summary: `docs/validation/reports/2026-07-06-pr35-benchmark-v4-100-case-proof-summary.md`. |
| 25 | PR-36 | `alvaro/evidence-pr36-v4-live-readiness` | Implemented locally; final gates pass; post-adversarial three-run v4 readiness READY | Run strict live-agent readiness against the 100-case v4 fixture and close trusted-lane blockers without relying on deterministic fallback. | Three strict v4 live-agent runs pass the repeated-run readiness gate with trusted precision, trusted valuable rate, trusted generic rate, trusted-eligible high-value recall, and trusted endpoint recovery all at target while hard failures stay 0. | Added a trusted-promotion safety policy for strong-but-unsafe relation shapes, wired it into relation quality filtering, fixed hyphenated modifier-loss pruning, aligned v3/v4 gold rows with promotion policy, and added fixture validation so trusted gold cannot violate the same safety policy. Adversarial review then exposed `CAUSES`/gene-state association leaks, `growth` over-demotion, reason-code loss, a live `JAK2 activity` endpoint repair gap, and a `growth factor-independent proliferation` phrase gap; PR36 added RED/GREEN regressions and fixes for all. Strict v4 postreview2 runs1-3 aggregate to READY: worst trusted precision 1.0000, trusted valuable rate 1.0000, trusted generic rate 0.0000, trusted-eligible high-value recall 1.0000, trusted-eligible endpoint rate 1.0000, fallback 0, invalid agent 0, negative leakage 0, review-only trusted leakage 0, weak trusted leakage 0, and wrong verified CURIE links 0. Focused tests pass, touched-file Ruff passes, `make relation-feasibility-quality-gate` passes, final adversarial re-review is PASS, and `make service-checks` passes with coverage `87.03%`. Summary: `docs/validation/reports/2026-07-06-pr36-v4-live-readiness-summary.md`. |
| 26 | PR-37 | `alvaro/evidence-pr37-calibration-gate` | Implemented locally; post-adversarial three-run v4 readiness READY with calibration gate | Make audit support calibration measurable and blocking for trusted graph readiness. | Trusted candidate score ECE must be <= 0.0500 and required in every readiness source report. | Added support-calibration metrics, Markdown/JSON report fields, CLI output, readiness-gate thresholding, calibration sample counts, model-comparison calibration deltas, and direct missing/invalid calibration tests. RED tests proved the audit summary lacked calibration and the readiness gate ignored high trusted ECE. Adversarial review then found the first metric was self-fulfilling because it used `is_valuable`; PR37 fixed the metric to score only pre-gold verification signals against gold support and reran strict v4 live postreview runs1-3. The corrected aggregate is READY with trusted candidate score ECE 0.0000 worst/mean, all-candidate score ECE 0.0732 worst and 0.0671 mean, trusted precision 1.0000, trusted valuable rate 1.0000, trusted generic rate 0.0000, trusted endpoint rate 1.0000, and all hard failures 0. Production review-ranking calibration remains separate follow-up. Summary: `docs/validation/reports/2026-07-07-pr37-calibration-gate-summary.md`. |
| 27 | PR-38 | `alvaro/evidence-pr38-review-ranking-calibration` | Implemented locally; focused tests pass; adversarial fixes applied | Make production review-ranking calibration measurable from real human review outcomes. | Evidence-selection workspace snapshots expose review-ranking sample count, mean score, observed positive rate, and ECE from decided proposals and review items. | Added review-ranking calibration observations and summaries to `services/artana_evidence_api/ranking.py`, wired evidence-selection workspace snapshots to derive positive outcomes from promoted proposals/resolved review items and negative outcomes from rejected proposals/dismissed review items, and ignored pending items. RED tests proved the calibration API was missing; adversarial review then found calibration used capped display lists and lacked resolved-positive coverage, so PR38 now queries decided outcomes separately and tests a promoted proposal outside the display cap. GREEN focused tests pass (`8 passed`) and touched-file Ruff passes. Expert/shadow-mode thresholding remains follow-up. Summary: `docs/validation/reports/2026-07-07-pr38-review-ranking-calibration-summary.md`. |
| 28 | PR-39 | `alvaro/evidence-pr39-review-ranking-threshold-gate` | Implemented locally; adversarial blockers fixed; final gates pass | Make expert/shadow-mode review-ranking thresholding executable and fail-closed. | Calibration threshold gate rejects undersized, one-sided, source-incomplete, duplicate, non-discriminating, schema-invalid, or high-ECE review-ranking studies. | Added typed expert/shadow review-ranking decisions, strict study schema validation, threshold configuration, gate reports, a JSON/Markdown runner, and a committed seed fixture. RED tests proved the gate module and runner were missing; adversarial review then found fail-open CLI behavior, loose production ECE defaults, ECE-only constant-score false confidence, and schema drift acceptance. PR39 now exits nonzero on failed gates, defaults production ECE to 0.050, requires ROC AUC >= 0.700 and mean score separation >= 0.100, and rejects unknown study/decision fields. GREEN focused tests pass (`11 passed`), touched-file Ruff passes, API type-check passes, API service checks pass, and `make service-checks` passes with coverage `87.03%`. The seed fixture passes only with explicit relaxed seed ECE 0.150 and remains mechanics-only evidence. Production readiness still requires real expert/shadow labels at larger scale. Summary: `docs/validation/reports/2026-07-07-pr39-review-ranking-threshold-gate-summary.md`. |
| 29 | PR-40 | `alvaro/evidence-pr40-review-ranking-study-design-gate` | Implemented locally; post-adversarial gates pass | Ensure production review-ranking calibration studies prove enough expert/shadow study coverage before threshold claims. | Calibration gate rejects undercovered studies with too few research goals, too few evidence shapes, missing reviewer IDs, missing or blank adjudication notes, and cosmetic label variants that fake distinct coverage. | Added `evidence_shape` to calibration decisions, added gate-required study-level `adjudication_note` while keeping v1 files parseable, added normalized study-design metrics to gate reports, and made the core helper plus runner default to three distinct goals, three distinct evidence shapes, reviewer IDs on every decision, and an adjudication note. RED tests proved the helper bypass, reviewer-ID gap, blank-note gap, raw-label counting gap, seed-as-production gap, and missing-adjudication schema drift; GREEN focused tests pass (`20 passed`). The seed fixture is now an honest single-goal MED13 mechanics fixture: production-default seed checks fail with 2 study-design blockers, while an explicitly relaxed mechanics smoke check passes only to prove report rendering and threshold math. Touched-file Ruff passes, API type-check passes, API service checks pass, and `make service-checks` passes with coverage `87.03%`. Summary: `docs/validation/reports/2026-07-07-pr40-review-ranking-study-design-gate-summary.md`. |
| 30 | PR-41 | `alvaro/evidence-pr41-expert-study-gate` | Implemented locally; final gates pass; adversarial re-review PASS | Make a complete expert/shadow study bundle executable before it can support production-readiness claims. | Study gate fails closed unless the bundle declares real shadow-review evidence, every selection review is labeled and measurable, selection-review precision/recall, reviewer coverage, goal coverage, explanation quality, zero overclaiming, and review-ranking calibration all pass together. | Added `reviewer_id` preservation to selection reviews, strict nested selection-review schemas, `study_evidence_kind`, strict `evidence_selection_expert_study.v1` input, study-level thresholds/reporting, per-review JSON audit evidence, `scripts/run_evidence_selection_expert_study_gate.py`, and documented the bundle shape. RED tests proved the study gate and CLI were missing, JSON review inputs did not parse normal UUID/list fields, synthetic fixtures could pass, partially unlabeled reviews could pass, unmeasurable precision/recall and missing explanation scores could be averaged away, and nested selection extras were silently dropped. GREEN focused tests pass (`35 passed` across selection validation, review-ranking calibration, review-ranking runner, and expert-study runner). Touched-file Ruff passes, API type-check passes, API service checks pass, `make service-checks` passes with coverage `87.03%`, and final adversarial re-review reports PASS. Summary: `docs/validation/reports/2026-07-07-pr41-expert-study-gate-summary.md`. |
| 31 | PR-42 | `alvaro/evidence-pr42-expert-study-provenance-gate` | Implemented locally; final gates pass; adversarial re-review PASS | Make real-shadow expert-study provenance auditable instead of only declared. | Study gate fails closed unless the bundle includes a source manifest with hashed artifacts, exact selection-review run coverage, exact review-ranking decision-key coverage, required selection/review-ranking export artifact kinds, and reviewer-roster coverage. | Added typed source artifacts, strict source manifest validation, provenance summary output, source-manifest blockers, Markdown provenance reporting, and a `--min-source-artifact-count` runner threshold. RED tests proved `source_manifest` was rejected as schema drift, missing manifests could still pass, incomplete manifests were not blocked, invalid source hashes were not rejected, and Markdown omitted provenance evidence. Adversarial review then found duplicate run IDs could collapse through set comparison, artifact coverage was count-only, and whitespace-only manifest identity could pass; PR42 added regressions and fixes for all. The first service gate then found `evidence_selection_validation.py` over the architecture size budget, so provenance moved into `artana_evidence_api.evidence_selection.provenance`, reducing the validation module to 1016 lines while keeping architecture structure at `services/artana_evidence_api=237`. GREEN focused tests pass (`42 passed` across selection validation, review-ranking calibration, review-ranking runner, and expert-study runner). Touched-file Ruff passes, API type-check passes, API service checks pass, `make service-checks` passes with coverage `87.03%`, and adversarial re-review reports PASS. Summary: `docs/validation/reports/2026-07-07-pr42-expert-study-provenance-gate-summary.md`. |
| 32 | PR-43 | `alvaro/evidence-pr43-expert-study-bundle-builder` | Implemented locally; final gates pass; adversarial re-review PASS | Make expert-study bundles reproducible from source export files instead of hand-authored manifests. | Bundle builder computes source artifact hashes from the same bytes it parses, derives run IDs/decision keys/reviewer roster from validated inputs, preserves duplicates for the gate to block, and prevents CLI output from overwriting source artifacts. | Added `artana_evidence_api.evidence_selection.study_bundle`, a thin `scripts/build_evidence_selection_expert_study_bundle.py` CLI, read-once source artifact hashing/parsing, derived source manifests, concise CLI error handling, timezone-aware export timestamp validation, source/output collision protection, CI planner coverage for script-only changes, and service-gate wiring for the new CLI script. RED tests proved the builder and CLI were missing; adversarial review then found synthetic fixtures claiming real evidence, missing duplicate-ranking coverage, separate parse/hash reads, source overwrite risk, traceback-first CLI errors, missing write-error handling, and CI planner omission. GREEN focused tests pass (`46 passed` across bundle builder, CLI, CI planner, validation, and expert-study runner). `make artana-evidence-api-lint`, `make artana-evidence-api-type-check`, `make artana-evidence-api-service-checks`, `make service-checks` with coverage `87.03%`, and `uv run pre-commit run --all-files` pass. Summary: `docs/validation/reports/2026-07-07-pr43-expert-study-bundle-builder-summary.md`. |
| 33 | PR-44 | `alvaro/evidence-pr44-expert-source-export-metadata` | Implemented locally; final gates pass; adversarial re-review PASS | Make expert-study source identity self-describing and literal so manual CLI metadata cannot create provenance false confidence. | Selection-review and review-ranking source exports carry matching identity fields; the builder derives `source_manifest` identity from those exports; optional request/CLI identity fields are compatibility checks only; source timestamps must use exact `YYYY-MM-DDTHH:MM:SSZ`, and identity text fields must not have leading or trailing whitespace. | Added `artana_evidence_api.evidence_selection.source_exports`, self-describing `evidence_selection_review_export.v1` and `evidence_selection_review_ranking_export.v1` envelopes, fail-closed identity matching, exact canonical UTC timestamp parsing, optional all-or-none compatibility checks, CLI derivation from source exports, and docs for the source-export contract. RED tests proved timezone-naive source timestamps were accepted, same-instant alternate UTC spellings could bypass literal identity, whitespace identity fields were normalized, and compatibility override mismatches lacked CLI coverage. GREEN focused tests pass (`73 passed` across bundle builder, CLI, validation, and expert-study runner). Touched-file Ruff, `make artana-evidence-api-type-check`, `make artana-evidence-api-service-checks`, and `make service-checks` pass with coverage `87.03%`. Adversarial re-review found no remaining code/spec blocker after exact timestamp and whitespace fixes; packaging notes were addressed by including the new source-export module and PR44 report in the PR set while leaving unrelated `uv.lock` unstaged. Summary: `docs/validation/reports/2026-07-07-pr44-expert-source-export-metadata-summary.md`. |
| 34 | PR-45 | `alvaro/evidence-pr45-expert-source-export-writer` | Implemented locally; Evidence API gate and adversarial review pass; aggregate live-key blocker found | Make PR44 source-export envelopes generated by a typed writer instead of hand-authored JSON. | Writer creates matching selection-review and review-ranking source exports from collected review JSON, rejects output paths that overwrite source inputs or collide with each other, writes paired outputs all-or-nothing with rollback, and CI treats the new script as Evidence API code. | Added `artana_evidence_api.evidence_selection.source_export_writer`, `scripts/build_evidence_selection_source_exports.py`, writer/CLI tests, CI planner coverage for the new script, and Makefile lint/type-check coverage. RED tests proved the writer module and CLI were missing and script-only changes would skip the Evidence API gate. Adversarial review then found paired outputs could be partially written, commit-phase rollback was missing, backup-preparation rollback was incomplete, and the CI planner regression belonged in the repo-control suite; PR45 added preflight-failure, second-final-replace rollback, and second-backup-preparation rollback regressions, temp-file paired writes with backup restore, and moved planner coverage to `tests/unit/test_ci_service_check_planner.py`. GREEN focused tests pass (`70 passed` across source-export writer, bundle builder, bundle CLI, and CI planner). Touched-file Ruff, `make artana-evidence-api-type-check`, `make artana-evidence-api-service-checks`, and adversarial re-review pass. `make service-checks` fails only when the local `.env.postgres` OpenAI key enables pre-existing real onboarding-agent integration tests; the model returned `pending_question_count` inconsistent with `pending_questions`, outside the PR45 writer path. Next stacked blocker: live onboarding contract normalization. Summary: `docs/validation/reports/2026-07-07-pr45-expert-source-export-writer-summary.md`. |
| 35 | PR-46 | `alvaro/evidence-pr46-live-onboarding-contract-normalization` | Implemented locally; final gates pass; adversarial fixes applied | Close the live-key aggregate gate blocker found during PR45 validation by making onboarding contracts robust to redundant count drift. | Onboarding agent contracts derive `pending_question_count` from valid normalized `pending_questions` before nested state validation, while malformed pending-question payloads still fail closed. | RED tests reproduced the live failure shape: clarification output with real pending questions but stale `pending_question_count`, plus plan-ready output with no pending questions but stale count. PR46 normalizes onboarding contract count drift, keeps the existing conservative downgrade from `plan_ready` with top-level questions to `clarification_request`, rejects non-string pending-question items instead of filtering them away, and preserves `review_needed`/`plan_ready` rejection when valid pending questions remain without a top-level downgrade. GREEN focused onboarding tests pass (`28 passed`), the exact live onboarding integration test passes against isolated Postgres with `.env.postgres`, touched-file Ruff passes, `make artana-evidence-api-type-check` passes, `make artana-evidence-api-service-checks` passes, and `make service-checks` passes with coverage `87.03%`. Summary: `docs/validation/reports/2026-07-07-pr46-live-onboarding-contract-normalization-summary.md`. |
| 36 | PR-47 | `alvaro/evidence-pr47-shadow-review-packet-export` | Implemented locally; final gates pass; adversarial re-review PASS | Make the next human shadow-review step reproducible without pretending unlabeled packets are expert evidence. | Shadow-review packets include durable candidate IDs, blank human selection labels, blank ranking outcomes, explicit completion-required fields, and `production_readiness_claim=false`; shadow-mode would-have-selected records count as harness selections, and real proposal/review-item artifacts produce ranking forms. | Added `artana_evidence_api.evidence_selection.shadow_review_packet`, `scripts/build_evidence_selection_shadow_review_packet.py`, packet/CLI tests, runtime result serializer ranking-score coverage, CI planner coverage, and Makefile lint/type-check coverage for the new script. RED tests proved the packet module and CLI were missing and script-only changes would skip the Evidence API gate. Adversarial review then found shadow-mode recommendations were misclassified as deferred-only, real result artifacts used `proposals`/`review_items` instead of `review_ranking_items`, and packet invariants were not schema-enforced; PR47 added real-artifact regressions and fixed all three. GREEN focused tests pass (`12 passed` across packet, CLI, serializer, CI planner, and Makefile contract), touched-file Ruff passes, `make artana-evidence-api-type-check` passes, `make artana-evidence-api-service-checks` passes, targeted adversarial re-review reports PASS, and `make service-checks` passes with coverage `87.03%`. The packet command consumes an evidence-selection result artifact and writes an explicitly incomplete `evidence_selection_shadow_review_packet.v1` file that can be reviewed by humans before PR45 source-export writing and PR41 expert-study gates. This is label-collection infrastructure, not a trusted-graph readiness claim. Summary: `docs/validation/reports/2026-07-07-pr47-shadow-review-packet-export-summary.md`. |
| 37 | PR-48 | `alvaro/evidence-pr48-shadow-review-completion-export` | Implemented locally; post-adversarial aggregate gate passes | Convert completed shadow-review packets into the strict raw inputs consumed by the PR45 source-export writer. | Completed packets fail closed unless reviewer IDs, explanation scores, overclaim counts, ranking outcomes, adjudication notes, and candidate-record references are complete; paired output writes avoid half-converted source inputs and successful overwrites do not leak backups. | Added `artana_evidence_api.evidence_selection.shadow_review_completion`, `scripts/build_evidence_selection_shadow_review_source_inputs.py`, completed-packet conversion tests, CLI tests, unknown-record and incomplete-label regressions, all-or-nothing paired output regression, whitespace-only reviewer regressions, directory-output rejection, no-backup overwrite regression, CI planner coverage, and Makefile lint/type-check coverage for the new script. Independent adversarial review initially BLOCKED PR48 for blank reviewer IDs and writer preflight/backup gaps; fixes landed and focused converter/CLI tests pass (`12 passed`), adjacent PR45/PR47/PR48 workflow tests pass (`31 passed`), touched-file Ruff passes, `make artana-evidence-api-type-check` passes, post-adversarial `make artana-evidence-api-service-checks` passes, and post-adversarial `make service-checks` passes with coverage `87.03%`. This turns a human-completed packet into `selection-review-labels.json` and `review-ranking-study.json`; it still does not claim production readiness until source exports and expert-study gates pass. Summary: `docs/validation/reports/2026-07-07-pr48-shadow-review-completion-export-summary.md`. |
| 38 | PR-49 | `alvaro/evidence-pr49-shadow-review-pipeline-gate` | Implemented locally; post-adversarial aggregate gate passes | Turn a completed shadow-review packet into a reproducible source-export, expert-study bundle, and gate-report handoff. | A completed packet can be converted into PR48 raw inputs, PR45 self-describing source exports, a PR43 expert-study bundle, and a PR41 expert-study gate report without manual file stitching; the CLI returns nonzero on failed gates while preserving the failure report, and output paths cannot overwrite the source packet. | Added `artana_evidence_api.evidence_selection.shadow_review_study_pipeline`, `scripts/build_evidence_selection_shadow_review_study_artifacts.py`, pipeline/CLI tests, relaxed-threshold pass coverage, default-threshold failed-gate report preservation, output-dir/file rejection, source-packet collision regression, CI planner coverage, Makefile lint/type-check coverage, and a typing cleanup in `scripts/run_evidence_selection_expert_study_gate.py`. Independent adversarial review initially BLOCKED PR49 because `--packet output_dir/selection-review-labels.json --output-dir output_dir` could overwrite the completed packet; PR49 now carries packet-path metadata and preflights all fixed outputs against the source packet before any write. Focused/adjacent PR41/43/45/48/49 tests pass (`85 passed`), touched-file Ruff passes, `make artana-evidence-api-type-check` passes, post-adversarial `make artana-evidence-api-service-checks` passes, and `make service-checks` passes with coverage `87.03%`. Summary: `docs/validation/reports/2026-07-07-pr49-shadow-review-pipeline-gate-summary.md`. |
| 39 | PR-50 | `alvaro/evidence-pr50-shadow-review-study-batch` | Implemented locally; post-adversarial aggregate gate passes; adversarial re-review PASS | Run completed shadow-review study packets as a measured suite instead of a one-packet proof. | A strict batch manifest can run many completed packets through the PR49 single-packet pipeline, preserve each per-entry gate report, aggregate pass/fail counts, fail closed by default on any failed entry, and protect source manifests from artifact/report overwrites. | Added `artana_evidence_api.evidence_selection.shadow_review_study_batch`, `scripts/build_evidence_selection_shadow_review_study_batch.py`, batch/CLI tests, duplicate entry/export/output-subdir guards, unsafe output-subdir rejection, manifest artifact collision protection, aggregate JSON/Markdown report writing, per-entry gate-report preservation, `--allow-failed-gate` behavior, CI planner coverage, and Makefile lint/type-check coverage. RED tests failed on the missing module/CLI/gate wiring; GREEN focused PR50 tests pass (`9 passed`), adjacent PR48/49/50/gate/CI/Makefile tests pass (`59 passed`), touched-file Ruff passes, `make artana-evidence-api-type-check` passes, `make artana-evidence-api-service-checks` passes, and `make service-checks` passes with coverage `87.03%`. Adversarial review then BLOCKED cross-entry packet/artifact overwrite and packet/report overwrite risk; PR50 now computes one protected source-path set from the manifest plus every packet path, uses it for per-entry artifact and aggregate report preflights, resolves manifest-relative packet paths, and adds regressions for cross-entry source-packet artifact collision, packet/report collision, duplicate output subdirs, and duplicate export IDs. Post-fix focused PR50 tests pass (`13 passed`), adjacent PR48/49/50/gate/CI/Makefile tests pass (`63 passed`), touched-file Ruff passes, `make artana-evidence-api-type-check` passes, `make artana-evidence-api-service-checks` passes, and `make service-checks` passes with coverage `87.03%`. Adversarial re-review reports PASS and reran the old overwrite repro successfully. Summary: `docs/validation/reports/2026-07-07-pr50-shadow-review-study-batch-summary.md`. |
| 40 | PR-51 | `alvaro/evidence-pr51-shadow-review-batch-suite-gate` | Implemented locally; final Evidence API gate passes; adversarial PASS | Prevent tiny, narrow, cloned, low-sample, or low-quality shadow-review batches from being treated as production study evidence. | Batch reports must include a non-relaxable production suite gate that fails closed unless entry count, passed-entry count/rate, failed-entry count, total sample size, source-run/study identity, cross-batch diversity, aggregate quality, and raw unrounded quality floors pass together. | Added `EvidenceSelectionShadowReviewStudyBatchSuiteThresholds`, production-floor enforcement for suite thresholds, suite summaries/blocking reasons, `result.passed` based on the suite gate rather than only failed-entry count, CLI `--min-batch-*` controls that can tighten but not relax production floors, and Markdown suite-gate rendering. RED/GREEN regressions cover one-entry overclaiming, failed-entry diversity padding, punctuation-spoofed diversity labels, rounded pass-rate and rounded quality comparisons, cloned source runs, thin total sample size, and relaxed per-entry quality thresholds. Focused batch/CLI tests pass (`22 passed`), adjacent PR47-PR51/source-export/bundle/expert-study/CI/Makefile tests pass (`160 passed`), touched-file Ruff passes, `make artana-evidence-api-type-check` passes, final `make artana-evidence-api-service-checks` passes, and adversarial review reports PASS on production-overclaim correctness. Summary: `docs/validation/reports/2026-07-07-pr51-shadow-review-batch-suite-gate-summary.md`. |
| 41 | PR-52 | `alvaro/evidence-pr52-shadow-review-batch-report-transparency` | Implemented locally; focused gates pass; adversarial PASS | Make PR51 suite-gate enforcement visible to operators reading the Markdown report. | Markdown reports expose whether production floors were applied and show requested-vs-enforced suite thresholds without changing gate math. | Added production-floor reporting, a Suite Thresholds table, `--allow-failed-gate` help text that mentions suite-gate failures, and defensive `unknown` rendering when old/malformed reports omit production-floor status. RED tests proved the Markdown report hid production-floor enforcement, the help text only mentioned entry failures, and missing production-floor fields rendered misleadingly as `no`. GREEN focused transparency tests pass (`3 passed`), focused batch/CLI tests pass (`24 passed`), touched-file Ruff passes, `make artana-evidence-api-type-check` passes, and adversarial review reports PASS after the defensive nit fix. Summary: `docs/validation/reports/2026-07-07-pr52-shadow-review-batch-report-transparency-summary.md`. |
| 42 | PR-53 | `alvaro/evidence-pr53-shadow-review-batch-manifest-builder` | Implemented locally; Evidence API gate passes; adversarial PASS | Remove the manual manifest-authoring gap before running real completed shadow-review packets through the batch suite gate. | Completed human-labeled packets can be converted into a strict `evidence_selection_shadow_review_study_batch.v1` manifest through a validated builder path. | Added `artana_evidence_api.evidence_selection.shadow_review_study_batch_manifest`, `scripts/build_evidence_selection_shadow_review_study_batch_manifest.py`, completed-packet validation before manifest creation, manifest-relative packet paths, derived entry/output/export IDs, duplicate packet-path rejection, source-packet overwrite protection, docs/template commands, CI planner coverage, and Makefile type-check coverage. RED tests proved the module/script were missing and CI/type gates skipped the new script. GREEN new builder tests pass (`4 passed`), adjacent shadow-review workflow/gate tests pass (`58 passed`), touched-file Ruff passes, `make artana-evidence-api-type-check` passes, `make artana-evidence-api-service-checks` passes, and adversarial review reports PASS with no blocking findings. Summary: `docs/validation/reports/2026-07-07-pr53-shadow-review-batch-manifest-builder-summary.md`. |

## PR Evidence Packet

Every PR should update this section or append a new dated entry under
`Evidence Log`.

Required PR evidence:

```text
PR:
Branch:
Commit:
Date:
Goal:
Changed files:
Tests run:
Audit command:
Report artifact:
Before metrics:
After metrics:
Safety invariant added or tightened:
Known remaining risk:
Reviewer/adversarial notes:
```

Minimum commands for evidence-quality PRs:

```bash
uv run --python python3.13 \
  --with ruff ruff check \
  scripts/run_relation_feasibility_audit.py \
  scripts/validation/relation_feasibility \
  tests/unit/test_relation_feasibility_audit.py

uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest tests/unit/test_relation_feasibility_audit.py -q

uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/<date>-<pr>-agent-strict
```

The default benchmark is
`scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`.
Use `--cases` only when intentionally comparing against another fixture.

Add service-specific checks when a PR changes service code:

```bash
make artana-evidence-api-service-checks
make graph-service-checks
make service-checks
```

Run only the service checks relevant to the changed boundary, then run the
aggregate gate before merge when the PR is ready.

## Evidence Log

### 2026-07-10 - Shadow-Review Consolidation Hardening

Branch: `alvaro/evidence-consolidated-shadow-study`

Goal: Close adversarial provenance and artifact-publication gaps before real
human shadow-review data is collected.

Evidence:

- `services/artana_evidence_api/evidence_selection/shadow_review_integrity.py`
- `services/artana_evidence_api/evidence_selection/shadow_review_completion.py`
- `services/artana_evidence_api/evidence_selection/shadow_review_study_pipeline.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline.py`

Result:

- The packet command now emits an editable completion copy and a separate
  producer-signed machine sidecar. Completion conversion verifies the signed
  digest and rejects any changed machine-owned facts.
- Batch defaults allow one packet to contribute a narrow per-entry measurement
  while retaining the production suite's aggregate diversity and sample gates.
- Artifact writers detect hardlink aliases, sanitize Pydantic diagnostics, use
  canonical UTC provenance timestamps, and avoid publishing partial study
  output when an artifact or gate-report step fails.

Validation:

- Focused shadow-review, source-export, bundle, and validation tests passed.
- Full Evidence API unit suite passed: `pytest services/artana_evidence_api/tests/unit -q`.
- `make artana-evidence-api-type-check`,
  `make relation-feasibility-quality-gate`, and
  `pre-commit run --all-files` passed.
- The static/boundary/contract phases of
  `make artana-evidence-api-service-checks` passed. Its Postgres-backed test
  phase could not run because the local Docker socket and Postgres service were
  unavailable.

Known remaining risk:

- This hardens the human-review measurement workflow; it does not substitute
  for the required real, independently reviewed shadow-study data or prove
  trusted-graph readiness.

### 2026-07-07 - PR-38 Review-Ranking Calibration

PR: PR-38 review-ranking calibration

Branch: `alvaro/evidence-pr38-review-ranking-calibration`

Goal: Make production review-ranking calibration observable from actual human
review decisions.

Evidence:

- `docs/validation/reports/2026-07-07-pr38-review-ranking-calibration-summary.md`
- `services/artana_evidence_api/ranking.py`
- `services/artana_evidence_api/evidence_selection_workspace_snapshot.py`
- `services/artana_evidence_api/tests/unit/test_ranking.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py`

Result:

- Review-ranking calibration summary includes sample count, mean score,
  observed positive rate, and expected calibration error.
- Evidence-selection workspace snapshots now include
  `review_ranking_calibration`.
- Positive outcomes are promoted proposals and resolved review items.
- Negative outcomes are rejected proposals and dismissed review items.
- Pending items do not affect calibration.

Validation:

- RED focused tests failed on missing calibration API.
- GREEN focused tests passed: `2 passed`.
- Expanded focused tests passed after adversarial fixes: `8 passed`.
- Touched-file Ruff passed.

Known remaining risk:

- Production ranking thresholding still needs a larger expert or shadow-mode
  review set before setting a hard ECE gate.

### 2026-07-07 - PR-37 Calibration Gate

PR: PR-37 calibration gate

Branch: `alvaro/evidence-pr37-calibration-gate`

Goal: Make score calibration a measured and blocking trusted-readiness metric
instead of an unverified Definition-of-Green claim.

Evidence:

- `docs/validation/reports/2026-07-07-pr37-calibration-gate-summary.md`
- `reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run1/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run2/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run3/relation_feasibility_report.json`
- `reports/relation_feasibility_readiness/2026-07-07-pr37-calibration-gate-postreview/relation_feasibility_readiness_report.json`
- `scripts/validation/relation_feasibility/metrics/calibration.py`

Final three-run strict live-agent trusted-lane metrics:

| Metric | Worst | Mean |
|---|---:|---:|
| Trusted readiness | READY | READY |
| Trusted candidate score ECE | 0.0000 | 0.0000 |
| All-candidate score ECE | 0.0732 | 0.0671 |
| Completed-agent precision | 0.9718 | 0.9770 |
| Completed-agent recall | 0.9200 | 0.9467 |
| Completed-agent valuable rate | 0.5493 | 0.5640 |
| High-value recall | 0.9200 | 0.9600 |
| Trusted candidate precision | 1.0000 | 1.0000 |
| Trusted candidate valuable rate | 1.0000 | 1.0000 |
| Trusted candidate generic rate | 0.0000 | 0.0000 |
| Trusted-eligible high-value recall | 1.0000 | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 | 1.0000 |
| Entailment checked rate | 1.0000 | 1.0000 |
| Verified CURIE match rate | 0.7931 | 0.8276 |
| All-candidate generic relation rate | 0.3239 | 0.3166 |

Hard failures:

- fallback cases: `0`
- invalid agent cases: `0`
- negative-control leakage: `0`
- raw unknown relation types/surfaces: `0`
- review-only trusted leakage: `0`
- weak trusted leakage: `0`
- wrong verified CURIE links: `0`

Interpretation: trusted auto-promotion support calibration is now measured and
enforced by the readiness gate. Production review-ranking calibration remains a
follow-up prioritization issue, not a trusted graph blocker.

### 2026-07-07 - PR-36 V4 Live-Agent Trusted Readiness

PR: PR-36 v4 live-agent trusted readiness

Branch: `alvaro/evidence-pr36-v4-live-readiness`

Goal: Run the strict live-agent readiness loop against the 100-case v4 fixture
and prevent broad or structurally under-grounded review evidence from leaking
into trusted graph auto-promotion.

Evidence:

- `docs/validation/reports/2026-07-06-pr36-v4-live-readiness-summary.md`
- `reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run1/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run2/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-07-pr36-v4-live-readiness-postreview2-run3/relation_feasibility_report.json`
- `reports/relation_feasibility_readiness/2026-07-07-pr36-v4-live-readiness-postreview2/relation_feasibility_readiness_report.json`
- `services/artana_evidence_api/document_extraction_support/review_policy/trusted_promotion_safety_policy.py`

Final three-run strict live-agent trusted-lane metrics:

| Metric | Worst | Mean |
|---|---:|---:|
| Trusted readiness | READY | READY |
| Completed-agent precision | 0.9861 | 0.9908 |
| Completed-agent recall | 0.9467 | 0.9600 |
| Completed-agent valuable rate | 0.5694 | 0.5733 |
| High-value recall | 0.9600 | 0.9733 |
| Trusted candidate precision | 1.0000 | 1.0000 |
| Trusted candidate valuable rate | 1.0000 | 1.0000 |
| Trusted candidate generic rate | 0.0000 | 0.0000 |
| Trusted-eligible high-value recall | 1.0000 | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 | 1.0000 |
| Entailment checked rate | 1.0000 | 1.0000 |
| Verified CURIE match rate | 0.8161 | 0.8314 |
| All-candidate generic relation rate | 0.3288 | 0.3211 |

Hard failures:

- fallback cases: `0`
- invalid agent cases: `0`
- negative-control leakage: `0`
- raw unknown relation types: `0`
- raw unknown relation type surfaces: `0`
- review-only gold trusted leakage: `0`
- weak-claim trusted leakage: `0`
- wrong verified CURIE links: `0`

Validation:

- Quality-filter suite: `62 passed`
- Focused regression bundle: passed
- Touched-file Ruff: `All checks passed!`
- `make relation-feasibility-quality-gate`: passed
- Strict v4 postreview2 live-agent runs1-3: all `GREEN`
- Repeated-run readiness gate with `--fail-on-not-ready`: `READY`
- Final adversarial re-review: PASS
- `make service-checks`: passed with coverage `87.03%`

Adversarial review fixes:

- Added `CAUSES` and non-dictionary gene-state association regressions so
  bare-gene/gene-state disease claims cannot bypass promotion safety.
- Prevented `growth` inside molecular target names such as epidermal growth
  factor receptor from being treated as a composite growth process.
- Merged weak-review and trusted-promotion safety reason codes so audit trails
  do not lose either reason family.
- Added the `Ruxolitinib INHIBITS JAK2 activity` conversion regression and
  repair so a verified direct target is recovered instead of trusting a
  model-only process endpoint.
- Added the `growth factor-independent proliferation` regression so target-like
  tokens inside process labels do not bypass composite-process review-only
  safety; the v4 fixture and postreview2 live reports do not contain this phrase,
  so the live-readiness metrics above remain the authoritative postreview2
  batch.

Interpretation:

PR36 makes the v4 trusted lane ready under the current repeated strict
live-agent gate. The change is not a fallback or benchmark-only shortcut: it
adds code-level trusted-promotion safety rules and applies the same policy to
fixture validation. Remaining all-candidate generic noise and review-only CURIE
gaps stay visible as follow-up review-lane work, not trusted auto-promotion
blockers.

### 2026-07-06 - PR-34 Live Model A/B Proof

PR: PR-34 live model A/B proof

Branch: `alvaro/evidence-pr34-live-model-ab-proof`

Goal: Prove whether a stronger extraction model should replace the current
configured model for trusted-readiness evaluation, using the same v3 fixture and
fail-closed adoption rules.

Evidence:

- `docs/validation/reports/2026-07-06-pr34-live-model-ab-proof-summary.md`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/relation_model_comparison_report.json`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/relation_model_comparison_report.md`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/runs/current/run1/relation_feasibility_report.json`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/runs/current/run2/relation_feasibility_report.json`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/runs/current/run3/relation_feasibility_report.json`
- `reports/relation_model_comparison/2026-07-06-pr34-live-model-ab-proof/runs/candidate/run1/relation_feasibility_report.json`

Model comparison decision:

- current model: `openai:gpt-5.4-mini`
- candidate model: `openai:gpt-5`
- decision: `KEEP_CURRENT`
- candidate adoption blocker: candidate audit run failed
- candidate completed reports: `1/3`
- candidate failed run: run2 exited `2` after live-agent preflight timed out

Current model worst-run metrics across v3 runs1-3:

| Metric | Worst |
|---|---:|
| Trusted readiness | READY |
| Completed-agent precision | 1.0000 |
| Completed-agent recall | 1.0000 |
| Completed-agent valuable rate | 0.5333 |
| High-value recall | 1.0000 |
| Trusted candidate precision | 1.0000 |
| Trusted candidate valuable rate | 1.0000 |
| Trusted candidate generic rate | 0.0000 |
| Trusted-eligible high-value recall | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 |
| Entailment checked rate | 1.0000 |
| Verified CURIE match rate | 0.7250 |

Candidate completed run1 metrics:

| Metric | Value |
|---|---:|
| Verdict | GREEN |
| Completed-agent precision | 1.0000 |
| Completed-agent recall | 0.9667 |
| High-value recall | 0.9500 |
| Trusted candidate precision | 1.0000 |
| Trusted-eligible high-value recall | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 |
| Fallback cases | 0 |
| Invalid agent cases | 0 |
| Wrong verified CURIE links | 0 |

Validation:

- RED/GREEN fixture-pinning regression passed.
- RED/GREEN failed-candidate-audit reporting regression passed.
- Symmetric failed-current-run regression passed.
- Focused model-comparison suite: `13 passed`.
- `make relation-feasibility-quality-gate`: passed.
- `make service-checks`: passed with coverage `87.03%`.
- Corrected live A/B command used
  `--cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`.

Interpretation:

Do not switch the default extraction model to `openai:gpt-5` from this evidence.
The current model is repeatably READY on the trusted lane, while the stronger
candidate did not complete the required three-run gate and its only completed
run was worse on completed-agent recall, high-value recall, and valuable
candidate rate.

### 2026-07-06 - PR-35 Benchmark V4 100-Case Proof

PR: PR-35 benchmark v4 100-case proof

Branch: `alvaro/evidence-pr35-benchmark-v4-100-case-proof`

Goal: Make the Definition-of-Green benchmark scale requirement executable by
adding a 100-case v4 fixture and tests that fail when the fixture is too small
or too narrow.

Evidence:

- `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json`
- `tests/unit/test_relation_feasibility_fixture_validation.py`
- `docs/validation/reports/2026-07-06-pr35-benchmark-v4-100-case-proof-summary.md`

Fixture coverage:

- validator issue count: `0`
- total cases: `100`
- gold relation signatures: `75`
- unique gold relation signatures: `74`
- repeated gold relation signatures: `1`
- strong-specific cases: `50`
- weak review-only cases: `25`
- negative controls: `25`
- high-value specific cases: `50`
- true low-value review gold cases: `25`
- any review-only gold cases: `62`
- long-document topic cases: `8`
- adversarial negated near-miss cases: `6`

RED/GREEN proof:

- RED: `test_v4_fixture_reaches_definition_of_green_scale` failed with
  `FileNotFoundError` while the v4 fixture was absent.
- Adversarial RED: high-value review-only rows could satisfy the old blended
  low-value counter.
- Adversarial RED: duplicate v4 relation signatures padded the 100-case count,
  and new broad v4 pathway/gene rows were trusted candidates.
- GREEN: `uv run pytest tests/unit/test_relation_feasibility_fixture_validation.py -q`
  passed with `7 passed`.

Remaining proof:

- After mergeable local validation, run strict live-agent readiness against the
  v4 fixture before claiming trusted-graph readiness.

Final local validation:

- `uv run ruff check scripts/validation/relation_feasibility/fixture_checks/validation.py tests/unit/test_relation_feasibility_fixture_validation.py`: passed.
- `make relation-feasibility-quality-gate`: passed.
- `make service-checks`: passed with coverage `87.03%`.
- Final adversarial re-review: PASS, with only residual risk that strict
  live-agent v4 readiness remains the next proof before any trusted-graph-ready
  claim.

### 2026-07-06 - PR-33 Review Burden Pruning And Agent Retry Hardening

PR: PR-33 review burden pruning

Branch: `alvaro/evidence-pr33-review-burden-pruning`

Goal: Remove repeated low-value live-agent false positives from the review lane
and add agent-only retries for rare zero-candidate and schema-invalid responses,
without letting deterministic fallback count as evidence.

Evidence:

- `docs/validation/reports/2026-07-06-pr33-review-burden-pruning-summary.md`
- `reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run1/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run2/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run3/relation_feasibility_report.json`
- `reports/relation_feasibility_readiness/2026-07-06-pr33-review-burden-postadversarial3-runs1-3/relation_feasibility_readiness_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr33-review-burden-postadversarial3-runs1-3/relation_feasibility_failure_analysis_report.json`

Final three-run strict live-agent metrics:

| Metric | Worst | Mean |
|---|---:|---:|
| Trusted readiness | READY | READY |
| Completed-agent precision | 1.0000 | 1.0000 |
| Completed-agent recall | 1.0000 | 1.0000 |
| Completed-agent valuable rate | 0.5333 | 0.5333 |
| High-value recall | 1.0000 | 1.0000 |
| Trusted candidate precision | 1.0000 | 1.0000 |
| Trusted candidate valuable rate | 1.0000 | 1.0000 |
| Trusted candidate generic rate | 0.0000 | 0.0000 |
| Trusted-eligible high-value recall | 1.0000 | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 | 1.0000 |
| Entailment checked rate | 1.0000 | 1.0000 |
| Verified CURIE match rate | 0.7250 | 0.7250 |

Failure attribution:

- missed gold relations: `0`
- repeated false positives: `0`
- fallback cases: `0`
- invalid agent cases: `0`
- negative-control leakage: `0`
- weak-claim trusted leakage: `0`
- review-only gold trusted leakage: `0`
- wrong verified CURIE links: `0`
- CURIE gaps: `35`, mostly review-only endpoint decisions and unverified model
  hints that remain outside trusted promotion

Validation:

- Focused PR33 relation/retry suite: `80 passed in 0.87s`
- Quality-filter suite: `47 passed in 0.16s`
- Touched-file Ruff: `All checks passed!`
- `make relation-feasibility-quality-gate`: passed
- `make service-checks`: passed with coverage `87.03%`
- Post-adversarial3 strict live-agent runs1-3: all `GREEN`
- Adversarial review fixes: invalid target siblings can no longer shadow valid
  pathway evidence, and raw-but-unusable model relations no longer suppress the
  zero-candidate agent retry. The post-review schema failure is now covered by
  RED/GREEN schema-repair retry regressions, including schema-to-zero retry
  chaining, weak-pass candidate preservation, and unknown-only candidate retry.
- Readiness aggregate:
  `reports/relation_feasibility_readiness/2026-07-06-pr33-review-burden-postadversarial3-runs1-3/relation_feasibility_readiness_report.md`
- Failure analysis:
  `reports/relation_feasibility_failure_analysis/2026-07-06-pr33-review-burden-postadversarial3-runs1-3/relation_feasibility_failure_analysis_report.md`

### 2026-07-06 - PR-29 V3 CURIE Recovery And Rare-Disease Recall

PR: PR-29 v3 CURIE recovery

Branch: `alvaro/evidence-pr29-v3-curie-recovery`

Goal: Recover verified endpoint CURIEs for repeated v3 high-value misses and
make the live agent extract direct rare-disease gene-variant associations
without crediting deterministic fallback.

Evidence:

- `docs/validation/reports/2026-07-06-pr29-v3-curie-recovery-summary.md`
- `reports/relation_feasibility/2026-07-06-pr29-v3-curie-recovery-run7/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-06-pr29-v3-curie-recovery-run7/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr29-v3-curie-recovery-run7/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr29-v3-curie-recovery-run7/relation_feasibility_failure_analysis_report.md`

Final strict live-agent metrics:

| Metric | Value |
|---|---:|
| Verdict | YELLOW |
| Completed-agent precision | 0.9032 |
| Completed-agent recall | 0.9333 |
| Completed-agent valuable rate | 0.5161 |
| High-value recall | 1.0000 |
| High-value review-only recall | 1.0000 |
| Trusted high-value recall | 0.3500 |
| Low-value review recall | 0.8000 |
| Trusted-eligible CURIE-linked endpoint rate | 1.0000 |
| Verified CURIE match rate | 0.7250 |
| Model wrong CURIE hints | 2 |
| Wrong verified CURIE links | 0 |
| Weak-claim trusted leakage count | 0 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control leakage cases | 0 |
| Generic relation rate | 0.2903 |

Validation:

- Focused RED/GREEN verified dictionary tests passed.
- Focused RED/GREEN CURIE-linking tests passed.
- Focused RED/GREEN candidate conversion tests proved review-only endpoint
  grounding demotes the whole candidate from trusted eligibility.
- V3 fixture validation now rejects trusted gold rows that use review-only
  endpoint labels.
- V3 fixture validation now rejects invalid `review_status` values and
  review-only endpoint labels that keep trusted CURIEs.
- High-value review-only capture now has explicit metrics, separating useful
  review evidence from trusted graph evidence.
- Prompt regression for rare-disease gene-variant associations passed.
- Touched-file Ruff passed.
- `make relation-feasibility-quality-gate` passed.
- Strict live-agent run3 was superseded after adversarial review found broad or
  incorrect exact CURIE curation.
- Strict live-agent run7 is the authoritative result: YELLOW with trusted
  endpoint rate `1.0000`, high-value review-only recall `1.0000`, wrong
  verified CURIE links `0`, fallback `0`, invalid
  agent `0`, negative-control leakage `0`, and weak trusted leakage `0`.

Known remaining risk:

- This is still not trusted-graph ready.
- Trusted high-value recall is only `0.3500` because many high-value gene-state,
  composite response, and molecular subtype endpoints are correctly review-only
  until structured grounding exists.
- Generic relation rate remains high at `0.2903`, and valuable candidate rate is
  only `0.5161`.
- The next PR should reduce generic relation noise and add structured grounding
  for safe gene-state or molecular-subtype concepts without weakening safety
  floors.

### 2026-07-06 - PR-27 Benchmark V3 And Generated Proof Docs

PR: PR-27 benchmark v3 and generated proof docs

Branch: `alvaro/evidence-pr27-benchmark-v3-doc-proof`

Goal: Make the relation-feasibility benchmark harder and broader, then generate
proof summaries from JSON so metrics and blockers do not drift from artifacts.

Evidence:

- `docs/validation/reports/2026-07-06-pr27-benchmark-v3-doc-proof-summary.md`
- `docs/validation/reports/2026-07-06-pr27-v2-relation-feasibility-report.json`
- `docs/validation/reports/2026-07-06-pr27-v2-generated-summary.md`
- `docs/validation/reports/2026-07-06-pr27-v3-relation-feasibility-report.json`
- `docs/validation/reports/2026-07-06-pr27-v3-failure-analysis-report.json`
- `docs/validation/reports/2026-07-06-pr27-v3-generated-summary.md`
- `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- `reports/relation_feasibility/2026-07-06-pr27-v2-run1/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-06-pr27-v3-run2/relation_feasibility_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr27-v3-run2/relation_feasibility_failure_analysis_report.json`

Result:

- V2 seed fixture verdict: GREEN
- V3 expanded fixture verdict: RED
- V3 completed-agent precision: 0.7333
- V3 completed-agent recall: 0.7333
- V3 high-value recall: 0.7000
- V3 trusted high-value recall: 0.2000
- V3 trusted-eligible CURIE endpoint rate: 0.3000
- V3 completed-agent valuable candidate rate: 0.3667
- V3 generic relation rate: 0.3000
- V3 model-only wrong CURIE hints: 9
- V3 fallback cases: 0
- V3 invalid strict-agent cases: 0
- V3 negative-control leakage: 0
- V3 weak-claim trusted leakage: 0
- V3 wrong verified CURIE links: 0

Interpretation:

PR27 shows that the previous v2 seed was too curated to prove production
biomedical value. The live agent path remains safe on hard negative controls,
but the expanded fixture exposes real quality blockers in high-value recall,
trusted endpoint recovery, generic relation noise, and near-miss specificity.

Validation:

- Focused PR27 tests passed.
- `make relation-feasibility-quality-gate` passed.
- V3 live-agent run2 completed with fallback 0 and invalid agent 0.
- Failure attribution completed for V3 run2.
- Adversarial re-review passed after tracked proof docs, metric, and fixture
  validation fixes.
- `git diff --check` passed.
- `pre-commit run --all-files` passed.
- `make service-checks` passed with coverage 87.03%.

### 2026-07-06 - PR-24 Grounding Decision Table

PR: PR-24 grounding decision table

Branch: `alvaro/evidence-pr24-grounding-decision-table`

Goal: Make every remaining endpoint-grounding gap either safely verified or
explicitly review-only, with model hints unable to create trusted identifiers
for broad or composite labels.

Evidence:

- `docs/validation/reports/2026-07-06-pr24-grounding-decision-table-summary.md`
- `reports/relation_feasibility/2026-07-06-pr24-grounding-decision-table-run3/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-06-pr24-grounding-decision-table-run3/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr24-grounding-decision-table-run3/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr24-grounding-decision-table-run3/relation_feasibility_failure_analysis_report.md`

Final strict live-agent metrics:

| Metric | Value |
|---|---:|
| Verdict | GREEN |
| Completed-agent precision | 0.9615 |
| Completed-agent recall | 1.0000 |
| Completed-agent valuable rate | 0.7692 |
| High-value recall | 1.0000 |
| Trusted high-value recall | 0.8500 |
| Low-value review recall | 1.0000 |
| Trusted-eligible CURIE-linked endpoint rate | 1.0000 |
| Verified CURIE match rate | 1.0000 |
| Weak-claim trusted leakage count | 0 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Wrong verified CURIE links | 0 |
| Missed gold relations | 0 |
| False positives | 1 safe review-only candidate |
| Generic relation rate | 0.1154 |

Failure attribution:

- All eight remaining endpoint gaps are `review_only_endpoint` rows with
  explicit `grounding_reason_code`, `review_only_for_relation_feasibility_v2`,
  and `trusted_identifier_allowed=False`.
- The only false positive in run3 is `cisplatin TREATS platinum-sensitive
  tumors`; it is `review_only`, has no trusted object CURIE, and carries
  `context_dependent` plus `subset_relation` review reasons.
- Generic relation rate remains `0.1154`, above the trusted-graph target, and
  stays a follow-up blocker.

Validation:

- Focused RED/GREEN grounding decision tests passed.
- Affected grounding/linking/failure-analysis suites passed.
- Affected document extraction suites passed.
- `make relation-feasibility-quality-gate` passed.
- Strict live-agent run1 passed with fallback 0 and invalid agent 0.
- Strict live-agent run2 exposed a primary-pass raw relation type crash; PR24
  now routes primary LLM output through the code-owned unknown-type guard.
- Strict live-agent run3 passed with fallback 0, invalid agent 0, and wrong
  verified CURIE links 0.

Known remaining risk:

- This is still single-run evidence.
- Review-only endpoint policy intentionally abstains rather than inventing broad
  CURIEs; final readiness still requires repeatability and graph-side
  promotion enforcement.

### 2026-07-05 - PR-23 Low-Value Review Recall

PR: PR-23 low-value review recall

Branch: `alvaro/evidence-pr23-low-value-review-recall`

Draft PR: https://github.com/med13foundation/artana-evidence-platform/pull/106

Goal: Recover weak but useful low-value evidence with the live agent path while
forcing weak evidence to remain review-only and excluding deterministic fallback
from success.

Evidence:

- `docs/validation/reports/2026-07-05-pr23-low-value-review-recall-summary.md`
- `reports/relation_feasibility/2026-07-05-pr23-low-value-review-recall-run7/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr23-low-value-review-recall-run7/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr23-low-value-review-recall-run7/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr23-low-value-review-recall-run7/relation_feasibility_failure_analysis_report.md`

Final strict live-agent metrics:

| Metric | Value |
|---|---:|
| Verdict | GREEN |
| Completed-agent precision | 1.0000 |
| Completed-agent recall | 1.0000 |
| High-value recall | 1.0000 |
| Trusted high-value recall | 0.8500 |
| Low-value review recall | 1.0000 |
| Low-value review CURIE endpoint capture rate | 1.0000 |
| Trusted-eligible CURIE-linked endpoint rate | 1.0000 |
| Verified CURIE match rate | 1.0000 |
| Weak-claim trusted leakage count | 0 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control leakage cases | 0 |
| Raw unknown relation-type surfaces | 0 |
| Wrong verified CURIE links | 0 |

Validation:

- Focused RED/GREEN weak-pass tests passed.
- Affected extraction, prompt, quality-filter, and review-policy tests passed.
- `make relation-feasibility-quality-gate` passed.
- Strict live-agent run7 passed with all five low-value review cases captured
  as `review_only`.
- Adversarial review findings from run6 were addressed before run7: mixed
  strong/weak sentence poisoning, weak-pass structured proposal leakage, and
  fallback-creditable low-value review metrics now have regressions.
- `make service-checks` passed with coverage 87.03% against the 86% gate.
- PR #106 GitHub checks passed and `mergeStateStatus` was `CLEAN` while the PR
  remained draft.

Known remaining risk:

- Precision returned to 1.0000 after adversarial mixed-sentence scoping and weak-pass proposal rejection fixes.
- Generic review-lane noise remains visible and should be tightened in a
  follow-up without losing weak-review recall.
- Repeatability still needs multi-run proof before final trusted-readiness
  claims.

### 2026-07-05 - PR-22 Low-Value Review Lane And Trusted Verdict Split

PR: PR-22 low-value review lane and trusted verdict split

Branch: `alvaro/evidence-pr22-low-value-review-lane`

Goal: Separate trusted-eligible endpoint recovery from low-value review evidence
so weak/hedged claims are measured without blocking trusted high-value promotion
or leaking into trusted graph evidence.

Evidence:

- `docs/validation/reports/2026-07-05-pr22-low-value-review-lane-summary.md`
- `reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_failure_analysis_report.md`

Result: strict live-agent run4 is GREEN for the single-run trusted-lane gate:
completed-agent precision `1.0000`, high-value recall `1.0000`, trusted
high-value recall `0.8500`, trusted-eligible CURIE-linked endpoint rate
`1.0000`, weak-claim trusted leakage `0`, fallback cases `0`, invalid-agent
cases `0`, negative-control leakage `0`, and wrong verified CURIE links `0`.
The production proposal path also carries `review_only` status into draft
metadata, blocks it with a `review_only_candidate` trust-floor failure, and
keeps promotion request metadata from overriding verifier-owned review fields.
Final validation includes focused RED/GREEN regressions, touched-file ruff,
`make relation-feasibility-quality-gate`, architecture checks, `git diff --check`,
final adversarial review, and `make service-checks` with coverage 87.03% against
the 86% gate.

Remaining risk: this is not final trusted-graph readiness. Low-value review
recall remains `0.4000`, low-value review endpoint capture remains `0.2000`,
and final readiness still requires repeated strict live-agent runs plus graph
promotion enforcement.

### 2026-07-05 - PR-21 Verified Grounding And Review-Only Abstention

PR: PR-21 verified grounding and review-only abstention

Branch: `alvaro/evidence-pr21-verified-grounding-closure`

Goal: Improve verified endpoint recovery and trusted high-value recall while
keeping broad/composite endpoint labels review-only.

Evidence:

- `docs/validation/reports/2026-07-05-pr21-verified-grounding-summary.md`
- `reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_failure_analysis_report.md`

Result: strict live-agent path remains RED, but the grounding slice materially
improves the trusted path: completed-agent precision `1.0000`, high-value recall
`1.0000`, trusted high-value recall `0.8500`, verified endpoint rate `0.8810`,
wrong verified links `0`, fallback cases `0`, invalid-agent cases `0`, and
false positives `0`.

### 2026-07-05 - PR-17 Readiness Failure Attribution

PR: PR-17 readiness failure attribution

Branch: `alvaro/evidence-pr17-readiness-failure-attribution`

Goal: Convert the PR16 repeatability failures into a structured error queue for
the PR18-PR22 recovery loop.

Command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/2026-07-05-pr16-repeatability-run1/relation_feasibility_report.json \
  --report current=reports/relation_feasibility/2026-07-05-pr16-repeatability-run2/relation_feasibility_report.json \
  --report current=reports/relation_feasibility/2026-07-05-pr16-repeatability-run3/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr17-pr16-baseline
```

Evidence:

- `docs/validation/reports/2026-07-05-pr17-readiness-failure-attribution-summary.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr17-pr16-baseline/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr17-pr16-baseline/relation_feasibility_failure_analysis_report.md`

Result:

- Repeated missed gold patterns: 9
- Repeated false-positive patterns: 7
- Canonical-supported CURIE-gap patterns: 11
- Proposal candidates: 9
- Proposal gold matches: 4
- Proposal-eligible gold count: 6
- Trusted proposal capture count: 0

Interpretation:

The top next lane is verified entity linking, especially `MAPK signaling`,
`homologous recombination DNA repair`, `response to pembrolizumab`,
`aggressive tumor growth`, `cardiac septal development`, and
`ERK phosphorylation`. The second lane is high-value resistance relation
recovery, especially `CONFERS_RESISTANCE_TO` and `resistance to gefitinib`
representation.

### 2026-07-05 - PR-19 High-Value Relation Recovery

PR: PR-19 high-value relation recovery

Branch: `alvaro/evidence-pr19-high-value-relation-recovery`

Goal: Recover repeated high-value drug-resistance relations without letting
unapproved proposal surfaces count as trusted graph evidence.

Commands:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_keeps_structured_new_type_proposals \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_filters_review_required_raw_types \
  services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  tests/unit/test_relation_feasibility_audit.py \
  services/artana_evidence_db/tests/unit/test_governance.py::test_graph_governance_repository_seeds_builtin_entity_and_relation_types \
  services/artana_evidence_db/tests/unit/test_app.py::test_seed_builtin_dictionary_entries_persists_core_relation_constraints \
  -q

make relation-feasibility-quality-gate

bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2'

PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr19-run2
```

Evidence:

- `docs/validation/reports/2026-07-05-pr19-high-value-relation-recovery-summary.md`
- `reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr19-run2/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr19-run2/relation_feasibility_failure_analysis_report.md`

Result:

- Verdict: RED
- Agent completed cases: 30
- Fallback cases: 0
- Invalid strict-agent cases: 0
- Negative-control leakage cases: 0
- Completed-agent precision: 0.9048
- High-value recall: 0.9500
- Completed-agent valuable rate: 0.9048
- Generic relation rate: 0.0000
- Raw unknown relation types: 0
- Raw unknown relation inventory surfaces: 0
- Governed proposal candidates: 0
- Verified CURIE-linked gold endpoint rate: 0.8108
- Model CURIE wrong count: 0
- Wrong verified CURIE links: 0

Interpretation:

PR19 closes the repeated drug-resistance shape problem by approving
`CONFERS_RESISTANCE_TO` through both Evidence API extraction and graph
dictionary governance. The remaining RED verdict is not a resistance-semantics
failure; it is verified endpoint coverage plus PR20 qualifier preservation,
especially `BRCA1 loss` being shortened to `BRCA1`.

### 2026-07-05 - PR-20 Qualifier Preservation And Precision

PR: PR-20 qualifier preservation and precision adjudication

Branch: `alvaro/evidence-pr20-qualifier-precision-adjudication`

Goal: Preserve biomedical modifiers such as `loss` and keep entailed context
relations out of trusted candidate precision when a direct mechanism relation is
available.

Commands:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_evidence_grounding.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_prunes_redundant_generic_siblings \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_discover_relation_candidates_reports_llm_pruned_generic_siblings \
  services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q

make relation-feasibility-quality-gate

bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4'

PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr20-run4
```

Evidence:

- `docs/validation/reports/2026-07-05-pr20-qualifier-precision-summary.md`
- `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr20-run4/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr20-run4/relation_feasibility_failure_analysis_report.md`

Result:

- Verdict: RED
- Agent completed cases: 30
- Fallback cases: 0
- Invalid strict-agent cases: 0
- Negative-control leakage cases: 0
- Completed-agent precision: 0.9500
- Completed-agent recall: 0.7600
- Completed-agent valuable rate: 0.9500
- High-value recall: 0.9500
- Trusted high-value recall: 0.5500
- Generic relation rate: 0.0500
- Quality-filtered candidates: 7
- False positives in failure attribution: 1
- Verified CURIE-linked gold endpoint rate: 0.8108
- Model CURIE wrong count: 0
- Wrong verified CURIE links: 0

Interpretation:

PR20 blocks broad subject substitution, narrows context shadowing, scopes
modifier detection to the candidate claim clause including comma-and coordinated
claims, and keeps context relations out of trusted high-value recall. Run3 was
stronger, but run4 is the latest evidence and shows repeatability variance. The
stricter trusted high-value recall metric is only `0.5500`, so the system is
still not trusted-graph ready until verified entity grounding and repeatability
improve.

### 2026-07-02 - PR-0 Baseline Strict Agent Run

PR: PR-0 quality harness

Branch: `alvaro/evidence-pr0-quality-harness`

Goal: Capture the current strict-agent baseline before expanding the quality
harness.

Command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-02-pr0-baseline-agent-strict
```

Evidence:

- `reports/relation_feasibility/2026-07-02-pr0-baseline-agent-strict/relation_feasibility_report.md`
- `reports/relation_feasibility/2026-07-02-pr0-baseline-agent-strict/relation_feasibility_report.json`

Result:

- Verdict: RED
- Precision: 0.6667
- Recall: 0.5000
- Valuable candidate rate: 0.6667
- Generic relation rate: 0.3333
- Agent-completed cases: 0/6
- Fallback or unavailable cases: 6/6
- Invalid strict-agent cases: 6/6

Interpretation:

The strict audit is behaving correctly: unavailable agent extraction remains a
RED result and deterministic fallback candidates are not credited as agent
success.

### 2026-07-02 - PR-0 Expanded V2 Strict Agent Run

PR: PR-0 quality harness

Branch: `alvaro/evidence-pr0-quality-harness`

Goal: Prove the expanded 30-case synthetic seed fixture loads, reports richer
metrics, and surfaces adversarial quality warnings.

Command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-02-pr0-agent-strict-v2
```

Evidence:

- `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- `reports/relation_feasibility/2026-07-02-pr0-agent-strict-v2-fixed/relation_feasibility_report.md`
- `reports/relation_feasibility/2026-07-02-pr0-agent-strict-v2-fixed/relation_feasibility_report.json`
- `docs/validation/reports/2026-07-02-pr0-agent-strict-v2-summary.md`
- `docs/validation/reports/2026-07-02-pr0-agent-strict-v2-summary.json`

Result:

- Verdict: RED
- Cases: 30
- Gold relations: 25
- Precision: 0.7778
- Recall: 0.2800
- Valuable candidate rate: 0.6667
- Generic relation rate: 0.1111
- Agent-completed cases: 0/30
- Fallback or unavailable cases: 30/30
- Invalid strict-agent cases: 30/30
- Completed-agent precision: 0.0000
- Completed-agent recall: 0.0000
- Completed-agent valuable candidate rate: 0.0000
- Fallback candidates that would look valuable: 6
- Support sentence alignment rate: 0.7778
- Adversarial findings: `fallback_only_report`,
  `fallback_candidates_look_valuable`, `substring_grounding_only`,
  `generic_relation_rate_high`

Interpretation:

The expanded fixture and adversarial report layer are working. The local run
still cannot prove agent quality because all 30 cases used unavailable/fallback
diagnostics. This is acceptable for PR-0 because the goal is honest measurement,
not improving extraction quality yet.

Adversarial review:

- Initial verdict: BLOCK
- Issues found: substring-only support could look valuable, fallback candidates
  inflated normal quality metrics, default CLI still used the starter fixture,
  and report snapshots were ignored.
- Fixes added: gold support-sentence alignment, completed-agent metrics,
  default v2 fixture, merge-visible report snapshots, and a control test proving
  report snapshots are not ignored.
- Final verdict: PASS

### 2026-07-02 - PR-1 No Fallback Trust Gate

PR: PR-1 no fallback trust

Branch: planned `alvaro/evidence-pr1-no-fallback-trust`; currently stacked in
worktree branch `alvaro/evidence-pr0-quality-harness` until PR-0 is split.

Goal: Ensure fallback output cannot be confused with completed agent extraction
or trusted evidence in document and proposal metadata.

Changed files:

- `services/artana_evidence_api/document_extraction_contracts.py`
- `services/artana_evidence_api/document_extraction_drafts.py`
- `services/artana_evidence_api/document_extraction.py`
- `services/artana_evidence_api/document_extraction_support/variant_aware_trust_metadata.py`
- `services/artana_evidence_api/research_init_document_extraction_runtime.py`
- `services/artana_evidence_api/routers/documents.py`
- `services/artana_evidence_api/variant_aware_document_extraction.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `services/artana_evidence_api/tests/unit/test_documents_router.py`
- `services/artana_evidence_api/tests/unit/test_research_init.py`
- `services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py`
- `docs/validation/reports/2026-07-02-pr1-no-fallback-trust-summary.md`
- `docs/validation/reports/2026-07-02-pr1-no-fallback-trust-summary.json`

Tests run:

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_treats_same_key_signal_enrichment_as_untrusted \
  -q
```

Result: RED before the final fix, then GREEN. The RED run proved same-key
deterministic signal enrichment produced observation drafts without
`fallback_from_signals`; after the fix those drafts carry
`trusted_evidence_eligible=False`.

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_treats_same_key_signal_enrichment_as_untrusted \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_detects_unmatched_signal_with_non_variant_agent_entity \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_treats_mixed_signal_fallback_as_untrusted \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_treats_signal_only_generated_output_as_fallback \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_falls_back_to_deterministic_signals \
  services/artana_evidence_api/tests/unit/test_documents_router.py::test_extract_document_marks_variant_fallback_proposals_as_not_trusted \
  -q
```

Result: 6 passed.

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_documents_router.py \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_research_init.py::test_execute_research_init_emits_progress_and_marks_fallback_drafts_untrusted \
  -q
```

Result: 133 passed.

```bash
uv run --python python3.13 \
  --with ruff ruff check \
  services/artana_evidence_api/variant_aware_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Static checks, OpenAPI contract check, architecture size and
structure checks, migrations, and isolated Postgres Evidence API tests
completed.

```bash
make service-checks
```

Result: passed. Graph static checks, Evidence API static checks, architecture
checks, migrations, and coverage gate completed. Coverage was 86.83% against an
86% requirement.

Audit command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-02-pr1-no-fallback-trust-agent-strict-r6
```

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-02-pr1-no-fallback-trust-summary.md`
- Local full report:
  `reports/relation_feasibility/2026-07-02-pr1-no-fallback-trust-agent-strict-r6/relation_feasibility_report.md`
- Local full JSON:
  `reports/relation_feasibility/2026-07-02-pr1-no-fallback-trust-agent-strict-r6/relation_feasibility_report.json`

After metrics:

- Verdict: RED
- Precision: 0.7778
- Recall: 0.2800
- Valuable candidate rate: 0.6667
- Generic relation rate: 0.1111
- Agent-completed cases: 0/30
- Fallback or unavailable cases: 30/30
- Invalid strict-agent cases: 30/30
- Fallback trusted count in PR-1 route regression: 0
- Fallback trusted count in same-key deterministic signal enrichment
  regression: 0

Safety invariant added or tightened:

Candidate extraction diagnostics now explicitly emit:

```python
agent_extraction_completed = llm_candidate_status == "completed"
fallback_output_used = (
    llm_candidate_status
    in {"llm_empty", "fallback", "fallback_error", "unavailable"}
    or fallback_candidate_count > 0
)
trusted_evidence_eligible = agent_extraction_completed and not fallback_output_used
```

Document extraction proposals inherit the same three trust flags before
persistence. A regression test proves a fallback-created proposal carries
`trusted_evidence_eligible=False`.

Variant-aware extraction now also fails closed when deterministic genomics
signals contribute to proposal material. Same-key signal enrichment, signal-only
generated output, unmatched deterministic signal variants, review item nested
proposal payloads, route responses, and research-init persistence all have
regression coverage.

Known remaining risk:

The strict audit remains RED because no local agent run completed. PR-1 does
not improve extraction quality; it prevents fallback output from being labeled
as trusted evidence while later PRs add grounding, entailment, entity linking,
and trust-tier floors.

Reviewer/adversarial notes:

- Initial adversarial verdicts: BLOCK. Issues found in variant-aware routes,
  research-init persistence, signal-only generated output, review item
  conversion, unmatched deterministic signal variants, and same-key deterministic
  signal enrichment.
- Final adversarial verdict: PASS. Reviewer found no remaining route,
  research-init, nested-review, unmatched-signal, or same-key signal-enrichment
  path where deterministic signal output is credited as trusted evidence.

### 2026-07-02 - PR-2 Grounding Gate

PR: PR-2 grounding gate

Branch: planned `alvaro/evidence-pr2-grounding-gate`; currently stacked in
worktree branch `alvaro/evidence-pr0-quality-harness` until PR-0 and PR-1 are
split.

Goal: Add deterministic sentence anchoring and subject/object presence checks,
then make AI-authored graph claims fail closed when structured grounding is
missing or incomplete.

Changed files:

- `services/artana_evidence_api/document_extraction_support/evidence_grounding.py`
- `services/artana_evidence_api/document_extraction_drafts.py`
- `services/artana_evidence_api/tests/unit/test_evidence_grounding.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `services/artana_evidence_db/validation/claim_ai_evidence_validation.py`
- `services/artana_evidence_db/validation/__init__.py`
- `services/artana_evidence_db/graph_validation_service.py`
- `services/artana_evidence_db/routers/relations.py`
- `services/artana_evidence_db/routers/claims.py`
- `services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py`
- `services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py`
- `tests/e2e/artana_evidence_api/test_live_graph_promotion.py`
- `scripts/validation/relation_feasibility/models.py`
- `scripts/validation/relation_feasibility/scoring.py`
- `scripts/validation/relation_feasibility/reporting.py`
- `scripts/validation/relation_feasibility/adversarial.py`
- `tests/unit/test_relation_feasibility_audit.py`
- `docs/validation/reports/2026-07-02-pr2-grounding-gate-summary.md`
- `docs/validation/reports/2026-07-02-pr2-grounding-gate-summary.json`

Tests run:

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_grounding.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  tests/unit/test_relation_feasibility_audit.py \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py::test_graph_service_ai_claim_requires_structured_grounding \
  -q
```

Result: 69 passed.

After adversarial review found the canonical relation bypass, this focused
graph regression set was added and run:

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py::test_graph_service_ai_claim_requires_structured_grounding \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py::test_graph_service_create_relation_rejects_ai_generated_ungrounded_evidence \
  -q
```

Result: 8 passed.

```bash
uv run --python python3.13 \
  --with ruff ruff check <PR-2 touched Python files>
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Static checks, OpenAPI contract check, architecture size and
structure checks, migrations, and isolated Postgres Evidence API tests
completed.

```bash
make graph-service-checks
```

Result: passed before and after the adversarial bypass fix. Static checks, type
checks, boundary check, OpenAPI and TypeScript contract checks, graph release
contract, architecture checks, migrations, and isolated Postgres graph tests
completed.

```bash
make service-checks
```

Result: passed. Aggregate service gate completed with coverage 86.83% against
the 86% requirement. A final aggregate rerun after the adversarial bypass fix
initially failed because the live graph promotion e2e fixture was missing the
new required `metadata.evidence_grounding`; after updating the fixture, the
aggregate gate passed in the migrated Postgres service-check environment.

Architecture note:

The first service-gate run caught the right failure: adding root modules pushed
both services over their root-module budgets and the graph validator over its
file-size budget. The fix was structural, not an override:

- API grounding logic moved under `document_extraction_support`.
- Graph AI provenance/grounding logic moved under `validation`.
- `graph_validation_service.py` dropped from 1202 to 1109 lines.
- Architecture size and structure guards now pass.

Audit command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-02-pr2-grounding-gate-agent-strict
```

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-02-pr2-grounding-gate-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-02-pr2-grounding-gate-summary.json`
- Local full report:
  `reports/relation_feasibility/2026-07-02-pr2-grounding-gate-agent-strict/relation_feasibility_report.md`
- Local full JSON:
  `reports/relation_feasibility/2026-07-02-pr2-grounding-gate-agent-strict/relation_feasibility_report.json`

After metrics:

- Verdict: RED
- Precision: 0.7778
- Recall: 0.2800
- Valuable candidate rate: 0.6667
- Generic relation rate: 0.1111
- Grounded sentence rate: 1.0000
- Both-arguments-present count: 9
- Both-arguments-present rate: 1.0000
- Gold support sentence alignment rate: 0.7778
- Agent-completed cases: 0/30
- Fallback or unavailable cases: 30/30
- Invalid strict-agent cases: 30/30
- Fallback candidates that would look valuable: 6
- Adversarial findings: `fallback_only_report`,
  `fallback_candidates_look_valuable`, `entailment_not_checked`,
  `generic_relation_rate_high`

Safety invariant added or tightened:

Document extraction proposals now include `metadata.evidence_grounding` with
sentence anchor offsets, match kind, match score, subject presence, object
presence, and the final `grounded` boolean. The audit only counts a relation as
valuable if its evidence sentence is anchored and contains both relation
arguments.

AI-authored graph claims for evidence-requiring relation types now fail closed
unless `metadata.evidence_grounding` has:

```json
{
  "grounded": true,
  "subject_present": true,
  "object_present": true
}
```

The claim creation route returns HTTP 400 for AI-authored
`insufficient_evidence` validation results instead of persisting an ungrounded
claim.

The same hard floor now applies to canonical relation creation. `POST
/relations` validates AI-authored relation-create requests after ordinary
triple validation and before it creates the resolved claim or materializes a
canonical relation. The regression test uses `evidence_sentence_source` set to
`artana_generated` with `object_present=false` and expects HTTP 400.

Known remaining risk:

The strict audit remains RED because no local agent run completed. PR-2 proves
the grounding gate exists and fails closed, but it still cannot prove live
agent extraction quality. It also does not verify relation entailment; that is
PR-3.

Reviewer/adversarial notes:

- Built-in adversarial report now correctly flags `entailment_not_checked`
  rather than the old substring-only warning.
- Independent adversarial review initially returned BLOCK. The blocking finding
  was that canonical relation promotion could bypass the PR-2 hard floor via
  `POST /relations`.
- Fix: the shared AI evidence validator now accepts both claim-create and
  relation-create requests, and `POST /relations` calls
  `validate_ai_authored_relation_request` before persistence.
- Final adversarial re-review verdict: PASS.
- Remaining non-blocking risk: direct `POST /relations` writes still depend on
  AI markers because `KernelRelationCreateRequest` has no `agent_run_id` or
  `ai_provenance` field. Proposal promotion sets
  `evidence_sentence_source=artana_generated`, so the reviewed bypass is
  covered.

### 2026-07-02 - PR-3 Entailment Verifier

PR: PR-3 entailment verifier

Branch: planned `alvaro/evidence-pr3-entailment-verifier`; currently stacked
in worktree branch `alvaro/evidence-pr0-quality-harness` until PR-0 through
PR-2 are split.

Goal: Add fail-closed support verification for grounded triples so a
co-mentioned sentence is not enough to count as valuable or trusted evidence.

Changed files:

- `services/artana_evidence_api/document_extraction_support/evidence_support_verifier.py`
- `services/artana_evidence_api/document_extraction_drafts.py`
- `services/artana_evidence_api/proposal_actions.py`
- `services/artana_evidence_db/validation/claim_ai_evidence_validation.py`
- `services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `services/artana_evidence_api/tests/unit/test_proposal_actions.py`
- `services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py`
- `services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py`
- `tests/e2e/artana_evidence_api/test_live_graph_promotion.py`
- `scripts/validation/relation_feasibility/models.py`
- `scripts/validation/relation_feasibility/scoring.py`
- `scripts/validation/relation_feasibility/reporting.py`
- `scripts/validation/relation_feasibility/adversarial.py`
- `tests/unit/test_relation_feasibility_audit.py`
- `docs/validation/reports/2026-07-02-pr3-entailment-verifier-summary.md`
- `docs/validation/reports/2026-07-02-pr3-entailment-verifier-summary.json`

Tests run:

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py -q
```

Result: 7 passed.

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_document_extraction_modules.py -q
```

Result: 52 passed.

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_proposal_actions.py -q
```

Result: 22 passed.

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest tests/unit/test_relation_feasibility_audit.py -q
```

Result: 15 passed.

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py -q
```

Result: 8 passed.

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py::test_graph_service_ai_claim_requires_structured_grounding \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py::test_graph_service_ai_claim_requires_entailing_support_verification \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py::test_graph_service_create_relation_rejects_ai_generated_ungrounded_evidence \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py::test_graph_service_create_relation_rejects_ai_generated_non_entailing_support \
  -q
```

Result: 4 passed.

```bash
uv run --python python3.13 \
  --with ruff ruff check <PR-3 touched Python files>
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Static checks, type checks, boundary check, OpenAPI contract
check, architecture checks, migrations, and isolated Postgres Evidence API
tests completed.

```bash
make graph-service-checks
```

Result: passed. Static checks, type checks, boundary check, OpenAPI and
TypeScript contract checks, release contract, architecture checks, migrations,
and isolated Postgres graph tests completed.

```bash
make service-checks
```

Result: passed. Aggregate service gate completed with coverage 86.83% against
the 86% requirement.

Audit command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-02-pr3-entailment-verifier-agent-strict
```

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-02-pr3-entailment-verifier-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-02-pr3-entailment-verifier-summary.json`
- Local full report:
  `reports/relation_feasibility/2026-07-02-pr3-entailment-verifier-agent-strict/relation_feasibility_report.md`
- Local full JSON:
  `reports/relation_feasibility/2026-07-02-pr3-entailment-verifier-agent-strict/relation_feasibility_report.json`

After metrics:

- Verdict: RED
- Precision: 0.7778
- Recall: 0.2800
- Valuable candidate rate: 0.6667
- Generic relation rate: 0.1111
- Grounded sentence rate: 1.0000
- Both-arguments-present count: 9
- Both-arguments-present rate: 1.0000
- Gold support sentence alignment rate: 0.7778
- Entailment required count: 8
- Entailment checked count: 8
- Entailment supported count: 8
- Entailment checked rate: 1.0000
- Entailment supported rate: 1.0000
- Agent-completed cases: 0/30
- Fallback or unavailable cases: 30/30
- Invalid strict-agent cases: 30/30
- Fallback candidates that would look valuable: 6
- Adversarial findings: `fallback_only_report`,
  `generic_relation_rate_high`

Safety invariant added or tightened:

Grounded document-extraction relation proposals now carry
`metadata.support_verification` with one of `ENTAILS`, `NEUTRAL`, or
`CONTRADICTS`. Model-backed verifier exceptions fail closed to `NEUTRAL`.
The heuristic verifier is direction-aware for directional relations: reversed
active evidence is `NEUTRAL`, not `ENTAILS`. Passive cue spans are kept on the
passive path so `EGFR is activated by MED13` supports `MED13 ACTIVATES EGFR`
but not the reversed `EGFR ACTIVATES MED13`.

Ungrounded candidates omit `metadata.support_verification`; a skipped support
check is no longer encoded as a completed `NEUTRAL` check.

Contradicted support floors proposal confidence and ranking to `0.1` and adds
`metadata.support_verification_floor="contradiction"`. Candidate extraction
trust metadata now requires `support_verification.support == "ENTAILS"` before
`trusted_evidence_eligible` can remain true.

The graph service now rejects AI-authored evidence-requiring claim and
canonical relation writes unless `metadata.support_verification.support ==
"ENTAILS"`. This moves support verification from advisory proposal metadata
to a persistence-boundary invariant.

Promotion request metadata is filtered before graph claim or canonical relation
requests are built. Reviewer-supplied metadata cannot overwrite verifier-owned
`evidence_grounding`, `support_verification`, support floors, fallback flags,
or trust flags.

The feasibility audit now records entailment required, checked, and supported
counts/rates. Required candidates are valuable only when support verification
returns `ENTAILS`.

Known remaining risk:

The strict audit remains RED because no local agent run completed. PR-3 proves
the support-verification gate exists and fails closed, but it still cannot prove
live agent extraction quality. The verifier in this slice is conservative and
deterministic unless a model adapter is supplied; later PRs still need relation
type hardening, specificity pruning, entity linking, calibrated scoring, and
trust-tier hard floors.

Reviewer/adversarial notes:

- Built-in adversarial reporting no longer emits `entailment_not_checked` when
  all required candidates were actually checked.
- Independent adversarial review initially returned BLOCK. The blocking
  findings were role-blind reversed-direction support, support metadata
  attached when grounding failed, and no graph-boundary hard floor for
  entailing support.
- Fix: direction-aware support verification, no support metadata on failed
  grounding, and graph AI evidence validation requiring `support=ENTAILS` for
  claim and canonical relation writes.
- Re-review returned BLOCK for passive-direction reversal and promotion
  metadata override. Fix: passive cue spans cannot take the active path, and
  promotion request metadata is filtered for verifier-owned fields.
- Final adversarial re-review verdict: PASS. Remaining risk is non-blocking:
  the verifier is still deterministic and heuristic unless a model adapter is
  supplied, so broader semantic nuance remains a later quality problem.
- The strict report still flags `fallback_only_report` and
  `generic_relation_rate_high`, which is correct: fallback-only output is not
  agent quality, and over-generalization is still above the target.

### 2026-07-03 - PR-4 Relation-Type Hardening

PR: PR-4 relation-type hardening

Branch: planned `alvaro/evidence-pr4-relation-type-hardening`; currently
stacked in worktree branch `alvaro/evidence-pr0-quality-harness` until earlier
PR slices are split.

Goal: Constrain LLM relation extraction to canonical types or an explicit
new-type proposal channel, and make resolver/legacy validation failures fail
closed instead of preserving raw relation types.

Changed files:

- `services/artana_evidence_api/document_extraction_relation_taxonomy.py`
- `services/artana_evidence_api/document_extraction_prompting.py`
- `services/artana_evidence_api/document_extraction_contracts.py`
- `services/artana_evidence_api/document_extraction.py`
- `services/artana_evidence_api/document_extraction_drafts.py`
- `services/artana_evidence_api/document_extraction_support/proposal_relation_type_guard.py`
- `services/artana_evidence_api/proposal_store.py`
- `services/artana_evidence_api/relation_type_resolver.py`
- `services/artana_evidence_api/graph_integration/preflight.py`
- `services/artana_evidence_api/routers/review_queue.py`
- `services/artana_evidence_api/variant_aware_document_extraction.py`
- `services/artana_evidence_api/tests/support.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `services/artana_evidence_api/tests/unit/test_graph_client.py`
- `services/artana_evidence_api/tests/unit/test_proposal_actions.py`
- `services/artana_evidence_api/tests/unit/test_proposals_router.py`
- `services/artana_evidence_api/tests/unit/test_relation_type_resolver.py`
- `services/artana_evidence_api/tests/unit/test_app.py`
- `services/artana_evidence_api/tests/unit/test_proposal_store.py`
- `services/artana_evidence_api/tests/unit/test_review_queue_router.py`
- `services/artana_evidence_api/tests/unit/test_sqlalchemy_stores.py`
- `services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py`
- `services/artana_evidence_db/routers/claims.py`
- `services/artana_evidence_db/tests/support.py`
- `services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py`
- `scripts/run_relation_feasibility_audit.py`
- `scripts/validation/relation_feasibility/models.py`
- `scripts/validation/relation_feasibility/runner.py`
- `scripts/validation/relation_feasibility/scoring.py`
- `scripts/validation/relation_feasibility/reporting.py`
- `scripts/validation/relation_feasibility/adversarial.py`
- `tests/unit/test_relation_feasibility_audit.py`
- `docs/validation/reports/2026-07-03-pr4-relation-type-hardening-summary.md`
- `docs/validation/reports/2026-07-03-pr4-relation-type-hardening-summary.json`

Tests run:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_schema_rejects_raw_unknown_relation_type \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_schema_accepts_structured_new_relation_proposal \
  services/artana_evidence_api/tests/unit/test_relation_type_resolver.py::TestRelationAgentFallback::test_agent_failure_requires_review_without_registering_raw_type \
  services/artana_evidence_api/tests/unit/test_graph_client.py::test_legacy_relation_validation_fails_closed_for_relation_writes \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_skips_structured_new_type_proposals \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_filters_review_required_raw_types \
  -q
```

Result: 6 passed after RED/GREEN.

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_relation_type_resolver.py \
  services/artana_evidence_api/tests/unit/test_graph_client.py \
  -q
```

Result: passed.

Post-adversarial graph and API boundary regressions:

```bash
uv run pytest \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py::test_graph_service_create_claim_rejects_unknown_relation_type \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_preserves_decomposed_mechanism_claims \
  services/artana_evidence_api/tests/unit/test_graph_client.py::test_create_claim_blocks_missing_relation_type_without_side_effects \
  services/artana_evidence_api/tests/unit/test_graph_client.py::test_create_claim_dictionary_fetch_failure_blocks_without_side_effects \
  services/artana_evidence_api/tests/unit/test_graph_client.py::test_create_relation_blocks_missing_relation_type_without_side_effects \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_skips_raw_unknown_relation_types \
  -q
```

Result: 7 passed.

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_graph_client.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

Result: 124 passed.

```bash
uv run pytest \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py \
  -q
```

Result: 38 passed. The standalone graph fixture now includes reasoning-path
tables because claim mutations invalidate reasoning paths.

Post-re-review rejected relation and proposal-store regressions:

```bash
uv run pytest \
  tests/unit/test_relation_feasibility_audit.py \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_promotes_strong_rejected_relations_to_review_items \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_canonicalizes_rejected_relation_review_items \
  services/artana_evidence_api/tests/unit/test_review_queue_router.py::test_review_queue_action_rejects_raw_unknown_candidate_claim_conversion \
  services/artana_evidence_api/tests/unit/test_proposal_store.py::test_in_memory_harness_proposal_store_rejects_raw_unknown_candidate_claim_type \
  services/artana_evidence_api/tests/unit/test_proposal_store.py::test_in_memory_harness_proposal_store_canonicalizes_candidate_claim_type \
  services/artana_evidence_api/tests/unit/test_proposal_store.py::test_in_memory_harness_proposal_store_migrates_legacy_relation_type_key \
  services/artana_evidence_api/tests/unit/test_proposal_store.py::test_in_memory_harness_proposal_store_maps_legacy_suggests_relation \
  services/artana_evidence_api/tests/unit/test_sqlalchemy_stores.py::test_sqlalchemy_harness_proposal_store_rejects_raw_unknown_candidate_claim_type \
  services/artana_evidence_api/tests/unit/test_sqlalchemy_stores.py::test_sqlalchemy_harness_proposal_store_canonicalizes_candidate_claim_type \
  services/artana_evidence_api/tests/unit/test_sqlalchemy_stores.py::test_sqlalchemy_harness_proposal_store_migrates_legacy_relation_type_key \
  services/artana_evidence_api/tests/unit/test_sqlalchemy_stores.py::test_sqlalchemy_harness_proposal_store_maps_legacy_suggests_relation \
  -q
```

Result: 28 passed.

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_review_queue_router.py \
  services/artana_evidence_api/tests/unit/test_proposal_store.py \
  services/artana_evidence_api/tests/unit/test_sqlalchemy_stores.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

Result: 87 passed.

```bash
uv run pytest tests/unit/test_relation_feasibility_audit.py -q
```

Result: 17 passed.

```bash
uv run ruff check <PR-4 touched files>
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Static checks, type checks, boundary check, OpenAPI contract
check, architecture checks, migrations, isolated Postgres tests, and cleanup
completed after the final proposal-store compatibility fixes. Earlier runs
caught two correct compatibility gaps: flat test gateways without validation
authority failed after legacy validation became fail-closed, and legacy
proposal payloads using `relation_type`, `proposed_relation`, or `SUGGESTS`
needed governed migration before persistence.

```bash
make graph-service-checks
```

Result: passed. Static checks, type checks, boundary check, OpenAPI and
TypeScript contract checks, release contract, architecture checks, migrations,
and isolated Postgres graph tests completed. The graph `/claims` route now
rejects unknown relation types before persistence while known review-only
claims remain queryable and cannot promote.

```bash
make service-checks
```

Result: passed with captured exit code 0. The aggregate service gate completed
static, type, boundary, contract, architecture, migration, and isolated
Postgres coverage checks across both services. Coverage was 86.83% against the
86% floor, and the ephemeral database was dropped at cleanup.

Audit command:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-03-pr4-relation-type-hardening-agent-strict
```

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-03-pr4-relation-type-hardening-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-03-pr4-relation-type-hardening-summary.json`
- Local full report:
  `reports/relation_feasibility/2026-07-03-pr4-relation-type-hardening-agent-strict/relation_feasibility_report.md`
- Local full JSON:
  `reports/relation_feasibility/2026-07-03-pr4-relation-type-hardening-agent-strict/relation_feasibility_report.json`

After metrics:

- Verdict: RED
- Precision: 0.7778
- Recall: 0.2800
- Valuable candidate rate: 0.6667
- Generic relation rate: 0.1111
- Raw unknown relation type count: 0
- Raw unknown relation type rate: 0.0000
- Relation type inventory surfaces: 9
- Raw unknown inventory relation type count: 0
- Raw unknown inventory relation type rate: 0.0000
- Agent-completed cases: 0/30
- Fallback or unavailable cases: 30/30
- Invalid strict-agent cases: 30/30
- Entailment checked rate: 1.0000
- Entailment supported rate: 1.0000

Safety invariant added or tightened:

The LLM extraction schema now accepts only canonical relation types or the
explicit `PROPOSE_NEW_RELATION_TYPE` sentinel. New relation proposals must use
`proposed_relation_type` plus `new_relation_type_rationale`; raw new types in
`relation_type` are schema errors.

Structured new relation proposals are skipped by normal candidate creation.
Malformed or legacy raw types that reach resolver decisions are kept only when
the resolver maps or typo-corrects them to an existing type. `requires_review`
and `register_new` decisions remove the candidate from normal extraction
output.

Resolver agent failure now returns `requires_review`, not `register_new`.
Legacy flat graph gateways without validation no longer silently permit
relation writes; success paths must expose validation authority, and unknown
legacy relation writes become non-persistable review/block paths.

The feasibility audit now records `raw_unknown_relation_type_count` and
`raw_unknown_relation_type_rate` for extracted candidates and
`raw_unknown_relation_type_surface_count` for supplied relation-type inventory
surfaces. Any surviving raw unknown candidate or review/proposal/graph/
dictionary surface type is a RED quality issue and an adversarial finding.

Rejected-relation review items now canonicalize relation types before creating
nested proposal drafts. Raw unknown rejected relation labels stay skipped as
review/audit material instead of becoming normal `candidate_claim` proposal
payloads.

Candidate-claim proposal persistence now uses a shared relation-type guard in
both in-memory and SQLAlchemy stores. Known synonyms such as `AFFECTS` are
canonicalized to `MODULATES`; raw unknown relation labels such as
`PROTECTS_AGAINST` are rejected before persistence. Review-queue conversion
turns legacy raw unknown nested proposal payloads into 409 conflicts.

Known remaining risk:

The strict audit remains RED because no local agent run completed. PR-4 closes
raw relation-type leakage and makes the gate measurable, but it still cannot
prove live agent extraction quality. Relation over-generalization remains above
target and is PR-5's scope.

Reviewer/adversarial notes:

- Built-in adversarial report still flags `fallback_only_report`,
  `fallback_candidates_look_valuable`, and `generic_relation_rate_high`, which
  is correct for a local fallback-only strict run.
- External adversarial review initially returned BLOCK. Issues found:
  graph `/claims` persisted raw unknown relation types, variant-aware extraction
  accepted raw relation labels into normal claim staging, preflight
  auto-submitted relation-type dictionary proposals as a write side effect, and
  the audit raw-unknown metric did not cover all relevant surfaces.
- Fixes added: graph claim unknown-type rejection before persistence, shared
  canonicalization for draft and variant-aware extraction, defensive skip of
  `PROPOSE_NEW_RELATION_TYPE` in normal drafts, no automatic dictionary
  proposal command on raw unknown graph writes, and broader regression tests.
- External adversarial re-review returned BLOCK for one remaining side door:
  supported rejected-relation review items could still carry raw relation types
  into nested `candidate_claim` proposal drafts, and the audit raw-unknown
  metric was candidate-only.
- Fix: rejected-relation review items canonicalize or skip relation labels,
  proposal stores reject raw unknown candidate-claim relation types, review
  conversion fails closed on legacy raw unknown nested payloads, and the audit
  contract now scores supplied relation-type inventory surfaces.
- Final compatibility fix: legacy proposal payloads using `relation_type`,
  `proposed_relation`, or the old `SUGGESTS` placeholder are migrated to
  governed `proposed_claim_type` values before persistence.
- External adversarial final re-review: PASS. Reviewer caveat: the strict audit
  currently populates candidate relation-type inventory surfaces; proposal,
  graph, and dictionary surfaces are covered by boundary tests until a real
  live-agent inventory artifact exists.

### 2026-07-03 - PR-5 Specificity Pruning

PR: PR-5 specificity pruning

Branch: planned `alvaro/evidence-pr5-specificity-pruning`; currently stacked
in worktree branch `alvaro/evidence-pr0-quality-harness` until earlier PR
slices are split.

Goal: Suppress redundant generic siblings and weak generic relation probes
before they can inflate the candidate set or reviewer queue.

Changed files:

- `services/artana_evidence_api/document_extraction.py`
- `services/artana_evidence_api/document_extraction_contracts.py`
- `services/artana_evidence_api/document_extraction_diagnostics.py`
- `services/artana_evidence_api/document_extraction_drafts.py`
- `services/artana_evidence_api/document_extraction_prompting.py`
- `services/artana_evidence_api/document_extraction_support/relation_specificity_pruning.py`
- `scripts/run_relation_feasibility_audit.py`
- `scripts/validation/relation_feasibility/models.py`
- `scripts/validation/relation_feasibility/scoring.py`
- `scripts/validation/relation_feasibility/reporting.py`
- `tests/unit/test_relation_feasibility_audit.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `docs/validation/reports/2026-07-03-pr5-specificity-pruning-summary.md`
- `docs/validation/reports/2026-07-03-pr5-specificity-pruning-summary.json`

Tests run:

```bash
uv run pytest \
  tests/unit/test_relation_feasibility_audit.py::test_audit_counts_pruned_generic_relation_siblings \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_prunes_redundant_generic_siblings \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_prunes_redundant_generic_relation_siblings \
  -q
```

Result: failed before implementation, then passed after adding the shared
specificity-pruning helper and draft/extraction guards.

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_suppresses_weak_generic_correlations \
  -q
```

Result: failed before implementation, then passed after suppressing weak
exploratory generic correlations.

```bash
uv run pytest \
  tests/unit/test_relation_feasibility_audit.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  -q
```

Result: passed.

```bash
uv run ruff check <PR-5 touched files>
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed. The first run correctly failed `architecture_size` because the
initial edit pushed `document_extraction.py` to 1212 lines. The weak generic
predicate moved into `document_extraction_support/relation_specificity_pruning.py`;
the rerun passed with `document_extraction.py` under the 1200-line budget. A
later adversarial fix briefly pushed the file back over budget; removing the
local wrapper and keeping telemetry support in the helper module brought it to
1197 lines and the final service-check run passed.

```bash
make service-checks
```

Result: passed with total coverage 86.83%. The broad gate completed graph
static/type/boundary/contract checks, graph release-contract alignment, Evidence
API static/type/boundary/OpenAPI/architecture checks, Alembic migration setup on
an ephemeral Postgres database, and the full pytest suite. Live external API,
running-service, and OpenAI-key integration tests remained explicitly skipped.

Audit commands:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor deterministic \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-03-pr5-specificity-pruning-deterministic
```

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-03-pr5-specificity-pruning-agent-strict
```

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-03-pr5-specificity-pruning-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-03-pr5-specificity-pruning-summary.json`
- Local strict-agent report:
  `reports/relation_feasibility/2026-07-03-pr5-specificity-pruning-agent-strict/relation_feasibility_report.md`
- Local deterministic report:
  `reports/relation_feasibility/2026-07-03-pr5-specificity-pruning-deterministic/relation_feasibility_report.md`

After metrics:

- Strict-agent verdict: RED
- Strict-agent invalid cases: 30/30
- Strict-agent generic relation rate: 0.0000
- Strict-agent fallback candidates that would look valuable: 6
- Deterministic verdict: YELLOW
- Deterministic precision: 0.7500
- Deterministic recall: 0.2400
- Deterministic valuable candidate rate: 0.7500
- Deterministic generic relation rate: 0.0000

Safety invariant added or tightened:

`ASSOCIATED_WITH` is now treated as a fallback relation type, not a peer to
specific mechanisms. Generic candidates are pruned when the same normalized
subject/object pair has a canonical specific sibling. Weak exploratory generic
correlations are suppressed before staging. The prompt now tells the LLM to
output only the specific mechanism when one sentence supports both a generic
association and a specific relation.

Known remaining risk:

The strict audit remains RED because no local agent run completed. PR-5 proves
that local fallback/triage output no longer exceeds the generic-rate target,
but it still cannot prove live-agent relation specificity.

Reviewer/adversarial notes:

- Built-in adversarial reporting no longer flags `generic_relation_rate_high`
  for the PR-5 audit snapshots because generic relation rate is 0.0000.
- Independent adversarial review initially returned BLOCK. Issues found:
  weak exploratory generic LLM candidates could still become staged drafts, and
  LLM generic-sibling pruning telemetry was dropped before audit diagnostics.
- Fixes added: weak generic candidates are suppressed by the shared specificity
  filter and at draft assembly, `discover_relation_candidates` preserves
  pruned-generic telemetry, and research-init test fakes now use typed
  `ExtractedRelationCandidate` payloads.
- Independent adversarial re-review: PASS.

### 2026-07-03 - PR-6 CURIE Entity Linking

PR: PR-6 CURIE entity linking

Branch: planned `alvaro/evidence-pr6-curie-entity-linking`; currently stacked
in worktree branch `alvaro/evidence-pr0-quality-harness` until earlier PR
slices are split.

Goal: Add agent-supplied entity CURIE support, validate/abstain on unsafe
identifier claims, propagate linked identifiers into graph entity creation
payloads, and measure CURIE-linked gold endpoint coverage.

Changed files:

- `services/artana_evidence_api/document_extraction.py`
- `services/artana_evidence_api/document_extraction_contracts.py`
- `services/artana_evidence_api/document_extraction_drafts.py`
- `services/artana_evidence_api/document_extraction_prompting.py`
- `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- `services/artana_evidence_api/document_extraction_support/relation_resolution_decisions.py`
- `scripts/run_relation_feasibility_audit.py`
- `scripts/validation/relation_feasibility/models.py`
- `scripts/validation/relation_feasibility/scoring.py`
- `scripts/validation/relation_feasibility/runner.py`
- `scripts/validation/relation_feasibility/reporting.py`
- `tests/unit/test_relation_feasibility_audit.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `docs/validation/reports/2026-07-03-pr6-curie-linking-summary.md`
- `docs/validation/reports/2026-07-03-pr6-curie-linking-summary.json`

Tests run:

```bash
uv run pytest \
  tests/unit/test_relation_feasibility_audit.py::test_audit_requires_curie_linked_gold_entities \
  tests/unit/test_relation_feasibility_audit.py::test_audit_turns_red_when_gold_curie_endpoints_are_missing \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_prompt_schema_builders_validate_structured_outputs \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_propagates_curie_identifiers_for_graph_entity_creation \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_preserves_valid_curies_and_abstains_invalid \
  -q
```

Result: failed before implementation, then passed after adding CURIE candidate
fields, normalization/abstention, draft identifier propagation, and audit
metrics.

```bash
uv run pytest \
  tests/unit/test_relation_feasibility_audit.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_proposal_actions.py \
  -q
```

Result: passed.

```bash
uv run ruff check <PR-6 touched files>
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Live external API, running-service, and OpenAI-key integration
tests remained explicitly skipped.

Audit commands:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor deterministic \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-03-pr6-curie-linking-deterministic
```

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-03-pr6-curie-linking-agent-strict
```

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-03-pr6-curie-linking-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-03-pr6-curie-linking-summary.json`
- Local strict-agent report:
  `reports/relation_feasibility/2026-07-03-pr6-curie-linking-agent-strict/relation_feasibility_report.md`
- Local deterministic report:
  `reports/relation_feasibility/2026-07-03-pr6-curie-linking-deterministic/relation_feasibility_report.md`

After metrics:

- Strict-agent verdict: RED
- Strict-agent invalid cases: 30/30
- Strict-agent gold CURIE endpoints: 37
- Strict-agent candidate CURIE endpoints: 0
- Strict-agent CURIE-linked gold endpoint rate: 0.0000
- Deterministic verdict: RED
- Deterministic gold CURIE endpoints: 37
- Deterministic candidate CURIE endpoints: 0
- Deterministic CURIE-linked gold endpoint rate: 0.0000

Safety invariant added or tightened:

Entity identity is now explicit. LLM extraction may provide endpoint CURIEs,
but unsupported prefixes, malformed CURIEs, and obvious label/type mismatches
are treated as abstentions. Draft promotion can now carry validated identifiers
into graph entity creation instead of creating label-only nodes when the agent
provided a safe identifier.

Known remaining risk:

The strict primary gate remains RED locally. PR-6 adds the capability and the
measurement, but it does not prove live-agent identity-linking quality until an
agent extraction run completes and reaches `curie_linked_gold_endpoint_rate >=
0.95`.

Reviewer/adversarial notes:

- Deterministic fallback is explicitly RED for PR-6 because it has zero
  CURIE-linked gold endpoints.
- Strict-agent remains RED because no local agent cases completed; this
  continues to prevent fallback from being credited as agent evidence quality.

### 2026-07-03 - PR-7 Evidence-Aware Scoring

PR: PR-7 evidence-aware scoring

Branch: planned `alvaro/evidence-pr7-evidence-aware-scoring`; currently
stacked in worktree branch `alvaro/evidence-pr0-quality-harness` until earlier
PR slices are split.

Goal: Make proposal ranking evidence-aware so specific grounded claims outrank
generic or unsupported claims even when review labels are otherwise identical.

Changed files:

- `services/artana_evidence_api/ranking.py`
- `services/artana_evidence_api/document_extraction_review.py`
- `services/artana_evidence_api/tests/unit/test_ranking.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `docs/validation/reports/2026-07-03-pr7-evidence-aware-scoring-summary.md`
- `docs/validation/reports/2026-07-03-pr7-evidence-aware-scoring-summary.json`

Tests run:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_ranking.py::test_rank_reviewed_candidate_claim_rewards_grounded_entailed_specific_evidence \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_review_helpers_rank_specific_grounded_entailed_claim_above_generic_ungrounded_claim \
  -q
```

Result: failed before implementation, then passed after adding evidence-quality
ranking inputs and feeding draft metadata into reviewed proposal ranking.

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_ranking.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  -q
```

Result: passed.

```bash
uv run ruff check <PR-7 touched files>
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Live external API, running-service, and OpenAI-key integration
tests remained explicitly skipped.

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-03-pr7-evidence-aware-scoring-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-03-pr7-evidence-aware-scoring-summary.json`

After metrics:

- Specific grounded entailed claim score: 0.9220
- Generic ungrounded unentailed claim score: 0.7220
- Strong evidence-quality component: 1.0000
- Weak evidence-quality component: 0.0000

Safety invariant added or tightened:

Review labels alone no longer determine document-extraction proposal ordering.
Grounding, argument presence, entailment support, and relation specificity are
first-class ranking components.

Known remaining risk:

This slice improves ranking after candidates exist. It does not prove live-agent
extraction quality, CURIE linking, or trusted-tier precision by itself.

Reviewer/adversarial notes:

- The RED/GREEN tests isolate ranking by giving strong and weak drafts the same
  factual support, goal relevance, priority, document count, and evidence
  reference count.

### 2026-07-03 - PR-8 Trust Ladder Hard Floors

PR: PR-8 trust ladder hard floors

Branch: planned `alvaro/evidence-pr8-trust-ladder-hard-floors`; currently
stacked in worktree branch `alvaro/evidence-pr0-quality-harness` until earlier
slices are split.

Goal:

Add a durable trust ladder so trusted evidence is earned from hard floors, not
from caller-provided metadata or weakened configuration.

Changed files:

- `services/artana_evidence_api/document_extraction_support/trust_ladder.py`
- `services/artana_evidence_api/document_extraction_drafts.py`
- `services/artana_evidence_api/proposal_actions.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `services/artana_evidence_api/tests/unit/test_proposal_actions.py`
- `services/artana_evidence_db/validation/trusted_evidence_floor.py`
- `services/artana_evidence_db/validation/claim_ai_evidence_validation.py`
- `services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py`
- `docs/validation/reports/2026-07-03-pr8-trust-ladder-hard-floors-summary.md`
- `docs/validation/reports/2026-07-03-pr8-trust-ladder-hard-floors-summary.json`

Tests run:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_candidate_extraction_trust_requires_all_hard_floors \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_candidate_extraction_trust_marks_verified_linked_agent_relation_trusted \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py::test_ai_claim_rejects_claimed_trusted_tier_without_linked_entities \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py::test_ai_claim_rejects_claimed_trusted_tier_from_fallback_output \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py::test_ai_claim_accepts_claimed_trusted_tier_when_hard_floors_pass \
  services/artana_evidence_api/tests/unit/test_proposal_actions.py::test_build_graph_claim_request_preserves_verifier_owned_metadata \
  services/artana_evidence_api/tests/unit/test_proposal_actions.py::test_build_graph_relation_request_preserves_verifier_owned_metadata \
  -q
```

Result: failed before implementation, then passed after adding the trust ladder,
graph trusted-claim floors, and promotion metadata protections.

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_documents_router.py::test_extract_document_marks_fallback_proposals_as_not_trusted_evidence \
  services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py::test_extract_variant_aware_document_treats_same_key_signal_enrichment_as_untrusted \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
  services/artana_evidence_api/tests/unit/test_proposal_actions.py \
  -q
```

Result: passed.

```bash
uv run ruff check <PR-8 touched files>
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Live external API, running-service, and OpenAI-key integration
tests remained explicitly skipped.

```bash
make graph-service-checks
```

Result: passed.

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-03-pr8-trust-ladder-hard-floors-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-03-pr8-trust-ladder-hard-floors-summary.json`

After metrics:

- Trusted adversarial cases accepted when all hard floors pass: 1/1
- Spoofed trusted adversarial cases rejected: 2/2
- Trusted-tier precision in focused hard-floor adversarial suite: 1.00
- Promotion metadata trust-tier override successes: 0/2

Safety invariant added or tightened:

Trusted evidence now requires completed agent extraction, no fallback output,
grounded sentence evidence, subject and object present, entailing support,
canonical relation type, and linked subject/object CURIEs. Graph writes that
claim trusted status are rejected unless those hard floors are present, and
review-request metadata cannot override verifier-owned trust tier or trust-floor
failures.

Known remaining risk:

The local strict agent audit still cannot measure gold trusted-tier precision
because local agent extraction has not completed. PR-8 prevents false trusted
claims; PR-9 and live-agent evaluation still need to prove recall and gold-set
precision on real agent outputs.

Reviewer/adversarial notes:

- `trust_floor_overrides` is intentionally ignored by graph validation; a
  request that claims trusted status from fallback output is rejected anyway.
- `trusted_evidence_eligible` is now the final hard-floor result on proposal
  drafts, while `agent_extraction_completed` and `fallback_output_used` remain
  visible as diagnostics.

### 2026-07-03 - PR-9 Reproducible Full-Text Extraction

PR: PR-9 reproducible full-text extraction

Branch: planned `alvaro/evidence-pr9-reproducible-fulltext-extraction`;
currently stacked in worktree branch `alvaro/evidence-pr0-quality-harness` until
earlier slices are split.

Goal:

Remove the extraction blind spot caused by `text[:4000]`, make replay keys
depend on full text and model behavior, and expose chunk coverage in diagnostics.

Changed files:

- `services/artana_evidence_api/document_extraction.py`
- `services/artana_evidence_api/document_extraction_contracts.py`
- `services/artana_evidence_api/document_extraction_diagnostics.py`
- `services/artana_evidence_api/document_extraction_support/full_text_chunking.py`
- `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- `services/artana_evidence_api/document_extraction_support/relation_specificity_pruning.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- `docs/validation/reports/2026-07-03-pr9-reproducible-fulltext-extraction-summary.md`
- `docs/validation/reports/2026-07-03-pr9-reproducible-fulltext-extraction-summary.json`

Tests run:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_llm_extraction_step_key_uses_full_text_beyond_prefix \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_reads_beyond_first_chunk \
  -q
```

Result: failed before implementation, then passed after chunking, full-text
fingerprints, and chunk telemetry were added.

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  -q
```

Result: passed.

```bash
uv run ruff check <PR-9 touched files>
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: failed first on architecture size because `document_extraction.py`
exceeded the 1200-line budget, then passed after moving prompt/conversion logic
into `document_extraction_support/llm_fulltext_extraction.py`. Live external
API, running-service, and OpenAI-key integration tests remained explicitly
skipped.

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-03-pr9-reproducible-fulltext-extraction-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-03-pr9-reproducible-fulltext-extraction-summary.json`

After metrics:

- Documents with identical first 4000 characters but different tails produce
  different extraction step keys.
- Relations after the first chunk are extracted by the LLM path in the focused
  regression.
- Chunk telemetry is emitted as `llm_extraction_chunk_count` and
  `llm_extraction_text_char_count`.
- `document_extraction.py` is 1169 lines after the split, below the 1200-line
  architecture budget.

Safety invariant added or tightened:

LLM extraction prompts no longer truncate to the first 4000 characters. Each
model call is scoped to a sentence-aware chunk and keyed by prompt version,
model id, full normalized document fingerprint, chunk index/count, and chunk
fingerprint.

Known remaining risk:

This removes the local blind spot and replay collision, but the strict live
agent audit still needs a configured model key to measure real recall and
precision across the full gold set.

Reviewer/adversarial notes:

- The RED blind-spot test used a fake model that only returned a relation when
  the late sentence appeared in the prompt. Before PR-9, the model path returned
  `llm_empty`; after PR-9, diagnostics report `completed` with at least two
  chunks.
- The first API service-check attempt failed on architecture size. The final
  pass proves the fix respects the repository's module-size guard.

### 2026-07-03 - PR-10 CI Quality Gate

PR: PR-10 CI quality gate

Branch: planned `alvaro/evidence-pr10-ci-quality-gate`; currently stacked in
worktree branch `alvaro/evidence-pr0-quality-harness` until earlier slices are
split.

Goal:

Make relation-quality regressions visible in normal CI and local service gates.

Changed files:

- `Makefile`
- `.github/workflows/evidence-api-service-checks.yml`
- `.github/workflows/graph-service-checks.yml`
- `scripts/ci/plan_service_checks.py`
- `tests/unit/test_ci_service_check_planner.py`
- `tests/unit/test_control_files.py`
- `docs/validation/evidence-excellence-progress-tracker.md`
- `docs/superpowers/plans/2026-07-02-evidence-excellence-implementation.md`
- `docs/validation/reports/*.md`
- `docs/validation/reports/*.json`
- `docs/validation/reports/2026-07-03-pr10-ci-quality-gate-summary.md`
- `docs/validation/reports/2026-07-03-pr10-ci-quality-gate-summary.json`

Tests run:

```bash
uv run pytest \
  tests/unit/test_ci_service_check_planner.py::test_relation_feasibility_quality_code_runs_evidence_api_and_repo_control \
  tests/unit/test_control_files.py::test_relation_feasibility_quality_gate_is_part_of_service_checks \
  tests/unit/test_control_files.py::test_ci_repo_control_jobs_run_relation_feasibility_quality_tests \
  -q
```

Result: failed before implementation, then passed after CI planner, Makefile,
and workflow wiring.

```bash
make relation-feasibility-quality-gate
```

Result: passed.

```bash
uv run ruff check \
  scripts/ci/plan_service_checks.py \
  tests/unit/test_ci_service_check_planner.py \
  tests/unit/test_control_files.py
```

Result: passed.

```bash
uv run pytest \
  tests/unit/test_ci_service_check_planner.py \
  tests/unit/test_control_files.py \
  tests/unit/test_coverage_enforcement_contract.py \
  tests/unit/test_makefile_type_gate_contract.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

Result: failed first because validation docs contained machine-specific
developer-home absolute paths, then passed after replacing those paths with
portable `python3.13` command references.

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-03-pr10-ci-quality-gate-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-03-pr10-ci-quality-gate-summary.json`

After metrics:

- Relation-feasibility audit-methodology changes now trigger Evidence API and
  repo-control CI paths.
- `make service-checks` now runs `relation-feasibility-quality-gate`.
- Evidence API and graph repo-control workflow jobs now run
  `tests/unit/test_relation_feasibility_audit.py`.
- Reusable docs path hygiene scan passes with no developer-home absolute paths.

Safety invariant added or tightened:

Quality-methodology code can no longer change without running the audit
regression tests. The normal local service gate also runs the relation
feasibility quality gate.

Known remaining risk:

The CI quality gate runs deterministic unit-level audit regressions. The
strict live-agent quality audit remains opt-in until model credentials are
available.

Reviewer/adversarial notes:

- The RED planner test showed that `scripts/validation/relation_feasibility/*`
  previously produced no service gates. PR-10 routes those changes through the
  Evidence API and repo-control paths.
- Bringing the docs hygiene test into the loop exposed stale machine-specific
  command examples; those were cleaned up as part of making the gate green.

### 2026-07-03 - Final Aggregate Gate And Audit Snapshot

PR: stacked PR-5 through PR-10 implementation loop

Branch: `alvaro/evidence-pr0-quality-harness`

Goal:

Verify the complete local implementation loop and record the remaining live-agent
truth without crediting fallback as success.

Commands:

```bash
make service-checks
```

Result: passed.

- Static checks: graph service and Evidence API passed.
- Architecture checks: passed.
- New relation-feasibility quality gate: passed.
- Coverage gate: passed at 86.86% against an 86% minimum.
- Live external API, running-service, and OpenAI-key tests remained explicitly
  skipped.

```bash
uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-03-final-agent-strict
```

Result: RED.

- Agent-completed cases: 0/30
- Fallback/agent-unavailable cases: 30/30
- Invalid strict-agent cases: 30/30
- Precision against gold, fallback-only comparison: 0.7500
- Recall against gold, fallback-only comparison: 0.2400
- Generic relation rate: 0.0000
- CURIE-linked gold endpoint rate: 0.0000

```bash
uv run python scripts/run_relation_feasibility_audit.py \
  --extractor deterministic \
  --output-dir reports/relation_feasibility/2026-07-03-final-deterministic-comparison
```

Result: RED.

- Precision against gold: 0.7500
- Recall against gold: 0.2400
- Valuable candidate rate: 0.7500
- Generic relation rate: 0.0000
- CURIE-linked gold endpoint rate: 0.0000

Report artifact:

- Merge-visible snapshot:
  `docs/validation/reports/2026-07-03-final-aggregate-summary.md`
- Merge-visible JSON:
  `docs/validation/reports/2026-07-03-final-aggregate-summary.json`
- Strict agent report:
  `reports/relation_feasibility/2026-07-03-final-agent-strict/relation_feasibility_report.md`
- Deterministic comparison report:
  `reports/relation_feasibility/2026-07-03-final-deterministic-comparison/relation_feasibility_report.md`

Report hashes:

- Strict JSON:
  `32e4c619f22cc9c9cc12090332d148c9dba4b087624184f2418b3e3655337b85`
- Strict Markdown:
  `544097fb4665daa81759242333cd8e0b9e67f7c5e3de1bba712b4e4b7fb7ffb7`
- Deterministic JSON:
  `db43f21c237397462e62c569261e78484effdd9475919c0d2e9a60396ef13f29`
- Deterministic Markdown:
  `8d967de7cb7a70dd74afc0595ddd182a4db4185ee1f4a949df69503e020d4d36`

Interpretation:

The codebase now has hard gates for fallback trust, grounding, entailment,
relation typing, specificity, CURIE propagation, trust tiers, full-text chunking,
and CI regression visibility. The local truth remains that the trusted agent
goal is not proven until the agent path completes with model credentials and
recovers CURIE-linked gold endpoints.

### 2026-07-01 - Strict Agent Baseline

PR: none

Branch: current worktree

Goal: Establish whether the current agent path can be evaluated without
deterministic fallback credit.

Evidence:

- `reports/relation_feasibility/2026-07-01-agent-strict/relation_feasibility_report.md`
- `reports/relation_feasibility/2026-07-01-agent-strict/relation_feasibility_report.json`

Result:

- Verdict: RED
- Agent-completed cases: 0/6
- Fallback or unavailable cases: 6/6
- Invalid strict-agent cases: 6/6
- Blocking reason: `OPENAI_API_KEY not configured`

Interpretation:

The local environment cannot yet prove agent extraction quality because the LLM
path did not complete. This is a useful failure: the strict audit refuses to
count deterministic fallback output as agent success.

### 2026-07-01 - Deterministic Comparison

PR: none

Branch: current worktree

Goal: Compare current fallback-like deterministic extraction quality without
counting it as agent success.

Evidence:

- `reports/relation_feasibility/2026-07-01-deterministic-comparison/relation_feasibility_report.md`
- `reports/relation_feasibility/2026-07-01-deterministic-comparison/relation_feasibility_report.json`

Result:

- Verdict: YELLOW
- Precision: 0.6667
- Recall: 0.5000
- Valuable candidate rate: 0.6667
- Generic relation rate: 0.3333

Interpretation:

The deterministic path may be useful for triage, but it is not strong enough
for trusted graph construction and does not satisfy the product goal of
agent-generated evidence.

### 2026-07-02 - Code Comparison Against High-Accuracy Design

PR: none

Branch: current worktree

Goal: Compare the current repo and starter audit against the high-accuracy
design brief.

Evidence:

- Evidence sentence presence is checked in
  `services/artana_evidence_db/graph_validation_service.py`, but support is not
  verified.
- Draft evidence is copied from candidate sentences in
  `services/artana_evidence_api/document_extraction_drafts.py`.
- Review ranking in `services/artana_evidence_api/ranking.py` does not include
  relation specificity or verified grounding.
- LLM extraction relation type is still a free string in
  `services/artana_evidence_api/document_extraction_prompting.py`.
- Relation resolver can fail open in
  `services/artana_evidence_api/relation_type_resolver.py`.
- Legacy graph preflight can assume relation validation is allowed in
  `services/artana_evidence_api/graph_integration/preflight.py`.
- Auto-promotion can set `APPROVED` without `reviewed_by` in
  `services/artana_evidence_db/_relation_auto_promotion_mixin.py`.

Interpretation:

The design brief is directionally correct. The extractor may produce useful
specific candidates, but the system does not yet structurally verify grounding,
entity identity, relation specificity, calibrated scoring, or trusted-tier
safety.

### 2026-07-03 - PR2-PR8 Live Agent Remediation Pass

PR: PR2-PR8 stacked remediation pass

Branch: `alvaro/evidence-pr0-quality-harness`

Goal: Convert the strict live-agent audit from fallback/unavailable validation
into a real completed-agent quality measurement, then record the remaining
trusted-evidence blockers.

Changed areas:

- `scripts/validation/relation_feasibility/`
- `scripts/run_relation_feasibility_audit.py`
- `services/artana_evidence_api/document_extraction_prompting.py`
- `services/artana_evidence_api/document_extraction_contracts.py`
- `services/artana_evidence_api/document_extraction_support/`
- `services/artana_evidence_api/alembic/versions/024_unique_active_proposal_fingerprints.py`
- `services/artana_evidence_api/alembic/versions/018_harness_review_items.py`
- `tests/unit/test_relation_feasibility_audit.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `tests/unit/database/test_artana_evidence_api_alembic_migration_regressions.py`

Tests and gates run:

- `make setup-postgres` passed and applied migration 024.
- `make service-checks` passed with coverage 87.03% after the final
  adversarial-fix pass.
- Strict live-agent feasibility audit completed successfully.

Audit command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-03-pr8-live-agent-remediation
```

Report artifacts:

- `reports/relation_feasibility/2026-07-03-pr8-live-agent-remediation/relation_feasibility_report.md`
- `reports/relation_feasibility/2026-07-03-pr8-live-agent-remediation/relation_feasibility_report.json`
- `docs/validation/reports/2026-07-03-pr8-live-agent-remediation-summary.md`

After metrics:

| Metric | Value |
|---|---:|
| Verdict | RED |
| Agent completion rate | 30/30 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control cases | 5 |
| Negative-control empty completions | 5 |
| Negative-control leakage cases | 0 |
| Completed-agent precision | 0.6552 |
| Completed-agent recall | 0.7600 |
| High-value recall | 0.8500 |
| Low-value recall | 0.4000 |
| Completed-agent valuable rate | 0.5517 |
| Generic relation rate | 0.1379 |
| Raw unknown relation types | 0 |
| Governed proposal candidates | 2 |
| Governed proposal gold matches | 1 |
| Governed proposal-eligible recall | 0.5000 |
| Candidate CURIE present rate | 0.5690 |
| Verified CURIE match rate | 0.0000 |
| Model CURIE wrong count | 13 |
| Verified CURIE-linked gold endpoint rate | 0.0000 |

Safety invariants added or tightened:

- Empty live-agent completions are counted as valid only when internally
  consistent and fallback-free.
- Fallback/unavailable traces remain RED in strict mode.
- High-value recall is separated from low-value recall.
- New relation proposals are measured as governed proposals, not trusted graph
  edges, and are staged as separate non-trusted relation-type review proposals.
- Prompt relation types are generated from the canonical extraction taxonomy.
- Broad entity/object shortening is rejected at LLM conversion time.
- Model CURIE hints are not counted as verified gold endpoint links and cannot
  become graph identifiers unless a verified linker confirms them.
- Historical duplicate active proposal fingerprints are cleaned before the
  partial unique index is created; promoted duplicates win over pending ones,
  while multiple promoted duplicates abort for manual cleanup.

Known remaining risk:

The live agent path is now measurable and fallback-free, but not trusted-graph
ready. Verified CURIE match rate is still 0.0000, 13 model CURIE hints are
wrong against gold, precision is below 0.80, valuable rate is below 0.70, one
governed proposal-eligible relation is still missed, generic relation rate is
above target, and at least one required entailment check is still missed.

Reviewer/adversarial notes:

The live report still flags `entailment_not_checked`,
`relation_arguments_missing_from_sentence`, and `generic_relation_rate_high`.

### 2026-07-13 - Categorical Shadow-Study Contracts

Branch: `alvaro/evidence-shadow-study-categorical-contract`

Evidence report:
`docs/validation/reports/2026-07-13-pr-semantic-shadow-study-categorical-contract.md`

Progress:

- Review agents now return categorical findings, candidate-bound citations,
  and explanations; deterministic code derives numeric quality metrics.
- Selection-only studies no longer fabricate review-ranking evidence.
- Production evidence origin is explicit, and AI/synthetic review cannot pass
  the readiness gate.
- Batch reports separate all observed entries from passed production entries.
- Adversarial regressions cover contradictory overclaim declarations,
  candidate binding, and all-selection and mixed-study suites.

Remaining proof boundary:

- `real_shadow_review` is still declared, not cryptographically attested.
- Citation text and locators are not yet checked against immutable canonical
  source bytes.
- Source-manifest digests are not yet reverified by resolving artifacts at gate
  time.
- This contract work improves measurement integrity but does not change the
  latest live trusted-graph precision, linking, specificity, or entailment
  results.

### 2026-07-13 - Ranking Calibration And Authority Boundaries

Branch: `alvaro/evidence-semantic-pr5-ranking-calibration`

Evidence report:
`docs/validation/reports/2026-07-13-pr-semantic-pr5-ranking-calibration.md`

Progress:

- Operational rank, calibrated probability, retrieval ordering, and legacy
  queue confidence now have separate typed origins and responsibilities.
- Probability artifacts cannot self-assert `validated`; validation is derived
  by the held-out gate.
- Frozen calibration protocols are producer-signed and tamper-checked.
- The fitter rejects held-out leakage and training-set digest drift.
- Retrieval-only ranking cannot authorize proposal or review-item staging.
- Missing ECE remains unavailable and blocks production ranking claims.
- Independent adversarial findings were reproduced, fixed, and covered by
  regression tests.

Remaining proof boundary:

- No real 12-question training plus 8-question held-out expert corpus has been
  collected yet.
- This PR improves measurement truth, not live relation precision, specificity,
  entity linking, or entailment.
- Trusted-graph readiness remains blocked until the signed real-human study and
  the existing live relation-quality gates both pass.

### 2026-07-13 - Semantic Selector Repeatability Harness

Branch: `alvaro/evidence-semantic-pr6-live-repeatability`

Evidence report:
`docs/validation/reports/2026-07-13-pr-semantic-pr6-live-repeatability-harness.md`

Progress:

- A frozen source-lock protocol is written before any model execution.
- Current and candidate judge models run in an interleaved schedule over
  identical source records, with distinct IDs required for every agent attempt,
  including failed validation retries.
- Numeric quality metrics are recomputed from categorical decisions and the
  frozen fixture instead of accepted from an agent or report envelope.
- Run envelopes are rebound to exact evaluation files and SHA-256 digests.
- Deterministic policy hard-gates worst-run and per-case precision, recall,
  coverage, categorical stability, abstention burden, invalid-agent decisions,
  canaries, and runtime observations. Variance remains diagnostic and cannot by
  itself cause model adoption.
- Exact registered judge models are pinned without enabling public runtime model
  overrides. Candidate adoption cannot use model-authored confidence.
- Normalized terminal-event snapshots bind model identity, every execution ID,
  token use, cost, and latency. Every aggregate is recomputed from those events,
  and zero-denominator ratios fail closed.
- Source copies, run artifacts, protocol, recomputed report, and Markdown are
  covered by an in-generation bundle manifest and digest anchor. Publication is
  one atomic directory rename; a failure produces only an explicit failure
  receipt.
- The trusted mainline must contain merged PR `#148` commit `d23b1dea`, and the
  evaluated commit must contain that frozen mainline snapshot. Commit, ref,
  worktree, and source bytes are checked again before publication.
- The registered live candidate is `openai:gpt-5.6-luna`; its availability and a
  minimal Responses API inference were verified with the configured account.
- The branch was rebased onto merged PR `#148` commit `d23b1dea`. The focused
  post-adversarial suite now has 59 passing tests; package mypy and the full
  `make service-checks` gate pass with `87.43%` coverage.
- An initial live diagnostic exposed missing bundled source provenance. After
  that adversarial finding was fixed, the final three-run interleaved v3 matrix
  completed at evaluated commit `71460f59`.
- The protocol now freezes those five repository source files into the source
  lock, copies them under repository-relative bundle paths, and replays the
  existing prediction-to-snapshot provenance checks from bundled bytes.
- The final committed bundle has 23 verified manifest entries and is published
  at
  `docs/validation/reports/semantic-model-comparisons/2026-07-13-pr6-gpt-5.6-luna-v3/`.
- New regressions reject repository path escape, pre-run source drift, and a
  tampered source snapshot even when the generic manifest is rehashed.
- The baseline score is recomputed from its bundled categorical predictions,
  and execution loads its in-memory fixture and baseline only from staged bytes.
  An adversarial re-review found no remaining blocker in these boundaries.
- The deterministic result is `INCONCLUSIVE`: neither model passed the repeated
  quality gate, no model is selected, and production readiness remains false.
- The current model had seven unstable records, worst recall `0.7692`, and one
  failed schema-validation attempt in every run whose token/cost usage was
  unavailable. It passed all canary runs and used no deterministic fallback.
- Luna was stable on every primary record with worst recall `1.0000` and
  complete telemetry, but its two malformed canaries changed from select in run
  1 to abstain in runs 2 and 3. It passed only one of three canary runs and used
  no deterministic fallback.
- The apparent Luna recall gain is not admissible evidence because
  `brca1:pmid:30191368` is labeled pathogenic in the fixture while the underlying
  abstract describes uncertain significance and possible benign or
  reduced-penetrance interpretations.

Remaining proof boundary:

- No production model switch is justified by this matrix. The ambiguous canary
  records require independent expert adjudication against a richer bounded
  source packet before the gold labels are changed or the comparison is rerun.
- The source-complete v3 artifact is published and verified. The next run must
  wait for independent correction of the defective AI-adjudicated gold rather
  than repeat the same invalid benchmark.
- Failed local output-validation attempts are now retained with typed failure
  and explicit unavailable-usage provenance. Artana still does not expose
  provider usage on its bare schema-validation exception path, so those values
  cannot be recovered or estimated by this service.
- The frozen fixture remains AI-adjudicated diagnostic evidence, not expert
  gold.
- Calibration remains unavailable until the real disjoint expert training and
  held-out partitions are collected.
- Model repeatability does not prove end-to-end trusted relation quality or
  trusted-graph readiness.

### 2026-07-13 - Semantic Benchmark V2 Integrity

Branch: `alvaro/evidence-pr151-expert-benchmark-v2`

Evidence reports:

- `docs/validation/reports/2026-07-13-pr151-semantic-benchmark-v2.md`
- `docs/validation/reports/2026-07-13-pr151-semantic-benchmark-v2-summary.md`

Progress:

- The v1 fixture and four source snapshots remain immutable historical AI
  diagnostic evidence, bound by their existing SHA-256 digests.
- A separate content-addressed packet manifest establishes the bounded input
  inventory for benchmark v2 without rewriting v1 and explicitly inventories
  each record as `unverified` or `known_insufficient`.
- AI adjudication has a strict categorical contract with rationale and literal
  packet spans. It cannot claim human/expert provenance or include numeric
  confidence/self-scores.
- The defective `brca1:pmid:30191368` label and source-incomplete
  `canary:pmid:27959700` and `canary:pmid:27393503` records are explicitly
  ambiguous pending expert review.
- Score eligibility is deterministic and reuses the existing expert-study
  bundle/provenance gate. The benchmark adds no parallel reviewer certification
  system.
- A passed existing study is necessary but insufficient. The benchmark resolves
  and hash-verifies declared source exports and verifies exact review, reviewer
  roster, run ID, export identity, and packet-manifest bindings. It then remains
  pending because the current provenance contract does not authenticate human
  identity or independently attest per-record packet sufficiency.
- The actual repeated model-comparison protocol now freezes benchmark v2 and
  recomputes an eligibility-aware adoption score from categorical outcomes.
  Pending evidence makes adoption and canary gates unavailable and forces an
  inconclusive decision with no selected model. V1 metrics remain diagnostic.
- The standalone benchmark report builder has no independently supplied score
  input. It loads the exact content-addressed prediction artifact and
  deterministically recomputes the report score against the report evaluation.
- All pending, ambiguous, and uncited records stay visible but are excluded from
  adoption metrics and canary gates. Empty eligible sets produce `unavailable`,
  not zero or pass.
- The initial integrity report is honest: 33 records visible, 0 score-eligible,
  30 pending expert, 3 ambiguous pending expert, adoption metrics unavailable,
  canary gate unavailable, and no production-readiness claim.
- Final focused, Ruff, mypy, and Postgres-backed service-check results are
  recorded in the PR151 validation summary.

Remaining proof boundary:

- A trusted external process must authenticate reviewer identity and bind that
  attestation to the existing reviewer roster, review run IDs, source-export
  digest, packet-manifest digest, and independent per-record sufficiency
  decisions. No AI adjudication in this PR satisfies that blocker.
- The three known-insufficient records need source-complete v2 packets before
  they can be independently attested and become eligible.
- The PR150 live model comparison remains historical diagnostic evidence and
  must not be reinterpreted with benchmark v2 metrics.

### 2026-07-13 - PR152 Failed Model-Attempt Telemetry

Branch: `alvaro/evidence-pr152-failed-attempt-telemetry`

Evidence report:
`docs/validation/reports/2026-07-13-pr152-failed-attempt-telemetry.md`

Progress:

- Every semantic model execution is registered before runtime setup and bound
  to a deterministic semantic batch digest, execution order, per-batch attempt
  number, source/search identity, record references, and governed step key.
- Artana terminal events are joined only when run ID, step key, frozen model,
  event ID, sequence, and event hash are present and consistent.
- Failed Pydantic output-schema events are normalized to the categorical pair
  `output_schema_validation` / `schema_contract_rejected`.
- Completed Artana responses rejected by service-local coverage, evidence
  reference, or run-identity validation remain queryable as rejected attempts
  and keep their original terminal outcome.
- Provider token and cost values are copied only when present on the Artana
  terminal event. Missing values are never priced or estimated and carry typed
  unavailable reasons.
- The complete normalized attempt snapshot, including failure association and
  usage provenance, is SHA-256 locked and all aggregates are recomputed from it.
- Model adoption remains fail closed when any attempt has incomplete runtime
  telemetry. Agent outputs remain categorical and deterministic scoring is
  unchanged.
- Focused unit/regression coverage, isolated-Postgres Artana failure-path
  coverage, Ruff, mypy, and service gates are recorded in the PR152 report.

Remaining proof boundary:

- Artana's current LiteLLM adapter extracts usage before Pydantic validation
  but re-raises a bare `ValidationError`; the kernel therefore cannot persist
  usage for that failed response. The service records
  `artana_exception_did_not_preserve_provider_usage` and does not invent the
  missing values.
- Provider sub-attempts performed inside Artana/LiteLLM retry handling are not
  separately exposed as terminal events. PR152 preserves every service-owned
  semantic execution and reports this upstream granularity limit honestly.
- This observability work does not change the PR150 model-comparison outcome,
  repair the AI-adjudicated fixture, or establish production/trusted-graph
  readiness.

## PR Update Template

Copy this block when a PR is opened or merged.

````markdown
### YYYY-MM-DD - PR-N Short Name

PR:

Branch:

Commit:

Goal:

Changed files:

-

Tests run:

-

Audit command:

```bash

```

Report artifact:

-

Before metrics:

| Metric | Value |
|---|---:|
| Agent completion rate |  |
| Fallback trusted count |  |
| Evidence anchor rate |  |
| Both-args-present rate |  |
| Entailment checked rate |  |
| Generic relation rate |  |
| CURIE-linked entity rate |  |
| Trusted-tier precision |  |

After metrics:

| Metric | Value |
|---|---:|
| Agent completion rate |  |
| Fallback trusted count |  |
| Evidence anchor rate |  |
| Both-args-present rate |  |
| Entailment checked rate |  |
| Generic relation rate |  |
| CURIE-linked entity rate |  |
| Trusted-tier precision |  |

Safety invariant added or tightened:

Known remaining risk:

Reviewer/adversarial notes:
````

## Definition Of Green

This initiative is green when the gold set has at least 100 labeled documents
and CI enforces all of the following:

- Agent extraction completes for required evaluation cases.
- No deterministic fallback output is credited as agent success.
- No fallback-only relation reaches a trusted tier.
- Every trusted relation has a sentence anchor.
- Every trusted relation has subject and object present in the supporting
  evidence span, normalization-aware.
- Every trusted relation has entailment support checked.
- Every trusted relation has canonical or reviewed relation type.
- Every trusted relation has CURIE-linked entities or explicit human-reviewed
  exceptions.
- Generic relations are suppressed when a specific supported sibling exists.
- Scores are calibrated enough to support reviewer prioritization.
- Trusted-tier precision is 1.00 on gold evaluation.
- Model, prompt, and full-text changes are cache-visible and reproducible.
- A quality regression fails CI.
