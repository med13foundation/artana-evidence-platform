# TG-04 Provider Receipt Recalibration

Date: 2026-07-17

## Decision

**THE MINIMAL CUSTODY SMOKE PASSED.** One existing real Luna response from the
immutable finite source-unit artifact now verifies live after separating the
provider-native response representation from Artana's adapter representation.

This result proves only the corrected receipt boundary for one response. It does
not qualify all 64 historical calls, improve scientific extraction, authorize a
new benchmark, or permit graph persistence.

## Frozen Evidence

- Source artifact:
  `/tmp/artana-tg04/finite-source-unit-2026-07-17/luna-r2.json`
- Source artifact SHA-256:
  `8c59553036a4dc58eb55e5b6381058401fcbff2a9069499f7f26b5abb1f3f58e`
- Revalidated response ID:
  `resp_0593ad7adffdf4cb006a5aad151ce8819ba8d5468cc386e7e9`
- Model: `gpt-5.6-luna`
- New model calls: `0`
- Historical receipt result: `mismatched / output_schema_missing`
- Recalibrated receipt result: `verified_live / none`

## Root Causes

### Response schema metadata is not retained on retrieval

Artana previously required the retrieved response to contain
`text.format.schema`. The live OpenAI retrieval omitted that field. The exact
schema SHA-256 was still present in the Artana invocation binding inside the
provider-retrieved input prompt.

The verifier now records the categorical source of schema evidence:

- `provider_response`
- `provider_input_binding`
- `provider_response_and_input_binding`
- `not_required`
- `unverified`

The live smoke verified the schema through `provider_input_binding`. A missing
or different retrieved binding still fails closed.

### LiteLLM and provider retrieval expose different output shapes

The execution-time adapter output and later provider-native output did not have
the same canonical JSON hash. Provider retrieval included a reasoning item and
provider-native message fields that were absent from the LiteLLM output retained
by Artana.

The scientific structured payload hash matched exactly. The verifier now keeps
the raw hash mismatch visible and permits the categorical result
`structured_payload_with_verified_envelope` only when all of these independently
match:

1. the provider output contains at most one inert reasoning item, exactly one
   completed final-answer assistant message, exactly one structured
   `output_text`, and no commentary message, refusal, function call, extra
   message, or unknown output item;
2. response ID, model, completion status, message role, and message status;
3. structured payload SHA-256;
4. provider-retrieved prompt SHA-256;
5. invocation and kernel run IDs;
6. source, input, and evidence-unit SHA-256 values;
7. output-schema SHA-256 from the provider-retrieved invocation binding.

If the structured payload also differs, verification still fails with the
existing output or payload mismatch category. Exact raw-output equality remains
the stronger `exact_provider_output` category.

## Live Smoke Result

| Field | Result |
| --- | --- |
| Receipt status | `verified_live` |
| Failure | `none` |
| Provider response completed | yes |
| Exact raw output hash | no |
| Output verification | `structured_payload_with_verified_envelope` |
| Structured payload hash | exact match |
| Input topology | verified |
| Invocation topology | verified |
| Schema evidence | `provider_input_binding` |
| Schema hash | exact match |

## Validation

- New focused regressions cover response-omitted schema metadata, response plus
  input schema evidence, mismatched input schema, exact provider output, and
  adapter-transformed output with an exact structured payload.
- Adversarial regressions reject extra assistant messages, refusal content,
  function calls, unknown output items, and non-inert reasoning content.
- Existing receipt failure tests continue to reject changed output, payload,
  prompt, source, evidence-unit, model, role, status, and invocation evidence.
- All focused receipt, finite-unit, and claim-frame tests passed.
- Strict Ruff and mypy checks passed for the changed receipt boundary and tests.
- An independent adversarial review found the initially permissive transformed
  output grammar. The grammar was narrowed and regression-tested before commit.

## Next Isolated Experiment

After this custody-only PR merges, run exactly one procedure source unit through
one extractor and one blinded verifier using the same frozen eligibility rules.
The only question will be whether both agents categorize the unit as procedural
and exclude it from scientific evidence. Do not include an expert event or an
unannotated discovery in that run.

Proceed to a one-event reconstruction experiment only if the procedure unit has
two valid agent outputs, zero scientific candidates, zero binding failures,
fallback zero, and every provider receipt verifies live.
