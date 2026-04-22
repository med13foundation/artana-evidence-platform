# Run Transparency

This page explains the transparency features that were added to
`artana_evidence_api`.

Use this page when you want to answer:

- what tools a run was allowed to use
- what tools it actually executed
- whether a human review later changed the outcome

## What Was Added

Every run now exposes two dedicated transparency endpoints:

- `GET /v1/spaces/{space_id}/runs/{run_id}/capabilities`
- `GET /v1/spaces/{space_id}/runs/{run_id}/policy-decisions`

Every run also persists two matching artifacts:

- `run_capabilities`
- `policy_decisions`

These are additive features. They do not change the existing workflow routes,
artifacts, supervisor responses, or chat responses.

## The Simple Mental Model

Think about transparency in three layers:

1. `capabilities`
   This is the frozen snapshot of what the run was allowed to use when it
   started.
2. `events`
   This is the raw lifecycle stream for the run.
3. `policy-decisions`
   This is the cleaned-up ordered record of what the run actually tried to do,
   including later manual review actions when they can be tied back to the run.

If you only remember one rule:

- use `capabilities` to answer "what could this run do?"
- use `policy-decisions` to answer "what did this run do?"

## When To Use Each Endpoint

| Endpoint | Use it when you want to know | Typical reader |
| --- | --- | --- |
| `/runs/{run_id}/capabilities` | what tools were visible, blocked, or filtered | developers, operators, UI clients |
| `/runs/{run_id}/policy-decisions` | what the run executed and how those decisions ended | developers, reviewers, auditors |
| `/runs/{run_id}/events` | the raw lifecycle trace | debugging and low-level inspection |

## `capabilities`: What The Run Could Use

This endpoint returns the run's frozen tool snapshot.

It is created at run start and does not change later.

Typical fields include:

- `run_id`
- `space_id`
- `harness_id`
- `policy_profile`
- `tool_groups`
- `visible_tools`
- `filtered_tools`
- `artifact_key`
- `created_at`

What it tells you:

- which tools the harness was allowed to use
- which tools were filtered out
- why a tool was filtered
- the policy profile that shaped the run

Example:

```bash
export HARNESS_URL="http://localhost:8091"
export TOKEN="your-jwt-token"
export SPACE_ID="11111111-1111-1111-1111-111111111111"
export RUN_ID="44444444-4444-4444-4444-444444444444"

curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/capabilities" \
  -H "Authorization: Bearer $TOKEN"
```

What to look for first:

- `visible_tools`
- `filtered_tools`
- `policy_profile`
- `artifact_key`

## `policy-decisions`: What The Run Actually Did

This endpoint returns the ordered decision log for the run.

Unlike `capabilities`, this record grows as the run executes and as later
manual review actions are attached to the run.

Typical fields include:

- `run_id`
- `space_id`
- `harness_id`
- `artifact_key`
- `summary`
- `declared_policy`
- `decisions`
- `updated_at`

Each decision record is normalized so the shape stays stable across workflows.

Important fields on each decision:

- `decision_source`
- `tool_name`
- `decision`
- `reason`
- `status`
- `event_id`
- `approval_id`
- `artifact_key`
- `started_at`
- `completed_at`

Example:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/policy-decisions" \
  -H "Authorization: Bearer $TOKEN"
```

## What `decision_source` Means

`policy-decisions` can contain more than one kind of decision.

Current values:

- `tool`
  The harness executed a shared graph or literature tool through the Artana
  tool path.
- `manual_review`
  A user later promoted or rejected something that can be traced back to this
  run.

This means one run can show both:

- what the harness executed automatically
- what a human later approved, promoted, or rejected

## Common Questions

### Why do I sometimes see tools in `capabilities` but not in `policy-decisions`?

Because the run was allowed to use those tools, but it did not need them.

### Why can `policy-decisions` be empty?

This usually means one of these things:

- the run has not started yet
- the harness did not call a shared tool
- the run finished without any attributable tool or manual-review decisions

### Why do I see a later manual-review record after the run already completed?

Because transparency is about the full decision story for that run, not just
the synchronous execution window. If a chat-derived graph candidate is later
promoted or rejected, that decision can still be attached to the original run.

### How is this different from `events`?

`events` is the raw lifecycle log.

`policy-decisions` is the structured answer to:

- what was attempted
- what decision was taken
- what was the outcome

Use `events` for low-level debugging.
Use `policy-decisions` for product and audit views.

## Typical Workflow

This is the recommended order when you are inspecting a run:

1. Start or fetch a run.
2. Read `capabilities` once to see the allowed tool surface.
3. Read `policy-decisions` to see what the run actually executed.
4. Read `events` only if you need the lower-level trace.
5. Read `artifacts` if you want the actual content outputs.

In practice, most users should use this sequence:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/capabilities" \
  -H "Authorization: Bearer $TOKEN"

curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/policy-decisions" \
  -H "Authorization: Bearer $TOKEN"

curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/artifacts" \
  -H "Authorization: Bearer $TOKEN"
```

## Example: Verified Chat Run

A good first example is a verified chat run.

Typical inspection flow:

1. send a chat message
2. record the returned `run.id`
3. open `capabilities`
4. open `policy-decisions`
5. if the chat produced graph-write candidates, review one
6. open `policy-decisions` again and confirm the manual review entry is there

That gives you a full trace from:

- declared capability
- tool execution
- final human review

## Example: Approval-Gated Curation Run

For curation runs, `policy-decisions` is especially useful because it helps
explain pauses and resumes.

Typical pattern:

- the run executes preflight tools
- the run pauses for approval
- approvals are resolved
- the run resumes
- final actions are recorded

This is much easier to follow through `policy-decisions` than by reading raw
events alone.

## Artifact Keys To Remember

The most important transparency artifacts are:

- `run_capabilities`
- `policy_decisions`

You can fetch them directly through the artifact routes if you already know the
key:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/artifacts/run_capabilities" \
  -H "Authorization: Bearer $TOKEN"

curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/artifacts/policy_decisions" \
  -H "Authorization: Bearer $TOKEN"
```

Most clients should still prefer the dedicated endpoints because they are the
clearest public API.

## Best Practices

- Always inspect `capabilities` before assuming a missing tool call is a bug.
- Use `policy-decisions` as the default audit view for runs.
- Use `events` only when you need lower-level lifecycle detail.
- For UI pages, show `capabilities` as a snapshot and `policy-decisions` as a
  timeline.
- For support/debugging, compare the four views in this order:
  `progress`, `capabilities`, `policy-decisions`, `events`.

## Related Docs

- [Getting Started](./getting-started.md)
- [Core Concepts](./concepts.md)
- [API Reference](./api-reference.md)
- [Example Use Cases](./use-cases.md)
