# TG04 V10 Provider-Rule Visibility Development Result

Created: 2026-07-20

Decision: `DEVELOPMENT_PROOF_INCOMPLETE_STOP`

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
  `cba8ea9a3f0e944c65e7cbb819b1b3ceac1d656d232b38e63d901f98bdb2c1e8`

## Validation

- 97 combined frozen-V10, V1, and V2 tests: pass
- V1/V2 Ruff: pass
- V2 strict MyPy: pass
- V10 tree changed: no
- New source selected or frozen: no

## Stop Rule

Offline V2 is ready for independent review, but the development proof has not
passed live end to end. Do not select or freeze another untouched source yet.
The next decision is intentionally small: either accept one separately
preregistered V2 call on a different already exposed fixture, or stop and
reassess whether one-shot V10 is worth another development call. No contract
rewrite is justified by this result.
