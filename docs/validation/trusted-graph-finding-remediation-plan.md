# Trusted Graph Finding Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every concrete blocker found by PR-17 failure attribution so live-agent relation extraction can safely feed trusted graph promotion.

**Architecture:** Treat the agent as a candidate generator, then verify every claim through focused gates. Entity grounding remains in `services/artana_evidence_api/document_extraction_support`; relation extraction and review accounting remain in the evidence API and validation harness; graph promotion enforcement remains in `services/artana_evidence_db`.

**Tech Stack:** Python, pytest, ruff, Artana Kernel model runtime, relation feasibility reports, graph dictionary governance, verified CURIE linking, repeatability readiness gates.

---

## Evidence Source

This plan is driven by the PR-17 failure attribution baseline:

- Failure attribution report:
  `reports/relation_feasibility_failure_analysis/2026-07-05-pr17-pr16-baseline/relation_feasibility_failure_analysis_report.md`
- Source strict live-agent reports:
  `/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run1/relation_feasibility_report.json`
  `/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run2/relation_feasibility_report.json`
  `/Users/alvaro/.codex/worktrees/b8c0/artana-evidence-platform-pr16/reports/relation_feasibility/2026-07-05-pr16-repeatability-run3/relation_feasibility_report.json`

Baseline result:

| Area | Count |
|---|---:|
| Repeated missed gold relation patterns | 9 |
| Repeated false-positive or non-gold candidate patterns | 7 |
| Canonical-supported CURIE gap patterns | 11 |
| Governed proposal candidates | 9 |
| Proposal gold matches | 4 |
| Proposal-eligible gold relations | 6 |
| Trusted proposal captures | 0 |

Current readiness blockers:

| Gate | Current worst or mean | Target |
|---|---:|---:|
| Completed-agent precision | worst 0.7619 | >= 0.8000 |
| High-value recall | worst 0.8000 | >= 0.8500 |
| Verified CURIE endpoint rate | worst 0.6486 | >= 0.9500 |
| Source audit verdicts | 3 RED reports | 0 RED reports |

Non-blocking hard-safety gates that must stay green:

- `fallback_case_count == 0`
- `invalid_agent_case_count == 0`
- `negative_control_leakage_count == 0`
- `raw_unknown_relation_type_count == 0`
- `raw_unknown_relation_type_surface_count == 0`
- `wrong_verified_curie_link_count == 0`

## First-Principles Policy

The trusted graph is only allowed to promote evidence that satisfies all of these conditions:

1. The live agent completed without fallback.
2. The evidence sentence is grounded in the source document.
3. The evidence sentence contains both relation endpoints.
4. The relation is entailed by the sentence.
5. The relation type is approved by dictionary governance.
6. The subject and object are verified by the linker or explicitly marked not-linkable with review evidence.
7. Governed proposals are staged for review, not counted as trusted auto-promotion.
8. A repeated-run readiness gate passes on worst-run metrics.

The system should never make a weak claim look strong by renaming buckets. A useful proposal is valuable, but it is still not trusted evidence until governance and verification approve it.

## PR Lane Summary

| Lane | Purpose | Primary metric moved |
|---|---|---|
| PR-18 | Verified entity grounding and CURIE policy | verified CURIE endpoint rate |
| PR-19 | Resistance and sensitivity relation semantics | high-value recall |
| PR-20 | Precision, directionality, and non-gold adjudication | completed-agent precision |
| PR-21 | Repeatability, model A/B, and consensus | worst-run readiness |
| PR-22 | Runtime graph promotion hard gate | promotion safety |

## Finding Ledger

Every finding below must be closed by a PR, an explicit "review-only by design" decision, or a benchmark correction with evidence.

### Missed Gold Relations

