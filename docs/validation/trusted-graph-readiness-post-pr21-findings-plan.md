# Post-PR21 Trusted Graph Readiness Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every current post-PR21 finding that prevents Artana Evidence live-agent output from being safely promoted into the trusted graph.

**Architecture:** Keep the live agent as a candidate generator and make trust a code-enforced contract. Evidence API owns extraction, grounding, review-lane classification, support verification, and audit metrics. Graph DB owns final promotion enforcement, relation governance, provenance, and fail-closed policy. Validation scripts own repeated-run proof and must keep fallback, low-value review evidence, and trusted auto-promotion as separate scorecard lanes.

**Tech Stack:** Python, FastAPI service modules, Pydantic contracts, pytest, ruff, strict live-agent relation feasibility audits, failure attribution reports, readiness gates, verified entity dictionaries, graph trusted-evidence floors, Postgres-backed service checks, and adversarial review loops.

---

## Current Evidence Snapshot

This plan starts from the latest strict live-agent PR21 evidence in this worktree.

Source artifacts:

- `reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_failure_analysis_report.md`
- `docs/validation/reports/2026-07-05-pr21-verified-grounding-summary.md`

Latest state:

| Gate | PR21 run3 value | Target | Status |
|---|---:|---:|---|
| Verdict | RED | READY | Blocking |
| Strict live-agent cases completed | 30/30 | 30/30 | Passing |
| Fallback cases | 0 | 0 | Passing |
| Invalid strict-agent cases | 0 | 0 | Passing |
| Negative-control leakage cases | 0 | 0 | Passing |
| Raw unknown relation types | 0 | 0 | Passing |
| Raw unknown relation inventory surfaces | 0 | 0 | Passing |
| Wrong verified CURIE links | 0 | 0 | Passing |
| Completed-agent precision | 1.0000 | >= 0.8000 | Passing |
| Completed-agent recall | 0.8000 | >= 0.6000 | Passing |
| High-value recall | 1.0000 | >= 0.8500 | Passing |
| Trusted high-value recall | 0.8500 | >= 0.8500 | Passing, no margin |
| Generic relation rate | 0.0000 | <= 0.0500 | Passing |
| Candidate CURIE present rate | 0.9250 | observe | Informational |
| Verified CURIE-linked gold endpoint rate | 0.8810 | >= 0.9500 | Blocking |
| Low-value review recall | 0.0000 | separate review target | Blocking |

Failure attribution from PR21 run3:

| Area | Current evidence |
|---|---|
| Missed gold relations | 5, all low-value hedged or broad review-lane cases |
| False positives | 0 |
| CURIE endpoints lost to missed gold | 5, all from low-value missed relations |
| Remaining CURIE gaps | `aggressive tumor growth`, `ERK phosphorylation`, `response to pembrolizumab` |
| Review-only endpoint flags | Present for broad or composite endpoint labels |

Interpretation:

- The live-agent path now works and is precise on this fixture.
- The system is not trusted-graph ready because the readiness gate is still RED.
- The remaining RED state is not a model-runtime failure. It is a trust-contract design problem: low-value review evidence, composite endpoint policy, repeatability, model selection proof, graph promotion enforcement, and benchmark breadth.

## Non-Negotiable Trust Contract

Trusted graph readiness must never be achieved by relaxing the scorecard. It is true only when all of these are true:

- Strict live-agent runs complete with `fallback_case_count == 0`.
- Invalid agent cases, negative-control leakage, raw unknown relation types, raw unknown relation surfaces, and wrong verified CURIE links remain `0`.
- Trusted high-value claims require completed-agent provenance, verified subject and object grounding, approved relation type, grounded support sentence, entailment support, and no fallback trace.
- Low-value hedged evidence can be useful, but it must enter a review-only lane and must not satisfy trusted auto-promotion.
- Composite or event-like endpoints must either have a curated safe grounding policy or explicit review-only abstention. Broad ontology parents do not count as safe grounding.
- Graph DB must reject unsafe trusted AI evidence even if Evidence API or a report artifact incorrectly marks it trusted.
- Readiness must be proven on repeated strict live-agent runs using worst-run metrics, not only a single favorable run.

## Implementation Loop For Every PR

Each PR lane must follow this loop:

