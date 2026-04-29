# Full Type Hardening Plan

This plan turns the current mypy cleanup into a measurable engineering project.
The goal is not "make mypy quiet" by adding suppressions. The goal is to make
the service contracts, JSON payloads, SQLAlchemy access, tests, and package
boundaries precise enough that the type checker can follow imports without
losing confidence.

## Current State

The repo now has two strict runtime type gates:

- Evidence API: `make -s artana-evidence-api-type-check`
- Graph service: `make -s graph-service-type-check`

Both runtime gates run package-based mypy from `services/`, follow imports, and
do not use broad `--disable-error-code` suppressions. The graph gate also keeps
`scripts/export_graph_openapi.py` covered with a separate script-level mypy
check so moving the service package to `-p artana_evidence_db` does not drop
OpenAPI exporter coverage.

Tests and Alembic migrations remain excluded from the runtime type gates by
design. Runtime gates enforce production service contracts; migration scripts
are historical operational scripts, and tests can be typed later through a
separate test-specific gate without weakening runtime enforcement.

`disallow_any_expr = false` remains intentional. The services cross JSON,
Pydantic, SQLAlchemy, and external payload boundaries; the enforced policy is to
use typed contracts and local narrowing helpers at those boundaries rather than
turn on a global expression-level `Any` ban that would create noise without a
clearer runtime contract.

The only remaining `ignore_missing_imports = true` override is for `requests`
and `requests.*`, because this environment does not currently provide bundled
`requests` stubs. New local service modules must not be added to missing-import
overrides.

Historical baseline: the first strict-import Evidence API runtime run had
`351` errors across `34` files, and the graph-service runtime run had `1,545`
errors across `74` files. Both strict-import baselines now report `0` errors.

## First Principles

1. Type checking is a contract system, not a formatting gate.
   Every fix should make an API boundary, data shape, or runtime assumption more
   explicit.

2. Shrink broad uncertainty before fixing individual errors.
   A single bad JSON alias, SQLAlchemy result type, or import mode can create
   hundreds of noisy downstream errors.

3. Production contracts come before test ergonomics.
   Harden runtime types first, then adjust test fixtures to match the stricter
   contracts.

4. Do not spread `Any`.
   If an escape hatch is unavoidable for external runtimes, keep it local,
   named, and documented.

5. Keep every PR mergeable.
   Each slice should keep the existing service checks green and reduce at least
   one measured category of type debt.

## Target End State

The final state should be:

- Evidence API type check runs without `--follow-imports=skip`.
- Graph service type check runs without `--follow-imports=skip`.
- Broad disabled error classes are removed from service type gates.
- JSON payloads have typed access helpers instead of ad hoc indexing into
  `JSONValue`.
- SQLAlchemy `Result`, `Row`, and scalar query usage is typed consistently.
- Runtime tests use typed fixtures/builders where production contracts require
  them; broader test-suite typing is left to a separate future gate.
- CI can enforce the stricter gates without hiding cross-module drift.

## Workstreams

### 1. Baseline And Measurement Harness

Purpose: make the problem observable before changing behavior.

Tasks:

- Add strict exploratory targets that do not replace the current CI gate yet:
  - `artana-evidence-api-type-check-strict-imports`
  - `graph-service-type-check-strict-imports`
- Make those targets run from one package root so mypy does not see the same
  file as both `services.artana_evidence_api.*` and `artana_evidence_api.*`.
- Add a small script or documented command that summarizes mypy errors by:
  - error code
  - file
  - production vs test path
  - service
- Store each baseline in a lightweight text artifact during the work, for
  example `tmp/type-hardening/evidence-api-baseline.txt`. Do not commit large
  generated logs.

Acceptance:

- Current gates still pass.
- Strict exploratory targets run repeatably.
- Baseline counts are available before any broad refactor starts.

### 2. Package And Mypy Configuration Cleanup

Purpose: remove structural noise before fixing real typing problems.

Tasks:

- Standardize mypy invocation around package names from `services/`, not mixed
  path/package invocations.
- Clean stale or unused `pyproject.toml` mypy override sections.
- Keep Alembic migrations excluded from runtime type gates, because migration
  scripts are not the same quality target as production service code.
- Keep tests excluded from runtime type gates; add a separate test-type gate in
  a future issue if test typing becomes a product priority.

