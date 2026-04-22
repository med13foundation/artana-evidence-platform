# Graph History Docs

This folder contains historical and migration-focused documents for the
standalone graph service.

Use this folder when you need to understand:

- how the graph service was extracted from the platform app
- which migration phases were completed
- why some service-boundary decisions were made
- the historical progress log for the extraction work

For day-to-day usage, start at [../README.md](../README.md) instead.

Current note:

- the migration tracked in `migration-phase2*.md` is now implemented and
  validated in the repo
- this folder should be treated as historical rationale and closure context,
  not as the primary current-state reference

## Files

- [migration-phase2-checklist.md](migration-phase2-checklist.md)
  Progress checklist for executing the phase-2 implementation plan.
- [migration-phase2.md](migration-phase2.md)
  Phase-2 design plan for productization, domain-pack separation, auth and
  tenancy boundary hardening, and query/read-model evolution.
- [service-migration-plan.md](service-migration-plan.md)
  The full extraction plan, phase breakdown, milestone notes, and progress log.
