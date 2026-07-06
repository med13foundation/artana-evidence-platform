# Post-PR22 Trusted Graph Readiness Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Robustly close every remaining finding from the PR22 live-agent audit so Artana Evidence can prove trusted-graph readiness without relying on deterministic fallback or broad, low-value generalities.

**Architecture:** Keep the live agent as the evidence candidate generator, but make trust a code-enforced contract. Evidence API owns extraction, review-only classification, verified grounding, support verification, and audit telemetry. Graph DB owns final trusted-promotion rejection. Validation scripts own repeatability, model comparison, failure attribution, and generated proof artifacts.

**Tech Stack:** Python, FastAPI service modules, Pydantic contracts, pytest, ruff, relation feasibility audits, failure attribution reports, repeated strict live-agent runs, verified entity dictionaries, graph trusted-evidence floors, Postgres service checks, and adversarial review loops.

---

## Source Evidence

This plan starts from the latest PR22 strict live-agent run in this worktree:

- `reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run1/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run1/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr22-low-value-review-lane-run1/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr22-low-value-review-lane-run1/relation_feasibility_failure_analysis_report.md`

Latest PR22 run1 state:

| Metric | Value | Target | Status |
|---|---:|---:|---|
| Single-run verdict | RED | not RED | Blocking |
| Blocking reason | Too few CURIE-linked gold endpoints were recovered by extraction. | no trusted-lane blocker | Blocking |
| Completed-agent precision | 1.0000 | >= 0.8000 | Passing |
| Completed-agent recall | 0.8800 | >= 0.6000 | Passing |
| Completed-agent valuable candidate rate | 0.9091 | >= 0.7000 | Passing |
| High-value recall | 1.0000 | >= 0.8500 | Passing |
| Trusted high-value recall | 0.8500 | >= 0.8500 | Passing, no margin |
| Low-value recall | 0.4000 | observe separately | Weak |
| Low-value review candidates | 2 | increasing | Improved |
| Low-value review recall | 0.4000 | >= 0.8000 before readiness claim | Blocking review quality |
| All-gold CURIE-linked endpoint rate | 0.9048 | diagnostic | Low because low-value review claims are included |
| Trusted-eligible CURIE-linked endpoint rate | 1.0000 | >= 0.9500 | Passing |
| Low-value review CURIE endpoint capture rate | 0.2000 | >= 0.6000 before readiness claim | Blocking review quality |
| Weak-claim trusted leakage | 0 | 0 | Passing |
| Fallback cases | 0 | 0 | Passing |
| Invalid strict-agent cases | 0 | 0 | Passing |
| Wrong verified CURIE links | 0 | 0 | Passing |
| False positives | 0 | 0 preferred | Passing |

Failure attribution:

| Finding | Evidence |
|---|---|
| Missed low-value review claims | `weak_akt_trend_survival`, `weak_med13_may_link_chd`, `weak_met_correlated_resistance` |
| Missed low-value CURIE endpoints | `AKT activation`, `MED13`, `congenital heart disease`, `MET amplification` |
| Remaining CURIE gaps | `aggressive tumor growth`, `ERK phosphorylation`, `response to pembrolizumab`, `HRD score`, `platinum sensitivity`, `inflammatory signaling` |
| False positives | none |
| Model comparison | only one current-model run; no controlled stronger-model evidence |

## First-Principles Diagnosis

The system is not mainly blocked by "the model cannot extract relations." The current agent path completes, avoids fallback, avoids false positives on this run, and recovers all high-value gold relations.

The trusted-graph blockers are contract and proof problems:

1. The single-run verdict still uses the old all-gold endpoint denominator. That incorrectly lets low-value review evidence keep the trusted-lane verdict RED even when trusted-eligible endpoint recovery is 1.0000.
2. The low-value lane is partially implemented. It captures some weak evidence as review-only, but misses three useful weak/hedged cases and only links 20% of low-value review CURIE endpoints.
3. Endpoint grounding lacks a complete decision table for event-like, process-like, biomarker-score, treatment-response, and generic resistance labels.
4. Repeatability is not proven. One good strict run does not prove trusted-graph readiness.
5. A stronger model might help recall, but that is not proven. It could also add unsafe specificity loss, wrong CURIE hints, or weak-claim trusted leakage.
6. Graph promotion must remain a separate fail-closed boundary. A green audit is evidence, not the enforcement layer.
7. The benchmark is still a seed fixture, not a production-representative biomedical evaluation.
8. Manual docs can drift from JSON reports.

