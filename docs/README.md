# Docs Index

Status date: April 30, 2026.

This directory describes the current extracted backend repo. The source of
truth in this checkout is two Python services:

- `services/artana_evidence_api`: evidence workflows, identity/API keys,
  documents, durable direct source-search capture and handoff, proposals,
  review items, research-plan orchestration, chat, and AI tasks.
- `services/artana_evidence_db`: governed graph, dictionary, claims,
  relations, provenance, graph views, workflows, and graph admin sync.

Not present in this checkout: a frontend app, the old top-level `src/` package,
or `packages/artana_api`.

## Start Here

- [Current System](./architecture/current-system.md)
- [User Guide](./user-guide/README.md)
- [Remaining Work](./remaining_work_priorities.md)
- [Module Packaging Plan](./architecture/module-packaging-plan.md)
- [Source Plugin Developer Guide](./source_plugins.md)
- [V2 API Migration Plan](./v2_api_migration_plan.md)

## Architecture

- [Source Boundaries](./architecture/source-boundaries.md)
- [Module Packaging Plan](./architecture/module-packaging-plan.md)
- [Local Identity Boundary](./architecture/local-identity-boundary.md)
- [Pending Boundary Issues](./architecture/pending-boundary-issues.md)
- [Research Plan Architecture](./research_init_architecture.md)
- [Full AI Orchestrator](./full_AI_orchestrator.md)
- [Artana Kernel Integration Notes](./artana-kernel/docs/README.md)

## Migration And Release

- [Graph Release Policy](./graph/reference/release-policy.md)
- [Graph Release Checklist](./graph/reference/release-checklist.md)
- [Graph Upgrade Guide](./graph/reference/upgrade-guide.md)
- [GitHub Projects Playbook](./github_projects_playbook.md)

## Archive

- [Archived Planning Docs](./archive/README.md)
