# GitHub Projects Playbook

This repo now has a stronger GitHub work-management shape:

- structured issue intake lives in `.github/ISSUE_TEMPLATE/`
- new issues and pull requests can be auto-added to a GitHub Project through `.github/workflows/project-intake.yml`
- triage health reporting lives in `.github/workflows/project-triage-health.yml`
- a local report generator lives in `scripts/project_triage_report.py`

The goal is simple: use labels for taxonomy, use the GitHub Project for workflow state, and keep the backlog easy to triage every week.

## Recommended project

Create one owner-level GitHub Project for this repository:

- Name: `Monorepo Delivery`
- Owner: `med13foundation`
- Default repository: `med13foundation/monorepo`

One strong project is better than multiple half-maintained boards. If the team later needs a separate long-horizon roadmap project, keep this one as the delivery and triage source of truth.

Current live project:

- `https://github.com/users/med13foundation/projects/1`

## Fields

Use these project fields.

### Workflow fields

- `Status` (single select): `Inbox`, `Ready`, `In progress`, `In review`, `Blocked`, `Done`
- `Priority` (single select): `P0`, `P1`, `P2`, `P3`
- `Area` (single select): `Research Inbox`, `Evidence API`, `Evidence DB`, `Extraction`, `Graph`, `Research Init`, `Data Sources`, `Agents`, `Auth/Security`, `Docs`, `Infrastructure`, `Cross-cutting`
- `Effort` (single select): `XS`, `S`, `M`, `L`, `XL`
- `Next action` (text)
- `Last reviewed` (date)

### Planning fields

- `Target iteration` (iteration)
- `Target date` (date)

### Built-in fields worth enabling

- `Assignees`
- `Labels`
- `Repository`
- `Parent issue`
- `Sub-issue progress`

## Views

Create these saved views.

### 1. Inbox

- Layout: table
- Filter: `repo:med13foundation/monorepo status:Inbox`
- Sort: `updated`
- Purpose: new issues and PRs that need first-pass triage

### 2. Unowned urgent work

- Layout: table
- Filter: `repo:med13foundation/monorepo priority:P0,P1 no:assignee -status:Done`
- Sort: `priority`, then `updated`
- Purpose: show anything urgent without an explicit owner

### 3. Active delivery

- Layout: board
- Group by: `Status`
- Filter: `repo:med13foundation/monorepo -status:Done`
- Purpose: day-to-day execution view

### 4. Blocked

- Layout: table
- Filter: `repo:med13foundation/monorepo status:Blocked`
- Purpose: blocked queue that needs unblock decisions, not silent waiting

### 5. Evidence API review

- Layout: table
- Filter: `repo:med13foundation/monorepo label:"evidence-api-review" -status:Done`
- Purpose: keep the large review backlog visible without drowning the rest of the project

### 6. Security

- Layout: table
- Filter: `repo:med13foundation/monorepo label:security -status:Done`
- Purpose: isolate security-sensitive work for prioritization

### 7. This iteration

- Layout: board or table
- Filter: `repo:med13foundation/monorepo -status:Done`
- Slice by: `Target iteration`
- Purpose: weekly planning and execution

### 8. Roadmap

- Layout: roadmap
- Group by: `Area`
- Use: `Target date` or `Target iteration`
- Purpose: high-level sequencing for epics and major initiatives

## Labels vs project state

Keep this boundary clean.

- Labels are for taxonomy and durable meaning.
- Project fields are for workflow state and planning.

Use labels for things like:

- `bug`
- `enhancement`
- `security`
- `performance`
- `testing`
- `architecture`
- `observability`
- `documentation`
- `evidence-api-review`

Use project fields instead of labels for:

- current status
- current queue
- blocked vs in progress
- effort
- next action

The existing `triage:P0` to `triage:P3` labels can stay for now because they are already used heavily in the repo. Over time, the project `Priority` field should become the cleaner planning surface, with labels retained mainly for backward compatibility and issue-list search.

## Built-in project automation

Enable these built-in GitHub Project workflows in the project UI.

- When an item is added to the project, set `Status` to `Inbox`
- When an issue or pull request is closed, set `Status` to `Done`
- When a pull request is merged, set `Status` to `Done`
- Auto-archive `Done` items after 14 days

That gives the project a default state machine without forcing everything through custom Actions logic.

## Repo automation

This repo now includes two GitHub Actions workflows for project management.

### Project intake

File: `.github/workflows/project-intake.yml`

What it does:

- listens for newly opened, reopened, transferred, or labeled issues
- listens for newly opened, reopened, or labeled pull requests
- adds the item to the configured GitHub Project using the official `actions/add-to-project` action

Required configuration:

- repository variable: `GH_PROJECT_URL`
- repository secret: `PROJECT_AUTOMATION_TOKEN`

Recommended `GH_PROJECT_URL` format:

- `https://github.com/orgs/<owner>/projects/<number>`
- or `https://github.com/users/<owner>/projects/<number>`

`PROJECT_AUTOMATION_TOKEN` should be either:

- a fine-grained personal access token with organization `Projects` read/write plus repo issue and pull request read access
- or a GitHub App token with equivalent project access

### Triage health report

File: `.github/workflows/project-triage-health.yml`

What it does:

- runs on weekdays at 15:00 UTC and on manual dispatch
- generates a markdown report of intake gaps, urgent unassigned work, blocked items, and stale P0/P1 issues
- writes the report to the workflow summary
- can optionally publish the latest report into a tracking issue

Optional configuration:

- repository variable: `TRIAGE_REPORT_ISSUE_NUMBER`

If `TRIAGE_REPORT_ISSUE_NUMBER` is set, the workflow will upsert a bot comment on that issue and keep the latest report in one stable place.

## Weekly operating cadence

Use a lightweight cadence.

### Daily or near-daily

- empty the `Inbox` view
- label and prioritize every new item
- assign owners to all `P0` and `P1` items

### Weekly planning

- review `Unowned urgent work`
- review `Blocked`
- review `Evidence API review`
- pull the next slice into `In progress`
- update `Last reviewed` on the items that were actively triaged

### Weekly status update

- post a project status update in the GitHub Project with `On track`, `At risk`, or `Off track`
- summarize wins, current blockers, and the next 1 to 3 focus areas

## Triage rules

Use these rules consistently.

### Priority

- `P0`: urgent correctness, security, or access problem that should be addressed first
- `P1`: high-priority functional gap or major regression
- `P2`: important follow-up or medium-priority improvement
- `P3`: low-priority cleanup, backlog, or longer-horizon work

### Status

- `Inbox`: not yet triaged
- `Ready`: clearly scoped and ready to be picked up
- `In progress`: someone is actively working it
- `In review`: work exists and needs review or verification
- `Blocked`: cannot move without an external decision or prerequisite
- `Done`: merged, closed, or intentionally completed

### Ownership

- every `P0` and `P1` should have an owner the same day it is triaged
- every `Blocked` item should have a `Next action`
- epics should use parent issue plus sub-issues instead of giant unchecked bodies

## Local usage

You can generate the same health snapshot locally with:

```bash
python3 scripts/project_triage_report.py --repo med13foundation/monorepo
```

That is useful before planning sessions or while cleaning up backlog drift.

## Suggested rollout order

1. Create the GitHub Project in the org.
2. Add the fields and views above.
3. Set `GH_PROJECT_URL`.
4. Set `PROJECT_AUTOMATION_TOKEN`.
5. Optionally create a tracking issue and set `TRIAGE_REPORT_ISSUE_NUMBER`.
6. Run `Project Triage Health` manually once to confirm the workflow and report output.
7. Start using the issue forms as the only new issue entry path.
