# Trusted Graph Readiness Findings Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every known finding that blocks Artana Evidence live-agent output from safe trusted-graph promotion.

**Architecture:** Keep the live agent as a hypothesis generator and make trust a code-enforced contract. Evidence API owns extraction, entity grounding, support verification, value adjudication, and audit reporting. Graph DB owns dictionary governance, relation constraints, provenance, and promotion hard gates. Validation scripts own repeated-run readiness evidence and must never treat deterministic fallback as trusted evidence.

**Tech Stack:** Python, FastAPI service modules, Pydantic contracts, pytest, ruff, relation feasibility audits, failure attribution reports, graph dictionary governance, verified entity dictionaries, local ontology fixtures, Postgres-backed service checks, and strict live-agent model runs.

---

## Baseline

This plan uses the current PR20 live-agent state as the baseline.

Source artifacts:

- `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr20-run4/relation_feasibility_failure_analysis_report.md`
- `docs/validation/reports/2026-07-05-pr20-qualifier-precision-summary.md`

Current live-agent scorecard:

| Gate | Current value | Target | Status |
|---|---:|---:|---|
| Verdict | RED | not RED | Blocking |
| Agent completed cases | 30 | 30 | Passing |
| Fallback cases | 0 | 0 | Passing |
| Invalid strict-agent cases | 0 | 0 | Passing |
| Negative-control leakage cases | 0 | 0 | Passing |
| Raw unknown candidate relation types | 0 | 0 | Passing |
| Raw unknown relation inventory surfaces | 0 | 0 | Passing |
| Wrong verified CURIE links | 0 | 0 | Passing |
| Completed-agent precision | 0.9500 | >= 0.8000 | Passing |
| Completed-agent recall | 0.7600 | >= 0.6000 | Passing |
| High-value recall | 0.9500 | >= 0.8500 | Passing |
| Trusted high-value recall | 0.5500 | >= 0.8500 | Blocking |
| Completed-agent valuable rate | 0.9500 | >= 0.7000 | Passing |
| Generic relation rate | 0.0500 | < 0.0500 | At ceiling |
| Verified CURIE-linked gold endpoint rate | 0.8108 | >= 0.9500 | Blocking |

Important interpretation:

- Runtime safety is in good shape: the strict live-agent path completes with no fallback, no invalid agent cases, no negative-control leakage, no raw unknown relation surfaces, and no wrong verified links.
- Trusted graph readiness is still blocked because the system cannot yet prove enough high-value claims with verified endpoint IDs.
- Stronger models may help candidate generation, spelling, and recall, but they cannot replace verified entity grounding, support verification, repeatability, and graph promotion policy.

## Closure Rules

Every lane in this plan must preserve these rules:

- Strict live-agent runs use `--extractor agent`.
- Deterministic fallback is allowed only for triage comparison and never counts as trusted readiness evidence.
- Model-suggested CURIEs are hints until the verified linker confirms them.
- Governed relation proposals are review artifacts until dictionary governance approves them.
- A relation is trusted only when it has verified endpoints, approved relation type, grounded evidence sentence, entailing support, provenance, no-fallback trace, and graph promotion acceptance.
- A lane is mergeable only after tests, live-agent report, failure attribution, adversarial review, and docs all tell the same story.

Required loop for every PR lane:

1. Write the failing regression test first.
2. Run the focused test and capture the failure.
3. Implement the smallest service-boundary fix.
4. Run the focused tests until green.
5. Run `make relation-feasibility-quality-gate`.
6. Run one strict live-agent audit for the lane.
7. Run failure attribution for the new report.
8. Ask an adversarial reviewer to attack the diff and report.
9. Fix valid adversarial findings.
10. Run `git diff --check` and `make service-checks`.
11. Update `docs/validation/evidence-excellence-progress-tracker.md`.
12. Add or update a dated summary in `docs/validation/reports/`.
13. Commit only after all gates are clean.