## Non-Negotiable Readiness Contract

Do not claim trusted-graph readiness until all of these are true:

- Strict live-agent runs complete with `fallback_case_count == 0`.
- `invalid_agent_case_count == 0`.
- `negative_control_leakage_case_count == 0` or equivalent negative-control leakage count is `0`.
- `raw_unknown_relation_type_count == 0`.
- `raw_unknown_relation_type_surface_count == 0`.
- `wrong_verified_curie_link_count == 0`.
- `weak_claim_trusted_leakage_count == 0`.
- Worst-run `completed_agent_precision_against_gold >= 0.8000`.
- Worst-run `completed_agent_recall_against_gold >= 0.6000`.
- Worst-run `high_value_recall >= 0.8500`.
- Worst-run `trusted_high_value_recall >= 0.8500`.
- Worst-run `completed_agent_valuable_candidate_rate >= 0.7000`.
- Worst-run `generic_relation_rate <= 0.0500`.
- Worst-run `trusted_eligible_curie_linked_gold_endpoint_rate >= 0.9500`.
- Low-value review evidence is captured and reported separately, but never satisfies trusted auto-promotion.
- Graph DB rejects any trusted AI evidence missing completed-agent provenance, no-fallback trace, verified endpoints, approved relation type, grounded support sentence, support verification, and trusted-compatible review status.

All-gold endpoint recovery remains useful as a diagnostic metric. It must not be the trusted-lane blocker after low-value review metrics exist.

## PR Stack Overview

| PR | Branch | Owns | Can run in parallel? | Merge base |
|---|---|---|---|---|
| PR22A | `alvaro/evidence-pr22-low-value-review-lane` | Verdict metric contract and current review-only metric split | no, finish first | PR21 |
| PR23 | `alvaro/evidence-pr23-low-value-review-recall` | Missed weak/hedged review candidates and low-value endpoint capture | after PR22A | PR22A |
| PR24 | `alvaro/evidence-pr24-grounding-decision-table` | Remaining CURIE gap policy and verified/review-only endpoint table | after PR22A, can run beside PR23 if file ownership is split carefully | PR22A |
| PR25 | `alvaro/evidence-pr25-repeatability-model-ab` | Three-run readiness and stronger-model A/B proof | after PR22A, independent of PR23/PR24 except final thresholds | PR22A |
| PR26 | `alvaro/evidence-pr26-graph-promotion-fail-closed` | Graph DB trusted-promotion enforcement for review-only and fallback traces | after PR22A, can run beside PR23/PR24 | PR22A |
| PR27 | `alvaro/evidence-pr27-benchmark-v3-doc-proof` | Fixture breadth and generated evidence summaries | after PR25 for final readiness, but fixture design can start early | PR22A |

Recommended order:

```text
PR22A
  -> PR23
  -> PR24
  -> PR25
  -> PR26
  -> PR27
  -> final repeated strict live-agent readiness gate
```

PR23, PR24, and PR26 can be developed in parallel after PR22A if each branch avoids editing the same modules at the same time. PR25 can start as a validation harness branch once PR22A is stable.

## Shared Implementation Loop

Every PR must follow this loop:

- [ ] Write the failing regression test first.
- [ ] Run the focused test and capture the expected failure.
- [ ] Implement the smallest code change at the owning boundary.
- [ ] Run the focused test until it passes.
- [ ] Run touched-file ruff.
- [ ] Run `make relation-feasibility-quality-gate`.
- [ ] Run one strict live-agent audit with `--extractor agent`.
- [ ] Run failure attribution on the strict audit report.
- [ ] Run adversarial review against the diff, report, failure attribution, and remaining risks.
- [ ] Fix every valid adversarial finding.
- [ ] Run `git diff --check`.
- [ ] Run `make service-checks` before merge.
- [ ] Update `docs/validation/evidence-excellence-progress-tracker.md`.
- [ ] Add a dated summary under `docs/validation/reports/`.

Strict live-agent audit example:

```bash
RUN_ID=2026-07-05-pr22-low-value-review-lane-run4
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/'"$RUN_ID"
```

