# Multi-Source And Automated Workflows

Once the basic document and review flow is comfortable, these workflows help
you cover more ground.

## Evidence Runs

Use `evidence-runs` as the goal-driven front door for iterative research.

Good for:

- giving the harness a research goal and follow-up instructions
- asking the harness to create supported structured source searches
- screening durable saved source-search results for relevance
- creating guarded source handoffs for selected records
- staging selected records as reviewable proposals or review items
- preserving selected, skipped, and deferred reasons for review
- continuing the same research space over time

Endpoints:

- `POST /v2/spaces/{space_id}/evidence-runs`
- `POST /v2/spaces/{space_id}/evidence-runs/{evidence_run_id}/follow-ups`

Current behavior: evidence runs default to `planner_mode: "model"`. When the
model planner is configured, you can submit only a goal/instructions and the
harness will choose a small set of supported source searches, run them, screen
the durable results, create guarded handoffs, and stage review-gated proposals
or review items. You can still provide `source_searches` or `candidate_searches`
directly for manual control. Shadow mode records recommendations without
creating handoffs.
If model planning is not configured, goal-only requests return a clear
unavailable error; explicit source-search requests can still run
deterministically.

Goal-only example:

```json
{
  "goal": "Find evidence linking MED13 variants to congenital heart disease",
  "mode": "guarded"
}
```

Manual deterministic example:

```json
{
  "goal": "Find evidence linking MED13 variants to congenital heart disease",
  "mode": "guarded",
  "planner_mode": "deterministic",
  "source_searches": [
    {
      "source_key": "clinvar",
      "query_payload": {"gene_symbol": "MED13"},
      "max_records": 5
    }
  ]
}
```

Explicit source-search example:

```json
{
  "goal": "Find evidence linking MED13 variants to congenital heart disease",
  "mode": "guarded",
  "source_searches": [
    {
      "source_key": "clinvar",
      "query_payload": {"gene_symbol": "MED13"},
      "max_records": 5
    }
  ]
}
```

PubMed uses a nested query payload:

```json
{
  "goal": "Find papers linking MED13 variants to congenital heart disease",
  "mode": "guarded",
  "source_searches": [
    {
      "source_key": "pubmed",
      "query_payload": {
        "parameters": {
          "search_term": "MED13 congenital heart disease"
        }
      },
      "max_records": 5
    }
  ]
}
```

MARRVEL uses gene or variant query fields:

```json
{
  "goal": "Find variant-context evidence for MED13",
  "mode": "guarded",
  "source_searches": [
    {
      "source_key": "marrvel",
      "query_payload": {
        "gene_symbol": "MED13",
        "panels": ["omim", "clinvar"]
      },
      "max_records": 5
    }
  ]
}
```

Evidence runs are for research triage and review preparation. They are not
clinical advice, automatic regulatory evidence, proof of causality, or a formal
systematic review unless your workflow also captures protocol fields, search
accounting, exclusions, and human reviewer decisions.

## Research Plan

Use `research-plan` when you already know the research question and source mix.

Good for:

- starting a new topic with several sources
- using PubMed plus structured sources such as MARRVEL or ClinVar
- producing an initial research state and source summary

Endpoint:

- `POST /v2/spaces/{space_id}/research-plan`

## Topic Setup

Use topic setup when you want a first map of a topic.

Good for:

- getting a head start from seed entities
- staging initial proposed updates for review
- creating a first research brief

Endpoint:

- `POST /v2/spaces/{space_id}/workflows/topic-setup/tasks`

## Continuous Learning

Use continuous learning when you want the system to refresh a space over time.

Good for:

- checking for new evidence
- creating a limited number of new proposals
- tracking next questions

Endpoint:

- `POST /v2/spaces/{space_id}/workflows/continuous-review/tasks`

## Schedules

Schedules save recurring workflow configuration.

Useful endpoints:

- `GET /v2/spaces/{space_id}/schedules`
- `POST /v2/spaces/{space_id}/schedules`
- `PATCH /v2/spaces/{space_id}/schedules/{schedule_id}`
- `POST /v2/spaces/{space_id}/schedules/{schedule_id}/pause`
- `POST /v2/spaces/{space_id}/schedules/{schedule_id}/resume`
- `POST /v2/spaces/{space_id}/schedules/{schedule_id}/start-now`

Use schedules only after you are confident the workflow is producing useful
reviewable output.

## Evidence Curation

Evidence curation is a more governed path for claim-writing workflows.

Endpoint:

- `POST /v2/spaces/{space_id}/workflows/evidence-curation/tasks`

Good for:

- high-impact claims
- workflows where explicit review and approval checkpoints matter

## Full Research

Full research composes larger workflows, such as topic setup, briefing chat, and
curation.

Useful endpoints:

- `POST /v2/spaces/{space_id}/workflows/full-research/tasks`
- `GET /v2/spaces/{space_id}/workflows/full-research/tasks`
- `GET /v2/spaces/{space_id}/workflows/full-research/tasks/{task_id}`
- `GET /v2/spaces/{space_id}/workflows/full-research/dashboard`

Full research is powerful, but it is not the best first workflow. Learn documents,
review items, the evidence map, and evidence search first.

## Autopilot

Autopilot is the broadest guarded AI workflow surface.

Endpoint:

- `POST /v2/spaces/{space_id}/workflows/autopilot/tasks`

Use it when you need a broad, guarded AI workflow and you understand the review
and transparency surfaces.
