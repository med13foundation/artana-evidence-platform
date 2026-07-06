# Trusted Graph Readiness Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Artana Evidence from "strict live-agent path completes" to "trusted graph auto-promotion is repeatably safe, valuable, specific, and entity-verified."

**Architecture:** Keep the model as a hypothesis generator and keep verification in explicit code. Candidate extraction stays in `services/artana_evidence_api`; graph trust and dictionary governance stay in `services/artana_evidence_db`; repeatability and readiness gates stay in `scripts/validation`.

**Tech Stack:** Python, FastAPI services, Artana Kernel model runtime, Pydantic contracts, pytest, ruff, Postgres-backed service checks, relation feasibility reports, optional biomedical entity grounders such as Gilda, BioPortal, or PubTator-style normalization.

---

## Current Evidence Baseline

Source evidence from the PR16 repeatability gate:

- Readiness artifact:
  `reports/relation_feasibility_readiness/2026-07-05-pr16-repeatability-readiness-r2/relation_feasibility_readiness_report.json`
- Run artifacts:
  `reports/relation_feasibility/2026-07-05-pr16-repeatability-run1/relation_feasibility_report.json`
  `reports/relation_feasibility/2026-07-05-pr16-repeatability-run2/relation_feasibility_report.json`
  `reports/relation_feasibility/2026-07-05-pr16-repeatability-run3/relation_feasibility_report.json`

Current PR16 status: `not_ready`.

| Gate | Worst run | Target | Status |
|---|---:|---:|---|
| Source audit verdicts | 3 RED reports | 0 RED reports | Blocking |
| Completed-agent precision | 0.7619 | >= 0.8000 | Blocking |
| Completed-agent recall | 0.6400 | >= 0.6000 | Passing |
| High-value recall | 0.8000 | >= 0.8500 | Blocking |
| Completed-agent valuable rate | 0.7619 | >= 0.7000 | Passing |
| Generic relation rate | 0.0000 | <= 0.0500 | Passing |
| Verified CURIE endpoint rate | 0.6486 | >= 0.9500 | Blocking |
| Entailment checked rate | 1.0000 | 1.0000 | Passing |
| Fallback cases | 0 | 0 | Passing |
| Invalid strict-agent cases | 0 | 0 | Passing |
| Negative-control leakage | 0 | 0 | Passing |
| Raw unknown relation surfaces | 0 | 0 | Passing |
| Wrong verified CURIE links | 0 | 0 | Passing |

Mean metrics:

| Metric | Mean |
|---|---:|
| Completed-agent precision | 0.7936 |
| Completed-agent recall | 0.6667 |
| High-value recall | 0.8333 |
| Valuable candidate rate | 0.7936 |
| Verified CURIE endpoint rate | 0.6847 |
| Entailment checked rate | 1.0000 |
| Generic relation rate | 0.0000 |

Important interpretation:

- The runtime trust failures are clean: fallback, invalid agent, negative leakage,
  unknown relation surfaces, and wrong verified CURIE links are all zero.
- The remaining work is quality and repeatability: verified entity linking,
  high-value relation capture, precision, and variance across live runs.
- Model CURIEs are still hints. They must not become trusted identifiers unless
  the verifier, dictionary, or ontology-backed linker confirms them.

## Findings To Address

| Finding | Root cause | Owning PR lane | Done when |
|---|---|---|---|
| Verified CURIE recovery is far below target | The verified linker is a small local record list, so model-suggested GO, disease, response, and process IDs often remain untrusted hints | PR18 | Worst-run verified CURIE endpoint rate is >= 0.9500 with wrong verified links still 0 |
| High-value resistance relations are repeatedly missed or mis-shaped | The extractor and scorer do not consistently handle resistance semantics, governed proposals, and canonical-vs-proposal credit | PR19 | Worst-run high-value recall is >= 0.8500 and proposal-eligible capture is measured separately |
| Precision drops below the auto-promotion floor | Some extractions are entailed but outside gold scope, some are direction/argument errors, and some proposals fail support verification | PR20 | Worst-run completed-agent precision is >= 0.8000 without lowering recall or hiding review-required candidates |
| Run-to-run variance remains too high | Single-sample extraction is nondeterministic and no consensus policy protects promotion from an unlucky run | PR21 | Three or more strict runs pass readiness using worst-run metrics |
| Stronger-model benefit is unknown | Current evidence uses the configured extraction model, but no controlled A/B compares model choices against the same gate | PR17 and PR21 | A/B report compares current model, stronger model, cost, latency, and worst-run readiness deltas |
| Auto-promotion must remain blocked until all gates pass | Validation reports prove quality, but runtime graph promotion needs an explicit policy boundary | PR22 | Graph promotion rejects every AI trusted relation missing verified entities, entailing support, approved relation type, provenance, and no-fallback trace |

