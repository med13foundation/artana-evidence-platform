# TG04 Source-General Event Discovery Checkpoint V1

Created: 2026-07-20

Decision: `ARCHITECTURE_STOP_SPECIALIZED_EXTRACTOR_REQUIRED`

The bounded offline discovery checkpoint is complete. Deterministic passage
grounding, dynamic candidate IDs, atomic scopes, and duplicate rejection work
across the exposed development fixtures. Unchanged staged V3 cannot consume
the resulting source-general event inventory without either rejecting dynamic
identities or losing scientific meaning outside its comparison-only ontology.

Per the preregistered stop rule, no source-specific workaround was added. The
current architecture path stops here. The next experiment should compare
specialized biomedical extraction systems as recall-only candidate generators,
while agents retain final scientific interpretation and adjudication.

## Custody

- Untouched source selected or accessed: no
- Provider calls: 0
- Retries or fallbacks: 0
- Frozen V10 changes: none
- Frozen staged V3 changes: none
- Graph writes: 0
- Production promotion claim: none

The checkpoint implementation and complete result are external to the product
at:

`/Users/alvaro/.codex/artana-evidence-experiments/tg04/source_general_discovery_checkpoint_v1`

Result SHA-256:
`97d6e74b05f71e82bb0eed7c5e54b184cba26407d7ad938119680cf7429a0698`

## Discovery Boundary

The discovery-agent contract accepts an arbitrary abstract and returns zero or
more findings with:

- an exact source passage;
- an exact trigger phrase;
- a categorical finding type;
- a categorical statement role: observed result, background, method, or
  hypothesis; and
- a short explanation of distinctness.

It receives no event IDs, expected cardinality, gold phrase, PMID, or
source-specific instruction. Scientific categories remain agent-owned.

Deterministic code performs only:

- exact and unique passage resolution;
- trigger resolution inside that passage;
- source-hash-and-offset candidate ID generation;
- event-local scope construction; and
- identical-span deduplication.

Absent, ambiguous, invented, or cross-scope text fails closed. Background,
method, and hypothesis candidates remain verification-required even if another
component attempts to mark them verified. Observed-result candidates also
remain verification-required until a semantic stage accepts them.

## Offline Results

| Exposed fixture | Known scopes | Recovered | Duplicates | Unsupported |
| --- | ---: | ---: | ---: | ---: |
| comparison, null, negation, statistics | 6 | 6 | 0 | 0 |
| therapeutic outcomes and utilization | 10 | 10 | 0 | 0 |
| early gene therapy, safety, uncertainty | 8 | 8 | 0 | 0 |
| human genetics | 3 | 3 | 0 | 0 |
| molecular mechanism | 4 | 4 | 0 | 0 |
| **Total** | **31** | **31** | **0** | **0** |

Deterministic exposed-fixture scope recall was `31/31 = 1.00`. Duplicate rate
was `0/31 = 0.00`, and every returned passage and trigger resolved to exact
source offsets.

This is an authored contract replay over previously exposed adjudications. It
proves the resolver and integration boundary. It does **not** prove live-agent
discovery recall or precision because provider calls were forbidden.

## Adversarial Evidence

Twelve focused tests passed. They prove:

- the prompt has no expected answer or source-specific identifier;
- production discovery files contain no eight-digit source identifiers, fixed
  event IDs, or exposed gold passages;
- every exposed scope resolves exactly;
- invented and repeated ambiguous passages fail closed;
- triggers must resolve uniquely inside their candidate passage;
- identical spans deduplicate;
- dynamic IDs are stable for the same source and offsets;
- non-result statements cannot bypass semantic verification; and
- dynamic discovery IDs are rejected by unchanged V3 transport validation.

Strict type checking passed for all nine checkpoint modules. Ruff lint and
format checks passed after the final cleanup.

## Why Unchanged V3 Fails

Dynamic IDs and event-local scopes work at the discovery boundary. They do not
work through unchanged V3 end to end.

Frozen V3 inherits a provider schema requiring exactly two findings and a
validator requiring the previously exposed identities. More importantly, its
scientific axes contain only:

- event kind: `COMPARISON`;
- direction: `HIGHER` or `UNCHANGED`;
- polarity: affirmative difference or negated difference;
- epistemic status: observed descriptive result or observed null result; and
- uncertainty: `NONE_STATED`.

Seven exposed genetics and molecular-mechanism candidates are outside that
ontology. V3 cannot faithfully represent variant association, molecular
interaction, expression regulation, mechanism, or stated uncertainty. Mapping
them to comparison categories would be deterministic scientific relabeling,
which is forbidden. Adding those categories would modify frozen V3, which is
also forbidden.

The remaining 24 replay candidates are comparison-shaped at the discovery
level, but their dynamic inventories still fail V3's fixed transport contract.
Therefore the requested acceptance condition, dynamic source-general candidates
flowing through unchanged V3, is structurally impossible.

## Specialized Extractor Evaluation

The next bounded checkpoint should treat a specialized extractor only as a
high-recall proposal generator. Its outputs receive no trust credit until an
agent verifies scientific type, participants, roles, polarity, uncertainty,
and support against the source.

Two evidence-backed candidates are:

1. **PubTator 3 / BioREx**, as the broad first lane. PubTator 3 exposes six
   biomedical entity families and BioREx relations including treatment,
   causation, comparison, interaction, association, correlation, inhibition,
   and stimulation. Its API and breadth make it practical for a source-general
   recall experiment.
2. **DeepEventMine**, as the nested molecular-event lane. It jointly extracts
   entities, triggers, argument roles, and nested events. This better matches
   mechanism-heavy sources, but its published benchmarks are concentrated in
   BioNLP molecular event corpora, so general clinical coverage cannot be
   assumed.

Primary references:

- PubTator 3 tutorial: <https://www.ncbi.nlm.nih.gov/research/pubtator3/tutorial>
- PubTator 3 API: <https://www.ncbi.nlm.nih.gov/research/pubtator3/api>
- PubTator 3 paper: <https://pmc.ncbi.nlm.nih.gov/articles/PMC11223843/>
- DeepEventMine paper: <https://pmc.ncbi.nlm.nih.gov/articles/PMC7750964/>

## Recommended Next Checkpoint

Run an offline, exposed-source comparison with three candidate inventories:

1. authored exposed scopes as the recall ceiling;
2. PubTator 3 / BioREx proposals; and
3. DeepEventMine proposals for molecular sources.

Normalize only exact spans, triggers, source offsets, and provenance. Measure
candidate scope recall, invented-span count, duplicate rate, and extraction
coverage by source family deterministically. Agents then accept, correct,
extend, reject, or abstain on each proposal using a new source-general staged
semantic contract derived from V3's separation of responsibilities.

V3 remains frozen as historical evidence. The new contract must not silently
call itself V3, and no untouched source should be consumed until the exposed
comparison shows higher recall without unsupported candidates.

## Conclusion

The discovery checkpoint succeeded at grounding and failed at unchanged-V3
integration. That is useful progress: the blocker is no longer passage custody
or dynamic scope construction. It is the scientific expressiveness and fixed
cardinality of the frozen semantic contract. The honest response is to stop
expanding that contract in place and test specialized recall generators behind
agent-owned adjudication.