Acceptance:

- No duplicate-module mypy errors.
- No unused mypy config sections.
- Strict-import exploratory command reports real type errors, not invocation
  artifacts.

### 3. JSON And Payload Typing

Purpose: eliminate the largest source of noisy union errors.

Typical symptoms:

- `JSONValue` indexed as if it is always a dict.
- `metadata["key"]["nested"]` without narrowing.
- Lists/dicts inferred as `object` or broad `JSONValue`.
- Tests asserting into nested payloads without type guards.

Tasks:

- Add or consolidate helpers for:
  - `as_json_object(value, context)`
  - `as_json_array(value, context)`
  - `optional_json_object(value)`
  - typed string/int/bool extraction from metadata
- Use those helpers in production code first:
  - orchestrator shadow planner payloads
  - phase comparison payloads
  - inline worker bridge metadata
  - source-document bridge metadata
- Update tests to use typed builders or local narrowing helpers before indexing.

Acceptance:

- `union-attr`, `index`, `operator`, and `typeddict-item` counts drop sharply.
- JSON narrowing lives in shared helpers, not repeated inline casts.
- Current service checks stay green.

### 4. SQLAlchemy Typing

Purpose: make database access typed instead of relying on implicit row shapes.

Typical symptoms:

- `Result[object]` where SQLAlchemy expects tuple row types.
- `.execute()` results treated as scalars without `.scalar_one()` or
  `.scalars()`.
- ORM model IDs and SQL expression values mixing raw strings and UUIDs.

Tasks:

- Fix repository result annotations in source-document bridges and related
  stores.
- Prefer `.scalars()`, `.scalar_one()`, `.mappings()`, or typed row unpacking
  over generic `Result[object]`.
- Keep migration scripts excluded or narrowly typed.

Acceptance:

- SQLAlchemy-specific `type-var`, `return-value`, and row-access errors are
  removed from production service code.
- Repository tests still pass against isolated Postgres.

### 5. Domain Contract And TypedDict Cleanup

Purpose: make service payload contracts explicit at the boundaries.

Tasks:

- Replace loose `dict[str, object]` request/response payloads with existing
  `JSONObject`, `TypedDict`, or Pydantic models where a real contract exists.
- Fix `ProposedRelation`, graph fact assessment, orchestrator decision, and
  review payload builders so tests and runtime use the same shapes.
- Avoid widening to `object` when the value is actually `JSONValue`.

Acceptance:

- `dict-item`, `list-item`, `return-value`, and `call-arg` errors are reduced
  in production and tests.
- Domain contract tests remain behaviorally unchanged.

### 6. Dependency Injection And Router Boundary Typing

Purpose: remove broad FastAPI and dependency typing suppressions carefully.

Tasks:

- Add typed dependency aliases where FastAPI `Depends(...)` creates noisy
  defaults.
- Keep router functions readable while making injected services explicit.
- Address `attr-defined` and `arg-type` errors caused by protocol/object
  mismatch.

Acceptance:

- Router modules pass without broad `attr-defined` and `arg-type` suppression.
- No endpoint behavior changes.
- OpenAPI contract checks still pass.

### 7. Test Fixture Hardening

Purpose: make tests prove the real contracts instead of bypassing them.

Tasks:

- Add typed fixture builders for common payload families:
  - graph responses
  - orchestrator artifacts
  - review items
  - source documents
  - inline worker bridge payloads
- Replace repeated raw nested dictionaries where they cause type drift.
- Remove redundant casts only after production typing is stable.

Acceptance:

- Tests type-check under the selected test gate.
- Runtime tests still pass.
- Test helper APIs are smaller than the duplicated dictionaries they replace.

### 8. Remove Disabled Error Codes In Order

Purpose: convert the cleanup into visible, reviewable milestones.

Recommended removal order:

1. `unreachable`
2. `has-type`
3. `assignment`
4. `attr-defined`
5. `arg-type`
6. `no-untyped-def`
7. `untyped-decorator`
8. `no-any-return`
9. `no-any-unimported`
10. `misc`

Rationale:

- The first three are usually local and low risk.
- `attr-defined` and `arg-type` expose protocol/interface drift.
- `no-untyped-def` and `untyped-decorator` require broader API decisions.
- `no-any-return`, `no-any-unimported`, and `misc` should be last because they
  often depend on import/config and third-party typing work.

