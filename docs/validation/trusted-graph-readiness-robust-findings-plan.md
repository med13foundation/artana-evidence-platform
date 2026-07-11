# Trusted Graph Readiness Robust Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Robustly close every known finding that blocks Artana Evidence live-agent output from safe trusted-graph promotion.

**Architecture:** Treat the live agent as a hypothesis generator, not as the trust authority. Evidence API owns extraction, grounding, support verification, value adjudication, and audit telemetry. Graph DB owns final promotion enforcement, relation dictionary governance, provenance, and fail-closed trust policy. Validation scripts own reproducible scorecards and must never count deterministic fallback as trusted evidence.

**Tech Stack:** Python, FastAPI service modules, Pydantic models, pytest, ruff, relation feasibility audits, failure attribution reports, strict live-agent runs, local verified dictionaries, ontology-backed grounding fixtures, graph service promotion tests, Postgres service checks, and repeated-run readiness gates.

---

## Source Evidence

This plan starts from the latest PR20 strict live-agent run:

- `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr20-run4/relation_feasibility_failure_analysis_report.md`
- `docs/validation/reports/2026-07-05-pr20-qualifier-precision-summary.md`

Current state:

| Gate | Current value | Merge-ready target | Status |
|---|---:|---:|---|
| Strict live-agent cases completed | 30/30 | 30/30 | Passing |
| Fallback cases | 0 | 0 | Passing |
| Invalid strict-agent cases | 0 | 0 | Passing |
| Negative-control leakage | 0 | 0 | Passing |
| Raw unknown relation surfaces | 0 | 0 | Passing |
| Wrong verified CURIE links | 0 | 0 | Passing |
| Completed-agent precision | 0.9500 | >= 0.8000 | Passing |
| Completed-agent recall | 0.7600 | >= 0.6000 | Passing |
| Completed-agent valuable rate | 0.9500 | >= 0.7000 | Passing |
| High-value recall | 0.9500 | >= 0.8500 | Passing |
| Trusted high-value recall | 0.5500 | >= 0.8500 | Blocking |
| Generic relation rate | 0.0500 | <= 0.0500 hard max, prefer < 0.0500 | At ceiling |
| Verified CURIE-linked gold endpoint rate | 0.8108 | >= 0.9500 | Blocking |
| Repeatability | one latest strict run | at least three strict runs | Blocking |
| Graph promotion enforcement | not proven end to end | fail closed | Blocking |

The important conclusion is that the system is no longer blocked by basic agent execution. It is blocked by proof quality: verified endpoint grounding, trusted high-value recall, run variance, graph promotion enforcement, and benchmark breadth.

## Non-Negotiable Readiness Contract

Trusted graph readiness is true only when all of these are true across repeated strict live-agent runs:

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
- worst-run `completed_agent_valuable_rate >= 0.7000`
- worst-run `generic_relation_rate <= 0.0500`
- worst-run `curie_linked_gold_endpoint_rate >= 0.9500`
- graph promotion rejects any AI relation missing verified endpoints, approved relation type, entailing evidence support, grounded support sentence, provenance, no-fallback trace, and review status compatible with trusted promotion

These thresholds may be raised after the system becomes stable. They must not be lowered to create a green report.

## Agile Execution Loop

Every PR lane must follow the same loop:

1. Select one finding or one tightly coupled finding group from the ledger.
2. Write the failing test first.
3. Run the focused test and capture the expected failure.
4. Implement the smallest first-principles fix at the owning service boundary.
5. Run the focused test until green.
6. Run the relevant boundary checks for the changed service.
7. Run `make relation-feasibility-quality-gate`.
8. Run one strict live-agent audit with `--extractor agent`.
9. Run failure attribution on the new report.
10. Request adversarial review against the diff, scorecard, and failure attribution.
11. Fix every valid adversarial finding.
12. Run `git diff --check` and `make service-checks`.
13. Update `docs/validation/evidence-excellence-progress-tracker.md`.
14. Add a dated evidence summary under `docs/validation/reports/`.
15. Commit only after tests, live evidence, adversarial review, and docs agree.

