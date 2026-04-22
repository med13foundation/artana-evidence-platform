# MED13 System Hierarchy Overview

This guide outlines the major areas of the MED13 admin platform and how they relate to one another. Use it to decide where a new workflow or feature should live.

```
┌───────────────────────────┐
│  System Settings          │
│  (/system-settings)       │
│  Global catalog controls  │
└────────────┬──────────────┘
             │
┌────────────▼──────────────┐
│   Global Data Discovery   │
│   (/data-discovery)       │
│   Catalog exploration     │
└────────────┬──────────────┘
             │
┌────────────▼──────────────┐
│  Research Spaces          │
│  (/spaces/{id}/…)         │
│  Tabs: Discover / Sources │
└───┬──────────┬───────────┘
    │          │
    │          │
┌───▼───┐  ┌───▼───┐
│Discover│  │Dashboard│
│(/spaces│  │(/dashboard)
│/{id}/  │  │KPIs & Nav│
│discovery)│ └─────────┘
└────────┘
```

## 1. Global Admin Settings (`/system-settings`)
- **Audience**: Foundation administrators
- **Purpose**: Configure platform-wide defaults (catalog availability, source permissions, template libraries, compliance switches).
- **Notes**:
  - The **Source Permissions** tab now exposes the `SpaceSourcePermissionsManager`, allowing admins to set `blocked/visible/available` for every space/source combination.
  - Changes apply to all research spaces unless overridden via per-space policies.

## 2. Global Data Discovery (`/data-discovery`)
- **Audience**: Curators/researchers exploring the catalog
- **Purpose**: Filter, search, and preview data sources using gene/phenotype criteria from a platform-wide perspective.
- **Notes**:
  - Read-focused workflow. Shows global availability plus a badge indicating whether the currently selected space can see the source.
  - Mutations now happen inside research spaces; this route is ideal for discovery, reporting, or governance spot checks.

## 3. Space-Scoped Discovery (`/spaces/{spaceId}/discovery`)
- **Audience**: Research space members acting on behalf of their workspace
- **Purpose**: Discover, test, and curate sources that have been approved for a specific space.
- **Notes**:
  - Mirrors the global experience but is fully sandboxed—source search results and testing actions are constrained to the space.
  - Uses React Query prefetching plus server-side `HydrationBoundary` to keep discovery fast even with per-space filters.
  - All session mutations (create/update/test/delete) now flow through this route, ensuring auditability.

## 4. Research Space Management (`/spaces/{spaceId}/…`)
- **Audience**: Curators operating within a specific research space
- **Purpose**: Manage the space’s data sources, curation workflows, membership, and settings.
- **Key tabs**:
  - **Discover Sources**: Newly added entry point that routes to `/spaces/{spaceId}/discovery`.
  - **Data Sources**: Configure ingestion schedules, trigger manual runs, inspect ingestion history (new scheduling UI lives here).
  - **Data Curation**: Operate the curation pipeline.
  - **Members**: Invite/remove collaborators.
- **Notes**: All per-space mutations belong here. Scheduling, quality metrics, and telemetry sit under the Data Sources tab.

## 5. System Dashboard (`/dashboard`)
- **Audience**: Admin overview
- **Purpose**: Display KPIs (source counts, ingestion status, system health) and link into the workflows above.
- **Notes**: Read-only metrics; actionable links route to Discovery or Research Space tabs.

## Placement Guidelines
- Use **System Settings** for platform-level levers or compliance requirements.
- Use **Global Data Discovery** for catalog exploration, comparison, and reporting across spaces.
- Use **Space-Scoped Discovery** when the workflow must respect space boundaries (testing, session management, quick source previews).
- Use **Research Space** tabs for anything that configures, runs, or audits a specific space’s data sources.
- Keep the **Dashboard** focused on monitoring and navigation—not direct configuration.
