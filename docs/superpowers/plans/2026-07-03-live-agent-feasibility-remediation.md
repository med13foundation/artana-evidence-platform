# Live Agent Feasibility Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 2026-07-03 strict live-agent relation feasibility run into a valid, repeatable quality gate and then improve the real agent path until the evidence is specific, valuable, and fallback-free.

**Architecture:** Keep the no-fallback live-agent path strict. Fix scorecard semantics first, then align the benchmark contract with the extraction taxonomy, then improve extraction, relation proposals, CURIE linking, and reporting in separate PRs.

**Tech Stack:** Python 3.13, pytest, Pydantic structured outputs, Artana Kernel model calls, relation feasibility harness under `scripts/validation/relation_feasibility`.

---

## Validity Analysis Of Current Result

Run artifact:

- JSON: `reports/relation_feasibility/20260703T225000Z/relation_feasibility_report.json`
- Markdown: `reports/relation_feasibility/20260703T225000Z/relation_feasibility_report.md`

Current top-line metrics:

```text
verdict=RED
case_count=30
gold_relation_count=25
candidate_count=32
valuable_candidate_count=13
agent_completed_case_count=22
fallback_case_count=0
invalid_agent_case_count=8
precision_against_gold=0.5000
recall_against_gold=0.6400
valuable_candidate_rate=0.4062
generic_relation_rate=0.0938
curie_linked_gold_endpoint_rate=0.1081
```

Validity conclusions:

1. The run is valid as proof that the live agent path executes without deterministic fallback. `fallback_case_count=0` and `fallback_candidate_count=0` are the important breakthrough.
2. The verdict reason is not valid enough yet. Five negative controls returned `llm_empty` with no fallback, which is correct behavior, but the current scorer marks every non-`completed` trace as invalid. `llm_empty` with zero fallback should mean "agent completed with zero extracted candidates."
3. The result is still RED after fixing that scoring bug. The better RED reasons are low CURIE recovery, only 13 valuable candidates out of 32, missed high-value relations, generic sibling noise, and unsupported or over-broad triples.
4. Two gold relations use `CONFERS_RESISTANCE_TO`, which is not in `LLM_VALID_RELATION_TYPES`. Because structured new relation proposals are currently skipped, those cases are partly testing a capability the current scoring path cannot credit.
5. The prompt and schema are not fully aligned. The schema accepts the full taxonomy, but the system prompt lists only a subset of canonical relation types. This likely contributes to outputs like `SUPPORTS` instead of `SENSITIZES_TO`, and `CAUSES` instead of `PREDISPOSES_TO`.
6. CURIE metrics are not trustworthy yet as a quality signal for production truth. The report shows many wrong or missing CURIE flags, so model-provided CURIEs should be treated as hints unless verified by a deterministic or graph-backed linker.
7. `make setup-postgres` is blocked by duplicate active `harness_proposals` rows before migration `024_unique_active_proposal_fingerprints`. This did not block the file-based live feasibility audit, but it blocks a clean full local service setup.

---

### PR 1: Fix Strict-Agent Scorecard Semantics

**Files:**
- Modify: `scripts/validation/relation_feasibility/models.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

- [x] **Step 1: Write failing tests for `llm_empty` no-fallback completion**

Add tests that prove `llm_empty` with zero fallback is an agent-completed zero-candidate result:

```python
def test_llm_empty_without_fallback_counts_as_agent_completed() -> None:
    trace = ExtractionTrace(
        extractor_mode="agent",
        llm_candidate_status="llm_empty",
        llm_candidate_count=0,
        fallback_candidate_count=0,
    )

    assert trace.agent_completed is True
    assert trace.fallback_used is False
```

- [x] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_audit.py::test_llm_empty_without_fallback_counts_as_agent_completed -q
```

Expected before implementation: FAIL because `agent_completed` only accepts `completed`.

- [x] **Step 3: Implement completion semantics**

Update `ExtractionTrace.agent_completed` and the case-level scorer so only
internally consistent empty-agent runs are credited:

```python
if self.extractor_mode != "agent" or self.fallback_used:
    return False
if self.llm_candidate_status == "completed":
    return True
return self.llm_candidate_status == "llm_empty" and self.llm_candidate_count == 0
```

- [x] **Step 4: Update reporting names**

Change report labels so `llm_empty` is not described as invalid extraction:

```text
Agent-completed cases
Agent zero-candidate cases
Fallback/agent-unavailable cases
Invalid strict-agent cases
```