Failure attribution example:

```bash
RUN_ID=2026-07-05-pr22-low-value-review-lane-run4
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/"$RUN_ID"/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/"$RUN_ID"
```

Do not paste `OPENAI_API_KEY` or provider keys into any doc, test, PR body, or report summary.

## PR22A: Fix The Verdict Contract

**Findings closed:** F-01, F-02 safety part.

**Root cause:** PR22 introduced trusted-eligible endpoint metrics, but the single-run `_verdict` function still blocks on all-gold endpoint rate. That mixes trusted high-value evidence with low-value review evidence.

**Files:**

- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `tests/unit/test_relation_feasibility_readiness_gate.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr22-low-value-review-lane-summary.md`

- [ ] **Step 1: Keep the failing regression test**

  Ensure `tests/unit/test_relation_feasibility_audit.py` contains a test with this behavior:

  ```python
  def test_verdict_uses_trusted_eligible_endpoint_rate_not_all_gold_rate() -> None:
      cases = (
          _case(
              case_id="trusted_endpoint_verdict_high",
              text="MED13 activates MAPK signaling.",
              gold=(
                  GoldRelation(
                      subject="MED13",
                      relation_type="ACTIVATES",
                      object="MAPK signaling",
                      support_sentence="MED13 activates MAPK signaling.",
                      value_level="high",
                      rationale="Trusted-eligible mechanism.",
                      subject_curie="HGNC:22474",
                      object_curie="GO:0000165",
                  ),
              ),
          ),
          _case(
              case_id="trusted_endpoint_verdict_low",
              text="MET amplification was correlated with resistance.",
              gold=(
                  GoldRelation(
                      subject="MET amplification",
                      relation_type="ASSOCIATED_WITH",
                      object="resistance",
                      support_sentence=(
                          "MET amplification was correlated with resistance."
                      ),
                      value_level="low",
                      rationale="Weak evidence belongs in review lane.",
                      subject_curie="HGNC:7029",
                  ),
              ),
          ),
      )

      def extractor(text: str) -> list[ExtractedRelation]:
          if "MED13" not in text:
              return []
          return [
              ExtractedRelation(
                  subject="MED13",
                  relation_type="ACTIVATES",
                  object="MAPK signaling",
                  sentence="MED13 activates MAPK signaling.",
                  subject_curie="HGNC:22474",
                  subject_curie_source="verified_linker",
                  object_curie="GO:0000165",
                  object_curie_source="verified_linker",
              ),
          ]

      report = run_feasibility_audit(cases=cases, extractor=extractor)

      assert report.summary.curie_linked_gold_endpoint_rate < 0.95
      assert report.summary.trusted_eligible_curie_linked_gold_endpoint_rate == 1.0
      assert report.summary.weak_claim_trusted_leakage_count == 0
      assert report.summary.verdict != "RED"
      assert "Too few CURIE-linked gold endpoints" not in report.summary.blocking_reasons
  ```

- [ ] **Step 2: Run the focused test to prove the bug**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_audit.py::test_verdict_uses_trusted_eligible_endpoint_rate_not_all_gold_rate \
    -q
  ```

  Expected before implementation: fail because `_verdict` still blocks on `curie_linked_gold_endpoint_rate`.

- [ ] **Step 3: Add trusted-lane fields to `_VerdictContext`**

  In `scripts/validation/relation_feasibility/scoring.py`, extend `_VerdictContext`:

  ```python
  trusted_eligible_gold_curie_endpoint_count: int
  trusted_eligible_curie_linked_gold_endpoint_rate: float
  weak_claim_trusted_leakage_count: int
  ```

- [ ] **Step 4: Pass endpoint split metrics into `_VerdictContext`**

  In `build_summary`, pass values from `endpoint_metric_summary`:

  ```python
  trusted_eligible_gold_curie_endpoint_count=(
      endpoint_metric_summary.trusted_eligible_gold_curie_endpoint_count
  ),
  trusted_eligible_curie_linked_gold_endpoint_rate=(
      endpoint_metric_summary.trusted_eligible_curie_linked_gold_endpoint_rate
  ),
  weak_claim_trusted_leakage_count=(
      endpoint_metric_summary.weak_claim_trusted_leakage_count
  ),
  ```

- [ ] **Step 5: Replace the all-gold RED condition**

  In `_verdict`, replace the all-gold endpoint hard failure with:

  ```python
  if (
      context.trusted_eligible_gold_curie_endpoint_count > 0
      and context.trusted_eligible_curie_linked_gold_endpoint_rate
      < _MIN_CURIE_LINKED_GOLD_ENDPOINT_RATE
  ):
      red_reasons.append(
          "Too few trusted-eligible CURIE-linked gold endpoints were recovered by extraction."
      )
  ```

  Keep `curie_linked_gold_endpoint_rate` in the summary and report as a diagnostic metric.

- [ ] **Step 6: Add weak-claim leakage as a single-run hard failure**

  In `_verdict`, add:

  ```python
  if context.weak_claim_trusted_leakage_count > 0:
      red_reasons.append("Weak low-value claims leaked into trusted evidence.")
  ```

- [ ] **Step 7: Re-run focused and affected tests**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
    services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
    tests/unit/test_relation_feasibility_audit.py \
    tests/unit/test_relation_feasibility_readiness_gate.py \
    -q
  ```

  Expected: all pass.

