# TG04 Sp1/Sp3 Relation Ledger V2 Invalid

Status: `INVALID_RUN`

Scientific qualification: `false`

Advancement: `SEPARATE_LEDGER_VALIDITY_FROM_CANDIDATE_CONSISTENCY`

This one-shot exposed breadth test applied the participant-relation ledger to `Sp1 and Sp3 bind to the GC-box present in the A3G promoter.`

## Execution Integrity

- already-exposed source and independently generated DeepEventMine proposal;
- finished runner and contract externally preregistered by SHA-256;
- adversarial preflight before execution;
- provider calls: `1`;
- model: default `openai:gpt-5.6-sol`;
- retries, fallback, replay, graph writes: `0`;
- no benchmark score or scientific gain decision.

The initial preflight vetoed unbound candidate decisions, a mutable executable runner, and binding-specific prompt coaching. These were corrected before the call; repeated preflight returned `GO`.

## Failure

The provider returned a schema-valid payload, but semantic validation rejected it:

```text
invalid role candidate shape: C4
```

Sol rejected the parser's direct Sp1/Sp3 Theme edges and represented one coordinated group Theme with Sp1 and Sp3 as separately addressable members. Its candidate trace retained both original member IDs and the corrected group role binding. The validator forbade participant/event trace references on a role candidate even though the schema allowed them.

The run therefore stopped before provider-receipt adjudication and independent source review. The raw frame receives no scientific credit.

## Diagnostic Observation

The rejected raw payload contained one binding event, separate Sp1/Sp3 identities under a coordinated group, the GC-box as binding Site, the GC-box as part of the A3G promoter, the promoter-to-A3G locus relation, and a localization event for `present in`. This remains diagnostic only.

## Methodological Correction

The loop has repeatedly allowed candidate-adjudication bookkeeping to erase an otherwise reviewable scientific frame. That is the wrong measurement boundary.

The next protocol must retain two independent categorical outcomes:

1. scientific-ledger validity: schema, source anchoring, references, types, cycles, live lineage, and independent source review;
2. candidate consistency: deterministic agreement between span/type/role decisions and final ledger bindings.

A candidate-consistency failure still fails the whole arm, but it must not prevent receipt verification or scientific-frame evaluation. The next test must use a different exposed source rather than retry this output.
