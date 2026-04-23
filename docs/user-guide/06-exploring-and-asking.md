# Exploring The Graph And Asking Questions

After evidence is promoted, it becomes part of the trusted graph. From there,
you can inspect it directly or ask AI-assisted questions over it.

## Browse Trusted Graph Data

List entities:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/graph-explorer/entities?q=MED13" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

List claims:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/graph-explorer/claims" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

List evidence for one claim:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/graph-explorer/claims/<claim_id>/evidence" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

Build a graph document around seed entities:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/graph-explorer/document" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "seeded",
    "seed_entity_ids": ["<entity_id>"],
    "include_claims": true,
    "include_evidence": true
  }'
```

Use graph explorer when you want read-only inspection without starting a new AI
run.

## Ask A Graph Search Question

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/agents/graph-search/runs" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Summarize the strongest MED13 evidence",
    "title": "MED13 graph search",
    "max_depth": 2,
    "top_k": 25,
    "curation_statuses": ["reviewed"],
    "include_evidence_chains": true
  }'
```

Use graph search when you want an evidence-backed answer over trusted graph
state.

## Ask Questions In Chat

Create a chat session:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/chat-sessions" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"title": "MED13 briefing"}'
```

Send a message:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/chat-sessions/<session_id>/messages" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "What is the strongest evidence linking MED13 to cardiomyopathy?",
    "max_depth": 2,
    "top_k": 10,
    "include_evidence_chains": true
  }'
```

Chat is useful when you want a conversational workflow over documents and graph
context.

If chat finds possible graph changes, stage them as proposals and review them
before trusting them:

```bash
curl -s "$ARTANA_API_BASE_URL/v1/spaces/$SPACE_ID/chat-sessions/<session_id>/proposals/graph-write" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -X POST
```