Strict live-agent audit template:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run1'
```

Failure attribution template:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run1/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-05-pr21-verified-grounding-closure-run1
```

Final repeated-run readiness template:

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

| ID | Finding | First-principles root cause | Owning PR | Robust closure evidence |
|---|---|---|---|---|
| F-01 | Verified CURIE-linked endpoint rate is `0.8108`, below `0.9500`. | The linker correctly refuses raw model hints, but the verified grounding layer does not cover recurring pathway, process, event, phenotype, and response labels. | PR21, PR23, PR24 | PR21 must improve verified endpoint recovery without wrong links; full closure requires worst-run verified CURIE-linked endpoint rate `>= 0.9500` and wrong verified CURIE links `0`. |
| F-02 | Trusted high-value recall is `0.5500` while high-value recall is `0.9500`. | Many high-value relations are found, but they cannot become trusted because one or both endpoints lack verified identifiers. | PR21 | Trusted high-value recall is `>= 0.8500`, and every trusted match has completed-agent provenance plus verified subject and object IDs. |
| F-03 | `MAPK signaling`, `homologous recombination DNA repair`, and `cardiac septal development` appear only as unverified model hints. | Model-proposed CURIEs are intentionally untrusted until confirmed by curated records or allowed ontology grounding. | PR21 | These labels link through verified curation and raw hints remain untrusted until confirmed. |
| F-04 | `aggressive tumor growth`, `ERK phosphorylation`, and `response to pembrolizumab` still have missing CURIE policy. | Composite and event-like endpoint labels need typed grounding rules, not generic text matching. | PR21 | Each label has a documented review-only abstention that blocks trusted promotion. |
| F-05 | The `BRCA1 loss SENSITIZES_TO cisplatin` high-value claim is run-variant. | The live agent can select a weaker surrounding association instead of the valuable drug-sensitivity claim. | PR22 and PR24 | The claim is recovered repeatably or withheld from trusted promotion unless consensus confirms it. |
| F-06 | `BRCA1 loss ASSOCIATED_WITH DNA repair defects` can survive as an entailed false positive. | Entailment alone is insufficient; the system also needs value-aware claim adjudication against more specific sibling claims. | PR22 | Locally true but lower-value sibling relations become review-only or are pruned when a higher-value supported relation is present. |
| F-07 | Generic relation rate is at the hard ceiling, `0.0500`. | A single broad relation can still pass quality filters under live-agent variance. | PR22 | Worst-run generic relation rate stays below or at `0.0500`, with operational target below `0.0500`, and high-value recall does not regress. |
| F-08 | Low-value hedged gold rows have `0.0000` low-value review recall. | Trusted extraction intentionally filters weak claims, but the product still needs a separate review-only capture lane for useful weak evidence. | PR23 | Low-value review recall is measured and improves without allowing weak claims into trusted promotion. |
| F-09 | Repeatability is not proven. | The current scorecard is based on single latest strict runs, and live-agent output varies between runs. | PR24 | Three strict runs pass readiness on worst-run metrics, or non-repeatable relations are held for review. |
| F-10 | Stronger-model benefit is unknown. | There is no controlled A/B harness comparing current and candidate models with identical fixtures, thresholds, cost, and failure attribution. | PR24 | A/B report includes at least three runs per model, worst-run metrics, mean metrics, cost, latency, and model-specific failure clusters. |
| F-11 | Runtime graph promotion is not proven to enforce the audit trust floor. | Audit readiness and graph promotion are separate boundaries; a green report must not be the only protection. | PR25 | Graph DB rejects any trusted AI relation missing verified endpoints, approved relation type, entailing support, provenance, or no-fallback trace. |
| F-12 | Benchmark confidence is still limited. | The current fixture is a strong regression suite but not a broad blinded biomedical corpus. | PR26 | A larger fixture adds oncology, rare disease, variants, pathways, drug response, negative controls, long documents, and adversarial near-misses. |
| F-13 | Evidence docs can drift from generated report JSON. | Several summaries are manually copied from live reports. | PR27 | Summary docs are generated or checked from report JSON and include artifact hashes. |