1. Pick exactly one finding or tightly coupled finding group from the ledger.
2. Write the failing regression test first.
3. Run the focused test and capture the expected failure.
4. Implement the smallest first-principles fix in the owning service boundary.
5. Run the focused test until green.
6. Run the relevant service lint, type, boundary, and contract checks when service contracts change.
7. Run `make relation-feasibility-quality-gate`.
8. Run one strict live-agent audit with `--extractor agent`.
9. Run failure attribution on the new strict report.
10. Request adversarial review against the diff, scorecard, and failure attribution.
11. Fix every valid adversarial finding.
12. Run `git diff --check` and `make service-checks`.
13. Update `docs/validation/evidence-excellence-progress-tracker.md`.
14. Add a dated evidence summary under `docs/validation/reports/`.
15. Commit only after tests, live evidence, adversarial review, and docs agree.

Strict live-agent audit command, using PR22 as the concrete example:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run1'
```

Failure attribution command, using the same PR22 example:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run1/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr22-low-value-review-lane-run1
```

Final repeated-run readiness command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-05-final-readiness-run1/relation_feasibility_report.json \
  --report reports/relation_feasibility/2026-07-05-final-readiness-run2/relation_feasibility_report.json \
  --report reports/relation_feasibility/2026-07-05-final-readiness-run3/relation_feasibility_report.json \
  --fail-on-not-ready \
  --output-dir reports/relation_feasibility_readiness/2026-07-05-final-readiness
```

## Finding Ledger

| ID | Finding | First-principles root cause | Owner lane | Robust closure evidence |
|---|---|---|---|---|
| F-01 | Verified CURIE-linked gold endpoint rate is `0.8810`, below `0.9500`. | The current all-gold endpoint metric mixes trusted-eligible claims with low-value review claims. Five denominator endpoints are lost because five low-value relations are not captured at all. | PR22 and PR24 | Add trusted-eligible endpoint metrics plus low-value review endpoint metrics. Readiness stays RED until trusted-eligible endpoints pass and low-value review capture is measured separately. |
| F-02 | Low-value review recall is `0.0000`. | The trusted path correctly avoids promoting hedged claims, but there is no live-agent review-only capture lane for useful weak evidence. | PR22 | Hedged claims produce review-only candidates with hedge metadata, support sentence, endpoints, and no trusted leakage. |
| F-03 | `aggressive tumor growth`, `ERK phosphorylation`, and `response to pembrolizumab` remain CURIE gaps. | These are broad, event-like, or composite endpoint labels. A single broad ontology parent would improve the metric but reduce graph trust. | PR23 | Each label has a typed grounding decision: curated safe grounding or explicit review-only abstention with reason codes visible in reports. |
| F-04 | Trusted high-value recall is exactly `0.8500`, with no safety margin. | PR21 reaches the current threshold, but review-only endpoint labels and live-agent variance can move the metric below target in another run. | PR23 and PR24 | Three strict runs keep worst-run trusted high-value recall `>= 0.8500`, or unstable high-value claims are held for review. |
| F-05 | Repeatability is not proven after PR21. | The latest improvement is demonstrated by one strict run after adversarial fixes. Live-agent outputs can vary. | PR24 | At least three strict runs pass on worst-run metrics, and failure attribution identifies repeated versus one-off failures. |
| F-06 | Stronger-model benefit is unknown. | There is no controlled A/B harness that compares the current configured model with a stronger candidate under identical fixture, prompt, thresholds, cost, latency, and failure attribution. | PR24 | Model comparison report contains at least three runs per model and adopts a stronger model only if worst-run trust metrics improve without new safety failures. |
| F-07 | Runtime graph promotion is not yet proven end to end for the current trust floor. | Audit readiness and graph persistence are separate boundaries. A green audit must not be the only protection. | PR25 | Graph DB rejects trusted AI relation writes missing verified endpoints, approved relation type, grounded support, entailment, provenance, no-fallback trace, or allowed review status. |
| F-08 | Benchmark confidence is limited by fixture breadth. | The current fixture is useful for regression but is still too small and curated to prove production biomedical value. | PR26 | A v3 blinded fixture expands cases across oncology, rare disease, variants, pathways, drug response, negative controls, long documents, and adversarial near-misses. |
| F-09 | Evidence docs can drift from JSON reports. | Manual summaries can preserve stale metrics after live-agent reports change. | PR27 | Summary docs are generated or checked from report JSON and include artifact hashes, branch, commit, fixture version, model label, and exact commands. |
| F-10 | PR21 merge hygiene is not finished until final local validation is clean. | The branch has useful changes, but final `make service-checks`, generated coverage cleanup, and staged scope still need confirmation before merge. | PR21 closeout | Service checks pass, generated `coverage.xml` churn is removed unless intentionally committed, and only intended files are staged. |

## PR21 Closeout: Verified Grounding Hygiene

Suggested branch: `alvaro/evidence-pr21-verified-grounding-closure`

**Findings addressed:** F-03 partially, F-04 partially, F-10 fully.

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_grounding/contracts.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_grounding/verified_dictionary.py`
- Modify: `scripts/validation/relation_feasibility/relation_matching.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Modify: `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`
- Modify: `services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `tests/unit/test_relation_feasibility_failure_analysis.py`
- Modify: `docs/validation/reports/2026-07-05-pr21-verified-grounding-summary.md`

