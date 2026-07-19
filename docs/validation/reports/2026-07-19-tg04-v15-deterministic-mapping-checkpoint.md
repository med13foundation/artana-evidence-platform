# TG-04 V15 Deterministic Mapping Checkpoint

## Decision

`CONTINUE_PROVIDER_FREE`

The procedural mapping defect exposed by V14 is corrected in a standalone,
versioned provider-free boundary. The next live run is not yet authorized because
replay of the exact stopped payload exposed a second independent source-binding
failure.

## What Changed

- Added a standalone V14 normalization proposal schema with no `operation` field.
- Kept event inventory, semantic categories, arguments, roles, source positions,
  reasoning, falsification, and abstention agent-authored.
- Added deterministic operation derivation from mapping cardinality and canonical
  representation equality.
- Added a separate envelope that preserves the raw proposal, derived operations,
  canonical V13 semantic-binding result, source identity, and original-extraction
  identity.
- Left the frozen V13 service, schemas, prompts, and execution behavior unchanged.

## Real V14 Regression

The exact stopped V14 primary and normalization outputs were extracted from the
sealed journal into:

`tests/fixtures/tg04_v14_deterministic_mapping_regression.json`

Fixture SHA-256:

`4d6c2b57d180fa36304baa5ee0660ba96027d46186d5a7f0d31a30249075b2ae`

The historical operation sequence was:

`REFRAME, REFRAME, UNCHANGED, REFRAME, UNCHANGED`

The deterministic sequence is:

`REFRAME, REFRAME, REFRAME, REFRAME, REFRAME`

No event, argument, span, rationale, source mapping, or scientific category was
changed to obtain that result. The historical V13 binder still rejects the two
false `UNCHANGED` labels exactly as before.

## Newly Exposed Failure

After operation derivation, the canonical source binder accepts three events and
rejects two:

1. Normalized event position 1: `TRIGGER_MENTION_INVALID`.
2. Normalized event position 3: `ARGUMENT_MENTION_INVALID`.

Both failures come from invented local context around `RCC-S`. The source names
`RCC-S` once at the beginning and then elides the repeated subject in coordinated
clauses. The agent supplied mention anchors as though `RCC-S` occurred again near
each later clause. Those contexts are not verbatim source text.

This is a valid fail-closed result. Deterministic code must not delete, rewrite,
or silently repair those anchors to make the old run pass.

## Interpretation

The operation failure was procedural, not scientific. Removing it reveals that
the agent also confused an implied semantic participant with a repeated textual
mention. The five-event scientific structure remains promising, but the stopped
payload is still not a valid source-bound result and receives zero scientific
credit.

The next provider contract must explicitly separate these rules:

- scientific roles may refer to a participant named elsewhere in the source;
- mention anchors describe only literal occurrences of the exact span;
- a unique exact span requires no mention anchor;
- a repeated exact span requires source-verbatim left/right context identifying
  exactly one occurrence; and
- an elided participant must never be represented by an invented textual
  occurrence.

The binder remains fail-closed. No deterministic semantic repair is authorized.

## Validation

- V14 operation field absent and extra input rejected.
- `UNCHANGED`, `REFRAME`, `SPLIT`, and `MERGE` derivation covered.
- Ambiguous many-to-many, incomplete, and unknown mappings rejected.
- Exact stopped V14 payload preserved as a hash-pinned regression.
- Historical V13 execution/schema checks included in the focused run.
- 134 focused tests passed.
- Ruff passed on changed Python files.
- No provider call, retry, fallback, graph write, or scientific qualification.

## Next Gate

Add a V14 prompt and executor that bind the standalone proposal schema, operation
derivation version, literal-anchor policy, review contract, model identity, and
raw-versus-canonical custody. Then adversarially prove that malformed anchors stop
before review and that valid unique-span proposals proceed without repair.

Only after repository gates pass may a different visible source be preregistered
for one non-qualifying five-call experiment.
