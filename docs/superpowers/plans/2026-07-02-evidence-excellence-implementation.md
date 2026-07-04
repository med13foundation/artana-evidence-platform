# Evidence Excellence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Artana Evidence relation extraction into an agent-first, evidence-grounded, measurable trusted-graph pipeline with PR-sized safety gates.

**Architecture:** Build a metric spine first, then harden one trust boundary per PR. Evidence API owns extraction, grounding, support verification, scoring, and evaluation orchestration. Graph Service owns canonical relation validation, dictionary governance, persistence safety, trust tiers, and auto-promotion floors.

**Tech Stack:** Python 3.13, FastAPI service modules, Pydantic schemas, pytest, pytest-asyncio, ruff, Alembic for graph schema changes, GitHub Actions, local `uv` commands for fast validation.

---

## Execution Model

This is a multi-PR implementation program. Do not build it as one monolith.
Each PR must make one quality gate stricter and must leave the tracker updated.

Standard branch names:

- `alvaro/evidence-pr0-quality-harness`
- `alvaro/evidence-pr1-no-fallback-trust`
- `alvaro/evidence-pr2-grounding-gate`
- `alvaro/evidence-pr3-entailment-verifier`
- `alvaro/evidence-pr4-relation-type-hardening`
- `alvaro/evidence-pr5-specificity-pruning`
- `alvaro/evidence-pr6-curie-entity-linking`
- `alvaro/evidence-pr7-evidence-aware-scoring`
- `alvaro/evidence-pr8-trust-ladder-hard-floors`
- `alvaro/evidence-pr9-reproducible-fulltext-extraction`
- `alvaro/evidence-pr10-ci-quality-gate`

Every PR uses this loop:

1. Red test: write the regression or quality-gate test first.
2. Verify red: run only the focused test and confirm it fails for the intended reason.
3. Minimal implementation: add the smallest service-local code that makes the test pass.
4. Focused verification: rerun the focused tests, then related service tests.
5. Strict audit: run the relation feasibility audit in strict agent mode.
6. Adversarial review: ask a separate reviewer to try to prove the PR still allows bad evidence.
7. Tracker update: update `docs/validation/evidence-excellence-progress-tracker.md` with commands, reports, and before/after metrics.
8. Full gate: run the relevant make target before merge.

Adversarial reviewer prompt for every PR:

```text
You are reviewing this Artana Evidence PR as an adversarial quality reviewer.
Try to prove that the PR still allows one of these failures:
- deterministic fallback credited as agent success
- sentence stored as evidence without supporting the relation
- generic relation accepted when a specific supported relation exists
- unresolved or junk entity becoming trusted graph data
- raw unknown relation type persisted without review
- machine path reaching trusted tier without verified grounding and hard floors
- benchmark score improving by hiding failures instead of fixing them

Return:
1. Blocking findings with file and line evidence.
2. Missing tests.
3. Metric or audit artifact that should be required before merge.
4. Verdict: BLOCK, NEEDS_EVIDENCE, or PASS.
```

## Current Seed Work

The current worktree already contains starter PR-0 material:

- `scripts/run_relation_feasibility_audit.py`
- `scripts/validation/relation_feasibility/`
- `tests/unit/test_relation_feasibility_audit.py`
- `docs/validation/evidence-excellence-progress-tracker.md`
- `docs/README.md`

Treat those files as the seed for PR-0. Do not mix later trust-gate code into
PR-0 unless it is necessary to make the quality harness accurate.

## File Responsibility Map

### Evaluation And Reporting

- `scripts/run_relation_feasibility_audit.py`: CLI entrypoint for strict agent and deterministic comparison runs.
- `scripts/validation/relation_feasibility/models.py`: typed benchmark, extraction, trace, and report contracts.
- `scripts/validation/relation_feasibility/io.py`: benchmark and report file IO.
- `scripts/validation/relation_feasibility/scoring.py`: quality metrics and verdict rules.
- `scripts/validation/relation_feasibility/reporting.py`: Markdown report rendering.
- `scripts/validation/relation_feasibility/adversarial.py`: static adversarial checks over reports and traces.
- `scripts/validation/relation_feasibility/fixtures/`: committed benchmark fixtures only.
- `tests/unit/test_relation_feasibility_audit.py`: repo-level unit tests for the audit loop.

