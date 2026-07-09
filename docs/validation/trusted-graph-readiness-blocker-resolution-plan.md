# Trusted Graph Readiness Blocker Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every currently known blocker that prevents the live-agent Artana Evidence path from being trusted-graph ready.

**Architecture:** Keep the agent as a high-recall hypothesis generator and keep trust in explicit verification code. Evidence API owns extraction, entity grounding, support verification, candidate quality, review staging, and audit reporting. Graph DB owns relation dictionaries, constraints, provenance, auto-promotion policy, and hard rejection of untrusted AI evidence.

**Tech Stack:** Python, FastAPI service modules, Pydantic contracts, pytest, ruff, Artana Kernel model runtime, relation feasibility audits, readiness gates, graph dictionary governance, local verified dictionaries, optional ontology-backed grounders, and Postgres service checks.

---

## Source Evidence

This plan is based on the latest strict live-agent evidence available in this worktree:

- PR19 live-agent audit:
  `reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2/relation_feasibility_report.json`
- PR19 failure attribution:
  `reports/relation_feasibility_failure_analysis/2026-07-05-pr19-run2/relation_feasibility_failure_analysis_report.md`
- PR19 merge-visible summary:
  `docs/validation/reports/2026-07-05-pr19-high-value-relation-recovery-summary.md`
- Existing recovery plan:
  `docs/validation/trusted-graph-finding-remediation-plan.md`

Latest PR19 run status:

| Gate | PR19 run2 value | Trusted target | Status |
|---|---:|---:|---|
| Agent completed cases | 30/30 | 30/30 | Passing |
| Fallback cases | 0 | 0 | Passing |
| Invalid strict-agent cases | 0 | 0 | Passing |
| Negative-control leakage | 0 | 0 | Passing |
| Raw unknown relation inventory surfaces | 0 | 0 | Passing |
| Wrong verified CURIE links | 0 | 0 | Passing |
| Completed-agent precision | 0.9048 | >= 0.8000 | Passing |
| High-value recall | 0.9500 | >= 0.8500 | Passing |
| Completed-agent valuable rate | 0.9048 | >= 0.7000 | Passing |
| Generic relation rate | 0.0000 | <= 0.0500 | Passing |
| Verified CURIE-linked gold endpoint rate | 0.8108 | >= 0.9500 | Blocking |
| Repeatability | one strict run | at least three strict runs | Blocking |
| Runtime promotion enforcement | not proven end to end | fail closed | Blocking |

The important interpretation is that the live path is no longer failing from basic runtime safety. It is failing because the system cannot yet prove that every promoted relation is entity-verified, repeatable, and specific enough for graph trust.

## Trusted-Graph Ready Definition

The system is trusted-graph ready only when all of these are true in repeated strict live-agent runs:

- `fallback_case_count == 0`
- `invalid_agent_case_count == 0`
- `negative_control_leakage_count == 0`
- `raw_unknown_relation_type_count == 0`
- `raw_unknown_relation_type_surface_count == 0`
- `wrong_verified_curie_link_count == 0`
- worst-run `completed_agent_precision_against_gold >= 0.8000`
- worst-run `high_value_recall >= 0.8500`
- worst-run `completed_agent_valuable_rate >= 0.7000`
- worst-run `generic_relation_rate <= 0.0500`
- worst-run `curie_linked_gold_endpoint_rate >= 0.9500`
- graph promotion rejects any AI relation without verified identifiers, approved relation type, evidence sentence, both endpoints present, entailing support, provenance, and no-fallback trace

The threshold can be made stricter later, but it must not be lowered to create a green report.

## Agile Loop

Each implementation lane must follow this loop:

1. Pick one blocker from the ledger below.
2. Write a failing unit or regression test that reproduces the blocker.
3. Run only the focused test and capture the expected failure.
4. Implement the smallest first-principles fix at the correct service boundary.
5. Run the focused test until green.
6. Run the relevant service tests and lint for the changed boundary.
7. Run `make relation-feasibility-quality-gate`.
8. Run one strict live-agent audit using `--extractor agent`.
9. Run failure attribution on the new report.
10. Ask for adversarial review against the diff and report.
11. Fix any valid adversarial finding.
12. Update `docs/validation/evidence-excellence-progress-tracker.md` and a dated report under `docs/validation/reports/`.
13. Commit the lane only after tests, report evidence, and docs agree.

