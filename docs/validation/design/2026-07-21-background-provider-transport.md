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
