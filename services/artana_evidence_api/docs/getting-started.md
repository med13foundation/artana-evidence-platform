# Getting Started

## Start Here First

If you only remember one thing, remember this workflow:

1. add evidence with documents
2. extract `pending_review` proposals
3. promote or reject them manually
4. ask grounded chat questions

That is the easiest way to learn the service.

If you only have a few minutes, jump to
[10-Minute Happy Path](#10-minute-happy-path).

## What This Service Is

`artana_evidence_api` is the API layer for governed research workflows.

In plain English, it helps you:

- bring in evidence from PDFs or text notes
- turn that evidence into staged proposals
- keep a human in control of graph writes
- ask grounded questions with document and graph context

It also exposes larger workflows such as:

- graph search
- graph chat
- research bootstrap
- continuous learning
- mechanism discovery
- governed claim curation
- supervisor workflows that compose several steps together

The service does not replace the graph service. It sits on top of
`services/artana_evidence_db` and calls it through typed HTTP boundaries.

## Default Local Ports

- Harness API: `http://localhost:8091`
- Graph API: `http://localhost:8090`

## Run The Service

From the repository root:

```bash
source venv/bin/activate
PYTHONPATH="$(pwd)/services/artana_evidence_api:$(pwd)" python -m artana_evidence_api
```

Open:

- Interactive docs: `http://localhost:8091/docs`
- OpenAPI JSON: `http://localhost:8091/openapi.json`
- Health check: `http://localhost:8091/health`

## Run The Background Loops

The API can create runs inline for synchronous user requests, but the service
also has dedicated queueing and execution loops.

Run the schedule queueing loop:

```bash
source venv/bin/activate
PYTHONPATH="$(pwd)/services/artana_evidence_api:$(pwd)" python -m artana_evidence_api.scheduler
```

Run the worker loop:

```bash
source venv/bin/activate
PYTHONPATH="$(pwd)/services/artana_evidence_api:$(pwd)" python -m artana_evidence_api.worker
```

## Run The Container

The service container is defined in
[../Dockerfile](../Dockerfile).

Build it from the repository root:

```bash
docker build -f services/artana_evidence_api/Dockerfile -t artana-evidence-api .
```

Run it:

```bash
docker run --rm -p 8091:8091 \
  -e GRAPH_API_URL=http://host.docker.internal:8090 \
  -e DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5432/med13 \
  -e GRAPH_JWT_SECRET=change-me \
  -e OPENAI_API_KEY=change-me \
  artana-evidence-api
```

## Required Environment Variables

These are the main runtime settings.

Required:

- `GRAPH_API_URL`
- `DATABASE_URL` or `ARTANA_STATE_URI`
- `GRAPH_JWT_SECRET` or `JWT_SECRET`
- `OPENAI_API_KEY` or `ARTANA_OPENAI_API_KEY`

Common optional settings:

- `ARTANA_EVIDENCE_API_SERVICE_HOST`
- `ARTANA_EVIDENCE_API_SERVICE_PORT`
- `ARTANA_EVIDENCE_API_SERVICE_RELOAD`
- `ARTANA_EVIDENCE_API_GRAPH_API_TIMEOUT_SECONDS`
- `ARTANA_EVIDENCE_API_SCHEDULER_POLL_SECONDS`
- `ARTANA_EVIDENCE_API_SCHEDULER_RUN_ONCE`
- `ARTANA_EVIDENCE_API_WORKER_ID`
- `ARTANA_EVIDENCE_API_WORKER_POLL_SECONDS`
- `ARTANA_EVIDENCE_API_WORKER_RUN_ONCE`
- `ARTANA_EVIDENCE_API_WORKER_LEASE_TTL_SECONDS`
- `GRAPH_ALLOW_TEST_AUTH_HEADERS`

## Authentication

All API routes use the same auth model as the rest of the repository.

Normal usage:

- send `Authorization: Bearer <token>`
- or send `X-Artana-Key: <art_sk_...>`

Example:

```bash
export HARNESS_URL="http://localhost:8091"
export TOKEN="your-jwt-token"
export SPACE_ID="11111111-1111-1111-1111-111111111111"

curl -s "$HARNESS_URL/health" \
  -H "Authorization: Bearer $TOKEN"
```

All examples below assume `SPACE_ID` is a research space you can access.

If you want to confirm who the service thinks you are, call:

```bash
curl -s "$HARNESS_URL/v1/auth/me" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

## Local Test Auth Shortcut

For local non-production smoke testing, the repository supports test headers
when `GRAPH_ALLOW_TEST_AUTH_HEADERS=1`.

Example:

```bash
export HARNESS_URL="http://localhost:8091"

curl -s "$HARNESS_URL/v1/harnesses" \
  -H "X-TEST-USER-ID: 11111111-1111-1111-1111-111111111111" \
  -H "X-TEST-USER-EMAIL: researcher@example.com" \
  -H "X-TEST-USER-ROLE: researcher"
```

Use this only for local development and tests.

## Bootstrap Or Issue An API Key Locally

If you want a normal Artana API key for SDK or HTTP usage, use:

[`scripts/issue_artana_evidence_api_key.py`](/Users/alvaro/Documents/Code/monorepo/scripts/issue_artana_evidence_api_key.py)

Fresh deployment, first key:

```bash
venv/bin/python scripts/issue_artana_evidence_api_key.py \
  --base-url http://localhost:8091 \
  --bootstrap-key "$ARTANA_EVIDENCE_API_BOOTSTRAP_KEY" \
  --email developer@example.com \
  --username developer \
  --full-name "Developer Example"
```

Already bootstrapped deployment, create another key from an existing
credential:

```bash
venv/bin/python scripts/issue_artana_evidence_api_key.py \
  --base-url http://localhost:8091 \
  --mode create \
  --api-key "$ARTANA_API_KEY" \
  --api-key-name "CLI Key"
```

By default the script prints shell exports, so you can do:

```bash
eval "$(venv/bin/python scripts/issue_artana_evidence_api_key.py ...)"
```

## Create Or Reuse Your Default Space

Once you have a working credential, the easiest space setup call is:

```bash
curl -s -X PUT "$HARNESS_URL/v1/spaces/default" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

That returns a personal default space if one already exists, or creates it if
it does not.

## 10-Minute Happy Path

If you only want one simple learning exercise, do this flow:

1. submit one text note or upload one PDF
2. run document extraction
3. list the review queue
4. promote or reject one queue item
5. ask a chat question with the document attached

What each step means:

- document upload gives the service evidence to work from
- extraction turns that evidence into staged review items
- promote or reject keeps a human in control
- chat lets you ask grounded questions with document context

What changes between text and PDF:

- text goes straight to extraction
- PDF upload stores the file first, and extraction runs enrichment before
  proposal staging

Example with one text note:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/documents/text" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "MED13 evidence note",
    "text": "MED13 associates with cardiomyopathy.",
    "metadata": {}
  }'
