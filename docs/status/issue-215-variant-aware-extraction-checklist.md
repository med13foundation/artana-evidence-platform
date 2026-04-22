# Issue #215 Variant-Aware Extraction Checklist

Status: Implemented and verified in-repo
Issue: https://github.com/med13foundation/monorepo/issues/215
Last updated: 2026-04-21

## Goal

Close the remaining gap between:

- the variant-aware extraction core in `src/`
- the user-facing document extraction flow in `services/artana_evidence_api`

The issue is complete when a researcher using the public extraction endpoint can
submit a clinical genomics document and get:

- a first-class `VARIANT` entity candidate or governed staged variant entity
- exact anchors: `gene_symbol + hgvs_notation`
- preserved variant metadata when present:
  - transcript
  - `hgvs_cdna`
  - `hgvs_protein`
  - `hgvs_genomic`
  - classification
  - zygosity
  - inheritance
  - exon/intron
  - genomic position / genome build
- variant-rooted phenotype relations, not only generic gene-phenotype claims
- decomposed mechanism claims instead of malformed text fragments
- review items for incomplete or ambiguous variant extraction, rather than
  silent downgrade to vague generic claims

## Delivered State

What now exists in the repo:

- deterministic genomics signal parsing in
  `src/domain/services/genomics_signal_parser.py`
- first-class extracted entity candidates in
  `src/domain/agents/contracts/extraction.py`
- extraction prompts that explicitly preserve anchored variant fields and
  instruct the model to decompose mechanistic chains in
  `src/infrastructure/llm/prompts/extraction/`
- adapter-side supplementation of exact anchored variants from deterministic
  genomics signals in
  `src/infrastructure/llm/adapters/extraction_agent_adapter.py`
- governed persistence and staging of extracted entity candidates in
  `src/application/agents/services/extraction_service.py`
- a public-path variant-aware bridge in
  `services/artana_evidence_api/variant_aware_document_extraction.py`
- public document extraction cutover in
  `services/artana_evidence_api/routers/documents.py`
- proposal/governance support for entity, observation, and claim promotion in
  `services/artana_evidence_api/proposal_actions.py` and
  `services/artana_evidence_api/routers/proposals.py`
- focused bridge, router, promotion, and live messy-text tests under
  `services/artana_evidence_api/tests/unit/` and
  `tests/e2e/test_live_variant_aware_extraction.py`

## Milestone Summary

| Phase | Status | Notes |
| --- | --- | --- |
| 1. Public path cutover | Complete | Public `/documents/{document_id}/extract` now routes genomics-capable documents through the variant-aware bridge. |
| 2. Proposal and governance bridge | Complete | Public path now stages entity, observation, and candidate-claim outputs instead of assuming relation-only extraction. |
| 3. Duplicate collapse and canonicalization | Complete | Equivalent mentions such as `c.977C>A`, `NM_015335.6:c.977C>A (p.Thr326Lys)`, `Thr326Lys`, and `T326K` collapse onto one anchored candidate while preserving evidence. |
| 4. Phenotype and mechanism quality | Complete | Variant-rooted claims are preserved, incomplete phenotype synthesis becomes reviewable output, and decomposed mechanism claims stay as short auditable proposals. |
| 5. Cross-source completion | Complete | Bridge normalization and adapter coverage now keep one variant-aware output shape for `text`, `pdf`, `pubmed`, `clinvar`, and `marrvel`. |
| 6. Tests | Complete | Focused unit, router, live messy-text, and service-level verification all pass. |
| 7. Docs and closeout | Complete in repo | Evidence API docs now describe the shipped behavior. A GitHub issue closeout comment can be posted separately when desired. |

## Detailed Checklist

### Phase 1 Public Path Cutover

#### 1.1 Introduce a variant-aware document extraction bridge in Evidence API

- [x] Add a new internal orchestration module in
      `services/artana_evidence_api/` dedicated to variant-aware extraction
      handoff from harness documents to the newer extraction stack
- [x] Input contract for the bridge includes:
      - document id
      - source type
      - text content
      - current graph transport bundle
      - review context
      - space id
- [x] Output contract for the bridge includes:
      - extracted entities
      - extracted observations
      - extracted relations
      - rejected facts
      - skipped/review-required items
      - diagnostics metadata suitable for artifact persistence

Implemented in:

- `services/artana_evidence_api/variant_aware_document_extraction.py`

Acceptance criteria:

- [x] The bridge constructs a variant-aware extraction request from one
      `HarnessDocumentRecord`
- [x] The bridge returns structured extraction results without depending on the
      legacy `ExtractedRelationCandidate` contract