Required strict audit command:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-prNN-short-name-run1'
```

Required failure attribution command:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report current=reports/relation_feasibility/YYYY-MM-DD-prNN-short-name-run1/relation_feasibility_report.json \
  --output-dir reports/relation_feasibility_failure_analysis/YYYY-MM-DD-prNN-run1
```

Required final readiness command before declaring trusted-graph readiness:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/YYYY-MM-DD-final-run1 \
  --report reports/relation_feasibility/YYYY-MM-DD-final-run2 \
  --report reports/relation_feasibility/YYYY-MM-DD-final-run3 \
  --fail-on-not-ready \
  --output-dir reports/relation_feasibility_readiness/YYYY-MM-DD-final
```

## Finding Ledger

| ID | Finding | Root cause | Owner lane | Closure evidence |
|---|---|---|---|---|
| F-01 | Verified CURIE endpoint rate is `0.8108`, below `0.9500`. | The verified linker does not yet cover all recurring biomedical processes, phenotypes, and composite response labels. Model hints are intentionally untrusted. | PR18 plus integration rebase | Worst-run verified endpoint rate is `>= 0.9500`, with wrong verified CURIE links still `0`. |
| F-02 | `BRCA1 loss SENSITIZES_TO cisplatin` is missed while `BRCA1 SENSITIZES_TO cisplatin` appears as a false positive. | Extraction and scoring allow a biological modifier to be dropped from the subject, changing the claim. | PR20 | Broad subject substitution is blocked, `BRCA1 loss` is preserved, and precision does not regress. |
| F-03 | `ERK phosphorylation DOWNSTREAM_OF MEK` appears as an entailed but non-gold context relation. | The candidate is locally true but less valuable than the drug inhibition claim the case is meant to measure. The system needs value-aware adjudication, not only entailment. | PR20 | Context-only relation is review-only or lower priority when a more valuable direct drug-mechanism relation is supported. |
| F-04 | Low-value hedged relations are counted as misses even when they should not be trusted graph evidence. | The benchmark has low-value gold rows for trend, possible biomarker, and may-regulate language, but readiness should optimize trusted high-value promotion first. | PR20 | Report separates trusted recall from low-value review recall and does not pressure auto-promotion of hedged claims. |
| F-05 | Stronger-model benefit is unknown. | The harness supports model labels, but there is no controlled repeated-run A/B gate for baseline model versus stronger candidate model. | PR21 | A/B report compares at least three runs per model on the same fixture, including quality, cost, latency, and failure attribution. |
| F-06 | Repeatability is not proven. | PR19 evidence is one strict run, and the agent path can vary across runs. | PR21 | Three strict live-agent runs pass readiness on worst-run metrics, or consensus keeps non-repeatable claims review-only. |
| F-07 | Runtime graph promotion is not proven to enforce the same trust floor as the audit. | The audit can be red or green independently of graph auto-promotion policy. Promotion must fail closed at the graph boundary too. | PR22 | Graph DB rejects unverified AI relations even when API metadata tries to mark them trusted. |
| F-08 | Current benchmark is still too small and mostly synthetic for production confidence. | The v2 fixture is a strong regression harness, but not enough to prove broad biomedical value. | PR23 | Larger blinded fixture exists with oncology, rare disease, variant, pathway, drug-response, negative-control, and long-document cases. |
| F-09 | External ontology grounding could introduce silent wrong links. | More grounding coverage can increase recall while also increasing false positives unless namespace and ambiguity policy is strict. | PR18 and PR23 | Every new grounding source has fixture-backed tests for allowed namespaces, ambiguity abstention, and wrong-link blocking. |
| F-10 | Deterministic fallback can still confuse product interpretation if reports are mixed. | Fallback is useful for triage but not evidence of live-agent quality. | Every lane | Main scorecards label fallback/unavailable runs as invalid for trusted readiness. |

## PR18: Verified Entity Grounding Completion

**Goal:** Move verified CURIE endpoint recovery above the trusted threshold without trusting raw model CURIE hints.

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- Create or modify: `services/artana_evidence_api/document_extraction_support/entity_grounding/contracts.py`
- Create or modify: `services/artana_evidence_api/document_extraction_support/entity_grounding/verified_dictionary.py`
- Create or modify: `services/artana_evidence_api/document_extraction_support/entity_grounding/ontology.py`
- Modify: `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`
- Modify: `services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py`
- Modify: `services/artana_evidence_api/tests/unit/test_ontology_grounding.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`

- [ ] **Step 1: Add failing tests for every remaining PR19 CURIE gap**

  Add one test case for each endpoint from PR19 run2:

  - `aggressive tumor growth`
  - `MAPK signaling`
  - `homologous recombination DNA repair`
  - `cardiac septal development`
  - `ERK phosphorylation`
  - `response to pembrolizumab`

  Expected failure before implementation:

  - known process and phenotype labels do not return `source == "verified_linker"`
  - composite response labels either return no link or must explicitly abstain with a review-only reason

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
    services/artana_evidence_api/tests/unit/test_ontology_grounding.py \
    -q
  ```