```

Then:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/documents/<document_id>/extract" \
  -H "Authorization: Bearer $TOKEN" \
  -X POST
```

Then:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/review-queue?document_id=<document_id>" \
  -H "Authorization: Bearer $TOKEN"
```

Then:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/chat-sessions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "First document chat"
  }'
```

And finally:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/chat-sessions/<session_id>/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What does this document suggest about MED13?",
    "document_ids": ["<document_id>"],
    "refresh_pubmed_if_needed": true
  }'
```

What success looks like:

- the document exists and has its own `document_id`
- extraction returns a non-zero `proposal_count` when evidence was found
- the review queue shows pending items linked back to the document
- chat returns an answer plus verification metadata

If you prefer Python instead of `curl`, the matching SDK guides are:

- [SDK README](../../packages/artana_api/README.md)
- [SDK Examples](../../packages/artana_api/examples/README.md)

## First Six Calls To Make

If you are new to the service, this is the easiest way to learn it.

1. Check health:

```bash
curl -s "$HARNESS_URL/health" -H "Authorization: Bearer $TOKEN"
```

2. Confirm your identity:

```bash
curl -s "$HARNESS_URL/v1/auth/me" -H "X-Artana-Key: $ARTANA_API_KEY"
```

3. Get or create your default space:

```bash
curl -s -X PUT "$HARNESS_URL/v1/spaces/default" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

4. List available harnesses:

```bash
curl -s "$HARNESS_URL/v1/harnesses" -H "Authorization: Bearer $TOKEN"
```

5. Start a research bootstrap run:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/agents/research-bootstrap/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "objective": "Map the strongest evidence around MED13 and congenital heart disease",
    "source_type": "pubmed",
    "max_depth": 2,
    "max_hypotheses": 10
  }'
```

6. Inspect the run artifacts:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/<run_id>/artifacts" \
  -H "Authorization: Bearer $TOKEN"
```

And then, once you have staged work, list the review queue:

```bash
curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/review-queue" \
  -H "Authorization: Bearer $TOKEN"
```

If that feels too advanced, skip back to the document workflow above first.

## What Was Just Added: Run Transparency

The newest addition to the service is run transparency.

Every run now gives you two extra views:

- `capabilities`
  what the run was allowed to use when it started
- `policy-decisions`
  what the run actually executed, plus later human review decisions that can be
  tied back to the run

If you only want one quick learning exercise after your first run, do this:

1. start any run
2. copy the returned `run.id`
3. fetch `capabilities`
4. fetch `policy-decisions`

Example:

```bash
export SPACE_ID="11111111-1111-1111-1111-111111111111"
export RUN_ID="<run_id>"

curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/capabilities" \
  -H "Authorization: Bearer $TOKEN"

curl -s "$HARNESS_URL/v1/spaces/$SPACE_ID/runs/$RUN_ID/policy-decisions" \
  -H "Authorization: Bearer $TOKEN"
```

Use these endpoints to answer three simple questions:

- what could the run do?
- what did it actually do?
- did a later human review change the final outcome?

For the full guide, read [Run Transparency](./transparency.md).

## Which Workflow Should I Use?

Use:

- `graph-search` when you want one grounded answer against the graph
- `chat-sessions` when you want a conversational workflow with memory
- `research-bootstrap` when a space is empty and needs an initial evidence map
- `continuous-learning` when you want recurring refresh cycles
- `mechanism-discovery` when you want ranked candidate mechanisms
- `graph-curation` when you already have staged proposals and need approval-gated review
- `supervisor` when you want one parent workflow that can bootstrap, chat, and curate