- [ ] **Step 1: Re-run focused PR21 tests**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
    tests/unit/test_relation_feasibility_audit.py \
    tests/unit/test_relation_feasibility_failure_analysis.py \
    -q
  ```

  Expected: all focused tests pass.

- [ ] **Step 2: Re-run architecture and quality gates**

  ```bash
  make architecture-size-check
  make architecture-structure-check
  make relation-feasibility-quality-gate
  git diff --check
  ```

  Expected: all commands pass.

- [ ] **Step 3: Re-run `make service-checks`**

  ```bash
  make service-checks
  ```

  Expected: repository service checks pass. If this updates `coverage.xml`, remove the generated diff unless coverage output is intentionally tracked in the PR.

- [ ] **Step 4: Confirm strict PR21 evidence still matches the summary**

  ```bash
  rg -n "Verdict|Trusted high-value recall|Verified CURIE-linked gold endpoint rate|Low-value review recall" \
    reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_report.md
  ```

  Expected values: verdict RED, trusted high-value recall `0.8500`, verified CURIE-linked gold endpoint rate `0.8810`, low-value review recall `0.0000`.

**Merge gate:** PR21 is mergeable when local validation is clean and the PR description honestly says the branch improved precision and trusted high-value recall but did not make the system trusted-graph ready.

## PR22: Low-Value Review Lane And Metric Split

Suggested branch: `alvaro/evidence-pr22-low-value-review-lane`

**Findings closed:** F-01, F-02.

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/review_only_candidate_policy.py`
- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py`
- Create: `services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Modify: `scripts/validation/relation_feasibility/readiness.py`
- Modify: `scripts/validation/relation_feasibility/trusted_metric_rules.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `tests/unit/test_relation_feasibility_readiness_gate.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr22-low-value-review-lane-summary.md`

- [ ] **Step 1: Write failing tests for the five missed low-value cases**

  Add cases for:

  - `weak_akt_trend_survival`
  - `weak_hrd_possible_biomarker`
  - `weak_il6_may_regulate_inflammation`
  - `weak_med13_may_link_chd`
  - `weak_met_correlated_resistance`

  Expected behavior:

  - hedged candidates are emitted with `review_status == "review_only"`
  - hedge reason codes include `hedged_language`, `trend_only`, `possible_biomarker`, `may_regulate`, or `correlated_only`
  - review-only candidates can improve `low_value_review_recall`
  - review-only candidates cannot improve `trusted_high_value_recall`
  - review-only candidates cannot be graph-promotion eligible

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
    tests/unit/test_relation_feasibility_audit.py::test_low_value_review_metrics_require_review_only_candidate \
    -q
  ```

  Expected before implementation: new policy tests fail because the review-only policy module does not exist.

- [ ] **Step 2: Implement review-only policy**

  Implement `review_only_candidate_policy.py` with a focused interface:

  ```python
  @dataclass(frozen=True)
  class ReviewOnlyDecision:
      review_only: bool
      reason_codes: tuple[str, ...]
      trusted_promotion_allowed: bool


  def classify_review_only_candidate(
      *,
      relation_type: str,
      support_sentence: str,
      value_level: str | None,
  ) -> ReviewOnlyDecision:
      ...
  ```

  Required decisions:

  | Evidence language | Decision |
  |---|---|
  | `trend toward` | review-only, `trend_only`, no trusted promotion |
  | `possible biomarker` | review-only, `possible_biomarker`, no trusted promotion |
  | `may regulate` | review-only, `may_regulate`, no trusted promotion |
  | `correlated with` | review-only, `correlated_only`, no trusted promotion |
  | direct causal, resistance, sensitivity, activation, inhibition, or biomarker support without hedge | not review-only by this policy |