- [ ] **Step 8: Run the PR22A live-agent audit**

  ```bash
  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --output-dir reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run4'
  ```

  Expected: the single-run report no longer has the old all-gold endpoint blocker when `trusted_eligible_curie_linked_gold_endpoint_rate >= 0.9500`.

- [ ] **Step 9: Run failure attribution and document the result**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
    --report current=reports/relation_feasibility/2026-07-05-pr22-low-value-review-lane-run4/relation_feasibility_report.json \
    --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr22-low-value-review-lane-run4
  ```

  Add a summary in `docs/validation/reports/2026-07-05-pr22-low-value-review-lane-summary.md`.

**Merge gate:** PR22A is mergeable only if trusted-lane endpoint recovery gates use `trusted_eligible_curie_linked_gold_endpoint_rate`, weak-claim leakage is hard-failed, fallback is still `0`, wrong verified links are still `0`, and the new live-agent report is honest about remaining low-value review gaps.

## PR23: Complete Low-Value Review Recall

**Findings closed:** F-03, F-04.

**Root cause:** The current policy can mark weak candidates review-only after they exist, but the live agent still omits three weak/hedged cases. The extractor prompt and post-filter need to preserve weak-but-useful evidence as review-only instead of either dropping it or treating it as trusted.

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_contracts.py`
- Modify: `services/artana_evidence_api/document_extraction_support/review_policy/review_only_candidate_policy.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py`
- Modify: `services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py`
- Modify: `services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Create: `docs/validation/reports/2026-07-05-pr23-low-value-review-recall-summary.md`

- [ ] **Step 1: Add policy tests for each missed weak case**

  Add tests to `services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py` for:

  ```python
  "AKT activation showed a trend toward reduced survival."
  "MED13 may be linked to congenital heart disease."
  "MET amplification correlated with resistance."
  ```

  Expected decisions:

  | Sentence pattern | Required reason codes |
  |---|---|
  | `trend toward reduced survival` | `hedged_language`, `trend_only` |
  | `may be linked to congenital heart disease` | `hedged_language`, `may_link` |
  | `correlated with resistance` | `hedged_language`, `correlated_only` |

- [ ] **Step 2: Run policy tests before implementation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
    -q
  ```

  Expected before implementation: `may be linked` is not classified with a specific reason if `may_link` is missing.

- [ ] **Step 3: Extend the review-only policy**

  In `review_policy/review_only_candidate_policy.py`, add a focused pattern for weak links:

  ```python
  _MAY_LINK_RE = re.compile(
      r"\bmay\s+(?:be\s+)?(?:link(?:ed)?|associat(?:ed|e))\s+(?:to|with)\b",
      re.IGNORECASE,
  )
  ```

  Then add:

  ```python
  if _MAY_LINK_RE.search(support_sentence) is not None:
      reasons.append("may_link")
  ```

  Keep `trusted_promotion_allowed=False` whenever any review-only reason exists.