- [x] **Step 5: Verify focused tests**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest tests/unit/test_relation_feasibility_audit.py -q
```

Expected: PASS.

Evidence:

```text
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest tests/unit/test_relation_feasibility_audit.py services/artana_evidence_api/tests/unit/test_document_extraction_modules.py services/artana_evidence_api/tests/unit/test_output_schema_registry.py -q
103 passed

make relation-feasibility-quality-gate
32 passed

make artana-evidence-api-lint
All checks passed!

make artana-evidence-api-type-check
Success: no issues found in 472 source files
```

Adversarial review evidence:

```text
Round 1 finding: malformed llm_empty traces could be overcredited.
Fix: llm_empty requires llm_candidate_count=0 and case-level zero candidates.

Round 1 finding: fallback/fallback_error statuses needed explicit regressions.
Fix: strict fallback and fallback_error traces are covered and remain invalid.

Round 1 finding: CLI and Markdown could over-credit all-candidate metrics.
Fix: CLI labels all-candidate metrics explicitly and Markdown calls them comparison/triage metrics.

Round 2 finding: JSON case trace could still serialize agent_completed=true for malformed llm_empty with emitted candidates.
Fix: CaseResult.to_json overrides extraction_trace.agent_completed with case-level semantics.

Round 2 finding: CLI generic and CURIE metrics still lacked all-candidate prefix.
Fix: CLI now prints all_candidate_generic_relation_rate and all_candidate_curie_linked_gold_endpoint_rate.
```

---

### PR 2: Split Trusted Evidence Metrics From Triage Metrics

**Files:**
- Modify: `scripts/validation/relation_feasibility/models.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Add failing tests for high-value versus low-value recall**

Add a test fixture with one high-value gold relation and one low-value weak association:

```python
def test_summary_reports_high_value_and_low_value_recall_separately() -> None:
    report = run_feasibility_audit(
        cases=(
            _case_with_gold("high", value_level="high"),
            _case_with_gold("low", value_level="low"),
        ),
        extractor=_extracts_only_high_value_case,
        require_agent_completion=True,
    )

    assert report.summary.high_value_gold_relation_count == 1
    assert report.summary.high_value_recall == 1.0
    assert report.summary.low_value_gold_relation_count == 1
    assert report.summary.low_value_recall == 0.0
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_audit.py::test_summary_reports_high_value_and_low_value_recall_separately -q
```

Expected before implementation: FAIL because summary does not expose value-tier recall.

- [ ] **Step 3: Add summary fields**

Add fields to `FeasibilitySummary`:

```python
high_value_gold_relation_count: int
high_value_missed_gold_count: int
high_value_recall: float
low_value_gold_relation_count: int
low_value_missed_gold_count: int
low_value_recall: float
negative_control_empty_count: int
```

- [ ] **Step 4: Compute tiered metrics**

In `build_summary`, count gold relations by `value_level` and missed indices by their gold relation tier. Keep all-candidate recall, but make verdict decisions use high-value recall for trusted graph readiness.

- [ ] **Step 5: Verify focused tests and report rendering**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_audit.py -q
```

Expected: PASS and markdown includes high-value recall, low-value recall, and negative-control empty count.

---

### PR 3: Align Prompt, Schema, And Taxonomy

**Files:**
- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_relation_taxonomy.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Test: `services/artana_evidence_api/tests/unit/test_output_schema_registry.py`

- [ ] **Step 1: Write a failing prompt coverage test**

Add:

```python
def test_llm_prompt_lists_every_extraction_relation_type() -> None:
    for relation_type in LLM_VALID_RELATION_TYPES:
        assert relation_type in LLM_EXTRACTION_SYSTEM_PROMPT
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_prompt_lists_every_extraction_relation_type -q
```

Expected before implementation: FAIL because the prompt omits several canonical types.

- [ ] **Step 3: Generate the prompt relation list from taxonomy**

Create a focused helper in `document_extraction_prompting.py`:

```python
def _relation_type_prompt_lines() -> str:
    return "\n".join(f"    {relation_type}" for relation_type in sorted(LLM_VALID_RELATION_TYPES))