| ID | Failure pattern | Occurrences | Root cause | Owning lane | Done when |
|---|---|---:|---|---|---|
| M-01 | `complex_nsclc_alias`: `MET amplification CONFERS_RESISTANCE_TO erlotinib` | 3 | Valuable resistance relation is discovered as a governed proposal or typo instead of a trusted canonical relation. | PR-19 | Canonical or reviewed proposal credit recovers the relation in all three runs without raw unknown surfaces. |
| M-02 | `generic_sibling_met_resistance`: `MET amplification CONFERS_RESISTANCE_TO erlotinib` | 3 | Same resistance semantics gap, plus generic sibling pruning must prefer the specific resistance edge over broad association. | PR-19 | Specific resistance relation is recovered and generic sibling is suppressed or review-only. |
| M-03 | `generic_sibling_egfr_t790m_resistance`: `EGFR T790M CONFERS_RESISTANCE_TO gefitinib` | 3 | The benchmark previously used `CAUSES resistance to gefitinib`, while the model often proposed the more specific drug-resistance shape. | PR-19 | Governance chooses one representation and the harness credits the approved shape consistently. |
| M-04 | `generic_sibling_brca1_loss_cisplatin`: `BRCA1 loss SENSITIZES_TO cisplatin` | 1 | Subject qualifier is dropped or weakened from `BRCA1 loss` to `BRCA1`, changing the biological meaning. | PR-20 | Qualifier preservation test passes and `BRCA1 loss` is kept as the subject for sensitivity claims. |
| M-05 | `weak_akt_trend_survival`: `AKT activation ASSOCIATED_WITH reduced survival` | 3 | Low-value hedged association is intentionally filtered from trusted extraction, but the audit still records it as missed. | PR-20 | Low-value recall is reported separately as review-only and does not block trusted graph readiness. |
| M-06 | `weak_hrd_possible_biomarker`: `HRD score BIOMARKER_FOR platinum sensitivity` | 3 | Hedged biomarker language should be triage-only unless review accepts it. | PR-20 | Review-only candidate accounting captures it or records a deliberate low-value miss. |
| M-07 | `weak_il6_may_regulate_inflammation`: `IL6 REGULATES inflammatory signaling` | 3 | Hedged regulatory language should not be promoted as strong evidence. | PR-20 | Audit separates low-value review recall from trusted high-value recall. |
| M-08 | `weak_med13_may_link_chd`: `MED13 ASSOCIATED_WITH congenital heart disease` | 3 | Hedged disease association is low value and should not pressure trusted promotion. | PR-20 | Low-value handling is explicit in report and tracker. |
| M-09 | `weak_met_correlated_resistance`: `MET amplification ASSOCIATED_WITH resistance` | 3 | Generic resistance association is lower value than the specific drug-resistance relation. | PR-19 and PR-20 | Specific resistance relation is recovered; generic relation is review-only or pruned. |

### False Positives Or Non-Gold Candidates

| ID | Failure pattern | Occurrences | Root cause | Owning lane | Done when |
|---|---|---:|---|---|---|
| FP-01 | `EGFR T790M PROPOSE_NEW_RELATION_TYPE CONFERS_RESISTANCE_TO gefitinib` | 3 | Useful relation is in proposal space because `CONFERS_RESISTANCE_TO` is not approved in the extraction taxonomy. | PR-19 | Either approved as canonical or counted only in governed proposal recall with no precision penalty for trusted evidence. |
| FP-02 | `MET amplification PROPOSE_NEW_RELATION_TYPE CONFERS_RESISTANCE_TO erlotinib` | 3 | Same relation-type governance gap as FP-01. | PR-19 | Same as FP-01. |
| FP-03 | `ERK phosphorylation DOWNSTREAM_OF MEK` | 3 | The agent extracts a true context relation, but it is not the valuable drug-inhibition gold relation for this case. | PR-20 | Directionality and value-ranking keep this as non-promotable context when a better supported gold relation exists. |
| FP-04 | `MET amplification PROPOSE_NEW_RELATION_TYPE CONFOUNDS erlotinib` | 1 | Proposal spelling/semantics are not normalized before review accounting. | PR-19 | Unknown proposals are either normalized to approved review candidates or rejected with a deterministic reason. |
| FP-05 | `MET amplification PROPOSE_NEW_RELATION_TYPE CONFOERS_RESISTANCE_TO erlotinib` | 1 | Typo in a valuable proposal should not become an unknown relation surface. | PR-19 | Edit-distance or synonym guard maps this to `CONFERS_RESISTANCE_TO` only when safe; otherwise review queue records `proposal_normalization_failed`. |
| FP-06 | `MET amplification PROPOSE_NEW_RELATION_TYPE CONFERS_RESISTANCE_TO erlotinib` | 1 | Useful proposal is not yet approved canonical evidence. | PR-19 | Same as FP-01. |
| FP-07 | `BRCA1 SENSITIZES_TO cisplatin` | 1 | Subject is too broad; the evidence says `BRCA1 loss`, not all BRCA1. | PR-20 | Modifier preservation blocks broad subject substitution for loss-of-function and amplification claims. |