#### 1.2 Route public document extraction through the new bridge

- [x] Update `services/artana_evidence_api/routers/documents.py` so
      genomics-capable extraction uses the new bridge instead of the older
      relation-candidate-only path
- [x] Keep a compatibility path for obviously non-genomics extraction
- [x] Ensure the run record, artifact storage, and document metadata updates
      still happen for the new path

Acceptance criteria:

- [x] `POST /v1/spaces/{space_id}/documents/{document_id}/extract` uses the new
      variant-aware extraction flow for genomics-capable documents
- [x] Existing harness run and artifact behavior still works
- [x] Document metadata still records extraction status and diagnostics

### Phase 2 Proposal And Governance Bridge

#### 2.1 Stop assuming document extraction is relation-only

- [x] Replace public-path assumptions that all extraction output is
      `ExtractedRelationCandidate`
- [x] Introduce public-path handling for:
      - `ExtractedEntityCandidate`
      - `ExtractedObservation`
      - `ExtractedRelation`
      - `RejectedFact`

Primary touchpoints:

- `services/artana_evidence_api/routers/documents.py`
- `services/artana_evidence_api/variant_aware_document_extraction.py`

Acceptance criteria:

- [x] Variant entity candidates can become staged proposals or governed graph
      writes
- [x] Variant metadata observations can be staged without inventing fake
      generic relation proposals
- [x] Rejected facts are surfaced as diagnostics instead of being silently lost

#### 2.2 Build governed staging for variant-aware outputs

- [x] Add proposal-building support for variant entity candidates
- [x] Add proposal-building or direct governed persistence for variant metadata
      observations
- [x] Add proposal-building support for variant-rooted phenotype and mechanism
      relations
- [x] Add review-item staging for incomplete variant candidates

Acceptance criteria:

- [x] Incomplete variant extraction does not silently collapse to a generic gene
      claim
- [x] Incomplete variant extraction results in explicit reviewable output
- [x] Exact anchored variant extraction can move through the normal governed
      persistence path

### Phase 3 Duplicate Collapse And Canonicalization

#### 3.1 Collapse repeated mentions of the same variant

- [x] Add deterministic collapse rules for equivalent mentions such as:
      - `c.977C>A`
      - `p.Thr326Lys`
      - `NM_015335.6:c.977C>A`
      - `NM_015335.6:c.977C>A (p.Thr326Lys)`
      - short protein-form labels like `Thr326Lys` or `T326K` when supported by
        nearby anchored context
- [x] Prefer the richest supported canonical candidate when multiple candidates
      match the same variant key

Primary touchpoints:

- `src/infrastructure/llm/adapters/extraction_agent_adapter.py`
- `src/domain/services/genomics_signal_parser.py`
- `services/artana_evidence_api/variant_aware_document_extraction.py`

Acceptance criteria:

- [x] One clinical report mentioning the same variant multiple ways does not
      generate a noisy pile of near-duplicate candidates
- [x] The canonical kept variant contains the richest available anchors and
      metadata

#### 3.2 Preserve source evidence while collapsing duplicates

- [x] Keep all relevant evidence locators/excerpts available in diagnostics or
      merged metadata even when duplicate candidates collapse

Acceptance criteria:

- [x] Duplicate collapse does not reduce auditability

### Phase 4 Phenotype And Mechanism Quality Hardening

#### 4.1 Strengthen variant-rooted phenotype extraction

- [x] Prefer phenotype spans that are close to the variant context
- [x] Avoid broad generic fallback claims when the document is clearly
      variant-specific
- [x] Preserve exact evidence spans for phenotype claims

Acceptance criteria:

- [x] Issue-style clinical report produces variant-rooted phenotype output, not
      only generic gene-phenotype output

#### 4.2 Strengthen mechanism-chain decomposition

- [x] Add explicit decomposition expectations for mechanism narratives such as:
      - variant located in functional region or domain
      - variant disrupts modification/binding/degradation step
      - mechanism involves gene or protein context
      - mechanism explains phenotype or downstream state
- [x] Keep speculative steps at lower support and reviewable status
- [x] Do not emit one long opaque mechanism relation at the public-path staging
      layer

Acceptance criteria:

- [x] Phosphodegron / stability / degradation narratives become several short
      auditable claims
- [x] Strongly speculative steps are downgraded or staged for review

### Phase 5 Cross-Source Completion

#### 5.1 PubMed and raw text/PDF

- [x] Verify the new public path works for:
      - uploaded text
      - uploaded PDF
      - PubMed-backed documents