- [ ] **Step 4: Update the extraction prompt to preserve weak evidence only as review-only**

  In `document_extraction_prompting.py`, add explicit extraction guidance:

  ```text
  Weak, hedged, trend-only, possible biomarker, may-link, and correlation-only claims should be emitted only when they are useful for human review. Mark them as review_only and include the hedge reason. Do not mark them trusted_evidence_eligible.
  ```

  The prompt must still tell the model not to invent relations absent from the support sentence.

- [ ] **Step 5: Add audit tests for low-value capture without trust leakage**

  In `tests/unit/test_relation_feasibility_audit.py`, add a test with the three missed cases. Assert:

  ```python
  assert report.summary.low_value_review_recall >= 0.8
  assert report.summary.weak_claim_trusted_leakage_count == 0
  assert report.summary.trusted_high_value_recall >= 0.85
  ```

  Also assert candidate quality flags include `review_only_candidate` and `review_reason:<code>`.

- [ ] **Step 6: Run focused tests**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
    services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
    tests/unit/test_relation_feasibility_audit.py::test_low_value_review_metrics_count_review_only_canonical_candidate \
    tests/unit/test_relation_feasibility_audit.py::test_endpoint_metrics_split_trusted_eligible_from_low_value_review \
    -q
  ```

- [ ] **Step 7: Run strict live-agent PR23 audit**

  ```bash
  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --output-dir reports/relation_feasibility/2026-07-05-pr23-low-value-review-recall-run1'
  ```

  Expected directional improvement:

  - `low_value_review_recall >= 0.8000`
  - `weak_claim_trusted_leakage_count == 0`
  - `fallback_case_count == 0`
  - `wrong_verified_curie_link_count == 0`
  - no new false positives

- [ ] **Step 8: Adversarial review prompt**

  Ask the reviewer:

  ```text
  Review PR23 for hidden trust leakage. Try to prove that a weak, hedged, trend-only, or correlation-only relation can become trusted_evidence_eligible or satisfy trusted_high_value_recall. Also check whether the prompt now encourages the model to over-extract weak generalities.
  ```

**Merge gate:** PR23 is mergeable only if low-value review recall improves materially, weak claims cannot be trusted, and the precision/high-value metrics do not regress.

## PR24: Endpoint Grounding Decision Table

**Findings closed:** F-05.

**Root cause:** Endpoint grounding currently has some verified labels and some review-only labels, but the remaining gap labels need explicit decisions. The system must never improve metrics by attaching a broad or unsafe CURIE to a composite concept.

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_support/entity_grounding/contracts.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_grounding/verified_dictionary.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- Modify: `services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py`
- Modify: `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`
- Modify: `tests/unit/test_relation_feasibility_failure_analysis.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Create: `docs/validation/reports/2026-07-05-pr24-grounding-decision-table-summary.md`

- [ ] **Step 1: Add a grounding-decision test for every PR22 gap**

  Required labels:

  | Label | Expected decision |
  |---|---|
  | `aggressive tumor growth` | review-only unless a precise approved ontology identifier is curated |
  | `ERK phosphorylation` | verified only if curated as the exact process/event used by the fixture; otherwise review-only |
  | `response to pembrolizumab` | review-only unless a precise treatment-response concept is approved |
  | `HRD score` | review-only or verified score concept if explicitly curated |
  | `platinum sensitivity` | review-only or verified phenotype/drug-response concept if explicitly curated |
  | `inflammatory signaling` | model hint `GO:0006954` remains untrusted unless explicitly curated |
  | `reduced survival` | review-only or verified prognosis/outcome concept if explicitly curated |
  | `resistance` | review-only unless relation object is made drug-specific |

  The test must assert no label returns a trusted link solely because the model supplied a plausible CURIE.

- [ ] **Step 2: Add decision metadata to review-only records**

  Extend review-only records so the report can explain why an endpoint is not trusted:

  ```python
  curation_status="review_only_for_relation_feasibility_v2"
  reason_code="composite_event_label"
  trusted_identifier_allowed=False
  ```

  Use existing contract names when possible; do not create a parallel dictionary format.

- [ ] **Step 3: Add failure-analysis rows for unresolved endpoint policy**

  In `failure_analysis.py`, include the grounding decision in `curie_gaps` rows:

  ```python
  {
      "gap_type": "review_only_endpoint",
      "grounding_reason": "composite_event_label",
  }
  ```

  This makes review-only abstention auditable instead of looking like accidental missing data.

