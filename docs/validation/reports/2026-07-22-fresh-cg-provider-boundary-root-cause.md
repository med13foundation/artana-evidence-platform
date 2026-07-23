# Fresh-CG provider-boundary root cause

## Decision

The primary cause is **B — provider enforcement defect**.

The final SDK HTTP payload contained `max_output_tokens: 20000`. The stored
provider response also reports `max_output_tokens: 20000`, but completed with
`output_tokens: 40443`, including `reasoning_tokens: 5544`. It did not terminate
as `incomplete`; its status is `completed` and `incomplete_details` is null.

OpenAI documents `max_output_tokens` as an upper bound that includes visible
output and reasoning tokens. The reasoning guide further states that reaching
that value yields `status: incomplete` with reason `max_output_tokens`.

- [Official Responses create reference](https://developers.openai.com/api/reference/resources/responses/methods/create#responses-create-max_output_tokens)
- [Official reasoning guide](https://developers.openai.com/api/docs/guides/reasoning#managing-the-context-window)
- [Official OpenAI Python SDK source, v2.44.0](https://github.com/openai/openai-python/blob/v2.44.0/src/openai/resources/responses/responses.py)

## Evidence by failure class

### A. Request serialization defect — rejected

The frozen `20000` value flows from Fresh-CG configuration through
`ProviderRequest` to `responses.create(max_output_tokens=...)`. An offline
`httpx.MockTransport` capture exercised the installed `openai==2.44.0` SDK and
captured the final JSON body without headers. It contained the exact
`max_output_tokens` field and value. The capture made no external request.

### B. Provider enforcement defect — supported

The same provider response reports both the requested ceiling (`20000`) and
usage above it (`40443`). Official semantics make this an inclusive output plus
reasoning ceiling, so the reasoning breakdown must not be added again.

### C. Usage finalization or custody defect — rejected

The original boundary compares terminal and confirmation usage byte-for-byte
before budget validation. A `RECEIPT_BUDGET` failure therefore proves that this
equality check passed. Two later read-only retrievals also returned identical
full-envelope hashes, status, usage, and reported ceiling.

### D. Local accounting defect — secondary reporting omission

This did not cause the provider overrun. It did cause the invalid result to
show zero admitted aggregate cost while real rejected spend remained nested in
diagnostics. Operational-accounting V2 now separates:

- admitted scientific spend: `$0.00`;
- rejected, unadmitted provider spend: `$0.246147`;
- global budget consumption: `$0.246147`;
- observed usage: 3,489 input, 40,443 output, 43,932 total tokens.

The sealed result remains byte-identical and receives no scientific credit.

### E. Multiple causal defects — rejected

The local reporting omission is downstream of the provider overrun. It did not
alter the request, response, provider generation, usage fields, or receipt
decision, so it is not a second cause of the original incident.

## Readiness

The operational accounting is corrected in a separate versioned artifact, but
the primary provider enforcement defect is external and not locally
correctable. A replacement holdout case has not been selected or adjudicated,
and no new scientific experiment is authorized. Raising the budget would not
correct this incident and is prohibited.