First strict live-agent command to run after PR21:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run1'
```

First failure attribution command to run after PR21:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run1/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr21-verified-grounding-closure-run1
```

Final readiness command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-05-final-readiness-run1 \
  --report reports/relation_feasibility/2026-07-05-final-readiness-run2 \
  --report reports/relation_feasibility/2026-07-05-final-readiness-run3 \
  --fail-on-not-ready \
  --output-dir reports/relation_feasibility_readiness/2026-07-05-final-readiness
```

## Finding Ledger

| ID | Finding | Root cause | Owning lane | Done when |
|---|---|---|---|---|
| F-01 | Verified CURIE-linked gold endpoint rate is 0.8108, below 0.9500. | The verified linker still lacks coverage for recurring biological processes, molecular events, therapy responses, and phenotypes. | PR21 | Worst-run verified CURIE-linked endpoint rate is >= 0.9500 with wrong verified CURIE links still 0. |
| F-02 | Trusted high-value recall is 0.5500 even while high-value recall is 0.9500. | Many high-value matches are not trusted because one or both endpoints are not verified. | PR21 | Trusted high-value recall is >= 0.8500 and remains tied to completed-agent provenance and verified endpoint matches. |
| F-03 | Model CURIE hints for `MAPK signaling`, `homologous recombination DNA repair`, and `cardiac septal development` are not verified. | The verifier correctly refuses raw model hints, but no fixture-backed grounding source confirms the labels. | PR21 | Model hints are either confirmed by local curation or explicitly abstained with review-only metadata. |
| F-04 | Missing CURIEs remain for `aggressive tumor growth`, `ERK phosphorylation`, and `response to pembrolizumab`. | Composite and event-like endpoint labels are not represented in a typed grounding policy. | PR21 | Each label has an approved verified concept or a documented review-only abstention that blocks auto-promotion. |
| F-05 | `BRCA1 loss SENSITIZES_TO cisplatin` is still run-variant. | The live agent can choose a weaker generic association instead of the valuable drug sensitivity relation. | PR24 | Run3 recovered the claim, but run4 missed it; consensus must keep non-repeatable claims review-only or recover them repeatably. |
| F-06 | `BRCA1 loss ASSOCIATED_WITH DNA repair defects` is still run-variant. | The relation is locally entailed but less valuable than the gold sensitivity claim. | PR24 | Run3 false positives were 0, but run4 had this false positive; consensus/value adjudication must prevent trusted promotion. |
| F-07 | Generic relation rate is back at the ceiling, 0.0500. | A single generic association can still survive precision filters under live-agent variance. | PR22 and PR24 | Worst-run generic relation rate is below 0.0500 while high-value recall does not regress. |
| F-08 | Low-value weak or hedged gold cases are not captured as review candidates. | The trusted path intentionally filters hedged claims, but the review queue lacks a separate low-value capture path. | PR23 | Low-value review recall is measured separately and review-only captures do not count as trusted promotion. |
| F-09 | Repeatability is not proven after PR20. | Current evidence is a single strict run, and live extraction can vary. | PR24 | At least three strict runs pass readiness on worst-run metrics, or non-repeatable claims are withheld from promotion. |
| F-10 | Stronger-model benefit is unknown. | There is no controlled A/B run comparing the current configured model with a stronger candidate under the same gates. | PR24 | A/B report includes three runs per model, quality deltas, cost, latency, and failure attribution. |
| F-11 | Runtime graph promotion is not proven to enforce the same trust floor as the audit. | Validation scripts and graph promotion policy are separate boundaries. | PR25 | Graph DB rejects every AI trusted relation missing verified endpoints, entailing support, approved relation type, provenance, or no-fallback trace. |
| F-12 | Benchmark confidence is still limited. | The current goldset is a strong regression seed but not a production-scale biomedical validation corpus. | PR26 | A larger blinded corpus covers oncology, rare disease, variants, pathways, drug response, negative controls, and long documents. |
| F-13 | Validation documents can drift from generated report metrics. | Some summary fields are copied manually after runs. | PR27 | Summary docs are generated or checked from JSON metrics and include artifact hashes. |

## PR21: Verified Entity Grounding Closure

Suggested branch: `alvaro/evidence-pr21-verified-grounding-closure`

**Goal:** Close F-01 through F-04 by moving verified endpoint recovery above the readiness threshold without trusting raw model hints.

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/entity_grounding_contracts.py`
- Create: `services/artana_evidence_api/document_extraction_support/verified_entity_dictionary.py`
- Create: `services/artana_evidence_api/document_extraction_support/local_ontology_grounding.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Create: `services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py`
- Create: `services/artana_evidence_api/tests/unit/test_local_ontology_grounding.py`
- Modify: `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Write failing tests for current CURIE gaps**

  Add these tests to `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`:

  ```python
  def test_verified_linker_confirms_mapk_signaling_instead_of_trusting_model_hint() -> None:
      link = normalize_entity_curie(
          "GO:0000165",
          label="MAPK signaling",
          source="model",
      )

      assert link.status == "linked"
      assert link.source == "verified_linker"
      assert link.model_hint_curie == "GO:0000165"
      assert link.to_metadata()["trusted_identifier"] is True


  def test_unapproved_composite_response_abstains_from_trusted_identifier() -> None:
      link = normalize_entity_curie(
          None,
          label="response to pembrolizumab",
          source="none",
      )

      assert link.status == "unlinked"
      assert link.source == "none"
      assert link.reason in {"missing_curie", "grounding_requires_review"}
      assert link.to_metadata()["trusted_identifier"] is False
  ```

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    -q
  ```

  Expected before implementation: the MAPK test fails because the current verified linker does not confirm the model hint, and the composite response policy is not explicit.

- [ ] **Step 2: Split grounding into focused units**

  Implement:

  - `EntityGroundingCandidate` dataclass in `entity_grounding_contracts.py`
  - `EntityGrounder` protocol in `entity_grounding_contracts.py`
  - `VerifiedEntityDictionary` in `verified_entity_dictionary.py`
  - `LocalOntologyGrounder` in `local_ontology_grounding.py`
  - final trust adjudication in `entity_curie_linking.py`

  Required behavior:

  - verified dictionary records can produce `source == "verified_linker"`
  - raw model hints cannot produce trusted identifiers by themselves
  - ambiguous matches abstain with `reason == "ambiguous_grounding"`
  - unsupported namespaces abstain with `reason == "unsupported_curie_prefix"`
  - composite labels abstain with `reason == "grounding_requires_review"` unless a local curation record explicitly approves them

- [ ] **Step 3: Add fixture-backed curation records**

  Add local verified records for the PR20 gap queue only after choosing an approved concept for each label:

  - `MAPK signaling`
  - `homologous recombination DNA repair`
  - `cardiac septal development`
  - `ERK phosphorylation`
  - `aggressive tumor growth`
  - `response to pembrolizumab`

  Each record must contain:

  ```python
  _VerifiedEntityRecord(
      label="MAPK signaling",
      curie="GO:0000165",
      entity_type="BIOLOGICAL_PROCESS",
      aliases=("MAPK pathway", "MAPK signaling pathway"),
      curation_status="approved_for_relation_feasibility_v2",
  )
  ```

  If a label cannot be safely approved, add an explicit review-only rule instead of a forced link.

- [ ] **Step 4: Prove scoring uses verified links only**

  Add or strengthen tests in `tests/unit/test_relation_feasibility_audit.py`:

  ```python
  def test_trusted_high_value_recall_requires_verified_endpoint_sources() -> None:
      cases = (
          _case(
              case_id="trusted_recall_model_hint_only",
              text="MED13 activates MAPK signaling.",
              gold=(
                  GoldRelation(
                      subject="MED13",
                      relation_type="ACTIVATES",
                      object="MAPK signaling",
                      support_sentence="MED13 activates MAPK signaling.",
                      value_level="high",
                      rationale="High-value pathway activation.",
                      subject_curie="HGNC:22474",
                      object_curie="GO:0000165",
                  ),
              ),
          ),
      )

      def extractor(_: str) -> RelationExtractionResult:
          return RelationExtractionResult(
              relations=(
                  ExtractedRelation(
                      subject="MED13",
                      subject_curie="HGNC:22474",
                      subject_curie_source="model",
                      relation_type="ACTIVATES",
                      object="MAPK signaling",
                      object_curie="GO:0000165",
                      object_curie_source="model",
                      sentence="MED13 activates MAPK signaling.",
                  ),
              ),
              trace=ExtractionTrace(
                  extractor_mode="agent",
                  llm_candidate_status="completed",
              ),
          )

      report = run_feasibility_audit(cases=cases, extractor=extractor)

      assert report.summary.high_value_recall == 1.0
      assert report.summary.trusted_high_value_recall == 0.0
      assert report.summary.curie_linked_gold_endpoint_rate == 0.0
  ```

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
    services/artana_evidence_api/tests/unit/test_local_ontology_grounding.py \
    tests/unit/test_relation_feasibility_audit.py \
    -q
  ```