- [ ] **Step 4: Run focused grounding tests**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    tests/unit/test_relation_feasibility_failure_analysis.py \
    -q
  ```

- [ ] **Step 5: Run strict live-agent PR24 audit**

  ```bash
  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --output-dir reports/relation_feasibility/2026-07-05-pr24-grounding-decision-table-run1'
  ```

  Expected:

  - `wrong_verified_curie_link_count == 0`
  - no raw model hint is counted as verified
  - all remaining endpoint gaps have an explicit decision reason
  - trusted-eligible endpoint rate remains `>= 0.9500`

- [ ] **Step 6: Adversarial review prompt**

  ```text
  Review PR24 for unsafe grounding. Try to find any label where the dictionary maps a broad, generic, or composite concept to a CURIE just to improve the metric. Check whether model hints can bypass verified curation.
  ```

**Merge gate:** PR24 is mergeable only if every remaining endpoint gap is either safely verified or explicitly review-only, with wrong verified CURIE links still at `0`.

## PR25: Repeatability And Stronger-Model A/B

**Findings closed:** F-06, F-07.

**Root cause:** Current evidence has one PR22 strict run for the latest path and one model group. A stronger model could improve low-value recall, but it could also increase over-extraction or wrong grounding. The only acceptable answer is controlled measurement.

**Files:**

- Create: `scripts/run_relation_model_comparison.py`
- Create: `scripts/validation/relation_feasibility/model_comparison.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Modify: `scripts/validation/relation_feasibility/readiness.py`
- Modify: `tests/unit/test_relation_feasibility_readiness_gate.py`
- Modify: `tests/unit/test_relation_feasibility_failure_analysis.py`
- Create: `docs/validation/reports/2026-07-05-pr25-repeatability-model-ab-summary.md`

- [ ] **Step 1: Add tests for model comparison admission rules**

  In `tests/unit/test_relation_feasibility_failure_analysis.py`, add fixtures with `current` and `candidate` reports. Assert:

  ```python
  assert candidate["worst_trusted_eligible_curie_linked_gold_endpoint_rate"] >= current["worst_trusted_eligible_curie_linked_gold_endpoint_rate"]
  assert candidate["worst_completed_agent_precision_against_gold"] >= 0.8
  assert candidate["weak_claim_trusted_leakage_count"] == 0
  assert candidate["wrong_verified_curie_link_count"] == 0
  ```

- [ ] **Step 2: Create a small model-comparison module**

  `model_comparison.py` should accept already-written report paths and return:

  ```python
  @dataclass(frozen=True, slots=True)
  class ModelComparisonDecision:
      adopted_model_label: str | None
      blocking_reasons: tuple[str, ...]
      metric_deltas: Mapping[str, float]
      safety_failures: tuple[str, ...]
  ```

  It must not call the model itself. It should only evaluate report artifacts.

- [ ] **Step 3: Create a wrapper script for repeated runs**

  `scripts/run_relation_model_comparison.py` should orchestrate commands, not embed scoring logic. It must:

  - require `--current-model-label current`
  - require `--candidate-model-label candidate`
  - require `--runs-per-model 3`
  - write one report directory per run
  - write a final comparison JSON and Markdown artifact
  - refuse to run if the candidate model env var is missing

- [ ] **Step 4: Run current model three times**

  ```bash
  for run in 1 2 3; do
    bash -lc 'set -a; source .env.postgres; set +a; \
      PYTHONPATH="$(pwd)/services:$(pwd)" \
      .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
      --extractor agent \
      --output-dir reports/relation_feasibility/2026-07-05-pr25-current-run'"$run"
  done
  ```

- [ ] **Step 5: Run candidate model three times**

  Operator requirement: set `ARTANA_STRONGER_MODEL_CANDIDATE` to an approved model id before running this step. The plan does not assume the stronger model will win.

  ```bash
  test -n "${ARTANA_STRONGER_MODEL_CANDIDATE:-}"
  for run in 1 2 3; do
    bash -lc 'set -a; source .env.postgres; set +a; \
      export ARTANA_AI_EVIDENCE_EXTRACTION_MODEL="'"$ARTANA_STRONGER_MODEL_CANDIDATE"'"; \
      PYTHONPATH="$(pwd)/services:$(pwd)" \
      .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
      --extractor agent \
      --output-dir reports/relation_feasibility/2026-07-05-pr25-candidate-run'"$run"
  done
  ```