### Evidence API Trust Gates

- `services/artana_evidence_api/document_extraction.py`: agent extraction orchestration, diagnostics, chunking, model call behavior.
- `services/artana_evidence_api/document_extraction_prompting.py`: structured extraction and review schemas.
- `services/artana_evidence_api/document_extraction_drafts.py`: proposal draft construction and evidence metadata.
- `services/artana_evidence_api/evidence_grounding.py`: deterministic sentence anchor and args-present checks.
- `services/artana_evidence_api/evidence_support_verifier.py`: fail-closed entailment verifier interface and result mapping.
- `services/artana_evidence_api/relation_specificity.py`: generic-sibling suppression and specificity decisions.
- `services/artana_evidence_api/entity_linking.py`: CURIE-or-abstain mention linking for extracted entities.
- `services/artana_evidence_api/ranking.py`: evidence-aware ranking formula.
- `services/artana_evidence_api/score_calibration.py`: calibration function for raw evidence scores.

### Graph Service Trust Gates

- `services/artana_evidence_db/graph_validation_service.py`: authoritative graph write validation.
- `services/artana_evidence_db/kernel_relation_models.py`: relation and relation-evidence persistence columns.
- `services/artana_evidence_db/graph_core_models.py`: Pydantic relation and relation-evidence contracts.
- `services/artana_evidence_db/relation_autopromotion_policy.py`: hard floors for machine promotion policy.
- `services/artana_evidence_db/_relation_auto_promotion_mixin.py`: auto-promotion execution and trust-tier decision.
- `services/artana_evidence_db/relation_trust_tier.py`: explicit trust ladder helpers.
- `services/artana_evidence_db/alembic/versions/036_relation_trust_tier.py`: graph migration for trust-tier fields if needed.

### Tests

- `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `services/artana_evidence_api/tests/unit/test_ranking.py`
- `services/artana_evidence_api/tests/unit/test_relation_type_resolver.py`
- `services/artana_evidence_api/tests/unit/test_proposal_actions.py`
- `services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py`
- `services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py`
- `tests/unit/test_relation_feasibility_audit.py`

## Task 0: Prepare PR Branch And Baseline

**Files:**

- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Modify: `docs/superpowers/plans/2026-07-02-evidence-excellence-implementation.md`

- [ ] **Step 1: Create the PR-0 branch**

Run:

```bash
git switch -c alvaro/evidence-pr0-quality-harness
```

Expected: branch switches to `alvaro/evidence-pr0-quality-harness`.

- [ ] **Step 2: Record current changed files**

Run:

```bash
git status --short
```

Expected: the starter audit files, tracker, and this plan are visible. No unrelated user edits are reverted.

- [ ] **Step 3: Run the current unit checks**

Run:

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest tests/unit/test_relation_feasibility_audit.py -q
```

Expected: relation feasibility audit tests pass.

- [ ] **Step 4: Run the current strict agent baseline**

Run:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-02-pr0-baseline-agent-strict
```

Expected when no OpenAI key is configured: RED with invalid strict-agent cases. Expected when the key is configured: agent completion metrics are populated and fallback cases are not credited as agent success.

- [ ] **Step 5: Update tracker evidence**

Append one evidence-log entry to `docs/validation/evidence-excellence-progress-tracker.md` with the branch, command, result, and report path from Step 4.

## Task 1: PR-0 Quality Harness Expansion

**Files:**

- Modify: `scripts/validation/relation_feasibility/models.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Create: `scripts/validation/relation_feasibility/adversarial.py`
- Create: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Modify: `scripts/run_relation_feasibility_audit.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`

- [ ] **Step 1: Add failing tests for richer gold labels**

Add tests to `tests/unit/test_relation_feasibility_audit.py`:

