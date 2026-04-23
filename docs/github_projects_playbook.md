# GitHub Projects Playbook

Status date: April 23, 2026.

This playbook is for the extracted backend repo:

- Repository: `med13foundation/artana-evidence-platform`
- Default branch: `main`
- Current service branches should use the `alvaro/` prefix unless a maintainer
  asks for something else.

The old monorepo project filters no longer apply here.

## Recommended Labels

Use labels to keep the queue readable:

- priority: `triage:P0`, `triage:P1`, `triage:P2`, `triage:P3`
- topic: `architecture`, `documentation`, `testing`, `security`,
  `observability`, `graph-service`, `evidence-api`, `identity`, `deployment`
- state: `triage:blocked`, `needs-review`, `ready`

## Useful Views

Create project views around the extracted repo:

- Inbox: `repo:med13foundation/artana-evidence-platform is:open -status:Done`
- Urgent: `repo:med13foundation/artana-evidence-platform label:triage:P0,triage:P1 is:open`
- Evidence API: `repo:med13foundation/artana-evidence-platform label:evidence-api is:open`
- Graph service: `repo:med13foundation/artana-evidence-platform label:graph-service is:open`
- Architecture debt: `repo:med13foundation/artana-evidence-platform label:architecture is:open`
- Deployment: `repo:med13foundation/artana-evidence-platform label:deployment is:open`

## Pull Request Expectations

Before opening or merging a backend PR, record:

- what service changed;
- which contract artifacts changed, if any;
- which checks ran;
- whether the change affects local tester onboarding, graph contracts, or
  deploy-time environment variables.

For service code changes, prefer these checks:

```bash
make graph-service-checks
make artana-evidence-api-service-checks
```

For docs-only changes, at least run a docs/path sanity pass and the release-doc
contract if graph release docs changed:

```bash
make graph-phase6-release-check
```

## Triage Report

The repo includes a generic issue triage helper. It requires `gh` auth.

```bash
python3 scripts/project_triage_report.py \
  --repo med13foundation/artana-evidence-platform
```

The script still uses a few historical topic label names internally, but the
`--repo` argument is the source of truth for which repository it inspects.