- [ ] **Step 5: Validate PR21**

  Run:

  ```bash
  make relation-feasibility-quality-gate
  make service-checks
  ```

  Then run strict live-agent audit and failure attribution.

  Merge target:

  - `curie_linked_gold_endpoint_rate >= 0.9500`
  - `trusted_high_value_recall >= 0.8500`
  - `wrong_verified_curie_link_count == 0`
  - `fallback_case_count == 0`

## PR22: Value Adjudication Backstop And Generic Relation Suppression

Suggested branch: `alvaro/evidence-pr22-value-adjudication`

**Goal:** Turn the PR20 value-adjudication fixes for F-05 through F-07 into a reusable backstop so repeatability runs cannot reintroduce generic/context trusted evidence.

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/relation_value_adjudication.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_specificity_pruning.py`
- Modify: `services/artana_evidence_api/document_extraction_support/evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py`
- Create: `services/artana_evidence_api/tests/unit/test_relation_value_adjudication.py`
- Modify: `services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Write failing tests for the remaining BRCA1 cases**

  Add to `services/artana_evidence_api/tests/unit/test_relation_value_adjudication.py`:

  ```python
  from artana_evidence_api.document_extraction_support.relation_value_adjudication import (
      RelationValueCandidate,
      adjudicate_relation_value,
  )


  def test_drug_response_claim_beats_generic_context_when_both_are_entailed() -> None:
      sentence = (
          "BRCA1 loss sensitizes tumors to cisplatin by impairing DNA repair."
      )

      decisions = adjudicate_relation_value(
          sentence=sentence,
          candidates=(
              RelationValueCandidate(
                  subject="BRCA1 loss",
                  relation_type="SENSITIZES_TO",
                  object="cisplatin",
              ),
              RelationValueCandidate(
                  subject="BRCA1 loss",
                  relation_type="ASSOCIATED_WITH",
                  object="DNA repair defects",
              ),
          ),
      )

      assert decisions["BRCA1 loss|SENSITIZES_TO|cisplatin"].trusted_priority == "high"
      assert decisions["BRCA1 loss|ASSOCIATED_WITH|DNA repair defects"].trusted_priority == "review_only"
      assert decisions["BRCA1 loss|ASSOCIATED_WITH|DNA repair defects"].reason == (
          "shadowed_by_more_specific_drug_response"
      )
  ```

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_relation_value_adjudication.py \
    -q
  ```

  Expected before implementation: the module or adjudication function does not exist.

- [ ] **Step 2: Implement value adjudication as a small pure module**

  Implement these rules:

  - `SENSITIZES_TO`, `CONFERS_RESISTANCE_TO`, `INHIBITS`, `ACTIVATES`, and `BIOMARKER_FOR` outrank same-sentence `ASSOCIATED_WITH` when the same endpoint is involved.
  - Generic `ASSOCIATED_WITH` is review-only when a more specific relation captures the same claim.
  - Context relations such as `DOWNSTREAM_OF` remain allowed when they are separate claims, not phrase shadows.
  - Adjudication annotates reason codes and does not silently delete candidates.

- [ ] **Step 3: Wire adjudication into extraction quality filtering**

  The filter should produce traceable decisions:

  - `accepted`
  - `quality_filtered`
  - `review_only`

  Preserve these reasons:

  - `dropped_subject_modifier`
  - `dropped_object_modifier`
  - `context_relation_shadowed_by_direct_mechanism`
  - `shadowed_by_more_specific_drug_response`
  - `generic_relation_shadowed_by_specific_relation`

- [ ] **Step 4: Validate PR22**

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_relation_value_adjudication.py \
    services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
    services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py \
    tests/unit/test_relation_feasibility_audit.py \
    -q

  make relation-feasibility-quality-gate
  make service-checks
  ```

  Merge target:

  - the BRCA1 sensitivity case remains recovered or review-only by consensus
  - generic relation rate is below 0.0500
  - completed-agent precision remains >= 0.9000 on the lane run
  - high-value recall remains >= 0.9000 on the lane run