- [ ] **Step 3: Split readiness metrics**

  Keep `curie_linked_gold_endpoint_rate` visible, then add:

  - `trusted_eligible_curie_linked_gold_endpoint_rate`
  - `trusted_eligible_gold_curie_endpoint_count`
  - `trusted_eligible_curie_linked_gold_endpoint_count`
  - `low_value_review_curie_endpoint_capture_rate`
  - `weak_claim_trusted_leakage_count`

  Readiness rules:

  - trusted readiness uses `trusted_eligible_curie_linked_gold_endpoint_rate >= 0.9500`
  - low-value review lane uses `low_value_review_recall >= 0.8000` as a product-quality target
  - `weak_claim_trusted_leakage_count` must be `0`
  - all-gold `curie_linked_gold_endpoint_rate` remains reported as diagnostic context

- [ ] **Step 4: Run validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
    services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
    tests/unit/test_relation_feasibility_audit.py \
    tests/unit/test_relation_feasibility_readiness_gate.py \
    -q

  make relation-feasibility-quality-gate
  ```

- [ ] **Step 5: Run live-agent evidence and adversarial review**

  Run the strict audit and failure attribution commands from the implementation loop using output names containing `pr22-low-value-review-lane-run1`.

  Adversarial review must attack:

  - weak claims leaking into trusted promotion
  - metric split hiding true misses
  - false review-only credit without support sentence alignment
  - low-value review candidates missing endpoint metadata

**Merge gate:** PR22 is mergeable when low-value review recall improves, weak-claim trusted leakage remains `0`, and trusted readiness uses trusted-eligible endpoint recovery without deleting the all-gold diagnostic metric.

## PR23: Composite Endpoint Grounding And Abstention Policy

Suggested branch: `alvaro/evidence-pr23-composite-endpoint-policy`

**Findings closed:** F-03 and part of F-04.

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/entity_grounding/composite_endpoint_policy.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_grounding/contracts.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_grounding/verified_dictionary.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- Create: `services/artana_evidence_api/tests/unit/test_composite_endpoint_policy.py`
- Modify: `services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py`
- Modify: `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `tests/unit/test_relation_feasibility_failure_analysis.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr23-composite-endpoint-policy-summary.md`

- [ ] **Step 1: Write failing tests for the three remaining review-only endpoints**

  Required endpoint decisions:

  | Label | Required policy |
  |---|---|
  | `aggressive tumor growth` | review-only phenotype or outcome endpoint; no broad auto-promotion |
  | `ERK phosphorylation` | review-only molecular event unless a curated event-level grounding is added |
  | `response to pembrolizumab` | review-only therapy-response outcome unless a curated response concept is added |

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_composite_endpoint_policy.py \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    tests/unit/test_relation_feasibility_audit.py::test_review_only_grounding_labels_are_flagged_without_gold_curie \
    -q
  ```

  Expected before implementation: the new composite endpoint policy tests fail because the policy module does not exist.

- [ ] **Step 2: Implement typed composite decisions**

  Implement `composite_endpoint_policy.py` with this behavior:

  - returns `grounding_kind == "review_only_composite_endpoint"` for the three labels above
  - records `endpoint_shape` as `phenotype_outcome`, `molecular_event`, or `therapy_response`
  - records `promotion_block_reason == "composite_endpoint_requires_curator_review"`
  - refuses broad fallback IDs such as a parent pathway when the label is a narrower event
  - exposes reason codes to scoring and failure attribution

- [ ] **Step 3: Update report flags**

  Report flags must distinguish:

  - `review_only_object_grounding`
  - `composite_endpoint_requires_review`
  - `broad_ontology_parent_rejected`
  - `missing_safe_grounding`

  Failure attribution must show whether the remaining gap is a real missing safe ID or an intentional abstention.

- [ ] **Step 4: Run validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_composite_endpoint_policy.py \
    services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    tests/unit/test_relation_feasibility_audit.py \
    tests/unit/test_relation_feasibility_failure_analysis.py \
    -q

  make relation-feasibility-quality-gate
  ```

- [ ] **Step 5: Run live-agent evidence and adversarial review**

  Run the strict audit and failure attribution commands from the implementation loop using output names containing `pr23-composite-endpoint-policy-run1`.

  Adversarial review must attack:

  - broad parent ontology links being accepted as safe
  - review-only labels being counted as trusted
  - high-value recall becoming artificially green through abstention
  - report flags hiding useful review candidates

