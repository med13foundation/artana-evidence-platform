# Artana Resource Library – Ingestion & Curation Reliability PRD/FSD

## 1. Purpose

Close reliability and type-safety gaps surfaced by the current CI/pre-commit pipeline:
- Ensure ingestion provenance updates succeed without violating frozen Pydantic models.
- Maintain backward compatibility in RO-Crate packaging while modernising the API.
- Deliver typed review queue objects end-to-end (repository → service → API → tests).

## 2. Background

`make all` and the pre-commit hooks fail today due to:
- Black rewriting legacy files.
- Ruff enforcing rules (`TC003`, `PLC0415`, `T201`, `RUF059`) that existing modules violate.

Functional changes already staged—provenance mutation fix, RO-Crate compatibility, typed review queue—must be documented, hardened, and aligned with the stricter tooling before broader lint cleanup begins.

## 3. Goals

- Preserve Clean Architecture boundaries while:
  - Fixing provenance mutation safety.
  - Supporting legacy `license` kwargs in the RO-Crate builder.
  - Returning strongly typed review queue data.
- Align local tooling (Ruff ≥ 0.14) with the rule set defined in `pyproject.toml`.
- Ensure `make all` passes after targeted fixes.

## 4. Non-Goals

- A full lint/style remediation across untouched modules.
- Large-scale refactors of ingestion or curation flows beyond the issues listed here.

## 5. Functional Requirements

### R1. Ingestion Provenance (BaseIngestor)
- **R1.1** Replace `dataclasses.replace` with `Provenance.add_processing_step()` so ingest metadata is appended without mutating the frozen Pydantic model.
- **R1.2** Preserve provenance processing history for downstream audit logging.

### R2. RO-Crate Builder Compatibility
- **R2.1** Allow legacy constructor usage via `license=` while keeping `license_id` canonical.
- **R2.2** Expose a `license` property mapped to `license_id`; reject conflicting values when both args are provided.
- **R2.3** Reject unexpected kwargs to avoid silent configuration drift.

### R3. Review Queue Type Safety
- **R3.1** Introduce `ReviewQueueItem` dataclass to normalise repository rows and provide typed accessors.
- **R3.2** Return `ReviewQueueItem` from `ReviewService.submit()` and `ReviewService.list_queue()`.
- **R3.3** `/curation/queue` endpoint serialises via `ReviewQueueItem.to_serializable()` without changing the response shape.
- **R3.4** Update unit/integration tests to consume dataclass attributes.

## 6. Tooling & Quality Requirements

- **T1** Upgrade pre-commit Ruff hook to `astral-sh/ruff-pre-commit` (≥ v0.14.3).
- **T2** Ensure `make format`, `make lint`, `make all` all succeed post-change.
- **T3** Regenerate Bandit report; no findings expected for modified files.
- **T4** Use `# noqa: PLC0415` only when architectural layering requires local imports (currently in review service).

## 7. Architecture Impacts

- **Domain/Application Layers:** `ReviewQueueItem` formalises the interface, enabling future pydantic response models.
- **Infrastructure Layer:** Provenance updates are now immutable, preventing ingestion failures when runtime validation rejects data.
- **Packaging Module:** Backward-compatible adjustments stay within the adapter layer; domain entities remain untouched.

## 8. Data Model & Migrations

- No schema or migration changes required. Provenance and review repositories continue using existing tables.

## 9. API Changes

- `/curation/queue` retains the existing JSON payload; internal representation now uses `ReviewQueueItem`.
- No new endpoints introduced.

## 10. Testing Strategy

- **Unit:** Extend review service tests, RO-Crate builder tests, provenance regression tests.
- **Integration:** Re-run ClinVar/PubMed ingestor suites after provenance fix.
- **QA Gates:** `make format`, `make lint`, `make test`, `make all`.
- Pre-commit hooks must run cleanly on all modified files before merge.

## 11. Open Questions

- Should Alembic migrations adopt Ruff `TC00x` rules immediately, or defer to a dedicated cleanup sprint?
- Should `test_real_apis.py` move out of `tests/` to avoid linting constraints intended for true tests?
- Can review service imports be hoisted without breaking dependency container wiring, eliminating the need for `# noqa`?

## 12. Suggested Timeline

| Day | Task |
| --- | ---- |
| 0   | Merge targeted fixes (provenance, RO-Crate, review service) plus Ruff hook upgrade. |
| 1–2 | Address lint issues in the touched files; confirm green `make all`. |
| 3+  | Schedule follow-up sprint for broader Ruff cleanup across untouched modules. |
