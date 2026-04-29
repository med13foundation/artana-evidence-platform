# Example Use Cases

These examples are written for new users.

Assume:

```bash
export HARNESS_URL="http://localhost:8091"
export TOKEN="your-jwt-token"
export SPACE_ID="11111111-1111-1111-1111-111111111111"
export SEED_ENTITY_ID="22222222-2222-2222-2222-222222222222"
```

## Which Use Case Should I Start With?

Start with:

- Use Case 1 if you want to review one PDF or text note
- Use Case 2 if you want to ask a question with one tracked document
- Use Case 3 if you want direct PubMed search
- Use Case 4 if you want a large multi-step bootstrap
- Use Case 5 if you want continuous refreshes
- Use Case 6 if you want ranked mechanism candidates
- Use Case 7 if you want approval-driven claim curation
- Use Case 8 if you want the full supervisor flow
- Use Case 9 if you want a supervisor dashboard
- Use Case 10 if you want transparency and audit inspection

## Use Case 1: Review One Document

Goal:

- upload or submit one document
- extract possible facts
- review those facts through generic proposals

Submit one text note:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/documents/text" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "MED13 evidence note",
    "text": "MED13 associates with cardiomyopathy.",
    "metadata": {}
  }'
```

Or upload one PDF:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/documents/pdf" \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@./med13.pdf" \
  -F "title=MED13 paper"
```

Run extraction:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/documents/<document_id>/extraction" \
  -H "Authorization: Bearer $TOKEN" \
  -X POST
```

List the staged review queue for that document:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/review-items?document_id=<document_id>" \
  -H "Authorization: Bearer $TOKEN"
```

Promote one staged queue item:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/review-items/<item_id>/decision" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "promote",
    "reason": "Approved after document review",
    "metadata": {}
  }'
```

Reject one instead:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/review-items/<item_id>/decision" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "reject",
    "reason": "Keep this out of the graph",
    "metadata": {}
  }'
```

What to look for:

- the uploaded or submitted document has a stable `document_id`
- extraction returns a `proposal_count`
- queue items include the originating `document_id` and `task_id`

## Use Case 2: Ask A Grounded Question With One Document

Goal:

- ask a question using the graph plus one tracked document
- inspect verification and evidence
- stage proposals from chat if the answer is verified

Create a chat session:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/chat-sessions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "MED13 briefing chat"
  }'
```

Send a message:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/chat-sessions/<session_id>/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What does this document suggest about MED13 and cardiomyopathy?",
    "document_ids": ["<document_id>"],
    "max_depth": 2,
    "top_k": 10,
    "include_evidence_chains": true,
    "refresh_pubmed_if_needed": true
  }'
```

Read the result:

- `result.answer`
- `result.verification.status`
- `result.evidence`
- `assistant_message.metadata`
- `result.fresh_literature`

The default review path is to stage generic proposals:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/chat-sessions/<session_id>/suggested-updates" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidates": null
  }'
```

Then review those staged items through `/review-items/<item_id>/decision`.

Inline candidate review still exists, but generic proposal staging plus the
review queue is the easier default to explain and operate.

Inspect the transparency snapshot for the chat run:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/capabilities" \
  -H "Authorization: Bearer $TOKEN"
```

This tells you:

- which tools were visible to the run
- which tools were filtered out

Then inspect the ordered decision log:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/decisions" \
  -H "Authorization: Bearer $TOKEN"
```

This tells you:

- what tools the run actually executed
- whether the run paused for approval
- whether a later human review promoted or rejected something tied to this run

For a fuller explanation of what those two endpoints mean, read
[Run Transparency](./transparency.md).

What to look for:

- `result.answer` for the readable answer
- `result.verification` for the confidence and grounded status
- `result.fresh_literature` when PubMed refresh is enabled
- staged generic proposals if you want reviewed graph writes

## Use Case 3: Search PubMed Directly

Goal:

- run a saved literature search
- inspect preview results
- reuse that search result later

Start the search:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/sources/pubmed/searches" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "gene_symbol": "MED13",
      "search_term": "MED13 cardiomyopathy",
      "max_results": 25
    }
  }'
```

Fetch the saved job:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/sources/pubmed/searches/<job_id>" \
  -H "Authorization: Bearer $TOKEN"
```

What to look for:

- `id` for the saved search job
- `preview_results` for the first literature hits
- `total_results` for the search size

## Use Case 4: Bootstrap A New Research Space

Goal:

- create a first graph snapshot
- generate a research brief
- stage initial claim proposals

Start the bootstrap run:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/workflows/topic-setup/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"objective\": \"Map the strongest evidence around MED13 and congenital heart disease\",
    \"seed_entity_ids\": [\"$SEED_ENTITY_ID\"],
    \"source_type\": \"pubmed\",
    \"max_depth\": 2,
    \"max_hypotheses\": 10
  }"
```

What to look for in the response:

- `task_id`
- `graph_snapshot.id`
- `research_brief`
- `proposal_count`

List the outputs for the task:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/outputs" \
  -H "Authorization: Bearer $TOKEN"
```

## Use Case 5: Create A Continuous-Learning Schedule

Goal:

- save a recurring learning configuration
- run it immediately once
- inspect the `delta_report`

Create a schedule:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/schedules" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"Daily MED13 learning\",
    \"cadence\": \"daily\",
    \"seed_entity_ids\": [\"$SEED_ENTITY_ID\"],
    \"source_type\": \"pubmed\",
    \"max_depth\": 2,
    \"max_new_proposals\": 20,
    \"max_next_questions\": 5,
    \"run_budget\": {
      \"max_tool_calls\": 20,
      \"max_external_queries\": 10,
      \"max_new_proposals\": 20,
      \"max_runtime_seconds\": 300,
      \"max_cost_usd\": 5.0
    },
    \"metadata\": {}
  }"
```

