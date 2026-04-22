# Space-Scoped Discovery: Admin Training Guide

This guide summarizes the operational steps required to launch and maintain the new space-scoped discovery experience. Share it with MED13 system administrators and research space leads before enabling the feature flag in production.

## 1. Prerequisites

- Database migrations applied through `alembic upgrade head`.
- CLI access to the application container/VM with the project virtualenv activated.
- Backups (logical or snapshot) for the database instance you are about to mutate.
- Feature flag or configuration toggle to expose `/spaces/{spaceId}/discovery` in the UI (kept **off** until Section 4 is complete).

## 2. Run the Data Migration Script

1. Activate the project’s virtual environment.
2. Execute the migration helper:

```bash
./scripts/migrate_to_space_scoped_discovery.py \
  --available-source clinvar \
  --log-level INFO
```

3. Use `--dry-run` first in any environment you do not want to mutate immediately.
4. The script will:
   - Seed the deterministic MED13 system user and default research space if they do not exist.
   - Reassign any legacy discovery sessions without a `research_space_id`.
   - Generate per-space activation rules for every active catalog entry (defaulting to `blocked` except for the sources provided via `--available-source`).
5. Capture the log summary for change management records.

## 3. Verify Source Permissions in the UI

1. Sign in as a system administrator and open `/system-settings`.
2. Switch to the **Source Permissions** tab (powered by `SpaceSourcePermissionsManager`).
3. Confirm that:
   - Every research space is listed across the table header.
   - All sources show one of the `blocked / visible / available` badges.
   - The defaults applied by the script match expectations (e.g., only ClinVar is `available` globally).
4. Adjust specific sources/spaces as needed to onboard teams gradually.

## 4. Enable Space-Scoped Discovery for Researchers

Once permissions look correct:

1. Flip the feature flag (or configuration setting) that surfaces the “Discover Sources” entry inside each research space.
2. Ask a space owner to validate `/spaces/{spaceId}/discovery` by:
   - Running a catalog search.
   - Creating a discovery session.
   - Testing a source and verifying audit logs.
3. Update onboarding materials to reference the new flow (catalog exploration now happens inside the research space rather than the global `/data-discovery` route).

## 5. Operational Runbook

| Action | Responsible Team | Steps |
|-------|------------------|-------|
| Add a new space | Platform Ops | Create space → run migration script (fills default permissions) → verify in UI |
| Allow a new source globally | Platform Ops | Add source via System Settings → rerun migration (to seed defaults) → adjust specific spaces |
| Temporary access for a space | Space Owner + Admin | Admin toggles permission to `visible/available` → owner works in `/spaces/{id}/discovery` → admin reverts when done |

## 6. Rollback Procedure

If you must revert to the legacy global model:

```bash
./scripts/rollback_space_scoped_discovery.py \
  --fallback-space-id 560e9e0b-13bd-4337-a55d-2d3f650e451f
```

- The script removes every research-space scoped rule and reassigns all sessions to the fallback space (MED13 core by default).
- Use `--dry-run` to preview the counts before committing.
- After rollback, disable the feature flag and communicate to researchers that discovery is temporarily global again.

---

**Tip:** Keep both scripts under version control and run them as part of your deployment pipeline so lower environments always mirror production changes. Document every execution (timestamp, operator, options used) in your compliance tracker.