**Merge gate:** PR23 is mergeable when composite endpoints have explicit typed policy, no broad wrong CURIEs are introduced, and high-value candidates with review-only endpoints are useful to reviewers but cannot auto-promote.

## PR24: Repeatability And Stronger-Model A/B

Suggested branch: `alvaro/evidence-pr24-repeatability-model-ab`

**Findings closed:** F-04, F-05, F-06.

**Files:**

- Modify: `scripts/run_relation_feasibility_audit.py`
- Modify: `scripts/run_relation_feasibility_readiness_gate.py`
- Modify: `scripts/summarize_relation_readiness_failures.py`
- Modify: `scripts/validation/relation_feasibility/readiness.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Create: `scripts/validation/relation_feasibility/model_comparison.py`
- Create: `tests/unit/test_relation_feasibility_model_comparison.py`
- Modify: `tests/unit/test_relation_feasibility_readiness_gate.py`
- Modify: `tests/unit/test_relation_feasibility_failure_analysis.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr24-repeatability-model-ab-summary.md`

- [ ] **Step 1: Write failing tests for worst-run gating**

  Tests must prove:

  - three runs are required for readiness
  - average metrics cannot hide a bad run
  - one run below trusted high-value recall target keeps readiness not ready
  - one run with fallback, invalid agent output, negative leakage, wrong verified CURIE, or weak-claim trusted leakage keeps readiness not ready

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_readiness_gate.py \
    -q
  ```

- [ ] **Step 2: Write failing tests for model comparison**

  `model_comparison.py` must report:

  - model label
  - run count
  - worst-run and mean precision
  - worst-run and mean high-value recall
  - worst-run and mean trusted high-value recall
  - worst-run and mean trusted-eligible endpoint rate
  - fallback count
  - invalid-agent count
  - wrong verified CURIE count
  - weak-claim trusted leakage count
  - cost when present
  - latency when present
  - repeated failure clusters

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_model_comparison.py \
    -q
  ```

- [ ] **Step 3: Run three strict audits for the current model**

  ```bash
  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --model-label current \
    --output-dir reports/relation_feasibility/2026-07-05-pr24-current-run1'
  ```

  Repeat with `run2` and `run3`.

- [ ] **Step 4: Run three strict audits for the stronger candidate model**

  ```bash
  bash -lc 'set -a; source .env.postgres; set +a; \
    export ARTANA_AI_EVIDENCE_EXTRACTION_MODEL="$ARTANA_STRONGER_MODEL_CANDIDATE"; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --model-label candidate \
    --output-dir reports/relation_feasibility/2026-07-05-pr24-candidate-run1'
  ```

  Repeat with `run2` and `run3`.

  Required precondition: `ARTANA_STRONGER_MODEL_CANDIDATE` must be set in the shell or `.env.postgres`. The run must fail preflight if this variable is empty.

- [ ] **Step 5: Compare and decide**

  Stronger model adoption is allowed only when all are true:

  - candidate worst-run trusted high-value recall is higher or equal
  - candidate worst-run trusted-eligible endpoint rate is higher or equal
  - candidate fallback, invalid-agent, negative leakage, wrong verified CURIE, and weak trusted leakage counts are all `0`
  - candidate cost and latency are recorded
  - adversarial review finds no cherry-picked comparison

**Merge gate:** PR24 is mergeable when repeatability is measured with worst-run gates and model choice is evidence-backed. A stronger model can help, but it cannot replace grounding, review policy, and graph enforcement.

## PR25: Graph Promotion Hard Gate

Suggested branch: `alvaro/evidence-pr25-graph-promotion-hard-gate`

**Findings closed:** F-07.

**Files:**

- Modify: `services/artana_evidence_db/validation/trusted_evidence_floor.py`
- Modify: `services/artana_evidence_db/validation/claim_ai_evidence_validation.py`
- Modify: `services/artana_evidence_db/relation_claim_service.py`
- Modify: `services/artana_evidence_db/claim_evidence_service.py`
- Modify: `services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py`
- Modify: `services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py`
- Create: `services/artana_evidence_db/tests/unit/test_trusted_relation_promotion_policy.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr25-graph-promotion-hard-gate-summary.md`

- [ ] **Step 1: Write failing promotion rejection tests**

  Graph DB must reject trusted AI evidence with:

  - missing subject CURIE
  - missing object CURIE
  - model-only subject or object CURIE source
  - review-only endpoint status
  - unapproved relation type
  - missing evidence sentence
  - support status other than entailed
  - fallback extraction trace
  - missing provenance
  - weak-claim trusted leakage metadata

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
    services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py \
    services/artana_evidence_db/tests/unit/test_trusted_relation_promotion_policy.py \
    -q
  ```

  Expected before implementation: the new policy tests fail if a bypass path exists or if the test module does not exist.

