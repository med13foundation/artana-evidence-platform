# Module Packaging Plan

Status date: April 30, 2026.

## Purpose

The monolith cleanup removed oversized files and made the architecture-size gate
enforceable. The next cleanup is different: reduce flat module sprawl by moving
related modules into small packages that match the service responsibilities.

In simple terms:

- The code is no longer made of giant files.
- The next problem is that many small files now sit side by side at the service
  root.
- We should group those files by product/runtime concern so a developer can
  find the right area quickly.

## Current Live State

Current code-backed facts from this checkout:

- The per-file production budget is `1200` physical lines in
  `scripts/validate_architecture_size.py`.
- `architecture_overrides.json` has no active file-size exceptions.
- No in-scope production Python file exceeds the size budget.
- `services/artana_evidence_api` has 237 top-level Python modules.
- `services/artana_evidence_db` has 184 top-level Python modules.
- The largest remaining module families are:
  - Evidence API: `full_ai_orchestrator_*`, `research_init_*`,
    `sqlalchemy_*`, `phase*_compare*`, source handoff, and routers.
  - Graph service: `ai_full_mode_*`, `dictionary_*`, `graph_domain_*`,
    graph workflow, and kernel dictionary models.

This is acceptable for the monolith cleanup branch, but it is not the final
shape we want.

## Goals

- Keep the two service boundaries clear:
  - Evidence API owns user workflow, orchestration, documents, review, and AI
    runtime behavior.
  - Graph service owns graph persistence, dictionary governance, graph
    validation, provenance, and graph API contracts.
- Move related modules into packages that explain ownership.
- Keep public compatibility imports during the transition.
- Avoid large "utils" buckets unless the helpers are truly shared and small.
- Keep every moved package under the existing architecture-size gate.
- Add tests or import checks that prove old compatibility paths still work.
- Add a package-structure guard so this does not turn into package-level
  monoliths or a new flat pile inside subdirectories.

## Non-Goals

- Do not change endpoint behavior.
- Do not change OpenAPI contracts except for intentional, reviewed contract
  changes.
- Do not remove public compatibility import paths in the same pass that moves
  implementation modules.
- Do not add a frontend or UI package.
- Do not lower the 1200-line cap as part of this packaging pass.

## Target Shape

### Evidence API

```text
services/artana_evidence_api/
  full_ai_orchestrator/
    runtime.py
    execute.py
    queue.py
    response.py
    action_registry.py
    workspace_support.py
    artifacts.py
    progress/
    guarded/
    shadow/
    shadow_planner/

  research_init/
    runtime.py
    completion.py
    guarded.py
    documents/
    sources/
    pubmed.py
    mondo.py

  stores/
    sqlalchemy/
      review_documents.py
      schedules_spaces.py
      state_chat.py
    artana/

  phase_compare/
    phase1.py
    phase2.py
    progress.py
    summaries.py
    telemetry.py

  source_handoff/
    runtime.py
    documents.py
```

Root modules such as `full_ai_orchestrator_runtime.py` and
`research_init_runtime.py` should remain as thin compatibility facades until all
internal imports are migrated.

### Graph Service

```text
services/artana_evidence_db/
  ai_full_mode/
    service.py
    concepts.py
    graph_changes.py
    decisions.py
    repository.py
    models.py

  dictionary/
    management.py
    proposals.py
    repository.py
    search.py
    router_support.py
    models.py
    transforms.py

  graph_domain/
    config.py
    constraints.py
    qualifiers.py
    relation_types.py
    synonyms.py
    types.py

  workflows/
    service.py
    planning.py
```

Root modules should remain as compatibility facades first, then be removed only
after all repo-local imports and tests prove the package paths are canonical.

### Scripts

```text
scripts/
  full_ai_real_space_canary/
    runner.py
    reporting.py
    utils.py

  live_evidence_session_audit/
    runner.py
    support.py

  phase1_guarded_eval/
    runner.py
    common.py
    render.py
    report.py
    review.py
```

The current script entrypoints should remain executable by file path and by
`python -m scripts.<entrypoint>` during the transition.

## Compatibility Facade Contract

Root compatibility modules are allowed during the migration, but they must be
boring and explicit.

Rules:

- Use explicit imports and explicit `__all__`; do not use star imports.
- Keep the facade docstring clear: it exists for compatibility only.
- Do not put new implementation logic in a facade.
- New repo-local code should import the canonical package path, not the old root
  path.
- For plain constants, dataclasses, Pydantic models, and enum-like values,
  explicit re-export is enough.
- For functions or objects that are monkeypatched through the old path, add a
  focused test proving `mock.patch("old_module.name")` still affects the
  runtime path, or migrate the test and remove the old monkeypatch seam.