#### 5.2 ClinVar and MARRVEL

- [x] Verify structured genomics grounding feeds directly into first-class
      `VARIANT` output
- [x] Verify source-specific enrichment does not bypass the new variant-aware
      contract

Acceptance criteria:

- [x] All extraction-capable genomics sources use one consistent variant-aware
      output shape

### Phase 6 Tests

#### 6.1 Unit tests

- [x] Variant alias collapse chooses one canonical candidate
- [x] Incomplete anchors trigger review rather than generic fallback
- [x] Phenotype extraction remains variant-rooted when text is clearly
      variant-specific
- [x] Mechanism-chain decomposition yields multiple short claims
- [x] Duplicate collapse preserves evidence references

Covered by:

- `tests/unit/domain/test_genomics_signal_parser.py`
- `tests/unit/infrastructure/llm/test_extraction_agent_adapter.py`
- `tests/unit/application/services/test_extraction_service.py`
- `services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py`

#### 6.2 Integration tests

- [x] Public document extraction route uses the new variant-aware bridge
- [x] Genomics document extraction stages variant entities and variant-rooted
      claims
- [x] Incomplete variant candidates become review items
- [x] Non-genomics extraction still works and does not regress

Covered by:

- `services/artana_evidence_api/tests/unit/test_documents_router.py`

#### 6.3 End-to-end golden examples

- [x] Add one golden test directly based on the issue example:
      - MED13 c.977C>A (p.Thr326Lys)
      - transcript
      - likely pathogenic classification
      - heterozygous / de novo / autosomal dominant context when present
      - exon and genomic coordinates
      - phenotype list
- [x] Add one mechanism-rich coverage case for phosphodegron / Fbw7 /
      degradation / stability language

Acceptance criteria:

- [x] The public extraction flow returns or stages the expected variant and
      associated structured outputs for the issue-style example

Covered by:

- `tests/e2e/test_live_variant_aware_extraction.py`
- `services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py`

#### 6.4 Live verification

- [x] Expand `tests/e2e/test_live_variant_aware_extraction.py` so it asserts:
      - anchored variant entity exists
      - variant metadata is preserved
      - duplicate variant count stays bounded
      - mechanism claims are decomposed, not malformed fragments

### Phase 7 Docs And Closure

#### 7.1 Documentation updates

- [x] Update Evidence API docs to say the public extraction endpoint is now
      variant-aware for genomics-capable documents
- [x] Update user guide examples to show first-class variant extraction instead
      of generic relation-only language
- [x] Record repo-side issue closure status in this checklist

Primary touchpoints:

- `services/artana_evidence_api/docs/api-reference.md`
- `services/artana_evidence_api/docs/user-guide.md`
- `services/artana_evidence_api/docs/full-research-workflow.md`

#### 7.2 Issue closure checklist

Do not close issue #215 until all of these are true:

- [x] Public extraction endpoint uses the new variant-aware path
- [x] Issue-style clinical genomics example passes end to end
- [x] Exact anchored variant entity appears in governed output
- [x] Variant metadata is preserved
- [x] Phenotype links are variant-rooted where appropriate
- [x] Mechanism chain is decomposed into short claims
- [x] Duplicate collapse is acceptable under live noisy text
- [x] Docs describe the shipped behavior accurately

## Verification Runbook

The strongest relevant checks for this slice are:

```bash
venv/bin/ruff check src services/artana_evidence_api tests/e2e/test_live_variant_aware_extraction.py
PYTHONPATH=.:services venv/bin/pytest tests/unit/domain/test_genomics_signal_parser.py -q
PYTHONPATH=.:services venv/bin/pytest tests/unit/infrastructure/llm/test_extraction_agent_adapter.py -q
PYTHONPATH=.:services venv/bin/pytest tests/unit/application/services/test_extraction_service.py -q
PYTHONPATH=.:services venv/bin/pytest services/artana_evidence_api/tests/unit/test_variant_aware_document_extraction.py services/artana_evidence_api/tests/unit/test_documents_router.py services/artana_evidence_api/tests/unit/test_proposal_actions.py services/artana_evidence_api/tests/unit/test_proposals_router.py services/artana_evidence_api/tests/unit/test_graph_client.py -q
PYTHONPATH=.:services venv/bin/pytest tests/e2e/test_live_variant_aware_extraction.py -q -s
make artana-evidence-api-service-checks
```

Note: the repo's service-level gate is the authoritative type-check/lint/test
gate for this slice. Ad hoc top-level `mypy` invocations outside that service
profile can be noisier than the supported verification path.
