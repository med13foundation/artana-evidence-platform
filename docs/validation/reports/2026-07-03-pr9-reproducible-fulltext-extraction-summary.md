# PR-9 Reproducible Full-Text Extraction Evidence Snapshot

Date: 2026-07-03

Branch: planned `alvaro/evidence-pr9-reproducible-fulltext-extraction`;
currently stacked in worktree branch `alvaro/evidence-pr0-quality-harness` until
earlier slices are split.

## Scope

PR-9 removes the `text[:4000]` extraction blind spot and makes model replay keys
safe for full-text documents:

- Relation extraction text is split into sentence-aware chunks.
- Each LLM extraction prompt includes prompt version, full document fingerprint,
  chunk index/count, chunk character range, and chunk fingerprint.
- Extraction step keys now include prompt version, model id, max relation
  budget, full normalized document fingerprint, chunk index/count, and chunk
  fingerprint.
- Candidate diagnostics now expose `llm_extraction_chunk_count` and
  `llm_extraction_text_char_count`.

## Focused Result

| Scenario | Result |
|---|---|
| Two documents share the first 4000 chars but differ after that | Different extraction step keys |
| Evidence sentence appears only after the first chunk | Extracted by the LLM path |
| Long-document extraction succeeds | Diagnostics report at least two chunks |
| PR9 refactor exceeds file-size budget | Fixed by moving prompt/conversion helpers into support module |

## Validation

- RED/GREEN PR-9 tests:
  - `test_llm_extraction_step_key_uses_full_text_beyond_prefix`
  - `test_extract_relation_candidates_with_llm_reads_beyond_first_chunk`
- Focused extraction/module suite passed:
  - `services/artana_evidence_api/tests/unit/test_document_extraction.py`
  - `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- `ruff check` on touched PR-9 files passed.
- First `make artana-evidence-api-service-checks` attempt failed on the
  1200-line architecture-size budget.
- Final `make artana-evidence-api-service-checks` passed after the split. Live
  external API, running-service, and OpenAI-key integration tests were
  explicitly skipped.

## Known Remaining Risk

This slice proves full-text prompt coverage and replay-key safety locally. It
does not prove real live-agent recall or precision until the strict audit can
run with a configured model key.