### CURIE Gaps

| ID | Endpoint | Cases | Occurrences | Root cause | Owning lane | Done when |
|---|---|---|---:|---|---|---|
| C-01 | `aggressive tumor growth`, missing CURIE | `complex_her2_amplification_growth` | 3 | Phenotype/process label is not grounded by the current verified dictionary. | PR-18 | Linker either verifies an approved phenotype/process CURIE or marks the endpoint ungroundable and excludes it from auto-promotion. |
| C-02 | `MAPK signaling`, model hint `GO:0000165` | `complex_ret_variant_alias` | 3 | Verified linker lacks pathway/process records and treats model GO IDs as untrusted hints. | PR-18 | `MAPK signaling` links through verified linker, not raw model trust. |
| C-03 | `MAPK signaling`, model hint `GO:0000165` | `long_document_tail_relation_braf` | 3 | Same MAPK verified-linking gap as C-02, with long-document tail coverage. | PR-18 | Long-document candidate keeps the verified MAPK link when the relation is near the tail. |
| C-04 | `MAPK signaling`, model hint `GO:0000165` | `strong_braf_v600e_activates_mapk` | 3 | Same MAPK verified-linking gap as C-02. | PR-18 | Direct BRAF-MAPK activation candidate has verified endpoint grounding. |
| C-05 | `homologous recombination DNA repair`, model hint `GO:0000724` | `strong_brca1_regulates_dna_repair` | 3 | Same verified linker coverage gap for DNA repair process. | PR-18 | Verified linker returns approved process CURIE or explicit review-only abstention. |
| C-06 | `response to pembrolizumab`, missing CURIE | `strong_pdl1_biomarker_immunotherapy` | 3 | Drug-response concepts are composite labels and not represented by current dictionary records. | PR-18 | The linker uses an approved response concept strategy and records the target namespace in tests. |
| C-07 | `ERK phosphorylation`, missing CURIE | `strong_mek_inhibits_erk` | 2 | Molecular event labels are missing from the local verified dictionary. | PR-18 | `ERK phosphorylation` receives a verified event/process grounding or review-only abstention. |
| C-08 | `cardiac septal development`, model hint `GO:0060389` | `strong_med13_activates_septal_development` | 1 | Model picks one plausible GO term but the verifier has no approved disambiguation rule. | PR-18 | Ambiguous GO hints abstain unless the dictionary has one approved target. |
| C-09 | `cardiac septal development`, model hint `GO:0061047` | `strong_med13_activates_septal_development` | 1 | Same ambiguity as C-08. | PR-18 | Same as C-08. |
| C-10 | `cardiac septal development`, model hint `GO:0060411` | `strong_med13_activates_septal_development` | 1 | Same ambiguity as C-08. | PR-18 | Same as C-08. |
| C-11 | `ERK phosphorylation`, model hint `GO:0000165` | `strong_mek_inhibits_erk` | 1 | Model hint points to broad MAPK cascade rather than the ERK phosphorylation event. | PR-18 | Wrong/broad model hint remains untrusted and the verifier chooses the approved event CURIE or abstains. |

