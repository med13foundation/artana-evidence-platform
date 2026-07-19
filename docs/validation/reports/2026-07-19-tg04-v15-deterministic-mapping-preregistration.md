# TG-04 V15 Deterministic Mapping Preregistration

## Decision

`AUTHORIZED_FOR_PROVIDER_FREE_IMPLEMENTATION`

V14 is a sealed negative operational result. It must not be rerun, rescored, or
rewritten. This checkpoint authorizes one isolated correction before a different
visible source is selected: remove procedural normalization-operation labels from
the provider contract and derive them deterministically.

No provider call, hidden source, graph write, or scientific-quality claim is
authorized by this document.

## Root Cause

The V14 normalizer represented all five source-explicit events but labeled two
one-to-one mappings `UNCHANGED` after changing representation fields. The frozen
binder correctly rejected those labels. `UNCHANGED` versus `REFRAME` is not a
biomedical judgment; it is an exact comparison between two structured records.

Asking an agent to calculate an exactly computable bookkeeping category added a
failure mode without adding scientific information.

## Frozen Hypothesis

Removing the procedural operation field from the agent-visible schema will let a
scientifically complete normalization pass the local boundary when, and only
when, its source-event mapping is complete and structurally valid.

The agent remains solely responsible for:

- event inventory and representation family;
- event type, direction, claim outcome, and epistemic status;
- participants, roles, context, and controlled-event topology;
- source-to-normalized-event positions;
- reasoning and falsification conditions; and
- abstention when scientific meaning is unresolved.

Deterministic code owns only the operation implied by mapping topology and exact
representation equality:

- `MERGE`: one normalized event maps from multiple source events;
- `SPLIT`: one source event maps to multiple normalized events;
- `UNCHANGED`: a one-to-one mapping is byte-equivalent as canonical JSON; and
- `REFRAME`: a one-to-one mapping is not byte-equivalent.

Ambiguous many-to-many topology, missing or unknown source positions, incomplete
coverage, and mixed operation topology fail closed. Code must not add, remove,
merge, split, or rewrite scientific events.

## Version Boundary

- Preserve every V13 contract, prompt, schema, manifest, journal, and result.
- Add a new provider schema that contains source positions but no operation field.
- Add a new issued execution identity and bind its exact prompt, schema, binder,
  review contract, and model lineage.
- Preserve the raw provider payload separately from deterministic derived labels.
- Keep the three-call execution non-qualifying without an independent completeness
  witness and live provider receipts.

## Provider-Free Acceptance Gates

1. The new JSON schema does not expose or accept an `operation` field.
2. Exact one-to-one equality derives `UNCHANGED`.
3. Any one-to-one representation change derives `REFRAME`.
4. One-to-many derives `SPLIT`; many-to-one derives `MERGE`.
5. Many-to-many, unknown, missing, or incomplete mappings fail closed.
6. The preserved V14 raw payload replays through the new binder without changing
   any event, argument, span, rationale, or source mapping.
7. The old V13 binder still rejects that same payload under the frozen contract.
8. Historical V13 schema and execution-manifest hashes remain unchanged.
9. Focused tests, lint, type checks, architecture checks, and `make service-checks`
   pass from a clean commit.
10. An independent adversarial reviewer finds no P0/P1 path that can use derived
    operations to alter scientific meaning or fabricate issued lineage.

## Stop Rules

- Stop before a provider call if any acceptance gate fails.
- Stop if deterministic derivation requires biomedical interpretation.
- Stop if the repair changes historical evidence or weakens fail-closed behavior.
- After the provider-free gates pass, preregister a different visible source and
  one scientific hypothesis before authorizing the next minimal live run.