Acceptance:

- Each removed error code stays removed in CI.
- If an error code must remain disabled for a narrow module, the override is
  local and documented in `pyproject.toml`.

### 9. Remove `--follow-imports=skip`

Purpose: make mypy validate the real dependency graph.

Tasks:

- Remove the flag from Evidence API first.
- Run full service checks.
- Remove the flag from graph service second.
- Run full service checks again.

Acceptance:

- `make -s artana-evidence-api-service-checks` passes.
- `make -s graph-service-checks` passes.
- Strict import-following is the default gate, not an exploratory target.

## PR Plan

This should not be one massive PR. Use stacked, measurable PRs.

1. PR 1: Add strict exploratory targets and baseline summary script.
2. PR 2: Clean package/mypy config and stale overrides.
3. PR 3: JSON narrowing helpers plus first production payload slice.
4. PR 4: SQLAlchemy result typing slice.
5. PR 5: Orchestrator/shadow planner payload typing.
6. PR 6: Router/dependency boundary typing.
7. PR 7: Test fixture hardening.
8. PR 8: Remove remaining disabled error codes for Evidence API.
9. PR 9: Remove `--follow-imports=skip` for Evidence API.
10. PR 10: Repeat strict-import removal for graph service.

Each PR should include:

- before/after mypy error count for the targeted slice
- exact command output summary
- affected error codes
- service checks run

## Tracking Checklist

- [x] Add strict exploratory mypy targets.
- [x] Add baseline summary command/script.
- [x] Capture Evidence API strict-import baseline.
- [x] Capture graph service strict-import baseline.
- [x] Fix package invocation and stale mypy config.
- [x] Add JSON narrowing helpers.
- [x] Harden first production JSON payload access slice.
- [x] Harden first SQLAlchemy repository/result typing slice.
- [x] Harden first orchestrator and shadow planner payload type slice.
- [x] Harden first router/dependency injection typing slice.
- [x] Decide test typing policy: runtime gates stay production-only; typed test
  fixture builders are future follow-up work, not required for the runtime gate.
- [x] Remove disabled Evidence API error codes from the strict-import gate.
- [x] Remove Evidence API `--follow-imports=skip` from the exploratory runtime gate.
- [x] Remove graph-service `--follow-imports=skip`.
- [x] Remove broad graph-service disabled error codes from the default gate.
- [x] Run and record current `make -s artana-evidence-api-service-checks`.
- [x] Run and record current `make -s graph-service-checks`.

## Progress Log

### Evidence API Runtime Strict-Import Gate

Applied in `alvaro/full-type-hardening`:

- Added strict-import mypy targets and a baseline summary script.
- Added JSON narrowing helpers in `artana_evidence_api.types.common`.
- Hardened production JSON access in the shadow planner, research-init runtime,
  transparency helpers, run routers, variant extraction, and supervisor flows.
- Fixed the first SQLAlchemy `Result` typing issue in the source-document bridge.
- Tightened runtime-skill registry typing and graph transport response narrowing.
- Updated async route annotations where endpoints legitimately return `202`
  `JSONResponse` objects.

Measured result:

- Before: `351` Evidence API runtime strict-import errors across `34` files.
- After: `0` Evidence API runtime strict-import errors across `196` runtime
  source files.

Verification:

- `make -s artana-evidence-api-type-check-strict-imports`
- `make -s artana-evidence-api-lint`
- `make -s artana-evidence-api-type-check`
- `make -s graph-service-type-check`
- `make -s artana-evidence-api-service-checks`
- `make -s graph-service-checks`

### Evidence API Disabled-Code Burn-Down

Additional hardening applied in `alvaro/full-type-hardening`:

- Removed these Evidence API strict-import suppressions:
  `no-any-unimported`, `no-any-return`, `misc`, `untyped-decorator`,
  `has-type`, `no-untyped-def`, `unreachable`, `assignment`, and
  `attr-defined`.
- Removed `arg-type`, the final Evidence API strict-import suppression.
- Fixed missing helper annotations, unreachable branches, rowcount handling,
  graph transport context-manager typing, Phase 1 compare coroutine handling,
  LLM structured-output narrowing, and several JSON payload conversions.

Measured result:

