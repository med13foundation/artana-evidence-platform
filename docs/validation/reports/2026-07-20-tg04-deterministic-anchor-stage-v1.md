# TG04 Deterministic Anchor Stage V1

Created: 2026-07-20

Decision: `EXPOSED_FIXTURE_STAGE_PROVEN_SCIENTIFIC_GATE_STILL_BLOCKED`

No provider call was made, no consumed source was retried, and no new
untouched source may be selected or frozen from this result.

## Architecture Decision

Exact source-occurrence resolution is no longer an obligation of the one-shot
scientific agent contract. It is a separate deterministic stage after agent
discovery and before frozen V10 compilation.

The agent remains the sole owner of scientific semantics:

- events and descriptive findings;
- predicates, polarity, direction, and modifiers;
- participants, scientific roles, and anaphoric identity;
- quoted source evidence and exclusions.

The deterministic stage may only:

- choose the atomic statement scope implied by the agent's quoted evidence;
- locate an exact quoted occurrence inside that scope;
- generate canonical V10 left and right context;
- create occurrence-specific transport participant identifiers when one
  conceptual participant is cited at different source occurrences;
- preserve anaphoric identity to an earlier event role;
- return `RESOLVED` or fail closed as `AMBIGUOUS`.

It may not invent, delete, merge, relabel, or score scientific claims. An
unused agent participant is an error rather than permission to delete it.

## Exposed Development Proof

The stage was tested against the already exposed V2 response for
`pubmed:40289860`.

- Source SHA-256:
  `e933d6dbc1e7599e41e093c5ad321131572ccdaddf871c8b610749519fe5ef84`
- V2 result SHA-256:
  `74a652882e3905b514a97f553794f62a3f773596a29b71c047319d2236f5a429`
- Resolved anchors: 93
- Occurrence-specific participant mappings: 25
- Resolution issues: 0
- Scientific semantic signature changed: no

The four previously ambiguous `OS` mentions now resolve to exact source
occurrences. Frozen V10 compilation advances beyond anchor validation and
then rejects the response with `CategoricalCueMismatchError`.

That remaining failure is intentional evidence that this stage does not
rewrite an agent's scientific categories to force a pass. Scientific
qualification remains blocked.

## Adversarial Fixtures

The tests also prove that:

- identical text in different atomic statements resolves within each event's
  local scope;
- the same text repeated twice inside one atomic scope returns `AMBIGUOUS`;
- transport identifiers and contexts are deterministic across repeated runs;
- the exposed response's categories, roles, polarity, direction, modifiers,
  evidence text, and participant meaning remain unchanged;
- later semantic compiler errors remain visible and fail closed.

## Validation

- external stage Ruff: pass
- external stage strict MyPy: pass
- stage plus frozen V10 tests: 76 passed
- provider calls: 0
- retries: 0
- fallbacks: 0
- graph writes: 0

External development package SHA-256 values:

- `__init__.py`:
  `e909cdeab06bd45064c277567b852e44fe63623843c25bc53cc0c7b48f49b6a6`
- `models.py`:
  `6ec04f73e08a0068b6c84d459ea4a845188b83691e6b46f6329b1c131ddbdbe5`
- `resolver.py`:
  `009499fa03855e95eb4ca4ea43f008da80c0ba88742120efd62ea228aab74087`
- `test_resolver.py`:
  `e8834d0b843f00e9fcf1bfffcf87110bca1ccecd03567cec04f3651bdf6e789c`

## Next Gate

Do not expand the one-shot prompt and do not freeze another untouched source.
First, use exposed fixtures to isolate the remaining
`CategoricalCueMismatchError` and test whether it is an agent semantic error,
an incorrect compiler expectation, or a projection mismatch. Advance only
after that classification is explicit and the staged pipeline passes exposed
fixtures without unsupported claims.