- [ ] **Step 2: Consolidate promotion policy**

  Keep `trusted_evidence_floor.py` as the single hard-floor decision point for trusted AI evidence and return reason codes that match audit terminology:

  - `missing_verified_subject`
  - `missing_verified_object`
  - `model_hint_only_identifier`
  - `review_only_endpoint`
  - `unapproved_relation_type`
  - `missing_evidence_sentence`
  - `support_not_entailed`
  - `fallback_trace_present`
  - `missing_provenance`
  - `weak_claim_trusted_leakage`

- [ ] **Step 3: Run graph service gates**

  ```bash
  make graph-service-lint
  make graph-service-type-check
  make graph-service-boundary-check
  make graph-service-contract-check
  make graph-service-test
  make graph-service-checks
  ```

- [ ] **Step 4: Run adversarial bypass review**

  Adversarial review must attack:

  - metadata spoofing
  - direct service call bypasses
  - relation evidence write paths that skip `trusted_evidence_floor.py`
  - update paths that change a review-only relation into trusted without revalidation

**Merge gate:** PR25 is mergeable when Graph DB fails closed even if upstream metadata lies.

## PR26: Blinded Benchmark Expansion

Suggested branch: `alvaro/evidence-pr26-blinded-benchmark-expansion`

**Findings closed:** F-08.

**Files:**

- Create: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Modify: `scripts/validation/relation_feasibility/io.py`
- Modify: `scripts/run_relation_feasibility_audit.py`
- Create: `tests/unit/test_relation_feasibility_fixture_v3.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr26-blinded-benchmark-expansion-summary.md`

- [ ] **Step 1: Write fixture validation tests**

  Tests must fail when v3 contains:

  - duplicate `case_id`
  - missing support sentence
  - missing rationale
  - invalid relation type
  - unsupported value level
  - trusted-eligible relation without endpoint policy
  - negative control with a gold relation
  - long-document case without relation position metadata

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_fixture_v3.py \
    -q
  ```

- [ ] **Step 2: Add at least 60 v3 cases**

  Required distribution:

  | Category | Minimum cases |
  |---|---:|
  | Oncology driver or resistance | 10 |
  | Rare disease or phenotype | 8 |
  | Variant-specific claims | 8 |
  | Pathway/process relations | 8 |
  | Drug response or biomarker | 8 |
  | Low-value hedged review-only claims | 8 |
  | Negative controls | 6 |
  | Long-document tail relations | 4 |

- [ ] **Step 3: Run v2 regression and v3 exploratory audits**

  ```bash
  make relation-feasibility-quality-gate

  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --fixture-version v3 \
    --output-dir reports/relation_feasibility/2026-07-05-pr26-v3-run1'
  ```

- [ ] **Step 4: Run adversarial benchmark review**

  Adversarial review must attack:

  - leakage from existing examples
  - cases that are too easy
  - ambiguous gold labels
  - invalid negative controls
  - ontology shortcuts that would make wrong links look correct

**Merge gate:** PR26 is mergeable when v3 expands confidence while keeping v2 as the stable regression gate.

## PR27: Generated Evidence Reports And Drift Guard

Suggested branch: `alvaro/evidence-pr27-generated-evidence-reports`

**Findings closed:** F-09.

**Files:**

- Create: `scripts/generate_relation_evidence_summary.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Modify: `scripts/validation/relation_feasibility/readiness.py`
- Create: `tests/unit/test_generate_relation_evidence_summary.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr27-generated-evidence-summary.md`

- [ ] **Step 1: Write failing summary-generation tests**

  Tests must prove:

  - metrics are read from JSON, not typed manually
  - artifact paths are included
  - SHA-256 hashes are included
  - branch and commit are included when available
  - fixture version and model label are included
  - exact commands are included
  - generation fails when required metrics are missing

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_generate_relation_evidence_summary.py \
    -q
  ```

- [ ] **Step 2: Generate PR summaries from artifacts**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/generate_relation_evidence_summary.py \
    --report reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_report.json \
    --failure-report reports/relation_feasibility_failure_analysis/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_failure_analysis_report.json \
    --output docs/validation/reports/2026-07-05-pr21-verified-grounding-summary.md
  ```