```python
def test_gold_relation_accepts_grounding_and_curie_labels() -> None:
    relation = GoldRelation(
        subject="MED13",
        relation_type="ACTIVATES",
        object="cardiac septal development",
        support_sentence="MED13 activates cardiac septal development.",
        value_level="high",
        rationale="Specific gene-to-process mechanism.",
        subject_curie="HGNC:22474",
        object_curie=None,
        requires_entailment=True,
    )

    assert relation.subject_curie == "HGNC:22474"
    assert relation.requires_entailment is True


def test_summary_reports_missing_agent_completion_as_red_even_with_candidates() -> None:
    cases = (
        _case(
            case_id="fallback_with_candidate",
            text="MED13 activates cardiac septal development.",
            gold=(
                GoldRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    support_sentence="MED13 activates cardiac septal development.",
                    value_level="high",
                    rationale="Specific mechanism.",
                ),
            ),
        ),
    )

    def extractor(_: str) -> RelationExtractionResult:
        return RelationExtractionResult(
            relations=(
                ExtractedRelation(
                    subject="MED13",
                    relation_type="ACTIVATES",
                    object="cardiac septal development",
                    sentence="MED13 activates cardiac septal development.",
                ),
            ),
            trace=ExtractionTrace(
                extractor_mode="agent",
                llm_candidate_status="unavailable",
                fallback_candidate_count=1,
            ),
        )

    report = run_feasibility_audit(
        cases=cases,
        extractor=extractor,
        require_agent_completion=True,
    )

    assert report.summary.verdict == "RED"
    assert report.summary.invalid_agent_case_count == 1
```

- [ ] **Step 2: Verify the tests fail**

Run:

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest tests/unit/test_relation_feasibility_audit.py -q
```

Expected: failure because `GoldRelation` does not yet expose the richer label fields.

- [ ] **Step 3: Extend typed audit contracts**

Modify `scripts/validation/relation_feasibility/models.py`:

```python
@dataclass(frozen=True, slots=True)
class GoldRelation:
    subject: str
    relation_type: str
    object: str
    support_sentence: str
    value_level: ValueLevel
    rationale: str
    subject_curie: str | None = None
    object_curie: str | None = None
    requires_entailment: bool = True