- [ ] **Step 6: Run repeated-readiness gate for the candidate stack**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
    --report reports/relation_feasibility/2026-07-05-pr25-current-run1 \
    --report reports/relation_feasibility/2026-07-05-pr25-current-run2 \
    --report reports/relation_feasibility/2026-07-05-pr25-current-run3 \
    --fail-on-not-ready \
    --output-dir reports/relation_feasibility_readiness/2026-07-05-pr25-current
  ```

  Repeat for candidate runs only if all safety hard failures are `0`.

- [ ] **Step 7: Run cross-model failure attribution**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
    --report current=reports/relation_feasibility/2026-07-05-pr25-current-run1 \
    --report current=reports/relation_feasibility/2026-07-05-pr25-current-run2 \
    --report current=reports/relation_feasibility/2026-07-05-pr25-current-run3 \
    --report candidate=reports/relation_feasibility/2026-07-05-pr25-candidate-run1 \
    --report candidate=reports/relation_feasibility/2026-07-05-pr25-candidate-run2 \
    --report candidate=reports/relation_feasibility/2026-07-05-pr25-candidate-run3 \
    --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr25-model-comparison
  ```

- [ ] **Step 8: Adoption rule**

  A stronger model can become the recommended config only if all are true:

  - worst-run trusted readiness improves or remains passing
  - low-value review recall improves without weak-claim trusted leakage
  - false positives do not increase materially
  - wrong verified CURIE links stay `0`
  - fallback and invalid-agent cases stay `0`
  - cost and latency are acceptable for the intended workflow

**Merge gate:** PR25 is mergeable when the repo can prove repeatability and can answer whether the stronger model helped with evidence, not opinion.

## PR26: Graph Promotion Fail-Closed Enforcement

**Findings closed:** F-08.

**Root cause:** Audit readiness is not enough. Graph DB must reject unsafe trusted AI evidence even if Evidence API or a future script accidentally labels it trusted.

**Files:**

- Modify: `services/artana_evidence_db/validation/trusted_evidence_floor.py`
- Modify: `services/artana_evidence_db/validation/claim_ai_evidence_validation.py`
- Modify: `services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py`
- Modify: `services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py`
- Modify: `services/artana_evidence_api/tests/unit/test_proposal_actions.py`
- Create: `docs/validation/reports/2026-07-05-pr26-graph-promotion-fail-closed-summary.md`

- [ ] **Step 1: Add graph-side failing tests**

  Add tests proving trusted AI evidence is rejected when:

  - `fallback_output_used is True`
  - `agent_extraction_completed is not True`
  - `review_status == "review_only"`
  - `review_reason_codes` contains any weak/hedged reason
  - `entity_linking.subject.status != "linked"`
  - `entity_linking.object.status != "linked"`
  - `support_verification.support != "ENTAILS"`
  - `trust_floor_failures` contains any non-empty value

- [ ] **Step 2: Tighten `trusted_evidence_floor_issue`**

  Add a review-status floor:

  ```python
  def _review_status_floor_issue(metadata: JSONObject) -> TrustedEvidenceFloorIssue | None:
      if metadata.get("review_status") == "review_only":
          return TrustedEvidenceFloorIssue(
              message="Trusted AI evidence cannot use review-only relation evidence.",
              next_action="route_to_human_review",
              next_action_reason=(
                  "Weak, hedged, or low-value evidence must stay in the review lane."
              ),
          )
      return None
  ```

  Call it before entity link floors:

  ```python
  return (
      _agent_path_floor_issue(metadata)
      or _grounding_floor_issue(metadata)
      or _support_floor_issue(metadata)
      or _failed_trust_floors_issue(metadata)
      or _review_status_floor_issue(metadata)
      or _entity_link_floor_issue(metadata)
  )
  ```