- Before this burn-down: `445` Evidence API errors across `58` files when all
  Evidence API suppressions were removed.
- Intermediate remaining debt: `270` `arg-type` errors across `44` Evidence API
  runtime files.
- Current remaining strict-import debt: `0` errors across `196` Evidence API
  runtime files.

Verification:

- `make -s artana-evidence-api-type-check-strict-imports`
- `make -s artana-evidence-api-type-check`

### Graph Service Runtime Strict-Import Gate

Additional hardening applied in `alvaro/full-type-hardening`:

- Added typed SQLAlchemy model annotations for table-bound ORM models so mypy can
  see runtime columns without changing database behavior.
- Added `require_table()` for table-bound model declarations and a typed
  `GraphTableOptions` helper.
- Tightened graph service protocols to use real domain models, read-only
  properties, `Sequence` where domain objects expose immutable tuples, and exact
  service method signatures.
- Replaced loose JSON iteration with explicit string-list/object-list narrowing
  in workflow and proposal paths.
- Removed the remaining strict-import `attr-defined`, `arg-type`, `assignment`,
  and `union-attr` failures under the graph strict-import gate.

Measured result:

- `1,545` errors across `74` runtime files.
- Error-code distribution:
  - `attr-defined`: `1,221`
  - `arg-type`: `238`
  - `assignment`: `47`
  - `union-attr`: `27`
- Current remaining strict-import debt: `0` errors across `218` graph service
  runtime files.

Verification:

- `make -s graph-service-type-check-strict-imports`
- `make -s graph-service-type-check`
- `make -s graph-service-lint`
- `make -s type-hardening-baseline`

### Issue #12 Closeout Gate Tightening

Applied in `alvaro/issue-12-type-hardening`:

- Converted the graph default type gate to package-based mypy with import
  following enabled and no broad disabled error-code flags.
- Kept `scripts/export_graph_openapi.py` covered by the graph type gate through
  a separate script mypy command.
- Made `graph-service-type-check-strict-imports` an alias of the default graph
  type gate, matching the Evidence API gate shape.
- Removed stale internal and unused mypy overrides. The only remaining
  `ignore_missing_imports = true` override is for `requests` / `requests.*`.
- Added graph Makefile/pre-commit regression tests so skipped imports and
  broad disabled error-code flags cannot return unnoticed.
- Recorded policy decisions for runtime-only gates, Alembic/test exclusions,
  and `disallow_any_expr = false`.

Escape-hatch inventory at closeout:

- Graph runtime: 1 localized `# type: ignore`, 3 `Any` tokens, 47 `cast(...)`
  calls.
- Evidence API runtime: 4 localized `# type: ignore`, 3 `Any` tokens, 408
  `cast(...)` calls.

Verification results from `2026-04-29 UTC`:

- `make -s graph-service-type-check`: passed; graph package and
  `scripts/export_graph_openapi.py` both reported `0` mypy issues.
- `make -s graph-service-type-check-strict-imports`: passed; alias ran the same
  graph package and OpenAPI exporter mypy checks.
- `make -s artana-evidence-api-type-check`: passed with `0` mypy issues across
  `272` source files.
- `make -s type-hardening-baseline`: passed; Evidence API and graph strict
  baselines both reported `0` errors.
- `venv/bin/pytest tests/unit/test_makefile_type_gate_contract.py -q`: passed
  with `9` regression tests.
- `make -s graph-service-checks`: passed.
- `make -s artana-evidence-api-service-checks`: passed.
- `make -s service-checks`: passed, including coverage at `87.44%` against the
  `86%` gate.
- `make all`: passed, including coverage at `87.44%` against the `86%` gate.
- `git diff --check`: passed.

## Non-Goals

- Do not build external identity in this type-hardening branch.
- Do not build frontend or SDK surfaces here.
- Do not rewrite runtime behavior just to satisfy mypy.
- Do not silence errors with broad `Any`, blanket ignores, or large global
  overrides.

## Definition Of Done

The full type-hardening project is done when:

1. Both services pass mypy without `--follow-imports=skip`.
2. Broad disabled error-code lists are gone from service type gates.
3. The full service gates pass:
   - `make -s artana-evidence-api-service-checks`
   - `make -s graph-service-checks`
4. The PR history shows a measurable burn-down from the initial strict baseline
   to zero blocking strict-import errors.