```

Use it inside `LLM_EXTRACTION_SYSTEM_PROMPT` or replace the static subset with a complete generated section.

- [ ] **Step 4: Add specific examples for known failures**

Include examples for:

```text
TP53 loss PREDISPOSES_TO early-onset breast cancer
BRCA1 loss SENSITIZES_TO cisplatin
PD-L1 expression BIOMARKER_FOR response to pembrolizumab
MET amplification PROPOSE_NEW_RELATION_TYPE CONFERS_RESISTANCE_TO erlotinib
```

- [ ] **Step 5: Verify schema compatibility**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_output_schema_registry.py -q
```

Expected: PASS.

---

### PR 4: Score Governed New Relation Proposals Without Treating Them As Trusted Graph Edges

**Files:**
- Modify: `services/artana_evidence_api/document_extraction_contracts.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `scripts/run_relation_feasibility_audit.py`
- Modify: `scripts/validation/relation_feasibility/models.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Write failing extraction test for proposed relation capture**

Change the current expectation that structured new relation proposals disappear:

```python
assert candidates[0].relation_type == "PROPOSE_NEW_RELATION_TYPE"
assert candidates[0].proposed_relation_type == "CONFERS_RESISTANCE_TO"
assert candidates[0].trusted_evidence_eligible is False
```

- [ ] **Step 2: Add typed proposed relation fields**

Extend `ExtractedRelationCandidate`:

```python
proposed_relation_type: str | None = None
new_relation_type_rationale: str | None = None
relation_governance_status: Literal["canonical", "requires_relation_review"] = "canonical"
```

- [ ] **Step 3: Convert `PROPOSE_NEW_RELATION_TYPE` into review-required candidates**

In `_llm_relation_to_candidate`, return a candidate with:

```python
relation_type=LLM_PROPOSE_NEW_RELATION_TYPE
proposed_relation_type=proposed_relation_type
relation_governance_status="requires_relation_review"
```

- [ ] **Step 4: Update feasibility scoring**

When gold relation type equals `candidate.proposed_relation_type`, count it as proposal recall but not trusted canonical evidence:

```python
proposal_matches_gold = (
    candidate.relation_type == "PROPOSE_NEW_RELATION_TYPE"
    and candidate.proposed_relation_type == gold.relation_type
)
```

- [ ] **Step 5: Verify proposal tests**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  tests/unit/test_relation_feasibility_audit.py -q
```

Expected: PASS.

---

### PR 5: Improve Specificity And Argument Fidelity

**Files:**
- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Test: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Add regression cases for observed misses**

Add focused unit cases for:

```text
Olaparib TREATS BRCA-mutated ovarian cancer
TP53 loss PREDISPOSES_TO early-onset breast cancer
PD-L1 expression BIOMARKER_FOR response to pembrolizumab
BRCA1 loss SENSITIZES_TO cisplatin
```

- [ ] **Step 2: Run the failing tests**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest tests/unit/test_relation_feasibility_audit.py -q
```

Expected before prompt changes: FAIL on at least the specificity cases.

- [ ] **Step 3: Tighten extraction instructions**

Update prompt rules:

```text
Preserve modifiers that define the biomedical entity or clinical subgroup.
Do not shorten "BRCA-mutated ovarian cancer" to "ovarian cancer".
Do not shorten "response to pembrolizumab" to "pembrolizumab response" unless both arguments remain explicit in the sentence.
Choose PREDISPOSES_TO for risk language and SENSITIZES_TO for drug-sensitivity language.
```

- [ ] **Step 4: Add post-parse guard against unsupported broadening**

In `llm_fulltext_extraction.py`, reject candidates whose object is a strict generic suffix of the gold-like phrase in the sentence when the sentence contains a more specific object phrase. Keep this conservative and test-driven.

- [ ] **Step 5: Verify focused tests**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  tests/unit/test_relation_feasibility_audit.py -q
```

Expected: PASS.

---

### PR 6: Make CURIE Linking Verifiable Instead Of Model-Guessed

**Files:**
- Modify: `services/artana_evidence_api/document_extraction_support/entity_curie_linking.py`
- Modify: `services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Write failing tests for model-guessed CURIE distrust**

Add:

```python
def test_model_curie_must_match_verified_linker_before_counting_as_linked() -> None:
    candidate = ExtractedRelationCandidate(
        subject_label="MED13",
        subject_curie="HGNC:29186",
        relation_type="ACTIVATES",
        object_label="cardiac septal development",
        object_curie="GO:0031070",
        sentence="MED13 activates cardiac septal development in the embryonic heart.",
    )

    assessment = assess_case(_med13_gold_case(), (candidate,))[0][0]

    assert assessment.has_subject_curie is True
    assert assessment.subject_curie_matches_gold is False
    assert assessment.is_valuable is True
```