- If preserving old-path monkeypatch behavior requires dynamic lookup, keep that
  lookup small and documented.

Compatibility tests should cover:

- old import path still imports;
- canonical package path still imports;
- old and canonical symbols are intentionally identical, or intentionally
  delegated;
- representative old-path monkeypatches still affect runtime behavior when we
  promise to preserve that behavior.

Place repository-level compatibility and packaging tests under `tests/unit`.
Keep service-specific behavior tests under the relevant service test tree.

## Package Structure Guard

The existing guard prevents oversized files. The packaging cleanup needs a
second guard that prevents new sprawl.

Add a structure check with concrete rules:

- Flag service-root module families when a shared prefix has more than 6 root
  modules, unless listed as an explicit compatibility exception.
- Flag package directories with more than 15 direct child Python modules unless
  they have a documented subpackage split plan.
- Flag `utils`, `support`, or `common` modules over 400 lines unless they are
  split by responsibility.
- Report root module counts for each service.
- Wire the check into `service-checks` or the normal service-specific check
  targets.
- Start with a repo-local AST import-graph checker so the rule can be reviewed
  and tuned with the existing boundary checks before adding a third-party
  import-lint dependency.

Target root-module counts by the end of Phase 5:

- `services/artana_evidence_api`: at most 190 top-level Python modules.
- `services/artana_evidence_db`: at most 155 top-level Python modules.

These are not final ideal numbers. They are the first measurable ratchet after
the monolith cleanup.

## Dependency Direction

Packaging should reduce coupling, not hide it one directory deeper.

Evidence API dependency direction:

```text
routers -> application/runtime packages -> stores/clients/types
full_ai_orchestrator -> research_init/source plugins/graph client/types
research_init -> source plugins/stores/graph client/types
stores -> models/types only
```

Graph service dependency direction:

```text
routers -> domain services -> repositories/models/runtime helpers
dictionary -> dictionary models/repository/governance helpers
ai_full_mode -> workflow/dictionary/repository contracts
graph_domain -> pure config/rules/types
```

The boundary checks should be extended when needed so low-level packages do not
import high-level routers or orchestrators.

## Migration Strategy

### Phase 0: Inventory And Rules

- [x] Generate an import map for the top-level module families.
- [x] Identify current facade modules and private test seams.
- [x] Record which paths are public compatibility paths.
- [x] Decide package names before moving files.
- [x] Add a small structure check that fails when a new large module family is
      added at the service root instead of inside a package.
- [x] Add a repo-local AST import-cycle check for the package families being
      moved.
- [x] Define the compatibility-facade list in a repo-local control file or test
      fixture so Phase 5 has something objective to clean up.
- [x] Enumerate every preserved old-path monkeypatch seam; each seam must have
      a compatibility test or an explicit removal/waiver note.

Acceptance criteria:

- [x] We know which imports must remain compatible.
- [x] We know which modules can move without public impact.
- [x] The new structure rule is wired into `service-checks` or a normal
      service check target.
- [x] The new structure rule reports current root module counts.
- [x] Compatibility facade behavior is documented and testable.

### Phase 1: Script Packages

Start with scripts because they are easier to verify and already have helper
modules.

- [x] Move full-AI canary helpers under `scripts/full_ai_real_space_canary/`.
- [x] Move live evidence audit helpers under
      `scripts/live_evidence_session_audit/`.
- [x] Move Phase 1 guarded-eval helpers under `scripts/phase1_guarded_eval/`.
- [x] Keep existing script files as entrypoint facades.
- [x] Verify each script works with both file-path execution and
      `python -m scripts.<entrypoint>`.
- [x] Keep `scripts/__init__.py` present so `python -m scripts.<entrypoint>`
      stays reliable.
- [x] Use `git mv` for moves so history remains followable.

Acceptance criteria:

- [x] Existing operator commands still work.
- [x] No bare sibling imports remain in split script helpers.
- [x] Script helper modules are grouped by runnable workflow.
- [x] Script entrypoint compatibility tests or smoke commands are recorded in
      the phase diff.

### Phase 2: Evidence API Full-AI Orchestrator

- [x] Create `services/artana_evidence_api/full_ai_orchestrator/`.
- [x] Move runtime models, constants, artifacts, queue, execution, progress,
      guarded, and response modules into that package.
- [x] Create `full_ai_orchestrator/shadow_planner/` for shadow planner
      workspace, prompts, validation, comparison, fallback, telemetry, and
      decisions.
- [x] Move the shadow-planner implementation modules into
      `full_ai_orchestrator/shadow_planner/`.
- [x] Keep explicit root compatibility facades for the old
      `full_ai_orchestrator_shadow_planner*` module paths.