## Dependency Graph

```text
PR17 Failure attribution and model A/B harness
  -> PR18 Ontology-backed verified entity linking
  -> PR19 High-value relation and proposal recovery
  -> PR20 Precision and adjudication gate
      -> PR21 Repeatability and model policy
          -> PR22 Graph promotion readiness enforcement
```

PR18, PR19, and PR20 can proceed in parallel after PR17 defines the shared
failure-attribution report format. PR21 consumes the outputs of PR18-PR20. PR22
is last because it turns readiness into runtime promotion policy.

## Global Merge Rules

Every PR in this recovery loop must preserve these invariants:

- Strict live-agent runs must use `--extractor agent` without `--allow-fallback`.
- `fallback_case_count == 0`.
- `invalid_agent_case_count == 0`.
- `negative_control_leakage_count == 0`.
- `raw_unknown_relation_type_count == 0`.
- `raw_unknown_relation_type_surface_count == 0`.
- `wrong_verified_curie_link_count == 0`.
- Deterministic fallback may be used for triage comparison only. It never counts
  as trusted graph evidence.
- Model CURIE hints may guide lookup, but only verified linker or governed
  dictionary matches count as trusted identifiers.
- Governed relation proposals are valuable review artifacts, not trusted
  auto-promotion, until approved by relation-type governance.
- Any metric regression must include an error decomposition before the PR can
  be marked ready.

Required repo checks before merge:

```bash
git diff --check
make relation-feasibility-quality-gate
make service-checks
```

Required live-agent readiness check before claiming trusted-graph ready:

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
```

## PR17: Failure Attribution And Model A/B Harness

Suggested branch: `alvaro/evidence-pr17-readiness-failure-attribution`

Goal: make every readiness failure explainable by repeated misses, false
positives, CURIE gaps, proposal misses, and model variance.

**Files:**

- Create: `scripts/summarize_relation_readiness_failures.py`
- Create: `scripts/validation/relation_feasibility/failure_analysis.py`
- Create: `tests/unit/test_relation_feasibility_failure_analysis.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Create report: `docs/validation/reports/2026-07-05-pr17-readiness-failure-attribution-summary.md`

**Implementation requirements:**

- Read one or more `relation_feasibility_report.json` files.
- Emit repeated missed gold relations by case, subject, relation type, object,
  value level, and occurrence count.
- Emit false positives by case, subject, relation type, proposed relation type,
  object, support verification status, and occurrence count.
- Emit CURIE gaps by endpoint label, role, candidate CURIE, candidate CURIE
  source, and occurrence count.
- Emit proposal capture statistics separately from trusted auto-promotion
  statistics.
- Emit a model comparison table when reports are grouped by model label.
- Never mutate source reports.

**Test checklist:**

- [ ] Add a unit test where the same high-value miss appears in three input
  reports and assert the summary count is `3`.
- [ ] Add a unit test where a model-hint CURIE is present but not verified and
  assert it is classified under `unverified_model_hint`, not `verified_match`.
- [ ] Add a unit test where a governed proposal matches a proposal-eligible gold
  relation and assert proposal credit is separate from trusted recall.
