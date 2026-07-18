# TG04 V5 Selection Preflight

## Decision

V5 stopped before any model call. The direct seeded selection is fresh, but its
sealed expert graph is not a complete finite representation of the source unit.
It cannot be used to qualify scientific recovery.

## Selection

- Seed: `5209c8aa2a793af30f577afdec8d92c4164b25e1560d399f74d27cef59a31190`
- Case: `bionlp-ge-2011-holdout:PMID-8690900`
- Unit: `source-unit-b4012fd75c3179695bb5c5a101af3064d6a35c0d2efef6cd6e9770299169c5f2`
- Rank: `0039c9790bea307ad394943174e808efc8f85efc3bdfed6c240b02ee1e9ac4d4`
- Expert graph: `095cd15b56ddd8546f72753c76fa6a68d16d583b973213a8ac2b73fca1626aee`
- Agent execution attempted: no

## Blocking Defect

The expert graph represents the CD80 up-regulation and IL-10-associated null
detection result. The same source unit also explicitly states that anti-CD28 mAb
CLB-CD28/1 restores NF-kappa B/Rel nuclear activity in IL-10-inhibited
lymphocytes. That second positive-regulation event is absent from the graph.

Running Luna against this unit would make the benchmark unable to distinguish a
complete answer from a source-supported extra event. The correct action is to
record a failed selection preflight, spend no model call, and derive the next
selection seed from the immutable JSON report hash.