- [ ] **Step 2: Implement verified dictionary coverage**

  Implement verified records only for concepts with a defensible identifier and allowed namespace. Preserve ambiguous or composite cases as review-only instead of forcing a CURIE.

  Required policy:

  - model hint CURIEs remain metadata hints
  - verified IDs require dictionary or ontology confirmation
  - ambiguous matches abstain
  - namespace mismatch abstains
  - broad parent IDs do not count when the gold concept is a narrower event

- [ ] **Step 3: Make audit scoring prove the distinction**

  Ensure `tests/unit/test_relation_feasibility_audit.py` proves:

  - model CURIE hints do not count as verified links
  - wrong verified links are blocking
  - review-only abstentions do not become trusted graph evidence
  - verified link rate improves only from `source == "verified_linker"`

- [ ] **Step 4: Run validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
    services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
    services/artana_evidence_api/tests/unit/test_ontology_grounding.py \
    tests/unit/test_relation_feasibility_audit.py \
    -q

  make relation-feasibility-quality-gate
  make service-checks
  ```

  Expected result:

  - unit tests pass
  - `wrong_verified_curie_link_count == 0`
  - strict live run verified endpoint rate improves toward or above `0.9500`

## PR20: Qualifier Preservation And Precision Adjudication

**Goal:** Prevent relation evidence from becoming over-broad, while keeping valuable high-value recall.

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_support/evidence_grounding.py`
- Modify: `services/artana_evidence_api/document_extraction_support/evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_specificity_pruning.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Modify: `services/artana_evidence_api/tests/unit/test_evidence_grounding.py`
- Modify: `services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`

- [x] **Step 1: Add the failing broad-subject regression**

  Add a regression where the source sentence is:

  ```text
  BRCA1 loss sensitizes tumors to cisplatin.
  ```

  Candidate `BRCA1 SENSITIZES_TO cisplatin` must be filtered with a reason such as `dropped_subject_modifier`.

  Candidate `BRCA1 loss SENSITIZES_TO cisplatin` must be kept when supported.

  Run:

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
    services/artana_evidence_api/tests/unit/test_evidence_grounding.py \
    -q
  ```

- [x] **Step 2: Implement modifier-preservation policy**

  The policy must reject broad substitutions when the sentence contains one of these biomedical modifiers and the candidate drops it:

  - `loss`
  - `loss of`
  - `amplification`
  - `activation`
  - `phosphorylation`
  - `mutation`
  - `variant`
  - specific variant tokens such as `T790M` or `V600E`

  The filter should operate on candidate labels and evidence sentence text, not on gold labels.

- [x] **Step 3: Add the context-relation adjudication regression**

  Add a case where `ERK phosphorylation DOWNSTREAM_OF MEK` is entailed but should not be promoted above the direct valuable mechanism relation in the same evidence context.

  Expected behavior:

  - the context relation may be retained as review-only
  - it must not count as trusted high-value evidence for the case
  - it must not hide the direct mechanism relation if the direct relation is present

- [x] **Step 4: Add low-value review accounting**

  Update scoring and reporting so low-value hedged relations are counted separately from trusted readiness.

  Required report fields:

  - `low_value_gold_relation_count`
  - `low_value_review_candidate_count`
  - `low_value_review_recall`
  - `trusted_high_value_recall`

  Required behavior:

  - high-value trusted readiness still blocks when high-value recall is too low
  - low-value misses do not force the model to promote hedged evidence as trusted
  - low-value candidates can be useful review artifacts