## PR23: Low-Value Review Capture

Suggested branch: `alvaro/evidence-pr23-low-value-review-capture`

**Goal:** Close F-08 without weakening trusted graph promotion.

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/review_candidate_staging.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py`
- Modify: `scripts/validation/relation_feasibility/models.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Create: `services/artana_evidence_api/tests/unit/test_review_candidate_staging.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Write failing review-only tests**

  Add to `services/artana_evidence_api/tests/unit/test_review_candidate_staging.py`:

  ```python
  def test_hedged_biomarker_claim_is_review_only_not_trusted() -> None:
      staged = stage_review_candidate(
          subject="HRD score",
          relation_type="BIOMARKER_FOR",
          object="platinum sensitivity",
          evidence_sentence="HRD score was explored as a possible biomarker for platinum sensitivity.",
          support_status="HEDGED",
      )

      assert staged.governance_status == "requires_evidence_review"
      assert staged.trusted_promotion_eligible is False
      assert staged.reason == "hedged_evidence_review_only"
  ```

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_review_candidate_staging.py \
    -q
  ```

- [ ] **Step 2: Add review-only staging for hedged relation evidence**

  Stage weak claims when the evidence contains cues such as:

  - `may`
  - `possible`
  - `trend`
  - `correlated`
  - `linked to`
  - `explored as`

  Required behavior:

  - review-only candidates are visible in audit metrics
  - review-only candidates are not trusted graph evidence
  - low-value review recall is reported separately from trusted high-value recall