- [ ] Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_failure_analysis.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  -q
```

**Live validation:**

- Run the analyzer against the three PR16 reports.
- Run one controlled stronger-model experiment if the model is configured and
  the account has access.
- Use the same benchmark, same readiness thresholds, and at least three runs per
  model before comparing.

**Decision rule for stronger models:**

- If the stronger model improves high-value recall or precision but CURIE
  recovery remains below `0.9500`, keep the stronger model as candidate
  generation only and continue PR18.
- If the stronger model improves proposal spelling but not trusted recall, keep
  the proposal normalization work in PR19.
- If the stronger model increases precision but lowers high-value recall, test a
  two-stage recall-then-rerank design instead of changing the default model.
- Do not switch production defaults from one successful run. Use worst-run
  readiness metrics across repeated runs.

**Merge gate:**

- Failure attribution report exists and names the current top blockers.
- Stronger-model comparison is either completed with report paths or explicitly
  blocked by unavailable model access.
- No readiness threshold is lowered.

## PR18: Ontology-Backed Verified Entity Linking

Suggested branch: `alvaro/evidence-pr18-ontology-verified-entity-linking`

Goal: raise verified CURIE endpoint recovery from the PR16 worst run `0.6486`
to at least `0.9500` without trusting raw model hints.

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/entity_linking_contracts.py`
- Create: `services/artana_evidence_api/document_extraction_support/verified_entity_dictionary.py`
- Create: `services/artana_evidence_api/document_extraction_support/ontology_grounding.py`
- Modify: `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Create: `services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py`
- Modify: `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`

**Implementation requirements:**

- Split the current hard-coded entity linker into focused units:
  `EntityGrounder` protocol, local verified dictionary, optional external
  grounder adapter, and final adjudicator.
- Add verified local records or fixture-backed ontology aliases for recurring
  PR16 gaps:
  `cardiac septal development`, `homologous recombination DNA repair`,
  `MAPK signaling`, `ERK phosphorylation`, `response to pembrolizumab`,
  `aggressive tumor growth`, and `platinum sensitivity`.
- Accept only allowed namespaces for each entity class. Examples:
  genes use HGNC or NCBIGene, drugs use DrugBank or CHEBI, phenotypes use HP,
  diseases use MONDO or MESH, biological processes use GO.
- Preserve model hints in metadata as hints, including `model_hint_curie` and
  `model_hint_status`.
- Count a CURIE as trusted only when `source == "verified_linker"`.
- Add ambiguity handling: when two high-scoring ontology matches conflict, the
  linker must abstain and queue review instead of choosing one silently.
- Cache external grounder results behind explicit configuration. Unit tests must
  use fixtures and must not require network access.

**Test checklist:**

- [ ] Write a failing unit test proving `MAPK signaling` links to a verified GO
  or governed ontology CURIE with `source == "verified_linker"`.
- [ ] Write a failing unit test proving a model-supplied wrong CURIE for `MAPK
  signaling` is replaced by the verified dictionary result and recorded as
  `model_hint_status == "replaced"`.
- [ ] Write a failing unit test proving an ambiguous label abstains and does not
  create graph identifiers.
- [ ] Write an audit regression proving model-only GO hints do not count toward
  `curie_linked_gold_endpoint_rate`.
- [ ] Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
  services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
  tests/unit/test_relation_feasibility_audit.py::test_model_curie_hints_do_not_count_as_verified_gold_endpoint_links \
  -q
```

**Adversarial review questions:**

- Can a drug label be verified as a gene?
- Can a model hint become trusted without dictionary or ontology confirmation?
- Can an ambiguous process label be promoted without review?
- Can a verified CURIE mismatch escape `wrong_verified_curie_link_count`?

**Merge gate:**

- Worst-run `curie_linked_gold_endpoint_rate >= 0.9500`.
- Worst-run `verified_curie_match_rate >= 0.9500`.
- `wrong_verified_curie_link_count == 0`.
- No increase in fallback, invalid-agent, or negative-control leakage counts.

## PR19: High-Value Relation And Proposal Recovery

Suggested branch: `alvaro/evidence-pr19-high-value-relation-recovery`