- [x] **Step 5: Run validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_api/tests/unit/test_document_extraction.py \
    services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
    services/artana_evidence_api/tests/unit/test_evidence_grounding.py \
    services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py \
    services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
    tests/unit/test_relation_feasibility_audit.py \
    -q

  make relation-feasibility-quality-gate
  make service-checks
  ```

  Expected result:

  - `BRCA1 loss` is recovered or broad `BRCA1` is filtered
  - context false positives do not reduce trusted precision
  - low-value review accounting appears in Markdown and JSON reports

  Current PR20 evidence:

  - Focused PR20 unit suite after adversarial fixes: 151 passed.
  - `make relation-feasibility-quality-gate`: 53 passed.
  - Strict live-agent run:
    `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.json`
  - Failure attribution:
    `reports/relation_feasibility_failure_analysis/2026-07-05-pr20-run4/relation_feasibility_failure_analysis_report.md`
  - Live result: completed-agent precision `0.9500`, high-value recall
    `0.9500`, trusted high-value recall `0.5500`, fallback `0`,
    invalid-agent `0`, negative leakage `0`.
  - Adversarial review fixes: expanded modifier coverage, stricter trusted
    high-value metric, low-value review-only accounting, narrower context
    shadowing for separate pathway claims, clause-local modifier checks, and
    review-only trust accounting for context relations; final re-review added
    comma-and coordinated-claim scoping and found no remaining PR20 blocker.
  - Remaining blocker: verified CURIE-linked endpoint rate `0.8108`, below
    the `0.9500` trusted-readiness target.

## PR21: Repeatability, Consensus, And Model A/B

**Goal:** Decide whether a stronger model actually helps, and prevent any single lucky or unlucky run from controlling graph trust.

**Files:**

- Modify: `scripts/run_relation_feasibility_audit.py`
- Modify: `scripts/run_relation_feasibility_readiness_gate.py`
- Modify: `scripts/validation/relation_feasibility/readiness.py`
- Modify: `scripts/validation/relation_feasibility/failure_analysis.py`
- Create: `scripts/run_relation_model_ab.py`
- Create: `tests/unit/test_relation_model_ab.py`
- Modify: `tests/unit/test_relation_feasibility_readiness_gate.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`

- [ ] **Step 1: Add model-label and run-label tests**

  Add tests proving reports preserve:

  - model label
  - model provider
  - extraction capability name
  - prompt version
  - run label
  - elapsed time
  - total candidate count
  - hard failure counts

- [ ] **Step 2: Add controlled A/B runner**

  `scripts/run_relation_model_ab.py` must run the same benchmark for each configured model group.

  Required inputs:

  ```bash
  --model baseline=openai:gpt-5-mini
  --model strong=<configured-stronger-model>
  --runs-per-model 3
  --output-dir reports/relation_model_ab/YYYY-MM-DD
  ```

  Required outputs:

  - per-run relation feasibility reports
  - one readiness report per model
  - one comparison summary JSON
  - one comparison summary Markdown

- [ ] **Step 3: Add consensus policy**

  Add readiness output that classifies each candidate pattern as:

  - repeated trusted candidate
  - one-off review-only candidate
  - repeated false positive
  - repeated missed high-value gold
  - repeated CURIE gap

  Promotion may only use repeated trusted candidates or candidates that pass an explicit stronger verification policy.

- [ ] **Step 4: Use a stronger model only if evidence proves it**

  A stronger model may become the default extraction model only when all of these are true:

  - worst-run readiness improves versus baseline
  - no hard safety counter regresses
  - wrong verified CURIE links remain `0`
  - generic relation rate remains `<= 0.0500`
  - verified endpoint rate is not solved by trusting model hints
  - latency and cost are documented

  If the stronger model improves recall but worsens precision, use it only as a recall-stage candidate generator followed by verifier or consensus filtering.

- [ ] **Step 5: Run validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_model_ab.py \
    tests/unit/test_relation_feasibility_readiness_gate.py \
    tests/unit/test_relation_feasibility_failure_analysis.py \
    -q

  make relation-feasibility-quality-gate
  make service-checks
  ```

## PR22: Graph Promotion Hard Gate

**Goal:** Make the graph service enforce trusted evidence rules even if upstream API metadata is wrong.

**Files:**

- Modify: `services/artana_evidence_db/validation/trusted_evidence_floor.py`
- Modify: `services/artana_evidence_db/_relation_auto_promotion_mixin.py`
- Modify: `services/artana_evidence_db/relation_autopromotion_policy.py`
- Modify: `services/artana_evidence_db/relation_repository.py`
- Modify: `services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py`
- Modify: `services/artana_evidence_db/tests/unit/test_trusted_evidence_floor.py`
- Modify: `services/artana_evidence_api/proposal_actions.py`
- Modify: `services/artana_evidence_api/tests/unit/test_proposal_actions.py`

