# TG04 V10 Provider-Rule Visibility Development Result

Created: 2026-07-20

Decision: `DEVELOPMENT_PROOF_FAILED_STOP`

No new untouched source may be frozen from this result.

## Bounded Change

Frozen V10 and the consumed source `pubmed:42454948` were not modified or
rerun. A development-only prompt catalog made visible:

- all 8 cross-field `ProviderShapeError` rules absent from JSON Schema;
- all 9 exported deterministic compiler error categories;
- exact source anchoring, semantic cue ownership, role topology, context
  linkage, polarity, anaphora, and unique-event obligations.

AST equality checks fail if a provider-shape rule or exported compiler error
category is omitted from the catalog.

## Live Exposed Proof

- Source: previously exposed `pubmed:40289860`
- Source SHA-256: `e933d6dbc1e7599e41e093c5ad321131572ccdaddf871c8b610749519fe5ef84`
- Model: `openai:gpt-5.6-sol`, provider-default reasoning
- Live calls: 1
- Retries: 0
- Fallbacks: 0
- Graph writes: 0
- Receipt: `verified_live`
- Replay: false
- Result artifact SHA-256:
  `1f45403e7b52b2524f6d094766a3af3c7a1279cc8bc6a1032b0f540319024b35`

The response passed the complete provider-shape contract, including the two
rules that invalidated the consumed source-1 run. Deterministic compilation
then rejected it with `ScientificShapeError`.

## Exact Remaining Failure

The agent split one null overall-survival comparison into two events with the
same clause, family, roles, result state, direction, polarity, modifiers, and
context. One event carried the log-rank detail and the other carried the
adjusted estimate. Frozen V10 correctly treats those as one scientific event
with multiple analysis details.

The V1 catalog named the broad `ScientificShapeError` category but did not
state this no-duplicate-event condition explicitly. Therefore the claim that
every validation rule was visible was not yet true.

## Narrow V2 Remediation

V1 remains immutable. V2 adds only the missing ScientificShape conditions,
including:

- unique semantic-event identity;
- merging qualifiers and analysis estimates into one event;
- complete anaphora constraints;
- exact role/type, family topology, polarity, contrast, participant-use, and
  context-use requirements.

An exposed regression proves that a duplicated analysis split is rejected and
the merged single event compiles successfully.

V2 external identities:

- rule catalog:
  `e5b8c807d78035bdbbd9aeba6c671ef30a9511511c87b834326d509f3011a6e4`
- prompt:
  `2363aad9148e2e1eb6c995643a449b1db9fdd525daa448745a127669e34f405f`
- tests:
  `151ec1269ac38bf81c26d1d8b218cc63201fb7914c24358e8d34458dd4ed9f9b`
- one-attempt runner:
  `931c4cdb8e4fa9f2ea2b795bd7f94b55940fd52137d46ce6225f2af19659eaf0`

## Validation

- 97 combined frozen-V10, V1, and V2 tests: pass
- V1/V2 Ruff: pass
- V2 strict MyPy: pass
- V10 tree changed: no
- New source selected or frozen: no

## V2 Live Result

The separately locked V2 call also stopped without retry:

- live calls: 1
- retries: 0
- fallback: 0
- graph writes: 0
- receipt: `verified_live`
- replay: false
- result artifact SHA-256:
  `74a652882e3905b514a97f553794f62a3f773596a29b71c047319d2236f5a429`
- terminal error: `AmbiguousAnchorError`

V2 prevented the earlier duplicate-event split but supplied insufficiently
specific context for four uses of the exact text `OS`. The phrase
`associated with worse OS.` occurs more than once, so the left/right context
did not uniquely identify one source occurrence.

This exposed a scope error in the visibility audit. V1 and V2 covered V10's
own provider-shape constants and exported compiler errors, but V10 compilation
also invokes inherited V9 `AnchorResolver` validation. Those inherited errors
were not included in the asserted complete inventory. Therefore we have not
proven that every effective validation rule is visible to the agent.

## Final Stop Rule

Both bounded exposed calls are now consumed and neither passed end to end. Do
not call either prompt again, select a new source, or freeze an untouched
source. Expanding to a V3 catalog immediately would recreate the contract loop
this work was intended to stop.

The next activity should be analysis, not implementation: decide whether the
one-shot contract should expose a mechanically generated effective validator
specification across V8/V9/V10, or whether exact anchor resolution should be a
separate deterministic or staged responsibility. No further provider call is
authorized by this report.
