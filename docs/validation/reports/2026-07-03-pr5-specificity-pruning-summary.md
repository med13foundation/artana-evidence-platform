# PR-5 Specificity Pruning Evidence Snapshot

Date: 2026-07-03

Branch: planned `alvaro/evidence-pr5-specificity-pruning`; currently stacked
in worktree branch `alvaro/evidence-pr0-quality-harness` until earlier slices
are split.

## Scope

PR-5 suppresses relation over-generalization before candidates reach normal
review or graph staging:

- Redundant `ASSOCIATED_WITH` candidates are pruned when the same normalized
  subject/object pair has a canonical, more-specific sibling relation.
- Weak exploratory generic correlations are not staged as document-extraction
  relation candidates.
- The LLM extraction prompt now makes `ASSOCIATED_WITH` a last resort when a
  more-specific relation fits the same subject/object pair.
- The feasibility audit records `pruned_generic_relation_count` and prints the
  count in JSON, Markdown, and the CLI summary line.

## Strict-Agent Result

The local strict-agent audit remains RED because the LLM/agent extractor did
not complete locally and the run used fallback/unavailable diagnostics. That is
expected and correct for this environment. PR-5's measurable local success is
that no generic relation candidates survive the fallback/triage snapshot.

| Metric | Value |
|---|---:|
| Verdict | RED |
| Precision | 0.7500 |
| Recall | 0.2400 |
| Valuable candidate rate | 0.7500 |
| Generic relation rate | 0.0000 |
| Generic relation count | 0 |
| Pruned generic relation siblings | 0 |
| Agent-completed cases | 0/30 |
| Fallback or unavailable cases | 30/30 |
| Invalid strict-agent cases | 30/30 |
| Fallback candidates that would look valuable | 6 |

## Deterministic Comparison

The deterministic comparison is still triage-only and not agent quality. It is
useful here as a before/after signal for over-generalization.

| Metric | Value |
|---|---:|
| Verdict | YELLOW |
| Precision | 0.7500 |
| Recall | 0.2400 |
| Valuable candidate rate | 0.7500 |
| Generic relation rate | 0.0000 |
| Generic relation count | 0 |
| Pruned generic relation siblings | 0 |

## Focused Validation

- RED/GREEN PR-5 tests:
  - `test_audit_counts_pruned_generic_relation_siblings`
  - `test_extract_relation_candidates_with_llm_prunes_redundant_generic_siblings`
  - `test_draft_builder_prunes_redundant_generic_relation_siblings`
  - `test_extract_relation_candidates_suppresses_weak_generic_correlations`
- Post-adversarial RED/GREEN tests:
  - `test_discover_relation_candidates_reports_llm_pruned_generic_siblings`
  - `test_extract_relation_candidates_with_llm_suppresses_weak_generic_correlations`
  - `test_draft_builder_skips_weak_generic_relation_candidates`
- Focused affected bundle passed:
  `tests/unit/test_relation_feasibility_audit.py`,
  `services/artana_evidence_api/tests/unit/test_document_extraction.py`, and
  `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
  with 104 tests passing after the adversarial fixes.
- Research-init compatibility regressions passed for the seven tests that use
  synthetic LLM candidate fakes.
- `ruff check` on touched PR-5 files passed.
- `make artana-evidence-api-service-checks` passed after moving helper logic
  into support modules to satisfy the 1200-line architecture budget for
  `document_extraction.py`.
- `make service-checks` passed with total coverage 86.83%; live external API,
  running-service, and OpenAI-key integration tests were explicitly skipped.
- Independent adversarial re-review: PASS. Initial BLOCK findings were weak
  exploratory generic LLM candidates reaching draft staging and LLM sibling
  pruning telemetry being dropped before audit diagnostics.

## Artifacts

- Strict-agent JSON:
  `reports/relation_feasibility/2026-07-03-pr5-specificity-pruning-agent-strict/relation_feasibility_report.json`
- Strict-agent Markdown:
  `reports/relation_feasibility/2026-07-03-pr5-specificity-pruning-agent-strict/relation_feasibility_report.md`
- Deterministic JSON:
  `reports/relation_feasibility/2026-07-03-pr5-specificity-pruning-deterministic/relation_feasibility_report.json`
- Deterministic Markdown:
  `reports/relation_feasibility/2026-07-03-pr5-specificity-pruning-deterministic/relation_feasibility_report.md`

## Hashes

| Artifact | SHA-256 |
|---|---|
| strict JSON | `c6c320a277cadb77e3e735308b954a75559e2264be348a32d6c743cacf40838a` |
| strict Markdown | `59b6964dcc0f863297c39b8bed12e79af1d6309354628cb0ea6f77afa67cae76` |
| deterministic JSON | `5562d16393922717adb7ec19418ce844d5737b97d47bf024c0c73610866835c6` |
| deterministic Markdown | `d215308263f83b49758c67c6e8a0771d1834d0249038b7f35948abf9a589e62f` |

## Known Remaining Risk

This slice removes generic relation leakage in local fallback/triage output but
does not prove live-agent extraction quality. The strict-agent run still has
zero completed agent cases, so PR-6 and later slices must keep treating fallback
as failure until a live agent-path inventory artifact exists.