## PR21: Verified Grounding And Review-Only Abstention

Suggested branch: `alvaro/evidence-pr21-verified-grounding-closure`

**Findings addressed:** F-01, F-02, F-03, F-04. PR21 is expected to materially
improve these findings, not by itself prove final trusted-graph readiness.

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/entity_grounding/verified_dictionary.py`
- Create: `services/artana_evidence_api/document_extraction_support/entity_grounding/contracts.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- Modify: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Create: `scripts/validation/relation_feasibility/relation_matching.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`
- Create: `services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr21-verified-grounding-summary.md`

**Steps:**

- [ ] Write failing tests for verified labels from the PR20 gap report: `MAPK signaling`, `homologous recombination DNA repair`, `cardiac septal development`, and `ERK phosphorylation`.
- [ ] Write failing tests for review-only abstention labels: `aggressive tumor growth`, `response to pembrolizumab`, and any broad response or phenotype label that cannot be safely represented by one approved CURIE.
- [ ] Split verified records out of `entity_curie_linking.py` into `verified_entity_dictionary.py` so the linker stays small and single-purpose.
- [ ] Add typed grounding contracts that distinguish `verified`, `model_hint_only`, `review_only`, `ambiguous`, `unsupported_namespace`, and `missing`.
- [ ] Update `entity_curie_linking.py` so raw model CURIE hints never produce `trusted_identifier == True` without verified dictionary or approved ontology confirmation.
- [ ] Update the gold fixture only for endpoints with safe approved identifiers. Keep unsafe composite labels without trusted gold CURIEs and record the abstention reason.
- [ ] Strengthen scoring tests so trusted high-value recall counts only completed-agent candidates with verified subject and object matches.
- [ ] Run focused grounding tests.

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
  services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

- [ ] Run `make relation-feasibility-quality-gate`.
- [ ] Run the PR21 strict live-agent audit and failure attribution.
- [ ] Run adversarial review focused on false verified links, over-broad ontology links, and silent model-hint trust.
- [ ] Run `make service-checks`.

**Merge gate:** PR21 is mergeable when verified endpoint rate and trusted high-value recall improve materially, wrong verified links remain `0`, unsafe labels abstain explicitly, and no fallback path is counted as trusted evidence.

## PR22: Value-Aware Precision And Generic Relation Suppression

Suggested branch: `alvaro/evidence-pr22-value-aware-precision`

**Findings closed:** F-05, F-06, F-07

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_specificity_pruning.py`
- Create: `services/artana_evidence_api/document_extraction_support/relation_value_adjudication.py`
- Modify: `services/artana_evidence_api/document_extraction_support/evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py`
- Create: `services/artana_evidence_api/tests/unit/test_relation_value_adjudication.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr22-value-aware-precision-summary.md`

**Steps:**

- [ ] Write a regression test where `BRCA1 loss SENSITIZES_TO cisplatin` is supported and `BRCA1 loss ASSOCIATED_WITH DNA repair defects` is also entailed; expected result is that the sensitivity claim stays trusted-eligible and the generic association becomes review-only.
- [ ] Add tests for context siblings where a broad `ASSOCIATED_WITH` claim competes with a specific `SENSITIZES_TO`, `RESISTANT_TO`, `TARGETS`, `BIOMARKER_FOR`, `ACTIVATES`, `INHIBITS`, or `REGULATES` claim in the same evidence window.
- [ ] Implement `relation_value_adjudication.py` as a focused module that ranks candidate claims by relation specificity, endpoint specificity, support sentence alignment, and value level.
- [ ] Make quality filtering use adjudication output without embedding ranking rules directly into the filter.
- [ ] Ensure generic relations can remain review candidates when clinically useful but cannot count toward trusted high-value recall when a more specific sibling exists.
- [ ] Run focused quality and adjudication tests.

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_relation_value_adjudication.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

- [ ] Run `make relation-feasibility-quality-gate`.
- [ ] Run strict live-agent audit and failure attribution.
- [ ] Run adversarial review focused on hidden recall loss and over-pruning valid separate claims.
- [ ] Run `make service-checks`.

**Merge gate:** PR22 is mergeable when generic relation rate stays within the hard max, high-value recall does not regress below target, and locally true low-value siblings cannot be auto-promoted as trusted graph evidence.

## PR23: Low-Value Review-Only Evidence Lane

Suggested branch: `alvaro/evidence-pr23-low-value-review-lane`

**Findings closed:** F-08

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Create: `services/artana_evidence_api/document_extraction_support/review_only_candidate_policy.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Create: `services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr23-low-value-review-summary.md`