Goal: fix repeated high-value misses, especially resistance semantics and
governed relation proposals.

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_relation_taxonomy.py`
- Create: `services/artana_evidence_api/document_extraction_support/relation_proposal_normalization.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`

**Implementation requirements:**

- Add explicit prompt examples for:
  `MET amplification confers resistance to erlotinib`,
  `EGFR T790M causes resistance to gefitinib`, and
  `BRCA1 loss sensitizes to cisplatin`.
- Normalize safe proposal spelling variants such as
  `CONFOERS_RESISTANCE_TO` only into review-required proposal surfaces, never
  into trusted canonical relation types.
- Split two scorecard concepts:
  trusted canonical recall and governed proposal capture.
- Decide through graph dictionary governance whether `CONFERS_RESISTANCE_TO`
  should remain a proposal type or become an approved canonical relation type.
- If it remains a proposal type, do not count it as trusted auto-promotion.
- If it becomes canonical, add graph-service dictionary migration or seed data
  plus API taxonomy sync tests.
- Ensure "causes resistance to gefitinib" can be represented consistently as
  either `CAUSES -> resistance to gefitinib` or as an approved resistance
  relation. The benchmark must state which representation is expected.

**Test checklist:**

- [x] Add a failing extraction conversion test for the MET resistance sentence.
- [x] Add a failing extraction conversion test for the EGFR T790M resistance
  sentence.
- [x] Add a failing scoring test where a governed proposal gets proposal capture
  credit but not trusted auto-promotion credit.
- [x] Add a failing regression where a misspelled proposal is review-required
  and cannot enter raw unknown relation inventory.
- [x] Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

**Adversarial review questions:**

- Does the fix overfit only the current gold sentences?
- Can a weak "may confer resistance" sentence enter trusted recall?
- Can a proposal be counted as trusted without governance approval?
- Does the fix increase generic `ASSOCIATED_WITH` noise?

**Merge gate:**

- Worst-run `high_value_recall >= 0.8500`.
- Proposal-eligible capture is reported separately and does not pollute trusted
  recall.
- Raw unknown relation surface counts remain zero.
- No regression in verified CURIE endpoint rate after PR18.

**Current PR19 evidence:**

- Summary:
  `docs/validation/reports/2026-07-05-pr19-high-value-relation-recovery-summary.md`
- Strict live-agent run:
  `reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2/relation_feasibility_report.md`
- Result: fallback 0, invalid-agent 0, negative-control leakage 0, raw unknown
  relation surfaces 0, completed-agent precision 0.9048, high-value recall
  0.9500, and valuable rate 0.9048.
- Verified CURIE endpoint rate is still 0.8108, so trusted graph readiness
  remains RED until PR18/PR20/PR21/PR22 are integrated and pass together.

## PR20: Precision, Reranking, And Non-Gold Adjudication

Suggested branch: `alvaro/evidence-pr20-precision-rerank-adjudication`

Goal: raise worst-run precision above `0.8000` while preserving high-value recall
and making true non-gold extractions visible instead of automatically treating
all of them as bad evidence.

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/relation_candidate_reranker.py`
- Modify: `services/artana_evidence_api/document_extraction_support/evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/models.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Create: `services/artana_evidence_api/tests/unit/test_relation_candidate_reranker.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`

**Implementation requirements:**

- Add a post-extraction reranker that scores:
  exact support sentence alignment, both-argument grounding, relation direction,
  object boundary precision, relation specificity, and verified endpoint status.
- Quarantine candidates that are entailed by text but outside the current gold
  set into an `adjudication_required` bucket.
- Keep the main precision metric strict, but add a companion metric:
  `entailed_non_gold_candidate_count`.
- Add direction-sensitive checks for examples like:
  `ERK phosphorylation DOWNSTREAM_OF MEK`.
- Avoid silently dropping true but non-gold relations from evidence logs. They
  should become review evidence that can improve the benchmark.
- Do not use the reranker to hide candidates after they were counted as agent
  output. The report must show raw, filtered, quarantined, and trusted counts.

**Test checklist:**

- [ ] Add a failing unit test where a reversed relation gets lower rank than the
  correct direction.
- [ ] Add a failing unit test where an entailed but non-gold relation is marked
  `adjudication_required`.
- [ ] Add a failing audit test proving adjudicated non-gold candidates are
  visible in the report and not counted as trusted precision wins.
- [ ] Add a failing test proving a missing support-verification candidate cannot
  be reranked into trusted eligibility.
- [ ] Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_relation_candidate_reranker.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

**Adversarial review questions:**

- Is the precision increase real, or did the code hide hard cases?
- Are non-gold entailed candidates recoverable for benchmark improvement?
- Did reranking reduce high-value recall below the readiness floor?
- Did reranking favor verified CURIE presence over actual relation support?

**Merge gate:**

- Worst-run `completed_agent_precision_against_gold >= 0.8000`.
- Worst-run `completed_agent_valuable_candidate_rate >= 0.7000`.
- Worst-run `high_value_recall >= 0.8500`.
- `entailment_checked_rate == 1.0000`.
- Reports include quarantined/adjudication counts.

**Current PR20 implementation note:**

The active PR20 branch follows the narrower root-cause blocker plan in
`docs/validation/trusted-graph-readiness-blocker-resolution-plan.md` rather than
the heavier reranker design above. The implemented slice adds dropped-modifier
filtering, context-relation shadowing, and explicit low-value review metrics.
After adversarial review, it also expands modifier coverage, makes
`trusted_high_value_recall` require completed-agent provenance and verified
gold endpoints, preserves separate pathway-context claims, scopes modifier
checks to the candidate claim clause, and treats context relations as review-only
for trusted high-value recall. Final adversarial re-review added comma-and
coordinated-claim scoping and found no remaining PR20 blocker. The latest strict
live-agent run reached completed-agent precision `0.9500`, high-value recall
`0.9500`, trusted high-value recall `0.5500`, fallback `0`, invalid-agent `0`,
and negative leakage `0`. The run remains RED because verified CURIE-linked
endpoint rate is `0.8108`.

Evidence:

- `docs/validation/reports/2026-07-05-pr20-qualifier-precision-summary.md`
- `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr20-run4/relation_feasibility_failure_analysis_report.md`

## PR21: Repeatability, Consensus, And Model Policy

Suggested branch: `alvaro/evidence-pr21-repeatability-model-policy`

Goal: make trusted relation output stable across live-agent runs and define when
a stronger model should be used.

**Files:**

- Create: `services/artana_evidence_api/document_extraction_support/relation_extraction_consensus.py`
- Modify: `services/artana_evidence_api/document_extraction_support/strict_relation_discovery.py`
- Modify: `services/artana_evidence_api/runtime/model_registry.py`
- Modify: `services/artana_evidence_api/artana.toml`
- Modify: `scripts/run_relation_feasibility_audit.py`
- Modify: `scripts/run_relation_feasibility_readiness_gate.py`
- Create: `services/artana_evidence_api/tests/unit/test_relation_extraction_consensus.py`
- Modify: `tests/unit/test_relation_feasibility_readiness_gate.py`

**Implementation requirements:**

- Add opt-in consensus mode for trusted-readiness runs:
  generate multiple model samples, normalize candidate identity, and promote
  only stable candidates that pass verification.
- Keep single-pass extraction available for latency-sensitive review queues.
- Add report fields for sample count, consensus threshold, candidates dropped by
  consensus, and candidates recovered by consensus.
- Add model labels to report metadata so current-model and stronger-model runs
  can be compared without guessing.
- Add a registry entry for a stronger model only after live model-health probe
  succeeds in the target environment.
- Use official model guidance as input to the experiment, but decide from local
  readiness reports, not from model marketing or intuition.

**Test checklist:**

- [ ] Add a failing unit test where a candidate appears in two of three samples
  and passes a `2/3` consensus threshold.
- [ ] Add a failing unit test where a candidate appears once and is marked
  unstable.
- [ ] Add a failing readiness test proving the model label and consensus
  settings are present in the readiness report.
- [ ] Add a failing test proving consensus mode cannot credit fallback output.
- [ ] Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_relation_extraction_consensus.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  -q
```