```

Update `to_json()` to include the three new fields.

- [ ] **Step 4: Parse the new fields**

Modify `scripts/validation/relation_feasibility/io.py` so `_parse_gold_relation()` passes:

```python
subject_curie=_optional_str(raw_relation.get("subject_curie")),
object_curie=_optional_str(raw_relation.get("object_curie")),
requires_entailment=bool(raw_relation.get("requires_entailment", True)),
```

Add a private helper in the same file:

```python
def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
```

- [ ] **Step 5: Add adversarial report checks**

Create `scripts/validation/relation_feasibility/adversarial.py`:

```python
"""Adversarial checks for relation feasibility reports."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.validation.relation_feasibility.models import FeasibilityReport


@dataclass(frozen=True, slots=True)
class AdversarialFinding:
    code: str
    message: str


def find_quality_illusions(report: FeasibilityReport) -> tuple[AdversarialFinding, ...]:
    findings: list[AdversarialFinding] = []
    summary = report.summary
    if summary.fallback_case_count > 0 and summary.agent_completed_case_count == 0:
        findings.append(
            AdversarialFinding(
                code="fallback_only_report",
                message="All reported candidates came from fallback or unavailable agent runs.",
            ),
        )
    if summary.grounded_sentence_rate == 1.0 and summary.candidate_count > 0:
        findings.append(
            AdversarialFinding(
                code="substring_grounding_only",
                message="Grounding is only substring-level until args-present and entailment checks exist.",
            ),
        )
    if summary.generic_relation_rate > 0.05:
        findings.append(
            AdversarialFinding(
                code="generic_relation_rate_high",
                message="Generic relation rate exceeds trusted-graph target.",
            ),
        )
    return tuple(findings)
```

- [ ] **Step 6: Render adversarial findings**

Modify `scripts/validation/relation_feasibility/reporting.py` to append an `Adversarial Checks` section using `find_quality_illusions(report)`.

- [ ] **Step 7: Add the expanded fixture**

Create `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json` with at least these categories:

- `strong_specific`
- `weak_association`
- `negative_control`
- `complex_mispairing`
- `generic_sibling`
- `long_document`

The initial PR-0 target is at least 30 cases. If live expert labels are not yet available, mark fixture provenance as `"curated_synthetic_seed"` in the JSON root and do not claim production representativeness in reports.

- [ ] **Step 8: Add CLI case selection**

Modify `scripts/run_relation_feasibility_audit.py` to support:

```bash
--cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json
```

Keep the current starter fixture as the default until v2 has 30 cases and passing parser tests.

- [ ] **Step 9: Verify PR-0**

Run:

```bash
uv run --python python3.13 \
  --with ruff ruff check \
  scripts/run_relation_feasibility_audit.py \
  scripts/validation/relation_feasibility \
  tests/unit/test_relation_feasibility_audit.py

uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest tests/unit/test_relation_feasibility_audit.py -q
```

Expected: ruff passes and all relation feasibility unit tests pass.

- [ ] **Step 10: Run adversarial audit and update tracker**

Run:

```bash
uv run --python python3.13 \
  python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json \
  --output-dir reports/relation_feasibility/2026-07-02-pr0-agent-strict-v2
```

Update `docs/validation/evidence-excellence-progress-tracker.md` with report path, verdict, agent completion, fallback count, and adversarial findings.

## Task 2: PR-1 No Fallback Trust

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_contracts.py`
- Modify: `services/artana_evidence_api/document_extraction_diagnostics.py`
- Modify: `services/artana_evidence_api/document_extraction.py`
- Modify: `services/artana_evidence_api/routers/documents.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- Modify: `services/artana_evidence_api/tests/unit/test_documents_router.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`

- [ ] **Step 1: Write fallback-credit regression tests**

Add tests asserting that `llm_candidate_status in {"unavailable", "fallback", "fallback_error", "llm_empty"}` yields metadata with:

```python
{
    "agent_extraction_completed": False,
    "fallback_output_used": True,
    "trusted_evidence_eligible": False,
}
```

- [ ] **Step 2: Verify tests fail**

Run:

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_documents_router.py \
  -q
```

Expected: failure because the explicit trusted eligibility metadata does not exist yet.

- [ ] **Step 3: Add diagnostic properties**

Extend `DocumentCandidateExtractionDiagnostics.as_metadata()` with explicit booleans:

```python
agent_extraction_completed = self.llm_candidate_status == "completed"
fallback_output_used = self.llm_candidate_status in {
    "llm_empty",
    "fallback",
    "fallback_error",
    "unavailable",
} or self.fallback_candidate_count > 0
trusted_evidence_eligible = agent_extraction_completed and not fallback_output_used
```

- [ ] **Step 4: Propagate metadata to proposal/document paths**

Ensure document ingestion and proposal creation paths carry the three booleans into proposal metadata where candidate extraction diagnostics are already stored.

- [ ] **Step 5: Verify PR-1**

Run:

```bash
make artana-evidence-api-service-checks
```

Expected: Evidence API checks pass.

- [ ] **Step 6: Adversarial review**

Ask the reviewer to find any route where fallback output can produce metadata with `trusted_evidence_eligible=True`.

## Task 3: PR-2 Evidence Grounding Gate

**Files:**

- Create: `services/artana_evidence_api/evidence_grounding.py`
- Modify: `services/artana_evidence_api/document_extraction_drafts.py`
- Modify: `services/artana_evidence_db/graph_validation_service.py`
- Create: `services/artana_evidence_api/tests/unit/test_evidence_grounding.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction.py`
- Modify: `services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py`

- [ ] **Step 1: Write anchor and args-present tests**

Create tests for:

- exact sentence anchor
- whitespace-normalized anchor
- fuzzy anchor below threshold rejected
- subject present and object present
- variant normalization example `p.Arg1174*` matching `R1174*`

- [ ] **Step 2: Implement deterministic grounding**

Create `services/artana_evidence_api/evidence_grounding.py` with:

```python
GroundingMatchKind = Literal["exact", "whitespace_normalized", "fuzzy", "none"]

@dataclass(frozen=True, slots=True)
class SentenceAnchor:
    start: int | None
    end: int | None
    match_kind: GroundingMatchKind
    score: float

@dataclass(frozen=True, slots=True)
class EvidenceGroundingResult:
    anchor: SentenceAnchor
    subject_present: bool
    object_present: bool

    @property
    def grounded(self) -> bool:
        return self.anchor.match_kind != "none" and self.subject_present and self.object_present
```

Add `anchor_sentence()`, `args_present()`, and `ground_relation_sentence()`.

- [ ] **Step 3: Persist grounding metadata**

Modify `build_document_extraction_drafts()` to add:

```python
"evidence_grounding": {
    "anchor_start": result.anchor.start,
    "anchor_end": result.anchor.end,
    "match_kind": result.anchor.match_kind,
    "subject_present": result.subject_present,
    "object_present": result.object_present,
    "grounded": result.grounded,
}
```

- [ ] **Step 4: Harden graph validation for AI-created relations**

Modify `GraphValidationService._has_evidence()` or its caller so AI-created relation writes require structured grounding metadata, not just any non-empty evidence string.

- [ ] **Step 5: Verify PR-2**

Run:

```bash
make artana-evidence-api-service-checks
make graph-service-checks
```

Expected: both relevant service checks pass.

- [ ] **Step 6: Audit and adversarial review**

Run strict audit and ask the reviewer to find a relation that passes with `"n/a"` evidence or a sentence missing one argument.

## Task 4: PR-3 Entailment Support Verifier

**Files:**

- Create: `services/artana_evidence_api/evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_drafts.py`
- Create: `services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction.py`

- [ ] **Step 1: Write fail-closed verifier tests**

Test cases:

- supported sentence returns `ENTAILS`
- unrelated sentence returns `NEUTRAL`
- contradiction returns `CONTRADICTS`
- model exception returns `NEUTRAL`

- [ ] **Step 2: Create verifier contract**

Create:

```python
TripleSupport = Literal["ENTAILS", "NEUTRAL", "CONTRADICTS"]

@dataclass(frozen=True, slots=True)
class TripleSupportResult:
    support: TripleSupport
    rationale: str
    model_id: str | None = None
```

Add `verify_triple_support()` with a fake model port path in tests and a production model path following the existing structured-output pattern.

- [ ] **Step 3: Integrate only after grounding passes**

Call the verifier only when PR-2 grounding says the sentence is anchored and both args are present.

- [ ] **Step 4: Reject contradictions**

Ensure `CONTRADICTS` marks proposal metadata as not trusted-eligible and gives low ranking/review priority.

- [ ] **Step 5: Verify PR-3**

Run:

```bash
make artana-evidence-api-service-checks
```

Expected: Evidence API checks pass and strict audit reports support-check coverage.

## Task 5: PR-4 Relation Type Hardening

**Files:**

- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_relation_taxonomy.py`
- Modify: `services/artana_evidence_api/relation_type_resolver.py`
- Modify: `services/artana_evidence_api/graph_integration/preflight.py`
- Modify: `services/artana_evidence_api/tests/unit/test_relation_type_resolver.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`

- [ ] **Step 1: Write tests for fail-closed unknown types**

Assert resolver failure produces a review-required decision, not `REGISTER_NEW` with raw type.

- [ ] **Step 2: Constrain extraction schema**

Change the LLM schema so canonical relation types are a typed enum or `Literal` union, and new-type proposals use a separate structured field.

- [ ] **Step 3: Deny legacy validation by default for relation writes**

Change `_legacy_allowed_validation()` behavior for relation validation paths so unknown authority means review-required or blocked, not persistable.

- [ ] **Step 4: Verify PR-4**

Run:

```bash
make artana-evidence-api-service-checks
```

Expected: raw unknown relation type persistence is covered by tests and blocked or queued.

## Task 6: PR-5 Specificity Pruning

**Files:**

- Create: `services/artana_evidence_api/relation_specificity.py`
- Modify: `services/artana_evidence_api/document_extraction.py`
- Create: `services/artana_evidence_api/tests/unit/test_relation_specificity.py`
- Modify: `tests/unit/test_relation_feasibility_audit.py`

- [ ] **Step 1: Write generic sibling tests**

Use candidate pairs where `X ASSOCIATED_WITH Y` and `X CONFERS_RESISTANCE_TO Y` share sentence and arguments. Assert the generic sibling is suppressed.

- [ ] **Step 2: Implement pruning**

Create a pure function:

```python
def prune_generic_siblings(
    candidates: Sequence[ExtractedRelationCandidate],
) -> tuple[ExtractedRelationCandidate, ...]:
    ...
```

- [ ] **Step 3: Integrate after relation resolution**

Call pruning after LLM candidate cleanup and relation-type resolution, before proposal drafts are built.

- [ ] **Step 4: Verify PR-5**

Run:

```bash
make artana-evidence-api-service-checks
```

Expected: generic relation rate drops in the audit when a specific sibling exists.

## Task 7: PR-6 CURIE Entity Linking

**Files:**

- Create: `services/artana_evidence_api/entity_linking.py`
- Create: `services/artana_evidence_api/entity_linking_contracts.py`
- Modify: `services/artana_evidence_api/document_extraction.py`
- Modify: `services/artana_evidence_api/document_extraction_drafts.py`
- Modify: `services/artana_evidence_api/proposal_actions.py`
- Create: `services/artana_evidence_api/tests/unit/test_entity_linking.py`
- Modify: `services/artana_evidence_api/tests/unit/test_proposal_actions.py`

- [ ] **Step 1: Write CURIE-or-abstain tests**

Test BRCA1, MED13, `p.Arg1174*`, a disease synonym, and an unknown junk label.

- [ ] **Step 2: Add contracts**

Create:

```python
EntityMentionType = Literal["gene", "disease", "phenotype", "drug", "protein", "variant", "unknown"]
EntityLinkDecisionType = Literal["linked", "abstain"]

@dataclass(frozen=True, slots=True)
class EntityLinkDecision:
    decision: EntityLinkDecisionType
    mention: str
    mention_type: EntityMentionType
    curie: str | None
    confidence: float
    rationale: str
```

- [ ] **Step 3: Prevent blind auto-create for abstained labels**

Change proposal promotion so abstained extracted labels queue for review instead of calling `_create_graph_entity_for_label()`.

- [ ] **Step 4: Verify PR-6**

Run:

```bash
make artana-evidence-api-service-checks
```

Expected: unknown labels do not auto-create trusted graph nodes from agent extraction.

## Task 8: PR-7 Evidence-Aware Scoring

**Files:**

- Modify: `services/artana_evidence_api/ranking.py`
- Create: `services/artana_evidence_api/score_calibration.py`
- Modify: `services/artana_evidence_api/document_extraction_contracts.py`
- Modify: `services/artana_evidence_api/tests/unit/test_ranking.py`
- Create: `services/artana_evidence_api/tests/unit/test_score_calibration.py`

- [ ] **Step 1: Write score-separation tests**

Assert a grounded specific causal relation outranks an equally relevant generic association, and unsupported/off-target claims have a hard low ceiling.

- [ ] **Step 2: Implement multiplicative evidence-aware scoring**

Use grounding and factual support as caps rather than small additive terms.

- [ ] **Step 3: Add calibration function**

Start with a deterministic table-based calibrator until enough labeled data exists for isotonic regression.

- [ ] **Step 4: Verify PR-7**

Run:

```bash
make artana-evidence-api-service-checks
```

Expected: score collapse between generic and specific relations is eliminated in tests.

## Task 9: PR-8 Trust Ladder And Hard Floors

**Files:**

- Create: `services/artana_evidence_db/relation_trust_tier.py`
- Modify: `services/artana_evidence_db/relation_autopromotion_policy.py`
- Modify: `services/artana_evidence_db/_relation_auto_promotion_mixin.py`
- Modify: `services/artana_evidence_db/kernel_relation_models.py`
- Modify: `services/artana_evidence_db/graph_core_models.py`
- Create: `services/artana_evidence_db/alembic/versions/036_relation_trust_tier.py`
- Modify: `services/artana_evidence_db/tests/unit/test_relation_auto_promotion.py`

- [ ] **Step 1: Write hard-floor tests**

Assert env or space policy cannot lower machine promotion below:

- at least 2 distinct sources
- at least 0.90 calibrated confidence
- conflict blocking enabled
- verified grounding required for machine trust

- [ ] **Step 2: Add trust tier helper**

Create:

```python
RelationTrustTier = Literal["CANDIDATE", "MACHINE_VERIFIED", "HUMAN_CURATED"]
```

Add helper functions that derive the allowed next tier from reviewer and evidence state.

- [ ] **Step 3: Add migration if a persisted tier column is required**

Use Alembic revision `036_relation_trust_tier.py` to add a nullable or defaulted trust-tier column. Keep migration forward-only.

- [ ] **Step 4: Verify PR-8**

Run:

```bash
make graph-service-checks
```

Expected: graph service checks pass and auto-promotion cannot cross hard floors.

## Task 10: PR-9 Reproducible Full-Text Extraction

**Files:**

- Modify: `services/artana_evidence_api/document_extraction.py`
- Create: `services/artana_evidence_api/document_chunking.py`
- Create: `services/artana_evidence_api/tests/unit/test_document_chunking.py`
- Modify: `services/artana_evidence_api/tests/unit/test_document_extraction.py`

- [ ] **Step 1: Write cache-key tests**

Assert the extraction step key changes when model id, prompt version, max relations, or text changes.

- [ ] **Step 2: Write long-document tests**

Assert a relation after character 4000 is included in a later chunk.

- [ ] **Step 3: Implement chunking**

Create chunk windows with sentence-boundary overlap using `_SENTENCE_SPLIT_RE` semantics.

- [ ] **Step 4: Pin model behavior**

Set temperature to 0 for extraction and review model calls where the model adapter supports it. Include model id and prompt version in replay keys.

- [ ] **Step 5: Verify PR-9**

Run:

```bash
make artana-evidence-api-service-checks
```

Expected: full-text extraction does not silently ignore document tails.

## Task 11: PR-10 CI Quality Gate

**Files:**

- Modify: `.github/workflows/evidence-api-service-checks.yml`
- Modify: `scripts/ci/plan_service_checks.py`
- Create: `tests/unit/test_evidence_quality_ci_contract.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`

- [ ] **Step 1: Write CI planner tests**

Assert changes under `scripts/validation/relation_feasibility/` and evidence-quality service files trigger the quality audit job.

- [ ] **Step 2: Add non-secret CI quality job**

Add a deterministic audit job using committed fixtures and no live API key. The job must fail if deterministic regression metrics drop below configured thresholds.

- [ ] **Step 3: Add optional live agent quality job**

Add a workflow-dispatch or secret-gated job that runs strict agent mode only when the required API key secret is present.

- [ ] **Step 4: Verify PR-10**

Run:

```bash
make service-checks
```

Expected: aggregate service checks pass locally; GitHub Actions quality gate is visible on PRs.

## Global Verification Commands

Run these before claiming any implementation PR is ready:

```bash
git diff --check
```

```bash
uv run --python python3.13 \
  --with ruff ruff check \
  scripts/run_relation_feasibility_audit.py \
  scripts/validation/relation_feasibility \
  tests/unit/test_relation_feasibility_audit.py
```

```bash
uv run --python python3.13 \
  --with pytest --with pytest-asyncio \
  pytest tests/unit/test_relation_feasibility_audit.py -q
```

When Evidence API changes:

```bash
make artana-evidence-api-service-checks
```

When Graph Service changes:

```bash
make graph-service-checks
```

Before final merge of a phase:

```bash
make service-checks
```

## Completion Criteria

The implementation program is complete only when
`docs/validation/evidence-excellence-progress-tracker.md` shows:

- strict agent evaluation reports attached for the current gold set
- deterministic fallback not counted as agent success
- fallback trusted count is 0
- both-args-present and entailment support are measured
- generic sibling suppression is measured
- CURIE linking or abstain is measured
- trust hard floors are tested
- reproducibility tests cover model, prompt, cache, and long documents
- CI enforces the deterministic quality gate and exposes optional live agent evaluation

## Self-Review Notes

Spec coverage:

- PR-0 covers the measurement spine.
- PR-1 covers fallback-vs-agent truth.
- PR-2 and PR-3 cover grounding and support verification.
- PR-4 and PR-5 cover relation specificity and relation-type governance.
- PR-6 covers entity identity and abstention.
- PR-7 covers meaningful ranking.
- PR-8 covers trust governance.
- PR-9 covers reproducibility and long documents.
- PR-10 covers CI enforcement.

Type consistency:

- Relation audit types stay under `scripts/validation/relation_feasibility/models.py`.
- Evidence API gates do not import Graph Service internals.
- Graph Service validation consumes structured metadata and persistence fields, not Evidence API modules.

Empty-section scan:

- This plan intentionally avoids empty implementation sections. Subsequent PRs should create more focused per-PR plans only if a task needs decomposition before code.
