# TG-04 V13 Visible Correction Result

## Decision

`ENTITY_CORRECTION_FOUND_TOPOLOGY_INVALID`.

This exposed, non-qualifying correction run does not authorize a reviewer call,
hidden selection, replication, or graph persistence.

## Evidence

- model: `openai:gpt-5.6-luna`
- evaluated commit: `ccad013d`
- frozen prior visible-report SHA-256:
  `7ef0926198a487d27a1145e58d2062c6b53026cc3fa2756dba163b9a64557332`
- correction provider attempts: `1`
- falsification provider attempts: `0`
- correction report SHA-256:
  `26e52466477a532c79711d415c512516ae1cb191020446d8cd9f35af3b1c57e6`
- deterministic semantic repairs: `0`
- fallback calls: `0`

The reviewer was correctly skipped after the correction failed its structured
contract. The same correction call must not be retried.

## Scientific Improvement Observed

The correction agent independently changed `apoptosis-linked gene 4` from
`OTHER_ENTITY` to `GENE_OR_PROTEIN`, retained its `CAUSE` role, preserved both
coordinated targets, kept neutral `REGULATION + SUPPORT + ASSERTED`, and marked
the source-event mapping `REFRAME`.

This is evidence that a role-separated Luna correction can detect and repair the
material entity-type contradiction without deterministic intervention.

## Exact Contract Failure

The correction agent misunderstood controlled-event reference ownership:

- it placed `controlled_event_ref` on the controlled expression event's
  `GENE_OR_PROTEIN` argument, although references are allowed only on a
  `BIOLOGICAL_PROCESS` `CAUSE` or `THEME`; and
- the outer regulation's two process themes referenced the outer regulation's
  own local ID instead of the distinct local IDs of the expression and
  cell-death controlled targets.

Pydantic rejected the first violation as `StructuredModelSchemaError`. The
second would also fail semantic topology binding because it is a self-reference.

## Root Cause And Next Gate

The schema restricts the field mechanically, but its agent-facing description
does not state the complete ownership rule. The prompt says references must
match returned IDs but does not give an unambiguous source-independent topology
example.

Before another visible call:

1. describe `controlled_event_ref` in the core output schema as an outer-process
   pointer to a distinct controlled event;
2. reject self-reference and require every controlled target to be referenced;
3. show a generic nested-event example where each outer process argument points
   to its corresponding target ID and target-local participants have null refs;
4. add adversarial tests for wrong-role refs, self refs, missing target refs, and
   swapped sibling refs; and
5. use a different visible case. Do not rerun this source.