Trigger an immediate run:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/schedules/<schedule_id>/start-now" \
  -H "Authorization: Bearer $TOKEN" \
  -X POST
```

Open the delta report artifact:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/outputs/delta_report" \
  -H "Authorization: Bearer $TOKEN"
```

## Use Case 6: Run Mechanism Discovery

Goal:

- search reasoning paths
- rank converging mechanisms
- stage mechanism proposals

Start the run:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/workflows/mechanism-discovery/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"seed_entity_ids\": [\"$SEED_ENTITY_ID\"],
    \"max_candidates\": 10,
    \"max_reasoning_paths\": 50,
    \"max_path_depth\": 4,
    \"min_path_confidence\": 0.0
  }"
```

What to inspect:

- `candidate_count`
- `proposal_count`
- `candidates[].ranking_score`

List the staged mechanism proposals:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/proposed-updates?proposal_type=mechanism_candidate" \
  -H "Authorization: Bearer $TOKEN"
```

## Use Case 7: Curate Staged Claims With Approval

Goal:

- turn staged proposals into a governed curation run
- review approvals
- resume the run

Start claim curation:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/workflows/evidence-curation/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "proposal_ids": [
      "33333333-3333-3333-3333-333333333333"
    ]
  }'
```

The run will usually pause. Check approvals:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/approvals" \
  -H "Authorization: Bearer $TOKEN"
```

Approve one action:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/approvals/<approval_key>/decision" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approved",
    "reason": "Ready to apply"
  }'
```

Resume the paused run:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/resume" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "All approvals resolved",
    "metadata": {}
  }'
```

Inspect final curation outputs:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/outputs/curation_summary" \
  -H "Authorization: Bearer $TOKEN"
```

## Use Case 8: Run A Full Supervisor Workflow

Goal:

- bootstrap a space
- ask a briefing question
- start governed curation
- resume the parent workflow after approval

Start the supervisor:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/workflows/full-research/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"objective\": \"Map the strongest evidence around MED13 and congenital heart disease\",
    \"seed_entity_ids\": [\"$SEED_ENTITY_ID\"],
    \"include_chat\": true,
    \"include_curation\": true,
    \"curation_source\": \"bootstrap\",
    \"briefing_question\": \"What is the strongest evidence I should review first?\",
    \"chat_max_depth\": 2,
    \"chat_top_k\": 10,
    \"curation_proposal_limit\": 5
  }"
```

Read typed supervisor detail:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/workflows/full-research/tasks/<task_id>" \
  -H "Authorization: Bearer $TOKEN"
```

What to inspect:

- `run.status`
- `bootstrap`
- `chat`
- `curation`
- `steps`
- `artifact_keys`

If the parent paused on child curation approval:

1. read `curation_task_id` from supervisor detail
2. list child approvals:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<curation_task_id>/approvals" \
  -H "Authorization: Bearer $TOKEN"
```

3. approve or reject each pending action
4. resume the parent:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/resume" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Child approvals complete",
    "metadata": {}
  }'
```

5. fetch supervisor detail again and confirm it is completed

## Use Case 9: Build A Dashboard For Supervisor Tasks

Goal:

- show recent supervisor activity
- highlight paused approval queues
- deep-link into the most important tasks

Fetch the dashboard summary:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/workflows/full-research/dashboard" \
  -H "Authorization: Bearer $TOKEN"
```

Useful query examples:

Only paused tasks:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/workflows/full-research/dashboard?status=paused" \
  -H "Authorization: Bearer $TOKEN"
```

Only chat-derived curation:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/workflows/full-research/dashboard?curation_source=chat_graph_write" \
  -H "Authorization: Bearer $TOKEN"
```

You can also page through typed supervisor rows:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/workflows/full-research/tasks?limit=20&offset=0&sort_by=updated_at&sort_direction=desc" \
  -H "Authorization: Bearer $TOKEN"
```

## Use Case 10: Audit What A Run Could Do And What It Actually Did

Goal:

- inspect a run safely without reading raw internal traces first
- understand allowed tools versus executed tools
- confirm whether later human review changed the final outcome

This works for any run type:

- `research-bootstrap`
- `graph-chat`
- `continuous-learning`
- `mechanism-discovery`
- `claim-curation`
- `supervisor`

Start with the run id you want to inspect.

Read the capability snapshot:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/capabilities" \
  -H "Authorization: Bearer $TOKEN"
```

Start with these fields:

- `workflow_template_id`
- `policy_profile`
- `visible_tools`
- `filtered_tools`

Then read the decision timeline:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/decisions" \
  -H "Authorization: Bearer $TOKEN"
```

Start with these fields:

- `summary`
- `declared_policy`
- `decisions`

How to read the result:

- if a tool is in `visible_tools` but never appears in `decisions`, the run was
  allowed to use it but did not need it
- if a decision has `decision_source = "tool"`, it came from harness execution
- if a decision has `decision_source = "manual_review"`, a later user action
  changed the outcome for something tied to this run

If you need the lower-level trace after that, open the raw event stream:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/events" \
  -H "Authorization: Bearer $TOKEN"
```

If you need the actual output content, open the outputs:

```bash
curl -s "$HARNESS_URL/v2/spaces/$SPACE_ID/tasks/<task_id>/outputs" \
  -H "Authorization: Bearer $TOKEN"
```

This is the recommended inspection order for operators and UI clients:

1. `capabilities`
2. `decisions`
3. `events`
4. `outputs`