**A/B validation matrix:**

| Variant | Runs | Required comparison |
|---|---:|---|
| Current default model, single sample | 3 | Baseline after PR18-PR20 |
| Stronger model, single sample | 3 | Precision, high-value recall, CURIE rate, latency, cost |
| Current default model, consensus | 3 | Precision gain versus recall loss |
| Stronger model, consensus | 3 | Best readiness candidate if cost and latency are acceptable |

**Merge gate:**

- At least one configured model policy passes the PR16 readiness thresholds
  across three strict live-agent runs, or the report proves the remaining
  blockers precisely enough to feed the next PR.
- Model switch recommendation includes cost, latency, and worst-run metrics.
- The production default is not changed unless repeated readiness evidence
  justifies it.

## PR22: Graph Promotion Readiness Enforcement

Suggested branch: `alvaro/evidence-pr22-trusted-promotion-policy`

Goal: make runtime graph auto-promotion obey the same trust rules as the
readiness gate.

**Files:**

- Create: `services/artana_evidence_db/trusted_relation_promotion_policy.py`
- Modify: `services/artana_evidence_db/graph_validation_service.py`
- Modify: `services/artana_evidence_db/claim_ai_evidence_validation.py`
- Modify: `services/artana_evidence_api/document_extraction_drafts.py`
- Modify: `services/artana_evidence_api/document_extraction_support/trust_ladder.py`
- Create: `services/artana_evidence_db/tests/unit/test_trusted_relation_promotion_policy.py`
- Modify: `services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`

**Implementation requirements:**

- Require no-fallback agent trace metadata for trusted AI relation promotion.
- Require verified subject and object identifiers unless the relation type
  explicitly allows a no-CURIE endpoint and the graph dictionary says why.
- Require entailing support verification.
- Require canonical or approved relation type.
- Require source sentence, locator, provenance, and audit metadata.
- Route missing or proposal-required cases to review queues, not trusted graph.
- Make graph service the final enforcement boundary even if the API makes a
  mistake.

**Test checklist:**

- [ ] Add a graph-service unit test proving a relation with model-only CURIEs is
  rejected for trusted promotion.
- [ ] Add a graph-service unit test proving a governed proposal is staged for
  review and not trusted promotion.