### Proposal And Model Gaps

| ID | Failure pattern | Baseline | Root cause | Owning lane | Done when |
|---|---|---:|---|---|---|
| P-01 | Proposal recall against proposal-eligible gold is incomplete | 4/6 | Useful relation proposals are not normalized, classified, and reported with enough detail. | PR-19 | Proposal recall is >= 0.9000 and still separate from trusted recall. |
| P-02 | Trusted proposal capture is zero | 0 | Governed proposals are correctly blocked from trusted promotion, but the report needs a review-success path after approval. | PR-19 and PR-22 | Approved relation types can graduate through governance; unapproved proposals cannot auto-promote. |
| V-01 | Stronger-model benefit is unknown | 1 model group | No controlled A/B harness compares current and stronger models on the same readiness gate. | PR-21 | A/B report includes current model, stronger model, cost, latency, and worst-run deltas across three runs each. |
| V-02 | Run-to-run readiness is still red | 3 RED reports | No consensus policy protects promotion from single-run variance. | PR-21 | Three strict runs pass readiness using worst-run metrics, or consensus keeps non-repeatable claims review-only. |

## Task 1: PR-18 Verified Entity Grounding

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/entity_linking_contracts.py`
- Create: `services/artana_evidence_api/document_extraction_support/verified_entity_dictionary.py`
- Create: `services/artana_evidence_api/document_extraction_support/ontology_grounding.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Test: `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`
- Test: `services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Write failing CURIE recovery tests**

  Add tests that assert these labels are not trusted from model hints alone and are trusted only when the verified linker returns the approved record:

  - `MAPK signaling`
  - `homologous recombination DNA repair`
  - `response to pembrolizumab`
  - `aggressive tumor growth`
  - `ERK phosphorylation`
  - `cardiac septal development`

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
    -q
  ```

  Expected before implementation: tests fail because the new verified dictionary and ambiguity handling do not exist.

- [ ] **Step 2: Split the linker into focused units**

  Implement:

  - `EntityGrounder` protocol in `entity_linking_contracts.py`
  - `VerifiedEntityDictionary` in `verified_entity_dictionary.py`
  - optional fixture-backed `OntologyGrounder` in `ontology_grounding.py`
  - final adjudication in `entity_curie_linking.py`

  Required behavior:

  - model CURIEs stay metadata hints unless the verified linker confirms them
  - ambiguous ontology matches abstain
  - unsupported namespaces abstain
  - label/type conflicts abstain
  - verified matches use `source == "verified_linker"`

- [ ] **Step 3: Add benchmark fixture CURIE policy**

  Update `biomedical_relation_goldset_v2.json` only for expert-approved or fixture-approved identifiers. If a concept is not safely groundable, mark that endpoint with a review-only metadata field rather than fabricating a CURIE.

  Required fixture decision records:

  | Label | Decision |
  |---|---|
  | `MAPK signaling` | approved verified process/pathway grounding |
  | `homologous recombination DNA repair` | approved verified process grounding |
  | `response to pembrolizumab` | approved composite response grounding or review-only abstention |
  | `aggressive tumor growth` | approved phenotype/process grounding or review-only abstention |
  | `ERK phosphorylation` | approved molecular event grounding or review-only abstention |
  | `cardiac septal development` | approved GO target or ambiguity abstention |

