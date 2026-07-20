# TG04 Layered V8 Exposed Schema Stop

## Decision

`INVALID_RUN`. No scientific improvement is claimed.

The exposed one-shot run on PMID 40289860 used `openai:gpt-5.6-sol` with
provider-default reasoning. It made one provider call and stopped on schema
validation. There were zero retries, fallbacks, replays, or graph writes.

## Frozen Inputs

- Contract SHA-256: `53c91757f3a79e4e8f072ba6d67f4e378c9514609de3527426d25aea402affe5`
- Runner SHA-256: `e8e3cf729bb019c0ef19e9fbbf9a1f3bd759bdfedb2c6a4e0748715c3f2502e1`
- Source SHA-256: `e933d6dbc1e7599e41e093c5ad321131572ccdaddf871c8b610749519fe5ef84`
- Result SHA-256: `7ad1610cd3cad15a3cc6ea0fe8423af7c0ad53d33eb2ade91d557b9890edb7bd`
- Provider response ID: `resp_0ccd6644e4c9ef02006a5e062185c8819a886f6bdce6761b96`

The external artifacts are under:

`/Users/alvaro/.codex/artana-evidence-experiments/tg04/layered_v8_exposed_40289860_v1`

## Contract Gate Before Execution

The contract passed 48 adversarial tests, Ruff, and strict MyPy. Independent
biomedical and structural reviewers both returned `GO` for the bounded
representation gate. All extracted assertions were forced to remain
`REVIEW_ONLY` pending independent source adjudication.

## Schema Failure

The provider returned 34 participants and 18 proposed assertions, but the
payload had 38 Pydantic validation errors:

| Error class | Count |
|---|---:|
| Agent-calculated offsets did not exactly bound copied text | 10 |
| Categorical analysis purpose had no exact supporting cue | 14 |
| Cascading nested-item errors | 13 |
| Descriptive methods assertion lacked the contract-required outcome | 1 |

This is not a model timeout and not evidence that stronger reasoning failed.
The response completed and contained substantial structured content. The run
failed because one provider response was asked to perform two different jobs:

1. categorical biomedical interpretation; and
2. deterministic occurrence resolution and contract bookkeeping.

The second job should not be provider-owned.

## Scientific Warning Signs

No formal scientific score was calculated because the run was schema-invalid
and the preregistered stop rule prohibited source adjudication. Inspection for
root-cause diagnosis found material category errors that a valid contract would
have rejected:

- `equally likely` with reported values 27% versus 28% was labeled
  `EXACT_EQUALITY` and `EQUAL_TO`;
- `no difference` was paired with `UNCHANGED`, conflating a null test with a
  literal unchanged outcome;
- one `no longer associated` assertion was labeled with affirmative event
  negation;
- several analysis purposes were supplied without a source cue;
- objective, methods, and eligibility statements were included despite the
  result-focused experiment intent.

The raw response also preserved useful result structure, including separate
unadjusted and adjusted survival nulls, three exposure-survival associations,
and the sensitivity-analysis null association with its adverse outcome
direction. Because the payload was invalid, those observations are diagnostic
only and do not count as scientific recovery.

## Root Cause

The V8 internal ledger is too large and too strict to serve directly as the
provider-facing schema. Provider-generated numeric offsets are brittle and
violate the intended division of labor: agents should return categorical
scientific judgments and exact text anchors; deterministic code should resolve
occurrences, calculate positions, validate references, and calculate metrics.

Increasing reasoning effort is not the next controlled variable. The previous
Sol medium-versus-xhigh effort probe was itself invalid: medium was
schema-invalid and xhigh timed out. This V8 run used default reasoning and again
failed at the representation boundary before scientific comparison.

## Next Hypothesis

Split the provider contract from the internal ledger:

1. Provider returns exact text anchors with minimal left/right context, never
   numeric offsets.
2. Provider returns only categorical sentence eligibility, proposition family,
   roles, result state, direction, epistemic modifiers, and analysis facets.
3. Deterministic code resolves each anchor to exactly one occurrence and creates
   the offset-bound internal ledger.
4. Unresolved or ambiguous anchors fail closed without retry.
5. Objective, methods, and eligibility sentences are categorically routed away
   from scientific result extraction by an agent decision, not by a biomedical
   keyword fallback.
6. An independent source-only agent reviews the compiled ledger before any
   deterministic scientific metric is calculated.

The next exposed experiment should compare this compiled-anchor contract with
the preserved V8 raw response on the same source. It gets one call and advances
only if it produces a valid compiled ledger with no unsupported assertion and
correctly distinguishes null difference, exact equality, equivalence, and
non-inferiority.
