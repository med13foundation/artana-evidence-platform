# TG04 Directional Comparison Ledger V1

Status: `SCIENTIFIC_FAIL_COMPARATOR_LEAKAGE`

Comparison frame: `VALID`

Scientific qualification: `false`

Advancement: `SEPARATE_COMPARISON_ONLY_REFS_THEN_EXPAND`

This exposed V3 experiment tested a typed directional comparison on a different source: IL-1beta up-regulation in EBV-transformed LCLs and group III BL cells compared with group I BL cells.

## Integrity

- source, runner, V2/V3 contracts, repository, fixture, and prior artifacts sealed;
- adversarial preflight before execution;
- one default `openai:gpt-5.6-sol` call;
- retries, fallback, replay, graph writes: `0`;
- live receipt: `verified_live`;
- attempt lineage: `pass`;
- candidate consistency: `NOT_APPLICABLE`;
- two independent source-only reviews and one adversarial adjudication;
- no benchmark score or automatic gain decision.

Preflight first found that comparison-only participants were treated as dangling, evidence-event links were optional, and measured properties were implicit. V3 was corrected before execution; repeated preflight returned `GO`.

## Scientific Improvement

The generated K1 frame correctly preserved:

- outcome: IL-1beta;
- measured property: `EXPRESSION`;
- left contexts: EBV-transformed LCLs and group III BL cells;
- right comparator: group I BL cells;
- effect direction: `INCREASE`;
- operator: `GREATER_THAN`;
- evidence event: E1;
- RT-PCR measurement context;
- zero invented mechanism, magnitude, significance, or baseline.

## Failed Gate

E1 also placed group I BL cells in its generic `CONTEXT` list. That creates a separately queryable edge asserting that the `INCREASE` event applies in the comparator population. The source supports the increase on the left relative to group I, not an increase in group I.

The final adjudicator assigned:

- source understanding: `CORRECT`;
- K1: `VALID`;
- E1 comparator edge: `UNSUPPORTED`;
- combined ledger: `FAIL`;
- unsupported content: `PRESENT`;
- V3 versus V2: `PARTIAL_GAIN`.

## Next Invariant

Right-side comparison participants must not also appear as generic Context roles on the comparison's evidence event unless the source independently asserts a separate event for that side. Comparison references count toward ledger connectivity and must not be duplicated into event roles merely to avoid dangling identities.

No untouched qualification run is authorized.