- [ ] **Step 4: Run PR-18 validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
    tests/unit/test_relation_feasibility_audit.py \
    -q

  make relation-feasibility-quality-gate
  ```

  Expected after implementation:

  - `wrong_verified_curie_link_count == 0`
  - no model hint is counted as trusted without verifier confirmation
  - verified CURIE endpoint rate improves in the strict live-agent audit

## Task 2: PR-19 Resistance And Proposal Semantics

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_relation_taxonomy.py`
- Modify: `services/artana_evidence_api/document_extraction_support/proposal_relation_type_guard.py`
- Modify: `services/artana_evidence_api/document_extraction_support/evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `services/artana_evidence_db/graph_domain_relation_types.py`
- Modify: `services/artana_evidence_db/_dictionary_relation_types.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Test: `services/artana_evidence_api/tests/unit/test_relation_type_resolver.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Test: `services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

- [x] **Step 1: Write failing resistance semantics tests**

  Add tests for:

  - `MET amplification confers resistance to erlotinib`
  - `EGFR T790M causes resistance to gefitinib`
  - proposal typo `CONFOERS_RESISTANCE_TO`
  - proposal surface `CONFERS_RESISTANCE_TO`

  Expected before implementation:

  - canonical resistance recovery fails
  - proposal typo remains unnormalized or unclassified

- [x] **Step 2: Make a governance decision for `CONFERS_RESISTANCE_TO`**

  Approved path:

  - add `CONFERS_RESISTANCE_TO` to API extraction taxonomy
  - add matching graph dictionary relation type
  - add relation constraints for alteration or gene-event to drug/therapy targets
  - preserve proposal history for old unapproved surfaces

  Review-only path:

  - keep `CONFERS_RESISTANCE_TO` outside canonical taxonomy
  - normalize all safe spelling variants to governed proposal review
  - exclude those proposals from trusted precision while counting proposal recall

  The PR must choose one path and document the reason in its evidence summary. It must not silently count review-only proposals as trusted graph evidence.

- [x] **Step 3: Normalize proposal spelling without unsafe invention**

  Add normalization for known safe review-required proposal variants:

  - `CONFERS_RESISTANCE_TO`
  - `CONFOERS_RESISTANCE_TO`

  Reject unrelated proposal strings with a specific reason such as `proposal_relation_type_unapproved`.

- [x] **Step 4: Run PR-19 validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_relation_type_resolver.py \
    services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
    services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py \
    tests/unit/test_relation_feasibility_audit.py \
    -q

  make relation-feasibility-quality-gate
  ```

  Expected after implementation:

  - M-01, M-02, and M-03 are closed or explicitly counted as governed proposal captures
  - FP-01, FP-02, FP-04, FP-05, and FP-06 no longer harm trusted precision
  - high-value recall worst run is >= 0.8500 or the remaining misses are named

  PR19 evidence:

  - Summary:
    `docs/validation/reports/2026-07-05-pr19-high-value-relation-recovery-summary.md`
  - Strict live-agent run:
    `reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2/relation_feasibility_report.md`
  - Failure attribution:
    `reports/relation_feasibility_failure_analysis/2026-07-05-pr19-run2/relation_feasibility_failure_analysis_report.md`
  - Result: strict live path completed 30/30 with fallback 0, invalid-agent 0,
    negative-control leakage 0, raw unknown relation surfaces 0, completed-agent
    precision 0.9048, high-value recall 0.9500, and valuable rate 0.9048.
  - Remaining blocker: trusted graph readiness is still RED because verified
    CURIE endpoint rate is 0.8108, and PR20 still needs to preserve qualifiers
    such as `BRCA1 loss`.

## Task 3: PR-20 Precision, Directionality, And Low-Value Accounting

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_specificity_pruning.py`
- Modify: `services/artana_evidence_api/document_extraction_support/evidence_support_verifier.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Test: `services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Test: `tests/unit/test_relation_feasibility_failure_analysis.py`

