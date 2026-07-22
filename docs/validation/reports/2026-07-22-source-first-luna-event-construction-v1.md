# Source-First Luna Event Construction V1

## Decision

`INVALID_PROVIDER_EXECUTION`

The experiment made exactly one authorized Luna-high creation call on the exposed
nested event. The remaining conditional cases did not run. The provider receipt
was internally consistent, but observed output usage exceeded the frozen
per-call output-token ceiling, so the run is invalid before scientific scoring.

## Previous Result Correction

The previous closed-candidate experiment remains frozen. Its accurate
interpretation is `STOP_SPECIALIST_NESTED_COVERAGE_INSUFFICIENT`: Luna correctly
recognized an incomplete DeepEventMine proposal set. It did not prove a Luna
scientific failure.

## Frozen Execution

- Source: `PMID-16428936`, exposed development data only
- Model: `openai:gpt-5.6-luna`
- Reasoning effort: `high`
- Provider creation calls: 1
- Retries and duplicate creation calls: 0
- Frozen maximum output tokens: 8,000
- Frozen maximum total tokens: 20,000
- Graph writes and promotions: 0

The provider input contained the event-local source passage, the highlighted
finding, two unrelated source-general structural examples, and the preserved
DeepEventMine proposal as an optional hint. It contained no public-gold answer,
expected event count, expected event ID, or prior reviewer conclusion.

## Provider Failure

Response ID:
`resp_0759f633f466358b006a60b5b75230819b881046552a23b33d`

The verified receipt reported:

- Input tokens: 1,371
- Output tokens: 10,368
- Reasoning tokens: 2,418
- Total tokens: 11,739
- Latency: 30.20 seconds
- Cost: $0.063579

The request sent `max_output_tokens=8000`, but the provider returned 10,368
output tokens. The existing receipt boundary validates total tokens, cost, and
latency; it does not carry or enforce the per-call output-token ceiling. That is
an experiment-integrity defect. Under the preregistered rules, a budget failure
is `INVALID_PROVIDER_EXECUTION`, even when the response and retrieval envelopes
otherwise match.

No patch or retry was made after the call.

## Unscored Scientific Diagnostic

The invalid output cannot receive scientific credit, but it still reveals the
same failure pattern:

1. Luna created a negative-regulation event for the decrease in c-Myc activity.
2. Luna created an outer positive-regulation event for `enhances`.
3. Luna did not create the explicit `sensitivity` event.
4. It attached `cancer cell` and `vinblastine` directly to the outer event,
   flattening the required nested structure.
5. It labeled the graph `COMPLETE` even though the typed graph was incomplete.
6. Every returned annotation was shifted left by one character, causing exact
   offset validation to fail before exposed-gold comparison.

Thus, even without the budget invalidation, the first scientific gate would not
have passed. Luna was allowed to discover missing events but still did not
construct the complete nested science.

## Validation

Focused tests prove rejection of missing roots, unknown and kind-mismatched
references, cycles, invalid or cross-scope offsets, unsupported text, duplicate
IDs, disconnected nodes, false `COMPLETE` declarations, and flattened direct
entity attachment. They also prove that provider packets exclude gold answers
and that conditional calls cannot precede the primary gate.

All outputs remain review-only. The three conditional calls were skipped.

The focused unit suite, Ruff, and MyPy passed. The single authorized
`make service-checks` run stopped at the architecture package-size guard before
service tests because this frozen experiment raised the context-experiment
package from 14 to 17 modules. Moving the modules after the provider call would
invalidate the recorded code hashes, so a narrow documented ceiling preserves
this checkpoint's custody. The architecture validator and its regression tests
were rerun after that non-executable control-file change; the full suite was not
repeated.