- [x] Add compatibility tests for the moved shadow-planner facades, including
      the existing old-path monkeypatch seam used by tests.
- [x] Enumerate the preserved shadow-planner old-path monkeypatch seams:
      `has_configured_openai_api_key`, `get_model_registry`, and
      `create_artana_postgres_store`.
- [x] Create `full_ai_orchestrator/progress/` for progress observer
      composition and progress-state persistence.
- [x] Move progress observer implementation modules into
      `full_ai_orchestrator/progress/`.
- [x] Keep explicit root compatibility facades for the old
      `full_ai_orchestrator_progress_*` module paths.
- [x] Add compatibility tests for the moved progress facades and the runtime
      call sites that expose the progress observer.
- [x] Confirm there are no preserved progress old-path monkeypatch seams in
      the current service tests.
- [x] Move runtime constants, result model, artifact helpers, initial-decision
      builder, and queue entrypoint into `full_ai_orchestrator/`.
- [x] Keep explicit root compatibility facades for the old runtime-support and
      queue module paths.
- [x] Preserve the old queue-path `ensure_run_transparency_seed` monkeypatch
      seam while the root queue facade remains.
- [x] Create `full_ai_orchestrator/guarded/` for guarded rollout policy,
      guarded selection, guarded artifact support, and guarded verification.
- [x] Move guarded implementation modules into `full_ai_orchestrator/guarded/`.
- [x] Keep explicit root compatibility facades for the old
      `full_ai_orchestrator_guarded_*` module paths.
- [x] Add compatibility tests for guarded facades and guarded canonical import
      direction.
- [x] Move response serialization and response-support helpers into
      `full_ai_orchestrator/`.
- [x] Keep explicit root compatibility facades for the old
      `full_ai_orchestrator_response*` module paths.
- [x] Create `full_ai_orchestrator/shadow/` for shadow checkpoint orchestration
      and shadow summary helpers.
- [x] Move shadow checkpoint and shadow-support implementation modules into
      `full_ai_orchestrator/shadow/`.
- [x] Keep explicit root compatibility facades for the old
      `full_ai_orchestrator_shadow_checkpoints` and
      `full_ai_orchestrator_shadow_support` module paths.
- [x] Add compatibility tests for shadow facades, internal package-path imports,
      the runtime recommendation monkeypatch seam, and duplicated shadow/guarded
      constants that remain pending a later split.
- [x] Move the full-AI execute entrypoint into `full_ai_orchestrator/execute.py`.
- [x] Keep an explicit root compatibility facade for the old
      `full_ai_orchestrator_execute` module path.
- [x] Preserve the old runtime-path `execute_research_init_run` monkeypatch
      seam while the root runtime facade remains.
- [x] Split `full_ai_orchestrator_common_support.py` into focused
      `full_ai_orchestrator/action_registry.py` and
      `full_ai_orchestrator/workspace_support.py` package modules.
- [x] Turn `full_ai_orchestrator_common_support.py` into a small compatibility
      facade and remove its large-helper exception from the structure guard.
- [x] Add compatibility tests proving the old common-support path re-exports
      the focused canonical modules and package internals no longer import it.
- [ ] Keep root `full_ai_orchestrator_*.py` facades where external or test
      imports still rely on them.
- [ ] Migrate internal imports to package paths.
- [ ] Add compatibility tests for root full-AI facades, including at least one
      test for each old-path monkeypatch seam that Phase 0 says must remain
      compatible.
- [ ] Run contract checks even if the move looks internal, because FastAPI and
      Pydantic can expose import-path drift indirectly.

Acceptance criteria:

- [ ] Full-AI orchestrator imports are package-based internally.
- [ ] Existing public/root import paths still pass compatibility tests.
- [ ] `make artana-evidence-api-contract-check` passes with no unintended
      artifact diff.
- [ ] The import-cycle check passes for the moved package family.
- [ ] `make artana-evidence-api-service-checks` passes.

### Phase 3: Evidence API Research Init, Stores, And Compare

- [ ] Create `research_init/` with subfolders for documents and sources.
- [ ] Move document extraction dependencies/runtime into
      `research_init/documents/`.
- [ ] Move source enrichment/execution modules into `research_init/sources/`.
- [ ] Create `stores/sqlalchemy/` for SQLAlchemy review/document, schedule,
      space, state, and chat stores.
- [ ] Create `phase_compare/` for Phase 1 and Phase 2 compare helpers.
- [ ] Keep root compatibility facades until internal imports are fully moved.
- [ ] Audit Evidence API Alembic `env.py`, model imports, and migration imports
      before moving anything that affects SQLAlchemy metadata.
- [ ] Add compatibility tests for old store and research-init import paths that
      remain documented compatibility paths.

Acceptance criteria:

- [ ] Research-init orchestration is easier to scan by workflow area.
- [ ] Store code is grouped by persistence backend and domain.
- [ ] Compare/reporting code is no longer scattered at the service root.
- [ ] Alembic migrations still run on a fresh ephemeral database.
- [ ] `make artana-evidence-api-contract-check` passes with no unintended
      artifact diff.
- [ ] The import-cycle check passes for the moved package families.
- [ ] Existing research-init, store, and compare tests pass.

### Phase 4: Graph Service Packages

- [ ] Create `ai_full_mode/` and move full-mode service, support, graph change,
      decision connector, repository mixin, and models into it.
- [ ] Create `dictionary/` and move management, proposal, repository, search,
      support, router support, transform, and model modules into it.
- [ ] Create `graph_domain/` and move domain config, constraints, qualifiers,
      relation types, synonyms, and types into it.
- [ ] Create `workflows/` and move graph workflow service/planning into it.
- [ ] Keep root compatibility facades until graph service imports are fully
      migrated.
- [ ] Audit graph Alembic `env.py`, especially eager model imports such as
      persistence and kernel model modules.
- [ ] Add compatibility tests for root graph-service import paths that remain
      documented compatibility paths.

Acceptance criteria:

- [ ] Graph dictionary code is package-local and governance ownership is clear.
- [ ] Graph full-mode code is package-local and no longer spread across root.
- [ ] Graph domain configuration is grouped by rule type.
- [ ] Graph Alembic migrations still run on a fresh ephemeral database.
- [ ] `make graph-service-contract-check` passes with no unintended artifact
      diff.
- [ ] The import-cycle check passes for the moved package families.
- [ ] `make graph-service-checks` passes.

### Phase 5: Compatibility Cleanup

- [ ] List remaining root compatibility facades.
- [ ] Remove only facades that are absent from the compatibility-facade control
      file, have no repo-local import references, and are not referenced by
      documented operator scripts or external integration notes.
- [ ] Keep public API and generated contract behavior unchanged.
- [ ] Update architecture docs once the package paths become canonical.

Acceptance criteria:

- [ ] `services/artana_evidence_api` has at most 190 top-level Python modules.
- [ ] `services/artana_evidence_db` has at most 155 top-level Python modules.
- [ ] Remaining root modules are true service entrypoints, public contracts, or
      stable compatibility shims.
- [ ] No endpoint or generated contract drift appears unless intentionally
      reviewed.

## Checks To Run

Run focused checks after each phase:

```bash
venv/bin/python scripts/validate_architecture_size.py
make artana-evidence-api-lint
make artana-evidence-api-type-check
make artana-evidence-api-boundary-check
make artana-evidence-api-contract-check
make graph-service-lint
make graph-service-type-check
make graph-service-boundary-check
make graph-service-contract-check
```

Run full gates before considering the packaging work complete:

```bash
make service-checks
```

For script moves, also run:

```bash
venv/bin/python scripts/run_full_ai_real_space_canary.py --help
venv/bin/python -m scripts.run_full_ai_real_space_canary --help
venv/bin/python scripts/run_live_evidence_session_audit.py --help
venv/bin/python -m scripts.run_live_evidence_session_audit --help
venv/bin/python scripts/run_phase1_guarded_eval.py --help
venv/bin/python -m scripts.run_phase1_guarded_eval --help
```

## Risks And Mitigations

| Risk | Mitigation |
| --- | --- |
| Import churn breaks private test seams | Follow the compatibility facade contract; add old-path import and monkeypatch tests. |
| Package moves create circular imports | Move one family at a time; run type checks plus an import-cycle check after each family. |
| OpenAPI artifacts drift accidentally | Run contract checks after every phase, not just at the end. |
| Alembic metadata import paths break | Audit `env.py` and migration imports before model/store moves; prove fresh migrations still run. |
| New packages become new hidden monoliths | Keep the 1200-line cap and add a concrete structure/sprawl check. |
| Developers cannot find canonical paths | Update docs and migrate internal imports to package paths. |
| Git history becomes hard to follow | Prefer `git mv` for file moves and keep each package move in a focused commit. |

## Definition Of Done

- [ ] `services/artana_evidence_api` has at most 190 top-level Python modules.
- [ ] `services/artana_evidence_db` has at most 155 top-level Python modules.
- [ ] Main module families live in named packages.
- [ ] Compatibility facades are explicit and tested.
- [ ] Old-path monkeypatch seams are either tested or intentionally removed.
- [ ] Package dependency direction is enforced by boundary/cycle checks.
- [ ] `architecture_overrides.json` remains empty.
- [ ] `scripts/validate_architecture_size.py` passes.
- [ ] `make service-checks` passes.
- [ ] Docs describe the new package layout.