- [ ] **Step 1: Write failing precision tests**

  Add tests for:

  - `Trametinib inhibits ERK phosphorylation downstream of MEK`
  - `BRCA1 loss sensitizes triple-negative breast cancer to cisplatin`
  - hedged phrases containing `may`, `trend`, `possible`, and `correlated`

  Expected before implementation:

  - `ERK phosphorylation DOWNSTREAM_OF MEK` is treated as a normal false positive
  - broad `BRCA1` can replace `BRCA1 loss`
  - low-value misses are mixed into the main remediation queue

- [ ] **Step 2: Add directionality and value adjudication**

  Required behavior:

  - context relations such as `DOWNSTREAM_OF` are non-promotable when they are not the primary valuable claim
  - broad subjects cannot replace event subjects like `BRCA1 loss`, `MET amplification`, or `TP53 loss`
  - hedged low-value relations are accounted as review-only triage
  - failure analysis separates high-value missed relations from low-value review-only misses

- [ ] **Step 3: Run PR-20 validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
    services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
    tests/unit/test_relation_feasibility_failure_analysis.py \
    -q

  make relation-feasibility-quality-gate
  ```

  Expected after implementation:

  - completed-agent precision worst run is >= 0.8000
  - M-04 and FP-07 are closed by qualifier preservation
  - FP-03 is downgraded to non-promotable context unless explicitly requested by a graph-review policy
  - M-05 through M-09 are no longer confused with trusted high-value readiness blockers

## Task 4: PR-21 Repeatability, Model A/B, And Consensus

**Files:**

- Create: `scripts/run_relation_model_ab.py`
- Create: `scripts/validation/relation_feasibility/model_comparison.py`
- Create: `scripts/validation/relation_feasibility/consensus.py`
- Modify: `scripts/validation/relation_feasibility/readiness.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Test: `tests/unit/test_relation_feasibility_model_comparison.py`
- Test: `tests/unit/test_relation_feasibility_consensus.py`
- Test: `tests/unit/test_relation_feasibility_readiness_gate.py`

- [ ] **Step 1: Write failing model comparison and consensus tests**

  Add tests that prove:

  - model labels are required for A/B reports
  - cost and latency fields are carried into the report
  - worst-run metrics are used for readiness
  - consensus keeps single-run-only claims out of auto-promotion

- [ ] **Step 2: Implement controlled model A/B runner**

  Required behavior:

  - same fixture for every model
  - same readiness thresholds for every model
  - at least three strict live-agent runs per model
  - output JSON and Markdown comparison reports
  - explicit blocked status when a model is unavailable

- [ ] **Step 3: Implement consensus policy**

  Required behavior:

  - claims that appear in only one run are review-only
  - claims that repeat with the same normalized triple and verified endpoints can be eligible
  - stronger model output cannot bypass PR-18, PR-19, PR-20, or PR-22 gates

- [ ] **Step 4: Run PR-21 validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_model_comparison.py \
    tests/unit/test_relation_feasibility_consensus.py \
    tests/unit/test_relation_feasibility_readiness_gate.py \
    -q
  ```

  Live comparison command shape:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 scripts/run_relation_model_ab.py \
    --model current="$ARTANA_AI_EVIDENCE_EXTRACTION_MODEL" \
    --model stronger="openai:gpt-5" \
    --runs-per-model 3 \
    --output-dir reports/relation_model_ab/YYYY-MM-DD-pr21
  ```

  Expected after implementation:

  - V-01 has an evidence artifact instead of speculation
  - V-02 has a consensus policy that prevents unstable single-run promotion

## Task 5: PR-22 Runtime Graph Promotion Hard Gate

**Files:**

- Modify: `services/artana_evidence_db/relation_autopromotion_policy.py`
- Modify: `services/artana_evidence_db/graph_validation_service.py`
- Modify: `services/artana_evidence_db/_relation_auto_promotion_mixin.py`
- Modify: `services/artana_evidence_db/relation_claim_service.py`
- Test: `services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py`
- Test: `services/artana_evidence_db/tests/unit/test_kernel_relation_suggestion_service.py`
- Test: `services/artana_evidence_db/tests/integration/test_entity_resolution_api.py`

