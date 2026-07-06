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
| Score calibration ECE | Uncalibrated | < 0.05 | Evidence-quality score split 0.9220 vs 0.7220; ECE not measured | PR-7 ranking tests | Ready for review; calibration dataset pending |
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
  --report current=/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run1/relation_feasibility_report.json \
  --report current=/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run2/relation_feasibility_report.json \
  --report current=/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run3/relation_feasibility_report.json \
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