- [ ] **Step 3: Validate PR23**

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_review_candidate_staging.py \
    tests/unit/test_relation_feasibility_audit.py \
    -q

  make relation-feasibility-quality-gate
  make service-checks
  ```

  Merge target:

  - low-value review candidate count increases on weak cases
  - trusted high-value precision does not decrease
  - no review-only candidate becomes auto-promotion eligible

## PR24: Repeatability, Consensus, And Model A/B

Suggested branch: `alvaro/evidence-pr24-repeatability-model-policy`

**Goal:** Close F-09 and F-10 by proving whether a stronger model materially improves readiness and by preventing single-run variance from auto-promoting claims.

**Files:**

- Create: `scripts/run_relation_model_ab_audit.py`
- Create: `scripts/validation/relation_feasibility/model_ab.py`
- Create: `scripts/validation/relation_feasibility/consensus.py`
- Create: `tests/unit/test_relation_model_ab_audit.py`
- Create: `tests/unit/test_relation_feasibility_consensus.py`
- Modify: `scripts/validation/relation_feasibility/readiness.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`

- [ ] **Step 1: Write failing consensus tests**

  Add to `tests/unit/test_relation_feasibility_consensus.py`:

  ```python
  from scripts.validation.relation_feasibility.consensus import (
      ConsensusRun,
      ConsensusRunRelation,
      build_relation_consensus,
  )


  def test_consensus_requires_repeated_verified_claim_before_promotion() -> None:
      consensus = build_relation_consensus(
          runs=(
              ConsensusRun(
                  run_id="run1",
                  trusted_candidates=(
                      ConsensusRunRelation(
                          subject="BRCA1 loss",
                          relation_type="SENSITIZES_TO",
                          object="cisplatin",
                          verified_endpoints=True,
                      ),
                  ),
              ),
              ConsensusRun(run_id="run2", trusted_candidates=()),
              ConsensusRun(
                  run_id="run3",
                  trusted_candidates=(
                      ConsensusRunRelation(
                          subject="BRCA1 loss",
                          relation_type="ASSOCIATED_WITH",
                          object="DNA repair defects",
                          verified_endpoints=True,
                      ),
                  ),
              ),
          ),
          min_supporting_runs=2,
      )

      assert consensus.trusted_claims == ()
      assert consensus.review_only_claims[0].reason == "not_repeatable"
  ```

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_consensus.py \
    -q
  ```

