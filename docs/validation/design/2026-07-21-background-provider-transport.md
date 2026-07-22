# Background Provider Transport

## Verified Provider Behavior

OpenAI Responses background mode is enabled with `background=true`. The
official guide demonstrates it with the GPT-5.6 family and instructs clients to
poll the same response ID while status is `queued` or `in_progress`.

The documented response statuses are `queued`, `in_progress`, `completed`,
`failed`, `cancelled`, and `incomplete`. This transport treats only `completed`
as success. The other three terminal states fail closed, and unknown states are
invalid.

The official Python SDK exposes response creation, retrieval, cancellation, and
input-item listing. Completed response objects expose usage. Cancellation is
documented as idempotent, but response creation is not. Therefore this design
does not send or claim a creation idempotency key.

Official references:

- https://developers.openai.com/api/docs/guides/background
- https://github.com/openai/openai-python/blob/main/src/openai/resources/responses/api.md
- https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response.py

The official `Response` contract states that the length and order of the
`output` array depend on the model. Reasoning items are first-class output
items, so receipt validation must not impose a one-reasoning-item cardinality
that the provider does not guarantee.

## State Machine

1. Submit one request with `background=true`, SDK retries disabled, and a short
   acknowledgement timeout.
2. Require a valid response ID, model, metadata, reasoning configuration, and
   response format from the acknowledgement.
3. If status is pending, poll only that response ID within a monotonic budget.
4. Stop immediately on completion, provider failure, cancellation,
   incompleteness, an unknown state, or polling timeout.
5. After completion, retrieve one confirmation snapshot and the stored input.
6. Apply the existing strict receipt boundary to the completed and confirmation
   snapshots, then parse the categorical structured payload.

The initial acknowledgement is lineage, not a completed scientific receipt.
The strict receipt comparison therefore uses two completed snapshots after the
background operation reaches `completed`.

## Non-Guarantees

- The public guide documents GPT-5.6 background mode. It does not separately
  document the private `gpt-5.6-sol` alias; the non-scientific smoke must prove
  that exact model accepts background execution.
- An acknowledgement timeout is ambiguous because no response ID is available.
  Creation is never repeated after that condition.
- Polling is retrieval, not another model-generation call.
- A local polling timeout does not prove provider cancellation. This checkpoint
  does not automatically cancel because cancellation cannot make a timed-out
  experiment valid.

## V4 Topology Correction

Scientific development V4 completed with one final structured message and a
stable canonical payload, but it also returned multiple reasoning items. The
original receipt selector rejected that valid provider topology before usage or
scientific validation could be finalized.

The corrected boundary accepts zero or more well-formed reasoning items and
still requires exactly one completed final assistant message with exactly one
structured `output_text` part. Receipt identity includes every output item in
order, so an added, removed, reordered, or changed reasoning item still fails
closed between completed and confirmation retrievals.

## V5 Budget And Offset Findings

Scientific development V5 passed the corrected topology boundary and completed
with a stable structured payload. Its receipt remained invalid because the
provider reported `161,166` total tokens against the frozen `40,000`-token
ceiling, even though the same frozen pricing formula placed the call below the
unchanged `$5.00` cost ceiling. V5 stays terminal and is not reinterpreted.

A read-only replay also showed that every returned mention text occurred in the
source, while `54/66` supplied character ranges had arithmetic drift of at most
three characters. The scientific prompt and output categories are therefore
unchanged in V6. A separate deterministic resolver may replace offsets only
when the agent's exact text has one unique nearest source occurrence and both
boundaries move no more than eight characters. Missing text, tied nearest
occurrences, and more distant corrections fail closed. The resolver preserves
the hash of the raw extraction in event lineage and records a second hash for
the resolved extraction. It never edits event types, roles, references, exact
text, negation, speculation, or any other scientific field.

V6 raises only the total-token accounting ceiling to `200,000`, based on the
preserved V5 provider usage. The request output limit and `$5.00` cost ceiling
remain unchanged. This corrects experiment validity; it does not make a
scientific result more likely to pass.
