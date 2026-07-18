# TG-04 Nested Event Holdout: Repeat 1

## Decision

**STOP_AND_RECALIBRATE_NESTED_EVENT_EXTRACTION**

This was the first and only fresh repeat. The deterministic gate failed, so
repeats 2 and 3 were not run. The unit is now exposed and may be used only as a
development regression, never as fresh qualification evidence.

## Sealed Unit

- Corpus: BioNLP-ST 2011 GENIA development archive
- Archive SHA-256: `f70e5f6d6e2a7f7fcdb5c8671715f3909a77662a6238015b2916ce939f2a890f`
- Case: `bionlp-ge-2011-holdout:PMID-9233802`
- Input SHA-256: `9e9ca12cb6b082b4dfcf925100a95eed632329c20b5f86c8a2ce4e66fafcf65c`
- Report SHA-256: `97d984a6429df4e7bf70fd49964d9efab911c9f9677c8910f9d06654f6d9f129`
- Model: configured `openai:gpt-5.6-luna`; executed `openai/gpt-5.6-luna`

Source unit:

> ZEB blocks the activity of c-Myb and Ets individually, but together the
> factors synergize to resist this repression.

## What Worked

- Both provider calls completed with accepted structured outputs.
- Both provider receipts were independently retrieved and verified live.
- No invalid agent response, binding rejection, identity mismatch, or
  deterministic extraction fallback occurred.
- The extractor recovered the sealed inner event: ZEB negatively regulates
  c-Myb.
- It also recovered a valid coordinated sibling: ZEB negatively regulates Ets.
- The extractor and verifier both classified the unit as a finding and agreed
  that the three proposed candidates were source-entailed.

## What Failed

- Artana did not connect `this repression` to the earlier `blocks` event.
- The outer resistance claim therefore had no controlled-event link.
- `the factors` was typed as `OTHER_ENTITY`; the verifier correctly rejected
  it for trusted projection because the antecedents are the proteins c-Myb and
  Ets.
- The sealed outer event and complete two-event graph were not recovered.

Failed requirements:

- `all_candidates_structure_trusted`
- `sealed_outer_event_recovered_once`
- `sealed_event_link_recovered_once`
- `complete_sealed_graph_recovered_once`
- `controlled_event_link_count_exact`

## Root Cause

The current controlled-event linker requires literal source containment: the
outer BIOLOGICAL_PROCESS span must contain the inner trigger and participants.
That works for phrases such as `TGF-beta induction of Foxp3`, but cannot express
anaphoric references such as `this repression`. The inventory contract also has
no machine-readable antecedent identity for `the factors`.

This is a representation gap, not merely a weaker-model failure. The model
recognized the scientific meaning, but Artana had no typed output field through
which it could preserve the reference.

## Independent Source Check

The PubMed record for PMID 9233802 confirms the title *c-Myb and Ets proteins
synergize to overcome transcriptional repression by ZEB* and repeats the sealed
sentence in the abstract. This supports the extractor's additional Ets event
and indicates that the plural `the factors` refers to c-Myb and Ets together.

The BioNLP outer event names only c-Myb as its direct cause. That annotation is
useful minimum structure, but it is narrower than the article's explicit plural
meaning. Future qualification must preserve exact benchmark fidelity and also
admit pre-adjudicated, source-entailed projection alternatives.

Authoritative source: <https://pubmed.ncbi.nlm.nih.gov/9233802/>

## Next Controlled Loop

1. Add an agent-authored, source-bound antecedent contract for anaphoric event
   themes and entity groups.
2. Resolve only the agent-declared source references deterministically; never
   infer biomedical antecedents in fallback code.
3. Use this exposed unit as a regression proving both event linking and plural
   participant preservation.
4. Select a new untouched unit content-blindly.
5. Before extraction, independently adjudicate acceptable source-supported
   graph projections and freeze them without exposing them to the extractor.
6. Run one fresh Luna repeat and stop again on any scientific gate failure.

Automatic graph persistence remains unauthorized.