**Steps:**

- [ ] Write tests for hedged examples from the fixture: `may regulate`, `trend toward`, `possible biomarker`, and `correlated with`.
- [ ] Require these candidates to be represented as review-only with explicit hedge metadata instead of trusted relation evidence.
- [ ] Add scorecard rows for low-value review recall and weak-claim trust leakage.
- [ ] Ensure review-only candidates cannot satisfy trusted high-value recall or graph auto-promotion gates.
- [ ] Run focused review-lane tests.

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

- [ ] Run `make relation-feasibility-quality-gate`.
- [ ] Run strict live-agent audit and failure attribution.
- [ ] Run adversarial review focused on weak evidence leaking into trusted promotion.
- [ ] Run `make service-checks`.

**Merge gate:** PR23 is mergeable when weak but potentially useful evidence is visible to reviewers while trusted promotion remains unchanged and strict.

## PR24: Repeatability, Consensus, And Stronger-Model A/B

Suggested branch: `alvaro/evidence-pr24-repeatability-model-ab`

**Findings closed:** F-05, F-09, F-10

**Files:**

- Modify: `scripts/run_relation_feasibility_audit.py`
- Modify: `scripts/summarize_relation_readiness_failures.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Modify: `scripts/validation/relation_feasibility/readiness.py`
- Create: `scripts/validation/relation_feasibility/model_comparison.py`
- Create: `tests/unit/test_relation_feasibility_model_comparison.py`
- Modify: `tests/unit/test_relation_feasibility_readiness_gate.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr24-repeatability-model-ab-summary.md`

**Steps:**

- [ ] Add a model label and run label to each audit report so multiple runs can be compared without manual bookkeeping.
- [ ] Write tests proving the readiness gate evaluates worst-run metrics, not only averages.
- [ ] Write tests proving a non-repeatable high-value claim cannot be marked promotion-ready unless consensus policy accepts it.
- [ ] Add a model comparison report that includes precision, recall, high-value recall, trusted high-value recall, verified endpoint rate, generic rate, fallback count, invalid-agent count, cost if available, latency if available, and failure clusters.
- [ ] Run three strict audits for the current model.
- [ ] Run three strict audits for the candidate stronger model approved by the runtime configuration.
- [ ] Compare models using identical fixture version, thresholds, and report format.
- [ ] Do not switch production default model unless the stronger model improves worst-run trusted readiness without introducing wrong verified links, fallback, invalid completions, or unacceptable cost/latency.

Current-model template:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --model-label current \
  --output-dir reports/relation_feasibility/2026-07-05-pr24-current-run1'
```

Candidate-model template:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  export ARTANA_AI_EVIDENCE_EXTRACTION_MODEL="$ARTANA_STRONGER_MODEL_CANDIDATE"; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --model-label candidate \
  --output-dir reports/relation_feasibility/2026-07-05-pr24-candidate-run1'
```

- [ ] Run focused comparison tests.

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_model_comparison.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  -q
```

- [ ] Run `make relation-feasibility-quality-gate`.
- [ ] Run adversarial review focused on cherry-picked model wins, average-only claims, and hidden cost/latency tradeoffs.
- [ ] Run `make service-checks`.

**Merge gate:** PR24 is mergeable when the system has a repeatable readiness report and a defensible model policy. A stronger model can be adopted only as an evidence-backed configuration decision, not as a substitute for verification.