- [ ] **Step 1: Add malicious-metadata tests**

  Add tests where an API request tries to set:

  ```json
  {
    "trusted_evidence_eligible": true,
    "subject_curie_source": "model",
    "object_curie_source": "verified_linker"
  }
  ```

  Expected result:

  - graph service rejects auto-promotion
  - rejection reason includes `unverified_subject_curie`
  - audit metadata records the attempted unsafe promotion

- [ ] **Step 2: Enforce all trusted floors at graph boundary**

  Graph promotion must require:

  - approved relation type
  - active relation constraint when applicable
  - evidence sentence
  - both relation arguments present in sentence
  - support verification is `ENTAILS`
  - subject and object identifiers are verified or explicitly governed as non-linkable
  - no fallback extraction trace
  - no review-required relation proposal
  - no raw unknown relation type surface

- [ ] **Step 3: Preserve review path**

  Unsafe AI candidates must not disappear. They should become review items with a clear reason, not trusted graph relations.

- [ ] **Step 4: Run validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py \
    services/artana_evidence_db/tests/unit/test_trusted_evidence_floor.py \
    services/artana_evidence_api/tests/unit/test_proposal_actions.py \
    -q

  make graph-service-checks
  make artana-evidence-api-service-checks
  make service-checks
  ```

## PR23: Benchmark Expansion And External Grounder Safety

**Goal:** Make the readiness result less fragile by expanding beyond the current synthetic seed while keeping tests deterministic.

**Files:**

- Modify: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Create: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Create: `scripts/validation/relation_feasibility/fixtures/ontology_grounding_cases.json`
- Modify: `scripts/validation/relation_feasibility/io.py`
- Modify: `tests/unit/test_relation_feasibility_fixtures.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Add fixture validation tests**

  Add tests that reject fixture rows missing:

  - `case_id`
  - `value_level`
  - `support_sentence`
  - subject label
  - object label
  - relation type
  - expected promotion tier
  - review-only reason when applicable

- [ ] **Step 2: Add blinded fixture categories**

  Add at least these categories:

  - oncology resistance
  - oncology sensitivity
  - rare disease gene-disease evidence
  - pathway activation
  - pathway inhibition
  - drug-response biomarker
  - phenotype/process grounding
  - negative-control association
  - long-document tail relation
  - ambiguous ontology label

- [ ] **Step 3: Gate external grounding through fixtures**

  External grounder adapters may be added only behind configuration and fixture-backed tests. Network access must not be required for unit tests.

- [ ] **Step 4: Run validation**

  ```bash
  PYTHONPATH="$(pwd)/services:$(pwd)" \
    .venv/bin/python3 -m pytest \
    tests/unit/test_relation_feasibility_fixtures.py \
    tests/unit/test_relation_feasibility_audit.py \
    -q

  make relation-feasibility-quality-gate
  make service-checks
  ```

## Merge Order

Recommended order:

1. PR18 verified entity grounding
2. PR19 high-value resistance relation recovery
3. PR20 qualifier preservation and precision adjudication
4. PR21 repeatability, consensus, and model A/B
5. PR22 graph promotion hard gate
6. PR23 benchmark expansion and external grounder safety

PR18 and PR20 can be developed in parallel after PR19 is rebased, but PR21 should consume the combined outputs of PR18 through PR20. PR22 should merge after PR21 so the runtime gate enforces the policy that the readiness gate proves.

## Adversarial Review Checklist

Every lane must answer these questions before merge:

- Did the change improve the real live-agent path, not deterministic fallback?
- Did any model hint become a trusted identifier without verification?
- Did a review-only proposal become trusted evidence by accident?
- Did precision improve by hiding valid candidates instead of classifying them?
- Did recall improve by promoting hedged or generic evidence?
- Did graph promotion remain fail-closed if API metadata is malicious or stale?
- Did the fixture change make the benchmark easier instead of more correct?
- Did the strict live run include `fallback_case_count == 0`?
- Did the docs include report artifact paths and exact metrics?

## Final Readiness Gate

After all lanes merge, run three strict live-agent audits from the same final branch:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-final-run1'

bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-final-run2'

bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-final-run3'
```

Then run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/YYYY-MM-DD-final-run1 \
  --report reports/relation_feasibility/YYYY-MM-DD-final-run2 \
  --report reports/relation_feasibility/YYYY-MM-DD-final-run3 \
  --fail-on-not-ready \
  --output-dir reports/relation_feasibility_readiness/YYYY-MM-DD-final

make service-checks
```

Only then can the system be called trusted-graph ready.