- [ ] **Step 2: Add A/B runner**

  `scripts/run_relation_model_ab_audit.py` must accept:

  - `--current-model-env ARTANA_AI_EVIDENCE_EXTRACTION_MODEL`
  - `--candidate-model-env ARTANA_AI_EVIDENCE_STRONG_MODEL`
  - `--runs-per-model 3`
  - `--extractor agent`
  - `--output-dir reports/relation_model_ab/2026-07-05-pr24`

  It must write:

  - per-run report paths
  - mean metrics by model
  - worst-run metrics by model
  - estimated cost when the provider reports usage
  - latency by run
  - failure attribution by model group

- [ ] **Step 3: Add model decision policy**

  Production model default can change only when:

  - candidate model improves worst-run readiness or trusted high-value recall
  - candidate model does not increase wrong verified links, fallback, invalid agent, or negative leakage
  - cost and latency are acceptable for the product workflow
  - three-run readiness is better than the current model

  If the stronger model improves recall but hurts precision, keep it as a candidate generator behind consensus and reranking rather than switching defaults.

- [ ] **Step 4: Validate PR24**

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_model_ab_audit.py \
    tests/unit/test_relation_feasibility_consensus.py \
    tests/unit/test_relation_feasibility_readiness_gate.py \
    -q

  make relation-feasibility-quality-gate
  make service-checks
  ```

  Merge target:

  - three-run readiness report exists for the current model
  - candidate stronger-model result exists or is explicitly blocked by model access
  - model decision is evidence-based and does not lower thresholds

## PR25: Graph Promotion Hard Gate

Suggested branch: `alvaro/evidence-pr25-graph-promotion-hard-gate`

**Goal:** Close F-11 by enforcing trusted graph readiness at the graph service boundary.

**Files:**

- Modify: `services/artana_evidence_db/graph_validation_service.py`
- Modify: `services/artana_evidence_db/relation_auto_promotion.py`
- Modify: `services/artana_evidence_db/claim_evidence_models.py`
- Modify: `services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py`
- Modify: `services/artana_evidence_db/tests/unit/test_graph_validation_service.py`
- Modify: `services/artana_evidence_db/tests/integration/test_relation_promotion_policy.py`

- [ ] **Step 1: Write failing graph rejection tests**

  Add to `services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py`:

  ```python
  def test_ai_relation_without_verified_endpoint_is_rejected_from_trusted_promotion() -> None:
      decision = evaluate_relation_auto_promotion(
          relation=ai_relation(
              subject_curie=None,
              object_curie="DrugBank:DB00515",
              relation_type="SENSITIZES_TO",
              support_status="ENTAILS",
              extraction_trace={"fallback_used": False},
          )
      )

      assert decision.promote is False
      assert "missing_verified_subject_identifier" in decision.blocking_reasons
  ```

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py \
    -q
  ```

