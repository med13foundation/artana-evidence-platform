# Provider Receipt Boundary Smoke

**Decision:** `INVALID_SMOKE_EXPERIMENT`

This checkpoint made one non-scientific categorical provider call. It did not
access a biomedical source, repeat the V2 scientific experiment, write to the
graph, or enable promotion.

## Custody

- Preregistration SHA-256:
  `e35244e61d6c757b2cf7a50cba5533058ff6832ab69abd427cba58a4cec763fe`
- Frozen-state SHA-256:
  `2e80373e84684b25e7063318739fa30beb400df56cf603e1f4ef2f88f8cb2791`
- Response ID: `resp_09fa66ffeda439fb006a5fd16b59ec8199af3a2ea4ed67fa20`
- Provider creation calls: `1`
- Provider retries and fallbacks: `0`
- Biomedical sources and sealed test sources accessed: `0`
- Scientific experiments run: `0`

The frozen smoke is terminal and was not retried. The raw response was not
committed.

## Live Failure

- Stage: `RECEIPT_SCHEMA`
- Root cause reported at the live boundary: creation response schema differed
  from the frozen request schema.
- Tokens, latency, and cost: `UNVERIFIED_NOT_RECORDED`.

Usage was not accepted because schema verification failed first. The accounting
values are intentionally not reported as zero.

## Root Cause

The mismatch was created inside Artana's SDK serialization boundary. Artana
serialized OpenAI response models with raw Pydantic `model_dump()`. That shape
uses Python model field names and materializes model defaults. The frozen request
uses the provider API shape.

The concrete schema example is the OpenAI SDK response-format model:

- API field: `schema`;
- Python model field: `schema_` with alias `schema`;
- optional response field: `description`, defaulting to `None` when it was not
  returned.

Therefore the failed comparison did not prove that the provider changed the
structured-output schema. It proved that Artana compared a request-shaped object
to a Python-model-shaped object. The failed smoke remains invalid because this
cause was discovered only after the authorized call.

## Offline Correction

The provider adapter now uses the OpenAI SDK's API-shaped serialization:

- provider aliases are enabled;
- fields not returned by the API remain absent;
- explicit provider `null` values remain visible;
- creation, retrieval, and input items use the same representation.

This correction does not allowlist schema changes. The resulting API-shaped
schema must still equal the frozen strict schema exactly. A mismatch now records
redacted field paths plus expected and actual schema hashes.

## Immutable Boundaries

The verifier requires exact agreement for:

- response ID, object type, creation time, model, status, and output-item IDs and
  types;
- requested and returned model identity and reasoning effort;
- custody metadata;
- retrieved provider input;
- API-shaped structured-output schema;
- canonical structured payload;
- completion status, errors, and incomplete details;
- creation-versus-retrieval usage, including detailed cached and reasoning token
  counts;
- deterministic token, latency, and cost budgets.

Missing usage, malformed output, unknown output topology, changed payload,
changed identity, changed input, changed schema, or any unknown envelope
difference fails closed.

## Explicit Transport Allowlist

Only these non-scientific differences can be accepted, and only under their
listed predicates:

| Field path | Predicate | Rationale |
| --- | --- | --- |
| `$.text` | retrieval omits it after request and creation schema verification | optional response text configuration |
| `$.completed_at` | one representation is `null`, the other a valid completion timestamp | optional completion timing metadata |
| `$.output[i].content[0].text` | canonical JSON payload hashes are exact | insignificant JSON object serialization only |
| `$.output[i].status` for reasoning | `null` versus `completed` | optional returned reasoning-item status |
| `$.output[i].content` for reasoning | missing, `null`, or empty on both sides | no reasoning content disclosed |
| `$.output[i].encrypted_content` for reasoning | missing or `null` on both sides | optional include-only field was not requested or disclosed |
| `$.output[i].phase` for the final message | `null` versus `final_answer` | optional message transport phase |
| `$.output[i].content[0].annotations` and `.logprobs` | missing, `null`, or empty on both sides | optional empty output-text metadata |

No wildcard allows unknown fields. Output-item reordering, extra item types,
changed IDs, disclosed reasoning content, non-empty annotations, or any new path
fails until separately understood and tested.

The allowlist is based on the official Responses create/retrieve contracts and
API compatibility policy: response output is heterogeneous; several transport
fields are optional; and optional response fields can be added over time. See
the [Responses API reference](https://developers.openai.com/api/reference/resources/responses/methods/create),
[retrieve response reference](https://developers.openai.com/api/reference/resources/responses/methods/retrieve),
and [API compatibility policy](https://developers.openai.com/api/reference/overview).

## Validation

- Focused receipt, provider-boundary, smoke-preflight, and scientific-preflight
  tests: `30 passed`.
- Focused Ruff: passed.
- Focused strict MyPy: passed for `9` source files.
- `make service-checks`: passed after the final offline correction.
- Repository coverage: `87.64%`, above the `86%` gate.

## Stop Decision

No unauthorized scientific preregistration was generated because the live smoke
did not validate. The corrected boundary is offline-green but not yet live-
validated. Any future transport smoke must be a new preregistered experiment with
new explicit authorization; it must not retry or reinterpret this response.