- [ ] **Step 3: Add doc drift check**

  The check must fail when a generated summary metric differs from the JSON report it cites.

- [ ] **Step 4: Run validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_generate_relation_evidence_summary.py \
    -q

  make relation-feasibility-quality-gate
  make service-checks
  ```

**Merge gate:** PR27 is mergeable when report summaries can be regenerated from JSON and stale metric drift is caught automatically.

## Final Readiness Drill

Suggested branch: `alvaro/evidence-final-trusted-graph-readiness`

Depends on: PR21, PR22, PR23, PR24, PR25, PR26, PR27.

- [ ] **Step 1: Rebase final readiness branch on the merged stack**

  ```bash
  git fetch origin
  git rebase origin/main
  ```

- [ ] **Step 2: Run repository gates**

  ```bash
  make service-checks
  git diff --check
  ```

- [ ] **Step 3: Run three strict final audits**

  Use output directories:

  - `reports/relation_feasibility/2026-07-05-final-readiness-run1`
  - `reports/relation_feasibility/2026-07-05-final-readiness-run2`
  - `reports/relation_feasibility/2026-07-05-final-readiness-run3`

- [ ] **Step 4: Run failure attribution for all three final audits**

  ```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
    --report run1=reports/relation_feasibility/2026-07-05-final-readiness-run1/relation_feasibility_report.json \
    --report run2=reports/relation_feasibility/2026-07-05-final-readiness-run2/relation_feasibility_report.json \
    --report run3=reports/relation_feasibility/2026-07-05-final-readiness-run3/relation_feasibility_report.json \
    --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-final-readiness
```

- [ ] **Step 5: Run repeated readiness gate**

  ```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
    --report reports/relation_feasibility/2026-07-05-final-readiness-run1/relation_feasibility_report.json \
    --report reports/relation_feasibility/2026-07-05-final-readiness-run2/relation_feasibility_report.json \
    --report reports/relation_feasibility/2026-07-05-final-readiness-run3/relation_feasibility_report.json \
    --fail-on-not-ready \
    --output-dir reports/relation_feasibility_readiness/2026-07-05-final-readiness
```

- [ ] **Step 6: Run adversarial final review**

  Review scope:

  - full diff
  - three strict audit reports
  - failure attribution
  - model comparison
  - graph promotion tests
  - generated docs
  - tracker status

- [ ] **Step 7: Generate final evidence summary**

  Use `scripts/generate_relation_evidence_summary.py` after PR27.

**Final trusted-graph readiness gate:** The system is ready only when repeated strict live-agent reports are READY and Graph DB independently rejects unsafe trusted-promotion attempts.

## Parallelization Plan

```text
PR21 closeout
  -> PR22 low-value review lane
  -> PR23 composite endpoint policy
  -> PR25 graph promotion hard gate
  -> PR27 generated evidence reports

PR22 + PR23
  -> PR24 repeatability and stronger-model A/B

PR26 benchmark expansion
  -> PR24 repeatability and stronger-model A/B
  -> final readiness drill

PR24 + PR25 + PR26 + PR27
  -> final readiness drill
```

Parallel lanes after PR21 closeout:

- PR22 and PR23 can run in parallel if they avoid editing the same scoring functions at the same time or one branch rebases on the other.
- PR25 can run independently in Graph DB.
- PR26 can run independently if it does not change v2 readiness behavior.
- PR27 can run independently after summary JSON fields are stable.
- PR24 should wait for PR22, PR23, and PR26 before making repeatability and model adoption claims.

## Progress Checklist

- [ ] PR21 closeout confirms grounding fixes, service checks, and honest RED status.
- [ ] PR22 adds low-value review capture and splits trusted readiness from review-lane diagnostics.
- [ ] PR23 adds typed composite endpoint policy without broad wrong CURIEs.
- [ ] PR24 proves repeatability and stronger-model policy through controlled A/B runs.
- [ ] PR25 enforces trusted evidence floors at Graph DB promotion.
- [ ] PR26 expands the benchmark with blinded v3 coverage.
- [ ] PR27 prevents evidence-summary drift from JSON artifacts.
- [ ] Final readiness drill passes three strict live-agent runs and graph hard-gate validation.
