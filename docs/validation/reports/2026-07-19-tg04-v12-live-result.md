# TG-04 V12 Live Scientific Result

## Decision

`STOP_WORKFLOW_INVALID`. V12 did not qualify scientific quality and does not
authorize replication or graph persistence.

## Frozen Evidence

- run: `tg04-v12-live-20260719`, repeat `1`
- model: `openai:gpt-5.6-luna`
- report SHA-256:
  `5d9310ddf9a1e5236b4517e5c179e526b473c50532eaeb4d9b2193de6124a4f6`
- provider attempts: `1`
- verified live provider receipts: `1`
- fallback calls: `0`
- normalization calls: `0`
- reviewer calls: `0`
- graph writes: `0`

The first command stopped before provider execution because the inherited
environment selected `openai:gpt-5.4-mini`. Its untouched `RESERVED` record was
resumed with a process-local `openai:gpt-5.6-luna` override. No provider lease,
response, journal, or retry existed before that resume.

## Observed Scientific Output

The primary Luna call categorized the title as `FINDING` and returned one joint
`REGULATION` event with:

- `apoptosis-linked gene 4` as the `GENE_OR_PROTEIN` cause;
- `Fas ligand expression` as one biological-process theme; and
- `cell death` as the second biological-process theme.

That is a complete source-valid direct representation admitted by the frozen
V12 projection contract. Luna did not invent regulation direction or claim that
either target occurred independently.

## Exact Failure

The raw event used `SOURCE_ASSERTED`, `ASSERTED`, and `UNSCOPED` polarity. The
shared inventory contract reserves `UNSCOPED` for `CONTROLLED_TARGET` events, so
Pydantic rejected the event with `StructuredModelSchemaError` before the
normalization and adversarial-review agents could run.

Luna's reasoning says it chose `UNSCOPED` because the title gives no positive or
negative regulation direction. This exposes a contract-language collision:

- `event_type` carries biological direction (`POSITIVE_REGULATION`,
  `NEGATIVE_REGULATION`, or neutral `REGULATION`);
- `polarity` is described as "direction or outcome" but is also used to encode
  whether a source-asserted result supports, refutes, or nullifies a claim; and
- `UNSCOPED` is a structural marker for a non-asserted controlled target.

The model supplied the correct neutral biological direction but put that
neutrality in the assertion-polarity field.

## Root-Cause Proof

A local, non-qualifying counterfactual changed only `polarity` from `UNSCOPED`
to `SUPPORT`. The unchanged raw event then passed the extraction schema with all
three participants and the `REGULATION` event type intact. No other field was
repaired.

This proves V12 is a workflow-contract failure, not evidence that Luna failed to
understand this source. It also means V12 did not test normalization quality and
cannot answer whether a second Luna agent improves the scientific graph.

## Stop Rule

Do not rerun this hidden unit. Do not count the counterfactual repair as agent
success. The next fresh trial must first separate biological effect direction,
claim outcome, epistemic force, and controlled-target assertion scope in both
the schema and prompt. Only then can a fresh hidden unit test scientific
comprehension rather than vocabulary ambiguity.