- [ ] **Step 3: Run graph validation tests**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
    services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py \
    -q
  ```

- [ ] **Step 4: Run graph service checks**

  ```bash
  make graph-service-checks
  ```

- [ ] **Step 5: Adversarial review prompt**

  ```text
  Review PR26 from the perspective of a malicious or buggy Evidence API client. Try to submit trusted AI relation evidence with fallback traces, review-only status, model-only CURIE hints, missing support verification, or failed trust floors. Verify Graph DB rejects it.
  ```

**Merge gate:** PR26 is mergeable when Graph DB independently rejects unsafe trusted AI evidence and all existing graph validation tests still pass.

## PR27: Benchmark V3 And Generated Proof Docs

**Findings closed:** F-09, F-10.

**Root cause:** The current fixture is a valuable regression seed but is too small and too curated to prove production biomedical value. Manual Markdown summaries can also drift from JSON reports.

**Files:**

- Create: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Create: `scripts/validation/relation_feasibility/fixture_validation.py`
- Create: `scripts/generate_relation_feasibility_summary.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `tests/unit/test_control_files.py`
- Create: `tests/unit/test_relation_feasibility_fixture_validation.py`
- Create: `tests/unit/test_generate_relation_feasibility_summary.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr27-benchmark-v3-doc-proof-summary.md`

- [ ] **Step 1: Add fixture validation rules**

  `fixture_validation.py` must reject:

  - duplicate `case_id`
  - missing support sentence
  - gold relation without subject/object/relation type
  - trusted high-value gold row with missing subject or object CURIE unless explicitly marked review-only
  - negative-control case with gold relations
  - low-value weak case missing a `value_level`

- [ ] **Step 2: Add v3 fixture coverage**

  `biomedical_relation_goldset_v3.json` must include at least:

  - 20 high-value specific relation cases
  - 10 low-value review-only weak/hedged cases
  - 10 negative controls
  - oncology drug response
  - rare disease gene-to-phenotype
  - variant-to-disease risk
  - pathway regulation
  - biomarker and treatment response
  - long-document chunking case
  - adversarial near-miss where entities appear but relation is negated

- [ ] **Step 3: Generate docs from JSON**

  `generate_relation_feasibility_summary.py` must read:

  - relation feasibility JSON
  - failure attribution JSON
  - readiness JSON when present

  It must write a Markdown summary containing:

  - branch
  - commit
  - command
  - model label
  - fixture path
  - artifact hashes
  - key metrics
  - blocking reasons
  - remaining failures

- [ ] **Step 4: Run fixture and summary tests**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_fixture_validation.py \
    tests/unit/test_generate_relation_feasibility_summary.py \
    tests/unit/test_control_files.py \
    -q
  ```

- [ ] **Step 5: Run v2 and v3 audits separately**

  ```bash
  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
    --output-dir reports/relation_feasibility/2026-07-05-pr27-v2-run1'
  ```

  ```bash
  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
    --output-dir reports/relation_feasibility/2026-07-05-pr27-v3-run1'
  ```

**Merge gate:** PR27 is mergeable when v3 fixture validation passes, generated summaries are reproducible from JSON, and the docs clearly separate seed-fixture readiness from broader production confidence.

## Final Trusted-Graph Readiness Gate

After PR22A through PR27 are merged or stacked together, run:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-final-readiness-run1'
```

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-final-readiness-run2'
```

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-final-readiness-run3'
```

Then:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-05-final-readiness-run1 \
  --report reports/relation_feasibility/2026-07-05-final-readiness-run2 \
  --report reports/relation_feasibility/2026-07-05-final-readiness-run3 \
  --fail-on-not-ready \
  --output-dir reports/relation_feasibility_readiness/2026-07-05-final-readiness
```

Trusted graph readiness can be stated only if this final readiness gate exits `0`, graph service checks pass, and the generated final docs match the JSON artifacts.

## Progress Checklist

- [ ] PR22A fixes single-run verdict contract.
- [ ] PR22A live-agent run proves old all-gold endpoint blocker is gone.
- [ ] PR23 captures missed low-value review cases without trusted leakage.
- [ ] PR24 gives every remaining endpoint gap a verified or review-only decision.
- [ ] PR25 proves repeatability across at least three strict live-agent runs.
- [ ] PR25 answers stronger-model value with A/B evidence.
- [ ] PR26 proves Graph DB rejects unsafe trusted AI evidence.
- [ ] PR27 expands benchmark breadth and makes summary docs generated/checkable.
- [ ] Final readiness gate passes on worst-run metrics.
- [ ] `make service-checks` passes.
- [ ] Progress tracker contains links to every report artifact.