## PR25: Graph Promotion Hard Gate

Suggested branch: `alvaro/evidence-pr25-graph-promotion-hard-gate`

**Findings closed:** F-11

**Files:**

- Modify: `services/artana_evidence_db/graph_validation_service.py`
- Modify: `services/artana_evidence_db/relation_evidence_service.py`
- Modify: `services/artana_evidence_db/graph_repository.py`
- Modify: `services/artana_evidence_db/models.py`
- Modify: `services/artana_evidence_db/tests/unit/test_graph_validation_service.py`
- Create: `services/artana_evidence_db/tests/unit/test_trusted_relation_promotion_policy.py`
- Modify: `services/artana_evidence_db/tests/integration/test_relation_evidence_api.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr25-graph-promotion-hard-gate-summary.md`

**Steps:**

- [ ] Write tests proving graph promotion rejects AI relations with missing subject CURIE, missing object CURIE, model-only CURIE source, unapproved relation type, missing evidence sentence, non-entailing support, fallback trace, missing provenance, or review-only status.
- [ ] Add a single promotion-policy function that returns a decision envelope with reason codes instead of scattering checks across service methods.
- [ ] Ensure audit reason codes and graph rejection reason codes use the same vocabulary where possible.
- [ ] Preserve governance audit records for rejected promotions.
- [ ] Run graph focused tests.

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_db/tests/unit/test_graph_validation_service.py \
  services/artana_evidence_db/tests/unit/test_trusted_relation_promotion_policy.py \
  services/artana_evidence_db/tests/integration/test_relation_evidence_api.py \
  -q
```

- [ ] Run `make graph-service-checks`.
- [ ] Run `make service-checks`.
- [ ] Run adversarial review focused on bypass paths and metadata spoofing.

**Merge gate:** PR25 is mergeable when Graph DB fails closed even if Evidence API or an audit artifact incorrectly labels an unsafe AI relation as trusted.

## PR26: Blinded Benchmark Expansion

Suggested branch: `alvaro/evidence-pr26-blinded-benchmark-expansion`

**Findings closed:** F-12

**Files:**

- Modify: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Create: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Modify: `scripts/validation/relation_feasibility/fixtures.py`
- Modify: `scripts/run_relation_feasibility_audit.py`
- Create: `tests/unit/test_relation_feasibility_fixture_v3.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr26-blinded-benchmark-summary.md`

**Steps:**

- [ ] Add at least 60 total cases in v3 across oncology, rare disease, variants, pathways, drug response, phenotype links, long documents, negative controls, and adversarial near-misses.
- [ ] Require each gold relation to specify value level, support sentence, rationale, endpoint specificity expectation, relation specificity expectation, and trusted-promotion eligibility.
- [ ] Add fixture validation tests that fail on duplicate case IDs, missing support sentences, missing rationales, invalid relation types, unsupported value levels, and unsafe trusted labels without endpoint policy.
- [ ] Add negative controls that look semantically close but should produce no trusted relation.
- [ ] Add long-document cases where the valuable relation appears outside the first chunk.
- [ ] Run fixture validation tests.

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_fixture_v3.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

- [ ] Run `make relation-feasibility-quality-gate`.
- [ ] Run one strict live-agent audit against v3.
- [ ] Run failure attribution against v3.
- [ ] Run adversarial review focused on benchmark leakage, overly easy cases, and gold-label ambiguity.
- [ ] Run `make service-checks`.

**Merge gate:** PR26 is mergeable when v3 makes the readiness claim harder to game and the report clearly distinguishes v2 regression results from v3 broader-confidence results.

## PR27: Generated Evidence Reports And Drift Guard

Suggested branch: `alvaro/evidence-pr27-generated-evidence-reports`

**Findings closed:** F-13

**Files:**

- Create: `scripts/generate_relation_evidence_summary.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Modify: `scripts/validation/relation_feasibility/readiness.py`
- Create: `tests/unit/test_generate_relation_evidence_summary.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create: `docs/validation/reports/2026-07-05-pr27-generated-evidence-summary.md`

**Steps:**

- [ ] Write tests proving generated summaries read metrics from JSON instead of manual Markdown copies.
- [ ] Include artifact paths, SHA-256 hashes, branch, commit, fixture version, model label, and exact command in generated summaries.
- [ ] Fail generation when required metrics are missing.
- [ ] Add a doc check that compares selected summary metrics with report JSON.
- [ ] Run summary tests.

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_generate_relation_evidence_summary.py \
  -q
```