- [ ] **Step 2: Enforce promotion contract**

  Promotion must require:

  - verified subject identifier
  - verified object identifier
  - approved relation type
  - dictionary constraint compatibility
  - grounded evidence sentence
  - support status `ENTAILS`
  - provenance source ID
  - no fallback in extraction trace
  - not review-only
  - not governed proposal unless approved by dictionary governance

- [ ] **Step 3: Validate PR25**

  Run:

  ```bash
  make graph-service-test
  make graph-service-checks
  make service-checks
  ```

  Merge target:

  - graph DB rejects every untrusted AI relation even if API metadata tries to mark it trusted
  - audit readiness and graph promotion policy use the same trust floor

## PR26: Blinded Benchmark Expansion

Suggested branch: `alvaro/evidence-pr26-blinded-benchmark-expansion`

**Goal:** Close F-12 by making readiness evidence statistically harder to game.

**Files:**

- Modify: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Create: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Create: `scripts/validation/relation_feasibility/fixtures/README.md`
- Modify: `tests/unit/test_relation_feasibility_fixtures.py`
- Modify: `scripts/run_relation_feasibility_audit.py`

- [ ] **Step 1: Add fixture validation tests**

  Add tests that require every fixture case to include:

  - `case_id`
  - source text
  - value level
  - gold relation type
  - subject and object labels
  - support sentence
  - endpoint CURIE or explicit review-only grounding decision
  - negative-control label when applicable

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_fixtures.py \
    -q
  ```

- [ ] **Step 2: Add blinded v3 case groups**

  Add at least these groups:

  - oncology resistance
  - oncology sensitivity
  - rare disease gene association
  - variant-drug response
  - pathway activation and inhibition
  - biomarker response
  - molecular event grounding
  - negative controls
  - long-document tail relations
  - hedged low-value review cases

  Minimum size for first v3 gate:

  - 80 high-value gold relations
  - 20 low-value review relations
  - 20 negative controls
  - at least 10 long-document cases

- [ ] **Step 3: Validate PR26**

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_fixtures.py \
    tests/unit/test_relation_feasibility_audit.py \
    -q

  make relation-feasibility-quality-gate
  make service-checks
  ```

  Merge target:

  - v2 remains the regression gate
  - v3 becomes the confidence gate
  - readiness reports name which fixture version they used

## PR27: Generated Evidence Reports And Final Readiness

Suggested branch: `alvaro/evidence-pr27-generated-evidence-readiness`

**Goal:** Close F-13 and prevent human-written docs from drifting away from JSON report truth.

**Files:**

- Create: `scripts/render_relation_feasibility_summary.py`
- Create: `scripts/validation/relation_feasibility/report_snapshot.py`
- Create: `tests/unit/test_relation_feasibility_report_snapshot.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Modify: `docs/validation/reports/README.md`

- [ ] **Step 1: Write failing snapshot tests**

  Add to `tests/unit/test_relation_feasibility_report_snapshot.py`:

  ```python
  import json


  def test_snapshot_renders_metrics_from_json_without_manual_numbers(tmp_path: Path) -> None:
      report_path = tmp_path / "relation_feasibility_report.json"
      report_path.write_text(
          json.dumps(
              {
                  "summary": {
                      "verdict": "RED",
                      "completed_agent_precision_against_gold": 0.95,
                      "trusted_high_value_recall": 0.55,
                      "curie_linked_gold_endpoint_rate": 0.8108,
                      "fallback_case_count": 0,
                  }
              }
          ),
          encoding="utf-8",
      )

      markdown = render_report_snapshot(report_path)

      assert "| Verdict | RED |" in markdown
      assert "| Trusted high-value recall | 0.5500 |" in markdown
      assert "| Verified CURIE-linked gold endpoint rate | 0.8108 |" in markdown
  ```

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_report_snapshot.py \
    -q
  ```