- [ ] **Step 2: Add source metadata for CURIEs**

Extend candidate metadata or candidate fields with:

```python
subject_curie_source: Literal["model", "verified_linker", "none"] = "none"
object_curie_source: Literal["model", "verified_linker", "none"] = "none"
```

- [ ] **Step 3: Prefer graph/entity linker over model CURIE**

Use `entity_curie_linking.py` as the single place that normalizes, accepts, or rejects CURIEs. Model CURIEs should be inputs to verification, not final truth.

- [ ] **Step 4: Update scoring**

Report separately:

```text
candidate_curie_present_rate
verified_curie_match_rate
model_curie_wrong_count
```

- [ ] **Step 5: Verify focused tests**

Run:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  tests/unit/test_relation_feasibility_audit.py -q
```

Expected: PASS.

---

### PR 7: Fix Local Postgres Migration Blocker

**Files:**
- Modify: `services/artana_evidence_api/alembic/versions/024_unique_active_proposal_fingerprints.py`
- Test: `services/artana_evidence_api/tests/unit/test_sqlalchemy_stores.py`
- Test: `services/artana_evidence_api/tests/unit/test_proposal_dedup.py`

- [ ] **Step 1: Reproduce duplicate active proposal failure in a migration test**

Use two `harness_proposals` rows with identical `(space_id, claim_fingerprint)` and active statuses:

```python
("pending_review", "promoted")
```

Expected before implementation: unique index creation fails.

- [ ] **Step 2: Add deterministic cleanup before unique index creation**

In migration `024`, before `op.create_index`, mark older duplicate active rows as superseded or withdrawn while preserving audit fields:

```sql
UPDATE artana_evidence_api.harness_proposals p
SET status = 'superseded'
WHERE p.id IN (
  SELECT id FROM (
    SELECT id,
           row_number() OVER (
             PARTITION BY space_id, claim_fingerprint
             ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST, id DESC
           ) AS rn
    FROM artana_evidence_api.harness_proposals
    WHERE claim_fingerprint IS NOT NULL
      AND status IN ('pending_review', 'promoted')
  ) ranked
  WHERE rn > 1
);
```

- [ ] **Step 3: Verify setup**

Run:

```bash
make setup-postgres
```

Expected: completes without duplicate index failure.

---

### PR 8: Rerun Live Gate And Update Evidence Tracker

**Files:**
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Add: `docs/validation/reports/<date>-live-agent-feasibility.md`

- [ ] **Step 1: Run repository checks**

Run:

```bash
make service-checks
```

Expected: PASS.

- [ ] **Step 2: Run strict live-agent feasibility**

Run:

```bash
make live-agent-relation-feasibility-check
```

Expected after remediation:

```text
fallback_cases=0
invalid_agent_cases=0
high_value_recall improves
valuable_candidate_rate improves
curie_linked_gold_endpoint_rate is reported as verified, not guessed
```

- [ ] **Step 3: Add evidence note**

Create a report entry with:

```markdown
# Live Agent Feasibility Evidence - YYYY-MM-DD

- Command: `make live-agent-relation-feasibility-check`
- Report path: `reports/relation_feasibility/<timestamp>/relation_feasibility_report.md`
- Fallback cases:
- Invalid agent cases:
- High-value recall:
- Precision:
- Valuable candidate rate:
- Verified CURIE match rate:
- Remaining RED/YELLOW blockers:
```

- [ ] **Step 4: Update tracker**

Append the result to `docs/validation/evidence-excellence-progress-tracker.md` with the exact report path and metrics.

---

## Execution Order

1. PR 1: scorecard semantics.
2. PR 2: trusted versus triage metrics.
3. PR 3: prompt/schema/taxonomy alignment.
4. PR 4: proposed relation type scoring.
5. PR 5: specificity and argument fidelity.
6. PR 6: verified CURIE linking.
7. PR 7: Postgres migration blocker.
8. PR 8: rerun live gate and update evidence tracker.

## Definition Of Done

```text
fallback_cases=0
invalid_agent_cases=0
negative controls produce zero candidates and are counted as correct empty completions
high_value_recall >= 0.80
precision_against_gold >= 0.80
valuable_candidate_rate >= 0.70
generic_relation_rate <= 0.25
verified CURIE endpoint recovery is reported separately from guessed CURIEs
make service-checks passes
make setup-postgres passes
```