- [ ] Run `make relation-feasibility-quality-gate`.
- [ ] Run `make service-checks`.
- [ ] Run adversarial review focused on stale docs, copied metrics, and unverifiable evidence.

**Merge gate:** PR27 is mergeable when generated evidence reports can be trusted as a faithful view of the JSON artifacts.

## Final Readiness Drill

Suggested branch: `alvaro/evidence-final-trusted-graph-readiness`

**Depends on:** PR21, PR22, PR23, PR24, PR25, PR26, PR27

**Steps:**

- [ ] Rebase the final readiness branch on the merged stack.
- [ ] Run `make service-checks`.
- [ ] Run three strict live-agent audits on the final fixture version.
- [ ] Run failure attribution on each run.
- [ ] Run the repeated-run readiness gate with `--fail-on-not-ready`.
- [ ] Trigger adversarial review against the full stack, final reports, graph promotion tests, and generated evidence docs.
- [ ] Fix valid adversarial findings in the smallest owning PR or a final narrow patch.
- [ ] Update `docs/validation/evidence-excellence-progress-tracker.md` with final status.
- [ ] Generate final evidence summary from JSON artifacts.

**Final merge gate:** The system is trusted-graph ready only when repeated strict live-agent runs pass the readiness gate and Graph DB rejects unsafe trusted-promotion attempts independently of the audit report.

## Parallelization Plan

```text
PR21 verified grounding
  -> PR24 repeatability and model A/B
      -> final readiness drill

PR22 value-aware precision
  -> PR24 repeatability and model A/B
      -> final readiness drill

PR23 low-value review lane
  -> PR24 repeatability and model A/B
      -> final readiness drill

PR25 graph promotion hard gate
  -> final readiness drill

PR26 blinded benchmark expansion
  -> PR24 repeatability and model A/B
  -> final readiness drill

PR27 generated evidence reports
  -> final readiness drill
```

PR21, PR22, PR23, PR25, PR26, and PR27 can start in parallel if each branch is isolated. PR24 should consume PR21, PR22, PR23, and PR26 outputs before making model or consensus claims. The final readiness branch should merge only after PR24 and PR25 both pass.

## Stronger Model Decision Policy

A stronger model may improve extraction recall, relation specificity, and wording stability. It cannot by itself make the system trusted-graph ready, because trusted readiness depends on verified grounding, support entailment, graph promotion policy, and repeatability.

Use this decision table:

| Candidate result | Decision |
|---|---|
| Better recall but more wrong verified links | Reject for trusted promotion. |
| Better averages but worse worst-run metrics | Keep for review experiments only. |
| Better trusted high-value recall with fallback 0, invalid 0, wrong verified links 0, and acceptable cost/latency | Adopt behind configuration after PR24. |
| No material quality gain | Keep current model and invest in grounding, adjudication, and corpus quality. |
| Higher cost/latency with marginal quality gain | Keep as optional escalation for hard cases, not default extraction. |

## Progress Checklist

- [ ] PR21 closes verified grounding and trusted high-value recall gaps.
- [ ] PR22 closes generic/context false-positive precision gaps.
- [ ] PR23 captures low-value evidence as review-only without trusted leakage.
- [ ] PR24 proves repeatability and model policy through controlled A/B runs.
- [ ] PR25 enforces the same trust floor at Graph DB promotion.
- [ ] PR26 expands benchmark confidence with blinded v3 cases.
- [ ] PR27 prevents evidence-doc drift from JSON artifacts.
- [ ] Final readiness drill passes repeated strict live-agent gate and graph hard-gate validation.