- [ ] **Step 2: Add report snapshot renderer**

  The renderer must:

  - read `relation_feasibility_report.json`
  - render a Markdown summary
  - include SHA-256 hashes for JSON and Markdown artifacts
  - list blocking reasons
  - list hard safety gates
  - list trusted graph readiness gates
  - refuse to render when required metrics are missing

- [ ] **Step 3: Validate final readiness**

  Run three strict live-agent audits after PR21 through PR26 are merged:

  ```bash
  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --output-dir reports/relation_feasibility/2026-07-05-final-readiness-run1'

  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --output-dir reports/relation_feasibility/2026-07-05-final-readiness-run2'

  bash -lc 'set -a; source .env.postgres; set +a; \
    PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
    --extractor agent \
    --output-dir reports/relation_feasibility/2026-07-05-final-readiness-run3'
  ```

  Then run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
    --report reports/relation_feasibility/2026-07-05-final-readiness-run1 \
    --report reports/relation_feasibility/2026-07-05-final-readiness-run2 \
    --report reports/relation_feasibility/2026-07-05-final-readiness-run3 \
    --fail-on-not-ready \
    --output-dir reports/relation_feasibility_readiness/2026-07-05-final-readiness
  ```

  Merge target:

  - readiness status is `ready`
  - source audit verdicts are not RED
  - all hard safety counts are zero
  - worst-run trusted metrics meet thresholds
  - graph promotion hard gate passes integration tests

## Merge Order

```text
Current PR20 closeout
  -> PR21 Verified Entity Grounding Closure
      -> PR22 Value Adjudication And Generic Relation Suppression
          -> PR23 Low-Value Review Capture
              -> PR24 Repeatability, Consensus, And Model A/B
                  -> PR25 Graph Promotion Hard Gate
                      -> PR26 Blinded Benchmark Expansion
                          -> PR27 Generated Evidence Reports And Final Readiness
```

PR21 and PR22 can be developed in parallel after PR20 is committed, but PR24 should consume their outputs before making a model decision. PR25 can begin with contract tests in parallel, but it should merge after PR21 through PR24 define the final trust floor.

## Progress Checklist

- [ ] PR20 committed with qualifier preservation, trusted high-value metric accounting, and service checks.
- [ ] PR21 closes verified endpoint and trusted high-value recall blockers.
- [ ] PR22 closes remaining high-value miss, generic false positive, and generic-rate ceiling risk.
- [ ] PR23 captures low-value hedged claims as review-only candidates.
- [ ] PR24 proves repeatability and stronger-model policy.
- [ ] PR25 enforces promotion trust floor in Graph DB.
- [ ] PR26 expands benchmark confidence.
- [ ] PR27 generates evidence docs from JSON and runs final readiness.

## Definition Of Trusted-Graph Ready

The system is trusted-graph ready only when the final readiness gate proves all of these across at least three strict live-agent runs:

- `fallback_case_count == 0`
- `invalid_agent_case_count == 0`
- `negative_control_leakage_count == 0`
- `raw_unknown_relation_type_count == 0`
- `raw_unknown_relation_type_surface_count == 0`
- `wrong_verified_curie_link_count == 0`
- worst-run `completed_agent_precision_against_gold >= 0.8000`
- worst-run `completed_agent_recall_against_gold >= 0.6000`
- worst-run `high_value_recall >= 0.8500`
- worst-run `trusted_high_value_recall >= 0.8500`
- worst-run `completed_agent_valuable_candidate_rate >= 0.7000`
- worst-run `generic_relation_rate < 0.0500`
- worst-run `curie_linked_gold_endpoint_rate >= 0.9500`
- graph promotion integration tests prove fail-closed behavior for untrusted AI evidence