- [ ] **Step 1: Write failing promotion safety tests**

  Add tests proving auto-promotion rejects:

  - fallback-generated evidence
  - unverified subject CURIE
  - unverified object CURIE
  - unknown relation type
  - governed relation proposal
  - support verification other than `ENTAILS`
  - missing provenance
  - single-run-only candidate when consensus is required

- [ ] **Step 2: Enforce trusted evidence envelope**

  The graph service must require a machine-readable evidence envelope with:

  - agent completion trace
  - no-fallback flag
  - verified subject endpoint
  - verified object endpoint
  - approved relation type
  - support verification result
  - provenance ID
  - consensus or repeated-source proof when policy requires it

- [ ] **Step 3: Run PR-22 validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py \
    services/artana_evidence_db/tests/unit/test_kernel_relation_suggestion_service.py \
    services/artana_evidence_db/tests/integration/test_entity_resolution_api.py \
    -q

  make graph-service-checks
  ```

  Expected after implementation:

  - P-02 is closed safely: approved proposals can graduate only after governance
  - unapproved proposal output cannot auto-promote
  - graph promotion policy matches the readiness gate

## Cross-PR Adversarial Loop

Run this loop after each PR lane:

1. Run focused unit tests for the changed module.
2. Run `make relation-feasibility-quality-gate`.
3. Run three strict live-agent audits with no fallback.
4. Run readiness gate on the three reports.
5. Run failure attribution on the same reports.
6. Update the evidence tracker with exact metrics and report paths.
7. Ask an adversarial reviewer to answer these questions:
   - Did we improve the metric by lowering the standard?
   - Did we count fallback or review-only proposals as trusted evidence?
   - Did model hints become trusted identifiers without verifier proof?
   - Did we hide a false positive as "non-gold but useful" without a review gate?
   - Did the fix overfit the synthetic benchmark?

Required commands:

```bash
git diff --check
make relation-feasibility-quality-gate
make service-checks
```

Strict live-agent readiness command shape:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-prNN-run1

PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-prNN-run2

PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-prNN-run3

PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/YYYY-MM-DD-prNN-run1 \
  --report reports/relation_feasibility/YYYY-MM-DD-prNN-run2 \
  --report reports/relation_feasibility/YYYY-MM-DD-prNN-run3 \
  --fail-on-not-ready \
  --output-dir reports/relation_feasibility_readiness/YYYY-MM-DD-prNN

PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report reports/relation_feasibility/YYYY-MM-DD-prNN-run1 \
  --report reports/relation_feasibility/YYYY-MM-DD-prNN-run2 \
  --report reports/relation_feasibility/YYYY-MM-DD-prNN-run3 \
  --output-dir reports/relation_feasibility_failure_analysis/YYYY-MM-DD-prNN
```

## Final Trusted-Graph Ready Gate

The system is trusted-graph ready only when this table is green on three strict live-agent runs:

| Gate | Required result |
|---|---:|
| Source audit verdicts | 0 RED |
| Completed-agent precision | >= 0.8000 worst run |
| Completed-agent recall | >= 0.6000 worst run |
| High-value recall | >= 0.8500 worst run |
| Completed-agent valuable rate | >= 0.7000 worst run |
| Generic relation rate | <= 0.0500 worst run |
| Verified CURIE endpoint rate | >= 0.9500 worst run |
| Entailment checked rate | 1.0000 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control leakage | 0 |
| Raw unknown relation candidates | 0 |
| Raw unknown relation inventory surfaces | 0 |
| Wrong verified CURIE links | 0 |

The final merge evidence must include:

- readiness JSON and Markdown report
- failure attribution JSON and Markdown report
- model A/B report
- graph promotion safety test output
- updated `docs/validation/evidence-excellence-progress-tracker.md`