- [ ] Add a graph-service unit test proving fallback trace metadata blocks
  trusted promotion.
- [ ] Add an API draft-builder test proving review-only cases carry enough
  metadata for a curator to approve later.
- [ ] Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_db/tests/unit/test_trusted_relation_promotion_policy.py \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  -q
```

**Adversarial review questions:**

- Can an API bug bypass graph-side trust floors?
- Can fallback metadata be omitted and still promote?
- Can a proposal relation become trusted without approval?
- Can missing CURIEs be hidden in metadata while identifiers are absent?

**Merge gate:**

- Graph trusted promotion rejects missing verifier, missing verified entity,
  fallback trace, unknown relation type, and unapproved proposal cases.
- Full readiness gate passes across three strict live-agent runs.
- `make graph-service-checks`, `make artana-evidence-api-service-checks`, and
  `make service-checks` pass.

## Adversarial Review Loop For Every PR

Run this loop before each PR is marked ready:

1. False-positive reviewer: search for unsupported claims, wrong direction,
   wrong entity boundaries, generic inflation, hidden fallback credit, and
   model-only CURIE trust.
2. False-negative reviewer: search for missed high-value relations,
   over-abstention, proposal misses, and over-pruning of valid specific claims.
3. Dictionary reviewer: search for ambiguous labels, namespace mismatch, stale
   aliases, and unsafe ontology matches.
4. Readiness reviewer: rerun focused tests and inspect the JSON report, not only
   the Markdown summary.
5. Convert every accepted review finding into a failing test or fixture case.
6. Fix the implementation.
7. Rerun focused tests, `make relation-feasibility-quality-gate`, and the
   strict live-agent audit when model credentials are available.
8. Update this plan, the progress tracker, and the PR evidence packet with
   before/after metrics.

Do not resolve a review finding by lowering a readiness threshold.

## Evidence Packet Template

Every PR in this loop must include this exact evidence packet in the PR body:

```text
PR:
Branch:
Base branch:
Base commit:
Goal:
Finding addressed:
Primary metric:
Before metric:
After metric:
Files changed:
Focused tests:
Repository gates:
Live-agent command:
Live-agent report paths:
Readiness report path:
Fallback cases:
Invalid strict-agent cases:
Negative-control leakage:
Raw unknown relation surfaces:
Wrong verified CURIE links:
Model used:
Consensus settings:
Cost/latency note:
Adversarial review findings:
Known remaining risk:
```

## Definition Of Trusted-Graph Ready

The system is trusted-graph ready only when all of these are true in the same
three-run strict live-agent readiness report:

- `trusted_graph_ready == true`.
- Source audit RED count is `0`.
- `completed_agent_precision_against_gold >= 0.8000`.
- `completed_agent_recall_against_gold >= 0.6000`.
- `high_value_recall >= 0.8500`.
- `completed_agent_valuable_candidate_rate >= 0.7000`.
- `generic_relation_rate <= 0.0500`.
- `curie_linked_gold_endpoint_rate >= 0.9500`.
- `verified_curie_match_rate >= 0.9500`.
- `entailment_checked_rate == 1.0000`.
- `fallback_case_count == 0`.
- `invalid_agent_case_count == 0`.
- `negative_control_leakage_count == 0`.
- `raw_unknown_relation_type_count == 0`.
- `raw_unknown_relation_type_surface_count == 0`.
- `wrong_verified_curie_link_count == 0`.
- Graph promotion rejects AI trusted relations that lack verified entities,
  entailing support, approved relation types, provenance, and no-fallback trace
  metadata.

## External Research References

- OpenAI model selection and GPT-5.5 guidance:
  <https://developers.openai.com/api/docs/models>
- OpenAI model optimization and eval loop:
  <https://developers.openai.com/api/docs/guides/model-optimization>
- OpenAI evaluation best practices:
  <https://developers.openai.com/api/docs/guides/evaluation-best-practices>
- Gilda biomedical entity grounding:
  <https://gilda.readthedocs.io/en/latest/>
- BioPortal Annotator:
  <https://bioportal.bioontology.org/annotator>

## Self-Review

- Spec coverage: every blocker from PR16 is mapped to at least one PR lane.
- Placeholder scan: the plan contains no open-ended placeholder tasks.
- Boundary check: Evidence API owns extraction and review, Graph Service owns
  promotion trust, validation scripts own scorecards.
- Safety check: no step allows deterministic fallback, model-only CURIEs, or
  unapproved proposal types to count as trusted graph evidence.
