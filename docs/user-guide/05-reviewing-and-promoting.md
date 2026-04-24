# Reviewing And Promoting Evidence

The review items list is the safest default way to decide what becomes trusted graph
knowledge.

## List Review Items

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/review-items" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

Useful filters include:

- `status`
- `item_type`
- `kind`
- `task_id`
- `document_id`
- `source_family`

For example, list items from one document:

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/review-items?document_id=<document_id>" \
  -H "X-Artana-Key: $ARTANA_API_KEY"
```

## Promote A Good Item

Promote means: "I reviewed this and want it to become trusted graph knowledge."

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/review-items/<item_id>/decision" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "promote",
    "reason": "Reviewed and approved",
    "metadata": {}
  }'
```

## Reject A Weak Item

```bash
curl -s "$ARTANA_API_BASE_URL/v2/spaces/$SPACE_ID/review-items/<item_id>/decision" \
  -H "X-Artana-Key: $ARTANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "reject",
    "reason": "Evidence is not strong enough",
    "metadata": {}
  }'
```

## Other Actions

Common actions:

- `promote`: approve a proposal into the graph
- `reject`: keep a proposal out of the graph
- `convert_to_proposal`: turn a review-only note into a concrete proposal
- `mark_resolved`: mark a review-only follow-up as handled
- `dismiss`: close a review-only item without promoting it
- `approve`: approve a gated run action

## Variant-Aware Review Tip

For variant-aware extraction, promote entity candidates before observations
that depend on them.

For example, if an `observation_candidate` describes a new variant, promote the
linked `entity_candidate` first. Then retry or promote the observation.

That keeps the graph clean: observations should attach to known entities.

## Lower-Level Proposed-Update Endpoints

The review items list is the preferred surface, but lower-level proposed-update endpoints
exist:

- `GET /v2/spaces/{space_id}/proposed-updates`
- `GET /v2/spaces/{space_id}/proposed-updates/{proposal_id}`
- `POST /v2/spaces/{space_id}/proposed-updates/{proposal_id}/promote`
- `POST /v2/spaces/{space_id}/proposed-updates/{proposal_id}/reject`

Use those when building advanced tools or debugging proposal records directly.
